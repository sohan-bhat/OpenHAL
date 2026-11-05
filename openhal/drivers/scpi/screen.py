"""The simulated oscilloscope's screen as a PNG, drawn in pure Python with a 5 by 7 bitmap font.

The screen is 800 by 480 pixels. A status line sits on top with the acquisition state, the
timebase, the trigger and the generator. The 10 by 8 division graticule fills the middle, with
minor ticks on its centre lines, the trigger level marked on the right edge and the trigger point
on the top edge. Each shown channel draws in its own colour with a soft glow. The bottom line
holds each channel's scale and the measurements read so far.
"""

from __future__ import annotations

import math
import struct
import zlib
from typing import Any

WIDTH, HEIGHT = 800, 480
LEFT, TOP, DIV_X, DIV_Y = 50, 36, 70, 50
COLUMNS, ROWS = 10, 8
BACKGROUND = (7, 9, 12)
GRID = (58, 62, 70)
AXIS = (96, 101, 110)
TEXT = (214, 218, 222)
DIM = (120, 124, 130)
COLORS = {1: (247, 212, 64), 2: (64, 214, 232), 3: (232, 96, 204), 4: (86, 146, 255)}
STATES = {"TD": ("TRIG'D", (110, 200, 130)), "AUTO": ("AUTO", (236, 176, 70)), "WAIT": ("WAIT", (236, 176, 70))}
NAMES = {"FREQ": "Freq", "PER": "Per", "VPP": "Vpp", "VMAX": "Vmax", "VMIN": "Vmin", "VAVG": "Vavg", "VRMS": "Vrms"}
UNITS = {"FREQ": "Hz", "PER": "s", "RIS": "s", "FALL": "s"}
FONT = {
    "0": "0E11131519110E", "1": "040C040404040E", "2": "0E11010204081F", "3": "1F02040201110E",
    "4": "02060A121F0202", "5": "1F101E0101110E", "6": "0608101E11110E", "7": "1F010204080808",
    "8": "0E11110E11110E", "9": "0E11110F01020C", "A": "0E1111111F1111", "B": "1E11111E11111E",
    "C": "0E11101010110E", "D": "1C12111111121C", "E": "1F10101E10101F", "F": "1F10101E101010",
    "G": "0E11101711110F", "H": "1111111F111111", "I": "0E04040404040E", "J": "0702020202120C",
    "K": "11121418141211", "L": "1010101010101F", "M": "111B1515111111", "N": "11111915131111",
    "O": "0E11111111110E", "P": "1E11111E101010", "Q": "0E11111115120D", "R": "1E11111E141211",
    "S": "0F10100E01011E", "T": "1F040404040404", "U": "1111111111110E", "V": "11111111110A04",
    "W": "1111111515150A", "X": "11110A040A1111", "Y": "1111110A040404", "Z": "1F01020408101F",
    "a": "00000E010F110F", "e": "00000E111F100E", "g": "00000F110F010E", "i": "04000C0404040E",
    "k": "10101214181412", "l": "0C04040404040E", "m": "00001A15151111", "n": "00001619111111",
    "p": "00001E111E1010", "q": "00000D130F0101", "r": "00001619101010", "s": "00000E100E011E",
    "u": "0000111111130D", "v": "00001111110A04", "x": "0000110A040A11", "z": "00001F0204081F",
    ".": "00000000000C0C", "-": "0000001F000000", "+": "0004041F040400", ":": "000C0C000C0C00",
    "/": "00010204081000", "'": "0C040800000000", "*": "0004150E150400", "=": "00001F001F0000",
}  # fmt: skip


