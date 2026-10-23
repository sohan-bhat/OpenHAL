"""Serial simulators. A pyserial-like port backed by a device model, and a pty bridge.

`SimulatedPort` behaves like `serial.Serial` from the link's point of view (blocking `read` with
a timeout, `write`, `close`), so drivers run their real protocol code against it. `PtyBridge`
serves the same device model on a pseudo terminal, so tests can also open it with real pyserial.

Device models implement `receive(data) -> bytes` and may implement `poll(now) -> bytes` for
output the device sends on its own (Marlin temperature auto-reports, Firmata analog reports)
and `on_open() -> bytes` for a boot banner sent when the port opens.
The serial, marlin and firmata drivers all reuse these classes.
"""

from __future__ import annotations

import contextlib
import os
import re
import select
import threading
import time
from typing import Protocol


class DeviceModel(Protocol):
    def receive(self, data: bytes) -> bytes: ...


class PortGoneError(OSError):
    """Raised by a simulated port after it was unplugged, like pyserial's SerialException."""


def _poll(model: DeviceModel, now: float) -> bytes:
    poll = getattr(model, "poll", None)
    return poll(now) if poll is not None else b""


class SimulatedPort:
    """One open simulated port. Thread safe. Faults are set on the owning `SerialSimulator`."""

    def __init__(self, sim: SerialSimulator) -> None:
        self._sim = sim
        self._rx = bytearray()
        self._cond = threading.Condition()
        self.is_open = True
        self.unplugged = False
        self.timeout = 0.05

    @property
    def in_waiting(self) -> int:
        with self._cond:
            return len(self._rx)

    def deliver(self, data: bytes) -> None:
        if not data:
            return
        with self._cond:
            self._rx.extend(data)
            self._cond.notify_all()

    def read(self, size: int = 1) -> bytes:
        deadline = time.monotonic() + self.timeout
        with self._cond:
            while True:
                if self.unplugged:
                    raise PortGoneError("device disconnected")
                if not self.is_open:
                    raise PortGoneError("port closed")
                self.deliver_unlocked(_poll(self._sim.model, time.monotonic()))
                if self._rx:
                    data = bytes(self._rx[:size])
                    del self._rx[:size]
                    return data
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return b""
                self._cond.wait(min(remaining, 0.02))

    def deliver_unlocked(self, data: bytes) -> None:
        if data:
            self._rx.extend(data)

    def write(self, data: bytes, /) -> int:
        if self.unplugged or not self.is_open:
            raise PortGoneError("device disconnected")
        self._sim.written.append(bytes(data))
        reply = self._sim.model.receive(bytes(data))
        if self._sim.silent:
            return len(data)
        if self._sim.garble:
            reply = re.sub(rb"[0-9]", b"?", reply)
        if self._sim.latency_s > 0:
            timer = threading.Timer(self._sim.latency_s, self.deliver, args=(reply,))
            timer.daemon = True
            timer.start()
        else:
            self.deliver(reply)
        return len(data)

    def unplug(self) -> None:
        with self._cond:
            self.unplugged = True
            self._cond.notify_all()

    def close(self) -> None:
        with self._cond:
            self.is_open = False
            self._cond.notify_all()


class SerialSimulator:
    """Owns a device model and hands out simulated ports, one per connect, like replugging a cable."""

    def __init__(self, model: DeviceModel) -> None:
        self.model = model
        self.port: SimulatedPort | None = None
        self.opened = 0
        self.written: list[bytes] = []
        self.latency_s = 0.0
        self.silent = False
        self.garble = False
        self.refuse_open = False

    def opener(self) -> SimulatedPort:
        if self.refuse_open:
            from openhal.drivers.base import DriverError

            raise DriverError("Could not open the simulated port (refuse_open is set).")
        self.opened += 1
        self.port = SimulatedPort(self)
        on_open = getattr(self.model, "on_open", None)
        if on_open is not None:
            self.port.deliver(on_open())
        return self.port

    def unplug(self) -> None:
        """Break the current port. The next connect opens a fresh one."""
        if self.port is not None:
            self.port.unplug()

    def push(self, data: bytes) -> None:
        """Send unsolicited bytes from the device."""
        if self.port is not None:
            self.port.deliver(data)

    def sent_text(self) -> str:
        return b"".join(self.written).decode("ascii", errors="replace")


