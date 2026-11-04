"""A simulated inverted fluorescence microscope for the micromanager driver. Offline and fast.

The core is pymmcore-plus's UniMMCore, the real Micro-Manager core, with Python devices loaded in
place of hardware device adapters, so the driver calls the same CMMCorePlus methods the driver calls on a
real microscope and no native adapter is needed. The devices are a camera, an XY stage, a focus
drive, an objective turret, a filter wheel, a shutter and an LED light source.

The slide. `slide.jpg` is a real micrograph, SK8/18-2 human derived cells with vimentin in green
(Alexa 488) and nuclei in blue (DAPI), imaged by ZEISS Microscopy on an Axio Observer 7 and shared
on Wikimedia Commons under CC BY 2.0. The file is the original cropped to drop its scale bar, and
docs/DEPENDENCIES.md records the source. The micrograph keeps its true scale of 0.0725 um per pixel,
so the cells cover about 200 by 143 um at the stage's origin, with dark glass around the cells.

The optics. The camera has 1024 by 768 pixels of 6.5 um. The turret holds a 20x/0.8, a 40x/0.95
and a 63x/1.4 oil objective, so the field of view shrinks from 333 to 106 um as the
magnification grows, and the stage pans that field across the slide. The filter wheel picks
what reaches the camera, DAPI for the nuclei, GFP for the vimentin, both, or TRITC, which shows
nothing because the slide has no red stain. Exposure and LED intensity scale the brightness,
and every frame carries shot and read noise.

Focus. The slide is in focus at z = 1500 um, tilted a few um per mm, and each objective is
parfocal within a couple of um. Defocus blurs the frame by the cone of light the objective's
numerical aperture gives, outside half the depth of field.

The z limit. On this inverted microscope a larger z moves the objective up toward the slide, and
the objective's front lens touches the slide one working distance above focus, 550, 250 or
190 um for the three objectives. A move past that point stops at the slide and raises an error,
as a stalled focus drive would, and the stage holds still until the objective moves back down.

Fault hooks. `unplug()` makes every device call fail as a lost connection does, `delay_s`
slows every call, and `fail_next` makes the next stage move fail.
"""

from __future__ import annotations

import functools
import math
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import numpy as np
from PIL import Image, ImageFilter
from pymmcore_plus.core import FocusDirection
from pymmcore_plus.experimental.unicore import (
    GenericDevice,
    ShutterDevice,
    SimpleCameraDevice,
    StageDevice,
    StateDevice,
    UniMMCore,
    XYStageDevice,
)

HERE: Final = Path(__file__).parent
SLIDE: Final = HERE / "slide.jpg"
SLIDE_UM_PER_PX: Final = 0.0725
SENSOR: Final = (768, 1024)
CAMERA_PIXEL_UM: Final = 6.5
FOCUS_Z_UM: Final = 1500.0
TILT: Final = (0.003, -0.002)


@dataclass(frozen=True)
class Objective:
    label: str
    magnification: float
    na: float
    medium: float
    working_distance_um: float
    parfocal_um: float

    @property
    def depth_of_field_um(self) -> float:
        """Wide field depth of field at 520 nm, from the wave and the camera pixel terms."""
        return 0.52 * self.medium / self.na**2 + self.medium * CAMERA_PIXEL_UM / (self.magnification * self.na)

    @property
    def cone(self) -> float:
        """How fast the blur grows with defocus, the tangent of the half angle the aperture accepts."""
        return math.tan(math.asin(min(self.na / self.medium, 0.99)))


OBJECTIVES: Final = (
    Objective("20x Plan-Apochromat 0.8", 20, 0.8, 1.0, 550.0, 0.0),
    Objective("40x Plan-Apochromat 0.95", 40, 0.95, 1.0, 250.0, 1.6),
    Objective("63x Plan-Apochromat 1.4 Oil", 63, 1.4, 1.518, 190.0, -1.2),
)
FILTERS: Final = ("DAPI", "GFP", "DAPI-GFP", "TRITC")
CHANNEL_PRESETS: Final = {"DAPI": "DAPI", "GFP": "GFP", "Dual": "DAPI-GFP", "TRITC": "TRITC"}


