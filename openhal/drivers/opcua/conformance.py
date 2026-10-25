"""The OPC UA driver's conformance case, against the shared simulated pump skid."""

from __future__ import annotations

import asyncio

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.opcua.driver import OpcuaDriver
from openhal.drivers.opcua.simulator import shared
from openhal.spec import loads
from openhal.spec.models import DeviceFile

NS = "nsu=urn:openhal:sim:pump;s="
FILE = """
device: Simulated pump skid
id: opcua-sim
connect: {{ opcua: "{endpoint}", timeout: 500 ms }}
read:
  temperature: {{ unit: degC, map: {{ node: "{ns}Pump.Temperature" }} }}
  level: {{ unit: percent, map: {{ node: "{ns}Tank.Level" }} }}
  running: {{ type: bool, map: {{ node: "{ns}Pump.Running" }} }}
write:
  speed: {{ unit: rpm, min: 0, max: 2000, max_change_per_s: 500, map: {{ node: "{ns}Pump.Speed" }} }}
  mode: {{ type: enum, values: [auto, manual], map: {{ node: "{ns}Pump.Mode" }} }}
actions:
  stop: {{ map: {{ object: "{ns}Pump", method: "{ns}Pump.Stop" }} }}
safe_state:
  - {{ action: stop }}
  - {{ speed: 0 }}
hazard: medium
confirmed: {{ by: conformance, at: 2026-10-24 }}
"""


def case() -> ConformanceCase:
    sim = shared()

    def make(file: DeviceFile) -> Driver:
        return OpcuaDriver(file)

    async def broken(driver: Driver) -> None:
        assert isinstance(driver, OpcuaDriver)
        driver.client.disconnect_socket()
        for _ in range(200):
            if not (await driver.health()).connected:
                return
            await asyncio.sleep(0.01)

    async def slow(driver: Driver) -> None:
        sim.hang(1.0)

    async def cleanup() -> None:
        await asyncio.sleep(1.0)

    return ConformanceCase(
        name="opcua",
        file=loads(FILE.format(endpoint=sim.endpoint, ns=NS)),
        make=make,
        break_connection=broken,
        make_slow=slow,
        cleanup=cleanup,
    )
