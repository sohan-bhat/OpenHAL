"""The rpi-gpio driver against gpiozero's mock pin factory."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from gpiozero import DigitalOutputDevice

from openhal.drivers.base import DriverError
from openhal.drivers.rpi_gpio import watch_stop_button
from openhal.drivers.rpi_gpio.conformance import FILE
from openhal.drivers.rpi_gpio.driver import RpiGpioDriver
from openhal.drivers.rpi_gpio.simulator import mock_factory, pin_state, press, release
from openhal.kernel import Kernel
from openhal.kernel.commands import Write
from openhal.kernel.principals import human
from openhal.spec import loads, validate_path
from openhal.spec.models import DeviceFile

ROOT = Path(__file__).parents[3]
EXAMPLES = [*sorted((ROOT / "openhal" / "drivers" / "rpi_gpio" / "examples").glob("*.hal.yaml"))]
EXAMPLES.append(ROOT / "spec" / "examples" / "rpi-relay.hal.yaml")
WHO = human("tester")


def device(pins: str, channels: str, extra: str = "") -> DeviceFile:
    return loads(
        f"device: Pi\nid: pi\nconnect: {{ rpi-gpio: {pins}{extra} }}\n{channels}\nhazard: low\n"
        "confirmed: { by: t, at: 2026-10-24 }\n"
    )


def make(file: DeviceFile = FILE) -> tuple[RpiGpioDriver, Any]:
    factory = mock_factory()
    return RpiGpioDriver(file, pin_factory=factory), factory


async def kernel_for(driver: RpiGpioDriver) -> Kernel:
    kernel = Kernel()
    kernel.register(driver.device, driver)
    await kernel.connect(driver.device.device_id)
    return kernel


@pytest.mark.parametrize(
    ("pins", "message"),
    [("{ a: 17, b: 17 }", "more than once"), ("{ a: 28 }", "less than or equal to 27"), ("{ A: 4 }", "pattern")],
)
def test_bad_pins(pins: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        RpiGpioDriver(device(pins, "read:\n  x: { type: bool, map: { pin: 5 } }"))


@pytest.mark.parametrize(
    ("channels", "message"),
    [
        ("read:\n  a: { unit: V }", "GPIO inputs are bool"),
        ("write:\n  a: { type: enum, values: [x] }", "bool or number"),
        ("read:\n  ghost: { type: bool }", "has no pin"),
        ("read:\n  a: { type: bool }\n  b: { type: bool, map: { pin: 4 } }", "both use GPIO 4"),
        ("write:\n  a: { unit: V, min: 0, max: 1 }", "percent"),
        ("write:\n  a: { unit: percent, min: 0, max: 120 }", "go past what PWM can do"),
        ("write:\n  a: { unit: dimensionless, min: 0, max: 2 }", "0 to 1"),
        ("write:\n  a: { unit: percent, min: 0, max: 50, map: { mode: servo } }", "angle"),
        ("write:\n  a: { unit: degree, min: -100, max: 0, map: { mode: servo } }", "servo's range"),
        ("write:\n  a: { unit: degree, min: 0, max: 1, map: { mode: servo, min_angle: 5, max_angle: 0 } }", "below"),
        ("write:\n  a: { type: bool, map: { gpio: 4 } }", "Extra inputs"),
        ("actions:\n  go: {}", "no actions"),
    ],
)
def test_bad_maps(channels: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        RpiGpioDriver(device("{ a: 4 }", channels))


async def test_active_low_relay_and_connect_state() -> None:
    driver, factory = make()
    kernel = await kernel_for(driver)
    assert pin_state(factory, 17) == 1.0, "active-low outputs start inactive, which is a high pin"
    assert (await driver.read("relay")).value is False
    decision = await kernel.execute(Write(device="conformance-gpio", channel="relay", value=True), WHO)
    assert decision.status == "done", decision.message
    assert pin_state(factory, 17) == 0.0
    assert (await driver.read("relay")).value is True
    await driver.close()


async def test_keep_leaves_outputs_alone() -> None:
    file = device("{ lamp: 5 }", "write:\n  lamp: { type: bool }", ", on_connect: keep, pin_factory: mock")
    driver, factory = make(file)
    factory.pin(5).drive_high()
    await driver.connect()
    assert (await driver.read("lamp")).value is True


async def test_inputs_follow_the_pull_resistor() -> None:
    channels = (
        "read:\n"
        "  button: { type: bool }\n"
        "  sensor: { type: bool, map: { pull: down } }\n"
        "  open_drain: { type: bool, map: { pull: none, active_high: false } }"
    )
    driver, factory = make(device("{ button: 5, sensor: 6, open_drain: 13 }", channels))
    await driver.connect()
    assert (await driver.read("button")).value is False
    press(factory, 5)
    assert (await driver.read("button")).value is True
    release(factory, 5)
    assert (await driver.read("button")).value is False
    factory.pin(6).drive_high()
    assert (await driver.read("sensor")).value is True
    factory.pin(13).drive_low()
    assert (await driver.read("open_drain")).value is True


async def test_pwm_duty_in_percent_and_fraction() -> None:
    channels = (
        "write:\n"
        "  fan: { unit: percent, min: 0, max: 100, map: { active_high: true } }\n"
        "  led: { unit: dimensionless, min: 0, max: 1, map: { pin: 19, frequency: 500 } }"
    )
    driver, factory = make(device("{ fan: 18 }", channels))
    kernel = await kernel_for(driver)
    await kernel.execute(Write(device="pi", channel="fan", value="40 %"), WHO)
    await kernel.execute(Write(device="pi", channel="led", value="0.25 dimensionless"), WHO)
    assert pin_state(factory, 18) == pytest.approx(0.4)
    assert pin_state(factory, 19) == pytest.approx(0.25)
    assert factory.pin(19).frequency == 500
    assert (await driver.read("fan")).value == pytest.approx(40.0)
    assert (await driver.read("led")).value == pytest.approx(0.25)


async def test_servo_angles_and_units() -> None:
    channels = "write:\n  arm: { unit: radian, min: -0.5, max: 0.5, map: { mode: servo } }"
    driver, factory = make(device("{ arm: 12 }", channels))
    kernel = await kernel_for(driver)
    reading = await driver.read("arm")
    assert reading.value is None, "a servo with no pulse has no known angle"
    decision = await kernel.execute(Write(device="pi", channel="arm", value="0.5 radian"), WHO)
    assert decision.status == "done", decision.message
    assert (await driver.read("arm")).value == pytest.approx(0.5)
    pulse_ms = pin_state(factory, 12) * 20
    assert pulse_ms == pytest.approx(1.5 + 0.5 * (28.6479 / 90), rel=1e-3)


async def test_safe_state_through_the_kernel() -> None:
    driver, factory = make()
    kernel = await kernel_for(driver)
    for channel, value in (("relay", True), ("fan", "80 %")):
        await kernel.execute(Write(device="conformance-gpio", channel=channel, value=value), WHO)
    result = await kernel.stop_all(WHO, "test")
    assert result.devices[0].status == "safe"
    assert pin_state(factory, 17) == 1.0
    assert pin_state(factory, 18) == pytest.approx(1.0), "fan is active-low here, so 0 % is a high pin"


async def test_pins_held_elsewhere_fail_cleanly() -> None:
    driver, factory = make()
    holder = DigitalOutputDevice(18, pin_factory=factory)
    with pytest.raises(DriverError, match="Could not claim the GPIO pins"):
        await driver.connect()
    assert driver.devices == {}
    assert (await driver.health()).connected is False
    holder.close()
    await driver.connect()
    assert (await driver.health()).connected


async def test_released_pins_are_noticed() -> None:
    driver, _ = make()
    kernel = await kernel_for(driver)
    driver.devices["relay"].close()
    health = await driver.health()
    assert health.connected is False
    assert "relay" in health.detail
    with pytest.raises(DriverError, match="not claimed"):
        await driver.read("relay")
    decision = await kernel.execute(Write(device="conformance-gpio", channel="relay", value=True), WHO)
    assert decision.status in ("failed", "blocked")
    with pytest.raises(DriverError, match="no channel"):
        await driver.read("nope")


async def test_stop_button_calls_back_on_the_loop() -> None:
    factory = mock_factory()
    loop = asyncio.get_running_loop()
    pressed: list[str] = []
    done = asyncio.Event()

    async def stop() -> None:
        pressed.append("async")
        done.set()

    button = watch_stop_button(27, stop, loop=loop, bounce_s=None, pin_factory=factory)
    press(factory, 27)
    await asyncio.wait_for(done.wait(), 2)
    assert button.pressed
    release(factory, 27)
    button.close()
    plain = watch_stop_button(26, lambda: pressed.append("sync"), bounce_s=None, pin_factory=factory)
    press(factory, 26)
    assert pressed == ["async", "sync"]
    plain.close()
    threaded = watch_stop_button(25, lambda: pressed.append("loop"), loop=loop, bounce_s=None, pin_factory=factory)
    press(factory, 25)
    await asyncio.sleep(0.05)
    assert pressed[-1] == "loop"
    threaded.close()
    with pytest.raises(ValueError, match="BCM number"):
        watch_stop_button(40, stop)


def test_stop_button_pin_comes_from_unused_pins() -> None:
    assert RpiGpioDriver(FILE).stop_button_pin() == 27
    assert RpiGpioDriver(FILE).stop_button_pin("relay") is None


async def test_discover_reads_the_board_model(tmp_path: Path) -> None:
    model = tmp_path / "model"
    model.write_text("Raspberry Pi 5 Model B Rev 1.0\x00")
    found = await RpiGpioDriver.discover(model_file=model)
    assert [(item.address, item.label) for item in found] == [("local", "Raspberry Pi 5 Model B Rev 1.0")]
    model.write_text("Generic x86 board")
    assert await RpiGpioDriver.discover(model_file=model) == []
    assert await RpiGpioDriver.discover(model_file=tmp_path / "missing") == []


async def test_identify_and_describe() -> None:
    driver, _ = make()
    identity = await driver.identify()
    assert identity["pin_factory"] == "MockFactory"
    described = await driver.describe()
    assert described is not None
    assert "stop_button" in described["notes"]


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda path: path.name)
def test_examples_validate_and_load(path: Path) -> None:
    report = validate_path(path)
    assert report.ok, report.problems
    assert report.file is not None
    RpiGpioDriver(report.file)
