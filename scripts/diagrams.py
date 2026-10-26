"""Build the house-style diagrams in docs/diagrams from their D2 sources, light and dark.

D2 lays out the nodes. This script then makes the result match docs/DESIGN.md: our fonts, 1.5 px
strokes, connector labels above their lines, a transparent background and an accessible title and
description. The flow diagram also gets its return line routed over the top with right angles only
and a flowing dash animation on the wires that stops under prefers-reduced-motion.

The architecture and sequence diagrams redraw the Mermaid blocks in docs and the spec. The website
shows the D2 version of a block only while docs/diagrams/diagrams.json records that block's current
text, so a changed block falls back to Mermaid until its D2 source is updated and rebuilt. Run it
through scripts/build-diagrams.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
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
    "light": {"accent": "#1D5FB4", "line": "#8A919C", "blocked": "#B42318", "label": "#4F5661", "border": "#DADDE2"},
    "dark": {"accent": "#7DB2F0", "line": "#5A626D", "blocked": "#F07068", "label": "#A0A7B1", "border": "#2A2F36"},
}
SHARED = ("theme-light.d2", "theme-dark.d2", "house.d2")
MANIFEST = DIAGRAMS / "diagrams.json"


@dataclass(frozen=True)
class Redraw:
    """A D2 diagram that redraws one Mermaid block of a page."""

    source: str
    index: int
    title: str
    desc: str


REDRAWS = {
    "architecture-components": Redraw(
        "docs/ARCHITECTURE.md",
        0,
        "OpenHAL components",
        "Four clients, the MCP server, the CLI, the Python library and the dashboard, call the hub's local API. "
        "Inside the one hub process the API passes commands through tokens and principals to the safety kernel, "
        "which alone gives drivers a single-use grant and writes the audit log. The routine engine, watchdogs and "
        "confirmation queue also go through the kernel. Drivers reach the hardware and bridged systems.",
    ),
    "architecture-command": Redraw(
        "docs/ARCHITECTURE.md",
        1,
        "The life of a command",
        "An agent asks openhal mcp to water the plant. The hub API passes it to the safety kernel, which runs its "
        "checks in order. A blocked command is logged and answered with the reason. A command that needs a person "
        "is queued with an expiry. An allowed command gets a single-use grant, the driver verifies and consumes it, "
        "acts, and the kernel logs the result.",
    ),
    "architecture-discovery": Redraw(
        "docs/ARCHITECTURE.md",
        2,
        "Device discovery",
        "openhal discover looks for devices over USB, mDNS, VISA, BLE, ecosystem APIs and Raspberry Pi checks, "
        "identifies each with read-only commands, and asks the library matcher. A match offers a library file that "
        "loads read-only. A known protocol builds a draft file. An unknown device is listed and offered the driver "
        "writer.",
    ),
    "architecture-writer": Redraw(
        "docs/ARCHITECTURE.md",
        3,
        "The driver writer",
        "For an unknown device the driver writer tries a library match, then a protocol driver's self-description, "
        "then a sketch, then a manual, then read-only probing. Each path ends in a draft device file with every "
        "limit marked suggested. A person answers the limits interview, approves a staged test plan, and the writer "
        "saves the device file, scaffolding a new driver first when one is needed.",
    ),
    "architecture-routine": Redraw(
        "docs/ARCHITECTURE.md",
        4,
        "Routine execution",
        "A trigger fires a routine. The routine engine checks it is enabled and approved, then sends each read and "
        "command to the safety kernel as the routine's principal. A blocked step stops the run. An allowed step goes "
        "to the driver with a grant. The engine records the run.",
    ),
    "architecture-bridge": Redraw(
        "docs/ARCHITECTURE.md",
        5,
        "Bridges",
        "The safety kernel sends a bridge driver a write with a grant. The bridge calls the bridged system, gets the "
        "new state and returns the result. The device file governs the limits even when the bridged system has its "
        "own.",
    ),
    "architecture-stop": Redraw(
        "docs/ARCHITECTURE.md",
        6,
        "Stop",
        "A stop from any client sets the kernel's global lock first, cancels pending confirmations and pauses every "
        "routine, applies each device's safe state, reports per device, and blocks commands until a person unlocks.",
    ),
    "spec-exchange": Redraw(
        "spec/2026-10-24/architecture.md",
        0,
        "One blocked and one granted action",
        "A client asks the hub to water for 120 s. The safety kernel blocks it as above the maximum and the hub "
        "answers error -32010 LIMIT_EXCEEDED. The client asks for 20 s. Every check passes, the kernel issues a "
        "single-use grant, the driver consumes it and runs the pump, and the hub answers with a result and then a "
        "hal/value notification of the new soil moisture.",
    ),
}

FLOW_TITLE = "OpenHAL flow"
FLOW_DESC = (
    "OpenHAL flow. An AI client sends hal/action to the hub. The safety kernel checks it against the device "
    "file's limits. An allowed command gets a grant and goes through the driver to the Arduino plant waterer, "
    "and the reading comes back to the client. A command that fails a check is blocked with INTERLOCK_BLOCKED "
    "because the tank is empty."
)
FLOW_ORDER = ["hal/action", "check", "grant", "command", "reading"]
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
    "grid-rows: 2\ngrid-columns: 5\nhorizontal-gap: 90\nvertical-gap: 48",
    "grid-columns: 2\ngrid-rows: 5\nhorizontal-gap: 52\nvertical-gap: 52",
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
        for shared in SHARED:
            shutil.copy(DIAGRAMS / shared, work / shared)
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
    if match is None:
        return ""
    lines = re.findall(r"<tspan[^>]*>(.*?)</tspan>", match.group(1)) or [match.group(1)]
    return "\n".join(html.unescape(re.sub(r"<[^>]+>", "", line)) for line in lines)


def relabel(body: str, x: float, y: float) -> str:
    body = re.sub(
        r'<text x="[-\d.]+" y="[-\d.]+"',
        f'<text x="{x:.1f}" y="{y:.1f}"',
        body,
        count=1,
    )
    return re.sub(r'<tspan x="[-\d.]+"', f'<tspan x="{x:.1f}"', body)


LABEL_LINE = 17
MONO_ADVANCE = 0.632
LABEL_SIZE = 13


def center_chip(svg: str, nodes: dict[str, Box]) -> str:
    """Move the device files chip to the hub's middle, so the check wire runs level with the others."""
    chip, hub = nodes["hub.files"], nodes["hub"]
    dy = hub.cy - chip.cy
    if abs(dy) < 0.5:
        return svg
    token = base64.b64encode(b"hub.files").decode().rstrip("=")
    opening = re.compile(rf'<g class="({re.escape(token)}=*)">')
    svg, count = opening.subn(rf'<g class="\1" transform="translate(0 {dy:.1f})">', svg, count=1)
    if count:
        nodes["hub.files"] = Box(chip.x, chip.y + dy, chip.w, chip.h)
    return svg


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
    if not narrow:
        svg = center_chip(svg, nodes)
    top = min(box.y for name, box in nodes.items() if "." not in name)
    left = min(box.x for name, box in nodes.items() if "." not in name)
    route_y = top - 22
    route_x = left - 22

    flows: list[str] = []
    outcome_bottom: list[float] = []
    outcome_right: list[float] = []

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
        is_blocked = "blocked" in wire_id
        if is_blocked and label:
            below = nodes["blocked"]
            body = relabel(body, below.cx, below.y + below.h + LABEL_LINE + 2)
            body = body.replace("text-anchor:start", "text-anchor:middle", 1)
            outcome_bottom.append(below.y + below.h + 2 * LABEL_LINE + 8)
            longest = max(len(line) for line in label.split("\n")) if label else 0
            outcome_right.append(below.cx + longest * LABEL_SIZE * MONO_ADVANCE / 2 + 6)
        elif abs(y1 - y2) < 0.5 and label:
            body = relabel(body, (x1 + x2) / 2, y1 - 8)
        elif abs(x1 - x2) < 0.5 and label:
            body = relabel(body, x1 + 9, (y1 + y2) / 2 + 4)
            body = body.replace("text-anchor:middle", "text-anchor:start", 1)
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
    if outcome_bottom:
        svg = grow_bottom(svg, max(outcome_bottom))
    if outcome_right:
        svg = grow_right(svg, max(outcome_right))
    return add_title(svg, FLOW_TITLE, FLOW_DESC)


