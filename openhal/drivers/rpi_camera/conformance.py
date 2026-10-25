"""The rpi-camera driver's conformance case, against the fake Picamera2 class."""

from __future__ import annotations

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.rpi_camera.driver import RpiCameraDriver
from openhal.drivers.rpi_camera.simulator import FakeRig
from openhal.spec import loads
from openhal.spec.models import DeviceFile

FILE = loads(
    """
device: Conformance Pi camera
id: conformance-rpi-camera
connect: { rpi-camera: 0, configuration: video, width: 640, height: 480, warmup: 0 s, timeout: 2 s }
read:
  frame: { type: image }
  light: { unit: lux, map: { metadata: Lux } }
  exposure: { unit: us, map: { metadata: ExposureTime } }
hazard: low
"""
)


class _Case:
    def __init__(self) -> None:
        self.rig = FakeRig()

    def make(self, file: DeviceFile) -> Driver:
        return RpiCameraDriver(file, picamera2_class=self.rig.picamera2_class())

    async def break_connection(self, driver: Driver) -> None:
        sensor = self.rig.sensors[0]
        sensor.fail_capture = True
        await driver.health()
        sensor.fail_capture = False

    async def make_slow(self, driver: Driver) -> None:
        self.rig.sensors[0].delay_s = 3.0


def case() -> ConformanceCase:
    state = _Case()
    return ConformanceCase(
        name="rpi-camera",
        file=FILE,
        make=state.make,
        break_connection=state.break_connection,
        make_slow=state.make_slow,
    )
