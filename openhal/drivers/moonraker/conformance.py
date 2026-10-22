"""The Moonraker driver's conformance case, against the simulated Moonraker over HTTP."""

from __future__ import annotations

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.moonraker.driver import MoonrakerDriver
from openhal.drivers.moonraker.simulator import MoonrakerSim
from openhal.spec import loads
from openhal.spec.models import DeviceFile

FILE = loads(
    """
device: { name: Simulated Voron, manufacturer: Voron Design }
id: moonraker-sim
match: { moonraker: { hostname: "voron*" } }
connect: { moonraker: voron.local, port: 7125, timeout: 500 ms }
read:
  state: { type: enum, values: [standby, printing, paused, complete, cancelled, error] }
  extruder_temp: { unit: degC, range: [0, 320] }
  bed_temp: { unit: degC, range: [0, 130] }
write:
  extruder_target: { unit: degC, min: 0, max: 260, max_change_per_s: 50 }
  bed_target: { unit: degC, min: 0, max: 110 }
  fan_speed: { unit: percent, min: 0, max: 100 }
actions:
  home:
    args: { axes: { type: enum, values: [x, y, z, all] } }
    require: ["state != printing"]
  pause: { require: ["state == printing"] }
  cancel: {}
safe_state:
  - { extruder_target: 0, bed_target: 0 }
hazard: medium
confirmed: { by: conformance, at: 2026-10-24 }
"""
)


def case() -> ConformanceCase:
    sim = MoonrakerSim()

    def make(file: DeviceFile) -> Driver:
        return MoonrakerDriver(file, http_transport=sim.http_transport())

    async def broken(driver: Driver) -> None:
        sim.fail_next = 1

    async def slow(driver: Driver) -> None:
        sim.latency_s = 5.0

    async def cleanup() -> None:
        sim.latency_s = 0.0

    return ConformanceCase(
        name="moonraker", file=FILE, make=make, break_connection=broken, make_slow=slow, cleanup=cleanup
    )