def flow_path(d: str, color: str, name: str) -> str:
    slug = re.sub(r"[^a-z]+", "-", name.lower()).strip("-") or "wire"
    return (
        f'<path class="oh-flow oh-{slug}" d="{d}" fill="none" stroke="{color}" stroke-width="1.5" '
        f'stroke-linecap="round" stroke-dasharray="{DASH} {GAP}" />'
    )


def flow_style() -> str:
    period = (DASH + GAP) * PERIODS
    delays = {slug: index * 0.35 for index, slug in enumerate(["hal-action", "check", "grant", "command", "reading"])}
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


def grow_bottom(svg: str, needed: float) -> str:
    """Grow the canvas downwards until it reaches `needed` in diagram units."""
    inner = re.search(
        r'width="(?P<w>[\d.]+)" height="(?P<h>[\d.]+)" viewBox="(?P<x>-?[\d.]+) (?P<y>-?[\d.]+) [\d.]+ [\d.]+"', svg
    )
    if inner is None:
        return svg
    room = needed - (float(inner["y"]) + float(inner["h"]))
    if room <= 0:
        return svg
    room = float(int(room + 0.999))

    def outer(match: re.Match[str]) -> str:
        w, h = float(match["w"]), float(match["h"]) + room
        return f'viewBox="0 0 {w:g} {h:g}" width="{w:g}" height="{h:g}"'

    svg = re.sub(r'viewBox="0 0 (?P<w>[\d.]+) (?P<h>[\d.]+)" width="[\d.]+" height="[\d.]+"', outer, svg, count=1)

    def grown(match: re.Match[str]) -> str:
        w, h = float(match["w"]), float(match["h"]) + room
        x, y = float(match["x"]), float(match["y"])
        return f'width="{w:g}" height="{h:g}" viewBox="{x:g} {y:g} {w:g} {h:g}"'

    return re.sub(
        r'width="(?P<w>[\d.]+)" height="(?P<h>[\d.]+)" viewBox="(?P<x>-?[\d.]+) (?P<y>-?[\d.]+) [\d.]+ [\d.]+"',
        grown,
        svg,
        count=1,
    )


