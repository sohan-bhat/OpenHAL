"""The micromanager driver's file checks, frame conversion and connection errors, without a microscope."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("pymmcore_plus")

from openhal.drivers.base import DriverError
from openhal.drivers.micromanager import frames, simulator
from openhal.drivers.micromanager.driver import MicromanagerDriver
from openhal.spec import loads
from openhal.spec.models import DeviceFile
from tests import no_hardware

ROOT = Path(__file__).resolve().parents[3]


def file(body: str, connect: str = 'micromanager: "sim:maps"') -> DeviceFile:
    return loads(f"device: Microscope\nid: scope\nconnect: {{ {connect} }}\n{body}\nhazard: medium\n")


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("read:\n  stage_x: { unit: um }", "needs a map"),
        ("read:\n  x: { unit: degC }", "converts to um"),
        ("read:\n  x: { unit: um, map: { stage: xy } }", "needs axis x or y"),
        ("read:\n  lamp: { unit: percent, map: { property: Level } }", "needs the device"),
        ("read:\n  lamp: { unit: percent, map: { state: Wheel, group: Channel } }", "exactly one"),
        ("read:\n  shutter: { unit: dimensionless }", "true or false"),
        ("read:\n  image: { unit: dimensionless }", "is an image"),
        ("write:\n  image: { type: bool }", "can only be read"),
        ("write:\n  objective: { type: bool, map: { state: Objective } }", "enum or a string"),
        (
            "write:\n  x: { unit: um, min: 0, max: 1 }\n  y: { unit: um, min: 0, max: 1 }\n"
            "actions:\n  move_xy: { args: { x: { unit: um, min: 0, max: 1 }, y: { unit: um, min: 0, max: 1 } } }",
            "to effects",
        ),
        ("actions:\n  move_xy: { args: { x: { unit: um, min: 0, max: 1 } } }", "takes the arguments x and y"),
        ("actions:\n  autofocus: { map: { command: autofocus, method: image } }", "needs a write channel"),
        ("actions:\n  home: { args: { speed: { unit: um, min: 0, max: 1 } } }", "takes no arguments"),
        ("actions:\n  autofocus: { map: { command: autofocus, span: 3 kg } }", "needs a length"),
    ],
)
def test_the_driver_checks_the_file_before_connecting(body: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        MicromanagerDriver(file(body))


@pytest.mark.parametrize("config", ["sim:", "Sim", "mm config", "lower_case"])
def test_config_is_sim_or_an_environment_variable(config: str) -> None:
    with pytest.raises(ValueError, match="config"):
        MicromanagerDriver(file("read:\n  busy: { type: bool }", f'micromanager: "{config}"'))


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("write:\n  wheel: { type: enum, values: [A], map: { state: Wheel } }", "not a loaded state device"),
        ("write:\n  filter: { type: enum, values: [DAPI, Cy5], map: { state: Filter } }", "no states"),
        ("write:\n  preset: { type: enum, values: [DAPI], map: { group: Light } }", "no group"),
        ("write:\n  lamp: { unit: percent, min: 0, max: 1, map: { device: LED, property: Watts } }", "no property"),
        ("read:\n  z: { unit: um, map: { stage: focus, device: XYStage } }", "not a loaded Stage device"),
        ("read:\n  shutter: { type: bool, map: { shutter: LED } }", "not a loaded shutter"),
    ],
)
async def test_connect_checks_every_map_against_the_configuration(body: str, message: str) -> None:
    simulator.reset_microscope("maps")
    driver = MicromanagerDriver(file(body))
    with pytest.raises(DriverError, match=message):
        await driver.connect()
    await driver.close()


async def test_a_configuration_comes_from_an_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENHAL_TEST_MM_CONFIG", raising=False)
    driver = MicromanagerDriver(file("read:\n  busy: { type: bool }", "micromanager: OPENHAL_TEST_MM_CONFIG"))
    assert not driver.simulated
    with pytest.raises(DriverError, match="Set the OPENHAL_TEST_MM_CONFIG environment variable"):
        await driver.connect()


async def test_tests_never_load_a_real_configuration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = tmp_path / "MMConfig.cfg"
    config.write_text("Device,Camera,DemoCamera,DCam\n")
    monkeypatch.setenv("OPENHAL_TEST_MM_CONFIG", str(config))
    driver = MicromanagerDriver(file("read:\n  busy: { type: bool }", "micromanager: OPENHAL_TEST_MM_CONFIG"))
    with pytest.raises(DriverError, match="could not start") as raised:
        await driver.connect()
    assert isinstance(raised.value.__cause__, no_hardware.RealHardwareError)


async def test_a_configuration_that_fails_to_load_names_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    class Refusing:
        def __init__(self, mm_path: str | None = None) -> None:
            self.mm_path = mm_path

        def loadSystemConfiguration(self, path: str) -> None:  # noqa: N802 (MMCore's name)
            raise RuntimeError("Line 3: Failed to load device adapter")

    monkeypatch.setenv("OPENHAL_TEST_MM_CONFIG", "/nowhere/MMConfig.cfg")
    monkeypatch.setattr("openhal.drivers.micromanager.driver._core_class", lambda: Refusing)
    driver = MicromanagerDriver(file("read:\n  busy: { type: bool }", "micromanager: OPENHAL_TEST_MM_CONFIG"))
    with pytest.raises(DriverError, match="could not load the configuration in OPENHAL_TEST_MM_CONFIG"):
        await driver.connect()


def test_a_deep_frame_stretches_and_a_dark_frame_stays_dark() -> None:
    rng = np.random.default_rng(1)
    signal = np.full((64, 80), 100, dtype=np.uint16)
    signal[20:40, 20:40] = 900
    stretched = frames.to_8bit(signal, 12, "auto")
    assert stretched.dtype == np.uint8
    assert stretched.max() == 255
    assert stretched.min() == 0
    full = frames.to_8bit(signal, 12, "full")
    assert full.max() == round(900 * 255 / 4095)
    dark = (100 + rng.normal(0, 3, (64, 80))).astype(np.uint16)
    assert frames.to_8bit(dark, 12, "auto").max() < 40


def test_color_frames_drop_alpha_and_odd_shapes_fail() -> None:
    bgra = np.zeros((10, 12, 4), dtype=np.uint8)
    assert frames.to_8bit(bgra, 8, "auto").shape == (10, 12, 3)
    for shape in ((10,), (10, 12, 2), (0, 12)):
        with pytest.raises(ValueError, match="not an image"):
            frames.to_8bit(np.zeros(shape, dtype=np.uint8), 8, "auto")


def test_frames_encode_within_the_size_asked() -> None:
    pixels = (np.arange(600 * 800) % 251).astype(np.uint8).reshape(600, 800)
    jpeg = frames.encode(pixels, "jpeg", 80, 400)
    png = frames.encode(pixels, "png", 80, 4096)
    assert jpeg.startswith(b"\xff\xd8\xff")
    assert png.startswith(b"\x89PNG")
    from openhal import images

    assert images.size(jpeg) == (400, 300)
    assert images.size(png) == (800, 600)


def test_the_focus_score_prefers_detail() -> None:
    rng = np.random.default_rng(2)
    sharp = (rng.random((200, 300)) * 255).astype(np.uint8)
    flat = np.full((200, 300), 128, dtype=np.uint8)
    assert frames.focus_score(sharp) > 10 * frames.focus_score(flat)
    assert frames.focus_score(np.zeros((4, 2))) == 0.0


def test_the_slide_is_small_and_credited() -> None:
    assert simulator.SLIDE.stat().st_size < 1_000_000
    credits = (ROOT / "docs" / "DEPENDENCIES.md").read_text(encoding="utf-8")
    assert "slide.jpg" in credits
    assert "CC BY 2.0" in credits
    assert "ZEISS Microscopy" in credits
