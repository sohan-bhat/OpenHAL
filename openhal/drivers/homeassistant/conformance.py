"""The Home Assistant bridge's conformance case, against the simulated REST API."""

from __future__ import annotations

import os

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.homeassistant.driver import HomeAssistantDriver
from openhal.drivers.homeassistant.simulator import HomeAssistantSim
from openhal.spec import loads
from openhal.spec.models import DeviceFile

TOKEN_ENV = "OPENHAL_CONFORMANCE_HA_TOKEN"  # noqa: S105 (the name of a variable, not a secret)
SIM_TOKEN = "conformance-token"  # noqa: S105 (a fake token for the simulator)

FILE = loads(
    f"""
device: Desk lamp and room sensor
id: ha-sim
connect:
  homeassistant: homeassistant.local
  token_env: {TOKEN_ENV}
  timeout: 500 ms
  entities: [light.desk_lamp, sensor.room_temperature, select.mode]
read:
  room_temp: {{ unit: degC, map: {{ entity: sensor.room_temperature }} }}
write:
  lamp_power: {{ type: bool, map: {{ entity: light.desk_lamp }} }}
  lamp_brightness:
    {{ unit: percent, min: 1, max: 100, step: 1, max_change_per_s: 50, map: {{ entity: light.desk_lamp }} }}
  mode: {{ type: enum, values: [eco, comfort, away], map: {{ entity: select.mode }} }}
safe_state: {{ lamp_power: false }}
hazard: low
confirmed: {{ by: conformance, at: 2026-10-24 }}
"""
)


def case() -> ConformanceCase:
    sim = HomeAssistantSim(token=SIM_TOKEN)
    previous = os.environ.get(TOKEN_ENV)
    os.environ[TOKEN_ENV] = SIM_TOKEN

    def make(file: DeviceFile) -> Driver:
        return HomeAssistantDriver(file, http_transport=sim.http_transport())

    async def broken(driver: Driver) -> None:
        sim.fail_next = 1

    async def slow(driver: Driver) -> None:
        sim.latency_s = 5.0

    async def cleanup() -> None:
        sim.latency_s = 0.0
        if previous is None:
            os.environ.pop(TOKEN_ENV, None)
        else:
            os.environ[TOKEN_ENV] = previous

    return ConformanceCase(
        name="homeassistant", file=FILE, make=make, break_connection=broken, make_slow=slow, cleanup=cleanup
    )
