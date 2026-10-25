"""Build the OpenHAL mark, wordmark and favicon in the protocol theme, in light and dark variants.

    uv run --with fonttools --with brotli python tools/readme/build.py

Writes docs/assets/wordmark-{light,dark}.svg with the text converted to paths, since GitHub loads no
web fonts, docs/assets/mark-{light,dark}.svg and docs/assets/favicon.svg. Diagrams are built
separately by scripts/build-diagrams.
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


MARK_LINES = ((11, 2, 11, 14), (2, 5, 8.5, 5), (8.5, 11, 5, 11))
MARK_ARROW = ((1.2, 11), (5.4, 7.8), (5.4, 14.2))
"""The mark on its 16 unit grid. A request stroke meets a stop bar, a return stroke points back."""


def mark_parts(x: float, y: float, scale: float, color: str) -> list[str]:
    parts = [
        f'<line x1="{x + u0 * scale}" y1="{y + v0 * scale}" x2="{x + u1 * scale}" y2="{y + v1 * scale}" '
        f'stroke="{color}" stroke-width="{2 * scale}" stroke-linecap="round"/>'
        for u0, v0, u1, v1 in MARK_LINES
    ]
    points = " ".join(f"{x + u * scale:.2f},{y + v * scale:.2f}" for u, v in MARK_ARROW)
    return [*parts, f'<polygon points="{points}" fill="{color}"/>']


def mark_markup(x: float, y: float, scale: float, color: str) -> str:
    return "".join(mark_parts(x, y, scale, color))


def mark(c: Canvas, x: float, y: float, scale: float, t: dict[str, str]) -> None:
    for part in mark_parts(x, y, scale, t["accent"]):
        c.add(part)


def mark_svg(t: dict[str, str]) -> str:
    c = Canvas(64, 64, "OpenHAL", "The OpenHAL mark. A request stroke meets a stop bar, and a return stroke points back.")
    c.add(mark_markup(0, 0, 4, t["accent"]))
    return c.svg().replace('viewBox="0 0 64 64"', 'viewBox="0 0 64 64" shape-rendering="geometricPrecision"')


def favicon() -> str:
    """One file for browsers, with the dark variant under prefers-color-scheme."""
    light, dark = THEMES["light"], THEMES["dark"]
    style = f"g{{color:{light['accent']}}}@media (prefers-color-scheme: dark){{g{{color:{dark['accent']}}}}}"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f"<title>OpenHAL</title><style>{style}</style><g>{mark_markup(0, 0, 1, 'currentColor')}</g></svg>\n"
    )


def wordmark(t: dict[str, str]) -> str:
    size = 34
    text_w = width("OpenHAL", "text", size, 700)
    c = Canvas(round(48 + text_w + 2), 44, "OpenHAL", "The OpenHAL mark and wordmark.")
    mark(c, 0, 4, 2.25, t)
    c.text("OpenHAL", 48, 34, face="text", size=size, weight=700, fill=t["text"])
    return c.svg()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, theme in THEMES.items():
        (OUT / f"wordmark-{name}.svg").write_text(wordmark(theme))
        (OUT / f"mark-{name}.svg").write_text(mark_svg(theme))
    (OUT / "favicon.svg").write_text(favicon())
    print(f"Wrote the wordmark, mark and favicon SVGs to {OUT}")


if __name__ == "__main__":
    main()
