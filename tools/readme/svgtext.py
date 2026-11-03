"""Text as SVG paths, from the design fonts in design/fonts.

GitHub shows README images without web fonts, so every letter in the README's SVGs is a path.
Glyphs come from IBM Plex Sans, a variable WOFF2 file set at a fixed weight, or from IBM Plex Mono,
one static WOFF2 file per weight. Kerning is not applied, which is fine at the label sizes the
diagrams use.
"""

from __future__ import annotations

import functools
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

FONTS = Path(__file__).resolve().parents[2] / "design" / "fonts"
FACES = {
    "text": "ibm-plex-sans-latin-wght-normal.woff2",
    "mono": "ibm-plex-mono-latin-{weight}-normal.woff2",
}


@functools.cache
def font(face: str, weight: int) -> TTFont:
    """The face at `weight`. A variable file is set at that weight, and a static file is the one cut at it."""
    source = FONTS / FACES[face].format(weight=weight)
    if not source.exists():
        raise FileNotFoundError(f"design/fonts has no {face} face at weight {weight}, looked for {source.name}")
    loaded = TTFont(source)
    if "fvar" not in loaded:
        return loaded
    return instancer.instantiateVariableFont(loaded, {"wght": weight})


def width(text: str, face: str, size: float, weight: int = 400, tracking: float = 0.0) -> float:
    loaded = font(face, weight)
    cmap = loaded.getBestCmap()
    scale = size / loaded["head"].unitsPerEm
    total = 0.0
    for char in text:
        name = cmap.get(ord(char), ".notdef")
        total += loaded["hmtx"][name][0] * scale + tracking * size
    return total - (tracking * size if text else 0.0)


def ink(text: str, face: str, size: float, weight: int = 400, tracking: float = 0.0) -> tuple[float, float]:
    """Where the outlines of `text` start and end, measured from where the text starts."""
    loaded = font(face, weight)
    cmap = loaded.getBestCmap()
    glyphs = loaded.getGlyphSet()
    scale = size / loaded["head"].unitsPerEm
    cursor = 0.0
    left, right = float("inf"), float("-inf")
    for char in text:
        name = cmap.get(ord(char), ".notdef")
        pen = BoundsPen(glyphs)
        glyphs[name].draw(pen)
        if pen.bounds:
            left = min(left, cursor + pen.bounds[0] * scale)
            right = max(right, cursor + pen.bounds[2] * scale)
        cursor += loaded["hmtx"][name][0] * scale + tracking * size
    return (left, right) if text else (0.0, 0.0)


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
) -> list[str]:
    """The path data of each letter of `text` with its baseline at y. Anchor is start, middle or end."""
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
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, cursor, y)))
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
) -> str:
    """One <path> drawing `text` with its baseline at y. Anchor is start, middle or end."""
    commands = "".join(letters(text, x, y, face=face, size=size, weight=weight, anchor=anchor, tracking=tracking))
    return f'<path fill="{fill}" d="{commands}"/>' if commands else ""