def grow_right(svg: str, needed: float) -> str:
    """Grow the canvas to the right until it reaches `needed` in diagram units."""
    inner = re.search(
        r'width="(?P<w>[\d.]+)" height="(?P<h>[\d.]+)" viewBox="(?P<x>-?[\d.]+) (?P<y>-?[\d.]+) [\d.]+ [\d.]+"', svg
    )
    if inner is None:
        return svg
    room = needed - (float(inner["x"]) + float(inner["w"]))
    if room <= 0:
        return svg
    room = float(int(room + 0.999))

    def outer(match: re.Match[str]) -> str:
        w, h = float(match["w"]) + room, float(match["h"])
        return f'viewBox="0 0 {w:g} {h:g}" width="{w:g}" height="{h:g}"'

    svg = re.sub(r'viewBox="0 0 (?P<w>[\d.]+) (?P<h>[\d.]+)" width="[\d.]+" height="[\d.]+"', outer, svg, count=1)

    def grown(match: re.Match[str]) -> str:
        w, h = float(match["w"]) + room, float(match["h"])
        x, y = float(match["x"]), float(match["y"])
        return f'width="{w:g}" height="{h:g}" viewBox="{x:g} {y:g} {w:g} {h:g}"'

    return re.sub(
        r'width="(?P<w>[\d.]+)" height="(?P<h>[\d.]+)" viewBox="(?P<x>-?[\d.]+) (?P<y>-?[\d.]+) [\d.]+ [\d.]+"',
        grown,
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


LIFELINE = re.compile(r'(<g class="(?P<id>[A-Za-z0-9+/=]+)"><path d="[^"]*" )stroke="[^"]*"([^>]*?)style="[^"]*"')
MESSAGE = re.compile(r'<g class="(?P<id>[A-Za-z0-9+/=]+)(?: [\w-]+)?">(?P<body>.*?)</g>', re.S)


def mermaid_blocks(path: Path) -> list[str]:
    """Every Mermaid block of a Markdown page, in order."""
    return [match.group(1).strip() for match in re.finditer(r"^```mermaid\n(.*?)\n```", path.read_text(), re.S | re.M)]


def mermaid_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode()).hexdigest()[:16]


