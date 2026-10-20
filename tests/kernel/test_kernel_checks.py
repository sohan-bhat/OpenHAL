"""Every kernel check in docs/SAFETY.md, in order, with its code and message."""

from __future__ import annotations

import pytest

from openhal.kernel import Action, Kernel, Write, agent, human, routine
from openhal.kernel.commands import Decision
from tests.kernel.conftest import FAN, HEATER, LASER, AddDevice, FakeClock

CLAUDE = agent("claude", "control_medium")
LOW = agent("low", "control_low")
READER = agent("reader", "read")


def fan(value: object) -> Write:
    return Write(device="desk-fan", channel="fan_speed", value=value)  # type: ignore[arg-type]


async def run(kernel: Kernel, command: Write | Action, who: object = CLAUDE) -> Decision:
    return await kernel.execute(command, who)  # type: ignore[arg-type]


async def test_allowed_write_reaches_driver(kernel: Kernel, add: AddDevice) -> None:
    driver = await add(FAN)
    decision = await run(kernel, fan("40 %"))
    assert decision.status == "done"
    assert decision.value == 40.0
    assert driver.hardware_writes() == [("write", "fan_speed", 40.0)]


@pytest.mark.parametrize(
    ("command", "code", "fragment"),
    [
        (Write(device="nope", channel="x", value="1 %"), "unknown_target", "no device"),
        (Write(device="desk-fan", channel="speed", value="1 %"), "unknown_target", "no write channel"),
        (Action(device="desk-fan", action="spin"), "unknown_target", "no action"),
    ],
)
async def test_check_1_shape(kernel: Kernel, add: AddDevice, command: Write | Action, code: str, fragment: str) -> None:
    driver = await add(FAN)
    decision = await run(kernel, command)
    assert (decision.status, decision.code) == ("blocked", code)
    assert fragment in decision.message
    assert driver.hardware_writes() == []


async def test_check_1_action_arguments(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN, settle=0)
    await add(HEATER)
    missing = await run(kernel, Action(device="heater", action="pulse"))
    assert missing.code == "bad_request"
    assert "missing arguments seconds" in missing.message
    extra = await run(kernel, Action(device="heater", action="pulse", args={"seconds": "2 s", "x": 1}))
    assert "unknown arguments x" in extra.message


async def test_check_2_stop_lock(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    driver = await add(FAN)
    await kernel.stop_all(CLAUDE, "test")
    decision = await run(kernel, fan("10 %"))
    assert decision.code == "stopped"
    assert [entry for entry in driver.hardware_writes() if entry[2] != 0.0] == []
    with pytest.raises(PermissionError):
        kernel.unlock(CLAUDE, "unlock")
    with pytest.raises(ValueError, match="Type unlock"):
        kernel.unlock(human(), "please")
    kernel.unlock(human(), "unlock")
    clock.advance(1)
    assert (await run(kernel, fan("10 %"))).status == "done"


async def test_check_3_read_only_file(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN.replace("confirmed: { by: tester, at: 2026-10-24 }", ""))
    decision = await run(kernel, fan("10 %"))
    assert decision.code == "read_only_file"
    assert "write.fan_speed" in decision.message


async def test_check_4_device_unavailable(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN, connect=False)
    decision = await run(kernel, fan("10 %"))
    assert decision.code == "device_unavailable"
    assert "not connected" in decision.message


async def test_check_5_scope(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN, settle=0)
    await add(HEATER)
    assert (await run(kernel, fan("10 %"), READER)).code == "not_permitted"
    assert (await run(kernel, Write(device="heater", channel="power", value="0 W"), LOW)).code == "not_permitted"
    assert (await run(kernel, fan("10 %"), LOW)).status == "done"


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (10, "bad_unit"),
        ("10", "bad_unit"),
        ("10 V", "bad_unit"),
        ("nan %", "bad_unit"),
        (True, "bad_unit"),
        ("101 %", "above_max"),
        ("-1 %", "below_min"),
        ("10.5 %", "bad_step"),
        ("1.5 dimensionless", "above_max"),
    ],
)
async def test_checks_6_to_9_values(kernel: Kernel, add: AddDevice, value: object, code: str) -> None:
    driver = await add(FAN)
    decision = await run(kernel, fan(value))
    assert decision.code == code, decision.message
    assert driver.hardware_writes() == []


