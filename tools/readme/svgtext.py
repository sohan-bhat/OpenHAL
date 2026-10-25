"""Text as SVG paths, from the design fonts in design/fonts.

GitHub shows README images without web fonts, so every letter in the README's SVGs is a path.
Glyphs come from the variable WOFF2 files at a fixed weight. Kerning is not applied, which is
fine at the label sizes the diagrams use.
"""

from __future__ import annotations

import functools
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

FONTS = Path(__file__).resolve().parents[2] / "design" / "fonts"
FACES = {
    "label": "sofia-sans-condensed-latin-wght-normal.woff2",
    "text": "atkinson-hyperlegible-next-latin-wght-normal.woff2",
    "mono": "martian-mono-latin-wght-normal.woff2",
}


@functools.cache
def font(face: str, weight: int) -> TTFont:
    variable = TTFont(FONTS / FACES[face])
    return instancer.instantiateVariableFont(variable, {"wght": weight})


def width(text: str, face: str, size: float, weight: int = 400, tracking: float = 0.0) -> float:
    loaded = font(face, weight)
    cmap = loaded.getBestCmap()
    scale = size / loaded["head"].unitsPerEm
    total = 0.0
    for char in text:
        name = cmap.get(ord(char), ".notdef")
        total += loaded["hmtx"][name][0] * scale + tracking * size
    return total - (tracking * size if text else 0.0)


def path(
    text: str,
    x: float,
    y: float,
    *,
    face: str,
    size: float,
    fill: str,
    weight: int = 400,
    anchor: str = "start",
    tracking: float = 0.0,
) -> str:
    """One <path> drawing `text` with its baseline at y. Anchor is start, middle or end."""
    loaded = font(face, weight)
    cmap = loaded.getBestCmap()
    glyphs = loaded.getGlyphSet()
    scale = size / loaded["head"].unitsPerEm
    total = width(text, face, size, weight, tracking)
    cursor = x - (total / 2 if anchor == "middle" else total if anchor == "end" else 0.0)
    pen = SVGPathPen(glyphs, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
    for char in text:
        name = cmap.get(ord(char), ".notdef")
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, cursor, y)))
        cursor += loaded["hmtx"][name][0] * scale + tracking * size
    commands = pen.getCommands()
    return f'<path fill="{fill}" d="{commands}"/>' if commands else ""
