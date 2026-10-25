"""The http driver's conformance case, run against the simulated smart plug."""

from __future__ import annotations

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.http.driver import HttpDriver
from openhal.drivers.http.simulator import SimulatedPlug
from openhal.spec import loads
from openhal.spec.models import DeviceFile

FILE = loads(
    """
device: Conformance plug
id: conformance-plug
connect: { http: "http://plug.local", timeout: 5 s, identify: /api/info, openapi: /openapi.json }
read:
  power: { unit: W, map: { path: /api/status, json: $.power.w } }
  label: { type: string, map: { path: /api/status, json: label } }
  snapshot: { type: image, map: { path: /snapshot.jpg } }
write:
  level:
    unit: dimensionless
    min: 0
    max: 255
    step: 1
    map: { path: /api/dimmer, method: PUT, body: { level: "{value}" }, state: { path: /api/status, json: dimmer } }
  relay:
    type: bool
    map: { path: /api/relay, body: { on: "{value}" }, state: { path: /api/status, json: relay.on } }
  mode:
    type: enum
    values: [auto, manual, eco]
    map: { path: /api/mode, method: GET, query: { set: "{value}" }, state: { path: /api/mode } }
actions:
  reboot:
    args: { delay_s: { unit: s, min: 0, max: 10 } }
    map: { path: /api/reboot, body: { delay_s: "{delay_s}" } }
safe_state: { relay: false, level: 0 }
hazard: low
confirmed: { by: conformance, at: 2026-10-24 }
"""
)


class _Case:
    def __init__(self) -> None:
        self.plug = SimulatedPlug()

    def make(self, file: DeviceFile) -> Driver:
        return HttpDriver(file, transport=self.plug.transport())

    async def break_connection(self, driver: Driver) -> None:
        assert isinstance(driver, HttpDriver)
        await driver.close()

    async def make_slow(self, driver: Driver) -> None:
        self.plug.delay_s = 5.0


def case() -> ConformanceCase:
    state = _Case()
    return ConformanceCase(
        name="http",
        file=FILE,
        make=state.make,
        break_connection=state.break_connection,
        make_slow=state.make_slow,
    )
