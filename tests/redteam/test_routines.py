"""Attack family 7. Routines.

A routine runs through the same kernel as principal `routine:<id>`, so it can't confirm its own
commands. It can't touch a high hazard device without a human-signed approval bound to its content
hash, it can't be enabled by an agent on this default hub, changing it invalidates the approval,
and a stop pauses it. Loops are bounded by the run interval and the max runtime.
"""

from __future__ import annotations

from openhal.hub.hub import Hub
from openhal.kernel import agent, human
from openhal.routines.engine import RoutineError
from tests.redteam.conftest import writes

LASER_ROUTINE = """
id: fire-laser
steps:
  - write: { device: laser, channel: power, value: 20 % }
"""

FAN_ROUTINE = """
id: cool-room
steps:
  - write: { device: desk-fan, channel: fan_speed, value: 10 % }
"""

HEATER_ROUTINE = """
id: heat-cure
steps:
  - write: { device: heater, channel: power, value: 30 W }
"""


async def test_a_routine_cannot_drive_a_high_hazard_device_without_approval(hub: Hub) -> None:
    hub.routines.create(human(), "fire-laser", "yaml", LASER_ROUTINE)
    hub.routines.enable(human(), "fire-laser")
    run = await hub.routines.run("fire-laser", by=human())
    assert run.status == "blocked"
    assert "confirm" in run.message
    assert writes(hub, "laser") == []


async def test_an_agent_cannot_enable_a_routine_on_the_default_hub(hub: Hub) -> None:
    hub.routines.create(agent("claude", "control_low"), "cool-room", "yaml", FAN_ROUTINE)
    for who in (agent("claude", "control_low"), agent("claude", "control_medium")):
        caught = None
        try:
            hub.routines.enable(who, "cool-room")
        except RoutineError as exc:
            caught = exc
        assert caught is not None, f"{who.scope} agent enabled a routine"
    assert not hub.routines.get("cool-room").enabled


async def test_editing_a_routine_disables_it_and_breaks_its_approval(hub: Hub) -> None:
    record = hub.routines.create(human(), "fire-laser", "yaml", LASER_ROUTINE)
    approval = hub.kernel.approve_routine(human(), "laser", "fire-laser", record.sha256)
    hub.add_approval("laser", approval)
    hub.routines.enable(human(), "fire-laser")
    run = await hub.routines.run("fire-laser", by=human())
    assert run.status == "ok", run.message
    assert ("write", "power", 20.0) in writes(hub, "laser")

    edited = LASER_ROUTINE.replace("20 %", "30 %")
    changed = hub.routines.create(human(), "fire-laser", "yaml", edited, replace=True)
    assert not changed.enabled
    assert changed.sha256 != record.sha256
    hub.routines.enable(human(), "fire-laser")
    after = await hub.routines.run("fire-laser", by=human())
    assert after.status == "blocked", "the old approval must not cover the edited routine"


async def test_a_routine_is_blocked_while_the_hub_is_stopped(hub: Hub) -> None:
    hub.routines.create(human(), "cool-room", "yaml", FAN_ROUTINE)
    hub.routines.enable(human(), "cool-room")
    await hub.kernel.stop_all(human(), "operator stop")
    assert not hub.routines.get("cool-room").enabled
    caught = None
    try:
        await hub.routines.run("cool-room", by=human())
    except RoutineError as exc:
        caught = exc
    assert caught is not None
    assert writes(hub, "desk-fan") == [("write", "fan_speed", 0.0)] or writes(hub, "desk-fan") == []


async def test_a_routine_principal_is_blocked_by_the_stop_lock(hub: Hub) -> None:
    from openhal.kernel import Write
    from openhal.kernel import routine as routine_principal

    await hub.kernel.stop_all(human(), "operator stop")
    decision = await hub.kernel.execute(
        Write(device="desk-fan", channel="fan_speed", value="5 %"), routine_principal("ramp", "control_low")
    )
    assert (decision.status, decision.code) == ("blocked", "stopped")
    assert writes(hub, "desk-fan") == [("write", "fan_speed", 0.0)]


async def test_a_routine_cannot_create_or_enable_routines(hub: Hub) -> None:
    from openhal.kernel import routine as routine_principal

    caught = None
    try:
        hub.routines.create(routine_principal("evil"), "spawn", "yaml", FAN_ROUTINE)
    except RoutineError as exc:
        caught = exc
    assert caught is not None
    hub.routines.create(human(), "cool-room", "yaml", FAN_ROUTINE)
    blocked = None
    try:
        hub.routines.enable(routine_principal("cool-room"), "cool-room")
    except RoutineError as exc:
        blocked = exc
    assert blocked is not None


async def test_a_routine_loop_is_throttled_by_the_run_interval(hub: Hub) -> None:
    source = """
id: spin
triggers:
  - every: 1 s
steps:
  - write: { device: desk-fan, channel: fan_speed, value: 5 % }
"""
    hub.routines.create(human(), "spin", "yaml", source)
    record = hub.routines.get("spin")
    hub.routines.enable(human(), "spin")
    first = hub.routines.due(record, now=1000.0)
    assert first is not None
    hub.routines._last_start[record.id] = 1000.0
    assert hub.routines.due(record, now=1000.5) is None
    assert hub.routines.due(record, now=1001.5) is not None
