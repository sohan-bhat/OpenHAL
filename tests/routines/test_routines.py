"""The routine engine. Validation, enabling rules, runs through the kernel, triggers and stop."""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from openhal.hub.config import HubConfig, RoutineSettings
from openhal.hub.hub import Hub
from openhal.kernel import agent, human
from openhal.routines.engine import RoutineEngine, RoutineError, parse
from openhal.routines.models import content_sha256
from openhal.spec import loads
from tests.kernel.conftest import FAN, LASER, FakeClock

KEEP_COOL = """
id: keep-cool
description: Run the fan harder when the room is warm.
triggers:
  - every: 30 s
  - when: "desk-fan.temperature > 28 degC"
steps:
  - if: "desk-fan.temperature > 28 degC"
    then:
      - write: { device: desk-fan, channel: fan_speed, value: 20 % }
    else:
      - write: { device: desk-fan, channel: fan_speed, value: 10 % }
  - log: checked the fan
"""

TOO_FAST = """
id: too-fast
steps:
  - write: { device: desk-fan, channel: fan_speed, value: 20 % }
  - write: { device: desk-fan, channel: fan_speed, value: 90 % }
  - write: { device: desk-fan, channel: fan_speed, value: 30 % }
"""

PYTHON = """
TRIGGERS = [{"every": "60 s"}]

async def run(ctx):
    temperature = await ctx.read("desk-fan", "temperature")
    ctx.log(f"temperature {temperature}")
    await ctx.write("desk-fan", "fan_speed", "15 %")
    await ctx.wait("0 s")
    assert ctx.value("desk-fan.fan_speed == 15 %") is True
"""


@pytest.fixture
async def hub(tmp_path: Path) -> AsyncIterator[Hub]:
    clock = FakeClock()
    hub = Hub(HubConfig(home=tmp_path, routines=RoutineSettings(min_interval_s=0.1)), clock=clock, in_memory=True)
    hub.add_device(
        loads(FAN.replace("connect: { mock: fan }", "connect: { mock: fan, initial: { temperature: 31.0 } }"))
    )
    await hub.start(load_devices=False)
    clock.advance(60)
    yield hub
    await hub.close()


def engine(hub: Hub) -> RoutineEngine:
    return hub.routines


async def test_yaml_routine_runs_through_the_kernel(hub: Hub) -> None:
    routines = engine(hub)
    record = routines.create(agent("claude", "control_low"), "keep-cool", "yaml", KEEP_COOL)
    assert not record.enabled
    assert routines.summary(record)["devices"] == ["desk-fan"]
    assert routines.summary(record)["triggers"] == ["every 30 s", "when desk-fan.temperature > 28 degC"]
    with pytest.raises(RoutineError, match="Only a human can enable"):
        routines.enable(agent("claude", "control_low"), "keep-cool")
    routines.enable(human(), "keep-cool")
    await hub.kernel.read("desk-fan", "temperature", human())
    run = await routines.run("keep-cool", by=human())
    assert run.status == "ok", run.message
    assert hub.kernel.devices["desk-fan"].driver.values["fan_speed"] == 20.0  # type: ignore[attr-defined]
    assert {"log": "checked the fan"} in run.steps
    assert routines.history("keep-cool")[0]["status"] == "ok"
    principals = {entry.principal for entry in hub.audit.entries(event="write")}
    assert principals == {"routine:keep-cool"}


async def test_blocked_steps_stop_the_run(hub: Hub) -> None:
    routines = engine(hub)
    routines.create(human(), "too-fast", "yaml", TOO_FAST)
    routines.enable(human(), "too-fast")
    run = await routines.run("too-fast", by=human())
    assert run.status == "blocked"
    assert "may change by 20 % per second" in run.message
    assert len([step for step in run.steps if step.get("status") == "done"]) == 1


async def test_continue_on_block(hub: Hub) -> None:
    routines = engine(hub)
    routines.create(human(), "too-fast", "yaml", TOO_FAST + "on_block: continue\n")
    routines.enable(human(), "too-fast")
    run = await routines.run("too-fast", by=human())
    assert run.status == "ok"
    assert [step.get("status") for step in run.steps] == ["done", "blocked", "blocked"]


