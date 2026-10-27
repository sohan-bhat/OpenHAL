"""A simulated printer webcam, the way crowsnest serves a USB camera on a Klipper printer's host.

`GET /webcam/?action=snapshot` answers with the frame the camera is showing, as JPEG. `show()`
changes the frame. The frames are the demo's line drawings (examples/print-babysitter/frames/),
never photos. The webcam is served through httpx.MockTransport to the http driver, so nothing
opens a socket or touches a camera.
"""

from __future__ import annotations

import httpx

from openhal.drivers.http.driver import HttpDriver
from openhal.spec.models import DeviceFile


class Webcam:
    """The camera, with every frame it can show by name."""

    def __init__(self, frames: dict[str, bytes], showing: str) -> None:
        self.frames = frames
        self.showing = showing
        self.snapshots = 0

    def show(self, name: str) -> None:
        if name not in self.frames:
            raise KeyError(f"The webcam has no frame named {name}.")
        self.showing = name

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._answer)

    def _answer(self, request: httpx.Request) -> httpx.Response:
        if request.method != "GET":
            return httpx.Response(405)
        if request.url.path == "/":
            return httpx.Response(200, text="crowsnest", headers={"Content-Type": "text/plain"})
        if request.url.path == "/webcam/" and request.url.params.get("action") == "snapshot":
            self.snapshots += 1
            return httpx.Response(200, content=self.frames[self.showing], headers={"Content-Type": "image/jpeg"})
        return httpx.Response(404, text="not found")


class SimulatedWebcam(HttpDriver):
    """The http driver on a simulated webcam. The driver reports itself as simulated, so clients label the frames
    demo data."""

    def __init__(self, device: DeviceFile, webcam: Webcam) -> None:
        super().__init__(device, transport=webcam.transport())

    @property
    def simulated(self) -> bool:
        return True
