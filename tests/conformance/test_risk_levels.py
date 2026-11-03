"""Conformance for spec/v0.1/safety.md, Risk levels. One test for each level and each numbered rule."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from openhal.drivers.mock import MockDriver
from openhal.hub.config import HubConfig
from openhal.hub.hub import Hub
from openhal.kernel import Action, Kernel, Write, agent, human
from openhal.kernel.principals import Principal
from openhal.spec import loads, risk
from openhal.spec.loader import from_data, load
from openhal.writer.engine import force_suggested
from tests.kernel.conftest import AddDevice, FakeClock
from tests.kernel.conftest import add as add
from tests.kernel.conftest import clock as clock
from tests.kernel.conftest import kernel as kernel

AGENT = agent("claude", "control_medium")

BOARD = """
device: Bench board
id: board
connect: { mock: board }
read:
  supply: { unit: V }
write:
  brightness: { unit: percent, min: 0, max: 100, max_change_per_s: 10, suggested: true }
  fan_speed: { unit: percent, min: 0, max: 80, max_change_per_s: 20, suggested: true }
  heater: { unit: percent, min: 0, max: 100, suggested: true }
actions:
  ignite: { suggested: true }
safe_state: { brightness: 0, fan_speed: 0, heater: 0 }
provenance: { source: self-described }
"""


def file(**write: Any) -> Any:
    return from_data({"device": "Board", "connect": {"driver": "mock"}, "write": write})


def percent(**extra: Any) -> dict[str, Any]:
    return {"unit": "percent", "min": 0, "max": 100, **extra}


async def run(kernel: Kernel, command: Write | Action, who: Principal = AGENT) -> Any:
    return await kernel.execute(command, who)


def put(channel: str, value: str) -> Write:
    return Write(device="board", channel=channel, value=value)


async def test_level_low_writes_at_once_with_the_full_range_and_no_rate(kernel: Kernel, add: AddDevice) -> None:
    await add(BOARD, settle=0)
    assert (await run(kernel, put("brightness", "100 %"))).status == "done"


async def test_level_medium_writes_at_once_within_the_range_and_rate(
    kernel: Kernel, add: AddDevice, clock: FakeClock
) -> None:
    await add(BOARD, settle=0)
    clock.advance(1)
    assert (await run(kernel, put("fan_speed", "60 %"))).code == "rate_limited"
    assert (await run(kernel, put("fan_speed", "15 %"))).status == "done"


async def test_level_high_is_read_only_until_a_human_confirms(kernel: Kernel, add: AddDevice) -> None:
    await add(BOARD)
    assert (await run(kernel, put("heater", "10 %"))).code == "read_only_file"
    confirmed = BOARD.replace(
        "heater: { unit: percent, min: 0, max: 100, suggested: true }", "heater: { unit: percent, min: 0, max: 100 }"
    ).replace("ignite: { suggested: true }", "ignite: {}")
    other = Kernel(clock=FakeClock())
    done = loads(confirmed + "confirmed: { by: tester, at: 2026-11-03 }\n")
    other.register(done, MockDriver(done))
    await other.connect("board")
    held = await other.execute(Action(device="board", action="ignite"), AGENT)
    assert held.status == "pending", "a high action that can't be undone waits for a person at least once"


@pytest.mark.parametrize("source", ["manual", "sketch", "bridge", "hand-written"])
async def test_a_suggested_range_from_a_file_the_device_did_not_supply_waits_for_a_human(
    kernel: Kernel, add: AddDevice, source: str
) -> None:
    await add(BOARD.replace("source: self-described", f"source: {source}"), settle=0)
    blocked = await run(kernel, put("brightness", "10 %"))
    assert blocked.code == "read_only_file"
    assert "brightness on board has only suggested limits" in blocked.message
    assert (await run(kernel, put("fan_speed", "10 %"))).code == "read_only_file"


@pytest.mark.parametrize("source", ["self-described", "driver-describe", "library"])
async def test_a_suggested_range_from_the_device_or_the_library_takes_commands(
    kernel: Kernel, add: AddDevice, source: str
) -> None:
    await add(BOARD.replace("source: self-described", f"source: {source}"), settle=0)
    assert (await run(kernel, put("brightness", "10 %"))).status == "done"


def test_the_device_files_example_takes_commands_at_once() -> None:
    text = Path("spec/v0.1/device-files.md").read_text(encoding="utf-8")
    example = loads(text.split("```yaml\n", 1)[1].split("```", 1)[0])
    assert example.writable
    assert {item.level for item in risk.assess(example).values() if item.kind == "action"} == {"medium"}


async def test_every_level_keeps_stop_and_the_safe_state(kernel: Kernel, add: AddDevice) -> None:
    driver = await add(BOARD)
    assert (await run(kernel, put("brightness", "40 %"))).status == "done"
    report = await kernel.stop_all(AGENT, "test")
    assert [item.status for item in report.devices] == ["safe"]
    assert ("write", "brightness", 0.0) in driver.transport_log
    assert (await run(kernel, put("brightness", "10 %"))).code == "stopped"


def test_rule_1_reading_is_low() -> None:
    found = risk.assess(loads(BOARD + "hazard: high\n"))
    assert found["read:supply"].level == "low"


def test_rule_2_the_highest_rule_wins_and_medium_when_none_applies() -> None:
    assert risk.level(file(heater_led=percent()), "write:heater_led") == "high"
    assert risk.level(file(output=percent()), "write:output") == "medium"


def test_rule_3_no_device_names() -> None:
    first = file(output=percent())
    renamed = from_data(
        {"device": "Prusa MK4 by Shelly", "connect": {"driver": "mock"}, "write": {"output": percent()}}
    )
    assert risk.level(first, "write:output") == risk.level(renamed, "write:output")


def test_rule_4_at_least_the_hazard() -> None:
    assert (
        risk.level(
            from_data(
                {"device": "B", "connect": {"driver": "mock"}, "write": {"brightness": percent()}, "hazard": "high"}
            ),
            "write:brightness",
        )
        == "high"
    )


def test_rule_5_units_and_descriptions_only_raise() -> None:
    assert risk.level(file(brightness=percent(unit="dimensionless")), "write:brightness") == "medium"
    assert risk.level(file(brightness=percent(unit="mol")), "write:brightness") == "medium"
    enum = {"type": "enum", "values": ["led", "heat"]}
    assert risk.level(file(mode=enum), "write:mode") == "high"


def test_rule_6_one_pin_one_level() -> None:
    shared = file(heater=percent(map={"pin": 5}), pin5=percent(map={"pin": 5, "mode": "pwm"}))
    assert risk.level(shared, "write:pin5") == "high"
    lamp = from_data(
        {"device": "Lamp", "connect": {"driver": "mock"}, "write": {"pin6": percent(map={"pin": 6, "mode": "pwm"})}}
    )
    assert risk.level(lamp, "write:pin6") == "medium"


def test_rule_7_three_motion_axes_are_high() -> None:
    joints = {name: {"unit": "deg", "min": 0, "max": 90} for name in ("a", "b", "c")}
    assert {risk.level(file(**joints), f"write:{name}") for name in joints} == {"high"}


def test_rule_8_a_person_s_level_moves_either_way_and_a_tool_drops_the_person() -> None:
    lowered = file(heater={"type": "bool", "risk": {"level": "medium", "by": "owner", "at": "2026-11-03"}})
    assert risk.level(lowered, "write:heater") == "medium"
    unsigned = file(heater={"type": "bool", "risk": "low"})
    assert risk.level(unsigned, "write:heater") == "high"
    draft = {
        "device": "B",
        "connect": {"driver": "mock"},
        "write": {"heater": {"type": "bool", "risk": {"level": "low", "by": "x", "at": "2026-11-03"}}},
    }
    assert force_suggested(draft)["write"]["heater"]["risk"] == "low"


@pytest.fixture
async def hub(tmp_path: Path) -> AsyncIterator[Hub]:
    (tmp_path / "devices").mkdir()
    (tmp_path / "devices" / "board.hal.yaml").write_text('openhal: "0.1"\n' + BOARD.lstrip())
    hub = Hub(HubConfig(home=tmp_path), in_memory=True)
    await hub.start()
    yield hub
    await hub.close()


async def test_rule_9_raising_is_at_once_lowering_needs_a_person(hub: Hub) -> None:
    person = human("owner")
    raised = await hub.risk.request(person, "board", "brightness", "high")
    assert raised["status"] == "done"
    held = await hub.risk.request(person, "board", "brightness", "low")
    assert held["status"] == "pending"
    typed = await hub.risk.request(person, "board", "fan_speed", "low", phrase="confirm")
    assert typed["status"] == "done"
    refused = await hub.risk.request(AGENT, "board", "heater", "high")
    assert refused["code"] == "not_permitted"


async def test_rule_10_changes_are_audited_and_saved(hub: Hub) -> None:
    await hub.risk.request(human("owner"), "board", "brightness", "medium")
    assert [entry.status for entry in hub.audit.entries(event="risk_change")] == ["done"]
    saved = load(hub.config.devices_dir / "board.hal.yaml").write["brightness"].risk
    assert (saved.level, saved.by) == ("medium", "owner")
