"""The can driver's conformance case, on python-can's virtual bus with a simulated motor drive."""

from __future__ import annotations

import asyncio
import time
import uuid

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.can.driver import CanDriver
from openhal.drivers.can.simulator import MotorController
from openhal.spec import loads
from openhal.spec.models import DeviceFile

CHANNELS = """
read:
  speed: { unit: rpm, map: { id: 0x101, byte: 0, length: 2 } }
  motor_temp: { unit: degC, range: [-20, 120], map: { id: 0x101, byte: 2, offset: -40 } }
  enabled: { type: bool, map: { id: 0x101, byte: 3, bits: 1 } }
  fault: { type: bool, map: { id: 0x101, byte: 3, bit: 1, bits: 1 } }
  voltage: { unit: V, map: { id: 0x101, byte: 4, length: 2, endian: little, scale: 0.01 } }
write:
  setpoint: { unit: rpm, min: 0, max: 3000, map: { id: 0x201, byte: 0, length: 2, data: [0, 0, 0] } }
  enable:
    type: bool
    map: { id: 0x201, byte: 2, bits: 1, data: [0, 0, 0], state: { id: 0x101, byte: 3, bits: 1 } }
  mode:
    type: enum
    values: [coast, eco, sport]
    map:
      id: 0x202
      lookup: { 0: coast, 1: eco, 2: sport }
      state: { id: 0x101, byte: 6, lookup: { 0: coast, 1: eco, 2: sport } }
actions:
  clear_fault: { map: { id: 0x2FF, data: [1] } }
  set_ramp:
    args: { rate: { unit: rpm/s, min: 100, max: 20000 } }
    map: { id: 0x2FF, data: [2, 0, 0], args: { rate: { byte: 1, length: 2 } } }
safe_state: { enable: false, setpoint: 0 }
hazard: medium
confirmed: { by: conformance, at: 2026-10-24 }
"""


def device_file(channel: str, *, extra: str = "", timeout: str = "500 ms") -> DeviceFile:
    connect = f"{{ can: {channel}, interface: virtual, timeout: {timeout}{extra} }}"
    return loads(f"device: Conformance motor drive\nid: conformance-can\nconnect: {connect}\n{CHANNELS}")


def fresh_channel() -> str:
    """A virtual bus name no other test uses, because python-can's virtual buses are process wide."""
    return f"openhal-{uuid.uuid4().hex[:10]}"


class _Case:
    def __init__(self) -> None:
        self.channel = fresh_channel()
        self.node = MotorController(self.channel).start()
        self.file = device_file(self.channel)

    def make(self, file: DeviceFile) -> Driver:
        return CanDriver(file)

    async def break_connection(self, driver: Driver) -> None:
        assert isinstance(driver, CanDriver)
        assert driver.bus is not None
        driver.bus.shutdown()
        deadline = time.monotonic() + 2.0
        while (await driver.health()).connected:
            if time.monotonic() > deadline:
                raise AssertionError("the driver did not detect the bus going down")
            await asyncio.sleep(0.02)

    async def cleanup(self) -> None:
        self.node.stop()


def case() -> ConformanceCase:
    state = _Case()
    return ConformanceCase(
        name="can", file=state.file, make=state.make, break_connection=state.break_connection, cleanup=state.cleanup
    )
