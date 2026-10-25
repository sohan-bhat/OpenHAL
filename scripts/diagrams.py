"""Build the house-style diagrams in docs/diagrams from their D2 sources, light and dark.

D2 lays out the nodes on a grid. This script then makes the result match docs/DESIGN.md: our fonts,
1.5 px strokes, connector labels above their lines, the return line routed over the top with right
angles only, a transparent background, an accessible title and description, and a flowing dash
animation on the wires that stops under prefers-reduced-motion. Run it through scripts/build-diagrams.
"""

from __future__ import annotations

import base64
import html
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parents[1]
DIAGRAMS = ROOT / "docs" / "diagrams"
FONTS = ROOT / "design" / "fonts"
CACHE = ROOT / ".cache" / "diagram-fonts"
D2_VERSION = "v0.9.0"
SVGO = "svgo@4.1.0"

STATIC_FONTS = {
    "regular": ("atkinson-hyperlegible-next-latin-wght-normal.woff2", 400),
    "italic": ("atkinson-hyperlegible-next-latin-wght-normal.woff2", 400),
    "semibold": ("atkinson-hyperlegible-next-latin-wght-normal.woff2", 600),
    "bold": ("atkinson-hyperlegible-next-latin-wght-normal.woff2", 700),
    "mono": ("atkinson-hyperlegible-mono-latin-wght-normal.woff2", 400),
    "mono-italic": ("atkinson-hyperlegible-mono-latin-wght-normal.woff2", 400),
    "mono-semibold": ("atkinson-hyperlegible-mono-latin-wght-normal.woff2", 600),
    "mono-bold": ("atkinson-hyperlegible-mono-latin-wght-normal.woff2", 700),
}

THEMES = {
    "light": {"accent": "#1D5FB4", "line": "#8A919C", "blocked": "#B42318", "label": "#4F5661"},
    "dark": {"accent": "#7DB2F0", "line": "#5A626D", "blocked": "#F07068", "label": "#A0A7B1"},
}

FLOW_TITLE = "OpenHAL flow"
FLOW_DESC = (
    "OpenHAL flow: an AI client sends hal/write to the hub; the safety kernel checks it against the device "
    "file's limits; allowed commands go through the driver to the device, and over-limit commands are blocked "
    "with LIMIT_EXCEEDED."
)
FLOW_ORDER = ["hal/write", "check", "grant", "command", "reading"]
TOP_ROOM = 40
DASH, GAP, PERIODS = 6, 10, 4


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


def static_fonts() -> dict[str, Path]:
    CACHE.mkdir(parents=True, exist_ok=True)
    made = {}
    for role, (source, weight) in STATIC_FONTS.items():
        target = CACHE / f"{source.removesuffix('.woff2')}-{weight}.ttf"
        if not target.exists():
            font = instancer.instantiateVariableFont(TTFont(FONTS / source), {"wght": weight})
            font.flavor = None
            font.save(target)
        made[role] = target
    return made


def d2_binary() -> str:
    found = shutil.which("d2")
    local = Path.home() / ".local" / "bin" / "d2"
    if found is None and local.exists():
        found = str(local)
    if found is None:
        sys.exit(f"The D2 CLI ({D2_VERSION}) is not on PATH. See docs/TOOLING.md.")
    version = subprocess.run([found, "--version"], capture_output=True, text=True, check=True).stdout.strip()  # noqa: S603
    if version != D2_VERSION:
        print(f"warning: D2 {version} differs from the pinned {D2_VERSION}", file=sys.stderr)
    return found


NARROW_GRID = (
    "grid-rows: 2\ngrid-columns: 5\nhorizontal-gap: 76\nvertical-gap: 56",
    "grid-columns: 2\ngrid-rows: 5\nhorizontal-gap: 64\nvertical-gap: 52",
)


