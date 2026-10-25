"""Build the README's wordmark and architecture diagram, in light and dark variants.

    uv run --with fonttools --with brotli python tools/readme/build.py

Writes docs/assets/{wordmark,architecture}-{light,dark}.svg. The diagram tells the story of one
request from docs/DESIGN.md: a write of 150 % is blocked against the device file's 100 % limit on
the limit-line gauge, and a write of 60 % is granted, reaches the device and reports back. The
numbers match the demo fan in openhal/hub (max 100 %, rate 20 %/s, current 20 %).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from svgtext import path, width

OUT = Path(__file__).resolve().parents[2] / "docs" / "assets"

THEMES = {
    "light": {
        "text": "#1F2328",
        "text2": "#59636E",
        "node": "#F6F8FA",
        "border": "#D0D7DE",
        "hero": "#1F2328",
        "red": "#B3261E",
        "green": "#276B43",
        "blue": "#2D5B8C",
        "track": "#D0D7DE",
        "arrow": "#59636E",
    },
    "dark": {
        "text": "#E6EDF3",
        "text2": "#9198A1",
        "node": "#161B22",
        "border": "#30363D",
        "hero": "#E6EDF3",
        "red": "#EE6B62",
        "green": "#5CB884",
        "blue": "#79A9DA",
        "track": "#3D444D",
        "arrow": "#9198A1",
    },
}
CAUTION, ON_CAUTION = "#F2B705", "#15181B"


class Canvas:
    def __init__(self, w: int, h: int, title: str, desc: str) -> None:
        self.w, self.h = w, h
        self.parts: list[str] = []
        self.title, self.desc = title, desc

    def add(self, markup: str) -> None:
        if markup:
            self.parts.append(markup)

    def rect(self, x: float, y: float, w: float, h: float, fill: str, stroke: str = "none", sw: float = 1) -> None:
        self.add(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="3" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{sw}"/>'
        )

    def line(self, points: list[tuple[float, float]], color: str, w: float = 2, head: bool = True) -> None:
        coords = " ".join(f"{x},{y}" for x, y in points)
        self.add(
            f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="{w}" '
            'stroke-linejoin="round" stroke-linecap="round"/>'
        )
        if head:
            (x0, y0), (x1, y1) = points[-2], points[-1]
            dx, dy = (x1 > x0) - (x1 < x0), (y1 > y0) - (y1 < y0)
            size = 6
            if dx:
                tri = [(x1, y1), (x1 - dx * size * 1.4, y1 - size), (x1 - dx * size * 1.4, y1 + size)]
            else:
                tri = [(x1, y1), (x1 - size, y1 - dy * size * 1.4), (x1 + size, y1 - dy * size * 1.4)]
            self.add(f'<polygon points="{" ".join(f"{x},{y}" for x, y in tri)}" fill="{color}"/>')

    def text(self, value: str, x: float, y: float, **style: object) -> None:
        self.add(path(value, x, y, **style))  # type: ignore[arg-type]

    def svg(self) -> str:
        body = "\n".join(self.parts)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" role="img" aria-labelledby="t d">\n'
            f'<title id="t">{self.title}</title>\n<desc id="d">{self.desc}</desc>\n{body}\n</svg>\n'
        )


def legend(c: Canvas, value: str, x: float, y: float, color: str) -> None:
    c.text(value.upper(), x, y, face="label", size=12, weight=700, fill=color, tracking=0.08)


def wordmark(theme: dict[str, str]) -> str:
    size = 44
    w = round(width("OpenHAL", "label", size, 700)) + 4
    c = Canvas(w, 52, "OpenHAL", "The OpenHAL wordmark.")
    c.text("OpenHAL", 2, 40, face="label", size=size, weight=700, fill=theme["text"])
    return c.svg()


# Layout, left to right. The kernel and its gauge get the most room.
CLIENT = (8, 160)
KERNEL = (216, 340)
DRIVER = (596, 96)
DEVICE = (732, 160)
TOP, BOTTOM = 140, 340
TRACK_X, TRACK_W, TRACK_Y = 236, 300, 230


def gauge_x(percent: float) -> float:
    return TRACK_X + percent * TRACK_W / 160


def architecture(t: dict[str, str]) -> str:
    c = Canvas(
        900,
        400,
        "How one write flows through OpenHAL",
        "An MCP client asks to set fan_speed to 150 percent. The device file gives a limit of 100 percent. "
        "The safety kernel draws both on its limit-line gauge and blocks the write as above_max. "
        "The client then asks for 60 percent, which is within the limit and rate, so the kernel issues a "
        "single-use grant. The driver uses the grant to send 60 percent to the device, and the device "
        "reports fan_speed 60 percent back.",
    )
    mono = {"face": "mono", "weight": 400}
    body = {"face": "text", "weight": 400}
    cx, cw = CLIENT
    kx, kw = KERNEL
    dx, dw = DRIVER
    vx, vw = DEVICE
    h = BOTTOM - TOP
    blocked_y, granted_y = 252, 300

    # Nodes
    c.rect(cx, TOP, cw, h, t["node"], t["border"])
    c.rect(kx, 24, kw, 68, t["node"], t["border"])
    c.rect(kx, TOP, kw, h, t["node"], t["hero"], 2)
    c.rect(dx, TOP, dw, h, t["node"], t["border"])
    c.rect(vx, TOP, vw, h, t["node"], t["border"])

    # Client
    legend(c, "Client", cx + 16, 164, t["text2"])
    c.text("Any MCP client", cx + 16, 190, size=15, fill=t["text"], face="text", weight=700)
    c.text("Claude, Cursor, ...", cx + 16, 210, size=13, fill=t["text2"], **body)
    c.text("CLI, Python", cx + 16, 228, size=13, fill=t["text2"], **body)
    c.text("fan_speed = 150 %", cx + cw - 8, blocked_y + 4, size=11, fill=t["text"], anchor="end", **mono)
    c.text("fan_speed = 60 %", cx + cw - 8, granted_y + 4, size=11, fill=t["text"], anchor="end", **mono)

    # Device file and its limit
    legend(c, "Device file", kx + 16, 48, t["text2"])
    c.text("fan_speed  max 100 %  rate 20 %/s", kx + 16, 76, size=12, fill=t["text"], **mono)
    mid = kx + kw / 2
    c.line([(mid, 92), (mid, TOP - 1)], t["arrow"])
    c.text("limit", mid + 10, 122, size=12, fill=t["text2"], **body)

    # Requests into the kernel
    c.line([(cx + cw, blocked_y), (kx - 1, blocked_y)], t["red"])
    c.line([(cx + cw, granted_y), (kx - 1, granted_y)], t["green"])

    # Kernel and the limit-line gauge, the hero
    legend(c, "Safety kernel", kx + 16, 164, t["text2"])
    c.rect(TRACK_X, TRACK_Y - 4, TRACK_W, 8, t["track"])
    c.rect(TRACK_X, TRACK_Y - 4, gauge_x(20) - TRACK_X, 8, t["blue"])
    c.line([(gauge_x(20), TRACK_Y - 10), (gauge_x(20), TRACK_Y + 10)], t["blue"], 2, head=False)
    c.text("current 20 %", TRACK_X, TRACK_Y - 18, size=12, fill=t["blue"], **mono)
    limit = gauge_x(100)
    c.line([(limit, TRACK_Y - 34), (limit, TRACK_Y + 14)], t["red"], 3, head=False)
    flag_w = width("MAX 100 %", "label", 12, 700, 0.08) + 14
    c.rect(limit + 1.5, TRACK_Y - 34, flag_w, 18, CAUTION)
    c.text("MAX 100 %", limit + 8, TRACK_Y - 21, face="label", size=12, weight=700, fill=ON_CAUTION, tracking=0.08)
    ok = gauge_x(60)
    c.add(f'<circle cx="{ok}" cy="{TRACK_Y}" r="9" fill="{t["green"]}"/>')
    c.add(
        f'<polyline points="{ok - 4.5},{TRACK_Y} {ok - 1.2},{TRACK_Y + 3.4} {ok + 4.6},{TRACK_Y - 3.6}" fill="none" '
        f'stroke="{t["node"]}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
    )
    bad = gauge_x(150)
    c.add(f'<circle cx="{bad}" cy="{TRACK_Y}" r="9" fill="{t["node"]}" stroke="{t["red"]}" stroke-width="2.2"/>')
    c.add(
        f'<path d="M{bad - 3.8} {TRACK_Y - 3.8} L{bad + 3.8} {TRACK_Y + 3.8} M{bad + 3.8} {TRACK_Y - 3.8} '
        f'L{bad - 3.8} {TRACK_Y + 3.8}" stroke="{t["red"]}" stroke-width="2.2" stroke-linecap="round"/>'
    )
    c.text("60 % granted", ok, TRACK_Y + 30, size=12, fill=t["green"], anchor="middle", **mono)
    c.text("150 % requested", kx + kw - 12, TRACK_Y + 30, size=12, fill=t["red"], anchor="end", **mono)
    c.text("BLOCKED  above_max, limit 100 %", kx + 16, 296, size=12, fill=t["red"], **mono)
    c.text("GRANTED  within limit and rate", kx + 16, 318, size=12, fill=t["green"], **mono)

    # Grant to the driver, the driver to the device
    c.line([(kx + kw, granted_y), (dx - 1, granted_y)], t["green"])
    c.text("grant", (kx + kw + dx) / 2, granted_y - 10, size=12, fill=t["green"], anchor="middle", **body)
    legend(c, "Driver", dx + 14, 164, t["text2"])
    c.text("uses the", dx + 14, 190, size=13, fill=t["text"], **body)
    c.text("grant once", dx + 14, 208, size=13, fill=t["text"], **body)
    c.line([(dx + dw, granted_y), (vx - 1, granted_y)], t["green"])
    c.text("60 %", (dx + dw + vx) / 2, granted_y - 10, size=11, fill=t["green"], anchor="middle", **mono)

    # Devices, real examples with their drivers
    legend(c, "Devices", vx + 12, 164, t["text2"])
    examples = [
        ("Klipper printer", "via Moonraker"),
        ("SCPI multimeter", "via VISA"),
        ("ESP32 board", "via OpenHAL firmware"),
        ("Home Assistant plugs", "via its API"),
    ]
    y = 190
    for name, via in examples:
        c.text(name, vx + 12, y, size=13, fill=t["text"], **body)
        c.text(via, vx + 12, y + 15, size=12, fill=t["text2"], **body)
        y += 38

    # The device reports back
    back = vx + vw / 2
    c.line([(back, BOTTOM), (back, 376), (cx + cw / 2, 376), (cx + cw / 2, BOTTOM + 1)], t["arrow"])
    c.text("reading  fan_speed = 60 %", 450, 368, size=11, fill=t["text2"], anchor="middle", **mono)
    return c.svg()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, theme in THEMES.items():
        (OUT / f"wordmark-{name}.svg").write_text(wordmark(theme))
        (OUT / f"architecture-{name}.svg").write_text(architecture(theme))
    print(f"Wrote wordmark and architecture SVGs to {OUT}")


if __name__ == "__main__":
    main()
