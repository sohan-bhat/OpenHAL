"""Simulated boards running the OpenHAL Arduino library's examples.

They speak the real protocol over an in-memory line transport, enforce their own limits and apply
their safe state when heartbeats stop. The desk fan cools a warm room. The plant waterer
(examples/plant-waterer/) wets the soil while its pump runs and refuses to pump from an empty tank.
Tests, the conformance case and `openhal demo` use them.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from collections.abc import Callable
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
    states: tuple[str, ...] = ()
    internal: bool = False


@dataclass
class SimAction:
    """An action the board runs. `run` gets the arguments by name and returns a refusal reason or None."""

    name: str
    args: tuple[tuple[str, str, float, float], ...]
    run: Callable[[dict[str, float]], str | None]


@dataclass
class FirmwareSimulator:
    """The desk fan board. Defaults match firmware/arduino/OpenHAL/examples/DeskFan/DeskFan.ino."""

    product: str = "desk-fan"
    version: str = "1.0.0"
    heartbeat_ms: int = 2000
    ambient_c: float = 31.0
    seed: int = 7
    channels: dict[str, SimChannel] = field(default_factory=dict)
    actions: dict[str, SimAction] = field(default_factory=dict)
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
            if channel.internal:
                continue
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
                if channel.states:
                    item["u"], item["s"] = "enum", list(channel.states)
                read.append(item)
        described = {"p": self.product, "v": self.version, "hb": self.heartbeat_ms, "r": read, "w": write}
        if self.actions:
            described["a"] = [
                {"n": action.name, "g": [{"n": n, "u": u, "min": lo, "max": hi} for n, u, lo, hi in action.args]}
                for action in self.actions.values()
            ]
        return described

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
        elif verb == "READ" and len(args) == 1 and self._visible(args[0]):
            self._send(encode(seq, "VAL", args[0], self._shown(self.channels[args[0]])))
        elif verb == "WRITE" and len(args) == 2 and self._visible(args[0]):
            self._set_output(seq, args[0], args[1])
        elif verb == "ACT" and args and args[0] in self.actions:
            self._run_action(seq, self.actions[args[0]], args[1:])
        else:
            self._send(encode(seq, "ERR", "unknown", verb))

    def _visible(self, name: str) -> bool:
        return name in self.channels and not self.channels[name].internal

    @staticmethod
    def _shown(channel: SimChannel) -> str:
        if channel.states:
            return channel.states[int(channel.value)]
        return format_number(round(channel.value, 2))

    def _run_action(self, seq: int, action: SimAction, words: tuple[str, ...]) -> None:
        if len(words) != 2 * len(action.args):
            self._send(encode(seq, "ERR", "format", action.name))
            return
        given = dict(zip(words[::2], words[1::2], strict=True))
        values: dict[str, float] = {}
        for name, _unit, low, high in action.args:
            try:
                value = parse_number(given[name])
            except (KeyError, ProtocolError):
                self._send(encode(seq, "ERR", "format", name))
                return
            if value < low or value > high:
                bound, limit = ("max", high) if value > high else ("min", low)
                self._send(encode(seq, "ERR", "limit", name, bound, format_number(limit)))
                return
            values[name] = value
        refused = action.run(values)
        if refused:
            self._send(encode(seq, "ERR", "interlock", refused))
            return
        self._send(encode(seq, "OK", action.name))

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


@dataclass
class PlantWatererSimulator(FirmwareSimulator):
    """The plant waterer board. Defaults match examples/plant-waterer/plant-waterer.ino.

    `speed` runs the soil and the pump faster than real time, so a 20 s watering can be recorded in
    half a second. Heartbeats always use real time. Soil moisture rises `wet_per_s` points per second
    of pumping and nothing dries it, so a run is the same every time.
    """

    product: str = "plant-waterer"
    heartbeat_ms: int = 3000
    moisture: float = 31.0
    tank_ok: bool = True
    wet_per_s: float = 0.75
    max_run_s: float = 30.0
    speed: float = 1.0

    def __post_init__(self) -> None:
        if not self.channels:
            self.channels = {
                "soil_moisture": SimChannel("soil_moisture", "percent", self.moisture, every_ms=1000, lo=0, hi=100),
                "tank": SimChannel("tank", "enum", 1.0 if self.tank_ok else 0.0, every_ms=1000, states=("empty", "ok")),
                "pump": SimChannel("pump", "bool", 0.0, writable=True, maximum=1, internal=True),
            }
        if not self.actions:
            self.actions = {
                "water": SimAction("water", (("duration", "s", 1.0, 30.0),), self._water),
                "stop": SimAction("stop", (), self._stop),
            }
        self._real_start = time.monotonic()
        self._pump_until = 0.0
        self._clock = self.now()
        super().__post_init__()

    def now(self) -> float:
        """Board time in seconds, `speed` times faster than real time."""
        return (time.monotonic() - self._real_start) * self.speed

    @property
    def pumping(self) -> bool:
        self._step()
        return self.channels["pump"].value > 0

    def remaining_s(self) -> float:
        """Real seconds until the pump stops on its own, 0 when it isn't running."""
        if not self.pumping:
            return 0.0
        return max(0.0, self._pump_until - self.now()) / self.speed + 0.05

    def refill(self) -> None:
        """Someone fills the tank, so the float switch reads ok."""
        self._step()
        self.tank_ok = True
        self.channels["tank"].value = 1.0

    def drain(self) -> None:
        """The tank runs dry. A running pump stops at once, as the sketch's loop() does."""
        self._step()
        self.tank_ok = False
        self.channels["tank"].value = 0.0
        if self.channels["pump"].value > 0:
            self._apply_safe("tank empty")

    def _water(self, args: dict[str, float]) -> str | None:
        if not self.tank_ok:
            return "tank_empty"
        self._step()
        self.channels["pump"].value = 1.0
        self._pump_until = self._clock + min(args["duration"], self.max_run_s)
        return None

    def _stop(self, _args: dict[str, float]) -> str | None:
        self.channels["pump"].value = 0.0
        return None

    def _step(self) -> None:
        super()._step()
        now = self.now()
        pump = self.channels["pump"]
        if pump.value > 0:
            ran = max(0.0, min(now, self._pump_until) - self._clock)
            self.moisture = min(100.0, self.moisture + self.wet_per_s * ran)
            if now >= self._pump_until:
                pump.value = 0.0
        self._clock = now
        self.channels["soil_moisture"].value = self.moisture


PROFILES: dict[str, Callable[[], FirmwareSimulator]] = {
    "desk-fan": FirmwareSimulator,
    "plant-waterer": PlantWatererSimulator,
}

SIMULATORS: dict[str, FirmwareSimulator] = {}
"""Simulators by name, so a test or the demo can reach the board behind `port: sim:<name>`."""


def simulator_for(name: str) -> FirmwareSimulator:
    """The simulator behind `port: sim:<name>`. `plant-waterer` gets the plant waterer board."""
    if name not in SIMULATORS:
        profile = PROFILES.get(name)
        product = name if name != "default" else "desk-fan"
        SIMULATORS[name] = profile() if profile else FirmwareSimulator(product=product)
    return SIMULATORS[name]
