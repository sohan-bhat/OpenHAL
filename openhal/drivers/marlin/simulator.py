"""A Marlin firmware simulator for tests and the conformance case.

It follows the host protocol described in the Marlin G-code reference (marlinfw.org/docs/gcode).
Lines may carry `N<line>` numbers and a `*<checksum>` (XOR of every byte before the `*`). Every
command is answered with `ok` once it finishes. Long moves such as G28 send
`echo:busy: processing` keepalives and queue later commands, as the real firmware does.

Supported. M105, M104, M140, M141, M106, M107, M110, M114, M115, M155, M27, M24, M25, M524, M112
and G28. Heaters drift toward their target so readings change over time.
"""

from __future__ import annotations

import re
import threading
import time
from collections import deque

FIRMWARE = (
    "FIRMWARE_NAME:Marlin 2.1.2.4 (Sep 12 2026) SOURCE_CODE_URL:github.com/MarlinFirmware/Marlin "
    "PROTOCOL_VERSION:1.0 MACHINE_TYPE:Simulated i3 EXTRUDER_COUNT:{extruders} "
    "UUID:cede2a2f-41a2-4748-9b12-c55c62f367ff"
)


def checksum(text: str) -> int:
    value = 0
    for byte in text.encode("ascii"):
        value ^= byte
    return value