class SimulatedDeviceError(RuntimeError):
    """A device in the simulated microscope reported an error."""


@functools.cache
def _slide() -> np.ndarray:
    """The micrograph as float RGB, faded to dark glass over its outer 320 pixels."""
    with Image.open(SLIDE) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    height, width = rgb.shape[:2]
    rows = np.minimum(np.arange(height), np.arange(height)[::-1]) / 320.0
    cols = np.minimum(np.arange(width), np.arange(width)[::-1]) / 320.0
    edge = np.clip(np.minimum.outer(rows, cols), 0.0, 1.0)
    fade = edge * edge * (3 - 2 * edge)
    faded: np.ndarray = rgb * fade[..., None]
    return faded


@functools.cache
def _stained(filter_label: str) -> Image.Image:
    """The slide through one filter, an 8-bit RGB image at the slide's own scale."""
    rgb = _slide()
    blue, green = rgb[..., 2], rgb[..., 1]
    dapi = np.clip(blue - 0.45 * green, 0, 255) * 1.25
    nuclei = np.stack([np.zeros_like(blue), 0.55 * dapi, dapi], axis=-1)
    vimentin = np.stack([np.zeros_like(green), np.clip(green - 0.55 * blue, 0, 255), np.zeros_like(green)], axis=-1)
    layers = {
        "DAPI": nuclei,
        "GFP": vimentin,
        "DAPI-GFP": rgb,
        "TRITC": np.zeros_like(rgb),
    }
    return Image.fromarray(np.clip(layers[filter_label], 0, 255).astype(np.uint8), "RGB")


