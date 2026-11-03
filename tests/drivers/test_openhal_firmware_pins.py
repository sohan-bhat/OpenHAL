"""Every pin of an OpenHAL board, from its description to the kernel, on the simulated bare board."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.openhal_firmware import protocol
from openhal.drivers.openhal_firmware.driver import OpenHalFirmwareDriver
from openhal.drivers.openhal_firmware.simulator import SIMULATORS, BareBoardSimulator, SimTransport
from openhal.kernel import Kernel, Write, agent
from openhal.service import devices
from openhal.spec import risk
from openhal.spec.loader import from_data
from openhal.spec.models import DeviceFile

AGENT = agent("claude", "control_medium")


@pytest.fixture(autouse=True)
def fresh() -> None:
    SIMULATORS.pop("bare-board", None)


async def described() -> dict[str, Any]:
    data = await devices.describe("openhal-firmware", "sim:bare-board")
    SIMULATORS.pop("bare-board", None)
    return data


@pytest.fixture
async def board() -> AsyncIterator[tuple[Kernel, DeviceFile, BareBoardSimulator]]:
    file = from_data(await described())
    kernel = Kernel()
    driver = OpenHalFirmwareDriver(file)
    kernel.register(file, driver)
    await kernel.connect(file.device_id)
    simulator = SIMULATORS["bare-board"]
    assert isinstance(simulator, BareBoardSimulator)
    yield kernel, file, simulator
    await driver.close()


def test_the_description_lists_pins_and_their_modes() -> None:
    sections = protocol.description_to_sections(BareBoardSimulator().description())
    assert sections["write"]["pin4"] == {"type": "bool", "map": {"pin": 4, "mode": "out"}, "suggested": True}
    assert sections["write"]["pin4_pwm"]["map"] == {"pin": 4, "mode": "pwm"}
    assert sections["write"]["pin4_mode"]["values"] == ["input", "input_pullup", "output", "pwm"]
    assert sections["write"]["pin16_mode"]["values"] == ["input", "output", "pwm"]
    assert sections["read"]["pin17_analog"] == {"unit": "percent", "range": [0, 100], "map": {"pin": 17, "mode": "adc"}}
    assert "pin2" not in sections["write"], "the LED's pin belongs to brightness"
    assert sections["write"]["brightness"]["map"] == {"pin": 2}
    assert "8 free pins" in sections["notes"]


@pytest.mark.parametrize(
    "pins",
    [
        [[4, "iz"]],
        [[4, ""]],
        [["4", "io"]],
        [[4, "io"], [4, "io"]],
        [[999, "io"]],
        "4:io",
    ],
)
def test_a_bad_pin_list_is_refused(pins: Any) -> None:
    with pytest.raises(protocol.ProtocolError):
        protocol.parse_description(json.dumps({"p": "x", "io": pins}))


def test_bad_pin_numbers_on_channels_and_bits_are_refused() -> None:
    with pytest.raises(protocol.ProtocolError, match="bad pin"):
        protocol.parse_description('{"p": "x", "r": [{"n": "a", "u": "V", "g": -1}]}')
    with pytest.raises(protocol.ProtocolError, match="bits"):
        protocol.parse_description('{"p": "x", "pb": 40}')


async def test_a_fresh_bare_board_gives_a_low_led_and_medium_pins() -> None:
    file = from_data(await described())
    levels = risk.assess(file)
    assert levels["write:brightness"].level == "low"
    assert not risk.own_rate(file, "brightness"), "the board's suggested rate doesn't cap a low LED"
    assert {levels[f"write:pin{pin}{tail}"].level for pin in (4, 5, 16) for tail in ("", "_mode")} == {"medium"}
    assert levels["read:pin17_analog"].level == "low"
    assert file.writable


async def test_an_agent_sets_a_raw_pwm_pin_and_a_stop_releases_it(
    board: tuple[Kernel, DeviceFile, BareBoardSimulator],
) -> None:
    kernel, file, simulator = board
    done = await kernel.execute(Write(device=file.device_id, channel="pin5_pwm", value=40, unit="%"), AGENT, wire=True)
    assert done.status == "done", done.message
    assert (simulator.pin_state[5], round(simulator.pin_value[5], 1)) == ("pwm", 40.0)
    mode = await kernel.read(file.device_id, "pin5_mode", AGENT)
    assert mode.value == "pwm"
    on = await kernel.execute(Write(device=file.device_id, channel="pin12", value=True), AGENT, wire=True)
    assert on.status == "done", on.message
    assert simulator.pin_state[12] == "out"
    report = await kernel.stop_all(AGENT, "test")
    assert [item.status for item in report.devices] == ["safe"]
    assert simulator.pin_state == {5: "in", 12: "in"}


async def test_mode_changes_and_analog_reads(board: tuple[Kernel, DeviceFile, BareBoardSimulator]) -> None:
    kernel, file, simulator = board
    simulator.pin_inputs[13] = 1
    pullup = await kernel.execute(Write(device=file.device_id, channel="pin13_mode", value="input_pullup"), AGENT)
    assert pullup.status == "done", pullup.message
    assert (await kernel.read(file.device_id, "pin13", AGENT)).value is True
    simulator.pin_inputs[17] = 25.0
    assert (await kernel.read(file.device_id, "pin17_analog", AGENT)).value == 25.0
    output = await kernel.execute(Write(device=file.device_id, channel="pin14_mode", value="output"), AGENT)
    assert output.status == "done"
    assert (await kernel.read(file.device_id, "pin14_pwm", AGENT)).value == 0.0


async def test_the_board_blocks_what_the_hub_never_sends() -> None:
    simulator = BareBoardSimulator()
    transport = SimTransport(simulator)
    await transport.connect()
    replies = []
    for seq, words in enumerate(
        [
            ("2", "out", "1"),
            ("5", "pwm", "150"),
            ("5", "out", "0.5"),
            ("17", "out", "1"),
            ("5", "dance"),
            ("5", "pwm"),
            ("x", "get"),
        ],
        start=1,
    ):
        await transport.write_line(protocol.encode(seq, "PIN", *words))
        replies.append(protocol.decode(await transport.read_line()).args)
    await transport.write_line(protocol.encode(9, "PIN", "5", "out", "1"))
    await transport.read_line()
    await transport.write_line(protocol.encode(10, "PIN", "5", "adc"))
    replies.append(protocol.decode(await transport.read_line()).args)
    assert replies == [
        ("unknown", "pin"),
        ("limit", "pin", "max", "100"),
        ("format", "pin"),
        ("unknown", "pin_mode"),
        ("format", "pin"),
        ("format", "pin"),
        ("unknown", "pin"),
        ("unknown", "pin_mode"),
    ]


async def test_a_pin_the_board_reports_garbled_is_a_driver_error(
    board: tuple[Kernel, DeviceFile, BareBoardSimulator],
) -> None:
    kernel, file, _simulator = board
    runtime = kernel.devices[file.device_id]
    driver = runtime.driver
    assert isinstance(driver, OpenHalFirmwareDriver)
    with pytest.raises(DriverError, match="doesn't take"):
        await driver._pin_write("pin5_pwm", 5, "pwm", "half")
    with pytest.raises(DriverError, match="takes input"):
        await driver._pin_write("pin5_mode", 5, "mode", "sideways")