async def test_dry_run_covers_every_branch(hub: Hub) -> None:
    routines = engine(hub)
    routines.create(human(), "too-fast", "yaml", TOO_FAST)
    result = routines.dry_run("too-fast")
    assert [item["step"] for item in result["decisions"]] == ["steps[0]", "steps[1]", "steps[2]"]
    assert [item["code"] for item in result["decisions"]] == [None, "rate_limited", "rate_limited"]
    assert not result["ok"]
    paced = TOO_FAST.replace(
        "  - write: { device: desk-fan, channel: fan_speed, value: 90 % }",
        "  - wait: 4 s\n  - write: { device: desk-fan, channel: fan_speed, value: 90 % }\n  - wait: 3 s",
    ).replace("id: too-fast", "id: paced")
    routines.create(human(), "paced", "yaml", paced)
    assert routines.dry_run("paced")["ok"], "waits advance the simulated clock"
    routines.create(human(), "keep-cool", "yaml", KEEP_COOL)
    branches = routines.dry_run("keep-cool")
    assert [item["step"] for item in branches["decisions"]] == ["steps[0].then[0]", "steps[0].else[0]"]
    assert branches["ok"]
    routines.create(human(), "py", "python", PYTHON)
    assert routines.dry_run("py")["problems"]


async def test_python_routine(hub: Hub) -> None:
    routines = engine(hub)
    record = routines.create(human(), "py", "python", PYTHON)
    assert routines.summary(record)["triggers"] == ["every 60 s"]
    with pytest.raises(RoutineError, match="Only a human can enable"):
        routines.enable(agent("claude", "control_low"), "py")
    routines.enable(human(), "py")
    run = await routines.run("py", by=human())
    assert run.status == "ok", run.message
    assert run.steps[0]["log"].startswith("temperature")


async def test_python_routine_failures(hub: Hub) -> None:
    routines = engine(hub)
    routines.create(human(), "boom", "python", "async def run(ctx):\n    raise ValueError('nope')\n")
    assert (await routines.run("boom", by=human())).status == "failed"
    routines.create(
        human(), "blocked", "python", "async def run(ctx):\n    await ctx.write('desk-fan', 'fan_speed', '500 %')\n"
    )
    run = await routines.run("blocked", by=human())
    assert run.status == "blocked"
    assert "limit is 100 %" in run.message


async def test_validation_errors() -> None:
    with pytest.raises(RoutineError, match="needs exactly device"):
        parse("x", "yaml", "id: x\nsteps:\n  - write: { device: d, value: 1 % }\n")
    with pytest.raises(RoutineError, match="id is"):
        parse("x", "yaml", "id: y\nsteps:\n  - log: hi\n")
    with pytest.raises(RoutineError, match="async def run"):
        parse("x", "python", "def run(ctx): pass\n")
    with pytest.raises(RoutineError, match="syntax error"):
        parse("x", "python", "async def run(ctx):\n  return (\n")
    with pytest.raises(RoutineError, match="TRIGGERS"):
        parse("x", "python", "TRIGGERS = [{'every': 'soon'}]\nasync def run(ctx): pass\n")
    with pytest.raises(RoutineError, match="every must be at least"):
        parse("x", "yaml", "id: x\ntriggers: [{every: 100 ms}]\nsteps:\n  - log: hi\n")
    with pytest.raises(RoutineError, match="mapping"):
        parse("x", "yaml", "- 1\n")
    with pytest.raises(RoutineError, match="kind"):
        parse("x", "lua", "")  # type: ignore[arg-type]


async def test_bare_numbers_need_units(hub: Hub) -> None:
    routines = engine(hub)
    routines.create(
        human(), "bare", "yaml", "id: bare\nsteps:\n  - write: { device: desk-fan, channel: fan_speed, value: 20 }\n"
    )
    assert any("needs a unit" in problem for problem in routines.dry_run("bare")["problems"])
    routines.enable(human(), "bare")
    run = await routines.run("bare", by=human())
    assert run.status == "failed"