class PtyBridge:
    """Serve a device model on a pseudo terminal so real pyserial can open it (POSIX only)."""

    def __init__(self, model: DeviceModel) -> None:
        self.model = model
        self._master, self._slave = os.openpty()
        self.path = os.ttyname(self._slave)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, name="openhal-pty-sim", daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select([self._master], [], [], 0.02)
                out = _poll(self.model, time.monotonic())
                if ready:
                    data = os.read(self._master, 4096)
                    out += self.model.receive(data)
                if out:
                    os.write(self._master, out)
            except OSError:
                return

    def close(self) -> None:
        self._stop.set()
        self._thread.join(1.0)
        for fd in (self._master, self._slave):
            with contextlib.suppress(OSError):
                os.close(fd)


class FanBoard:
    """A small line-protocol board used by the serial driver's tests and conformance case.

    Commands end with a newline and every reply is one line.

        TEMP?        T=<degC>
        FAN?         FAN=<0..255>
        FAN <0..255> OK, or ERR range
        LED?         LED=ON or LED=OFF
        LED ON|OFF   OK
        MODE?        MODE=<eco|normal|boost>
        MODE <name>  OK, or ERR mode
        BEEP <n>     OK
        ID?          FANBOARD,1.2
        anything     ERR unknown

    With `stream` set it also sends `T=<degC>` lines on its own every `stream_every` seconds.
    """

    def __init__(self, temperature: float = 24.5) -> None:
        self.temperature = temperature
        self.fan = 0
        self.led = False
        self.mode = "normal"
        self.beeps = 0
        self.stream = False
        self.stream_every = 0.1
        self._last_stream = 0.0
        self._pending = b""
        self.commands: list[str] = []

    def receive(self, data: bytes) -> bytes:
        self._pending += data
        out = b""
        while b"\n" in self._pending:
            raw, self._pending = self._pending.split(b"\n", 1)
            line = raw.decode("ascii", errors="replace").strip()
            if line:
                self.commands.append(line)
                out += (self.answer(line) + "\n").encode("ascii")
        return out

    def answer(self, line: str) -> str:
        parts = line.split()
        head = parts[0].upper()
        if head == "ID?":
            return "FANBOARD,1.2"
        if head == "TEMP?":
            return f"T={self.temperature - self.fan / 255 * 3:.2f}"
        if head == "FAN?":
            return f"FAN={self.fan}"
        if head == "FAN" and len(parts) == 2:
            try:
                value = int(parts[1])
            except ValueError:
                return "ERR value"
            if not 0 <= value <= 255:
                return "ERR range"
            self.fan = value
            return "OK"
        if head == "LED?":
            return f"LED={'ON' if self.led else 'OFF'}"
        if head == "LED" and len(parts) == 2 and parts[1] in ("ON", "OFF"):
            self.led = parts[1] == "ON"
            return "OK"
        if head == "MODE?":
            return f"MODE={self.mode}"
        if head == "MODE" and len(parts) == 2:
            if parts[1] not in ("eco", "normal", "boost"):
                return "ERR mode"
            self.mode = parts[1]
            return "OK"
        if head == "BEEP" and len(parts) == 2 and parts[1].isdigit():
            self.beeps += int(parts[1])
            return "OK"
        return "ERR unknown"

    def poll(self, now: float) -> bytes:
        if not self.stream or now - self._last_stream < self.stream_every:
            return b""
        self._last_stream = now
        return f"T={self.temperature:.2f}\n".encode("ascii")
