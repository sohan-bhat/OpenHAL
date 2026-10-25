"""A fake Picamera2 class. picamera2 only installs on Raspberry Pi OS, so tests use this instead.

The fake implements exactly the Picamera2 calls the driver makes, with the signatures from the
Raspberry Pi "Picamera2 Library" manual: `Picamera2.global_camera_info()`,
`Picamera2(camera_num)`, `camera_properties`, `create_still_configuration(main=...)`,
`create_video_configuration(main=...)`, `configure`, `options`, `start`, `capture_file(file,
format="jpeg")`, `capture_metadata`, `stop` and `close`. JPEG data comes from OpenCV when it is
installed and from a fixed tiny JPEG otherwise, so the driver's checks see a real JPEG.

Anything a fake can't prove (that these calls behave the same on a real Pi, timings, sensor
modes, autoexposure settling) is listed in docs/hardware-tests/rpi-camera.md.

Fault injection. `fail_open`, `fail_capture`, `delay_s` and `garbage` on `SimulatedSensor`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, BinaryIO, ClassVar

TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300100b0c0e0c0a100e0d0e1211101318281a181616183123251d"
    "283a333d3c3933383740485c4e404457453738506d51575f626768673e4d71797064785c656763ffc0000b08000800080101"
    "1100ffc4001f0000010501010101010100000000000000000102030405060708090a0bffc400b51000020103030204030505"
    "04040000017d01020300041105122131410613516107227114328191a1082342b1c11552d1f02433627282090a161718191a"
    "25262728292a3435363738393a434445464748494a535455565758595a636465666768696a737475767778797a8384858687"
    "88898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2"
    "e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9faffda0008010100003f00e4ebffd9"
)


def _jpeg(width: int, height: int, quality: int, frame: int) -> bytes:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return TINY_JPEG
    image = np.full((height, width, 3), 40, dtype=np.uint8)
    image[:, (frame * 16) % width, :] = 255
    ok, buffer = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return bytes(buffer) if ok else TINY_JPEG


@dataclass
class SimulatedSensor:
    """One camera module. Values and faults live here and outlive any one Picamera2 object."""

    num: int = 0
    model: str = "imx708"
    pixel_array: tuple[int, int] = (4608, 2592)
    lux: float = 320.0
    exposure_us: int = 16000
    gain: float = 1.5
    colour_temperature: int = 4500
    sensor_temperature: float = 41.0
    fail_open: bool = False
    fail_capture: bool = False
    garbage: bool = False
    delay_s: float = 0.0
    in_use: bool = False
    frames: int = 0
    started: int = 0

    def info(self) -> dict[str, Any]:
        return {
            "Model": self.model,
            "Location": 2,
            "Rotation": 180,
            "Id": f"/base/axi/pcie@120000/rp1/i2c@80000/{self.model}@1a",
            "Num": self.num,
        }


@dataclass
class FakeRig:
    """The cameras plugged into the simulated Pi. `picamera2_class()` returns a Picamera2 stand-in."""

    sensors: list[SimulatedSensor] = field(default_factory=lambda: [SimulatedSensor()])

    def picamera2_class(self) -> type[FakePicamera2]:
        rig = self

        class BoundPicamera2(FakePicamera2):
            RIG: ClassVar[FakeRig] = rig

        return BoundPicamera2


class FakePicamera2:
    RIG: ClassVar[FakeRig]

    @classmethod
    def global_camera_info(cls) -> list[dict[str, Any]]:
        return [sensor.info() for sensor in cls.RIG.sensors]

    def __init__(self, camera_num: int = 0) -> None:
        sensors = [sensor for sensor in self.RIG.sensors if sensor.num == camera_num]
        if not sensors:
            raise IndexError("list index out of range")
        self.sensor = sensors[0]
        if self.sensor.fail_open or self.sensor.in_use:
            raise RuntimeError("Failed to acquire camera: Device or resource busy")
        self.sensor.in_use = True
        self.options: dict[str, Any] = {}
        self.camera_properties = {"Model": self.sensor.model, "PixelArraySize": self.sensor.pixel_array}
        self._config: dict[str, Any] | None = None
        self._running = False
        self._closed = False

    def _configuration(self, kind: str, main: dict[str, Any] | None) -> dict[str, Any]:
        size = tuple((main or {}).get("size") or ((1920, 1080) if kind == "video" else self.sensor.pixel_array))
        return {"use_case": kind, "main": {"size": size, "format": "BGR888"}}

    def create_still_configuration(self, main: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
        return self._configuration("still", main)

    def create_video_configuration(self, main: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
        return self._configuration("video", main)

    def configure(self, config: dict[str, Any]) -> None:
        if self._running:
            raise RuntimeError("Camera must be stopped before configuring")
        self._config = config

    def start(self) -> None:
        if self._config is None:
            raise RuntimeError("Camera has not been configured")
        self._running = True
        self.sensor.started += 1

    def _check(self) -> None:
        if self._closed or not self._running:
            raise RuntimeError("Camera is not running")
        if self.sensor.delay_s:
            time.sleep(self.sensor.delay_s)
        if self.sensor.fail_capture:
            raise RuntimeError("Camera frontend has timed out")

    def capture_file(
        self, file_output: BinaryIO, name: str = "main", format: str | None = None, **_: Any
    ) -> dict[str, Any]:
        self._check()
        assert self._config is not None
        if format != "jpeg":
            raise ValueError(f"unsupported format {format}")
        self.sensor.frames += 1
        width, height = self._config["main"]["size"]
        quality = int(self.options.get("quality", 90))
        data = (
            b"not a jpeg"
            if self.sensor.garbage
            else _jpeg(min(width, 640), min(height, 480), quality, self.sensor.frames)
        )
        file_output.write(data)
        return self.capture_metadata()

    def capture_metadata(self) -> dict[str, Any]:
        self._check()
        sensor = self.sensor
        return {
            "Lux": sensor.lux,
            "ExposureTime": sensor.exposure_us,
            "AnalogueGain": sensor.gain,
            "ColourTemperature": sensor.colour_temperature,
            "SensorTemperature": sensor.sensor_temperature,
            "FrameDuration": 33333,
        }

    def stop(self) -> None:
        self._running = False

    def close(self) -> None:
        self._running = False
        if not self._closed:
            self._closed = True
            self.sensor.in_use = False
