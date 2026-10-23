"""The serial driver's conformance case, run against the simulated fan board."""

from __future__ import annotations

import asyncio

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.serial.driver import SerialDriver
from openhal.drivers.serial.simulator import FanBoard, SerialSimulator
from openhal.spec import loads
from openhal.spec.models import DeviceFile

FILE = loads(
    r"""
device: Serial fan board
id: serial-fan
connect: { serial: "sim://fan-board", baud: 115200, timeout: 500 ms, identify: "ID?" }
read:
  temperature: { unit: degC, map: { query: "TEMP?", parse: "^T=(?P<value>-?[0-9.]+)$" } }
write:
  fan_speed:
    unit: percent
    min: 0
    max: 100
    max_change_per_s: 50
    map:
      command: "FAN {value:.0f}"
      scale: 0.39215686
      expect: "^OK$"
      error: "^ERR"
      get: "FAN?"
      parse: "^FAN=(\\d+)$"
  led:
    type: bool
    map: { command: "LED {value}", on: "ON", off: "OFF", expect: "^OK$", get: "LED?", parse: "^LED=(ON|OFF)$" }
actions:
  beep:
    args: { count: { unit: dimensionless, min: 1, max: 5, step: 1 } }
    map: { command: "BEEP {count:.0f}", expect: "^OK$" }
safe_state: { fan_speed: 0, led: false }
hazard: low
confirmed: { by: conformance, at: 2026-10-24 }
"""
)


def case() -> ConformanceCase:
    sim = SerialSimulator(FanBoard())

    def make(file: DeviceFile) -> Driver:
        return SerialDriver(file, opener=sim.opener)

    async def broken(driver: Driver) -> None:
        sim.unplug()
        for _ in range(100):
            if not (await driver.health()).connected:
                return
            await asyncio.sleep(0.01)

    async def slow(driver: Driver) -> None:
        sim.latency_s = 5.0

    async def cleanup() -> None:
        sim.latency_s = 0.0

    return ConformanceCase(
        name="serial", file=FILE, make=make, break_connection=broken, make_slow=slow, cleanup=cleanup
    )
