"""Text as SVG paths, from the design fonts in design/fonts.

GitHub shows README images without web fonts, so every letter in the README's SVGs is a path.
Glyphs come from the variable WOFF2 files at a fixed weight. Kerning is not applied, which is
fine at the label sizes the diagrams use.
"""

from __future__ import annotations

import functools
from pathlib import Path

from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

FONTS = Path(__file__).resolve().parents[2] / "design" / "fonts"
FACES = {
    "text": "atkinson-hyperlegible-next-latin-wght-normal.woff2",
    "mono": "atkinson-hyperlegible-mono-latin-wght-normal.woff2",
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


Outline = list[list[tuple[float, float]]]
"""A glyph drawn as closed polygons in font units, in place of the font's own outline."""


def outline(char: str, face: str, weight: int) -> Outline:
    """The font's own outline of a glyph made of straight lines, as closed polygons in font units."""
    loaded = font(face, weight)
    pen = RecordingPen()
    loaded.getGlyphSet()[loaded.getBestCmap()[ord(char)]].draw(pen)
    polygons: Outline = []
    for operator, points in pen.value:
        if operator == "moveTo":
            polygons.append([points[0]])
        elif operator == "lineTo":
            polygons[-1].append(points[0])
        elif operator not in ("closePath", "endPath"):
            raise ValueError(f"{char} has a curve, so it can't be redrawn as polygons")
    return polygons


def letters(
    text: str,
    x: float,
    y: float,
    *,
    face: str,
    size: float,
    weight: int = 400,
    anchor: str = "start",
    tracking: float = 0.0,
    outlines: dict[str, Outline] | None = None,
) -> list[str]:
    """The path data of each letter of `text` with its baseline at y, with `outlines` in place of
    the font's own glyphs for the letters it names. Anchor is start, middle or end."""
    loaded = font(face, weight)
    cmap = loaded.getBestCmap()
    glyphs = loaded.getGlyphSet()
    scale = size / loaded["head"].unitsPerEm
    total = width(text, face, size, weight, tracking)
    cursor = x - (total / 2 if anchor == "middle" else total if anchor == "end" else 0.0)
    drawn = []
    for char in text:
        name = cmap.get(ord(char), ".notdef")
        pen = SVGPathPen(glyphs, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
        moved = TransformPen(pen, (scale, 0, 0, -scale, cursor, y))
        if outlines and char in outlines:
            for polygon in outlines[char]:
                moved.moveTo(polygon[0])
                for point in polygon[1:]:
                    moved.lineTo(point)
                moved.closePath()
        else:
            glyphs[name].draw(moved)
        drawn.append(pen.getCommands())
        cursor += loaded["hmtx"][name][0] * scale + tracking * size
    return drawn


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
    outlines: dict[str, Outline] | None = None,
) -> str:
    """One <path> drawing `text` with its baseline at y. Anchor is start, middle or end."""
    commands = "".join(
        letters(text, x, y, face=face, size=size, weight=weight, anchor=anchor, tracking=tracking, outlines=outlines)
    )
    return f'<path fill="{fill}" d="{commands}"/>' if commands else ""
