"""The Firmata driver's conformance case, run against the simulated StandardFirmata board."""

from __future__ import annotations

import asyncio

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.firmata.driver import FirmataDriver
from openhal.drivers.firmata.simulator import FirmataBoard
from openhal.drivers.serial.simulator import SerialSimulator
from openhal.spec import loads
from openhal.spec.models import DeviceFile

FILE = loads(
    """
device: Simulated Firmata board
id: firmata-sim
connect: { firmata: "sim://uno", timeout: 300 ms, settle: 0 s, sampling: 20 ms, vref: 5 V }
read:
  light: { unit: V, map: { pin: A0 } }
  button: { type: bool, map: { pin: 2, mode: pullup, invert: true } }
write:
  led: { type: bool, map: { pin: 13 } }
  fan: { unit: percent, min: 0, max: 100, max_change_per_s: 50, map: { pin: 9 } }
  arm: { unit: degree, min: 0, max: 180, map: { pin: 6, mode: servo } }
safe_state: { led: false, fan: 0 }
hazard: low
confirmed: { by: conformance, at: 2026-10-24 }
"""
)


def case() -> ConformanceCase:
    board = FirmataBoard()
    sim = SerialSimulator(board)

    def make(file: DeviceFile) -> Driver:
        return FirmataDriver(file, opener=sim.opener)

    async def broken(driver: Driver) -> None:
        sim.unplug()
        for _ in range(100):
            if not (await driver.health()).connected:
                return
            await asyncio.sleep(0.01)

    async def slow(driver: Driver) -> None:
        board.ignore_queries = True
        board.analog_reporting.clear()
        assert isinstance(driver, FirmataDriver)
        driver.analog_values.clear()

    async def cleanup() -> None:
        board.ignore_queries = False

    return ConformanceCase(
        name="firmata", file=FILE, make=make, break_connection=broken, make_slow=slow, cleanup=cleanup
    )