@dataclass
class Microscope:
    """The state of one simulated microscope, shared by every core that connects to the microscope."""

    x_um: float = 0.0
    y_um: float = 0.0
    z_um: float = 1000.0
    objective: int = 0
    filter: int = 2
    shutter_open: bool = False
    led_percent: float = 50.0
    exposure_ms: float = 50.0
    xy_speed_um_s: float = 20000.0
    z_speed_um_s: float = 5000.0
    xy_travel_um: tuple[float, float] = (-25000.0, 25000.0)
    z_travel_um: tuple[float, float] = (0.0, 5000.0)
    touching: bool = False
    crashes: int = 0
    lost: bool = False
    delay_s: float = 0.0
    fail_next: int = 0
    seed: int | None = None
    snaps: int = 0
    lighting: bool = False
    busy_until: dict[str, float] = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def __post_init__(self) -> None:
        self.rng = np.random.default_rng(self.seed)

    def unplug(self) -> None:
        self.lost = True

    def plug_in(self) -> None:
        self.lost = False

    def call(self, what: str) -> None:
        """Run before every device call, for the fault hooks."""
        if self.delay_s:
            time.sleep(self.delay_s)
        if self.lost:
            raise SimulatedDeviceError(f"No reply from the microscope's {what}. The connection is lost.")

    def fail(self, what: str) -> None:
        if self.fail_next > 0:
            self.fail_next -= 1
            raise SimulatedDeviceError(f"The {what} reported a hardware error (simulated).")

    @property
    def lens(self) -> Objective:
        return OBJECTIVES[self.objective]

    def focal_plane(self, x_um: float | None = None, y_um: float | None = None) -> float:
        """The z at which the slide is sharp under the current objective, at a stage position."""
        x = self.x_um if x_um is None else x_um
        y = self.y_um if y_um is None else y_um
        return FOCUS_Z_UM + TILT[0] * x + TILT[1] * y + self.lens.parfocal_um

    def contact(self, x_um: float | None = None, y_um: float | None = None) -> float:
        """The z at which the objective's front lens touches the slide."""
        return self.focal_plane(x_um, y_um) + self.lens.working_distance_um

    def busy(self, stage: str) -> bool:
        return time.monotonic() < self.busy_until.get(stage, 0.0)

    def move_xy(self, x_um: float, y_um: float) -> None:
        with self.lock:
            self.call("XY stage")
            self.fail("XY stage")
            low, high = self.xy_travel_um
            if not (low <= x_um <= high and low <= y_um <= high):
                raise SimulatedDeviceError(
                    f"The XY stage can't reach ({x_um:g}, {y_um:g}) um. Its travel is {low:g} to {high:g} um."
                )
            if self.touching or self.z_um >= self.contact(x_um, y_um):
                raise SimulatedDeviceError(
                    "The objective is touching the slide, so the stage didn't move. Lower the focus first."
                )
            distance = math.hypot(x_um - self.x_um, y_um - self.y_um)
            self.x_um, self.y_um = float(x_um), float(y_um)
            self.busy_until["xy"] = time.monotonic() + distance / self.xy_speed_um_s

    def move_z(self, z_um: float) -> None:
        with self.lock:
            self.call("focus drive")
            self.fail("focus drive")
            low, high = self.z_travel_um
            if not low <= z_um <= high:
                raise SimulatedDeviceError(
                    f"The focus drive can't reach z = {z_um:g} um. Its travel is {low:g} to {high:g} um."
                )
            limit = self.contact()
            start = self.z_um
            target = min(float(z_um), limit)
            self.z_um = target
            self.busy_until["z"] = time.monotonic() + abs(target - start) / self.z_speed_um_s
            self.touching = z_um >= limit
            if self.touching:
                self.crashes += 1
                raise SimulatedDeviceError(
                    f"The objective touched the slide at z = {limit:.1f} um and the focus drive stalled. "
                    "Check the slide and the objective, then move the focus down."
                )

    def frame(self, shape: tuple[int, int, int]) -> np.ndarray:
        """Render one camera frame, an 8-bit RGB array of `shape`."""
        with self.lock:
            self.call("camera")
            self.snaps += 1
            lit = self.shutter_open or self.lighting
            x, y, lens = self.x_um, self.y_um, self.lens
            defocus = self.z_um - self.focal_plane()
            gain = (self.exposure_ms / 50.0) * (self.led_percent / 50.0) if lit else 0.0
            stain = FILTERS[self.filter]
        height, width = shape[0], shape[1]
        signal = np.zeros((height, width, 3), dtype=np.float32)
        if gain > 0:
            signal = np.asarray(_field(stain, x, y, lens, defocus, (width, height)), dtype=np.float32) * gain
        noise = self.rng.standard_normal(signal.shape, dtype=np.float32)
        signal += noise * (1.2 + 0.35 * np.sqrt(signal))
        result: np.ndarray = np.clip(signal + 2.0, 0, 255).astype(np.uint8)
        return result


def _field(
    stain: str, x_um: float, y_um: float, lens: Objective, defocus_um: float, size: tuple[int, int]
) -> Image.Image:
    """The part of the slide in the field of view, scaled to the camera and blurred by defocus."""
    width, height = size
    slide = _stained(stain)
    um_per_px = CAMERA_PIXEL_UM / lens.magnification
    scale = um_per_px / SLIDE_UM_PER_PX
    center_x = slide.width / 2 + x_um / SLIDE_UM_PER_PX
    center_y = slide.height / 2 + y_um / SLIDE_UM_PER_PX
    left, top = center_x - width * scale / 2, center_y - height * scale / 2
    box = (
        max(0.0, left),
        max(0.0, top),
        min(float(slide.width), left + width * scale),
        min(float(slide.height), top + height * scale),
    )
    canvas = Image.new("RGB", (width, height))
    if box[2] - box[0] >= 1 and box[3] - box[1] >= 1:
        target = (
            round((box[0] - left) / scale),
            round((box[1] - top) / scale),
            round((box[2] - left) / scale),
            round((box[3] - top) / scale),
        )
        out = (max(1, target[2] - target[0]), max(1, target[3] - target[1]))
        canvas.paste(slide.resize(out, Image.Resampling.BILINEAR, box=box, reducing_gap=2.0), target[:2])
    blur_um = 0.5 * max(0.0, abs(defocus_um) - lens.depth_of_field_um / 2) * lens.cone
    radius = min(blur_um / um_per_px, 80.0)
    if radius > 0.3:
        canvas = canvas.filter(ImageFilter.GaussianBlur(radius))
    return canvas


