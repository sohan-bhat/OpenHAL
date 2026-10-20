"""A simulated board running the OpenHAL Arduino library's desk fan example.

It speaks the real protocol over an in-memory line transport, enforces its own limits, applies its
safe state when heartbeats stop, and gives the temperature some physics: the fan cools a warm room.
Tests, the conformance case and `openhal demo` use it.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import dataclass, field
from typing import Any

from openhal.drivers.openhal_firmware.protocol import (
    ProtocolError,
    decode,
    encode,
    format_number,
    parse_number,
)


@dataclass
class SimChannel:
    name: str
    unit: str
    value: float
    writable: bool = False
    minimum: float = 0.0
    maximum: float = 0.0
    safe: float = 0.0
    rate: float | None = None
    every_ms: int = 0
    lo: float | None = None
    hi: float | None = None


@dataclass
class FirmwareSimulator:
    """The desk fan board. Defaults match firmware/arduino/OpenHAL/examples/DeskFan/DeskFan.ino."""

    product: str = "desk-fan"
    version: str = "1.0.0"
    heartbeat_ms: int = 2000
    ambient_c: float = 31.0
    seed: int = 7
    channels: dict[str, SimChannel] = field(default_factory=dict)
    to_host: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    safe_events: int = 0
    corrupt_next: bool = False
    silent: bool = False
    received: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.channels:
            self.channels = {
                "temperature": SimChannel("temperature", "degC", self.ambient_c, lo=-20, hi=80),
                "fan_speed": SimChannel(
                    "fan_speed", "percent", 0.0, writable=True, minimum=0, maximum=100, safe=0, rate=20
                ),
            }
        self._random = random.Random(self.seed)  # noqa: S311 (simulation, not security)
        self._last_heartbeat = time.monotonic()
        self._last_step = time.monotonic()

    def description(self) -> dict[str, Any]:
        read = []
        write = []
        for channel in self.channels.values():
            if channel.writable:
                entry: dict[str, Any] = {
                    "n": channel.name,
                    "u": channel.unit,
                    "min": channel.minimum,
                    "max": channel.maximum,
                    "safe": channel.safe,
                }
                if channel.rate:
                    entry["rate"] = channel.rate
                write.append(entry)
            else:
                item: dict[str, Any] = {"n": channel.name, "u": channel.unit, "e": channel.every_ms}
                if channel.lo is not None and channel.hi is not None:
                    item["lo"], item["hi"] = channel.lo, channel.hi
                read.append(item)
        return {"p": self.product, "v": self.version, "hb": self.heartbeat_ms, "r": read, "w": write}

    def _step(self) -> None:
        now = time.monotonic()
        elapsed = min(now - self._last_step, 10.0)
        self._last_step = now
        if self.heartbeat_ms and (now - self._last_heartbeat) * 1000 > self.heartbeat_ms:
            self._apply_safe("heartbeat lost")
            self._last_heartbeat = now
        fan = self.channels.get("fan_speed")
        temperature = self.channels.get("temperature")
        if fan is not None and temperature is not None:
            target = self.ambient_c - 7.0 * fan.value / 100.0
            temperature.value += (target - temperature.value) * min(1.0, 0.25 * elapsed) + self._random.uniform(
                -0.03, 0.03
            )

    def _apply_safe(self, reason: str) -> None:
        changed = False
        for channel in self.channels.values():
            if channel.writable and channel.value != channel.safe:
                channel.value = channel.safe
                changed = True
        self.safe_events += 1
        if changed:
            self._send(encode(0, "SAFE", reason.replace(" ", "_")))

    def _send(self, line: str) -> None:
        if self.corrupt_next:
            self.corrupt_next = False
            line = line.replace("*", "*0", 1)
        self.to_host.put_nowait(line)

    def handle(self, line: str) -> None:
        """Process one line from the host, as the board's loop() would."""
        self.received.append(line)
        self._step()
        if self.silent:
            return
        try:
            message = decode(line)
        except ProtocolError:
            self._send(encode(0, "ERR", "checksum", "bad_line"))
            return
        seq, verb, args = message.seq, message.verb, message.args
        if verb == "HELLO":
            self._send(encode(seq, "OK", "openhal", "1", self.product, self.version))
        elif verb == "DESC":
            self._send(encode(seq, "DESC", json.dumps(self.description(), separators=(",", ":"))))
        elif verb == "HB":
            self._last_heartbeat = time.monotonic()
            self._send(encode(seq, "OK"))
        elif verb == "SAFE":
            self._apply_safe("host_request")
            self._send(encode(seq, "OK"))
        elif verb == "READ" and len(args) == 1 and args[0] in self.channels:
            self._send(encode(seq, "VAL", args[0], format_number(round(self.channels[args[0]].value, 2))))
        elif verb == "WRITE" and len(args) == 2 and args[0] in self.channels:
            self._set_output(seq, args[0], args[1])
        else:
            self._send(encode(seq, "ERR", "unknown", verb))

    def _set_output(self, seq: int, name: str, text: str) -> None:
        channel = self.channels[name]
        if not channel.writable:
            self._send(encode(seq, "ERR", "unknown", name))
            return
        try:
            value = parse_number(text)
        except ProtocolError:
            self._send(encode(seq, "ERR", "format", name))
            return
        if value < channel.minimum or value > channel.maximum:
            bound = "max" if value > channel.maximum else "min"
            limit = channel.maximum if bound == "max" else channel.minimum
            self._send(encode(seq, "ERR", "limit", name, bound, format_number(limit)))
            return
        channel.value = value
        self._send(encode(seq, "OK", name, format_number(value)))


class SimTransport:
    """A line transport connected to a FirmwareSimulator, with the same interface as the serial one."""

    def __init__(self, simulator: FirmwareSimulator) -> None:
        self.simulator = simulator
        self.open = False

    async def connect(self) -> None:
        # Opening a real port resets most boards, so nothing from an earlier session is left to read.
        while not self.simulator.to_host.empty():
            self.simulator.to_host.get_nowait()
        self.open = True

    async def write_line(self, line: str) -> None:
        if not self.open:
            raise ConnectionError("The simulated port is closed.")
        self.simulator.handle(line)

    async def read_line(self) -> str:
        if not self.open:
            raise ConnectionError("The simulated port is closed.")
        return await self.simulator.to_host.get()

    async def close(self) -> None:
        self.open = False


SIMULATORS: dict[str, FirmwareSimulator] = {}
"""Simulators by name, so a test or the demo can reach the board behind `port: sim:<name>`."""


def simulator_for(name: str) -> FirmwareSimulator:
    if name not in SIMULATORS:
        SIMULATORS[name] = FirmwareSimulator(product=name if name != "default" else "desk-fan")
    return SIMULATORS[name]
