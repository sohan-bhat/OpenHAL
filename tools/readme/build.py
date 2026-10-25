"""Build the README's images in the protocol theme, in light and dark variants.

    uv run --with fonttools --with brotli python tools/readme/build.py

Writes docs/assets/{wordmark,trace,sequence}-{light,dark}.svg. The trace is the signature from
docs/DESIGN.md: a hal/write of 150 % answered with -32010 LIMIT_EXCEEDED, then a granted one. The
sequence diagram follows the same two writes from Client to Device. Names and codes match
docs/adr/0015-openhal-hub-protocol.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from svgtext import path, width

OUT = Path(__file__).resolve().parents[2] / "docs" / "assets"

THEMES = {
    "light": {
        "surface": "#F4F5F7",
        "border": "#DADDE2",
        "text": "#15181C",
        "text2": "#4F5661",
        "accent": "#1D5FB4",
        "ok": "#1E7A44",
        "blocked": "#B42318",
    },
    "dark": {
        "surface": "#15181D",
        "border": "#2A2F36",
        "text": "#E7EAEE",
        "text2": "#A0A7B1",
        "accent": "#7DB2F0",
        "ok": "#5BC58A",
        "blocked": "#F07068",
    },
}

# The example exchange. LIMIT_EXCEEDED's reason follows the ADR 0015 template.
DEVICE, CHANNEL = "desk-fan", "fan_speed"
REASON = ("fan_speed 150 % exceeds the limit of 100 %", "(desk-fan.hal.yaml, confirmed by sohan 2026-10-24)")


class Canvas:
    def __init__(self, w: int, h: int, title: str, desc: str) -> None:
        self.w, self.h, self.title, self.desc = w, h, title, desc
        self.parts: list[str] = []

    def add(self, markup: str) -> None:
        if markup:
            self.parts.append(markup)

    def rect(self, x: float, y: float, w: float, h: float, fill: str, stroke: str = "none", r: float = 6) -> None:
        self.add(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" '
            'stroke-width="1"/>'
        )

    def arrow(self, x0: float, y: float, x1: float, color: str, dashed: bool = False) -> None:
        """A horizontal arrow in the house style, 1.5 px with a 6 px filled head at x1."""
        direction = 1 if x1 > x0 else -1
        end = x1 - direction * 6
        dash = ' stroke-dasharray="5 4"' if dashed else ""
        self.add(f'<line x1="{x0}" y1="{y}" x2="{end}" y2="{y}" stroke="{color}" stroke-width="1.5"{dash}/>')
        back = x1 - direction * 7
        self.add(f'<polygon points="{x1},{y} {back},{y - 4} {back},{y + 4}" fill="{color}"/>')

    def vline(self, x: float, y0: float, y1: float, color: str) -> None:
        self.add(f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y1}" stroke="{color}" stroke-width="1.5"/>')

    def text(self, value: str, x: float, y: float, **style: object) -> float:
        self.add(path(value, x, y, **style))  # type: ignore[arg-type]
        return width(value, str(style["face"]), float(style["size"]), int(style.get("weight", 400)))  # type: ignore[arg-type,call-overload]

    def svg(self) -> str:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" role="img" aria-labelledby="t d">\n'
            f'<title id="t">{self.title}</title>\n<desc id="d">{self.desc}</desc>\n'
            + "\n".join(self.parts)
            + "\n</svg>\n"
        )


Run = tuple[str, str, int]


def json_runs(t: dict[str, str], pairs: list[tuple[str, str | int]]) -> list[Run]:
    """A one-line JSON object as (text, color, weight) runs in the house syntax theme."""
    runs: list[Run] = [("{ ", t["text2"], 400)]
    for index, (key, value) in enumerate(pairs):
        runs += [(f'"{key}"', t["text2"], 400), (": ", t["text2"], 400)]
        runs.append((f'"{value}"', t["text"], 400) if isinstance(value, str) else (str(value), t["accent"], 400))
        if index < len(pairs) - 1:
            runs.append((", ", t["text2"], 400))
    runs.append((" }", t["text2"], 400))
    return runs


def draw_runs(c: Canvas, runs: list[Run], x: float, y: float, size: float) -> None:
    for value, color, weight in runs:
        x += c.text(value, x, y, face="mono", size=size, fill=color, weight=weight)


def mark(c: Canvas, x: float, y: float, scale: float, color: str) -> None:
    """The mark on its 16 unit grid. A request stroke meets a stop bar, a return stroke points back."""

    def line(u0: float, v0: float, u1: float, v1: float) -> None:
        c.add(
            f'<line x1="{x + u0 * scale}" y1="{y + v0 * scale}" x2="{x + u1 * scale}" y2="{y + v1 * scale}" '
            f'stroke="{color}" stroke-width="{2 * scale}" stroke-linecap="round"/>'
        )

    line(11, 2, 11, 14)
    line(2, 5, 8.5, 5)
    line(8.5, 11, 5, 11)
    points = " ".join(f"{x + u * scale:.2f},{y + v * scale:.2f}" for u, v in ((1.2, 11), (5.4, 7.8), (5.4, 14.2)))
    c.add(f'<polygon points="{points}" fill="{color}"/>')


def wordmark(t: dict[str, str]) -> str:
    size = 34
    text_w = width("OpenHAL", "text", size, 700)
    c = Canvas(round(48 + text_w + 2), 44, "OpenHAL", "The OpenHAL mark and wordmark.")
    mark(c, 0, 4, 2.25, t["accent"])
    c.text("OpenHAL", 48, 34, face="text", size=size, weight=700, fill=t["text"])
    return c.svg()


def direction(c: Canvas, y: float, outgoing: bool, color: str) -> None:
    if outgoing:
        c.arrow(20, y, 38, color)
    else:
        c.arrow(38, y, 20, color)


def blocked_shape(c: Canvas, x: float, y: float, color: str) -> None:
    c.add(f'<circle cx="{x}" cy="{y}" r="6" fill="none" stroke="{color}" stroke-width="1.5"/>')
    c.add(f'<line x1="{x - 4.2}" y1="{y - 4.2}" x2="{x + 4.2}" y2="{y + 4.2}" stroke="{color}" stroke-width="1.5"/>')


def ok_shape(c: Canvas, x: float, y: float, color: str, ground: str) -> None:
    c.add(f'<circle cx="{x}" cy="{y}" r="6" fill="{color}"/>')
    c.add(
        f'<polyline points="{x - 3},{y} {x - 0.8},{y + 2.3} {x + 3.2},{y - 2.7}" fill="none" stroke="{ground}" '
        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
    )


def trace(t: dict[str, str]) -> str:
    c = Canvas(
        880,
        212,
        "Two hal/write exchanges",
        "A client sends hal/write for desk-fan fan_speed 150 percent. The hub answers error -32010 "
        "LIMIT_EXCEEDED, fan_speed 150 percent exceeds the limit of 100 percent, from desk-fan.hal.yaml "
        "confirmed by sohan on 2026-10-24. The client sends hal/write for 60 percent, and the hub answers "
        "with a result of status done, value 60, unit percent.",
    )
    c.rect(0.5, 0.5, 879, 211, t["surface"], t["border"])
    size, method_x, payload_x = 13.5, 52, 200
    y_req1, y_err, y_reason1, y_reason2, y_req2, y_ok = 36, 64, 88, 110, 150, 178

    direction(c, y_req1 - 4.5, True, t["text"])
    c.text("hal/write", method_x, y_req1, face="mono", size=size, weight=700, fill=t["accent"])
    draw_runs(c, json_runs(t, [("device", DEVICE), ("channel", CHANNEL), ("value", "150 %")]), payload_x, y_req1, size)

    direction(c, y_err - 4.5, False, t["text"])
    blocked_shape(c, method_x + 6, y_err - 4.5, t["blocked"])
    c.text("error -32010", method_x + 20, y_err, face="mono", size=size, weight=700, fill=t["blocked"])
    c.text("LIMIT_EXCEEDED", payload_x, y_err, face="mono", size=size, weight=700, fill=t["blocked"])
    c.text(REASON[0], payload_x, y_reason1, face="mono", size=size, fill=t["text"])
    c.text(REASON[1], payload_x, y_reason2, face="mono", size=size, fill=t["text2"])

    direction(c, y_req2 - 4.5, True, t["text"])
    c.text("hal/write", method_x, y_req2, face="mono", size=size, weight=700, fill=t["accent"])
    draw_runs(c, json_runs(t, [("device", DEVICE), ("channel", CHANNEL), ("value", "60 %")]), payload_x, y_req2, size)

    direction(c, y_ok - 4.5, False, t["text"])
    ok_shape(c, method_x + 6, y_ok - 4.5, t["ok"], t["surface"])
    c.text("result", method_x + 20, y_ok, face="mono", size=size, weight=700, fill=t["ok"])
    draw_runs(c, json_runs(t, [("status", "done"), ("value", 60), ("unit", "%")]), payload_x, y_ok, size)
    return c.svg()


PARTICIPANTS = ["Client", "Hub", "Safety Kernel", "Driver", "Device"]
STEPS: list[tuple[int, int, str, str, bool]] = [
    (0, 1, "hal/write  150 %", "text2", False),
    (1, 2, "check limits", "text2", False),
    (2, 1, "blocked  above_max", "blocked", False),
    (1, 0, "error -32010 LIMIT_EXCEEDED", "blocked", False),
    (0, 1, "hal/write  60 %", "text2", False),
    (1, 2, "check limits", "text2", False),
    (2, 1, "granted  single-use grant", "ok", False),
    (1, 3, "write 60 %  with grant", "text2", False),
    (3, 4, "set 60 %", "text2", False),
    (4, 3, "reads 60 %", "text2", False),
    (1, 0, "result  done", "ok", False),
    (1, 0, "hal/value  60 %", "text2", True),
]


def sequence(t: dict[str, str]) -> str:
    c = Canvas(
        880,
        500,
        "Sequence of the two hal/write requests",
        "The Client sends hal/write 150 percent to the Hub. The Hub asks the Safety Kernel to check it against "
        "desk-fan.hal.yaml, the kernel blocks it as above the maximum, and the Hub answers error -32010 "
        "LIMIT_EXCEEDED. The Client sends hal/write 60 percent. The kernel grants it with a single-use grant, "
        "the Hub passes the write and the grant to the Driver, the Driver sets the Device to 60 percent and "
        "reads back 60 percent, the Hub answers result done and sends a hal/value notification.",
    )
    xs = [80, 260, 440, 620, 800]
    box_w, box_h, top = 140, 36, 8
    for x, name in zip(xs, PARTICIPANTS, strict=True):
        c.rect(x - box_w / 2, top, box_w, box_h, t["surface"], t["border"])
        c.text(name, x, top + 23, face="text", size=14, weight=700, fill=t["text"], anchor="middle")
        c.vline(x, top + box_h, 492, t["border"])
    y = 80.0
    for index, (a, b, label, color, dashed) in enumerate(STEPS):
        if index == 4:
            y += 14
        fill = t[color]
        c.arrow(xs[a], y, xs[b], fill, dashed)
        outcome = color != "text2"
        c.text(
            label,
            (xs[a] + xs[b]) / 2,
            y - 8,
            face="mono",
            size=12,
            fill=fill if outcome else t["text"],
            anchor="middle",
            weight=700 if outcome else 400,
        )
        y += 33
    return c.svg()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, theme in THEMES.items():
        (OUT / f"wordmark-{name}.svg").write_text(wordmark(theme))
        (OUT / f"trace-{name}.svg").write_text(trace(theme))
        (OUT / f"sequence-{name}.svg").write_text(sequence(theme))
    print(f"Wrote wordmark, trace and sequence SVGs to {OUT}")


if __name__ == "__main__":
    main()
