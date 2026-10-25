"""The pi-i2c-spi driver's conformance case, against a fake I2C bus with a simulated TMP102."""

from __future__ import annotations

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.pi_i2c_spi.driver import PiBusDriver
from openhal.drivers.pi_i2c_spi.simulator import FakeI2CBus, Tmp102
from openhal.spec import loads
from openhal.spec.models import DeviceFile

TEMPERATURE = "{ register: 0x00, length: 2, signed: true, bit: 4, bits: 12, scale: 0.0625 }"
T_HIGH = "{ register: 0x03, length: 2, signed: true, bit: 4, bits: 12, scale: 0.0625 }"
SHUTDOWN = "{ register: 0x01, length: 2, bit: 8, bits: 1 }"
RATE = "{ register: 0x01, length: 2, bit: 6, bits: 2, lookup: { 0: 0.25 Hz, 1: 1 Hz, 2: 4 Hz, 3: 8 Hz } }"

CHANNELS = f"""
read:
  temperature: {{ unit: degC, range: [-40, 125], map: {TEMPERATURE} }}
write:
  alert_high:
    unit: degC
    min: -40
    max: 125
    map: {{ register: 0x03, length: 2, signed: true, bit: 4, bits: 12, scale: 0.0625, state: {T_HIGH} }}
  shutdown:
    type: bool
    map: {{ register: 0x01, length: 2, bit: 8, bits: 1, preserve: true, state: {SHUTDOWN} }}
  rate:
    type: enum
    values: [0.25 Hz, 1 Hz, 4 Hz, 8 Hz]
    map:
      register: 0x01
      length: 2
      bit: 6
      bits: 2
      preserve: true
      lookup: {{ 0: 0.25 Hz, 1: 1 Hz, 2: 4 Hz, 3: 8 Hz }}
      state: {RATE}
safe_state: {{ shutdown: true }}
hazard: low
confirmed: {{ by: conformance, at: 2026-10-24 }}
"""


def device_file(*, extra: str = "", timeout: str = "500 ms") -> DeviceFile:
    connect = f"{{ pi-i2c-spi: i2c-1, address: 0x48, timeout: {timeout}{extra} }}"
    return loads(f"device: Conformance TMP102\nid: conformance-tmp102\nconnect: {connect}\n{CHANNELS}")


def case() -> ConformanceCase:
    bus = FakeI2CBus(chips={0x48: Tmp102()})

    def make(file: DeviceFile) -> Driver:
        return PiBusDriver(file, i2c_factory=bus.i2c)

    async def broken(driver: Driver) -> None:
        bus.fail_next = 1

    async def slow(driver: Driver) -> None:
        bus.latency_s = 3.0

    async def cleanup() -> None:
        bus.latency_s = 0.0

    return ConformanceCase(
        name="pi-i2c-spi", file=device_file(), make=make, break_connection=broken, make_slow=slow, cleanup=cleanup
    )
