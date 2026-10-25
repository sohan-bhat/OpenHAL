"""A simulated CAN node on python-can's virtual bus, for tests and the conformance case.

`MotorController` behaves like a small motor drive. It opens its own python-can virtual bus on
a channel name, broadcasts a status frame every 20 ms and acts on command frames, so a driver on
the same channel name sees real `can.Message` traffic. All ids are 11-bit.

    0x101  status, broadcast every 20 ms
           bytes 0-1  speed in rpm, unsigned big-endian
           byte 2     temperature, degC + 40
           byte 3     bit 0 enabled, bit 1 fault
           bytes 4-5  bus voltage in 0.01 V, unsigned little-endian
           byte 6     mode, 0 coast, 1 eco, 2 sport
    0x201  command, bytes 0-1 speed setpoint in rpm, byte 2 bit 0 enable
    0x202  mode, byte 0 mode
    0x2FF  service, byte 0 is 0x01 to clear a fault, or 0x02 with bytes 1-2 the ramp in rpm/s

Speed ramps toward the setpoint while enabled and a fault is not set. Faults to inject: `fault`,
`silent` (stops broadcasting), `malformed` (broadcasts a status frame two bytes long) and `stop()`.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

import can

STATUS_ID = 0x101
COMMAND_ID = 0x201
MODE_ID = 0x202
SERVICE_ID = 0x2FF
MODES = ("coast", "eco", "sport")


@dataclass
class MotorController:
    """Start with `start()`, stop with `stop()`. Every frame it receives is kept in `received`."""

    channel: str
    period_s: float = 0.02
    setpoint: int = 0
    enabled: bool = False
    mode: int = 0
    speed: float = 0.0
    temperature: float = 24.0
    voltage: float = 24.0
    ramp: float = 20_000.0
    fault: bool = False
    silent: bool = False
    malformed: bool = False
    received: list[can.Message] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._bus: can.BusABC | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def start(self) -> MotorController:
        if self._thread is not None:
            return self
        self._bus = can.Bus(interface="virtual", channel=self.channel, receive_own_messages=False)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"openhal-can-sim-{self.channel}", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        thread, bus = self._thread, self._bus
        self._thread = None
        self._bus = None
        self._stop.set()
        if thread is not None:
            thread.join(timeout=2)
        if bus is not None:
            bus.shutdown()

    def __enter__(self) -> MotorController:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def frames(self, arbitration_id: int) -> list[bytes]:
        """The data of every received frame with this id, oldest first."""
        with self._lock:
            return [bytes(message.data) for message in self.received if message.arbitration_id == arbitration_id]

    def status(self) -> bytes:
        """The status frame's data as it would be broadcast now."""
        flags = (1 if self.enabled else 0) | (2 if self.fault else 0)
        temperature = max(0, min(255, round(self.temperature + 40)))
        voltage = max(0, min(0xFFFF, round(self.voltage * 100)))
        speed = max(0, min(0xFFFF, round(self.speed)))
        head = speed.to_bytes(2, "big") + bytes([temperature, flags])
        return head + voltage.to_bytes(2, "little") + bytes([self.mode])

    def _run(self) -> None:
        bus = self._bus
        assert bus is not None
        last = time.monotonic()
        next_status = last
        while not self._stop.is_set():
            try:
                message = bus.recv(min(self.period_s, max(0.0, next_status - time.monotonic())))
            except can.CanError:
                return
            if message is not None:
                with self._lock:
                    self.received.append(message)
                self._handle(message)
            now = time.monotonic()
            self._step(now - last)
            last = now
            if now >= next_status:
                next_status = now + self.period_s
                if not self.silent:
                    data = self.status()[:2] if self.malformed else self.status()
                    try:
                        bus.send(can.Message(arbitration_id=STATUS_ID, is_extended_id=False, data=data))
                    except can.CanError:
                        return

    def _handle(self, message: can.Message) -> None:
        data = bytes(message.data)
        if message.arbitration_id == COMMAND_ID and len(data) >= 3:
            self.setpoint = int.from_bytes(data[0:2], "big")
            self.enabled = bool(data[2] & 1)
        elif message.arbitration_id == MODE_ID and data and data[0] < len(MODES):
            self.mode = data[0]
        elif message.arbitration_id == SERVICE_ID and data:
            if data[0] == 0x01:
                self.fault = False
            elif data[0] == 0x02 and len(data) >= 3:
                self.ramp = float(int.from_bytes(data[1:3], "big"))

    def _step(self, elapsed: float) -> None:
        target = float(self.setpoint) if self.enabled and not self.fault else 0.0
        change = self.ramp * elapsed
        if abs(target - self.speed) <= change:
            self.speed = target
        else:
            self.speed += change if target > self.speed else -change
        self.temperature += (24.0 + self.speed / 200.0 - self.temperature) * min(1.0, elapsed / 60.0)
