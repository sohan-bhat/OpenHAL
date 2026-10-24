"""The rpi-gpio driver's conformance case, against gpiozero's mock pin factory."""

from __future__ import annotations

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.rpi_gpio.driver import RpiGpioDriver
from openhal.drivers.rpi_gpio.simulator import mock_factory
from openhal.spec import loads
from openhal.spec.models import DeviceFile

FILE = loads(
    """
device: Conformance GPIO board
id: conformance-gpio
connect:
  rpi-gpio: { relay: 17, door: 22, fan: 18, valve_servo: 12, stop_button: 27 }
  active_high: false
  pin_factory: mock
read:
  door: { type: bool }
write:
  relay: { type: bool }
  fan: { unit: percent, min: 0, max: 100, map: { frequency: 1000 } }
  valve_servo: { unit: degree, min: -45, max: 45, map: { mode: servo } }
safe_state: { relay: false, fan: 0 }
hazard: low
confirmed: { by: conformance, at: 2026-10-24 }
"""
)


class _Case:
    def __init__(self) -> None:
        self.factory = mock_factory()

    def make(self, file: DeviceFile) -> Driver:
        return RpiGpioDriver(file, pin_factory=self.factory)

    async def break_connection(self, driver: Driver) -> None:
        # GPIO can't drop like a cable, but another part of the system can release the pins.
        assert isinstance(driver, RpiGpioDriver)
        for gpio in driver.devices.values():
            gpio.close()


def case() -> ConformanceCase:
    state = _Case()
    return ConformanceCase(name="rpi-gpio", file=FILE, make=state.make, break_connection=state.break_connection)
