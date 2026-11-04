"""The seabreeze driver's conformance case, against its own simulated spectrometer."""

from __future__ import annotations

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.seabreeze.driver import SeabreezeDriver
from openhal.drivers.seabreeze.simulator import spectrometer_for
from openhal.spec import loads
from openhal.spec.models import DeviceFile

FILE = loads(
    """
device: Conformance spectrometer
id: conformance-spectrometer
connect: { seabreeze: "sim:conformance", timeout: 2 s, scan_age: 0 s }
read:
  spectrum: { type: image }
  peak_wavelength: { unit: nm }
  peak_intensity: { unit: dimensionless }
  saturated: { type: bool }
  green: { unit: dimensionless, map: { wavelength: 532 nm } }
write:
  integration_time: { unit: ms, min: 1, max: 100 }
actions:
  store_dark: {}
  store_reference: {}
  clear_references: {}
hazard: low
"""
)


def case() -> ConformanceCase:
    spectrometer = spectrometer_for("conformance")

    def make(file: DeviceFile) -> Driver:
        return SeabreezeDriver(file)

    async def broken(driver: Driver) -> None:
        spectrometer.unplug()
        await driver.health()
        spectrometer.plug_in()

    async def slow(driver: Driver) -> None:
        spectrometer.delay_s = 3.0

    async def cleanup() -> None:
        spectrometer.delay_s = 0.0

    return ConformanceCase(
        name="seabreeze", file=FILE, make=make, break_connection=broken, make_slow=slow, cleanup=cleanup
    )