def si(value: float, unit: str, digits: int = 3) -> str:
    """A value with an SI prefix and `digits` significant figures, such as 200mV or 1.000kHz."""
    if not math.isfinite(value) or abs(value) >= 9.9e36:
        return "*****"
    if value == 0:
        return f"0.{'0' * (digits - 1)}{unit}"
    for factor, prefix in ((1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m"), (1e-6, "u"), (1e-9, "n")):
        if abs(value) >= factor * 0.9995 or factor == 1e-9:
            scaled = value / factor
            whole = len(str(int(abs(round(scaled, max(0, digits - 1))))))
            return f"{scaled:.{max(0, digits - whole)}f}{prefix}{unit}"
    return f"{value:g}{unit}"


class Canvas:
    """An RGB frame buffer with the few drawing calls the screen needs."""

    def __init__(self) -> None:
        self.pixels = bytearray(bytes(BACKGROUND) * (WIDTH * HEIGHT))

    def blend(self, x: int, y: int, color: tuple[int, int, int], alpha: float = 1.0) -> None:
        if 0 <= x < WIDTH and 0 <= y < HEIGHT:
            i = (y * WIDTH + x) * 3
            for k in range(3):
                self.pixels[i + k] = round(self.pixels[i + k] * (1 - alpha) + color[k] * alpha)

    def rect(self, x: int, y: int, w: int, h: int, color: tuple[int, int, int], alpha: float = 1.0) -> None:
        for yy in range(max(0, y), min(HEIGHT, y + h)):
            for xx in range(max(0, x), min(WIDTH, x + w)):
                self.blend(xx, yy, color, alpha)

    def text(self, x: int, y: int, words: str, color: tuple[int, int, int], scale: int = 2) -> int:
        """Draw text from its top left corner and return the x just past it."""
        for char in words:
            rows = FONT.get(char)
            for r in range(7) if rows else ():
                bits = int(rows[r * 2 : r * 2 + 2], 16) if rows else 0
                for c in range(5):
                    if bits & (0x10 >> c):
                        self.rect(x + c * scale, y + r * scale, scale, scale, color)
            x += 6 * scale
        return x

    def png(self) -> bytes:
        stride = WIDTH * 3
        raw = b"".join(b"\x00" + bytes(self.pixels[y * stride : (y + 1) * stride]) for y in range(HEIGHT))

        def chunk(tag: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

        header = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)
        body = chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
        return b"\x89PNG\r\n\x1a\n" + body


def _graticule(canvas: Canvas) -> None:
    right, bottom = LEFT + COLUMNS * DIV_X, TOP + ROWS * DIV_Y
    mid_x, mid_y = LEFT + COLUMNS * DIV_X // 2, TOP + ROWS * DIV_Y // 2
    for k in range(COLUMNS + 1):
        x = LEFT + k * DIV_X
        for y in range(TOP, bottom + 1, 1 if k in (0, COLUMNS) else 5):
            canvas.blend(x, y, AXIS if k in (0, COLUMNS) else GRID)
    for k in range(ROWS + 1):
        y = TOP + k * DIV_Y
        for x in range(LEFT, right + 1, 1 if k in (0, ROWS) else 5):
            canvas.blend(x, y, AXIS if k in (0, ROWS) else GRID)
    for x in range(LEFT, right, DIV_X // 5):
        canvas.rect(x, mid_y - 3, 1, 7, AXIS)
    for y in range(TOP, bottom, DIV_Y // 5):
        canvas.rect(mid_x - 3, y, 7, 1, AXIS)


def _trace(canvas: Canvas, lows: list[float], highs: list[float], color: tuple[int, int, int]) -> None:
    span, points = COLUMNS * DIV_X, len(lows)
    mid_y, limit = TOP + ROWS * DIV_Y / 2, ROWS / 2
    previous: float | None = None
    for column in range(span):
        first, last = column * points // span, max(column * points // span + 1, (column + 1) * points // span)
        low = min(lows[first:last])
        high = max(highs[first:last])
        if previous is not None:
            low, high = min(low, previous), max(high, previous)
        previous = highs[last - 1]
        if high < -limit or low > limit:
            continue
        top = round(mid_y - min(high, limit) * DIV_Y)
        bottom = round(mid_y - max(low, -limit) * DIV_Y)
        x = LEFT + column
        for y in range(top - 3, bottom + 4):
            edge = max(top - y, y - bottom, 0)
            canvas.blend(x, y, color, 1.0 if edge == 0 else 0.34 / edge)


def render(snapshot: dict[str, Any]) -> bytes:
    """The screen for a `BenchScope.snapshot()`, as PNG bytes."""
    canvas = Canvas()
    _graticule(canvas)
    channels = {int(n): spec for n, spec in snapshot["channels"].items()}
    for n, trace in sorted((int(n), t) for n, t in snapshot["traces"].items()):
        _trace(canvas, trace["lows"], trace["highs"], COLORS[n])
    trigger = snapshot["trigger"]
    source = channels[trigger["source"]]
    level = (trigger["level"] + source["offset"]) / source["scale"]
    if abs(level) <= ROWS / 2:
        y = round(TOP + ROWS * DIV_Y / 2 - level * DIV_Y)
        for k in range(7):
            canvas.rect(LEFT + COLUMNS * DIV_X + 2 + k, y - (6 - k), 1, 2 * (6 - k) + 1, COLORS[trigger["source"]])
    point = round(LEFT + COLUMNS * DIV_X / 2 - snapshot["position"] / snapshot["timebase"] * DIV_X)
    if LEFT <= point <= LEFT + COLUMNS * DIV_X:
        for k in range(7):
            canvas.rect(point - (6 - k), TOP - 9 + k, 2 * (6 - k) + 1, 1, (236, 176, 70))
    word, color = STATES.get(snapshot["status"], ("STOP", (226, 92, 84)))
    canvas.rect(8, 6, 92, 24, color, 0.22)
    canvas.text(14, 11, word, color)
    canvas.text(120, 11, f"H {si(snapshot['timebase'], 's')}", TEXT)
    x = canvas.text(290, 11, f"T CH{trigger['source']} ", COLORS[trigger["source"]])
    canvas.text(x, 11, f"{'+' if trigger['slope'] == 'POS' else '-'} {si(trigger['level'], 'V')}", TEXT)
    gen = snapshot["generator"]
    text = "GEN OFF"
    if gen["output"]:
        text = f"GEN {gen['function']} {si(gen['frequency'], 'Hz', 4)} {si(gen['amplitude'], 'Vpp')}"
    canvas.text(WIDTH - 12 * len(text) - 8, 11, text, TEXT if gen["output"] else DIM)
    x = 8
    for n in sorted(channels):
        spec = channels[n]
        label = f"CH{n} {si(spec['scale'], 'V')}" if spec["shown"] else f"CH{n}"
        canvas.rect(x, HEIGHT - 38, 12 * len(label) + 10, 26, COLORS[n] if spec["shown"] else DIM, 0.2)
        x = canvas.text(x + 5, HEIGHT - 32, label, COLORS[n] if spec["shown"] else DIM) + 14
    for item in snapshot["measurements"][-3:]:
        name = NAMES.get(item["item"], item["item"].title())
        x = canvas.text(x + 6, HEIGHT - 32, f"{name} ", DIM)
        x = canvas.text(x, HEIGHT - 32, si(item["value"], UNITS.get(item["item"], "V")), COLORS[item["source"]])
    return canvas.png()
