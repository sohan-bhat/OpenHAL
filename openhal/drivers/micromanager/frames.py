"""Camera frames as images an agent can see, and the sharpness score image autofocus uses.

Micro-Manager returns a frame as a numpy array, 2D for a monochrome camera with 8 to 16 bits per
pixel and height x width x 3 for a color camera after pymmcore-plus converts its BGRA. A frame
becomes an 8-bit image in one of two ways.

- `full` maps the camera's whole bit depth to 0 to 255, so brightness compares across frames.
- `auto` stretches a frame deeper than 8 bits from its 0.1 to its 99.9 percentile, as
  Micro-Manager's display does, but never over less than 5 % of the bit depth, so a dark frame
  stays dark instead of showing stretched noise. An 8-bit frame is already an image, so an 8-bit
  frame passes through unchanged.

The 8-bit image is scaled down to `max_side` pixels on its longer side and encoded as JPEG or PNG
with Pillow. The image is for looking at, not for measuring intensities.
"""

from __future__ import annotations

import io
from typing import Literal

import numpy as np
from PIL import Image

Contrast = Literal["full", "auto"]
Format = Literal["jpeg", "png"]
MIN_STRETCH = 0.05


def to_8bit(frame: np.ndarray, bit_depth: int, contrast: Contrast) -> np.ndarray:
    """A frame as uint8, 2D or with three color channels."""
    data = np.asarray(frame)
    if data.ndim == 3 and data.shape[2] == 4:
        data = data[..., :3]
    if data.ndim not in (2, 3) or (data.ndim == 3 and data.shape[2] != 3) or 0 in data.shape:
        raise ValueError(f"the camera returned an array of shape {data.shape}, not an image")
    full = float(2 ** max(1, min(bit_depth, 32)) - 1)
    if data.dtype == np.uint8:
        return data
    values = data.astype(np.float32)
    low, high = 0.0, full
    if contrast == "auto":
        sample = values[:: max(1, values.shape[0] // 256), :: max(1, values.shape[1] // 256)]
        low, high = (float(item) for item in np.percentile(sample, [0.1, 99.9]))
        if high - low < MIN_STRETCH * full:
            high = low + MIN_STRETCH * full
    scaled = (values - low) * (255.0 / max(high - low, 1e-6))
    result: np.ndarray = np.clip(scaled, 0, 255).astype(np.uint8)
    return result


def encode(pixels: np.ndarray, image_format: Format, quality: int, max_side: int) -> bytes:
    """An 8-bit frame as JPEG or PNG bytes, at most `max_side` pixels on its longer side."""
    image = Image.fromarray(pixels, "L" if pixels.ndim == 2 else "RGB")
    if max(image.size) > max_side:
        image.thumbnail((max_side, max_side), Image.Resampling.BILINEAR, reducing_gap=2.0)
    buffer = io.BytesIO()
    if image_format == "png":
        image.save(buffer, format="PNG", optimize=False)
    else:
        image.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def focus_score(frame: np.ndarray) -> float:
    """How sharp a frame is, the Brenner gradient of its gray levels over their mean.

    The frame is averaged down to at most 256 pixels across first, which keeps the score fast
    and steady against pixel noise. A larger score is sharper.
    """
    data = np.asarray(frame, dtype=np.float32)
    gray = data.mean(axis=2) if data.ndim == 3 else data
    step = max(1, gray.shape[1] // 256)
    rows, cols = (gray.shape[0] // step) * step, (gray.shape[1] // step) * step
    small = gray[:rows, :cols].reshape(rows // step, step, cols // step, step).mean(axis=(1, 3))
    if small.shape[1] < 3:
        return 0.0
    gradient = small[:, 2:] - small[:, :-2]
    return float(np.mean(gradient * gradient) / (float(small.mean()) + 1.0))
