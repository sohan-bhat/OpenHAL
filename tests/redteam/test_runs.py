"""Red team. Every way a run of steps could try to get past a check, through MCP and REST.

A run is many commands with timing between them, so each test tries to use that timing, the
repeat count, a second agent, a stop or a held step to get one command past the kernel. Every
attempt must end with the kernel's answer for that exact command, and nothing else reaching a mock.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from openhal.hub.hub import Hub
from openhal.mcp import TOOL_NAMES, Tools
from openhal.mcp.tools import RunStep
from openhal.spec import loads
from tests.kernel.conftest import FakeClock
from tests.redteam.conftest import Rest, Tokens, done_by_clients, driver, writes

PRESS = """
device: Bench press
id: press
connect: { mock: press, initial: { guard_closed: true } }
read:
  guard_closed: { type: bool }
actions:
  cycle:
    require:
      - { condition: "guard_closed == true", message: "the press cycles only with the guard closed" }
safe_state: []
hazard: low
confirmed: { by: owner, at: 2026-10-24 }
"""


def fan(value: float, increment: float | None = None) -> RunStep:
    return RunStep(kind="write", device="desk-fan", channel="fan_speed", value=value, unit="%", increment=increment)


def wait(seconds: float) -> RunStep:
    return RunStep(kind="wait", seconds=seconds)


def moving(hub: Hub, clock: FakeClock) -> None:
    """Waits move the hub's clock, as real time would."""

    async def sleep(seconds: float) -> None:
        clock.advance(seconds)
        await asyncio.sleep(0)

    hub.runs._sleep = sleep


def frozen(hub: Hub) -> None:
    """Waits return at once and no time passes, as if the run tried to outrun its own waits."""

    async def sleep(seconds: float) -> None:
        await asyncio.sleep(0)

    hub.runs._sleep = sleep


def gated(hub: Hub, clock: FakeClock) -> asyncio.Event:
    release = asyncio.Event()

    async def sleep(seconds: float) -> None:
        await release.wait()
        clock.advance(seconds)

    hub.runs._sleep = sleep
    return release


def fan_values(hub: Hub) -> list[Any]:
    return [value for _kind, channel, value in writes(hub, "desk-fan") if channel == "fan_speed"]


async def test_repeats_cant_outrun_the_rate_limit_in_the_plan(
    hub: Hub, clock: FakeClock, mcp_tools: Callable[[str], Tools], tokens: Tokens
) -> None:
    moving(hub, clock)
    clock.advance(1)
    run = await mcp_tools(tokens.agent).run_steps([fan(30, increment=10), wait(0.4)], repeat=5)
    assert (run.status, run.stop.code if run.stop else None) == ("blocked", "rate_limited")
    assert (run.stop.iteration, run.stop.step) == (1, 0)  # type: ignore[union-attr]
    assert run.error is not None
    assert run.error.name == "RATE_LIMITED"
    assert writes(hub, "desk-fan") == [], "nothing ran, not even the steps before the blocked one"


async def test_waits_that_take_no_time_cant_outrun_the_rate_limit_when_running(
    hub: Hub, clock: FakeClock, mcp_tools: Callable[[str], Tools], tokens: Tokens
) -> None:
    frozen(hub)
    clock.advance(1)
    run = await mcp_tools(tokens.agent).run_steps([fan(30), wait(1), fan(40)])
    assert run.plan["needs_confirmation"] == []
    assert (run.status, run.stop.code if run.stop else None, run.done_steps) == ("blocked", "rate_limited", 3)
    assert fan_values(hub) == [30.0]


async def test_increment_cant_step_past_a_limit(
    hub: Hub, clock: FakeClock, mcp_tools: Callable[[str], Tools], tokens: Tokens
) -> None:
    moving(hub, clock)
    clock.advance(10)
    run = await mcp_tools(tokens.agent).run_steps([fan(40, increment=20), wait(2)], repeat=5)
    assert (run.status, run.stop.code, run.stop.iteration) == ("blocked", "above_max", 4)  # type: ignore[union-attr]
    assert run.error is not None
    assert run.error.message.startswith("fan_speed 120 % exceeds the limit of 100 %")
    assert writes(hub, "desk-fan") == []


