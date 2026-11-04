"""A New Era NE-500 syringe pump that answers its RS-232 Basic mode protocol, for the library file's tests.

The protocol follows New Era's NE-500 user manual, publication 1200-02. A command ends with CR,
spaces don't count and lower case is read as upper case. Every reply is a packet, STX, the
two digit address, a status character and any data, then ETX. The status is I infusing, W
withdrawing, S stopped or P paused, and an error follows it as ?, ?NA or ?OOR.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

SUMMARY = """
10.1 RS-232 Command Summary
DIA  [ < float > ] Syringe inside diameter
RAT {C | I ] [ <float> [ UM | MM | UH | MH ]] Pumping rate
VOL [ <float> | <volume units>] Volume to be Dispensed, or set Volume units
DIR  [ INF | WDR | REV | STK ] Pumping direction
RUN [ <phase data> ] Starts the Pumping Program
PUR Start purge
STP Stop/pauses the Pumping Program
DIS Query volume dispensed
CLD { INF | WDR } Clear volume dispensed
VER Query firmware version
"""
"""The NE-500 command summary as its manual's appendix prints it, typo in RAT and all."""

RATE_ML_PER_H = {"UM": 0.06, "MM": 60.0, "UH": 0.001, "MH": 1.0}
NUMBER = re.compile(r"^\d{0,4}(\.\d{0,3})?$")


def _number(text: str) -> float | None:
    digits = text.replace(".", "")
    if not text or not NUMBER.match(text) or len(digits) > 4 or not digits:
        return None
    return float(text)


@dataclass
class Pump:
    diameter_mm: float = 14.43
    rate: float = 1.0
    rate_units: str = "MH"
    volume: float = 0.0
    volume_units: str = "ML"
    direction: str = "INF"
    status: str = "S"
    infused: float = 0.0
    withdrawn: float = 0.0
    time_scale: float = 1.0
    started: float | None = None
    buffer: bytes = b""
    sent: list[str] = field(default_factory=list)

    def receive(self, data: bytes) -> bytes:
        self.buffer += data
        out = b""
        while b"\r" in self.buffer:
            line, self.buffer = self.buffer.split(b"\r", 1)
            command = re.sub(r"[\s\x00-\x1f]", "", line.decode("ascii")).upper()
            self.sent.append(command)
            out += b"\x02" + self.answer(command).encode("ascii") + b"\x03"
        return out

    def _settle(self) -> None:
        if self.started is None or self.status not in ("I", "W"):
            return
        hours = (time.monotonic() - self.started) * self.time_scale / 3600
        pumped = hours * self.rate * RATE_ML_PER_H[self.rate_units]
        done = self.volume > 0 and pumped >= self.volume
        pumped = min(pumped, self.volume) if self.volume > 0 else pumped
        if self.status == "I":
            self.infused += pumped
        else:
            self.withdrawn += pumped
        self.started = time.monotonic()
        if done:
            self.status, self.started = "S", None

    def reply(self, data: str = "") -> str:
        return f"00{self.status}{data}"

    def answer(self, command: str) -> str:
        self._settle()
        running = self.status in ("I", "W")
        if command == "":
            return self.reply()
        if command == "VER":
            return self.reply("NE500V3.928")
        if command == "DIS":
            return self.reply(f"I{self.infused:.3f}W{self.withdrawn:.3f}{self.volume_units}")
        if command == "DIA":
            return self.reply(f"{self.diameter_mm:g}")
        if command.startswith("DIA"):
            value = _number(command[3:])
            if value is None or not 0.1 <= value <= 50:
                return self.reply("?OOR")
            if running:
                return self.reply("?NA")
            self.diameter_mm = value
            return self.reply()
        if command == "RAT":
            return self.reply(f"{self.rate:g}{self.rate_units}")
        if command.startswith("RAT"):
            body, units = command[3:], self.rate_units
            if body[-2:] in RATE_ML_PER_H:
                body, units = body[:-2], body[-2:]
            value = _number(body)
            if value is None or not 0 < value * RATE_ML_PER_H[units] <= 1000:
                return self.reply("?OOR")
            self.rate, self.rate_units = value, units
            return self.reply()
        if command == "VOL":
            return self.reply(f"{self.volume:g}{self.volume_units}")
        if command in ("VOLML", "VOLUL"):
            self.volume_units = command[3:]
            return self.reply()
        if command.startswith("VOL"):
            value = _number(command[3:])
            if value is None:
                return self.reply("?OOR")
            if running:
                return self.reply("?NA")
            self.volume = value
            return self.reply()
        if command == "DIR":
            return self.reply(self.direction)
        if command in ("DIRINF", "DIRWDR"):
            if running:
                return self.reply("?NA")
            self.direction = command[3:]
            return self.reply()
        if command == "RUN":
            self.status, self.started = ("I" if self.direction == "INF" else "W"), time.monotonic()
            return self.reply()
        if command == "STP":
            self.status, self.started = ("P" if running else "S"), None
            return self.reply()
        if command in ("CLDINF", "CLDWDR"):
            if running:
                return self.reply("?NA")
            if command == "CLDINF":
                self.infused = 0.0
            else:
                self.withdrawn = 0.0
            return self.reply()
        return self.reply("?")
