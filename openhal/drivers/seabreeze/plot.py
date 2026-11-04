"""A spectrum as a PNG chart an agent can look at, drawn with Pillow.

The chart puts wavelength in nm on the x axis and counts on the y axis, from 0 to the detector's
maximum, so a saturated spectrum reaches the top and a dark one stays at the bottom. The area under
the curve takes the color of each wavelength between 380 and 750 nm and gray outside that range.
The chart is for looking at. Numbers come from the reading channels.
"""

from __future__ import annotations

import io
import itertools
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

MARGIN = (64, 16, 20, 40)
"""Left, top, right and bottom margins in pixels."""


def _color(nm: float) -> tuple[int, int, int]:
    """An approximate display color for a wavelength, gray outside the visible range."""
    if nm < 380 or nm > 750:
        return (205, 205, 205)
    stops = (
        (380, (97, 0, 97)),
        (440, (0, 0, 255)),
        (490, (0, 255, 255)),
        (510, (0, 255, 0)),
        (580, (255, 255, 0)),
        (645, (255, 0, 0)),
        (750, (128, 0, 0)),
    )
    for (low, first), (high, second) in itertools.pairwise(stops):
        if low <= nm <= high:
            share = (nm - low) / (high - low)
            return tuple(round(a + (b - a) * share) for a, b in zip(first, second, strict=True))  # type: ignore[return-value]
    return (128, 0, 0)


def _step(span: float) -> float:
    raw = span / 6
    power = 10.0 ** math.floor(math.log10(raw))
    return float(next(power * factor for factor in (1, 2, 5, 10) if power * factor >= raw))


def render(wavelengths: np.ndarray, counts: np.ndarray, top: float, size: tuple[int, int] = (800, 400)) -> bytes:
    """The spectrum as PNG bytes. `top` is the detector's maximum count."""
    width, height = size
    left, upper, right, lower = MARGIN
    image = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    plot_w, plot_h = width - left - right, height - upper - lower
    low_nm, high_nm = float(wavelengths[0]), float(wavelengths[-1])

    def x_at(nm: float) -> float:
        return left + (nm - low_nm) / (high_nm - low_nm) * plot_w

    def y_at(value: float) -> float:
        return upper + plot_h - min(max(value, 0.0), top) / top * plot_h

    columns = np.linspace(low_nm, high_nm, plot_w)
    heights = np.interp(columns, wavelengths, counts)
    for index, (nm, value) in enumerate(zip(columns, heights, strict=True)):
        draw.line([(left + index, y_at(float(value))), (left + index, upper + plot_h)], fill=_color(float(nm)))
    points = [(x_at(float(nm)), y_at(float(value))) for nm, value in zip(columns, heights, strict=True)]
    draw.line(points, fill=(30, 30, 30), width=2)
    draw.rectangle([left, upper, left + plot_w, upper + plot_h], outline=(60, 60, 60))
    step = _step(high_nm - low_nm)
    tick = math.ceil(low_nm / step) * step
    while tick <= high_nm:
        x = x_at(tick)
        draw.line([(x, upper + plot_h), (x, upper + plot_h + 5)], fill=(60, 60, 60))
        draw.text((x - 12, upper + plot_h + 8), f"{tick:g}", fill=(30, 30, 30), font=font)
        tick += step
    count_step = _step(top)
    level = 0.0
    while level <= top:
        y = y_at(level)
        draw.line([(left - 5, y), (left, y)], fill=(60, 60, 60))
        draw.text((4, y - 6), f"{level:g}", fill=(30, 30, 30), font=font)
        level += count_step
    draw.text((left + plot_w // 2 - 40, height - 16), "wavelength (nm)", fill=(30, 30, 30), font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
