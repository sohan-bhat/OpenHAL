"""Raspberry Pi camera driver. Camera modules on the CSI connector, through picamera2. Read-only.

Protocol. picamera2 is the official Python library over libcamera on Raspberry Pi OS (Bookworm
and later). It is installed with apt (`python3-picamera2`), not pip, because it needs the system
libcamera bindings, so the driver imports it only when it opens a camera. The calls it uses are
`Picamera2.global_camera_info()`, `Picamera2(camera_num)`, `create_still_configuration` or
`create_video_configuration`, `configure`, `options["quality"]`, `start`, `capture_file(...,
format="jpeg")`, `capture_metadata`, `stop` and `close`.

Behavior worth knowing.

- The camera starts once at connect and keeps running, so captures are fast. Autoexposure and
  white balance need a moment after starting, so connect waits `warmup` before the first capture.
- `still` configurations use the full sensor resolution and are slow to capture. `video`
  configurations are smaller and faster. A `width` and `height` pick the main stream size.
- Number channels read per-frame metadata from libcamera, such as `Lux` and `ExposureTime`, and
  report them in their libcamera units (lux, microseconds, kelvin, degC).
- Only one process can hold a camera. A second open fails with "Device or resource busy".
- There are no write channels and no safe state.
"""

from __future__ import annotations

import asyncio
import io
import threading
import time
from typing import Annotated, Any, ClassVar, Final, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, model_validator

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.spec.models import DeviceFile
from openhal.spec.units import parse_duration

# libcamera metadata names and the units they come in (libcamera control_ids.yaml).
METADATA: Final[dict[str, str]] = {
    "Lux": "lux",
    "ExposureTime": "us",
    "AnalogueGain": "dimensionless",
    "DigitalGain": "dimensionless",
    "ColourTemperature": "K",
    "SensorTemperature": "degC",
    "FrameDuration": "us",
    "FocusFoM": "dimensionless",
    "LensPosition": "dimensionless",
}


def _seconds(value: Any) -> Any:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return parse_duration(value)


Duration = Annotated[float, BeforeValidator(_seconds), Field(ge=0, le=60)]


class RpiCameraParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    camera: int | Literal["auto"] = 0
    width: int | None = Field(default=None, ge=64, le=9152)
    height: int | None = Field(default=None, ge=64, le=6944)
    configuration: Literal["still", "video"] = "still"
    jpeg_quality: int = Field(default=85, ge=1, le=100)
    warmup: Duration = 1.0
    timeout: Duration = 10.0

    @model_validator(mode="after")
    def _size(self) -> RpiCameraParams:
        if (self.width is None) != (self.height is None):
            raise ValueError("Give both width and height, or neither.")
        return self


class MetadataMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: Literal[
        "Lux",
        "ExposureTime",
        "AnalogueGain",
        "DigitalGain",
        "ColourTemperature",
        "SensorTemperature",
        "FrameDuration",
        "FocusFoM",
        "LensPosition",
    ]


def _picamera2_class() -> Any:
    try:
        from picamera2 import Picamera2  # type: ignore[import-not-found]
    except ImportError as exc:
        raise DriverError(
            "picamera2 is not installed. On Raspberry Pi OS run sudo apt install python3-picamera2, and create "
            "the hub's virtual environment with --system-site-packages so it can see it."
        ) from exc
    return Picamera2