async def test_agent_opt_in_for_low_hazard(tmp_path: Path) -> None:
    hub = Hub(HubConfig(home=tmp_path, routines=RoutineSettings(agent_enable_low_hazard=True)), in_memory=True)
    hub.add_device(loads(FAN))
    hub.add_device(loads(LASER))
    await hub.start(load_devices=False)
    try:
        routines = hub.routines
        routines.create(
            agent("claude", "control_low"),
            "fan",
            "yaml",
            "id: fan\nsteps:\n  - write: { device: desk-fan, channel: fan_speed, value: 5 % }\n",
        )
        assert routines.enable(agent("claude", "control_low"), "fan").enabled_scope == "control_low"
        routines.create(
            agent("claude", "control_low"),
            "zap",
            "yaml",
            "id: zap\nsteps:\n  - write: { device: laser, channel: power, value: 5 % }\n",
        )
        with pytest.raises(RoutineError, match="low hazard"):
            routines.enable(agent("claude", "control_low"), "zap")
        with pytest.raises(RoutineError, match="read-only"):
            routines.create(agent("viewer", "read"), "x", "yaml", "id: x\nsteps:\n  - log: hi\n")
    finally:
        await hub.close()


async def test_high_hazard_needs_signed_approval(tmp_path: Path) -> None:
    hub = Hub(HubConfig(home=tmp_path), in_memory=True)
    hub.add_device(
        loads(LASER.replace("connect: { mock: laser }", "connect: { mock: laser, initial: { door_closed: true } }"))
    )
    await hub.start(load_devices=False)
    try:
        routines = hub.routines
        source = "id: zap\nsteps:\n  - write: { device: laser, channel: power, value: 5 % }\n"
        record = routines.create(human(), "zap", "yaml", source)
        routines.enable(human(), "zap")
        await hub.kernel.read("laser", "door_closed", human())
        assert (await routines.run("zap", by=human())).status == "blocked"
        approval = hub.kernel.approve_routine(human("sohan"), "laser", "zap", record.sha256)
        runtime = hub.kernel.devices["laser"]
        data = runtime.file.model_dump(by_alias=True, exclude={"extensions"})
        data["approvals"] = [approval.model_dump()]
        runtime.file = type(runtime.file).model_validate(data)
        hub.kernel.devices["laser"].accepted.clear()
        run = await routines.run("zap", by=human())
        assert run.status == "ok", run.message
        changed = routines.create(human(), "zap", "yaml", source + "  - log: changed\n", replace=True)
        assert not changed.enabled, "changing content disables the routine"
        assert changed.disabled_reason == "content changed"
    finally:
        await hub.close()


async def test_stop_disables_and_cancels(hub: Hub) -> None:
    routines = engine(hub)
    routines.create(human(), "slow", "yaml", "id: slow\nsteps:\n  - wait: 30 s\n")
    routines.enable(human(), "slow")
    task = asyncio.create_task(routines.run("slow", by=human()))
    await asyncio.sleep(0.05)
    await hub.kernel.stop_all(human(), "button")
    run = await task
    assert run.status == "cancelled"
    assert not routines.get("slow").enabled
    assert routines.get("slow").disabled_reason == "disabled by stop (button)"
    with pytest.raises(RoutineError, match="stopped"):
        routines.enable(human(), "slow")
    with pytest.raises(RoutineError, match="stopped"):
        await routines.run("slow", by=human())


