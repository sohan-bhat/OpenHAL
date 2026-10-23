"""Firmata protocol constants, encoders and a streaming parser.

Written from the Firmata protocol documentation (github.com/firmata/protocol, protocol.md,
pin-state-query.md, capability-query.md, servos.md). Firmata is MIDI-like. Command bytes have
the top bit set, data bytes are 7-bit, and longer messages are sysex frames between 0xF0 and
0xF7. Multi-byte values are sent least significant 7 bits first.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

DIGITAL_MESSAGE: Final = 0x90
ANALOG_MESSAGE: Final = 0xE0
REPORT_ANALOG: Final = 0xC0
REPORT_DIGITAL: Final = 0xD0
SET_PIN_MODE: Final = 0xF4
SET_DIGITAL_PIN_VALUE: Final = 0xF5
REPORT_VERSION: Final = 0xF9
SYSTEM_RESET: Final = 0xFF
START_SYSEX: Final = 0xF0
END_SYSEX: Final = 0xF7

ANALOG_MAPPING_QUERY: Final = 0x69
ANALOG_MAPPING_RESPONSE: Final = 0x6A
CAPABILITY_QUERY: Final = 0x6B
CAPABILITY_RESPONSE: Final = 0x6C
PIN_STATE_QUERY: Final = 0x6D
PIN_STATE_RESPONSE: Final = 0x6E
EXTENDED_ANALOG: Final = 0x6F
SERVO_CONFIG: Final = 0x70
STRING_DATA: Final = 0x71
REPORT_FIRMWARE: Final = 0x79
SAMPLING_INTERVAL: Final = 0x7A

INPUT: Final = 0
OUTPUT: Final = 1
ANALOG: Final = 2
PWM: Final = 3
SERVO: Final = 4
PULLUP: Final = 11
MODE_NAMES: Final = {INPUT: "input", OUTPUT: "output", ANALOG: "analog", PWM: "pwm", SERVO: "servo", PULLUP: "pullup"}
NOT_ANALOG: Final = 0x7F

MAX_SYSEX: Final = 4096


def split14(value: int) -> tuple[int, int]:
    """A value up to 14 bits as LSB and MSB 7-bit bytes."""
    return value & 0x7F, (value >> 7) & 0x7F


def pack7(value: int) -> bytes:
    """Any non-negative value as 7-bit bytes, least significant first, at least one byte."""
    out = bytearray()
    while True:
        out.append(value & 0x7F)
        value >>= 7
        if not value:
            return bytes(out)


def unpack7(data: bytes) -> int:
    value = 0
    for index, byte in enumerate(data):
        value |= (byte & 0x7F) << (7 * index)
    return value


def sysex(command: int, payload: bytes = b"") -> bytes:
    return bytes([START_SYSEX, command]) + payload + bytes([END_SYSEX])


def decode_string(data: bytes) -> str:
    """Firmata strings are sent as pairs of 7-bit bytes per character."""
    chars = [data[index] | (data[index + 1] << 7) for index in range(0, len(data) - 1, 2)]
    return bytes(char & 0xFF for char in chars).decode("latin-1")


def encode_string(text: str) -> bytes:
    out = bytearray()
    for byte in text.encode("latin-1"):
        out += bytes(split14(byte))
    return bytes(out)


@dataclass(frozen=True, slots=True)
class Message:
    """One complete message from the board."""

    kind: str
    """digital, analog, version, sysex, or malformed."""
    index: int = 0
    value: int = 0
    data: bytes = b""


class Parser:
    """Turns a byte stream into messages. Stray data bytes are reported as malformed and skipped."""

    def __init__(self) -> None:
        self._command: int | None = None
        self._data = bytearray()
        self._in_sysex = False

    def feed(self, chunk: bytes) -> list[Message]:
        messages: list[Message] = []
        for byte in chunk:
            message = self._byte(byte)
            if message is not None:
                messages.append(message)
        return messages

    def _byte(self, byte: int) -> Message | None:
        if self._in_sysex:
            if byte == END_SYSEX:
                self._in_sysex = False
                data = bytes(self._data)
                self._data.clear()
                if not data:
                    return Message("malformed", data=b"empty sysex")
                return Message("sysex", index=data[0], data=data[1:])
            if byte & 0x80:
                self._in_sysex = False
                self._data.clear()
                return self._start(byte) or Message("malformed", data=b"unterminated sysex")
            if len(self._data) < MAX_SYSEX:
                self._data.append(byte)
            return None
        if byte & 0x80:
            return self._start(byte)
        if self._command is None:
            return Message("malformed", data=bytes([byte]))
        self._data.append(byte)
        if len(self._data) < 2:
            return None
        command, data = self._command, bytes(self._data)
        self._command = None
        self._data.clear()
        value = data[0] | (data[1] << 7)
        if command & 0xF0 == DIGITAL_MESSAGE:
            return Message("digital", index=command & 0x0F, value=value)
        if command & 0xF0 == ANALOG_MESSAGE:
            return Message("analog", index=command & 0x0F, value=value)
        return Message("version", index=data[0], value=data[1])

    def _start(self, byte: int) -> Message | None:
        self._data.clear()
        if byte == START_SYSEX:
            self._in_sysex = True
            self._command = None
            return None
        if byte & 0xF0 in (DIGITAL_MESSAGE, ANALOG_MESSAGE) or byte == REPORT_VERSION:
            self._command = byte
            return None
        self._command = None
        return Message("malformed", data=bytes([byte]))


def parse_capabilities(data: bytes) -> list[dict[int, int]]:
    """CAPABILITY_RESPONSE payload to a list, per pin, of mode to resolution."""
    pins: list[dict[int, int]] = []
    current: dict[int, int] = {}
    index = 0
    while index < len(data):
        if data[index] == 0x7F:
            pins.append(current)
            current = {}
            index += 1
            continue
        if index + 1 >= len(data):
            break
        current[data[index]] = data[index + 1]
        index += 2
    return pins
