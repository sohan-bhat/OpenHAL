"""A GRBL 1.1 controller simulator for tests and the conformance case.

It models the documented line protocol (gnea/grbl wiki, "Grbl v1.1 Interface" and "Commands"),
written from the documentation and not from GRBL's GPL source. It plugs into
`openhal.drivers.serial.simulator.SerialSimulator`, so the driver runs its real serial code.

- Line commands end with a newline and get `ok` or `error:N`. Motion lines get `ok` once they are
  queued, and the machine then moves at the programmed feed in simulated time.
- Realtime bytes act at once and never get `ok`. `?` returns a status report, `!` holds the feed,
  `~` resumes, 0x85 cancels a jog and 0x18 soft resets.
- A reset while moving or holding raises ALARM:3. Soft and hard limit alarms block everything
  except `?` and a reset, and print `[MSG:Reset to continue]`, as GRBL does.
- While in alarm, G-code gets error:9 until `$X` or `$H`.
"""

from __future__ import annotations

import math
import re
import threading
import time
from collections import deque
from dataclasses import dataclass

AXES = ("X", "Y", "Z")
DEFAULTS: dict[int, float] = {
    0: 10,
    1: 25,
    2: 0,
    3: 0,
    4: 0,
    5: 0,
    6: 0,
    10: 1,
    11: 0.010,
    12: 0.002,
    13: 0,
    20: 0,
    21: 0,
    22: 0,
    23: 0,
    24: 25.0,
    25: 500.0,
    26: 250,
    27: 1.0,
    30: 1000,
    31: 0,
    32: 0,
    100: 250.0,
    101: 250.0,
    102: 250.0,
    110: 500.0,
    111: 500.0,
    112: 500.0,
    120: 10.0,
    121: 10.0,
    122: 10.0,
    130: 300.0,
    131: 300.0,
    132: 80.0,
}
MOTION_STATES = ("Run", "Jog", "Home", "Hold:1", "Hold:0")
WORD = re.compile(r"([A-Z])([-+]?(?:\d+\.?\d*|\.\d+))")


@dataclass
class Move:
    target: list[float]
    rate: float
    jog: bool = False


