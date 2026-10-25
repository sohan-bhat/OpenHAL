"""The Alpaca driver's conformance case, against the simulated Alpaca server."""

from __future__ import annotations

from openhal.conformance import ConformanceCase
from openhal.drivers.alpaca.driver import AlpacaDriver
from openhal.drivers.alpaca.simulator import AlpacaSim
from openhal.drivers.base import Driver
from openhal.spec import loads
from openhal.spec.models import DeviceFile

FILE = loads(
    """
device: Simulated Alpaca mount
id: alpaca-sim
connect: { alpaca: sim.local, device_type: telescope, timeout: 500 ms, action_wait: 1 s }
read:
  right_ascension: { unit: deg }
  declination: { unit: deg }
  slewing: { type: bool }
  at_park: { type: bool }
write:
  focus:
    unit: dimensionless
    min: 0
    max: 40000
    map: { device: focuser, method: move, param: Position, integer: true, readback: position }
  tracking: { type: bool }
actions:
  abort_slew: {}
  park: { require: ["slewing == false"] }
safe_state: { tracking: false }
hazard: medium
confirmed: { by: conformance, at: 2026-10-24 }
"""
)


def case() -> ConformanceCase:
    sim = AlpacaSim()
    sim.time_scale = 20

    def make(file: DeviceFile) -> Driver:
        return AlpacaDriver(file, http_transport=sim.http_transport())

    async def broken(driver: Driver) -> None:
        sim.fail_next = 1

    async def slow(driver: Driver) -> None:
        sim.latency_s = 5.0

    async def cleanup() -> None:
        sim.latency_s = 0.0

    return ConformanceCase(
        name="alpaca", file=FILE, make=make, break_connection=broken, make_slow=slow, cleanup=cleanup
    )