class SimCamera(SimpleCameraDevice):
    """A 1024 x 768 camera with 6.5 um pixels, imaging the simulated slide."""

    def __init__(self, scope: Microscope) -> None:
        super().__init__()
        self.scope = scope
        self.set_property_limits("Exposure", (0.1, 10000.0))

    def get_exposure(self) -> float:
        self.scope.call("camera")
        return self.scope.exposure_ms

    def set_exposure(self, exposure: float) -> None:
        self.scope.call("camera")
        self.scope.exposure_ms = float(exposure)

    def sensor_shape(self) -> tuple[int, int, int]:
        return (*SENSOR, 3)

    def dtype(self) -> Any:
        return np.uint8

    def snap(self, buffer: np.ndarray) -> Mapping[str, Any]:
        buffer[:] = self.scope.frame(buffer.shape)
        return {}


class SimXYStage(XYStageDevice):
    """A motorized XY stage with 50 mm of travel. Home is the slide's center."""

    def __init__(self, scope: Microscope) -> None:
        super().__init__()
        self.scope = scope

    def set_position_um(self, x: float, y: float) -> None:
        self.scope.move_xy(x, y)

    def get_position_um(self) -> tuple[float, float]:
        self.scope.call("XY stage")
        return (self.scope.x_um, self.scope.y_um)

    def busy(self) -> bool:
        return self.scope.busy("xy")

    def home(self) -> None:
        self.scope.move_xy(0.0, 0.0)

    def stop(self) -> None:
        self.scope.call("XY stage")
        self.scope.busy_until.pop("xy", None)

    def set_origin_x(self) -> None:
        raise SimulatedDeviceError("The simulated XY stage keeps its origin at the slide's center.")

    def set_origin_y(self) -> None:
        raise SimulatedDeviceError("The simulated XY stage keeps its origin at the slide's center.")


class SimFocus(StageDevice):
    """A motorized focus drive under the objective. A larger z moves toward the slide."""

    def __init__(self, scope: Microscope) -> None:
        super().__init__()
        self.scope = scope

    def set_position_um(self, val: float) -> None:
        self.scope.move_z(val)

    def get_position_um(self) -> float:
        self.scope.call("focus drive")
        return self.scope.z_um

    def get_focus_direction(self) -> FocusDirection:
        return FocusDirection.TowardSample

    def busy(self) -> bool:
        return self.scope.busy("z")

    def home(self) -> None:
        self.scope.move_z(self.scope.z_travel_um[0])

    def stop(self) -> None:
        self.scope.call("focus drive")
        self.scope.busy_until.pop("z", None)

    def set_origin(self) -> None:
        raise SimulatedDeviceError("The simulated focus drive keeps its origin at the bottom of its travel.")


class SimTurret(StateDevice):
    """A motorized objective turret."""

    def __init__(self, scope: Microscope) -> None:
        super().__init__({index: lens.label for index, lens in enumerate(OBJECTIVES)})
        self.scope = scope

    def get_state(self) -> int:
        self.scope.call("objective turret")
        return self.scope.objective

    def set_state(self, position: int) -> None:
        self.scope.call("objective turret")
        with self.scope.lock:
            self.scope.objective = int(position)
            if self.scope.z_um >= self.scope.contact():
                self.scope.touching = True
                self.scope.crashes += 1


