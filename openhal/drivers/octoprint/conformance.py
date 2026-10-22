"""The OctoPrint driver's conformance case, against the simulated OctoPrint REST API."""

from __future__ import annotations

import os

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.octoprint.driver import OctoPrintDriver
from openhal.drivers.octoprint.simulator import OctoPrintSim
from openhal.spec import loads
from openhal.spec.models import DeviceFile

KEY_ENV = "OPENHAL_CONFORMANCE_OCTOPRINT_KEY"

FILE = loads(
    f"""
device: Simulated OctoPrint printer
id: octoprint-sim
connect: {{ octoprint: octopi.local, port: 80, token_env: {KEY_ENV}, timeout: 500 ms }}
read:
  state: {{ type: enum, values: [standby, printing, paused, cancelling, error, offline] }}
  extruder_temp: {{ unit: degC, range: [0, 300] }}
  bed_temp: {{ unit: degC, range: [0, 120] }}
  progress: {{ unit: percent }}
write:
  extruder_target: {{ unit: degC, min: 0, max: 250, max_change_per_s: 50 }}
  bed_target: {{ unit: degC, min: 0, max: 100 }}
  fan_speed: {{ unit: percent, min: 0, max: 100 }}
actions:
  home:
    args: {{ axes: {{ type: enum, values: [x, y, z, all] }} }}
    require: ["state != printing"]
  pause: {{ require: ["state == printing"] }}
safe_state:
  - {{ extruder_target: 0, bed_target: 0, fan_speed: 0 }}
hazard: medium
confirmed: {{ by: conformance, at: 2026-10-24 }}
"""
)


def case() -> ConformanceCase:
    sim = OctoPrintSim(api_key="conformance-key")
    previous = os.environ.get(KEY_ENV)
    os.environ[KEY_ENV] = "conformance-key"

    def make(file: DeviceFile) -> Driver:
        return OctoPrintDriver(file, http_transport=sim.http_transport())

    async def broken(driver: Driver) -> None:
        sim.fail_next = 1

    async def slow(driver: Driver) -> None:
        sim.latency_s = 5.0

    async def cleanup() -> None:
        sim.latency_s = 0.0
        if previous is None:
            os.environ.pop(KEY_ENV, None)
        else:
            os.environ[KEY_ENV] = previous

    return ConformanceCase(
        name="octoprint", file=FILE, make=make, break_connection=broken, make_slow=slow, cleanup=cleanup
    )
