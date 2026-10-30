"""A simulated Modbus fan controller on pymodbus's own server, over TCP or RTU framing.

The server runs in a background thread with its own event loop, so tests and the conformance
case can start it from synchronous code and the driver connects to it over a real socket. RTU uses
pymodbus's `socket://` serial transport, which sends real RTU frames (with CRC) over TCP.

Register map (zero-based protocol addresses).

| Kind | Address | Format | Meaning |
|---|---|---|---|
| input | 0 | float32, big word order | supply voltage, V |
| input | 2 | float32, big word order | power, W |
| input | 4 | int16, scale 0.1 | motor temperature, degC |
| holding | 10 | uint16, scale 0.1 | speed setpoint, percent |
| holding | 12 | uint32, little word order | run hours |
| holding | 20 | uint16 | mode, 0 stop, 1 run, 2 auto |
| coil | 0 | bit | enable |
| discrete | 0 | bit | door closed |

Fault injection. `delay_s` makes every request slow, `exception` fails every request with a
Modbus exception code, and `stop()` and `start()` take the server away and bring it back.
"""

from __future__ import annotations

import asyncio
import socket
import struct
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any, Literal

from pymodbus import FramerType
from pymodbus.constants import ExcCodes
from pymodbus.pdu.device import ModbusDeviceIdentification
from pymodbus.server import ModbusSerialServer, ModbusTcpServer
from pymodbus.simulator import DataType, SimData, SimDevice

_SIZE = 64


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _float_words(value: float) -> list[int]:
    high, low = struct.unpack(">HH", struct.pack(">f", value))
    return [high, low]


@dataclass
class FanModel:
    """The simulated device. Writes land here and reads are served from here."""

    voltage: float = 230.0
    temperature_c: float = 24.5
    speed_raw: int = 0
    hours: int = 70_000
    mode: int = 0
    enable: bool = False
    door_closed: bool = True
    writes: list[tuple[int, int, Any]] = field(default_factory=list)

    @property
    def power(self) -> float:
        return round(2.5 + (0.45 * self.speed_raw if self.enable else 0.0), 3)

    def holding(self) -> dict[int, int]:
        return {10: self.speed_raw, 12: self.hours & 0xFFFF, 13: self.hours >> 16, 20: self.mode}

    def inputs(self) -> dict[int, int]:
        words = _float_words(self.voltage) + _float_words(self.power)
        temperature = struct.unpack(">H", struct.pack(">h", round(self.temperature_c * 10)))[0]
        return {0: words[0], 1: words[1], 2: words[2], 3: words[3], 4: temperature}

    def apply_registers(self, address: int, values: list[int]) -> None:
        for offset, word in enumerate(values):
            register = address + offset
            if register == 10:
                self.speed_raw = word
            elif register == 12:
                self.hours = (self.hours & 0xFFFF0000) | word
            elif register == 13:
                self.hours = (self.hours & 0xFFFF) | (word << 16)
            elif register == 20:
                self.mode = word


class ModbusSimulator:
    """Start with `start()`, stop with `stop()`. `address` and `port` say where it listens."""

    def __init__(self, transport: Literal["tcp", "rtu"] = "tcp", unit: int = 1) -> None:
        self.transport = transport
        self.unit = unit
        self.model = FanModel()
        self.delay_s = 0.0
        self.exception: ExcCodes | None = None
        self.requests = 0
        self.port = _free_port()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._server: ModbusTcpServer | ModbusSerialServer | None = None

    @property
    def address(self) -> str:
        """The `port` parameter for an RTU device file, or the host for TCP."""
        return f"socket://127.0.0.1:{self.port}" if self.transport == "rtu" else "127.0.0.1"

    def _device(self) -> SimDevice:
        return SimDevice(
            id=self.unit,
            simdata=(
                [SimData(0, count=_SIZE, values=False, datatype=DataType.BITS)],
                [SimData(0, count=_SIZE, values=False, datatype=DataType.BITS)],
                [SimData(0, count=_SIZE, values=0, datatype=DataType.REGISTERS)],
                [SimData(0, count=_SIZE, values=0, datatype=DataType.REGISTERS)],
            ),
            action=self._action,
            identity=ModbusDeviceIdentification(  # type: ignore[no-untyped-call]
                info_name={"VendorName": "OpenHAL", "ProductCode": "SIM-FAN", "MajorMinorRevision": "2.1"}
            ),
        )

    async def _action(
        self,
        function_code: int,
        start: int,
        address: int,
        count: int,
        registers: list[int],
        set_values: list[int] | list[bool] | None,
    ) -> ExcCodes | None:
        self.requests += 1
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if self.exception is not None:
            return self.exception
        model = self.model
        if set_values is not None:
            model.writes.append((function_code, address, list(set_values)))
            if function_code in (5, 15):
                if address == 0 and set_values:
                    model.enable = bool(set_values[0])
            elif function_code in (6, 16):
                model.apply_registers(address, [int(value) for value in set_values])
            return None
        if function_code in (3, 4):
            source = model.holding() if function_code == 3 else model.inputs()
            for register, word in source.items():
                if 0 <= register - start < len(registers):
                    registers[register - start] = word
        elif function_code in (1, 2):
            bit = model.enable if function_code == 1 else model.door_closed
            if registers:
                registers[0] = (registers[0] & ~1) | int(bit)
        return None

    async def _serve(self, ready: Future[None]) -> None:
        if self.transport == "tcp":
            self._server = ModbusTcpServer(self._device(), address=("127.0.0.1", self.port))
        else:
            self._server = ModbusSerialServer(self._device(), framer=FramerType.RTU, port=self.address)
        task = asyncio.ensure_future(self._server.serve_forever())
        for _ in range(200):
            if self._listening():
                ready.set_result(None)
                break
            await asyncio.sleep(0.01)
        else:
            ready.set_exception(RuntimeError("The Modbus simulator did not start listening."))
        await task

    def _listening(self) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=0.2):
                return True
        except OSError:
            return False

    def start(self) -> ModbusSimulator:
        if self._thread is not None:
            return self
        ready: Future[None] = Future()
        loop = asyncio.new_event_loop()
        self._loop = loop

        def run() -> None:
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._serve(ready))
            except Exception as exc:  # noqa: BLE001 (reported to the starting thread)
                if not ready.done():
                    ready.set_exception(exc)
            finally:
                pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
                for task in pending:
                    task.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.close()

        self._thread = threading.Thread(target=run, name="openhal-modbus-sim", daemon=True)
        self._thread.start()
        ready.result(timeout=5)
        return self

    def stop(self) -> None:
        loop, thread, server = self._loop, self._thread, self._server
        self._loop = self._thread = self._server = None
        if loop is None or thread is None:
            return
        if server is not None:
            asyncio.run_coroutine_threadsafe(server.shutdown(), loop).result(timeout=5)  # type: ignore[no-untyped-call]
        thread.join(timeout=5)
        deadline = time.monotonic() + 2
        while self._listening() and time.monotonic() < deadline:
            time.sleep(0.02)

    def __enter__(self) -> ModbusSimulator:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()
