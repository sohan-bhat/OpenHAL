"""The SiLA 2 driver's conformance case, against the simulated thermoshaker."""

from __future__ import annotations

import asyncio

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.sila2.driver import Sila2Driver
from openhal.drivers.sila2.simulator import ThermoShakerSim
from openhal.spec import loads
from openhal.spec.models import DeviceFile

FILE = """
device: Simulated thermoshaker
id: sila2-sim
connect: {{ sila2: 127.0.0.1, port: {port}, insecure: true, timeout: 500 ms, action_wait: 1 s }}
read:
  temperature: {{ unit: degC, stream: true, map: {{ feature: TemperatureController, property: CurrentTemperature }} }}
  mode:
    type: enum
    values: [idle, shaking]
    map: {{ feature: TemperatureController, property: DeviceState, field: Mode }}
write:
  target:
    unit: degC
    min: 4
    max: 60
    map:
      feature: TemperatureController
      command: SetTargetTemperature
      parameter: TargetTemperature
      readback: TargetTemperature
actions:
  stop_shaking: {{ map: {{ feature: ShakeController, command: StopShaking }} }}
safe_state:
  - {{ action: stop_shaking }}
hazard: medium
confirmed: {{ by: conformance, at: 2026-10-24 }}
"""


def case() -> ConformanceCase:
    sim = ThermoShakerSim()
    port = sim.start()

    def make(file: DeviceFile) -> Driver:
        return Sila2Driver(file)

    async def broken(driver: Driver) -> None:
        assert isinstance(driver, Sila2Driver)
        driver.client._channel.close()  # noqa: SLF001
        for _ in range(100):
            if not (await driver.health()).connected:
                return
            await asyncio.sleep(0.01)

    async def slow(driver: Driver) -> None:
        sim.block.delay_s = 3.0

    async def cleanup() -> None:
        sim.block.delay_s = 0.0
        await asyncio.to_thread(sim.stop)

    return ConformanceCase(
        name="sila2",
        file=loads(FILE.format(port=port)),
        make=make,
        break_connection=broken,
        make_slow=slow,
        cleanup=cleanup,
    )
