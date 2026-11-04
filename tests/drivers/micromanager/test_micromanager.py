"""The micromanager driver, against pymmcore-plus's real core with the simulated microscope's devices."""

from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest

pytest.importorskip("pymmcore_plus")

from PIL import Image

from openhal.drivers.base import DriverError
from openhal.drivers.micromanager import frames
from openhal.drivers.micromanager.driver import MicromanagerDriver
from openhal.drivers.micromanager.simulator import OBJECTIVES, Microscope, reset_microscope
from openhal.spec import load, loads
from tests.drivers.serial.kit import Bench, assert_done, assert_failed, eventually

LENSES = ", ".join(lens.label for lens in OBJECTIVES)
EXAMPLES = Path(__file__).resolve().parents[3] / "openhal" / "drivers" / "micromanager" / "examples"


def scope_file(name: str, *, z_max: float = 1650, extra: str = "") -> str:
    return f"""
device: Test microscope
id: scope
connect: {{ micromanager: "sim:{name}", timeout: 3 s, action_wait: 5 s, max_side: 512 }}
read:
  image: {{ type: image }}
  pixel_size: {{ unit: um }}
  busy: {{ type: bool }}
write:
  x: {{ unit: um, min: -150, max: 150 }}
  y: {{ unit: mm, min: -0.11, max: 0.11 }}
  z: {{ unit: um, min: 1000, max: {z_max} }}
  exposure: {{ unit: ms, min: 1, max: 1000 }}
  objective: {{ type: enum, values: [{LENSES}], map: {{ state: Objective }} }}
  filter: {{ type: enum, values: [DAPI, GFP, DAPI-GFP, TRITC], map: {{ state: Filter }} }}
  channel: {{ type: enum, values: [DAPI, GFP, Dual, TRITC], map: {{ group: Channel }} }}
  shutter: {{ type: bool }}
  light: {{ unit: percent, min: 0, max: 100, map: {{ device: LED, property: Intensity }} }}
actions:
  stop: {{}}
  move_xy:
    args: {{ x: {{ unit: um, min: -150, max: 150 }}, y: {{ unit: um, min: -110, max: 110 }} }}
    effects: [x, y]
  autofocus:
    args: {{ span: {{ unit: um, min: 5, max: 100 }} }}
    effects: [z]
  home_focus: {{ effects: [z] }}
{extra}
safe_state: {{ shutter: false }}
hazard: medium
confirmed: {{ by: tester, at: 2026-11-03 }}
"""


def make(name: str, text: str | None = None, **state: object) -> tuple[MicromanagerDriver, Microscope, Bench]:
    scope = reset_microscope(name, seed=7, **state)
    file = loads(text or scope_file(name))
    driver = MicromanagerDriver(file)
    return driver, scope, Bench(file, driver)