def render_d2(source: Path, theme: str, fonts: dict[str, Path], out: Path, narrow: bool = False) -> str:
    text = source.read_text().replace("@theme-light", f"@theme-{theme}")
    if narrow:
        if NARROW_GRID[0] not in text:
            sys.exit(
                "flow.d2 no longer starts with the expected grid lines. Update NARROW_GRID in scripts/diagrams.py."
            )
        text = text.replace(*NARROW_GRID)
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        for theme_file in DIAGRAMS.glob("theme-*.d2"):
            shutil.copy(theme_file, work / theme_file.name)
        (work / source.name).write_text(text)
        flags = [f"--font-{role}={path}" for role, path in fonts.items()]
        subprocess.run(  # noqa: S603
            [
                d2_binary(),
                "--layout",
                "elk",
                "--elk-padding",
                "[top=34,left=10,bottom=10,right=10]",
                "--pad",
                "12",
                "--scale",
                "1",
                *flags,
                str(work / source.name),
                str(out),
            ],
            check=True,
            capture_output=True,
        )
    return out.read_text()


def name_of(token: str) -> str:
    try:
        return html.unescape(base64.b64decode(token + "=" * (-len(token) % 4)).decode())
    except (ValueError, UnicodeDecodeError):
        return ""


NODE = re.compile(
    r'<g class="(?P<id>[A-Za-z0-9+/=]+)(?: [\w-]+)?"(?: style=\'opacity:0\')?><g class="shape" >'
    r'<rect x="(?P<x>[-\d.]+)" y="(?P<y>[-\d.]+)" width="(?P<w>[\d.]+)" height="(?P<h>[\d.]+)"'
)
WIRE = re.compile(r'<g class="(?P<id>[A-Za-z0-9+/=]+) wire">(?P<body>.*?)</g>', re.S)
PATH_D = re.compile(r'<path d="M (?P<x1>[-\d.]+) (?P<y1>[-\d.]+) L (?P<x2>[-\d.]+) (?P<y2>[-\d.]+)"')
SPACER = re.compile(r"<g class=\"[A-Za-z0-9+/=]+ spacer\" style='opacity:0'>.*?</g></g>", re.S)


def boxes(svg: str) -> dict[str, Box]:
    found = {}
    for match in NODE.finditer(svg):
        found[name_of(match["id"])] = Box(float(match["x"]), float(match["y"]), float(match["w"]), float(match["h"]))
    return found


def label_text(body: str) -> str:
    match = re.search(r"<text[^>]*>(.*?)</text>", body)
    return html.unescape(match.group(1)) if match else ""


def relabel(body: str, x: float, y: float) -> str:
    return re.sub(
        r'<text x="[-\d.]+" y="[-\d.]+"',
        f'<text x="{x:.1f}" y="{y:.1f}"',
        body,
        count=1,
    )