async def test_typed_channels(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN, settle=0)
    await add(HEATER)
    assert (await run(kernel, Write(device="heater", channel="mode", value="turbo"))).code == "bad_value"
    assert (await run(kernel, Write(device="heater", channel="mode", value="eco"))).status == "done"
    assert (await run(kernel, Write(device="heater", channel="enabled", value="yes"))).code == "bad_value"
    assert (await run(kernel, Write(device="heater", channel="enabled", value=True))).status == "done"
    assert (await run(kernel, Write(device="heater", channel="label", value="toolongvalue"))).code == "bad_value"
    assert (await run(kernel, Write(device="heater", channel="label", value="NOPE"))).code == "bad_value"
    assert (await run(kernel, Write(device="heater", channel="label", value=3))).code == "bad_value"
    assert (await run(kernel, Write(device="heater", channel="label", value="ok"))).status == "done"


async def test_check_6_converts_units(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN, settle=0)
    await add(HEATER)
    await run(kernel, fan("40 %"))
    decision = await run(kernel, Write(device="heater", channel="power", value="0.05 kW"))
    assert decision.status == "done"
    assert decision.value == pytest.approx(50.0)


async def test_check_10_rate(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    driver = await add(FAN)
    assert (await run(kernel, fan("20 %"))).status == "done"
    blocked = await run(kernel, fan("60 %"))
    assert blocked.code == "rate_limited"
    assert "possible in 2.0 s" in blocked.message
    clock.advance(1.0)
    assert (await run(kernel, fan("40 %"))).status == "done"
    clock.advance(0.5)
    assert (await run(kernel, fan("51 %"))).code == "rate_limited"
    assert (await run(kernel, fan("50 %"))).status == "done"
    assert [entry[2] for entry in driver.hardware_writes()] == [20.0, 40.0, 50.0]


async def test_check_10_first_write_uses_safe_state(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN, settle=1.0)
    assert (await run(kernel, fan("30 %"))).code == "rate_limited"
    assert (await run(kernel, fan("20 %"))).status == "done"


async def test_check_10_uses_latest_reading(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    driver = await add(FAN)
    driver.values["fan_speed"] = 80.0
    await kernel.read("desk-fan", "fan_speed", CLAUDE)
    clock.advance(1.0)
    assert (await run(kernel, fan("100 %"))).status == "done"


async def test_check_11_interlock_across_devices(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    await add(FAN, settle=0)
    heater = await add(HEATER)
    blocked = await run(kernel, Write(device="heater", channel="power", value="20 W"))
    assert blocked.code == "interlock"
    assert "fan at 30 %" in blocked.message
    for speed in ("20 %", "40 %"):
        await run(kernel, fan(speed))
        clock.advance(1)
    assert (await run(kernel, Write(device="heater", channel="power", value="20 W"))).status == "done"
    clock.advance(1)
    slow = await run(kernel, fan("20 %"))
    assert slow.code == "interlock", "lowering the fan below 30 % must be blocked while the heater is on"
    assert (await run(kernel, Write(device="heater", channel="power", value="0 W"))).status == "done"
    assert (await run(kernel, fan("20 %"))).status == "done"
    assert heater.hardware_writes() == [("write", "power", 20.0), ("write", "power", 0.0)]


async def test_check_11_unknown_blocks(kernel: Kernel, add: AddDevice) -> None:
    await add(HEATER)
    decision = await run(kernel, Write(device="heater", channel="power", value="10 W"))
    assert decision.code == "misconfigured", "its interlock names desk-fan, which isn't registered (F17)"
    assert "isn't registered" in decision.message


async def test_check_11_action_preconditions(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN, settle=0)
    await add(HEATER)
    blocked = await run(kernel, Action(device="heater", action="pulse", args={"seconds": "2 s"}), human())
    assert blocked.code == "interlock"
    assert "enabled == true" in blocked.message
    await run(kernel, Write(device="heater", channel="enabled", value=True))
    assert (
        await run(kernel, Action(device="heater", action="pulse", args={"seconds": "2 s"}), human())
    ).status == "done"


async def test_check_11_action_effects_count_as_unknown(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN, settle=0)
    await add(HEATER)
    decision = await run(kernel, Action(device="heater", action="purge"), human())
    assert decision.code == "interlock", "purge may change power, so the fan interlock must hold first"


async def test_check_12_duration_budget(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    await add(FAN, settle=0)
    heater = await add(HEATER)
    for speed in ("20 %", "40 %"):
        await run(kernel, fan(speed))
        clock.advance(1)
    assert (await run(kernel, Write(device="heater", channel="power", value="50 W"))).status == "done"
    assert await kernel.tick() == []
    clock.advance(61)
    fired = await kernel.tick()
    assert fired == ["heater: power > 40 W"]
    assert heater.values["power"] == 0.0, "the rule's default action is the safe state"
    again = await run(kernel, Write(device="heater", channel="power", value="45 W"))
    assert again.code == "duration_exceeded"
    assert (await run(kernel, Write(device="heater", channel="power", value="30 W"))).status == "done"
    await kernel.tick()
    clock.advance(31)
    await kernel.tick()
    assert (await run(kernel, Write(device="heater", channel="power", value="45 W"))).status == "done"


async def test_check_14_confirm_tier_and_window(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    await add(FAN, settle=0)
    heater = await add(HEATER)
    await run(kernel, Write(device="heater", channel="enabled", value=True))
    pending = await run(kernel, Action(device="heater", action="pulse", args={"seconds": "2 s"}))
    assert pending.status == "pending"
    assert pending.request_id
    assert heater.hardware_writes() == [("write", "enabled", True)]
    with pytest.raises(PermissionError):
        await kernel.confirm(pending.request_id, CLAUDE)
    done = await kernel.confirm(pending.request_id, human())
    assert done.status == "done"
    repeat = await run(kernel, Action(device="heater", action="pulse", args={"seconds": "2 s"}))
    assert repeat.status == "done", "confirm tier lets an identical repeat through for 10 minutes"
    other = await run(kernel, Action(device="heater", action="pulse", args={"seconds": "3 s"}))
    assert other.status == "pending"
    clock.advance(601)
    assert (await run(kernel, Action(device="heater", action="pulse", args={"seconds": "2 s"}))).status == "pending"


async def fan_up(kernel: Kernel, clock: FakeClock) -> None:
    for speed in ("20 %", "40 %"):
        await run(kernel, fan(speed))
        clock.advance(1)


async def test_check_14_each_time_and_expiry(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    await add(FAN, settle=0)
    await add(HEATER)
    await fan_up(kernel, clock)
    first = await run(kernel, Action(device="heater", action="purge"))
    assert first.status == "pending"
    clock.advance(301)
    with pytest.raises(LookupError, match="expired"):
        await kernel.confirm(first.request_id or "", human())


async def test_check_14_rejection(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    await add(FAN, settle=0)
    await add(HEATER)
    await fan_up(kernel, clock)
    pending = await run(kernel, Action(device="heater", action="purge"))
    with pytest.raises(PermissionError):
        kernel.reject(pending.request_id or "", CLAUDE)
    kernel.reject(pending.request_id or "", human(), "not now")
    with pytest.raises(LookupError):
        await kernel.confirm(pending.request_id or "", human())


async def test_confirmation_reevaluates(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN, settle=0)
    await add(HEATER)
    await run(kernel, Write(device="heater", channel="enabled", value=True))
    pending = await run(kernel, Action(device="heater", action="pulse", args={"seconds": "2 s"}))
    await run(kernel, Write(device="heater", channel="enabled", value=False))
    decision = await kernel.confirm(pending.request_id or "", human())
    assert decision.code == "interlock", "an approval must not run a command that is no longer safe"


async def test_high_hazard_always_queues(kernel: Kernel, add: AddDevice) -> None:
    laser = await add(LASER, initial={"door_closed": True})
    await kernel.read("laser", "door_closed", CLAUDE)
    first = await run(kernel, Write(device="laser", channel="power", value="10 %"))
    assert first.status == "pending"
    assert (await run(kernel, Write(device="laser", channel="power", value="10 %"), LOW)).code == "not_permitted"
    assert (await kernel.confirm(first.request_id or "", human())).status == "done"
    second = await run(kernel, Write(device="laser", channel="power", value="10 %"))
    assert second.status == "pending", "high hazard never gets an approval window"
    assert laser.hardware_writes() == [("write", "power", 10.0)]


async def test_routines_and_confirmation(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN, settle=0)
    await add(HEATER)
    worker = routine("night", "control_medium")
    await run(kernel, Write(device="heater", channel="enabled", value=True))
    decision = await run(kernel, Action(device="heater", action="pulse", args={"seconds": "2 s"}), worker)
    assert decision.code == "needs_confirmation"
    assert decision.status == "blocked"
    assert (await run(kernel, fan("10 %"), worker)).status == "done"


async def test_routine_on_high_hazard_needs_signed_approval(kernel: Kernel, add: AddDevice) -> None:
    laser_text = LASER
    await add(laser_text, initial={"door_closed": True})
    await kernel.read("laser", "door_closed", CLAUDE)
    sha = "a" * 64
    worker = routine("engrave", "control_medium", sha)
    assert (await run(kernel, Write(device="laser", channel="power", value="5 %"), worker)).code == "needs_confirmation"
    with pytest.raises(PermissionError):
        kernel.approve_routine(CLAUDE, "laser", "engrave", sha)
    approval = kernel.approve_routine(human("sohan"), "laser", "engrave", sha)
    runtime = kernel.devices["laser"]
    data = runtime.file.model_dump(by_alias=True, exclude={"extensions"})
    data["approvals"] = [approval.model_dump()]
    runtime.file = type(runtime.file).model_validate(data)
    assert (await run(kernel, Write(device="laser", channel="power", value="5 %"), worker)).status == "done"
    changed = routine("engrave", "control_medium", "b" * 64)
    assert (
        await run(kernel, Write(device="laser", channel="power", value="5 %"), changed)
    ).code == "needs_confirmation"
    forged = approval.model_copy(update={"signature": "0" * 64})
    data["approvals"] = [forged.model_dump()]
    runtime.file = type(runtime.file).model_validate(data)
    assert (await run(kernel, Write(device="laser", channel="power", value="5 %"), worker)).code == "needs_confirmation"


async def test_human_is_the_confirmer(kernel: Kernel, add: AddDevice) -> None:
    await add(LASER, initial={"door_closed": True})
    await kernel.read("laser", "door_closed", human())
    assert (await run(kernel, Write(device="laser", channel="power", value="5 %"), human())).status == "done"


async def test_session_limits_only_tighten(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    from openhal.kernel.checks import Block

    await add(FAN)
    kernel.tighten(CLAUDE, "desk-fan", "fan_speed", max="15 %")
    assert (await run(kernel, fan("20 %"))).code == "above_max"
    assert (await run(kernel, fan("20 %"), LOW)).status == "done", "session limits apply to one principal only"
    with pytest.raises(Block, match="only be tightened"):
        kernel.tighten(CLAUDE, "desk-fan", "fan_speed", max="50 %")
    with pytest.raises(Block, match="only be tightened"):
        kernel.tighten(CLAUDE, "desk-fan", "fan_speed", rate="50 %/s")
    with pytest.raises(Block):
        kernel.tighten(CLAUDE, "desk-fan", "fan_speed", min="-5 %")
    with pytest.raises(Block):
        kernel.tighten(CLAUDE, "desk-fan", "fan_speed", min="10 V")
    kernel.tighten(CLAUDE, "desk-fan", "fan_speed", rate="5 %/s")
    clock.advance(1)
    assert (await run(kernel, fan("10 %"), CLAUDE)).code == "rate_limited"
    assert (await run(kernel, fan("15 %"), CLAUDE)).status == "done"


async def test_dry_run_sees_earlier_steps(kernel: Kernel, add: AddDevice) -> None:
    driver = await add(FAN, settle=0)
    heater = await add(HEATER)
    plan = [fan("20 %"), fan("21 %"), fan("101 %"), Write(device="heater", channel="power", value="10 W")]
    decisions = kernel.dry_run(plan, CLAUDE)
    assert [decision.code for decision in decisions] == [None, "rate_limited", "above_max", "interlock"]
    assert "desk-fan.fan_speed >= 30 %" in decisions[3].message, "later steps see the fan at 20 % from step one"
    assert driver.hardware_writes() == []
    assert heater.hardware_writes() == []


async def test_driver_failure_is_reported(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN, fail_writes=True)
    decision = await run(kernel, fan("10 %"))
    assert decision.status == "failed"
    assert decision.code == "driver_error"


async def test_connection_loss_applies_safe_state(kernel: Kernel, add: AddDevice) -> None:
    driver = await add(FAN)
    await run(kernel, fan("20 %"))
    await kernel.connection_lost("desk-fan", "heartbeat missed")
    assert (await run(kernel, fan("10 %"))).code == "device_unavailable"
    assert driver.transport_log[-1][0] == "write"
    assert driver.values["fan_speed"] == 0.0


async def test_reads_are_logged_and_checked(kernel: Kernel, add: AddDevice) -> None:
    from openhal.drivers.base import DriverError

    await add(FAN)
    reading = await kernel.read("desk-fan", "temperature", READER)
    assert reading.unit == "degC"
    with pytest.raises(LookupError):
        await kernel.read("desk-fan", "pressure", READER)
    entries = kernel.audit.entries(event="read")
    assert [entry.status for entry in entries] == ["blocked", "done"]
    await kernel.connection_lost("desk-fan", "gone")
    with pytest.raises(DriverError):
        await kernel.read("desk-fan", "temperature", READER)
