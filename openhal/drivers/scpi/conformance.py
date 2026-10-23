"""The scpi driver's conformance case, through real PyVISA and pyvisa-py to the TCP bench supply."""

from __future__ import annotations

import asyncio

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.scpi.driver import ScpiDriver
from openhal.drivers.scpi.simulator import ScpiServer
from openhal.spec import loads

TEMPLATE = """
device: {{ name: Bench power supply, model: DP832, manufacturer: Rigol }}
id: scpi-psu
match:
  scpi_idn: "^RIGOL TECHNOLOGIES,DP832"
connect: {{ driver: scpi, resource: "{resource}", timeout: 500 ms }}
read:
  ch1_voltage: {{ unit: V, map: {{ query: "MEAS:VOLT? CH1" }} }}
  ch1_current: {{ unit: mA, map: {{ query: "MEAS:CURR? CH1", unit: A }} }}
write:
  ch1_output: {{ type: bool, map: {{ set: "OUTP CH1,{{on_off}}", get: "OUTP? CH1" }} }}
  ch1_volts: {{ unit: V, min: 0, max: 12, step: 0.01, map: {{ set: "SOUR1:VOLT {{value:.3f}}", get: "SOUR1:VOLT?" }} }}
actions:
  set_ch1:
    args:
      volts: {{ unit: V, min: 0, max: 12, step: 0.01 }}
      amps: {{ unit: A, min: 0, max: 1, step: 0.001 }}
    map: {{ command: "APPL CH1,{{volts}},{{amps}}" }}
safe_state:
  - {{ ch1_output: false }}
hazard: medium
confirmed: {{ by: conformance, at: 2026-10-24 }}
"""


def case() -> ConformanceCase:
    server = ScpiServer()
    file = loads(TEMPLATE.format(resource=server.resource))

    async def broken(driver: Driver) -> None:
        server.drop_connections()
        for _ in range(50):
            if not (await driver.health()).connected:
                return
            await asyncio.sleep(0.02)

    async def slow(driver: Driver) -> None:
        server.latency_s = 3.0

    async def cleanup() -> None:
        server.latency_s = 0.0
        await asyncio.to_thread(server.close)

    return ConformanceCase(
        name="scpi", file=file, make=ScpiDriver, break_connection=broken, make_slow=slow, cleanup=cleanup
    )
