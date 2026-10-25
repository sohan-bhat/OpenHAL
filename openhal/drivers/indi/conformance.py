"""The INDI driver's conformance case, against the simulated INDI server in its own thread."""

from __future__ import annotations

import asyncio

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.indi.driver import IndiDriver
from openhal.drivers.indi.simulator import IndiServerSim, ServerThread
from openhal.spec import loads
from openhal.spec.models import DeviceFile

FILE = """
device: Simulated INDI mount
id: indi-sim
connect: {{ indi: 127.0.0.1, port: {port}, device: Telescope Simulator, timeout: 500 ms, action_wait: 1 s }}
read:
  right_ascension: {{ unit: deg }}
  declination: {{ unit: deg }}
  slewing: {{ type: bool }}
  parked: {{ type: bool }}
write:
  focus:
    unit: dimensionless
    min: 0
    max: 50000
    map: {{ device: Focuser Simulator, property: ABS_FOCUS_POSITION, element: FOCUS_ABSOLUTE_POSITION }}
  tracking: {{ type: bool }}
actions:
  abort: {{}}
  park: {{ require: ["slewing == false"] }}
safe_state: {{ tracking: false }}
hazard: medium
confirmed: {{ by: conformance, at: 2026-10-24 }}
"""


def case() -> ConformanceCase:
    sim = IndiServerSim()
    sim.time_scale = 20
    sim.focuser.connected = True
    thread = ServerThread(sim)
    port = thread.start()

    def make(file: DeviceFile) -> Driver:
        return IndiDriver(file)

    async def broken(driver: Driver) -> None:
        thread.call(sim.drop_clients)
        for _ in range(200):
            if not (await driver.health()).connected:
                return
            await asyncio.sleep(0.01)

    async def slow(driver: Driver) -> None:
        sim.silent = True

    async def cleanup() -> None:
        sim.silent = False
        thread.stop()

    return ConformanceCase(
        name="indi",
        file=loads(FILE.format(port=port)),
        make=make,
        break_connection=broken,
        make_slow=slow,
        cleanup=cleanup,
    )