async def test_run_rules(hub: Hub) -> None:
    routines = engine(hub)
    routines.create(human(), "slow", "yaml", "id: slow\nmax_runtime: 1 s\nsteps:\n  - wait: 5 s\n")
    with pytest.raises(RoutineError, match="Only a human"):
        await routines.run("slow", by=agent("a", "control_low"))
    task = asyncio.create_task(routines.run("slow", by=human()))
    await asyncio.sleep(0.05)
    with pytest.raises(RoutineError, match="already running"):
        await routines.run("slow", by=human())
    run = await task
    assert run.status == "failed"
    assert "max runtime" in run.message
    with pytest.raises(KeyError):
        routines.get("nope")
    with pytest.raises(RoutineError, match="already exists"):
        routines.create(human(), "slow", "yaml", "id: slow\nsteps:\n  - log: x\n")
    with pytest.raises(RoutineError, match="Only a human can delete"):
        routines.delete(agent("a", "control_low"), "slow")
    routines.delete(human(), "slow")
    assert "slow" not in routines.records


async def test_unknown_devices_block_enabling(hub: Hub) -> None:
    routines = engine(hub)
    routines.create(
        human(), "ghost", "yaml", "id: ghost\nsteps:\n  - write: { device: ghost, channel: x, value: 1 % }\n"
    )
    with pytest.raises(RoutineError, match="aren't registered"):
        routines.enable(human(), "ghost")


async def test_triggers(hub: Hub) -> None:
    routines = engine(hub)
    record = routines.create(
        human(),
        "t",
        "yaml",
        "id: t\ntriggers:\n  - at: '07:00'\n  - when: 'desk-fan.fan_speed > 50 %'\n"
        "  - every: 10 s\nsteps:\n  - log: x\n",
    )
    morning = dt.datetime(2026, 10, 25, 7, 0)
    assert routines.due(record, now=0, wall=morning) == "at 07:00"
    assert routines.due(record, now=0, wall=morning) == "every 10 s", "the daily trigger fires once per day"
    routines._last_start["t"] = 100
    assert routines.due(record, now=100.05) is None, "min interval between runs"
    assert routines.due(record, now=105, wall=dt.datetime(2026, 10, 25, 8, 0)) is None
    hub.kernel.devices["desk-fan"].driver.values["fan_speed"] = 60.0  # type: ignore[attr-defined]
    await hub.kernel.read("desk-fan", "fan_speed", human())
    assert routines.due(record, now=106, wall=dt.datetime(2026, 10, 25, 8, 0)) == "when desk-fan.fan_speed > 50 %"
    assert routines.due(record, now=107, wall=dt.datetime(2026, 10, 25, 8, 0)) is None, "edge triggered"
    assert routines.due(record, now=111, wall=dt.datetime(2026, 10, 25, 8, 0)) == "every 10 s"


async def test_scheduler_runs_enabled_routines(hub: Hub) -> None:
    routines = engine(hub)
    routines.create(human(), "tick", "yaml", "id: tick\ntriggers: [{every: 1 s}]\nsteps:\n  - log: tick\n")
    routines.enable(human(), "tick")
    await asyncio.sleep(1.2)
    assert routines.get("tick").last_run is not None


async def test_files_on_disk(tmp_path: Path) -> None:
    config = HubConfig(home=tmp_path)
    config.ensure_dirs()
    (config.routines_dir / "night.routine.yaml").write_text("id: night\nsteps:\n  - log: hi\n")
    (config.routines_dir / "bad.routine.yaml").write_text("id: bad\nsteps: []\n")
    hub = Hub(config)
    try:
        assert "night" in hub.routines.records
        assert "bad" not in hub.routines.records
        assert hub.audit.entries(event="routine_load", status="failed")
        record = hub.routines.create(human(), "saved", "yaml", "id: saved\nsteps:\n  - log: hi\n")
        assert (config.routines_dir / "saved.routine.yaml").exists()
        hub.routines.enable(human(), "saved")
    finally:
        await hub.close()
    again = Hub(config)
    try:
        assert again.routines.get("saved").enabled
        (config.routines_dir / "saved.routine.yaml").write_text("id: saved\nsteps:\n  - log: edited\n")
    finally:
        await again.close()
    third = Hub(config)
    try:
        assert not third.routines.get("saved").enabled, "editing the file disables the routine"
    finally:
        await third.close()
    assert record.sha256 == content_sha256("yaml", "id: saved\nsteps:\n  - log: hi\n")
