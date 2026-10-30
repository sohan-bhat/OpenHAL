"""Image readings as the hub sends them (ADR 0015, Image readings).

A driver returns an image channel's frame as bytes. Clients get it as an object,

    { "mimeType": "image/jpeg", "bytes": 23817, "width": 640, "height": 480, "data": "<base64>" }

`describe()` gives everything but `data`. That is what the audit log, device views and records
keep, so a frame's pixels never land in the log. `width` and `height` come from the image header
and are None when the format is one this module can't read. A frame larger than MAX_BYTES
fails the read, with a reason that names the limit and the settings to lower.
"""

from __future__ import annotations

import base64
import struct
from typing import Any, Final

MAX_BYTES: Final = 2_000_000
"""The largest frame one reading may carry."""

OCTET_STREAM: Final = "application/octet-stream"
_SOF: Final = frozenset({0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF})


def mime_type(data: bytes) -> str:
    """The image format from its first bytes, or application/octet-stream."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return OCTET_STREAM


def is_image(data: bytes) -> bool:
    return mime_type(data) != OCTET_STREAM


def size(data: bytes) -> tuple[int | None, int | None]:
    """Width and height from the header of a JPEG, PNG or GIF. (None, None) when unknown."""
    kind = mime_type(data)
    if kind == "image/png" and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return int(width), int(height)
    if kind == "image/gif" and len(data) >= 10:
        width, height = struct.unpack("<HH", data[6:10])
        return int(width), int(height)
    if kind == "image/jpeg":
        return _jpeg_size(data)
    return None, None


def _jpeg_size(data: bytes) -> tuple[int | None, int | None]:
    index = 2
    while index + 4 <= len(data):
        if data[index] != 0xFF:
            return None, None
        marker = data[index + 1]
        if marker == 0xFF:
            index += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            index += 2
            continue
        length = struct.unpack(">H", data[index + 2 : index + 4])[0]
        if marker in _SOF and index + 9 <= len(data):
            height, width = struct.unpack(">HH", data[index + 5 : index + 9])
            return int(width), int(height)
        if marker == 0xDA:
            return None, None
        index += 2 + length
    return None, None


def describe(data: bytes) -> dict[str, Any]:
    """The image without its pixels, `{ mimeType, bytes, width, height }`."""
    width, height = size(data)
    return {"mimeType": mime_type(data), "bytes": len(data), "width": width, "height": height}


def value(data: bytes) -> dict[str, Any]:
    """The image as a reading's value, with the pixels base64 encoded in `data`."""
    return {**describe(data), "data": base64.b64encode(data).decode("ascii")}


def too_large(data: bytes, where: str) -> str | None:
    """The reason a frame can't be sent, or None when it fits."""
    if len(data) <= MAX_BYTES:
        return None
    return (
        f"The frame from {where} is {len(data) / 1_000_000:.1f} MB, over the {MAX_BYTES / 1_000_000:g} MB limit "
        "for one image reading. Lower the camera's resolution or JPEG quality, with width, height or jpeg_quality "
        "in the device file's connect settings or in the camera's own settings."
    )