class RpiCameraDriver(Driver):
    """Raspberry Pi camera modules through picamera2. Read-only JPEG frames and frame metadata."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="rpi-camera",
        protocols=("libcamera through picamera2",),
        hazard_default="low",
        summary="Raspberry Pi camera modules, read-only capture as JPEG.",
        safe_state_support="none",
    )
    params_model: ClassVar[type[Any] | None] = RpiCameraParams

    def __init__(self, device: DeviceFile, *, picamera2_class: Any = None) -> None:
        super().__init__(device)
        self.settings = RpiCameraParams.model_validate(device.connect.params)
        self._class = picamera2_class
        self._camera: Any = None
        self._lock = threading.Lock()
        self._failed = ""
        self.metadata: dict[str, str] = {}
        if device.write or device.actions:
            raise DriverError("The rpi-camera driver is read-only. Remove the write channels and actions.")
        for name, spec in device.read.items():
            if spec.type == "image":
                continue
            if spec.type != "number":
                raise DriverError(f"{name} is a {spec.type} channel. The rpi-camera driver reads images and numbers.")
            if spec.map is None:
                raise DriverError(f"{name} needs a map naming a metadata field, for example map: {{ metadata: Lux }}.")
            try:
                self.metadata[name] = MetadataMap.model_validate(spec.map).metadata
            except ValidationError as exc:
                problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
                raise DriverError(f"{name} has an invalid rpi-camera map. {problems}") from None

    @property
    def camera_class(self) -> Any:
        if self._class is None:
            self._class = _picamera2_class()
        return self._class

    @property
    def number(self) -> int:
        return 0 if self.settings.camera == "auto" else self.settings.camera

    # ------------------------------------------------------------------ discovery

    @classmethod
    async def discover(cls, *, picamera2_class: Any = None) -> list[Discovered]:
        """List attached camera modules. This asks libcamera what is attached and opens nothing."""
        try:
            camera_class = picamera2_class or _picamera2_class()
        except DriverError:
            return []
        found: list[Discovered] = []
        for entry in await asyncio.to_thread(camera_class.global_camera_info):
            model = str(entry.get("Model", "camera"))
            found.append(
                Discovered(
                    driver="rpi-camera",
                    address=str(entry.get("Num", len(found))),
                    identifiers={"model": model, "id": str(entry.get("Id", ""))},
                    label=f"Raspberry Pi camera {model}",
                )
            )
        return found

    async def identify(self) -> dict[str, str]:
        identity = {"camera": str(self.number)}
        try:
            cameras = await asyncio.to_thread(self.camera_class.global_camera_info)
        except DriverError:
            return identity
        for entry in cameras:
            if entry.get("Num") == self.number:
                identity["model"] = str(entry.get("Model", ""))
                identity["id"] = str(entry.get("Id", ""))
        return identity

    # ------------------------------------------------------------------ lifecycle

    def _open(self) -> Any:
        camera_class = self.camera_class
        if self.settings.camera == "auto" and not camera_class.global_camera_info():
            raise DriverError(
                "No camera module is attached. Check the ribbon cable and run rpicam-hello --list-cameras."
            )
        try:
            camera = camera_class(self.number)
        except IndexError:
            raise DriverError(
                f"There is no camera {self.number}. Run rpicam-hello --list-cameras to see them."
            ) from None
        except RuntimeError as exc:
            raise DriverError(
                f"Could not open camera {self.number} ({exc}). Another program may be using it."
            ) from None
        try:
            main = {"size": (self.settings.width, self.settings.height)} if self.settings.width else None
            create = (
                camera.create_still_configuration
                if self.settings.configuration == "still"
                else camera.create_video_configuration
            )
            camera.configure(create(main=main) if main else create())
            camera.options["quality"] = self.settings.jpeg_quality
            camera.start()
        except (RuntimeError, ValueError) as exc:
            camera.close()
            raise DriverError(f"Camera {self.number} would not start ({exc}).") from None
        return camera

    async def connect(self) -> None:
        await self.close()
        try:
            camera = await asyncio.wait_for(asyncio.to_thread(self._open), self.settings.timeout)
        except TimeoutError:
            raise TimeoutError(f"Camera {self.number} did not start within {self.settings.timeout:g} s.") from None
        self._camera = camera
        self._failed = ""
        if self.settings.warmup:
            await asyncio.sleep(self.settings.warmup)

    async def close(self) -> None:
        camera, self._camera = self._camera, None
        if camera is not None:
            await asyncio.to_thread(self._shutdown, camera)

    @staticmethod
    def _shutdown(camera: Any) -> None:
        try:
            camera.stop()
        finally:
            camera.close()

    async def health(self) -> Health:
        if self._camera is None:
            return Health(connected=False, detail=f"camera {self.number} is not open")
        if self._failed:
            return Health(connected=False, detail=f"camera {self.number} {self._failed}")
        try:
            await self._metadata()
        except (DriverError, TimeoutError) as exc:
            return Health(connected=False, detail=str(exc))
        return Health(connected=True, detail=f"camera {self.number}")

    # ------------------------------------------------------------------ reads

    def _jpeg(self) -> bytes:
        with self._lock:
            if self._camera is None:
                raise DriverError(f"Camera {self.number} is not open.")
            buffer = io.BytesIO()
            try:
                self._camera.capture_file(buffer, format="jpeg")
            except (RuntimeError, ValueError) as exc:
                self._failed = f"failed to capture ({exc})"
                raise DriverError(f"Camera {self.number} failed to capture ({exc}).") from None
        data = buffer.getvalue()
        if not (data.startswith(b"\xff\xd8") and data.rstrip(b"\x00").endswith(b"\xff\xd9")):
            raise DriverError(f"Camera {self.number} produced {len(data)} bytes that are not a JPEG image.")
        return data

    def _read_metadata(self) -> dict[str, Any]:
        with self._lock:
            if self._camera is None:
                raise DriverError(f"Camera {self.number} is not open.")
            try:
                return dict(self._camera.capture_metadata())
            except RuntimeError as exc:
                self._failed = f"stopped delivering frames ({exc})"
                raise DriverError(f"Camera {self.number} stopped delivering frames ({exc}).") from None

    async def _metadata(self) -> dict[str, Any]:
        try:
            return await asyncio.wait_for(asyncio.to_thread(self._read_metadata), self.settings.timeout)
        except TimeoutError:
            self._failed = "stopped answering"
            raise TimeoutError(f"Camera {self.number} gave no frame within {self.settings.timeout:g} s.") from None

    async def read(self, channel: str) -> Reading:
        spec = self.device.read.get(channel)
        if spec is None:
            raise DriverError(f"This rpi-camera device has no channel {channel!r}.")
        if self._camera is None:
            raise DriverError(f"Camera {self.number} is not open.")
        if spec.type == "image":
            try:
                data = await asyncio.wait_for(asyncio.to_thread(self._jpeg), self.settings.timeout)
            except TimeoutError:
                self._failed = "stopped answering"
                raise TimeoutError(f"Camera {self.number} gave no frame within {self.settings.timeout:g} s.") from None
            return Reading(channel, data, at=time.time())
        field = self.metadata[channel]
        metadata = await self._metadata()
        if field not in metadata:
            raise DriverError(
                f"Camera {self.number} doesn't report {field}. Its metadata has {', '.join(sorted(metadata))}."
            )
        raw = metadata[field]
        if isinstance(raw, bool) or not isinstance(raw, int | float):
            raise DriverError(f"Camera {self.number} reported {field} as {raw!r}, not a number.")
        return Reading(channel, float(raw), unit=METADATA[field])

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        raise DriverError("The rpi-camera driver is read-only.")

    # ------------------------------------------------------------------ describe

    async def describe(self) -> dict[str, Any] | None:
        if self._camera is None:
            return None
        metadata = await self._metadata()
        reads: dict[str, Any] = {"frame": {"type": "image"}}
        for field, unit in METADATA.items():
            if isinstance(metadata.get(field), int | float) and not isinstance(metadata.get(field), bool):
                name = "".join(f"_{char.lower()}" if char.isupper() else char for char in field).lstrip("_")
                reads[name] = {"unit": unit, "map": {"metadata": field}}
        properties = getattr(self._camera, "camera_properties", {}) or {}
        model = str(properties.get("Model", "camera"))
        return {
            "device": {"name": f"Raspberry Pi camera {model}", "model": model, "manufacturer": "Raspberry Pi"},
            "read": reads,
            "notes": f"Pixel array {properties.get('PixelArraySize', 'unknown')}. Metadata units are libcamera's.",
        }