def postprocess_flow(svg: str, colors: dict[str, str], narrow: bool = False) -> str:
    svg = SPACER.sub("", svg)
    svg = re.sub(
        r'<rect x="[-\d.]+" y="[-\d.]+" width="[\d.]+" height="[\d.]+" rx="0" fill="[^"]+" class=" fill-N7"'
        r' stroke-width="0" />',
        "",
        svg,
        count=1,
    )
    svg = svg.replace("stroke-width:2;", "stroke-width:1.5;").replace('stroke-width="2"', 'stroke-width="1.5"')
    svg = svg.replace(' mask="url(#', ' data-mask="url(#')
    nodes = boxes(svg)
    top = min(box.y for name, box in nodes.items() if "." not in name)
    left = min(box.x for name, box in nodes.items() if "." not in name)
    route_y = top - 22
    route_x = left - 22

    flows: list[str] = []

    def rewrite(match: re.Match[str]) -> str:
        wire_id, body = name_of(match["id"]), match["body"]
        label = label_text(body)
        path = PATH_D.search(body)
        if path is None:
            return match.group(0)
        x1, y1, x2, y2 = (float(path[k]) for k in ("x1", "y1", "x2", "y2"))
        if "&lt;-" in wire_id or "<-" in wire_id:
            device, client = nodes["device"], nodes["client"]
            if narrow:
                d = (
                    f"M {device.x:.1f} {device.cy:.1f} L {route_x:.1f} {device.cy:.1f} "
                    f"L {route_x:.1f} {client.cy:.1f} L {client.x - 1:.1f} {client.cy:.1f}"
                )
            else:
                d = (
                    f"M {device.cx:.1f} {device.y:.1f} L {device.cx:.1f} {route_y:.1f} "
                    f"L {client.cx:.1f} {route_y:.1f} L {client.cx:.1f} {client.y - 1:.1f}"
                )
            body = re.sub(r'<path d="[^"]*"', f'<path d="{d}"', body, count=1)
            body = re.sub(r' marker-start="[^"]*"', "", body)
            body = body.replace("<path d=", '<path marker-end="url(#oh-head-line)" d=', 1)
            if narrow:
                middle = (device.cy + client.cy) / 2
                body = relabel(body, route_x - 7, middle)
                body = body.replace(
                    'class="text-mono', f'transform="rotate(-90 {route_x - 7:.1f} {middle:.1f})" class="text-mono', 1
                )
            else:
                body = relabel(body, (device.cx + client.cx) / 2, route_y - 7)
            flows.append(flow_path(d, colors["line"], "reading"))
            return f'<g class="{match["id"]} wire">{body}</g>'
        if "files" in wire_id:
            chip = nodes["hub.files"]
            if narrow:
                x1 = x2 = chip.cx
            else:
                y1 = y2 = chip.cy
            d = f"M {x1:.1f} {y1:.1f} L {x2:.1f} {y2:.1f}"
            body = re.sub(r'<path d="[^"]*"', f'<path d="{d}"', body, count=1)
        else:
            d = f"M {x1:.1f} {y1:.1f} L {x2:.1f} {y2:.1f}"
        if abs(y1 - y2) < 0.5 and label:
            body = relabel(body, (x1 + x2) / 2, y1 - 8)
        elif abs(x1 - x2) < 0.5 and label:
            body = relabel(body, x1 + 9, (y1 + y2) / 2 + 4)
            body = body.replace("text-anchor:middle", "text-anchor:start", 1)
        is_blocked = "blocked" in wire_id
        color = colors["blocked"] if is_blocked else colors["accent"]
        flows.append(flow_path(d, color, "blocked" if is_blocked else label))
        return f'<g class="{match["id"]} wire">{body}</g>'

    svg = WIRE.sub(rewrite, svg)
    marker = (
        f'<marker id="oh-head-line" markerWidth="10" markerHeight="12" refX="7" refY="6" viewBox="0 0 10 12" '
        f'orient="auto" markerUnits="userSpaceOnUse"><polygon points="0,0 10,6 0,12" fill="{colors["line"]}" />'
        f"</marker>"
    )
    style = flow_style()
    insert = f'<defs>{marker}</defs><style type="text/css"><![CDATA[{style}]]></style>'
    svg = svg.replace("</svg></svg>", f'{insert}<g class="oh-flows">{"".join(flows)}</g></svg></svg>', 1)
    svg = grow_left(svg, TOP_ROOM) if narrow else grow_top(svg, TOP_ROOM)
    return add_title(svg, FLOW_TITLE, FLOW_DESC)


def flow_path(d: str, color: str, name: str) -> str:
    slug = re.sub(r"[^a-z]+", "-", name.lower()).strip("-") or "wire"
    return (
        f'<path class="oh-flow oh-{slug}" d="{d}" fill="none" stroke="{color}" stroke-width="1.5" '
        f'stroke-linecap="round" stroke-dasharray="{DASH} {GAP}" />'
    )


