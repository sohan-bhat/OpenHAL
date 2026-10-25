"""The GRBL driver's conformance case, run against the simulated controller."""

from __future__ import annotations

import asyncio

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.grbl.driver import GrblDriver
from openhal.drivers.grbl.simulator import GrblMachine
from openhal.drivers.serial.simulator import SerialSimulator
from openhal.spec import loads
from openhal.spec.models import DeviceFile

FILE = loads(
    """
device: Simulated GRBL router
id: grbl-sim
connect: { grbl: "sim://grbl", timeout: 500 ms, settle: 1 s, action_wait: 1 s, status_age: 0 s }
read:
  state: { type: enum, values: [idle, run, hold, jog, alarm, door, check, home, sleep] }
  position_x: { unit: mm }
  position_z: { unit: mm }
  feed_rate: { unit: mm/min }
write:
  spindle_speed: { unit: rpm, min: 0, max: 1000, confirm: confirm-each-time }
  flood: { type: bool, confirm: confirm-each-time }
actions:
  jog:
    args: { x: { unit: mm, min: -20, max: 20 }, feed: { unit: mm/min, min: 1, max: 1000 } }
    require: ["state == idle"]
    confirm: confirm-each-time
  hold: {}
safe_state: { spindle_speed: 0, flood: false }
hazard: high
confirmed: { by: conformance, at: 2026-10-24 }
"""
)


def case() -> ConformanceCase:
    machine = GrblMachine()
    machine.time_scale = 50
    sim = SerialSimulator(machine)

    def make(file: DeviceFile) -> Driver:
        return GrblDriver(file, opener=sim.opener)

    async def broken(driver: Driver) -> None:
        sim.unplug()
        for _ in range(100):
            if not (await driver.health()).connected:
                return
            await asyncio.sleep(0.01)

    async def slow(driver: Driver) -> None:
        sim.silent = True

    async def cleanup() -> None:
        sim.silent = False

    return ConformanceCase(name="grbl", file=FILE, make=make, break_connection=broken, make_slow=slow, cleanup=cleanup)
