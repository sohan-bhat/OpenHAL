"""A fake cv2.VideoCapture with a simulated USB camera. No camera, no video device.

The fake implements the VideoCapture calls the driver uses: `isOpened`, `read`, `grab`, `set`,
`get`, `release` and `getBackendName`. Frames are real numpy BGR images (a gradient with a moving
bar), so JPEG encoding in the driver is the real cv2 code.

Fault injection. `unplug()` makes reads fail as OpenCV does when the device disappears,
`delay_s` makes reads slow, `garbage` returns a frame that is not an image, and `refuse_open`
makes the capture fail to open.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

_PROPS = {
    cv2.CAP_PROP_FRAME_WIDTH: "width",
    cv2.CAP_PROP_FRAME_HEIGHT: "height",
    cv2.CAP_PROP_FPS: "fps",
    cv2.CAP_PROP_BRIGHTNESS: "brightness",
}


@dataclass
class SimulatedCamera:
    width: int = 640
    height: int = 480
    fps: float = 30.0
    brightness: float = 128.0
    max_width: int = 1280
    max_height: int = 720
    plugged: bool = True
    refuse_open: bool = False
    garbage: bool = False
    delay_s: float = 0.0
    frames: int = 0
    opened: list[Any] = field(default_factory=list)
    settings: list[tuple[str, float]] = field(default_factory=list)

    def frame(self) -> Any:
        self.frames += 1
        image = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        image[:, :, 1] = np.linspace(0, 255, self.width, dtype=np.uint8)[None, :]
        bar = (self.frames * 8) % self.width
        image[:, bar : bar + 4, 2] = 255
        return image

    def unplug(self) -> None:
        self.plugged = False

    def plug_in(self) -> None:
        self.plugged = True


class FakeCapture:
    """Stands in for cv2.VideoCapture."""

    def __init__(self, camera: SimulatedCamera, source: Any, api_preference: int = 0) -> None:
        self.camera = camera
        self.source = source
        self.api_preference = api_preference
        self._open = camera.plugged and not camera.refuse_open
        camera.opened.append(self)

    def isOpened(self) -> bool:  # noqa: N802 (OpenCV's name)
        return self._open

    def getBackendName(self) -> str:  # noqa: N802 (OpenCV's name)
        return "FAKE"

    def set(self, prop: int, value: float) -> bool:
        name = _PROPS.get(prop)
        if name is None or not self._open:
            return False
        self.camera.settings.append((name, value))
        if name == "width":
            self.camera.width = int(min(value, self.camera.max_width))
        elif name == "height":
            self.camera.height = int(min(value, self.camera.max_height))
        elif name == "fps":
            self.camera.fps = float(value)
        return True

    def get(self, prop: int) -> float:
        name = _PROPS.get(prop)
        if name is None or not self._open:
            return 0.0
        return float(getattr(self.camera, name))

    def grab(self) -> bool:
        if not (self._open and self.camera.plugged):
            return False
        self.camera.frames += 1
        return True

    def read(self) -> tuple[bool, Any]:
        if self.camera.delay_s:
            time.sleep(self.camera.delay_s)
        if not self._open or not self.camera.plugged:
            return False, None
        if self.camera.garbage:
            return True, np.zeros((0,), dtype=np.uint8)
        return True, self.camera.frame()

    def release(self) -> None:
        self._open = False


def capture_factory(camera: SimulatedCamera) -> Any:
    """A drop-in for cv2.VideoCapture that opens `camera`."""

    def make(source: Any, api_preference: int = 0) -> FakeCapture:
        return FakeCapture(camera, source, api_preference)

    return make
