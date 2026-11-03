"""The kernel's checks by risk level (docs/SAFETY.md, ADR 0023). Low, medium and high, and what stays at every level."""

from __future__ import annotations

from openhal.kernel import Action, Kernel, Write, agent, human
from openhal.kernel.commands import Decision
from openhal.kernel.principals import Principal
from tests.kernel.conftest import AddDevice, FakeClock

AGENT = agent("claude", "control_medium")
LOW = agent("low", "control_low")

BOARD = """
device: Bench board
id: board
connect: { mock: board }
read:
  uptime: { unit: s }
write:
  brightness: { unit: percent, min: 0, max: 100, max_change_per_s: 25, suggested: true }
  fan_speed: { unit: percent, min: 0, max: 80, max_change_per_s: 20, suggested: true }
  heater: { unit: percent, min: 0, max: 100, suggested: true }
actions:
  ignite: { suggested: true }
safe_state: { brightness: 0, fan_speed: 0, heater: 0 }
provenance: { source: self-described }
"""

KILN = """
device: Kiln
id: kiln
connect: { mock: kiln }
write:
  element: { type: bool }
  vent: { type: bool, confirm: confirm }
actions:
  fire: {}
  vent_open: { effects: [vent] }
  off: {}
safe_state: [{ element: false, vent: false }, { action: off }]
hazard: medium
confirmed: { by: tester, at: 2026-11-03 }
"""


def put(channel: str, value: object, device: str = "board") -> Write:
    return Write(device=device, channel=channel, value=value)  # type: ignore[arg-type]


async def run(kernel: Kernel, command: Write | Action, who: Principal = AGENT) -> Decision:
    return await kernel.execute(command, who)


async def test_low_writes_at_once_with_the_full_range_and_no_rate(kernel: Kernel, add: AddDevice) -> None:
    driver = await add(BOARD, settle=0)
    assert (await run(kernel, put("brightness", "100 %"))).status == "done"
    assert (await run(kernel, put("brightness", "0 %"))).status == "done"
    assert driver.transport_log[-1] == ("write", "brightness", 0.0)


async def test_medium_writes_at_once_within_the_device_range_and_rate(
    kernel: Kernel, add: AddDevice, clock: FakeClock
) -> None:
    await add(BOARD, settle=0)
    assert (await run(kernel, put("fan_speed", "90 %"))).code == "above_max"
    clock.advance(1)
    assert (await run(kernel, put("fan_speed", "60 %"))).code == "rate_limited"
    assert (await run(kernel, put("fan_speed", "20 %"))).status == "done"


async def test_high_is_read_only_until_a_person_confirms(kernel: Kernel, add: AddDevice) -> None:
    await add(BOARD)
    blocked = await run(kernel, put("heater", "10 %"))
    assert blocked.code == "read_only_file"
    assert "heater on board is high risk" in blocked.message
    assert (await run(kernel, Action(device="board", action="ignite"))).code == "read_only_file"
    assert (await run(kernel, put("heater", "10 %"), human())).code == "read_only_file"
    assert (await run(kernel, put("brightness", "10 %"))).status == "done"


async def test_a_person_set_rate_applies_to_a_low_channel(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    await add(BOARD.replace("max_change_per_s: 25, suggested: true", "max_change_per_s: 25"), settle=0)
    clock.advance(1)
    assert (await run(kernel, put("brightness", "100 %"))).code == "rate_limited"


async def test_a_session_rate_still_applies_to_a_low_channel(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    await add(BOARD, settle=0)
    assert kernel.tighten(AGENT, "board", "brightness", rate="50 %/s") == {"rate": 50.0}
    clock.advance(1)
    assert (await run(kernel, put("brightness", "100 %"))).code == "rate_limited"


async def test_a_low_target_needs_only_a_low_scope(kernel: Kernel, add: AddDevice) -> None:
    await add(BOARD)
    assert (await run(kernel, put("brightness", "10 %"), LOW)).status == "done"
    blocked = await run(kernel, put("fan_speed", "10 %"), LOW)
    assert blocked.code == "not_permitted"
    assert "board is medium hazard" in blocked.message


async def test_a_lowered_target_on_a_high_device_still_needs_its_scope(kernel: Kernel, add: AddDevice) -> None:
    lowered = BOARD.replace(
        "fan_speed: { unit: percent, min: 0, max: 80, max_change_per_s: 20, suggested: true }",
        "fan_speed: { unit: percent, min: 0, max: 80, risk: { level: medium, by: owner, at: 2026-11-03 } }",
    )
    await add(lowered + "hazard: high\n")
    blocked = await run(kernel, put("fan_speed", "10 %"), LOW)
    assert blocked.code == "not_permitted"
    assert "fan_speed is medium risk" in blocked.message
    held = await run(kernel, put("fan_speed", "10 %"))
    assert held.status == "pending", "a high hazard device holds every command each time"


async def test_a_high_action_that_cant_be_undone_waits_for_a_person(kernel: Kernel, add: AddDevice) -> None:
    driver = await add(KILN)
    first = await run(kernel, Action(device="kiln", action="fire"))
    assert first.status == "pending"
    assert first.request_id is not None
    assert (await kernel.confirm(first.request_id, human())).status == "done"
    assert (await run(kernel, Action(device="kiln", action="fire"))).status == "done", "one approval covers repeats"
    assert (await run(kernel, Action(device="kiln", action="off"))).status == "done"
    assert (await run(kernel, Action(device="kiln", action="vent_open"))).status == "done"
    assert (await run(kernel, put("element", True, "kiln"))).status == "done"
    ran = [name for kind, name, _ in driver.transport_log if kind == "action"]
    assert ran == ["fire", "fire", "off", "vent_open"]


async def test_stop_works_at_every_level(kernel: Kernel, add: AddDevice) -> None:
    driver = await add(BOARD)
    assert (await run(kernel, put("brightness", "40 %"))).status == "done"
    report = await kernel.stop_all(LOW, "test")
    assert [item.status for item in report.devices] == ["safe"]
    assert ("write", "brightness", 0.0) in driver.transport_log
    assert (await run(kernel, put("brightness", "10 %"))).code == "stopped"
    entries = kernel.audit.entries(device="board", event="write", limit=10)
    assert any(entry.status == "done" for entry in entries)
