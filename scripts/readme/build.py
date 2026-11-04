"""Build the OpenHAL mark, wordmark and favicon in the protocol theme, in light and dark variants.

    uv run --with fonttools --with brotli python scripts/readme/build.py

Writes docs/assets/wordmark-{light,dark}.svg with the text converted to paths, since GitHub loads no
web fonts, docs/assets/mark-{light,dark}.svg and docs/assets/favicon.svg. Diagrams are built
separately by scripts/build-diagrams.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from svgtext import ink, letters, path, width

OUT = Path(__file__).resolve().parents[2] / "docs" / "assets"

THEMES = {
    "light": {
        "surface": "#EFF1EF",
        "border": "#D7DAD7",
        "text": "#1D211C",
        "text2": "#60655F",
        "ok": "#3C754F",
        "blocked": "#A14034",
    },
    "dark": {
        "surface": "#212220",
        "border": "#383A36",
        "text": "#ECEEEC",
        "text2": "#AFB5AD",
        "ok": "#72B88E",
        "blocked": "#D57A72",
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


WORD = "OpenHAL"
INITIALS = "OH"
WEIGHT = 700
TRACKING = -0.04
INITIALS_TRACKING = -0.08
FILL = 0.94
"""The brand is the name set tight in IBM Plex Sans at its heaviest weight. There is no logo shape.
The initials' outlines span FILL of their square's width, measured on the letters and not their
advance widths, so OH fills the favicon."""


def initials_path(side: float, fill: str) -> str:
    """OH centered in a square `side` wide, its outlines across FILL of the width."""
    left, right = ink(INITIALS, "text", 1, WEIGHT, INITIALS_TRACKING)
    size = min(side * 0.9, side * FILL / (right - left))
    return path(
        INITIALS,
        side / 2 - (left + right) / 2 * size,
        side / 2 + size * 0.35,
        face="text",
        size=size,
        weight=WEIGHT,
        fill=fill,
        tracking=INITIALS_TRACKING,
    )


def initials(c: Canvas, side: float, color: str) -> None:
    c.add(initials_path(side, color))


def mark_svg(t: dict[str, str]) -> str:
    c = Canvas(64, 64, "OpenHAL", "The OpenHAL initials, OH, set tight in the brand face.")
    initials(c, 64, t["text"])
    return c.svg().replace('viewBox="0 0 64 64"', 'viewBox="0 0 64 64" shape-rendering="geometricPrecision"')


def favicon() -> str:
    """One file for browsers, with the dark variant under prefers-color-scheme."""
    light, dark = THEMES["light"], THEMES["dark"]
    shape = initials_path(16, "currentColor")
    style = f"g{{color:{light['text']}}}@media (prefers-color-scheme: dark){{g{{color:{dark['text']}}}}}"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f"<title>OpenHAL</title><style>{style}</style><g>{shape}</g></svg>\n"
    )


def wordmark(t: dict[str, str]) -> str:
    """The wordmark with each letter its own path, numbered by its place in the word, so the home page
    hero can set its [hardware], [abstraction] and [layer] labels under the H, the A and the L."""
    size = 38
    text_w = width(WORD, "text", size, WEIGHT, TRACKING)
    c = Canvas(round(text_w + 4), 44, "OpenHAL", "The OpenHAL wordmark.")
    drawn = letters(WORD, 2, 34, face="text", size=size, weight=WEIGHT, tracking=TRACKING)
    marks = "".join(f'<path data-at="{index}" d="{d}"/>' for index, d in enumerate(drawn))
    c.add(f'<g fill="{t["text"]}" data-baseline="34" data-size="{size}">{marks}</g>')
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
