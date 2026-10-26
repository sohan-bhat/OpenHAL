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


WORD = "OpenHAL"
INITIALS = "OH"
WEIGHT = 800
TRACKING = -0.06
INITIALS_TRACKING = -0.1
"""The brand is the name set tight in the text face at its heaviest weight. There is no logo shape."""


def fitted(text: str, box: float, size: float, tracking: float = TRACKING) -> float:
    """The largest size up to `size` at which `text` fits in `box` wide."""
    return min(size, box / width(text, "text", 1, WEIGHT, tracking))


def initials(c: Canvas, side: float, color: str) -> None:
    size = fitted(INITIALS, side * 0.94, side * 0.9, INITIALS_TRACKING)
    baseline = side / 2 + size * 0.35
    c.add(
        path(
            INITIALS,
            side / 2,
            baseline,
            face="text",
            size=size,
            weight=WEIGHT,
            fill=color,
            anchor="middle",
            tracking=INITIALS_TRACKING,
        )
    )


def mark_svg(t: dict[str, str]) -> str:
    c = Canvas(64, 64, "OpenHAL", "The OpenHAL initials, OH, set tight in the brand face.")
    initials(c, 64, t["text"])
    return c.svg().replace('viewBox="0 0 64 64"', 'viewBox="0 0 64 64" shape-rendering="geometricPrecision"')


def favicon() -> str:
    """One file for browsers, with the dark variant under prefers-color-scheme."""
    light, dark = THEMES["light"], THEMES["dark"]
    size = fitted(INITIALS, 16, 15, INITIALS_TRACKING)
    shape = path(
        INITIALS,
        8,
        8 + size * 0.35,
        face="text",
        size=size,
        weight=WEIGHT,
        fill="currentColor",
        anchor="middle",
        tracking=INITIALS_TRACKING,
    )
    style = f"g{{color:{light['text']}}}@media (prefers-color-scheme: dark){{g{{color:{dark['text']}}}}}"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f"<title>OpenHAL</title><style>{style}</style><g>{shape}</g></svg>\n"
    )


def wordmark(t: dict[str, str]) -> str:
    size = 38
    text_w = width(WORD, "text", size, WEIGHT, TRACKING)
    c = Canvas(round(text_w + 4), 44, "OpenHAL", "The OpenHAL wordmark.")
    c.add(path(WORD, 2, 34, face="text", size=size, weight=WEIGHT, fill=t["text"], tracking=TRACKING))
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