async def test_no_step_runs_after_a_stop(
    hub: Hub, clock: FakeClock, mcp_tools: Callable[[str], Tools], tokens: Tokens, rest: Rest
) -> None:
    release = gated(hub, clock)
    clock.advance(1)
    agent = mcp_tools(tokens.agent)
    run = await agent.run_steps([fan(30), wait(1), fan(40), wait(1), fan(50)], wait_s=0)
    await asyncio.sleep(0.05)
    assert run.status == "running"
    async with rest(tokens.other) as other:
        assert (await other.post("/v1/stop", json={"reason": "another agent saw smoke"})).status_code == 200
    release.set()
    ended = await agent.get_run(run.run_id, wait_s=5)
    assert (ended.status, ended.stop.code if ended.stop else None) == ("cancelled", "stopped")
    assert fan_values(hub) == [30.0, 0.0], "the first step, then the safe state"
    assert done_by_clients(hub) == [("agent:claude", "desk-fan", "write:fan_speed")]
    after = await agent.run_steps([fan(0)])
    assert (after.status, after.stop.code if after.stop else None) == ("blocked", "stopped")
    assert fan_values(hub) == [30.0, 0.0]


async def test_a_run_ends_at_its_time_cap(
    hub: Hub, clock: FakeClock, mcp_tools: Callable[[str], Tools], tokens: Tokens, rest: Rest
) -> None:
    moving(hub, clock)
    clock.advance(1)
    async with rest(tokens.human) as person:
        lowered = await person.post("/v1/runs/caps", json={"max_seconds": 2})
        assert lowered.json()["max_seconds"] == 2
    agent = mcp_tools(tokens.agent)
    never = RunStep(kind="wait_until", condition="desk-fan.temperature > 500 degC", timeout_s=2)
    run = await agent.run_steps([wait(1), never, fan(30)])
    assert (run.status, run.stop.code if run.stop else None) == ("cancelled", "time_cap")
    assert writes(hub, "desk-fan") == []
    with pytest.raises(ToolError, match=r"INVALID_PARAMS .* longer than the 2 s"):
        await agent.run_steps([wait(1)], repeat=3)


async def test_one_agent_cant_see_or_cancel_another_agents_run(
    hub: Hub, clock: FakeClock, mcp_tools: Callable[[str], Tools], tokens: Tokens, rest: Rest
) -> None:
    release = gated(hub, clock)
    clock.advance(1)
    owner, other = mcp_tools(tokens.agent), mcp_tools(tokens.other)
    run = await owner.run_steps([fan(30), wait(1), fan(40)], wait_s=0)
    with pytest.raises(ToolError, match="There is no run"):
        await other.cancel_run(run.run_id)
    with pytest.raises(ToolError, match="There is no run"):
        await other.get_run(run.run_id)
    assert await other.list_runs() == []
    async with rest(tokens.reader) as reader:
        assert (await reader.post(f"/v1/runs/{run.run_id}/cancel")).status_code == 404
    assert (await owner.get_run(run.run_id)).status == "running"
    refused = [entry.principal for entry in hub.audit.entries(event="run_cancel") if entry.status == "blocked"]
    assert refused == ["agent:viewer", "agent:other"]
    release.set()
    assert (await owner.get_run(run.run_id, wait_s=5)).status == "done"
    assert fan_values(hub) == [30.0, 40.0]


async def test_an_interlock_that_fails_partway_stops_the_run_at_that_action(
    hub: Hub, clock: FakeClock, mcp_tools: Callable[[str], Tools], tokens: Tokens
) -> None:
    await hub.add_and_start(loads(PRESS))
    press = driver(hub, "press")

    async def sleep(seconds: float) -> None:
        press.values["guard_closed"] = False
        clock.advance(seconds)

    hub.runs._sleep = sleep
    cycle = RunStep(kind="action", device="press", action="cycle")
    look = RunStep(kind="read", targets=["press.guard_closed"])
    run = await mcp_tools(tokens.agent).run_steps([cycle, wait(1), look, cycle], repeat=2)
    assert (run.status, run.stop.code if run.stop else None, run.stop.index if run.stop else None) == (
        "blocked",
        "interlock",
        3,
    )
    assert run.error is not None
    assert run.error.name == "INTERLOCK_BLOCKED"
    assert "guard closed" in run.message
    assert writes(hub, "press") == [("action", "cycle", {})]


