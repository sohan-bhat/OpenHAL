"""The modbus driver's conformance case, against pymodbus's server with a simulated fan controller."""

from __future__ import annotations

from typing import Literal

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.modbus.driver import ModbusDriver
from openhal.drivers.modbus.simulator import ModbusSimulator
from openhal.spec import loads
from openhal.spec.models import DeviceFile

CHANNELS = """
read:
  voltage: { unit: V, range: [200, 250], map: { register: 0, kind: input, format: float32 } }
  power: { unit: W, map: { register: 2, kind: input, format: float32 } }
  motor_temperature: { unit: degC, map: { register: 4, kind: input, format: int16, scale: 0.1 } }
  door_closed: { type: bool, map: { register: 0, kind: discrete } }
  run_hours: { unit: h, map: { register: 12, format: uint32, word_order: little } }
write:
  speed: { unit: percent, min: 0, max: 100, step: 0.1, map: { register: 10, scale: 0.1 } }
  enable: { type: bool, map: { register: 0, kind: coil } }
  mode: { type: enum, values: [stop, run, auto], map: { register: 20, values: { stop: 0, run: 1, auto: 2 } } }
safe_state: { enable: false, speed: 0 }
hazard: low
confirmed: { by: conformance, at: 2026-10-24 }
"""


def device_file(simulator: ModbusSimulator, *, timeout: str = "0.5 s") -> DeviceFile:
    """A device file pointing at a running simulator."""
    if simulator.transport == "tcp":
        connect = (
            f"{{ modbus: tcp, host: 127.0.0.1, port: {simulator.port}, unit: {simulator.unit}, timeout: {timeout} }}"
        )
    else:
        connect = f'{{ modbus: rtu, port: "{simulator.address}", unit: {simulator.unit}, timeout: {timeout} }}'
    return loads(f"device: Conformance fan controller\nid: conformance-modbus\nconnect: {connect}\n{CHANNELS}")


class _Case:
    def __init__(self, transport: Literal["tcp", "rtu"]) -> None:
        self.simulator = ModbusSimulator(transport).start()
        self.file = device_file(self.simulator)

    def make(self, file: DeviceFile) -> Driver:
        return ModbusDriver(file)

    async def break_connection(self, driver: Driver) -> None:
        self.simulator.stop()
        self.simulator.start()

    async def make_slow(self, driver: Driver) -> None:
        self.simulator.delay_s = 3.0

    async def cleanup(self) -> None:
        self.simulator.stop()


def case(transport: Literal["tcp", "rtu"] = "tcp") -> ConformanceCase:
    state = _Case(transport)
    return ConformanceCase(
        name=f"modbus-{transport}",
        file=state.file,
        make=state.make,
        break_connection=state.break_connection,
        make_slow=state.make_slow,
        cleanup=state.cleanup,
    )
