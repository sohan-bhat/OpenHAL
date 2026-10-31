"""UVC driver. USB webcams and other V4L2, AVFoundation or Media Foundation cameras, through OpenCV.

Protocol. USB Video Class 1.1 and 1.5 devices are handled by the operating system's video
stack (V4L2 on Linux, AVFoundation on macOS, Media Foundation or DirectShow on Windows), and
OpenCV's VideoCapture opens them by index or device path. The driver is read-only. It captures
frames and returns them as JPEG bytes, and reads capture properties such as the frame size.

Behavior worth knowing.

- Cameras queue frames, so the first frame read after a pause can be old. The driver grabs and
  drops `flush_frames` frames before each capture.
- A resolution or frame rate in the device file is a request. Cameras fall back to the nearest mode they
  support, and the `width`, `height` and `fps` properties report what the camera really uses.
- Setting the requested resolution when opening is configuration, not an actuation. The driver
  never changes exposure, focus or any other camera control.
- On macOS the first open triggers the camera permission prompt for the app running the hub.
- There are no write channels, so there is no safe state to apply.
"""

from __future__ import annotations

import asyncio
import re
import threading
import time
from pathlib import Path
from typing import Annotated, Any, ClassVar, Final, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.spec.models import DeviceFile
from openhal.spec.units import parse_duration

Property = Literal["width", "height", "fps", "brightness", "contrast", "saturation", "hue", "gain", "exposure", "focus"]
Backend = Literal["any", "v4l2", "avfoundation", "dshow", "msmf", "gstreamer"]
SYSFS: Final = Path("/sys/class/video4linux")


def _seconds(value: Any) -> Any:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return parse_duration(value)


Duration = Annotated[float, BeforeValidator(_seconds), Field(gt=0, le=60)]


class UvcParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: int | str = "auto"
    width: int | None = Field(default=None, ge=16, le=8192)
    height: int | None = Field(default=None, ge=16, le=8192)
    fps: float | None = Field(default=None, gt=0, le=240)
    jpeg_quality: int = Field(default=85, ge=1, le=100)
    backend: Backend = "any"
    flush_frames: int = Field(default=1, ge=0, le=30)
    timeout: Duration = 5.0


class PropertyMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    property: Property


def _cv2() -> Any:
    import cv2

    return cv2


def _prop_id(cv2: Any, name: str) -> int:
    ids = {
        "width": cv2.CAP_PROP_FRAME_WIDTH,
        "height": cv2.CAP_PROP_FRAME_HEIGHT,
        "fps": cv2.CAP_PROP_FPS,
        "brightness": cv2.CAP_PROP_BRIGHTNESS,
        "contrast": cv2.CAP_PROP_CONTRAST,
        "saturation": cv2.CAP_PROP_SATURATION,
        "hue": cv2.CAP_PROP_HUE,
        "gain": cv2.CAP_PROP_GAIN,
        "exposure": cv2.CAP_PROP_EXPOSURE,
        "focus": cv2.CAP_PROP_FOCUS,
    }
    return int(ids[name])


def _api(cv2: Any, backend: str) -> int:
    ids = {
        "any": cv2.CAP_ANY,
        "v4l2": cv2.CAP_V4L2,
        "avfoundation": cv2.CAP_AVFOUNDATION,
        "dshow": cv2.CAP_DSHOW,
        "msmf": cv2.CAP_MSMF,
        "gstreamer": cv2.CAP_GSTREAMER,
    }
    return int(ids[backend])


def _scan_sysfs(sysfs: Path) -> list[Discovered]:
    if not sysfs.is_dir():
        return []
    found = []
    for entry in sorted(sysfs.glob("video*"), key=lambda path: int(re.sub(r"\D", "", path.name) or 0)):
        label_file = entry / "name"
        label = label_file.read_text(encoding="utf-8", errors="replace").strip() if label_file.is_file() else None
        index_file = entry / "index"
        if index_file.is_file() and index_file.read_text().strip() not in ("", "0"):
            continue
        found.append(
            Discovered(driver="uvc", address=f"/dev/{entry.name}", identifiers={"usb_class": "video"}, label=label)
        )
    return found


