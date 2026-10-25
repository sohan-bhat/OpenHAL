"""The rpi-camera driver against the fake Picamera2 class (picamera2 doesn't install off a Pi)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.rpi_camera.conformance import FILE
from openhal.drivers.rpi_camera.driver import RpiCameraDriver
from openhal.drivers.rpi_camera.simulator import FakeRig, SimulatedSensor
from openhal.spec import loads, validate_path
from openhal.spec.models import DeviceFile

EXAMPLES = Path(__file__).parents[3] / "openhal" / "drivers" / "rpi_camera" / "examples"


def make(file: DeviceFile = FILE, rig: FakeRig | None = None) -> tuple[RpiCameraDriver, FakeRig]:
    rig = rig or FakeRig()
    return RpiCameraDriver(file, picamera2_class=rig.picamera2_class()), rig


def device(connect: str = "{ rpi-camera: 0, warmup: 0 s, timeout: 0.5 s }", channels: str = "") -> DeviceFile:
    return loads(
        f"device: Cam\nid: cam\nconnect: {connect}\nread:\n  frame: {{ type: image }}\n{channels}hazard: low\n"
    )


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("write:\n  x: { type: bool }\nconfirmed: { by: t, at: 2026-10-24 }", "read-only"),
        ("read:\n  x: { type: bool, map: { metadata: Lux } }", "images and numbers"),
        ("read:\n  x: { unit: lux }", "needs a map"),
        ("read:\n  x: { unit: lux, map: { metadata: Brightness } }", "Lux"),
    ],
)
def test_bad_files(text: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        RpiCameraDriver(loads(f"device: Cam\nconnect: {{ rpi-camera: 0 }}\n{text}\n"))


@pytest.mark.parametrize(
    ("connect", "message"),
    [
        ("{ rpi-camera: 0, width: 640 }", "both width and height"),
        ("{ rpi-camera: front }", "auto"),
        ("{ rpi-camera: 0, configuration: preview }", "still"),
    ],
)
def test_bad_params(connect: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        RpiCameraDriver(device(connect))


async def test_captures_jpeg_frames_and_metadata() -> None:
    driver, rig = make()
    await driver.connect()
    frame = await driver.read("frame")
    assert isinstance(frame.value, bytes)
    assert frame.value.startswith(b"\xff\xd8")
    light = await driver.read("light")
    assert (light.value, light.unit) == (320.0, "lux")
    exposure = await driver.read("exposure")
    assert (exposure.value, exposure.unit) == (16000.0, "us")
    assert rig.sensors[0].started == 1
    assert rig.sensors[0].frames == 1
    await driver.close()
    assert rig.sensors[0].in_use is False


async def test_configuration_and_quality_reach_picamera2() -> None:
    rig = FakeRig()
    camera_class = rig.picamera2_class()
    driver = RpiCameraDriver(
        device("{ rpi-camera: 0, width: 800, height: 600, jpeg_quality: 40, warmup: 0 s }"),
        picamera2_class=camera_class,
    )
    await driver.connect()
    camera = driver._camera
    assert camera._config == {"use_case": "still", "main": {"size": (800, 600), "format": "BGR888"}}
    assert camera.options["quality"] == 40
    video = RpiCameraDriver(
        device("{ rpi-camera: 0, configuration: video, warmup: 0 s }"), picamera2_class=camera_class
    )
    await driver.close()
    await video.connect()
    assert video._camera._config["main"]["size"] == (1920, 1080)


async def test_open_failures() -> None:
    rig = FakeRig(sensors=[SimulatedSensor(fail_open=True)])
    driver, _ = make(device(), rig)
    with pytest.raises(DriverError, match="Another program may be using it"):
        await driver.connect()
    missing, _ = make(device("{ rpi-camera: 3, warmup: 0 s }"))
    with pytest.raises(DriverError, match="There is no camera 3"):
        await missing.connect()
    none, _ = make(device("{ rpi-camera: auto, warmup: 0 s }"), FakeRig(sensors=[]))
    with pytest.raises(DriverError, match="No camera module is attached"):
        await none.connect()
    busy_rig = FakeRig()
    first, _ = make(device(), busy_rig)
    await first.connect()
    second, _ = make(device(), busy_rig)
    with pytest.raises(DriverError, match="busy"):
        await second.connect()
    assert (await second.health()).connected is False


async def test_capture_failures_garbage_and_timeouts() -> None:
    driver, rig = make(device(channels="  light: { unit: lux, map: { metadata: Lux } }\n"))
    await driver.connect()
    sensor = rig.sensors[0]
    sensor.garbage = True
    with pytest.raises(DriverError, match="not a JPEG"):
        await driver.read("frame")
    sensor.garbage = False
    sensor.fail_capture = True
    with pytest.raises(DriverError, match="failed to capture"):
        await driver.read("frame")
    health = await driver.health()
    assert health.connected is False
    sensor.fail_capture = False
    await driver.connect()
    assert (await driver.health()).connected
    sensor.delay_s = 1.0
    with pytest.raises(TimeoutError, match="no frame within"):
        await driver.read("light")
    assert (await driver.health()).connected is False


async def test_missing_metadata_fields() -> None:
    channels = "  focus: { unit: dimensionless, map: { metadata: FocusFoM } }\n"
    driver, _ = make(device(channels=channels))
    await driver.connect()
    with pytest.raises(DriverError, match="doesn't report FocusFoM"):
        await driver.read("focus")
    with pytest.raises(DriverError, match="no channel"):
        await driver.read("nope")


async def test_reads_need_an_open_camera() -> None:
    driver, _ = make()
    with pytest.raises(DriverError, match="not open"):
        await driver.read("frame")
    assert await driver.describe() is None


async def test_identify_discover_and_describe() -> None:
    rig = FakeRig(sensors=[SimulatedSensor(), SimulatedSensor(num=1, model="imx219")])
    driver, _ = make(FILE, rig)
    identity = await driver.identify()
    assert identity["model"] == "imx708"
    found = await RpiCameraDriver.discover(picamera2_class=rig.picamera2_class())
    assert [(item.address, item.identifiers["model"]) for item in found] == [("0", "imx708"), ("1", "imx219")]
    await driver.connect()
    described = await driver.describe()
    assert described is not None
    assert described["device"]["model"] == "imx708"
    assert described["read"]["lux"] == {"unit": "lux", "map": {"metadata": "Lux"}}
    assert described["read"]["exposure_time"] == {"unit": "us", "map": {"metadata": "ExposureTime"}}
    RpiCameraDriver(DeviceFile.model_validate({"device": "x", "connect": {"rpi-camera": 0}, "read": described["read"]}))


async def test_missing_picamera2_explains_how_to_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "picamera2", None)
    driver = RpiCameraDriver(FILE)
    with pytest.raises(DriverError, match="apt install python3-picamera2"):
        await driver.connect()
    assert await RpiCameraDriver.discover() == []
    assert await driver.identify() == {"camera": "0"}


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.hal.yaml")), ids=lambda path: path.name)
def test_examples_validate_and_load(path: Path) -> None:
    report = validate_path(path)
    assert report.ok, report.problems
    assert report.file is not None
    RpiCameraDriver(report.file)
