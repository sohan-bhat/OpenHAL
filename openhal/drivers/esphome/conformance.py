"""The ESPHome driver's conformance case, through the real APIClient to the native API simulator."""

from __future__ import annotations

import asyncio

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.esphome.driver import EspHomeDriver
from openhal.drivers.esphome.simulator import ThreadedSim
from openhal.spec import loads

TEMPLATE = """
device: Plant waterer
id: esphome-sim
match:
  esphome: {{ name: "plant-*" }}
connect: {{ esphome: 127.0.0.1, port: {port}, timeout: 500 ms }}
read:
  soil_moisture: {{ unit: percent, range: [0, 100] }}
  tank_empty: {{ type: bool }}
write:
  pump: {{ type: bool }}
  grow_light_brightness: {{ unit: percent, min: 0, max: 100, max_change_per_s: 50 }}
  mode: {{ type: enum, values: [manual, schedule, off] }}
actions:
  calibrate: {{}}
safe_state: {{ pump: false, grow_light_brightness: 0 }}
hazard: low
confirmed: {{ by: conformance, at: 2026-10-24 }}
"""


def case() -> ConformanceCase:
    runner = ThreadedSim()
    file = loads(TEMPLATE.format(port=runner.port))

    async def broken(driver: Driver) -> None:
        await runner.call(runner.sim.drop_connections())
        for _ in range(100):
            if not (await driver.health()).connected:
                return
            await asyncio.sleep(0.02)

    async def slow(driver: Driver) -> None:
        assert isinstance(driver, EspHomeDriver)
        runner.sim.latency_s = 5.0
        driver.states.clear()

    async def cleanup() -> None:
        runner.sim.latency_s = 0.0
        await asyncio.to_thread(runner.stop)

    return ConformanceCase(
        name="esphome", file=file, make=EspHomeDriver, break_connection=broken, make_slow=slow, cleanup=cleanup
    )