async def test_steps_cant_approve_unlock_widen_or_enable(
    hub: Hub, tokens: Tokens, rest: Rest, mcp_tools: Callable[[str], Tools]
) -> None:
    attempts = [
        {"kind": "approve", "request_id": "x"},
        {"kind": "confirm", "request_id": "x"},
        {"kind": "unlock", "phrase": "unlock"},
        {"kind": "tighten", "device": "desk-fan", "channel": "fan_speed", "max": {"value": 150, "unit": "%"}},
        {"kind": "limits", "device": "desk-fan", "channel": "fan_speed", "phrase": "confirm"},
        {"kind": "enable_routine", "routine_id": "x"},
        {"kind": "write", "device": "desk-fan", "channel": "fan_speed", "value": 30, "unit": "%", "approved": True},
        {"kind": "write", "device": "desk-fan", "channel": "fan_speed", "value": 30, "unit": "%", "request_id": "x"},
        {"kind": "action", "device": "heater", "action": "purge", "principal": "human:owner"},
    ]
    async with rest(tokens.agent) as agent:
        for step in attempts:
            response = await agent.post("/v1/runs", json={"steps": [step]})
            assert response.status_code == 422, step
        assert (await agent.post("/v1/runs/caps", json={"max_steps": 10_000, "phrase": "confirm"})).status_code == 403
    with pytest.raises(ValidationError):
        RunStep.model_validate({"kind": "unlock"})
    with pytest.raises(ValidationError):
        RunStep.model_validate({"kind": "write", "device": "desk-fan", "phrase": "confirm"})
    assert not [name for name in TOOL_NAMES if "caps" in name]
    assert hub.config.runs.max_steps == 200
    assert writes(hub, "desk-fan") == []


async def test_a_held_step_ends_the_run_and_approval_runs_only_that_step(
    hub: Hub, clock: FakeClock, mcp_tools: Callable[[str], Tools], tokens: Tokens, rest: Rest
) -> None:
    clock.advance(1)
    laser = RunStep(kind="write", device="laser", channel="power", value=5, unit="%")
    run = await mcp_tools(tokens.agent).run_steps([laser, fan(30)], wait_s=0.5)
    assert (run.status, run.done_steps) == ("pending", 1)
    assert run.request_id is not None
    assert run.finished_at is not None, "the run ended, nothing holds inside it"
    async with rest(tokens.human) as person:
        approved = await person.post(f"/v1/confirmations/{run.request_id}/approve", json={"phrase": "approve"})
        assert approved.json()["status"] == "done"
    await asyncio.sleep(0.05)
    assert writes(hub, "laser") == [("write", "power", 5.0)]
    assert writes(hub, "desk-fan") == [], "the steps after the held one never run"


async def test_a_run_acts_as_its_caller_and_no_one_else(
    hub: Hub, clock: FakeClock, mcp_tools: Callable[[str], Tools], tokens: Tokens
) -> None:
    clock.advance(1)
    reader = await mcp_tools(tokens.reader).run_steps([fan(30)])
    assert (reader.status, reader.error.name if reader.error else None) == ("blocked", "SCOPE_DENIED")
    agent = mcp_tools(tokens.agent)
    await agent.tighten_limits("desk-fan", "fan_speed", max={"value": 25, "unit": "%"})
    tight = await agent.run_steps([fan(30)])
    assert tight.error is not None
    assert "session limit of 25 %" in tight.error.message
    other = await mcp_tools(tokens.other).run_steps([fan(30)])
    assert other.status == "done", "the session limit belongs to the agent that set it"
    text = await agent.run_steps([RunStep(kind="write", device="desk-fan", channel="fan_speed", value="60 %")])
    assert (text.status, text.error.name if text.error else None) == ("blocked", "UNIT_INVALID")
    draft = await agent.run_steps([RunStep(kind="write", device="draft-lamp", channel="brightness", value=5, unit="%")])
    assert (draft.status, draft.error.name if draft.error else None) == ("blocked", "UNVERIFIED_LIMITS")
    assert done_by_clients(hub) == [("agent:other", "desk-fan", "write:fan_speed")]


async def test_the_audit_log_records_the_run_and_every_step(
    hub: Hub, clock: FakeClock, mcp_tools: Callable[[str], Tools], tokens: Tokens
) -> None:
    moving(hub, clock)
    clock.advance(1)
    run = await mcp_tools(tokens.agent).run_steps([fan(30), wait(1), fan(40), wait(1)], repeat=2)
    assert run.status == "done"
    steps = hub.audit.entries(event="run_step", limit=100)
    assert len(steps) == 8
    assert all(entry.principal == "agent:claude" and entry.body["details"]["run_id"] == run.run_id for entry in steps)
    assert [entry.status for entry in hub.audit.entries(event="run")] == ["done", "running"]
    assert fan_values(hub) == [30.0, 40.0, 30.0, 40.0]
    ok, broken = hub.audit.verify()
    assert ok, broken


async def test_run_ids_are_unguessable_and_private(hub: Hub, mcp_tools: Callable[[str], Tools], tokens: Tokens) -> None:
    run = await mcp_tools(tokens.agent).run_steps([wait(0.01)])
    assert len(run.run_id) == len("run-") + 16
    assert [item.run_id for item in await mcp_tools(tokens.agent).list_runs()] == [run.run_id]
    assert await mcp_tools(tokens.low).list_runs() == []
