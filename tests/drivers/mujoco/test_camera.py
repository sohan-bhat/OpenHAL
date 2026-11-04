"""Cameras on the mujoco driver. A fake renderer runs everywhere, and real rendering runs where OpenGL does."""

from __future__ import annotations

import threading
from typing import Any

import pytest

mujoco = pytest.importorskip("mujoco")
numpy = pytest.importorskip("numpy")

from openhal import images  # noqa: E402
from openhal.drivers.base import DriverError  # noqa: E402
from openhal.drivers.mujoco.camera import png  # noqa: E402
from openhal.drivers.mujoco.conformance import BENCH_ARM  # noqa: E402
from openhal.drivers.mujoco.driver import MujocoDriver  # noqa: E402
from openhal.spec import loads  # noqa: E402
from tests.drivers.mujoco.test_driver import ARM  # noqa: E402

CAMERA_XML = BENCH_ARM.replace(
    "</worldbody>", '<camera name="overhead" pos="0.2 0 0.8" xyaxes="0 -1 0 1 0 0"/>\n  </worldbody>'
)
SEEN = ARM.replace("read:\n", "read:\n  view: { type: image, map: { camera: overhead, width: 320, height: 240 } }\n")


class FakeRenderer:
    """Stands in for mujoco.Renderer, so the camera's own code runs where there is no OpenGL."""

    def __init__(self, model: Any, height: int, width: int) -> None:
        self.size = (width, height)
        self.cameras: list[int] = []
        self.thread = threading.get_ident()
        self.closed = False

    def update_scene(self, data: Any, camera: int) -> None:
        self.cameras.append(camera)

    def render(self) -> Any:
        width, height = self.size
        frame = numpy.zeros((height, width, 3), dtype=numpy.uint8)
        frame[:, :, 0] = 200
        return frame

    def close(self) -> None:
        self.closed = True


def driver_with(text: str = SEEN, *, renderer: Any = FakeRenderer) -> MujocoDriver:
    return MujocoDriver(loads(text), loader=lambda: mujoco.MjModel.from_xml_string(CAMERA_XML), renderer=renderer)


def gl_available() -> bool:
    found: list[bool] = []

    def attempt() -> None:
        try:
            model = mujoco.MjModel.from_xml_string(CAMERA_XML)
            renderer = mujoco.Renderer(model, height=32, width=32)
            renderer.close()
            found.append(True)
        except Exception:  # noqa: BLE001
            found.append(False)

    worker = threading.Thread(target=attempt)
    worker.start()
    worker.join()
    return found[0]


async def test_an_image_channel_reads_the_camera_as_png() -> None:
    made: list[FakeRenderer] = []

    def factory(model: Any, height: int, width: int) -> FakeRenderer:
        made.append(FakeRenderer(model, height, width))
        return made[-1]

    driver = driver_with(renderer=factory)
    await driver.connect()
    try:
        first = await driver.read("view")
        second = await driver.read("view")
    finally:
        await driver.close()
    assert isinstance(first.value, bytes)
    assert images.mime_type(first.value) == "image/png"
    assert images.size(first.value) == (320, 240)
    assert second.value == first.value
    assert len(made) == 1
    assert made[0].cameras == [0, 0]
    assert made[0].thread != threading.get_ident()
    assert made[0].closed


async def test_the_offscreen_buffer_grows_to_the_largest_frame() -> None:
    driver = driver_with(SEEN.replace("width: 320, height: 240", "width: 1280, height: 720"))
    await driver.connect()
    try:
        assert driver.world is not None
        assert driver.world.model.vis.global_.offwidth == 1280
        assert driver.world.model.vis.global_.offheight == 720
        assert (await driver.identify())["cameras"] == "overhead"
        assert (await driver.describe() or {})["read"]["overhead"] == {"type": "image", "map": {"camera": "overhead"}}
    finally:
        await driver.close()


async def test_a_renderer_that_fails_names_the_gl_setting() -> None:
    def broken(model: Any, height: int, width: int) -> Any:
        raise RuntimeError("no display")

    driver = driver_with(renderer=broken)
    await driver.connect()
    try:
        with pytest.raises(DriverError, match="MUJOCO_GL to egl or osmesa"):
            await driver.read("view")
    finally:
        await driver.close()


async def test_a_camera_the_model_lacks_fails_to_connect() -> None:
    driver = driver_with(SEEN.replace("camera: overhead", "camera: side"))
    with pytest.raises(DriverError, match=r"read\.view: the model has no camera named 'side'"):
        await driver.connect()
    assert driver.cameras is None


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("view: { type: image,", "view: { unit: mm,", "an image channel needs map.camera"),
        ("map: { camera: overhead,", "map: { joint: pan,", "width and height are a camera's frame size"),
        ("map: { camera: overhead,", "map: { camera: overhead, axis: x,", "a camera takes no axis"),
        ("width: 320", "width: 8", "greater than or equal to 16"),
        ("height: 240", "height: 4096", "less than or equal to 2048"),
    ],
)
def test_camera_maps_are_checked(old: str, new: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        driver_with(SEEN.replace(old, new))


def test_png_frames_decode_to_their_pixels() -> None:
    import zlib

    frame = numpy.arange(2 * 3 * 3, dtype=numpy.uint8).reshape(2, 3, 3)
    data = png(frame)
    assert images.size(data) == (3, 2)
    start = data.index(b"IDAT") + 4
    length = int.from_bytes(data[start - 8 : start - 4], "big")
    rows = zlib.decompress(data[start : start + length])
    assert rows == b"\x00" + frame[0].tobytes() + b"\x00" + frame[1].tobytes()


@pytest.mark.skipif(not gl_available(), reason="OpenGL isn't available. Set MUJOCO_GL to egl or osmesa.")
async def test_a_real_render_shows_the_scene() -> None:
    driver = MujocoDriver(loads(SEEN), loader=lambda: mujoco.MjModel.from_xml_string(CAMERA_XML))
    await driver.connect()
    try:
        reading = await driver.read("view")
    finally:
        await driver.close()
    assert isinstance(reading.value, bytes)
    assert images.size(reading.value) == (320, 240)
    assert len(reading.value) > 1000