def restyle_lifelines(svg: str, colors: dict[str, str]) -> str:
    def solid(match: re.Match[str]) -> str:
        if " -- )" not in name_of(match["id"]):
            return match.group(0)
        return f'{match.group(1)}stroke="{colors["border"]}"{match.group(3)}style="stroke-width:1;"'

    return LIFELINE.sub(solid, svg)


def lift_message_labels(svg: str) -> str:
    """Set each straight message's label just above its line, as the flow diagram does."""

    def lift(match: re.Match[str]) -> str:
        name, body = html.unescape(name_of(match["id"])), match["body"]
        ends = re.search(r"\((?P<a>[\w.]+) -> (?P<b>[\w.]+)\)\[\d+\]$", name)
        text = re.search(r'<text x="(?P<x>[-\d.]+)" y="(?P<y>[-\d.]+)"', body)
        if ends is None or text is None:
            return match.group(0)
        steps = [float(step) for step in re.findall(r'<tspan[^>]*dy="([-\d.]+)"', body)[1:]]
        if ends["a"].split(".")[-1] == ends["b"].split(".")[-1]:
            loop = re.search(r'<path d="(?P<d>[^"]+)"', body)
            if loop is None:
                return match.group(0)
            numbers = [float(value) for value in re.findall(r"-?[\d.]+", loop["d"])]
            xs, ys = numbers[0::2], numbers[1::2]
            y = (min(ys) + max(ys)) / 2 + 4 - sum(steps) / 2
            body = relabel(body, max(xs) + 8, y).replace("text-anchor:middle", "text-anchor:start", 1)
        else:
            path = PATH_D.search(body)
            if path is None or abs(float(path["y1"]) - float(path["y2"])) > 0.5:
                return match.group(0)
            body = relabel(body, float(text["x"]), float(path["y1"]) - 7 - sum(steps))
        body = body.replace(' mask="url(#', ' data-mask="url(#')
        return match.group(0).replace(match["body"], body)

    return MESSAGE.sub(lift, svg)


def postprocess_house(svg: str, colors: dict[str, str], title: str, desc: str) -> str:
    svg = re.sub(
        r'<rect x="[-\d.]+" y="[-\d.]+" width="[\d.]+" height="[\d.]+" rx="0" fill="[^"]+" class=" fill-N7"'
        r' stroke-width="0" />',
        "",
        svg,
        count=1,
    )
    svg = svg.replace("stroke-width:2;", "stroke-width:1.5;").replace('stroke-width="2"', 'stroke-width="1.5"')
    svg = restyle_lifelines(svg, colors)
    svg = lift_message_labels(svg)
    return add_title(svg, title, desc)


def build_redraws() -> None:
    fonts = static_fonts()
    manifest = []
    for name, redraw in REDRAWS.items():
        blocks = mermaid_blocks(ROOT / redraw.source)
        if redraw.index >= len(blocks):
            sys.exit(f"{redraw.source} has no Mermaid block {redraw.index} for {name}.d2.")
        for theme, colors in THEMES.items():
            out = DIAGRAMS / f"{name}-{theme}.svg"
            raw = render_d2(DIAGRAMS / f"{name}.d2", theme, fonts, out)
            out.write_text(postprocess_house(raw, colors, redraw.title, redraw.desc))
            svgo(out)
            print(f"{out.relative_to(ROOT)}  {out.stat().st_size / 1024:.0f} KB")
        manifest.append(
            {
                "name": name,
                "source": redraw.source,
                "index": redraw.index,
                "mermaid": mermaid_hash(blocks[redraw.index]),
                "title": redraw.title,
            }
        )
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{MANIFEST.relative_to(ROOT)}")


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
    build_redraws()
