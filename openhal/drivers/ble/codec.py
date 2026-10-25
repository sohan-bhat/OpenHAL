"""Encode and decode GATT characteristic values.

Formats follow the Bluetooth GATT Specification Supplement (section 2.2, "Format types") and the
format names in Assigned Numbers. GATT values are little-endian unless a profile says otherwise.

| Format | Bytes | Notes |
|---|---|---|
| uint8, uint16, uint24, uint32 | 1, 2, 3, 4 | unsigned integers |
| sint8, sint16, sint24, sint32 | 1, 2, 3, 4 | two's complement integers |
| float32, float64 | 4, 8 | IEEE 754 |
| sfloat (medfloat16) | 2 | IEEE 11073-20601 16-bit, 4-bit exponent and 12-bit mantissa |
| float (medfloat32) | 4 | IEEE 11073-20601 32-bit, 8-bit exponent and 24-bit mantissa |
| utf8 | rest of the value | text |

The IEEE 11073 special values (NaN, NRes, +INF, -INF and the reserved value) raise ValueError,
because they mean the sensor has no valid reading.
"""

from __future__ import annotations

import math
import struct
from typing import Final, Literal

Format = Literal[
    "uint8",
    "uint16",
    "uint24",
    "uint32",
    "sint8",
    "sint16",
    "sint24",
    "sint32",
    "float32",
    "float64",
    "sfloat",
    "medfloat16",
    "float",
    "medfloat32",
    "utf8",
]
Order = Literal["little", "big"]

SIZES: Final = {
    "uint8": 1,
    "sint8": 1,
    "uint16": 2,
    "sint16": 2,
    "uint24": 3,
    "sint24": 3,
    "uint32": 4,
    "sint32": 4,
    "float32": 4,
    "float64": 8,
    "sfloat": 2,
    "medfloat16": 2,
    "float": 4,
    "medfloat32": 4,
}
_SFLOAT_SPECIAL: Final = {0x07FF: "NaN", 0x0800: "NRes", 0x07FE: "+INF", 0x0802: "-INF", 0x0801: "reserved"}
_FLOAT_SPECIAL: Final = {
    0x007FFFFF: "NaN",
    0x00800000: "NRes",
    0x007FFFFE: "+INF",
    0x00800002: "-INF",
    0x00800001: "reserved",
}


def _signed(raw: int, bits: int) -> int:
    return raw - (1 << bits) if raw & (1 << (bits - 1)) else raw


def decode(data: bytes, fmt: Format, start: int = 0, order: Order = "little") -> float | str:
    """Decode one value starting at byte `start`. Raises ValueError for short or invalid data."""
    if fmt == "utf8":
        return data[start:].decode("utf-8", "replace").rstrip("\x00")
    size = SIZES[fmt]
    chunk = data[start : start + size]
    if len(chunk) < size:
        raise ValueError(f"needs {size} bytes at offset {start}, the value has {len(data)}")
    if fmt in ("float32", "float64"):
        value = struct.unpack(("<" if order == "little" else ">") + ("f" if fmt == "float32" else "d"), chunk)[0]
        if not math.isfinite(value):
            raise ValueError("is not a finite number")
        return float(value)
    raw = int.from_bytes(chunk, order)
    if fmt in ("sfloat", "medfloat16"):
        if raw in _SFLOAT_SPECIAL:
            raise ValueError(f"holds the special value {_SFLOAT_SPECIAL[raw]}")
        return float(_signed(raw & 0x0FFF, 12) * 10.0 ** _signed(raw >> 12, 4))
    if fmt in ("float", "medfloat32"):
        if raw in _FLOAT_SPECIAL:
            raise ValueError(f"holds the special value {_FLOAT_SPECIAL[raw]}")
        return float(_signed(raw & 0xFFFFFF, 24) * 10.0 ** _signed(raw >> 24, 8))
    if fmt.startswith("sint"):
        return float(_signed(raw, size * 8))
    return float(raw)


def encode(value: float | str, fmt: Format, order: Order = "little") -> bytes:
    """Encode one value. Raises ValueError if it doesn't fit the format."""
    if fmt == "utf8":
        return str(value).encode("utf-8")
    number = float(value)
    size = SIZES[fmt]
    if fmt in ("float32", "float64"):
        try:
            return struct.pack(("<" if order == "little" else ">") + ("f" if fmt == "float32" else "d"), number)
        except OverflowError:
            raise ValueError(f"{number:g} is too large for {fmt}") from None
    if fmt in ("sfloat", "medfloat16", "float", "medfloat32"):
        mantissa_bits, exponent_bits = (12, 4) if size == 2 else (24, 8)
        limit = (1 << (mantissa_bits - 1)) - 3
        low_exp, high_exp = -(1 << (exponent_bits - 1)), (1 << (exponent_bits - 1)) - 1
        for exponent in range(low_exp, high_exp + 1):
            mantissa = number / 10.0**exponent
            exact = abs(round(mantissa) * 10.0**exponent - number) <= 1e-9 * max(1.0, abs(number))
            if abs(mantissa) <= limit and exact:
                raw = (exponent & ((1 << exponent_bits) - 1)) << mantissa_bits | (
                    round(mantissa) & ((1 << mantissa_bits) - 1)
                )
                return raw.to_bytes(size, order)
        raise ValueError(f"{number:g} can't be written exactly as {fmt}")
    integer = round(number)
    bits = size * 8
    low, high = (-(1 << (bits - 1)), (1 << (bits - 1)) - 1) if fmt.startswith("sint") else (0, (1 << bits) - 1)
    if not low <= integer <= high:
        raise ValueError(f"{number:g} doesn't fit in {fmt}")
    return (integer & ((1 << bits) - 1)).to_bytes(size, order)