class GrblMachine:
    """The state of one simulated GRBL controller. Thread safe, ports call it from worker threads."""

    def __init__(
        self, *, homing: bool = False, soft_limits: bool = False, laser: bool = False, version: str = "1.1h"
    ) -> None:
        self.version = version
        self.settings = dict(DEFAULTS)
        self.settings[22] = 1 if homing else 0
        self.settings[20] = 1 if soft_limits else 0
        self.settings[32] = 1 if laser else 0
        self.state = "Alarm" if homing else "Idle"
        self.critical = False
        self.mpos = [0.0, 0.0, 0.0]
        self.g54 = [0.0, 0.0, 0.0]
        self.g92 = [0.0, 0.0, 0.0]
        self.distance = "G90"
        self.units = "G21"
        self.motion = "G0"
        self.feed = 0.0
        self.spindle = "M5"
        self.s_word = 0.0
        self.coolant: set[str] = set()
        self.time_scale = 1.0
        self.home_time_s = 0.2
        self.unsupported: set[str] = set()
        self.received: list[str] = []
        self.realtime: list[bytes] = []
        self.reports = 0
        self._line = b""
        self._moves: deque[Move] = deque()
        self._current: Move | None = None
        self._start: list[float] = [0.0, 0.0, 0.0]
        self._started_at = 0.0
        self._home_until = 0.0
        self._out: list[str] = []
        self._accessory_changed = True
        self._lock = threading.RLock()

    def on_open(self) -> bytes:
        """Arduino boards reset when the port opens, so the banner comes first."""
        with self._lock:
            return self._banner().encode("ascii")

    def _banner(self) -> str:
        text = f"\r\nGrbl {self.version} ['$' for help]\r\n"
        if self.state == "Alarm":
            text += "[MSG:'$H'|'$X' to unlock]\r\n"
        return text

    @property
    def speed(self) -> float:
        """The spindle speed GRBL reports in FS. Zero while the spindle is off."""
        if self.spindle == "M5":
            return 0.0
        return max(self.settings[31], min(self.settings[30], self.s_word))

    @property
    def wco(self) -> list[float]:
        return [self.g54[i] + self.g92[i] for i in range(3)]

    def receive(self, data: bytes) -> bytes:
        with self._lock:
            now = time.monotonic()
            self._advance(now)
            for value in data:
                byte = bytes([value])
                if byte in (b"?", b"!", b"~", b"\x18", b"\x85") or value >= 0x80:
                    self.realtime.append(byte)
                    self._realtime(byte, now)
                elif byte in (b"\n", b"\r"):
                    line = self._line.decode("ascii", errors="replace").strip()
                    self._line = b""
                    if line:
                        self.received.append(line)
                        if not self.critical:
                            self._out.append(self._execute(line.upper().replace(" ", ""), now))
                else:
                    self._line += byte
            return self._flush()

    def poll(self, now: float) -> bytes:
        with self._lock:
            self._advance(now)
            return self._flush()

    def _flush(self) -> bytes:
        out = "".join(line if line.endswith("\r\n") else line + "\r\n" for line in self._out if line)
        self._out.clear()
        return out.encode("ascii")

    def _realtime(self, byte: bytes, now: float) -> None:
        if byte == b"?":
            self._out.append(self.status())
        elif byte == b"\x18":
            self._reset()
        elif self.critical:
            return
        elif byte == b"!":
            if self.state == "Jog":
                self._cancel_jog()
            elif self.state == "Run":
                self.state = "Hold:0"
        elif byte == b"~":
            if self.state == "Hold:0":
                self._started_at = now
                self._start = list(self.mpos)
                self.state = "Run"
        elif byte == b"\x85" and self.state == "Jog":
            self._cancel_jog()

    def _cancel_jog(self) -> None:
        self._moves.clear()
        self._current = None
        self.state = "Idle"

    def _reset(self) -> None:
        moving = self.state in MOTION_STATES
        if moving:
            code = 6 if self.state == "Home" else 3
            self._out.append(f"ALARM:{code}")
            self.state = "Alarm"
        elif self.state != "Alarm":
            self.state = "Idle"
        self.critical = False
        self._moves.clear()
        self._current = None
        self.spindle = "M5"
        self.coolant.clear()
        self._accessory_changed = True
        self._line = b""
        self._out.append(self._banner())

    def _alarm(self, code: int, *, critical: bool) -> None:
        self._moves.clear()
        self._current = None
        self.state = "Alarm"
        self.spindle = "M5"
        self.coolant.clear()
        self._out.append(f"ALARM:{code}")
        if critical:
            self.critical = True
            self._out.append("[MSG:Reset to continue]")

    def trip_hard_limit(self) -> None:
        """Press a limit switch. GRBL halts at once and stays halted until a reset."""
        with self._lock:
            self._alarm(1, critical=True)

    def _advance(self, now: float) -> None:
        if self.state == "Home" and now >= self._home_until:
            self.mpos = [0.0, 0.0, 0.0]
            self.state = "Idle"
            self._out.append("ok")
            return
        if self.state not in ("Run", "Jog"):
            return
        while True:
            if self._current is None:
                if not self._moves:
                    self.state = "Idle"
                    return
                self._current = self._moves.popleft()
                self._start = list(self.mpos)
                self._started_at = now
                self.state = "Jog" if self._current.jog else "Run"
            move = self._current
            distance = math.dist(self._start, move.target)
            duration = 0.0 if move.rate <= 0 else distance / move.rate * 60.0
            elapsed = (now - self._started_at) * self.time_scale
            if elapsed >= duration:
                self.mpos = list(move.target)
                self._current = None
                continue
            fraction = elapsed / duration
            self.mpos = [self._start[i] + (move.target[i] - self._start[i]) * fraction for i in range(3)]
            return

    def status(self) -> str:
        """The reply to `?`."""
        self.reports += 1
        inch = self.settings[13] == 1
        scale = 1 / 25.4 if inch else 1.0
        state = "Alarm" if self.critical else self.state
        if int(self.settings[10]) & 1:
            position = "MPos:" + ",".join(f"{value * scale:.3f}" for value in self.mpos)
        else:
            position = "WPos:" + ",".join(f"{(self.mpos[i] - self.wco[i]) * scale:.3f}" for i in range(3))
        moving = self._current is not None and state in ("Run", "Jog")
        rate = (self._current.rate if moving and self._current else 0.0) * scale
        fields = [state, position, f"FS:{rate:.0f},{self.speed:.0f}"]
        if self.reports % 10 == 1:
            fields.append("WCO:" + ",".join(f"{value * scale:.3f}" for value in self.wco))
        if self._accessory_changed or self.reports % 10 == 1:
            self._accessory_changed = False
            fields.append("Ov:100,100,100")
            accessories = (
                ("S" if self.spindle == "M3" else "C" if self.spindle == "M4" else "")
                + ("F" if "M8" in self.coolant else "")
                + ("M" if "M7" in self.coolant else "")
            )
            if accessories:
                fields.append(f"A:{accessories}")
        return "<" + "|".join(fields) + ">"

    def _execute(self, line: str, now: float) -> str:
        if line.startswith("$"):
            return self._system(line[1:], now)
        if self.state == "Alarm" or self.state == "Jog":
            return "error:9"
        return self._gcode(line, now)

    def _system(self, command: str, now: float) -> str:
        if command == "":
            return "[HLP:$$ $# $G $I $N $x=val $Nx=line $J=line $SLP $C $X $H ~ ! ? ctrl-x]\r\nok"
        if command == "$":
            if self.state in ("Run", "Hold:0", "Hold:1"):
                return "error:8"
            return "\r\n".join(f"${key}={_fmt(value)}" for key, value in sorted(self.settings.items())) + "\r\nok"
        if command == "I":
            return f"[VER:{self.version}.20190830:]\r\n[OPT:V,15,128]\r\nok"
        if command == "G":
            words = [self.motion, "G54", "G17", self.units, self.distance, "G94", "M0", self.spindle]
            words += sorted(self.coolant) or ["M9"]
            words += ["T0", f"F{_fmt(self.feed)}", f"S{_fmt(self.s_word)}"]
            return f"[GC:{' '.join(words)}]\r\nok"
        if command == "#":
            if self.state in ("Run", "Hold:0", "Hold:1"):
                return "error:8"
            rows = [f"[G54:{_triple(self.g54)}]"] + [f"[G5{n}:0.000,0.000,0.000]" for n in range(5, 10)]
            rows += ["[G28:0.000,0.000,0.000]", "[G30:0.000,0.000,0.000]", f"[G92:{_triple(self.g92)}]"]
            rows += ["[TLO:0.000]", "[PRB:0.000,0.000,0.000:0]"]
            return "\r\n".join(rows) + "\r\nok"
        if command == "X":
            if self.state == "Alarm":
                self.state = "Idle"
                return "[MSG:Caution: Unlocked]\r\nok"
            return "ok"
        if command == "H":
            if self.settings[22] != 1:
                return "error:5"
            if self.state not in ("Idle", "Alarm"):
                return "error:8"
            self.state = "Home"
            self._home_until = now + self.home_time_s / self.time_scale
            return ""
        if command.startswith("J="):
            return self._jog(command[2:], now)
        match = re.fullmatch(r"(\d{1,3})=([-+]?[\d.]+)", command)
        if match:
            if self.state not in ("Idle", "Alarm"):
                return "error:8"
            self.settings[int(match.group(1))] = float(match.group(2))
            return "ok"
        return "error:3"

    def _words(self, line: str) -> list[tuple[str, float]] | str:
        position = 0
        words: list[tuple[str, float]] = []
        for match in WORD.finditer(line):
            if match.start() != position:
                return "error:1" if not line[position].isalpha() else "error:2"
            words.append((match.group(1), float(match.group(2))))
            position = match.end()
        if position != len(line):
            return "error:1" if not line[position].isalpha() else "error:2"
        return words

    def _target(self, axes: dict[str, float], distance: str, units: str, machine: bool) -> list[float]:
        scale = 25.4 if units == "G20" else 1.0
        target = list(self.mpos)
        for index, axis in enumerate(AXES):
            if axis not in axes:
                continue
            value = axes[axis] * scale
            if distance == "G91":
                target[index] = self.mpos[index] + value
            else:
                target[index] = value if machine else value + self.wco[index]
        return target

    def _outside(self, target: list[float]) -> bool:
        if self.settings[20] != 1:
            return False
        return any(not -self.settings[130 + i] - 1e-6 <= target[i] <= 1e-6 for i in range(3))

    def _jog(self, text: str, now: float) -> str:
        if self.state not in ("Idle", "Jog"):
            return "error:8"
        words = self._words(text)
        if isinstance(words, str):
            return words
        distance, units, machine, feed = self.distance, self.units, False, None
        axes: dict[str, float] = {}
        for letter, value in words:
            code = f"{letter}{value:g}"
            if code in ("G90", "G91"):
                distance = code
            elif code in ("G20", "G21"):
                units = code
            elif code == "G53":
                machine = True
            elif letter in AXES:
                axes[letter] = value
            elif letter == "F":
                feed = value
            else:
                return "error:16"
        if feed is None:
            return "error:22"
        if not axes:
            return "error:26"
        target = self._target(axes, distance, units, machine)
        if self._outside(target):
            return "error:15"
        rate = feed * (25.4 if units == "G20" else 1.0)
        self._moves.append(Move(target, rate, jog=True))
        if self.state == "Idle":
            self.state = "Jog"
            self._advance(now)
        return "ok"

    def _gcode(self, line: str, now: float) -> str:
        words = self._words(line)
        if isinstance(words, str):
            return words
        axes: dict[str, float] = {}
        codes: list[str] = []
        values: dict[str, float] = {}
        for letter, value in words:
            if letter in ("G", "M"):
                code = f"{letter}{value:g}"
                if code in self.unsupported:
                    return "error:20"
                codes.append(code)
            elif letter in AXES:
                axes[letter] = value
            elif letter in ("F", "S", "P", "L"):
                values[letter] = value
            else:
                return "error:20"
        known = {"G0", "G1", "G4", "G10", "G20", "G21", "G53", "G90", "G91", "M3", "M4", "M5", "M7", "M8", "M9"}
        for code in codes:
            if code not in known:
                return "error:20"
        for code in codes:
            if code in ("G20", "G21"):
                self.units = code
            elif code in ("G90", "G91"):
                self.distance = code
        if "F" in values:
            self.feed = values["F"] * (25.4 if self.units == "G20" else 1.0)
        if "G10" in codes:
            return self._set_offset(axes, values)
        if "S" in values:
            self.s_word = values["S"]
        for code in codes:
            if code in ("M3", "M4"):
                self.spindle = code
                self._accessory_changed = True
            elif code == "M5":
                self.spindle = "M5"
                self._accessory_changed = True
            elif code in ("M7", "M8"):
                self.coolant.add(code)
                self._accessory_changed = True
            elif code == "M9":
                self.coolant.clear()
                self._accessory_changed = True
        motion = next((code for code in codes if code in ("G0", "G1")), None)
        if motion is not None:
            self.motion = motion
        if axes:
            return self._queue_motion(axes, "G53" in codes, now)
        return "ok"

    def _set_offset(self, axes: dict[str, float], values: dict[str, float]) -> str:
        if values.get("L") != 20 or values.get("P", 0) not in (0, 1):
            return "error:20"
        if not axes:
            return "error:26"
        scale = 25.4 if self.units == "G20" else 1.0
        for index, axis in enumerate(AXES):
            if axis in axes:
                self.g54[index] = self.mpos[index] - self.g92[index] - axes[axis] * scale
        return "ok"

    def _queue_motion(self, axes: dict[str, float], machine: bool, now: float) -> str:
        if self.motion == "G1" and self.feed <= 0:
            return "error:22"
        target = self._target(axes, self.distance, self.units, machine)
        if self._outside(target):
            self._alarm(2, critical=True)
            return ""
        rate = self.feed if self.motion == "G1" else self.settings[110]
        self._moves.append(Move(target, rate))
        if self.state == "Idle":
            self.state = "Run"
            self._advance(now)
        return "ok"


def _fmt(value: float) -> str:
    return f"{value:.3f}" if value != int(value) else str(int(value))


def _triple(values: list[float]) -> str:
    return ",".join(f"{value:.3f}" for value in values)
