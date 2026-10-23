"""The Marlin driver's conformance case, run against the simulated printer."""

from __future__ import annotations

import asyncio

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.marlin.driver import MarlinDriver
from openhal.drivers.marlin.simulator import MarlinPrinter
from openhal.drivers.serial.simulator import SerialSimulator
from openhal.spec import loads
from openhal.spec.models import DeviceFile

FILE = loads(
    """
device: Simulated Marlin printer
id: marlin-sim
connect: { marlin: "sim://marlin", timeout: 500 ms, settle: 1 s, autoreport: 1 s }
read:
  extruder_temp: { unit: degC, range: [0, 300] }
  bed_temp: { unit: degC, range: [0, 120] }
  position_z: { unit: mm }
write:
  extruder_target: { unit: degC, min: 0, max: 250, max_change_per_s: 50 }
  bed_target: { unit: degC, min: 0, max: 100 }
  fan_speed: { unit: percent, min: 0, max: 100 }
actions:
  home: { args: { axes: { type: enum, values: [x, y, z, all] } } }
safe_state: { extruder_target: 0, bed_target: 0, fan_speed: 0 }
hazard: medium
confirmed: { by: conformance, at: 2026-10-24 }
"""
)


def case() -> ConformanceCase:
    printer = MarlinPrinter()
    sim = SerialSimulator(printer)

    def make(file: DeviceFile) -> Driver:
        return MarlinDriver(file, opener=sim.opener)

    async def broken(driver: Driver) -> None:
        sim.unplug()
        for _ in range(100):
            if not (await driver.health()).connected:
                return
            await asyncio.sleep(0.01)

    async def slow(driver: Driver) -> None:
        assert isinstance(driver, MarlinDriver)
        sim.silent = True
        printer.autoreport_s = 0.0
        driver.temps_at = 0.0

    async def cleanup() -> None:
        sim.silent = False

    return ConformanceCase(
        name="marlin", file=FILE, make=make, break_connection=broken, make_slow=slow, cleanup=cleanup
    )