def flow_style() -> str:
    period = (DASH + GAP) * PERIODS
    delays = {slug: index * 0.35 for index, slug in enumerate(["hal-write", "check", "grant", "command", "reading"])}
    rules = [
        f"@keyframes oh-flow {{ from {{ stroke-dashoffset: {period}; }} to {{ stroke-dashoffset: 0; }} }}",
        f"@keyframes oh-flow-pause {{ 0% {{ stroke-dashoffset: {period}; }} 70% {{ stroke-dashoffset: 0; }} "
        "100% { stroke-dashoffset: 0; } }",
        ".oh-flow { animation: oh-flow 2.4s ease-in-out infinite; }",
        ".oh-blocked { animation: oh-flow-pause 3s ease-in-out infinite; animation-delay: 0.7s; }",
        ".wire path.connection { stroke-opacity: 0.3; }",
    ]
    rules += [f".oh-{slug} {{ animation-delay: {delay:.2f}s; }}" for slug, delay in delays.items()]
    rules.append(
        "@media (prefers-reduced-motion: reduce) { .oh-flow { animation: none; display: none; } "
        ".wire path.connection { stroke-opacity: 1; } }"
    )
    return "\n".join(rules)


def grow_top(svg: str, room: int) -> str:
    def outer(match: re.Match[str]) -> str:
        w, h = float(match["w"]), float(match["h"]) + room
        return f'viewBox="0 0 {w:g} {h:g}" width="{w:g}" height="{h:g}"'

    svg = re.sub(r'viewBox="0 0 (?P<w>[\d.]+) (?P<h>[\d.]+)" width="[\d.]+" height="[\d.]+"', outer, svg, count=1)

    def inner(match: re.Match[str]) -> str:
        w, h = float(match["w"]), float(match["h"]) + room
        x, y = float(match["x"]), float(match["y"]) - room
        return f'width="{w:g}" height="{h:g}" viewBox="{x:g} {y:g} {w:g} {h:g}"'

    return re.sub(
        r'width="(?P<w>[\d.]+)" height="(?P<h>[\d.]+)" viewBox="(?P<x>-?[\d.]+) (?P<y>-?[\d.]+) [\d.]+ [\d.]+"',
        inner,
        svg,
        count=1,
    )


def grow_left(svg: str, room: int) -> str:
    def outer(match: re.Match[str]) -> str:
        w, h = float(match["w"]) + room, float(match["h"])
        return f'viewBox="0 0 {w:g} {h:g}" width="{w:g}" height="{h:g}"'

    svg = re.sub(r'viewBox="0 0 (?P<w>[\d.]+) (?P<h>[\d.]+)" width="[\d.]+" height="[\d.]+"', outer, svg, count=1)

    def inner(match: re.Match[str]) -> str:
        w, h = float(match["w"]) + room, float(match["h"])
        x, y = float(match["x"]) - room, float(match["y"])
        return f'width="{w:g}" height="{h:g}" viewBox="{x:g} {y:g} {w:g} {h:g}"'

    return re.sub(
        r'width="(?P<w>[\d.]+)" height="(?P<h>[\d.]+)" viewBox="(?P<x>-?[\d.]+) (?P<y>-?[\d.]+) [\d.]+ [\d.]+"',
        inner,
        svg,
        count=1,
    )


def add_title(svg: str, title: str, desc: str) -> str:
    return re.sub(
        r"(<svg xmlns=\"http://www.w3.org/2000/svg\"[^>]*?)>",
        lambda m: (
            f'{m.group(1)} role="img" aria-labelledby="oh-title oh-desc"><title id="oh-title">'
            f'{html.escape(title)}</title><desc id="oh-desc">{html.escape(desc)}</desc>'
        ),
        svg,
        count=1,
    )


def svgo(path: Path) -> None:
    config = Path(__file__).with_name("svgo.config.mjs")
    npx = shutil.which("npx")
    if npx is None:
        sys.exit("npx is not on PATH. Install Node.js 22 or newer. See docs/TOOLING.md.")
    subprocess.run([npx, "--yes", SVGO, "--config", str(config), str(path)], check=True, capture_output=True)  # noqa: S603


def build_flow() -> None:
    fonts = static_fonts()
    for narrow in (False, True):
        for theme, colors in THEMES.items():
            out = DIAGRAMS / f"flow{'-narrow' if narrow else ''}-{theme}.svg"
            raw = render_d2(DIAGRAMS / "flow.d2", theme, fonts, out, narrow)
            out.write_text(postprocess_flow(raw, colors, narrow))
            svgo(out)
            print(f"{out.relative_to(ROOT)}  {out.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    build_flow()
