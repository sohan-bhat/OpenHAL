"""The uvc driver against the fake VideoCapture and the simulated camera."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.uvc.conformance import FILE
from openhal.drivers.uvc.driver import UvcDriver
from openhal.drivers.uvc.simulator import SimulatedCamera, capture_factory
from openhal.kernel import Kernel
from openhal.kernel.principals import human
from openhal.spec import loads, validate_path
from openhal.spec.models import DeviceFile

EXAMPLES = Path(__file__).parents[3] / "openhal" / "drivers" / "uvc" / "examples"
WHO = human("tester")


def make(file: DeviceFile = FILE, camera: SimulatedCamera | None = None) -> tuple[UvcDriver, SimulatedCamera]:
    camera = camera or SimulatedCamera()
    return UvcDriver(file, capture_factory=capture_factory(camera)), camera


def device(connect: str = "{ uvc: auto }", channels: str = "read:\n  frame: { type: image }") -> DeviceFile:
    return loads(f"device: Cam\nid: cam\nconnect: {connect}\n{channels}\nhazard: low\n")


def decode(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    assert image is not None
    return image


@pytest.mark.parametrize(
    ("channels", "message"),
    [
        ("write:\n  x: { type: bool }\nconfirmed: { by: t, at: 2026-10-24 }", "read-only"),
        ("read:\n  x: { type: bool, map: { property: width } }", "images and numbers"),
        ("read:\n  x: { unit: dimensionless }", "needs a map"),
        ("read:\n  x: { unit: dimensionless, map: { property: zoom } }", "width"),
    ],
)
def test_bad_files(channels: str, message: str) -> None:
    text = f"device: Cam\nconnect: {{ uvc: auto }}\n{channels}\n"
    with pytest.raises(DriverError, match=message):
        UvcDriver(loads(text))


@pytest.mark.parametrize(
    ("connect", "message"),
    [("{ uvc: auto, jpeg_quality: 0 }", "greater than or equal to 1"), ("{ uvc: auto, backend: vfw }", "v4l2")],
)
def test_bad_params(connect: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        UvcDriver(device(connect))


def test_sources() -> None:
    assert UvcDriver(device("{ uvc: auto }")).source == 0
    assert UvcDriver(device("{ uvc: 2 }")).source == 2
    assert UvcDriver(device('{ uvc: "1" }')).source == 1
    assert UvcDriver(device("{ uvc: /dev/video4 }")).source == "/dev/video4"


async def test_frames_are_jpeg_at_the_requested_size() -> None:
    driver, camera = make()
    await driver.connect()
    assert ("width", 320.0) in camera.settings
    reading = await driver.read("frame")
    assert isinstance(reading.value, bytes)
    assert reading.value[:2] == b"\xff\xd8"
    assert reading.unit is None
    assert decode(reading.value).shape == (240, 320, 3)
    assert (await driver.read("width")).value == 320.0
    fps = await driver.read("fps")
    assert (fps.value, fps.unit) == (30.0, "Hz")
    second = await driver.read("frame")
    assert second.value != reading.value, "each read is a new frame"
    assert camera.frames >= 4, "a frame is flushed before each capture"
    await driver.close()


async def test_requested_size_is_only_a_request() -> None:
    driver, _ = make(device("{ uvc: auto, width: 4000, height: 3000 }"))
    await driver.connect()
    image = decode((await driver.read("frame")).value)  # type: ignore[arg-type]
    assert image.shape[:2] == (720, 1280)
    described = await driver.describe()
    assert described is not None
    assert "1280x720" in described["notes"]
    assert described["read"]["frame"] == {"type": "image"}


async def test_jpeg_quality_changes_the_size() -> None:
    low, _ = make(device("{ uvc: auto, jpeg_quality: 10 }"))
    high, _ = make(device("{ uvc: auto, jpeg_quality: 95 }"))
    await low.connect()
    await high.connect()
    small = await low.read("frame")
    large = await high.read("frame")
    assert len(small.value) < len(large.value)  # type: ignore[arg-type]


async def test_open_failures() -> None:
    driver, camera = make(camera=SimulatedCamera(refuse_open=True))
    with pytest.raises(DriverError, match="camera permission"):
        await driver.connect()
    assert (await driver.health()).connected is False
    with pytest.raises(DriverError, match="not open"):
        await driver.read("frame")
    assert camera.opened[0].isOpened() is False


async def test_unplugged_camera() -> None:
    driver, camera = make()
    await driver.connect()
    assert (await driver.health()).connected
    camera.unplug()
    assert (await driver.health()).connected is False
    with pytest.raises(DriverError, match="unplugged"):
        await driver.read("frame")
    camera.plug_in()
    health = await driver.health()
    assert health.connected is False
    assert "returned no frame" in health.detail
    await driver.connect()
    assert (await driver.health()).connected


async def test_garbage_and_slow_frames() -> None:
    driver, camera = make(device("{ uvc: auto, timeout: 0.3 s }"))
    await driver.connect()
    camera.garbage = True
    with pytest.raises(DriverError, match="not an image"):
        await driver.read("frame")
    camera.garbage = False
    camera.delay_s = 0.6
    with pytest.raises(TimeoutError, match="no frame within"):
        await driver.read("frame")


async def test_kernel_reads_and_no_writes() -> None:
    driver, _ = make()
    kernel = Kernel()
    kernel.register(FILE, driver)
    await kernel.connect(FILE.device_id)
    reading = await kernel.read(FILE.device_id, "frame", WHO)
    assert isinstance(reading.value, bytes)
    with pytest.raises(DriverError, match="no channel"):
        await driver.read("nope")


async def test_discover_reads_sysfs(tmp_path: Path) -> None:
    for index, (name, node) in enumerate((("HD Webcam", "0"), ("HD Webcam", "1"), ("Capture card", "0"))):
        entry = tmp_path / f"video{index}"
        entry.mkdir()
        (entry / "name").write_text(f"{name}\n")
        (entry / "index").write_text(f"{node}\n")
    found = await UvcDriver.discover(sysfs=tmp_path)
    assert [(item.address, item.label) for item in found] == [
        ("/dev/video0", "HD Webcam"),
        ("/dev/video2", "Capture card"),
    ]
    assert await UvcDriver.discover(sysfs=tmp_path / "missing") == []


async def test_identify() -> None:
    driver, _ = make()
    assert await driver.identify() == {"source": "0", "backend": "any"}
    await driver.connect()
    assert (await driver.identify())["backend"] == "FAKE"


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.hal.yaml")), ids=lambda path: path.name)
def test_examples_validate_and_load(path: Path) -> None:
    report = validate_path(path)
    assert report.ok, report.problems
    assert report.file is not None
    UvcDriver(report.file)