class UvcDriver(Driver):
    """USB cameras through OpenCV. Read-only JPEG frames and capture properties."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="uvc",
        protocols=("USB Video Class through V4L2, AVFoundation or Media Foundation",),
        hazard_default="low",
        summary="USB webcams, read-only frame capture as JPEG.",
        conformance="core",
        safe_state_support="none",
    )
    params_model: ClassVar[type[Any] | None] = UvcParams

    def __init__(self, device: DeviceFile, *, capture_factory: Any = None) -> None:
        super().__init__(device)
        self.settings = UvcParams.model_validate(device.connect.params)
        self._factory = capture_factory
        self._capture: Any = None
        self._lock = threading.Lock()
        self._failed = ""
        self.properties: dict[str, str] = {}
        if device.write or device.actions:
            raise DriverError("The uvc driver is read-only. Remove the write channels and actions from the file.")
        for name, spec in device.read.items():
            if spec.type == "image":
                continue
            if spec.type != "number":
                raise DriverError(f"{name} is a {spec.type} channel. The uvc driver reads images and numbers.")
            if spec.map is None:
                raise DriverError(
                    f"{name} needs a map naming a capture property, for example map: {{ property: width }}."
                )
            try:
                self.properties[name] = PropertyMap.model_validate(spec.map).property
            except ValidationError as exc:
                problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
                raise DriverError(f"{name} has an invalid uvc map. {problems}") from None

    @property
    def source(self) -> int | str:
        name = self.settings.name
        if name == "auto":
            return 0
        if isinstance(name, str) and name.isdigit():
            return int(name)
        return name

    @classmethod
    async def discover(cls, *, sysfs: Path = SYSFS) -> list[Discovered]:
        """List V4L2 capture devices on Linux from sysfs. Never opens a camera."""
        return await asyncio.to_thread(_scan_sysfs, sysfs)

    async def identify(self) -> dict[str, str]:
        identity = {"source": str(self.source), "backend": self.settings.backend}
        if self._capture is not None:
            identity["backend"] = str(await asyncio.to_thread(self._capture.getBackendName))
        return identity

    def _open(self) -> Any:
        cv2 = _cv2()
        factory = self._factory or cv2.VideoCapture
        capture = factory(self.source, _api(cv2, self.settings.backend))
        if not capture.isOpened():
            capture.release()
            raise DriverError(
                f"Could not open camera {self.source}. Check it is plugged in, not in use by another app, "
                "and that this app has camera permission."
            )
        for prop, value in (
            ("width", self.settings.width),
            ("height", self.settings.height),
            ("fps", self.settings.fps),
        ):
            if value is not None:
                capture.set(_prop_id(cv2, prop), float(value))
        return capture

    async def connect(self) -> None:
        await self.close()
        try:
            capture = await asyncio.wait_for(asyncio.to_thread(self._open), self.settings.timeout)
        except TimeoutError:
            raise TimeoutError(f"Camera {self.source} did not open within {self.settings.timeout:g} s.") from None
        self._capture = capture
        self._failed = ""

    async def close(self) -> None:
        capture, self._capture = self._capture, None
        if capture is not None:
            await asyncio.to_thread(capture.release)

    async def health(self) -> Health:
        if self._capture is None:
            return Health(connected=False, detail=f"camera {self.source} is not open")
        if self._failed:
            return Health(connected=False, detail=f"camera {self.source} {self._failed}")
        try:
            grabbed = await asyncio.wait_for(asyncio.to_thread(self._grab), self.settings.timeout)
        except TimeoutError:
            return Health(connected=False, detail=f"camera {self.source} stopped sending frames")
        if not grabbed:
            return Health(connected=False, detail=f"camera {self.source} returned no frame")
        return Health(connected=True, detail=f"camera {self.source}")

    def _grab(self) -> bool:
        with self._lock:
            return bool(self._capture is not None and self._capture.grab())

    def _capture_jpeg(self) -> bytes:
        cv2 = _cv2()
        with self._lock:
            capture = self._capture
            if capture is None:
                raise DriverError(f"Camera {self.source} is not open.")
            for _ in range(self.settings.flush_frames):
                capture.grab()
            ok, frame = capture.read()
        if not ok or frame is None:
            self._failed = "returned no frame"
            raise DriverError(f"Camera {self.source} returned no frame. It may have been unplugged.")
        shape = getattr(frame, "shape", ())
        if len(shape) not in (2, 3) or 0 in shape:
            raise DriverError(f"Camera {self.source} returned something that is not an image (shape {shape}).")
        encoded, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.settings.jpeg_quality])
        if not encoded:
            raise DriverError(f"Encoding the frame from camera {self.source} as JPEG failed.")
        return bytes(buffer)

    async def read(self, channel: str) -> Reading:
        spec = self.device.read.get(channel)
        if spec is None:
            raise DriverError(f"This uvc device has no channel {channel!r}.")
        if self._capture is None:
            raise DriverError(f"Camera {self.source} is not open.")
        if spec.type == "image":
            try:
                data = await asyncio.wait_for(asyncio.to_thread(self._capture_jpeg), self.settings.timeout)
            except TimeoutError:
                self._failed = "stopped sending frames"
                raise TimeoutError(f"Camera {self.source} gave no frame within {self.settings.timeout:g} s.") from None
            return Reading(channel, data, at=time.time())
        prop = self.properties[channel]
        cv2 = _cv2()
        with self._lock:
            value = float(self._capture.get(_prop_id(cv2, prop)))
        return Reading(channel, value, unit=spec.unit)

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        raise DriverError("The uvc driver is read-only.")

    async def describe(self) -> dict[str, Any] | None:
        if self._capture is None:
            return None
        cv2 = _cv2()
        with self._lock:
            size = [int(self._capture.get(_prop_id(cv2, prop))) for prop in ("width", "height")]
            fps = float(self._capture.get(_prop_id(cv2, "fps")))
        return {
            "match": {"usb_class": "video"},
            "read": {
                "frame": {"type": "image"},
                "frame_width": {"unit": "dimensionless", "map": {"property": "width"}},
                "frame_height": {"unit": "dimensionless", "map": {"property": "height"}},
            },
            "notes": f"The camera captures {size[0]}x{size[1]} at {fps:g} frames per second with these settings.",
        }