class SimFilterWheel(StateDevice):
    """A filter wheel with DAPI, GFP, dual band and TRITC cubes."""

    def __init__(self, scope: Microscope) -> None:
        super().__init__(dict(enumerate(FILTERS)))
        self.scope = scope

    def get_state(self) -> int:
        self.scope.call("filter wheel")
        return self.scope.filter

    def set_state(self, position: int) -> None:
        self.scope.call("filter wheel")
        self.scope.filter = int(position)


class SimShutter(ShutterDevice):
    """The excitation shutter in front of the LED."""

    def __init__(self, scope: Microscope) -> None:
        super().__init__()
        self.scope = scope

    def get_open(self) -> bool:
        self.scope.call("shutter")
        return self.scope.shutter_open

    def set_open(self, open: bool) -> None:
        self.scope.call("shutter")
        self.scope.shutter_open = bool(open)


class SimLED(GenericDevice):
    """A white LED light source with an intensity in percent."""

    def __init__(self, scope: Microscope) -> None:
        super().__init__()
        self.scope = scope
        self.register_property(
            "Intensity", default_value=50.0, getter=SimLED.intensity, setter=SimLED.set_intensity, limits=(0.0, 100.0)
        )

    def intensity(self) -> float:
        self.scope.call("LED")
        return self.scope.led_percent

    def set_intensity(self, value: float) -> None:
        self.scope.call("LED")
        self.scope.led_percent = float(value)


class SimulatedCore(UniMMCore):
    """UniMMCore with the simulated devices loaded, as a configuration file would load the devices."""

    def __init__(self, scope: Microscope) -> None:
        super().__init__(mm_path=str(HERE))
        self.scope = scope
        devices = {
            "Camera": SimCamera(scope),
            "XYStage": SimXYStage(scope),
            "ZDrive": SimFocus(scope),
            "Objective": SimTurret(scope),
            "Filter": SimFilterWheel(scope),
            "Shutter": SimShutter(scope),
            "LED": SimLED(scope),
        }
        for label, device in devices.items():
            self.loadPyDevice(label, device)
        self.initializeAllDevices()
        self.setCameraDevice("Camera")
        self.setXYStageDevice("XYStage")
        self.setFocusDevice("ZDrive")
        self.setShutterDevice("Shutter")
        self.setAutoShutter(True)
        self.defineConfigGroup("Channel")
        for preset, label in CHANNEL_PRESETS.items():
            self.defineConfig("Channel", preset, "Filter", "Label", label)

    def snapImage(self) -> None:  # noqa: N802 (MMCore's name)
        """Snap with the shutter open for the exposure when auto shutter is on, as MMCore does for its devices."""
        lighting = self.getAutoShutter()
        self.scope.lighting = lighting
        try:
            super().snapImage()
        finally:
            self.scope.lighting = False

    def getPixelSizeUm(self, cached: bool = False) -> float:  # noqa: N802 (MMCore's name)
        """The camera pixel at the slide under the current objective, as a pixel size configuration gives the size."""
        return CAMERA_PIXEL_UM / self.scope.lens.magnification


_MICROSCOPES: dict[str, Microscope] = {}


def microscope_for(name: str = "default") -> Microscope:
    """The simulated microscope with this name. Every core that connects to the name shares its state."""
    return _MICROSCOPES.setdefault(name, Microscope())


def reset_microscope(name: str = "default", **state: Any) -> Microscope:
    """Put a fresh simulated microscope under this name, with any starting state given."""
    _MICROSCOPES[name] = Microscope(**state)
    return _MICROSCOPES[name]


def build_core(name: str = "default") -> SimulatedCore:
    """A new core connected to the simulated microscope with this name."""
    scope = microscope_for(name)
    scope.call("hub")
    return SimulatedCore(scope)
