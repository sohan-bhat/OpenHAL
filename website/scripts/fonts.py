"""Subset the website's fonts to the characters the site shows and the weights it uses.

design/fonts holds IBM Plex Sans as variable WOFF2 files and IBM Plex Mono as one static WOFF2 file
per weight, all subset to Latin, which the Inspector and the image tools use. The website ships
smaller copies of the faces it renders: only the characters in website/src/fonts/glyphs.json, which
scripts/glyphs.mjs lists from a build, with a variable face's weight axis cut to the weights its
styles ask for. Each copy keeps its face's family, style and weight descriptor, so its @font-face rule
joins the one in design/tokens.css and the browser takes the copy first. A character the copy lacks
still renders in the full face. Writes the copies and website/src/fonts/fonts.json, then
website/src/styles/fonts.css with their @font-face rules.

Run it with uv run --no-project --with fonttools==4.67.0 --with brotli python website/scripts/fonts.py
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "design" / "fonts"
OUT = ROOT / "website" / "src" / "fonts"
CSS = ROOT / "website" / "src" / "styles" / "fonts.css"
GLYPHS = OUT / "glyphs.json"
ASCII = range(0x20, 0x7F)
NAMES = [0, 1, 2, 3, 4, 5, 6, 13, 14]


@dataclass(frozen=True)
class Face:
    """One face the website renders, the weights it renders it at and the weight its rule declares."""

    family: str
    style: str
    source: str
    target: str
    weights: tuple[int, int]
    declared: str
    features: tuple[str, ...]


TEXT_FEATURES = ("kern", "tnum", "ccmp", "locl", "mark", "mkmk")
MONO_FEATURES = ("ccmp", "locl", "mark", "mkmk")


def mono(weight: int, style: str = "normal") -> Face:
    return Face(
        "IBM Plex Mono",
        style,
        f"ibm-plex-mono-latin-{weight}-{style}.woff2",
        f"ibm-plex-mono-{weight}-{style}.woff2",
        (weight, weight),
        str(weight),
        MONO_FEATURES,
    )


FACES = [
    Face(
        "IBM Plex Sans",
        "normal",
        "ibm-plex-sans-latin-wght-normal.woff2",
        "ibm-plex-sans-normal.woff2",
        (400, 700),
        "100 700",
        TEXT_FEATURES,
    ),
    mono(400),
    mono(600),
    mono(700),
    mono(400, "italic"),
]


def wanted() -> set[int]:
    listed = json.loads(GLYPHS.read_text())["codepoints"]
    return set(ASCII) | {int(code, 16) for code in listed}


def load(path: Path) -> TTFont:
    return TTFont(path, recalcTimestamp=False, lazy=False)


def with_full_gvar(font: TTFont) -> TTFont:
    if "gvar" in font:
        gvar = font["gvar"]
        gvar.variations = {glyph: gvar.variations.get(glyph, []) for glyph in font.getGlyphOrder()}
    return font


def build(face: Face, codepoints: set[int]) -> tuple[bytes, list[int], list[int]]:
    source = load(DESIGN / face.source)
    original = sorted(source.getBestCmap())
    low, high = face.weights
    font = with_full_gvar(source)
    if "fvar" in font:
        font = instancer.instantiateVariableFont(font, {"wght": low if low == high else (low, high)})
    options = subset.Options()
    options.layout_features = list(face.features)
    options.name_IDs = NAMES
    options.name_languages = [0x409]
    options.notdef_outline = False
    options.recalc_bounds = True
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=sorted(codepoints & set(original)))
    subsetter.subset(with_full_gvar(font))
    font.flavor = "woff2"
    buffer = io.BytesIO()
    font.save(buffer)
    return buffer.getvalue(), sorted(font.getBestCmap()), original


def ranges(codepoints: list[int]) -> str:
    runs: list[tuple[int, int]] = []
    for code in codepoints:
        if runs and code == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], code)
        else:
            runs.append((code, code))
    return ", ".join(f"U+{a:X}" if a == b else f"U+{a:X}-{b:X}" for a, b in runs)


def main() -> None:
    codepoints = wanted()
    manifest = []
    rules = []
    for face in FACES:
        data, cmap, original = build(face, codepoints)
        (OUT / face.target).write_bytes(data)
        kind = "woff2" if face.weights[0] == face.weights[1] else "woff2-variations"
        manifest.append(
            {
                "family": face.family,
                "style": face.style,
                "file": face.target,
                "source": face.source,
                "weights": list(face.weights),
                "bytes": len(data),
                "sourceBytes": (DESIGN / face.source).stat().st_size,
                "unicodeRange": ranges(cmap),
                "sourceRange": ranges(original),
            }
        )
        rules.append(
            "\n".join(
                [
                    "@font-face {",
                    f'  font-family: "{face.family}";',
                    f"  font-style: {face.style};",
                    "  font-display: swap;",
                    f"  font-weight: {face.declared};",
                    f'  src: url("../fonts/{face.target}") format("{kind}");',
                    f"  unicode-range: {ranges(cmap)};",
                    "}",
                ]
            )
        )
        print(f"{face.target}  {len(data)} bytes, was {(DESIGN / face.source).stat().st_size}, {len(cmap)} characters")
    (OUT / "fonts.json").write_text(json.dumps({"faces": manifest}, indent=2) + "\n")
    CSS.write_text("\n\n".join(rules) + "\n")


if __name__ == "__main__":
    main()
