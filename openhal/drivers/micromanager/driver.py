"""Research microscopes through Micro-Manager, with pymmcore-plus. See docs/drivers/micromanager.md.

Protocol (pymmcore-plus 0.18 CMMCorePlus, the Python wrapper of Micro-Manager's MMCore 12). One
device file is one microscope, as one Micro-Manager configuration file (.cfg) describes the
microscope. The
configuration loads the device adapters for the camera, stages, turrets, wheels, shutters and
light sources, from Nikon, Zeiss, Olympus, Leica, ASI, Prior, Hamamatsu and others. Channel maps
are in `channels.py`, frame conversion in `frames.py` and the simulated microscope in
`simulator.py`.

- `config: sim` connects to the built-in simulated microscope. Otherwise `config` names an
  environment variable that holds the configuration file's path, because a device file never
  names a file the hub opens. `adapters_env` can name a variable that holds the Micro-Manager
  folder, and pymmcore-plus finds an installation from `mmcore install` without that variable.
- Every MMCore call runs on a worker thread, one at a time. A move waits for its device with
  `waitForDevice`, under the `timeout` set with `setTimeoutMs`, and the reading after a move is
  the position the device reports, not the one requested.
- An image channel snaps a frame (`snapImage`, `getImage`) and returns a JPEG or PNG. With auto
  shutter on, MMCore opens the shutter for the exposure, so a snap lights the sample.
- An x or y write keeps the other axis in place. `move_xy` moves both at once, and only
  inside the limits of the file's x and y channels.
- `autofocus` runs the configuration's autofocus device (`fullFocus`) when the configuration has
  one. Without an autofocus device the driver sweeps the focus drive, scores each frame's
  sharpness and stops at the sharpest z. The sweep never leaves the limits of the file's focus
  channel or goes faster than the channel's max_change_per_s, so the kernel's z limits hold for
  a sweep the kernel never sees step by step.
- `home` runs the adapters' own homing, which some stages don't implement. Homing moves the
  stage the way the hardware homes, so check the direction before confirming the action.
- An action longer than `action_wait` returns `started` and finishes in the background, and the
  next command waits for that action.

Safe state. Native. Running actions are cancelled, every stage the file uses stops in place,
and the core's shutter closes, which takes the excitation light off the sample. Nothing moves to
make the microscope safe.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import threading
import time
from collections.abc import Callable
from typing import Any, ClassVar, Final, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from openhal.drivers.base import Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.micromanager import channels, frames
from openhal.drivers.micromanager.channels import ChannelMap, to_unit
from openhal.drivers.serial import mapping
from openhal.spec.models import DeviceFile

T = TypeVar("T")
ENV_NAME: Final = r"^[A-Z_][A-Z0-9_]{0,63}$"
CANCEL_WAIT_S: Final = 2.0
FINE_STEPS: Final = 7
FALSE_WORDS: Final = frozenset({"", "0", "off", "false", "closed", "no"})


def _core_class() -> Any:
    from pymmcore_plus import CMMCorePlus

    return CMMCorePlus


def _native_unit(channel_map: ChannelMap) -> str | None:
    """The unit MMCore uses for what a channel reads, or None when the value passes through unchanged."""
    if channel_map.kind == "stage" or channel_map.camera == "pixel_size":
        return "um"
    if channel_map.camera == "exposure":
        return "ms"
    return None


class MicromanagerParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: str = Field(pattern=rf"^(sim(:[a-z0-9-]{{1,32}})?|{ENV_NAME[1:-1]})$")
    adapters_env: str | None = Field(default=None, pattern=ENV_NAME)
    timeout: float = Field(default=5.0, description="Longest wait for a device to finish a move or a snap.")
    action_wait: float = Field(default=8.0, description="How long an action waits before returning started.")
    image_format: Literal["jpeg", "png"] = "jpeg"
    jpeg_quality: int = Field(default=85, ge=1, le=100)
    max_side: int = Field(default=1024, ge=64, le=4096)
    contrast: Literal["full", "auto"] = "auto"
    auto_shutter: bool | None = None

    @field_validator("timeout", "action_wait", mode="before")
    @classmethod
    def _duration(cls, value: Any) -> float:
        return mapping.duration(value)

    @model_validator(mode="after")
    def _ranges(self) -> MicromanagerParams:
        for name, low, high in (("timeout", 0.5, 9), ("action_wait", 0.1, 9)):
            if not low <= getattr(self, name) <= high:
                raise ValueError(f"{name} must be between {low:g} s and {high:g} s.")
        return self

    @property
    def simulated(self) -> bool:
        return self.config == "sim" or self.config.startswith("sim:")


class MicromanagerDriver(Driver):
    """Microscopes and their cameras, stages, turrets, filter wheels, shutters and light sources."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="micromanager",
        protocols=("Micro-Manager MMCore through pymmcore-plus",),
        hazard_default="medium",
        summary="Research microscopes through Micro-Manager. Stage, focus, objective, filters, light and snapshots.",
        safe_state_support="native",
        conformance="full",
    )
    params_model: ClassVar[type[Any] | None] = MicromanagerParams

    def __init__(self, device: DeviceFile, *, core_factory: Callable[[], Any] | None = None) -> None:
        super().__init__(device)
        self.settings = MicromanagerParams.model_validate(device.connect.params)
        self._factory = core_factory
        self.core: Any = None
        self.reads, self.writes, self.actions = channels.build(device)
        self.labels: dict[str, str] = {}
        self.autofocus_device = ""
        self._lock = threading.Lock()
        self._busy = asyncio.Lock()
        self._running: set[asyncio.Task[Any]] = set()
        self._lost: str | None = None

    @property
    def simulated(self) -> bool:
        return self.settings.simulated

    @property
    def running(self) -> int:
        """How many actions are still running in the background."""
        return len(self._running)

    def _make_core(self) -> Any:
        if self._factory is not None:
            return self._factory()
        if self.settings.simulated:
            from openhal.drivers.micromanager import simulator

            return simulator.build_core(self.settings.config.partition(":")[2] or "default")
        path = os.environ.get(self.settings.config)
        if not path:
            raise DriverError(
                f"Set the {self.settings.config} environment variable to the path of a Micro-Manager "
                "configuration file (.cfg), then reconnect."
            )
        mm_path = None
        if self.settings.adapters_env is not None:
            mm_path = os.environ.get(self.settings.adapters_env)
            if not mm_path:
                raise DriverError(
                    f"Set the {self.settings.adapters_env} environment variable to the Micro-Manager folder."
                )
        core = _core_class()(mm_path=mm_path)
        try:
            core.loadSystemConfiguration(path)
        except Exception as exc:
            raise DriverError(
                f"Micro-Manager could not load the configuration in {self.settings.config} ({exc})."
            ) from exc
        return core

    async def _call(self, what: str, function: Callable[..., T], *args: Any, limit: float | None = None) -> T:
        """Run one MMCore call on a worker thread, holding the core for its whole length."""
        if self.core is None:
            raise DriverError(f"{self.device.device_id} is not connected. Connect the microscope first.")

        def run() -> T:
            with self._lock:
                return function(*args)

        try:
            return await asyncio.wait_for(asyncio.to_thread(run), limit or self.settings.timeout)
        except TimeoutError:
            raise TimeoutError(
                f"Micro-Manager didn't finish {what} within {limit or self.settings.timeout:g} s."
            ) from None
        except DriverError:
            raise
        except Exception as exc:
            raise DriverError(f"Micro-Manager returned an error for {what}. {exc}") from exc

    async def connect(self) -> None:
        await self.close()
        try:
            self.core = await asyncio.wait_for(asyncio.to_thread(self._make_core), 30.0)
        except TimeoutError:
            raise TimeoutError("Loading the Micro-Manager configuration took longer than 30 s.") from None
        except DriverError:
            raise
        except Exception as exc:
            raise DriverError(f"Micro-Manager could not start ({type(exc).__name__}, {exc}).") from exc
        self._lost = None
        await self._call("setup", self._setup)

    def _setup(self) -> None:
        core = self.core
        core.setTimeoutMs(round(self.settings.timeout * 1000))
        if self.settings.auto_shutter is not None:
            core.setAutoShutter(self.settings.auto_shutter)
        self.autofocus_device = str(core.getAutoFocusDevice())
        labels: dict[str, str] = {}
        for name, channel in self.reads.items():
            labels[name] = channels.resolve(core, channel, f"read.{name}", self.device.read[name].values)
        for name, channel in self.writes.items():
            labels[name] = channels.resolve(core, channel, f"write.{name}", self.device.write[name].values)
        self.labels = labels

    async def identify(self) -> dict[str, str]:
        identity = {"config": self.settings.config}
        if self.settings.simulated:
            identity["simulated"] = "true"
        if self.core is None:
            return identity

        def gather() -> dict[str, str]:
            core = self.core
            found = {"mmcore": str(core.getVersionInfo()), "api": str(core.getAPIVersionInfo())}
            camera = str(core.getCameraDevice())
            if camera:
                found["camera"] = f"{core.getDeviceLibrary(camera)} {core.getDeviceName(camera)}".strip()
            found["devices"] = str(len([label for label in core.getLoadedDevices() if label != "Core"]))
            return found

        return {**identity, **await self._call("identify", gather)}

    async def read(self, channel: str) -> Reading:
        if self._lost is not None:
            raise DriverError(f"The connection to the microscope failed ({self._lost}). Reconnect the microscope.")
        channel_map = self.reads.get(channel) or self.writes.get(channel)
        if channel_map is None:
            raise DriverError(f"{self.device.device_id} has no channel {channel!r}.")
        unit = self.device.channel_unit(channel)
        if channel_map.kind == "camera" and channel_map.camera == "image":
            return Reading(
                channel, await self._call(f"a snapshot from {self.labels[channel]}", self._snap), at=time.time()
            )
        value = await self._call(f"reading {channel}", self._value, channel, channel_map)
        native = _native_unit(channel_map)
        if isinstance(value, float) and unit and native:
            value = to_unit(value, native, unit)
        return Reading(channel, value, unit)

    def _snap(self) -> bytes:
        core = self.core
        core.snapImage()
        frame = core.getImage()
        try:
            pixels = frames.to_8bit(frame, int(core.getImageBitDepth()), self.settings.contrast)
        except ValueError as exc:
            raise DriverError(f"The camera returned something that is not an image ({exc}).") from None
        return frames.encode(pixels, self.settings.image_format, self.settings.jpeg_quality, self.settings.max_side)

    def _value(self, channel: str, channel_map: ChannelMap) -> Any:
        core, label = self.core, self.labels.get(channel, "")
        kind = channel_map.kind
        if kind == "stage":
            if channel_map.stage == "xy":
                x, y = core.getXYPosition(label)
                return float(x if channel_map.axis == "x" else y)
            return float(core.getPosition(label))
        if kind == "state":
            if self._type(channel) == "number":
                return float(core.getState(label))
            return str(core.getStateLabel(label))
        if kind == "group":
            return str(core.getCurrentConfig(label)) or None
        if kind == "camera":
            if channel_map.camera == "exposure":
                return float(core.getExposure())
            size = float(core.getPixelSizeUm())
            if size <= 0:
                raise DriverError(
                    "No pixel size configuration matches the current objective. Calibrate one in Micro-Manager."
                )
            return size
        if kind == "shutter":
            return bool(core.getShutterOpen(label))
        if kind == "status":
            return bool(core.systemBusy())
        raw = str(core.getProperty(label, channel_map.prop))
        wanted = self._type(channel)
        if wanted == "number":
            try:
                return float(raw)
            except ValueError:
                raise DriverError(f"{label}.{channel_map.prop} reads {raw!r}, which is not a number.") from None
        if wanted == "bool":
            return raw.strip().lower() not in FALSE_WORDS
        return raw

    def _type(self, channel: str) -> str:
        spec = self.device.write.get(channel) or self.device.read.get(channel)
        return spec.type if spec is not None else "number"

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        channel_map = self.writes.get(channel)
        if channel_map is None:
            raise DriverError(f"{self.device.device_id} has no write channel {channel!r}.")
        if self._lost is not None:
            raise DriverError(f"The connection to the microscope failed ({self._lost}). Reconnect the microscope.")
        native = value
        unit, native_unit = self.device.channel_unit(channel), _native_unit(channel_map)
        if isinstance(value, int | float) and not isinstance(value, bool) and unit and native_unit:
            native = to_unit(float(value), unit, native_unit)
        async with self._busy:
            await self._call(f"setting {channel}", self._set, channel, channel_map, native)
        return await self.read(channel)

    def _set(self, channel: str, channel_map: ChannelMap, value: Any) -> None:
        core, label = self.core, self.labels.get(channel, "")
        kind = channel_map.kind
        if kind == "stage":
            if channel_map.stage == "xy":
                x, y = core.getXYPosition(label)
                x, y = (float(value), float(y)) if channel_map.axis == "x" else (float(x), float(value))
                core.setXYPosition(label, x, y)
            else:
                core.setPosition(label, float(value))
            core.waitForDevice(label)
        elif kind == "state":
            if self._type(channel) == "number":
                core.setState(label, round(float(value)))
            else:
                core.setStateLabel(label, str(value))
            core.waitForDevice(label)
        elif kind == "group":
            core.setConfig(label, str(value))
            core.waitForConfig(label, str(value))
        elif kind == "camera":
            core.setExposure(float(value))
        elif kind == "shutter":
            core.setShutterOpen(label, bool(value))
            core.waitForDevice(label)
        else:
            text = (
                ("1" if value else "0")
                if isinstance(value, bool)
                else f"{value:g}"
                if isinstance(value, float)
                else str(value)
            )
            core.setProperty(label, channel_map.prop, text)
            core.waitForDevice(label)

    async def describe(self) -> dict[str, Any] | None:
        if self.core is None:
            return None
        from openhal.drivers.micromanager import describe

        return await self._call("describing the configuration", describe.proposal, self.core)

    async def health(self) -> Health:
        if self.core is None:
            return Health(connected=False, detail="not connected")
        if self._lost is not None:
            return Health(connected=False, detail=self._lost)
        started = time.monotonic()
        try:
            await self._call("a health check", self._probe)
        except (DriverError, TimeoutError) as exc:
            self._lost = str(exc)
            return Health(connected=False, detail=self._lost)
        busy = f", {len(self._running)} actions running" if self._running else ""
        kind = "simulated microscope" if self.simulated else "microscope"
        return Health(
            connected=True, detail=f"{kind} on Micro-Manager{busy}", latency_ms=(time.monotonic() - started) * 1000
        )

    def _probe(self) -> None:
        core = self.core
        stage = str(core.getXYStageDevice() or core.getFocusDevice())
        if stage and int(core.getDeviceType(stage)) == channels.device_type("XYStage"):
            core.getXYPosition(stage)
        elif stage:
            core.getPosition(stage)
        elif core.getCameraDevice():
            core.getExposure()

    async def _safe_state(self) -> None:
        running = list(self._running)
        for task in running:
            task.cancel()
        for task in running:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(task, CANCEL_WAIT_S)
        if self.core is None:
            return

        def stop() -> None:
            self._stop_stages()
            shutter = str(self.core.getShutterDevice())
            if shutter:
                self.core.setShutterOpen(shutter, False)

        await self._call("the safe state", stop)

    def _stage_label(self, stage: str) -> str:
        for name, channel_map in self.writes.items():
            if channel_map.stage == stage:
                return self.labels[name]
        if self.core is None:
            return ""
        return str(self.core.getXYStageDevice() if stage == "xy" else self.core.getFocusDevice())

    def _stop_stages(self) -> None:
        for stage in ("xy", "focus"):
            label = self._stage_label(stage)
            if label:
                with contextlib.suppress(Exception):
                    self.core.stop(label)

    async def close(self) -> None:
        for task in list(self._running):
            task.cancel()
        core, self.core = self.core, None
        if core is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(asyncio.to_thread(core.unloadAllDevices), 5.0)
