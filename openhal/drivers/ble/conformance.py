"""The ble driver's conformance case, against the fake BleakClient and simulated room sensor."""

from __future__ import annotations

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.ble.driver import BleDriver
from openhal.drivers.ble.simulator import FakePeripheral, FakeScanner, client_factory
from openhal.spec import loads
from openhal.spec.models import DeviceFile

FILE = loads(
    """
device: Conformance room sensor
id: conformance-ble
match: { ble_name: "^ENV-", ble_services: ["181a"] }
connect: { ble: auto, scan_timeout: 1 s, timeout: 2 s }
read:
  temperature: { unit: degC, stream: true, map: { characteristic: 2a6e, format: sint16, scale: 0.01 } }
  humidity: { unit: percent, stream: true, map: { characteristic: 2a6f, format: uint16, scale: 0.01 } }
  pressure: { unit: hPa, map: { characteristic: 2a6d, format: uint32, scale: 0.001 } }
  battery: { unit: percent, map: { characteristic: 2a19 } }
  maker: { type: string, map: { characteristic: 2a29, format: utf8 } }
write:
  led: { unit: percent, min: 0, max: 100, map: { characteristic: 6e400002-b5a3-f393-e0a9-e50e24dcca9e, scale: 0.5 } }
  mode:
    type: enum
    values: [quiet, normal, fast]
    map:
      characteristic: 6e400003-b5a3-f393-e0a9-e50e24dcca9e
      values: { quiet: 0, normal: 1, fast: 2 }
      response: false
safe_state: { led: 0 }
hazard: low
confirmed: { by: conformance, at: 2026-10-24 }
"""
)


class _Case:
    def __init__(self) -> None:
        self.peripheral = FakePeripheral()

    def make(self, file: DeviceFile) -> Driver:
        return BleDriver(file, client_factory=client_factory(self.peripheral), scanner=FakeScanner(self.peripheral))

    async def break_connection(self, driver: Driver) -> None:
        self.peripheral.drop()

    async def make_slow(self, driver: Driver) -> None:
        self.peripheral.delay_s = 5.0


def case() -> ConformanceCase:
    state = _Case()
    return ConformanceCase(
        name="ble",
        file=FILE,
        make=state.make,
        break_connection=state.break_connection,
        make_slow=state.make_slow,
    )
