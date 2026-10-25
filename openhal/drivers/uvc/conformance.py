"""The uvc driver's conformance case, against the fake VideoCapture and simulated camera."""

from __future__ import annotations

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.uvc.driver import UvcDriver
from openhal.drivers.uvc.simulator import SimulatedCamera, capture_factory
from openhal.spec import loads
from openhal.spec.models import DeviceFile

FILE = loads(
    """
device: Conformance camera
id: conformance-uvc
match: { usb_class: video }
connect: { uvc: auto, width: 320, height: 240, timeout: 2 s }
read:
  frame: { type: image }
  width: { unit: dimensionless, map: { property: width } }
  fps: { unit: Hz, map: { property: fps } }
hazard: low
"""
)


class _Case:
    def __init__(self) -> None:
        self.camera = SimulatedCamera()

    def make(self, file: DeviceFile) -> Driver:
        return UvcDriver(file, capture_factory=capture_factory(self.camera))

    async def break_connection(self, driver: Driver) -> None:
        # The camera is unplugged and plugged back in. The open capture stays dead until reopened.
        assert isinstance(driver, UvcDriver)
        self.camera.unplug()
        await driver.health()
        self.camera.plug_in()
        await driver.close()

    async def make_slow(self, driver: Driver) -> None:
        self.camera.delay_s = 3.0


def case() -> ConformanceCase:
    state = _Case()
    return ConformanceCase(
        name="uvc", file=FILE, make=state.make, break_connection=state.break_connection, make_slow=state.make_slow
    )