def pixels(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


async def test_connect_reads_every_device_from_the_core() -> None:
    driver, _scope, bench = make("reads")
    await bench.connect()
    assert driver.simulated
    identity = await driver.identify()
    assert identity["simulated"] == "true"
    assert identity["mmcore"].startswith("MMCore version")
    assert (await bench.read("x")).value == 0.0
    assert (await bench.read("z")).value == pytest.approx(1000.0)
    assert (await bench.read("objective")).value == OBJECTIVES[0].label
    assert (await bench.read("filter")).value == "DAPI-GFP"
    assert (await bench.read("channel")).value == "Dual"
    assert (await bench.read("exposure")).value == pytest.approx(50.0)
    assert (await bench.read("pixel_size")).value == pytest.approx(0.325)
    assert (await bench.read("shutter")).value is False
    assert (await bench.read("light")).value == pytest.approx(50.0)
    assert (await bench.read("busy")).value is False
    assert "simulated microscope" in (await driver.health()).detail
    await bench.close()


async def test_a_snapshot_is_an_image_of_the_slide_under_the_stage() -> None:
    _driver, scope, bench = make("snap")
    await bench.connect()
    assert_done(await bench.write("z", "1500 um"))
    first = await bench.read("image")
    assert isinstance(first.value, bytes)
    assert first.value.startswith(b"\xff\xd8\xff")
    image = pixels(first.value)
    assert image.size == (512, 384)
    assert_done(await bench.write("x", "120 um"))
    moved = pixels((await bench.read("image")).value)
    assert frames.focus_score(image) > 0
    assert image.tobytes() != moved.tobytes()
    assert scope.snaps >= 2
    await bench.close()


async def test_defocus_blurs_the_frame_and_focus_sharpens_it() -> None:
    _driver, scope, bench = make("blur", objective=2)
    await bench.connect()
    focal = scope.focal_plane()
    assert_done(await bench.write("z", f"{focal} um"))
    sharp = frames.focus_score(pixels((await bench.read("image")).value))
    assert_done(await bench.write("z", f"{focal - 8} um"))
    blurred = frames.focus_score(pixels((await bench.read("image")).value))
    assert sharp > 3 * blurred
    await bench.close()


async def test_the_filter_picks_the_stain_and_a_closed_shutter_gives_a_dark_frame() -> None:
    driver, _scope, bench = make("filters", z_um=1500.0)
    await bench.connect()
    assert_done(await bench.write("filter", "DAPI"))
    red, _green, blue = (band.getextrema()[1] for band in pixels((await bench.read("image")).value).split())
    assert blue > 3 * max(red, 30)
    assert_done(await bench.write("channel", "TRITC"))
    assert (await bench.read("filter")).value == "TRITC"
    assert max(band.getextrema()[1] for band in pixels((await bench.read("image")).value).split()) < 40
    assert_done(await bench.write("channel", "Dual"))
    assert driver.core.getAutoShutter() is True
    driver.core.setAutoShutter(False)
    dark = pixels((await bench.read("image")).value).convert("L")
    assert dark.getextrema()[1] < 40
    assert_done(await bench.write("shutter", True))
    lit = pixels((await bench.read("image")).value).convert("L")
    assert lit.getextrema()[1] > 100
    await bench.close()


async def test_writes_move_one_axis_and_read_back_the_device() -> None:
    _driver, scope, bench = make("writes")
    await bench.connect()
    assert_done(await bench.write("y", "-0.05 mm"))
    assert_done(await bench.write("x", "100 um"))
    assert (scope.x_um, scope.y_um) == (pytest.approx(100.0), pytest.approx(-50.0))
    assert (await bench.read("y")).value == pytest.approx(-0.05)
    assert_done(await bench.write("objective", OBJECTIVES[2].label))
    assert (await bench.read("pixel_size")).value == pytest.approx(6.5 / 63)
    assert_done(await bench.write("exposure", "0.2 s"))
    assert scope.exposure_ms == pytest.approx(200.0)
    assert_done(await bench.write("light", "80 %"))
    assert scope.led_percent == pytest.approx(80.0)
    assert_done(await bench.write("z", "1600 um"))
    assert scope.z_um == pytest.approx(1600.0)
    await bench.close()


async def test_the_kernel_blocks_z_past_the_limit_before_the_objective_moves() -> None:
    _driver, scope, bench = make("limit", objective=2)
    await bench.connect()
    decision = await bench.write("z", "1700 um")
    assert decision.status == "blocked"
    assert scope.crashes == 0
    assert scope.z_um == pytest.approx(1000.0)
    await bench.close()


async def test_a_move_into_the_slide_stalls_and_reports_a_fault() -> None:
    _driver, scope, bench = make("crash", text=scope_file("crash", z_max=3000), objective=2)
    await bench.connect()
    assert_failed(await bench.write("z", "1800 um"), "touched the slide")
    assert scope.crashes == 1
    assert scope.z_um == pytest.approx(scope.contact())
    assert_failed(await bench.write("x", "50 um"), "touching the slide")
    assert_done(await bench.write("z", "1400 um"))
    assert not scope.touching
    assert_done(await bench.write("x", "50 um"))
    await bench.close()


async def test_image_autofocus_finds_the_focal_plane_inside_the_z_limits() -> None:
    _driver, scope, bench = make("focus", objective=1, x_um=60.0, y_um=-30.0)
    await bench.connect()
    focal = scope.focal_plane()
    assert_done(await bench.write("z", f"{focal - 9} um"))
    visited: list[float] = []
    move = scope.move_z

    def spy(z_um: float) -> None:
        visited.append(z_um)
        move(z_um)

    scope.move_z = spy  # type: ignore[method-assign]
    assert_done(await bench.act("autofocus", span="30 um"))
    assert scope.z_um == pytest.approx(focal, abs=0.8)
    assert min(visited) >= 1000
    assert max(visited) <= 1650
    assert (await bench.read("z")).value == pytest.approx(scope.z_um)
    await bench.close()


async def test_autofocus_sweeps_stop_at_the_files_focus_limit() -> None:
    _driver, scope, bench = make("near", text=scope_file("near", z_max=1497), objective=1)
    await bench.connect()
    assert_done(await bench.write("z", "1490 um"))
    assert_done(await bench.act("autofocus", span="40 um"))
    assert scope.z_um <= 1497 + 1e-6
    assert scope.crashes == 0
    await bench.close()


async def test_a_device_autofocus_needs_an_autofocus_device() -> None:
    extra = "  focus_lock: { map: { command: autofocus, method: device }, effects: [z] }"
    _driver, _scope, bench = make("device", text=scope_file("device", extra=extra))
    await bench.connect()
    assert_failed(await bench.act("focus_lock"), "no autofocus device")
    await bench.close()


async def test_move_xy_home_and_stop() -> None:
    _driver, scope, bench = make("move", z_um=1500.0)
    await bench.connect()
    assert_done(await bench.act("move_xy", x="-40 um", y="25 um"))
    assert (scope.x_um, scope.y_um) == (pytest.approx(-40.0), pytest.approx(25.0))
    assert (await bench.read("x")).value == pytest.approx(-40.0)
    assert_done(await bench.act("home_focus"))
    assert scope.z_um == pytest.approx(0.0)
    assert_done(await bench.act("stop"))
    await bench.close()


async def test_a_long_autofocus_returns_started_and_a_stop_cancels_it() -> None:
    text = scope_file("long").replace("action_wait: 5 s", "action_wait: 200 ms")
    driver, scope, bench = make("long", text=text)
    await bench.connect()
    scope.delay_s = 0.05
    assert_done(await bench.act("autofocus", span="30 um"))
    assert driver.running
    scope.shutter_open = True
    assert await bench.stop() in ("safe", "done")

    async def finished() -> bool:
        return not driver.running

    await eventually(finished)
    assert scope.shutter_open is False
    scope.delay_s = 0.0
    await bench.close()


async def test_a_lost_microscope_reports_unhealthy_until_reconnected() -> None:
    driver, scope, bench = make("lost")
    await bench.connect()
    scope.unplug()
    health = await driver.health()
    assert not health.connected
    assert "lost" in health.detail
    scope.plug_in()
    with pytest.raises(DriverError, match="connection to the microscope failed"):
        await driver.read("x")
    await driver.connect()
    assert (await driver.health()).connected
    await bench.close()


async def test_a_slow_microscope_times_out() -> None:
    driver, scope, bench = make("slow")
    await bench.connect()
    scope.delay_s = 3.5
    with pytest.raises(TimeoutError, match="didn't finish"):
        await driver.read("x")
    scope.delay_s = 0.0
    await asyncio.sleep(3.6)
    await bench.close()


async def test_describe_proposes_limits_from_the_configuration() -> None:
    driver, _scope, bench = make("describe", z_um=1500.0)
    await bench.connect()
    proposal = await driver.describe()
    assert proposal is not None
    write = proposal["write"]
    assert write["z"]["max"] == pytest.approx(1550.0)
    assert write["z"]["min"] == pytest.approx(1000.0)
    assert write["objective"]["values"] == [lens.label for lens in OBJECTIVES]
    assert write["led_intensity"]["map"] == {"device": "LED", "property": "Intensity"}
    assert proposal["actions"]["autofocus"]["map"]["method"] == "image"
    assert all(entry.get("suggested") for entry in write.values())
    assert "crash limit" in proposal["notes"]
    await bench.close()


async def test_the_examples_load_and_the_simulated_one_holds_z_until_confirmed() -> None:
    for path in sorted(EXAMPLES.glob("*.hal.yaml")):
        MicromanagerDriver(load(path))
    scope = reset_microscope("default", seed=3)
    file = load(EXAMPLES / "simulated-microscope.hal.yaml")
    driver = MicromanagerDriver(file)
    bench = Bench(file, driver)
    await bench.connect()
    assert isinstance((await bench.read("image")).value, bytes)
    assert (await bench.write("z", "1500 um")).status == "blocked"
    assert scope.z_um == 1000.0
    assert_done(await bench.write("light", "60 %"))
    assert scope.led_percent == 60.0
    await bench.close()


async def test_move_xy_stays_inside_the_x_and_y_channel_limits() -> None:
    text = scope_file("bounds").replace(
        "args: { x: { unit: um, min: -150, max: 150 }", "args: { x: { unit: um, min: -500, max: 500 }"
    )
    _driver, scope, bench = make("bounds", text=text, z_um=1500.0)
    await bench.connect()
    assert_failed(await bench.act("move_xy", x="400 um", y="0 um"), "outside x's limits")
    assert (scope.x_um, scope.y_um) == (0.0, 0.0)
    await bench.close()


async def test_autofocus_steps_no_faster_than_the_focus_rate() -> None:
    text = scope_file("paced").replace(
        "z: { unit: um, min: 1000, max: 1650 }", "z: { unit: um, min: 1000, max: 1650, max_change_per_s: 200 }"
    )
    _driver, scope, bench = make("paced", text=text, objective=1, z_um=1500.0)
    await bench.connect()
    loop = asyncio.get_running_loop()
    started = loop.time()
    assert_done(await bench.act("autofocus", span="40 um"))
    assert loop.time() - started >= 40 / 200
    assert scope.z_um == pytest.approx(scope.focal_plane(), abs=0.8)
    await bench.close()
