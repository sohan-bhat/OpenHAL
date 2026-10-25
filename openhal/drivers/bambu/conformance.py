"""The bambu driver's conformance case, against a simulated printer on a local MQTT broker over TLS."""

from __future__ import annotations

import asyncio
import os
import time

from openhal.conformance import ConformanceCase
from openhal.drivers.bambu.driver import BambuDriver
from openhal.drivers.bambu.simulator import ACCESS_CODE, PrinterBroker, SimulatedPrinter
from openhal.drivers.base import Driver
from openhal.spec import loads
from openhal.spec.models import DeviceFile

SERIAL = "00M09A350100001"
TOKEN_ENV = "OPENHAL_CONFORMANCE_BAMBU_CODE"  # noqa: S105

CHANNELS = """
read:
  state: { type: enum, values: [idle, prepare, slicing, running, pause, finish, failed] }
  nozzle_temp: { unit: degC, range: [0, 320] }
  nozzle_target: { unit: degC }
  bed_temp: { unit: degC, range: [0, 120] }
  chamber_temp: { unit: degC }
  progress: { unit: percent }
  remaining: { unit: min }
  layer: { unit: dimensionless }
  job: { type: string }
write:
  speed_level: { type: enum, values: [silent, standard, sport] }
  chamber_light: { type: bool }
actions:
  pause: { require: ["state == running"] }
  resume: { require: ["state == pause"] }
  stop: {}
hazard: medium
confirmed: { by: conformance, at: 2026-10-24 }
"""


def device_file(broker: PrinterBroker, *, extra: str = "", serial: str = SERIAL) -> DeviceFile:
    connect = (
        f"{{ bambu: 127.0.0.1, port: {broker.port}, serial: {serial}, token_env: {TOKEN_ENV}, "
        f"cert_sha256: {broker.fingerprint}, timeout: 2 s, reply_wait: 1 s{extra} }}"
    )
    return loads(f"device: Conformance printer\nid: conformance-bambu\nconnect: {connect}\n{CHANNELS}")


def environ(name: str) -> str | None:
    """The environment the driver sees, with the simulator's access code."""
    return ACCESS_CODE if name == TOKEN_ENV else os.environ.get(name)


class _Case:
    def __init__(self) -> None:
        self.broker = PrinterBroker(SERIAL).start()
        self.printer = SimulatedPrinter(self.broker, SERIAL).attach()
        self.file = device_file(self.broker)

    def make(self, file: DeviceFile) -> Driver:
        return BambuDriver(file, environ=environ)

    async def break_connection(self, driver: Driver) -> None:
        assert isinstance(driver, BambuDriver)
        self.broker.kick_all()
        deadline = time.monotonic() + 3.0
        while driver.connected:
            if time.monotonic() > deadline:
                raise AssertionError("the driver did not notice the printer going away")
            await asyncio.sleep(0.02)

    async def cleanup(self) -> None:
        self.broker.stop()


def case() -> ConformanceCase:
    state = _Case()
    return ConformanceCase(
        name="bambu", file=state.file, make=state.make, break_connection=state.break_connection, cleanup=state.cleanup
    )