class MarlinPrinter:
    """The state of one simulated printer. Thread safe, because ports call it from worker threads."""

    def __init__(self, extruders: int = 1, *, ambient: float = 22.0) -> None:
        self.extruders = extruders
        self.ambient = ambient
        self.temps = {f"T{index}": ambient for index in range(extruders)} | {"B": ambient, "C": ambient}
        self.targets = dict.fromkeys(self.temps, 0.0)
        self.fans: dict[int, int] = {0: 0}
        self.position = {"X": 10.0, "Y": 20.0, "Z": 5.0, "E": 0.0}
        self.autoreport_s = 0.0
        self.autoreport_cap = True
        self.home_time_s = 0.0
        self.busy_every_s = 0.2
        self.sd_printing = False
        self.sd_paused = False
        self.sd_bytes = (0, 0)
        self.halted = False
        self.last_line = 0
        self.corrupt_next_ok = False
        self.corrupt_next_line = False
        self.unsupported: set[str] = set()
        self.drop_ok = False
        self.received: list[str] = []
        self._pending = b""
        self._queue: deque[str] = deque()
        self._busy_until = 0.0
        self._busy_command: str | None = None
        self._last_busy = 0.0
        self._last_report = 0.0
        self._last_step = time.monotonic()
        self._lock = threading.RLock()

    # The firmware prints a banner after the board resets, which happens when the port opens.
    def on_open(self) -> bytes:
        with self._lock:
            self.last_line = 0
            return b"start\necho:Marlin 2.1.2.4\necho: Last Updated: 2026-09-12\n"

    def receive(self, data: bytes) -> bytes:
        with self._lock:
            self._pending += data
            out: list[str] = []
            while b"\n" in self._pending:
                raw, self._pending = self._pending.split(b"\n", 1)
                line = raw.decode("ascii", errors="replace").strip()
                if line:
                    self._queue.append(line)
            self._drain(out, time.monotonic())
            return "".join(item + "\n" for item in out).encode("ascii")

    def poll(self, now: float) -> bytes:
        with self._lock:
            out: list[str] = []
            self._step(now)
            if self._busy_command is not None:
                if now >= self._busy_until:
                    self._finish_busy(out)
                elif now - self._last_busy >= self.busy_every_s:
                    self._last_busy = now
                    out.append("echo:busy: processing")
            self._drain(out, now)
            if self.autoreport_s and now - self._last_report >= self.autoreport_s and not self.halted:
                self._last_report = now
                out.append(self._temperature_report())
            return "".join(item + "\n" for item in out).encode("ascii")

    def _step(self, now: float) -> None:
        dt = min(now - self._last_step, 5.0)
        self._last_step = now
        for key, value in self.temps.items():
            goal = self.targets[key] if self.targets[key] > 0 else self.ambient
            self.temps[key] = value + (goal - value) * min(1.0, 0.8 * dt)

    def _drain(self, out: list[str], now: float) -> None:
        while self._queue and self._busy_command is None:
            self._handle(self._queue.popleft(), out, now)

    def _finish_busy(self, out: list[str]) -> None:
        self._busy_command = None
        self.position.update({"X": 0.0, "Y": 0.0, "Z": 0.0})
        out.append(self._position_report())
        out.append(self._ok())

    def _ok(self) -> str:
        if self.corrupt_next_ok:
            self.corrupt_next_ok = False
            return "o#k"
        return "ok"

    def _temperature_report(self) -> str:
        parts = []
        first = "T0" if self.extruders else None
        if first:
            parts.append(f"T:{self.temps[first]:.2f} /{self.targets[first]:.2f}")
        parts.append(f"B:{self.temps['B']:.2f} /{self.targets['B']:.2f}")
        if self.extruders > 1:
            parts += [f"T{i}:{self.temps[f'T{i}']:.2f} /{self.targets[f'T{i}']:.2f}" for i in range(self.extruders)]
        parts.append(f"C:{self.temps['C']:.2f} /{self.targets['C']:.2f}")
        parts.append("@:0 B@:0")
        return " ".join(parts)

    def _position_report(self) -> str:
        p = self.position
        return f"X:{p['X']:.2f} Y:{p['Y']:.2f} Z:{p['Z']:.2f} E:{p['E']:.2f} Count X:0 Y:0 Z:0"

    def _handle(self, line: str, out: list[str], now: float) -> None:
        self.received.append(line)
        if self.halted:
            return
        command = self._unwrap(line, out)
        if command is None:
            return
        words = command.split()
        code = words[0].upper()
        args = {word[0].upper(): word[1:] for word in words[1:] if word}
        if code == "M112":
            self.halted = True
            out.append("Error:Printer halted. kill() called!")
            return
        reply = self._run(code, args, out, now)
        if reply is None:
            return
        if not self.drop_ok:
            out.append(reply)

    def _unwrap(self, line: str, out: list[str]) -> str | None:
        match = re.fullmatch(r"N(\d+)\s+(.*?)\*(\d+)", line)
        if match is None:
            if line.startswith("N"):
                out.append(f"Error:No Checksum with line number, Last Line: {self.last_line}")
                out += [f"Resend: {self.last_line + 1}", "ok"]
                return None
            return line
        number, body, given = int(match.group(1)), match.group(2), int(match.group(3))
        if self.corrupt_next_line and not body.upper().startswith("M110"):
            self.corrupt_next_line = False
            given = -1
        if checksum(f"N{number} {body}") != given:
            out.append(f"Error:checksum mismatch, Last Line: {self.last_line}")
            out += [f"Resend: {self.last_line + 1}", "ok"]
            return None
        if body.upper().startswith("M110"):
            self.last_line = number
            return body
        if number != self.last_line + 1:
            out.append(f"Error:Line Number is not Last Line Number+1, Last Line: {self.last_line}")
            out += [f"Resend: {self.last_line + 1}", "ok"]
            return None
        self.last_line = number
        return body

    def _run(self, code: str, args: dict[str, str], out: list[str], now: float) -> str | None:
        heater_codes = {"M104": None, "M140": "B", "M141": "C"}
        if code in self.unsupported:
            out.append(f'echo:Unknown command: "{code}"')
            return self._ok()
        if code == "M110":
            if "N" in args:
                self.last_line = int(args["N"])
            return self._ok()
        if code == "M105":
            return f"{self._ok()} {self._temperature_report()}"
        if code in heater_codes:
            key = heater_codes[code] or f"T{int(args.get('T', '0'))}"
            if key not in self.targets:
                out.append(f"echo:Invalid extruder {args.get('T')}")
                return self._ok()
            self.targets[key] = float(args.get("S", "0"))
            return self._ok()
        if code == "M106":
            self.fans[int(args.get("P", "0"))] = max(0, min(255, int(float(args.get("S", "255")))))
            return self._ok()
        if code == "M107":
            self.fans[int(args.get("P", "0"))] = 0
            return self._ok()
        if code == "M114":
            out.append(self._position_report())
            return self._ok()
        if code == "M115":
            out.append(FIRMWARE.format(extruders=self.extruders))
            out.append(f"Cap:AUTOREPORT_TEMP:{1 if self.autoreport_cap else 0}")
            out.append("Cap:EMERGENCY_PARSER:1")
            return self._ok()
        if code == "M155":
            self.autoreport_s = float(args.get("S", "0"))
            return self._ok()
        if code == "M27":
            if self.sd_printing:
                out.append(f"SD printing byte {self.sd_bytes[0]}/{self.sd_bytes[1]}")
            else:
                out.append("Not SD printing")
            return self._ok()
        if code == "M24":
            self.sd_paused = False
            self.sd_printing = self.sd_bytes[1] > 0
            return self._ok()
        if code == "M25":
            self.sd_paused = True
            self.sd_printing = False
            return self._ok()
        if code == "M524":
            self.sd_printing = False
            self.sd_paused = False
            self.sd_bytes = (0, 0)
            return self._ok()
        if code == "G28":
            if self.home_time_s <= 0:
                self.position.update({"X": 0.0, "Y": 0.0, "Z": 0.0})
                out.append(self._position_report())
                return self._ok()
            self._busy_command = "G28"
            self._busy_until = now + self.home_time_s
            self._last_busy = now
            return None
        out.append(f'echo:Unknown command: "{code}"')
        return self._ok()

    def reset(self) -> bytes:
        """Press the reset button. Heaters turn off and the banner is printed again."""
        with self._lock:
            self.targets = dict.fromkeys(self.temps, 0.0)
            self._queue.clear()
            self._busy_command = None
            self.halted = False
            return self.on_open()
