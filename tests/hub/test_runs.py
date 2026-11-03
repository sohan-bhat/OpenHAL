"""Runs of steps, waits on a condition and samples, against a real embedded hub with mock devices.

The hub's clock is a fake clock, and the engine's sleep moves that clock, so a run of minutes takes
milliseconds and every rate check sees the time a real run would.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from openhal.drivers.mock import MockDriver
from openhal.hub.api import create_app, while_connected
from openhal.hub.config import HubConfig, load_config
from openhal.hub.hub import Hub
from openhal.hub.runs import (
    MAX_POINTS,
    CapsBody,
    RunBody,
    RunError,
    SampleBody,
    WaitBody,
)
from openhal.kernel.principals import agent, human
from openhal.spec import loads
from tests.kernel.conftest import FAN, HEATER, LASER, FakeClock

LAMP = """
device: Bench lamp
id: lamp
connect: { mock: lamp }
read:
  frame: { type: image }
write:
  on: { type: bool }
  brightness: { unit: "%", min: 0, max: 100 }
actions:
  flash:
    args:
      length: { unit: ms, min: 10, max: 500 }
    max_runs: { count: 2, per: 1 h }
safe_state: { on: false }
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""

WARMER = """
device: Warming plate
id: warmer
connect: { mock: warmer, simulate: heater, ambient_c: 31 }
read:
  temp: { unit: degC }
write:
  power: { unit: W, min: 0, max: 20 }
safe_state: { power: 0 }
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""

CLAUDE = agent("claude", "control_medium")
OTHER = agent("other", "control_medium")
OWNER = human("owner")

Steps = list[dict[str, Any]]


def body(steps: Steps, **extra: Any) -> RunBody:
    return RunBody.model_validate({"steps": steps, **extra})


def blink(on_s: float = 0.5) -> Steps:
    return [
        {"kind": "write", "device": "lamp", "channel": "on", "value": True},
        {"kind": "wait", "seconds": on_s},
        {"kind": "write", "device": "lamp", "channel": "on", "value": False},
        {"kind": "wait", "seconds": on_s},
    ]


def mock(hub: Hub, device: str) -> MockDriver:
    driver = hub.kernel.devices[device].driver
    assert isinstance(driver, MockDriver)
    return driver


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
async def hub(tmp_path: Path, clock: FakeClock) -> AsyncIterator[Hub]:
    hub = Hub(HubConfig(home=tmp_path), clock=clock, in_memory=True)
    for text in (FAN, HEATER, LASER, LAMP, WARMER):
        hub.add_device(loads(text))
    await hub.start(load_devices=False)
    clock.advance(60)
    for device in hub.kernel.devices:
        await hub.kernel.snapshot(device)

    async def sleep(seconds: float) -> None:
        clock.advance(seconds)
        await asyncio.sleep(0)

    hub.runs._sleep = sleep
    yield hub
    await hub.close()


Gate = Callable[[float], Awaitable[None]]


def gated(hub: Hub, clock: FakeClock) -> asyncio.Event:
    """Make every wait hold until the returned event is set, so a run stays running."""
    release = asyncio.Event()

    async def sleep(seconds: float) -> None:
        await release.wait()
        clock.advance(seconds)

    hub.runs._sleep = sleep
    return release


async def until_done(hub: Hub, run_id: str) -> dict[str, Any]:
    return await hub.runs.wait_for(CLAUDE, run_id, 5, 500)


async def test_a_run_blinks_a_lamp_through_the_kernel(hub: Hub) -> None:
    run = await hub.runs.start(CLAUDE, body(blink(), repeat=5))
    assert run["status"] == "done", run["message"]
    assert (run["total_steps"], run["done_steps"]) == (20, 20)
    assert [value for _kind, _channel, value in mock(hub, "lamp").hardware_writes()] == [True, False] * 5
    written = [entry for entry in hub.audit.entries(event="write", limit=100) if entry.principal == "agent:claude"]
    assert len(written) == 10
    assert len(hub.audit.entries(event="run_step", limit=100)) == 20
    assert [entry.status for entry in hub.audit.entries(event="run")] == ["done", "running"]
    assert run["message"] == "Done. All 20 steps ran."
    assert run["plan"] == {"commands_checked": 10, "needs_confirmation": [], "checked_when_run": []}


async def test_increment_steps_a_value_on_each_repeat(hub: Hub) -> None:
    steps = [
        {"kind": "write", "device": "lamp", "channel": "brightness", "value": 10, "unit": "%", "increment": 10},
        {"kind": "wait", "seconds": 1},
    ]
    run = await hub.runs.start(CLAUDE, body(steps, repeat=3))
    assert run["status"] == "done"
    assert [value for *_rest, value in mock(hub, "lamp").hardware_writes()] == [10.0, 20.0, 30.0]
    with pytest.raises(ValidationError, match="increment needs a number"):
        body([{"kind": "write", "device": "lamp", "channel": "on", "value": True, "increment": 1}])


async def test_a_plan_that_breaks_a_limit_runs_nothing(hub: Hub) -> None:
    steps = [
        {"kind": "write", "device": "lamp", "channel": "brightness", "value": 50, "unit": "%"},
        {"kind": "write", "device": "lamp", "channel": "brightness", "value": 150, "unit": "%"},
    ]
    run = await hub.runs.start(CLAUDE, body(steps))
    assert run["status"] == "blocked"
    assert (run["stop"]["index"], run["stop"]["code"]) == (1, "above_max")
    assert run["message"].startswith("Nothing ran. Blocked.")
    assert run["stop"]["decision"]["limit"] == {"max": 100.0, "unit": "%"}
    assert mock(hub, "lamp").hardware_writes() == []


async def test_a_step_that_needs_a_person_ends_the_run_with_its_request(hub: Hub) -> None:
    mock(hub, "laser").values["door_closed"] = True
    await hub.kernel.snapshot("laser")
    steps = [
        {"kind": "write", "device": "lamp", "channel": "on", "value": True},
        {"kind": "write", "device": "laser", "channel": "power", "value": 5, "unit": "%"},
        {"kind": "write", "device": "lamp", "channel": "on", "value": False},
    ]
    run = await hub.runs.start(CLAUDE, body(steps))
    assert run["status"] == "pending"
    assert run["plan"]["needs_confirmation"] == [1]
    assert run["request_id"] == hub.kernel.pending()[0].request_id
    assert "openhal confirm approve" in run["message"]
    assert run["done_steps"] == 2
    assert mock(hub, "lamp").hardware_writes() == [("write", "on", True)]
    assert mock(hub, "laser").hardware_writes() == []


async def test_a_failed_command_fails_the_run(hub: Hub) -> None:
    mock(hub, "lamp").settings.fail_writes = True
    run = await hub.runs.start(CLAUDE, body(blink()))
    assert (run["status"], run["stop"]["code"], run["done_steps"]) == ("failed", "driver_error", 1)


async def test_reads_in_a_run_report_failures_and_keep_going(hub: Hub) -> None:
    mock(hub, "lamp").settings.fail_reads = True
    steps = [{"kind": "read", "targets": ["lamp.on", "desk-fan.temperature"]}, {"kind": "wait", "seconds": 1}]
    run = await hub.runs.start(CLAUDE, body(steps))
    assert run["status"] == "done"
    first, second = run["results"][0]["readings"]
    assert first["ok"] is False
    assert "fail_reads" in first["error"]
    assert second["ok"] is True


async def test_caps_bound_steps_waits_and_runs_at_once(hub: Hub, clock: FakeClock) -> None:
    with pytest.raises(RunError, match="has 400 steps") as steps:
        await hub.runs.start(CLAUDE, body(blink(), repeat=100))
    assert steps.value.status == 400
    with pytest.raises(RunError, match="A run that waits of 700 s"):
        await hub.runs.start(CLAUDE, body([{"kind": "wait", "seconds": 350}], repeat=2))
    with pytest.raises(RunError, match="A wait_until step"):
        await hub.runs.start(CLAUDE, body([{"kind": "wait_until", "condition": "lamp.on == true", "timeout_s": 900}]))
    with pytest.raises(RunError, match="no channel"):
        await hub.runs.start(CLAUDE, body([{"kind": "read", "targets": ["lamp.glow"]}]))
    release = gated(hub, clock)
    first = await hub.runs.start(CLAUDE, body(blink(), wait_s=0))
    second = await hub.runs.start(CLAUDE, body(blink(), wait_s=0))
    with pytest.raises(RunError, match="already has 2") as busy:
        await hub.runs.wait_until(CLAUDE, WaitBody(condition="lamp.on == true", timeout_s=1))
    assert busy.value.status == 429
    assert (await hub.runs.start(OTHER, body(blink(), wait_s=0)))["status"] == "running"
    release.set()
    for run in (first, second):
        assert (await until_done(hub, run["run_id"]))["status"] == "done"


async def test_a_run_belongs_to_the_principal_that_started_it(hub: Hub, clock: FakeClock) -> None:
    release = gated(hub, clock)
    run = await hub.runs.start(CLAUDE, body(blink(), wait_s=0))
    with pytest.raises(RunError, match="There is no run") as hidden:
        await hub.runs.cancel(OTHER, run["run_id"])
    assert hidden.value.status == 404
    with pytest.raises(RunError):
        await hub.runs.wait_for(OTHER, run["run_id"], 0, 10)
    assert hub.runs.listed(OTHER) == []
    assert [item["run_id"] for item in hub.runs.listed(OWNER)] == [run["run_id"]]
    assert hub.runs.listed(CLAUDE)[0]["results"] == []
    assert hub.audit.entries(event="run_cancel")[0].status == "blocked"
    cancel = asyncio.create_task(hub.runs.cancel(OWNER, run["run_id"]))
    await asyncio.sleep(0)
    release.set()
    ended = await cancel
    assert (ended["status"], ended["stop"]["code"]) == ("cancelled", "cancelled")
    assert ended["message"] == "Cancelled by human:owner. The steps after this one did not run."
    again = await hub.runs.cancel(CLAUDE, run["run_id"])
    assert again["status"] == "cancelled"


async def test_a_stop_ends_runs_waits_and_samples_and_blocks_new_runs(hub: Hub, clock: FakeClock) -> None:
    gated(hub, clock)
    run = await hub.runs.start(CLAUDE, body(blink(), wait_s=0))
    wait = asyncio.create_task(hub.runs.wait_until(OTHER, WaitBody(condition="lamp.brightness > 90 %")))
    sample = asyncio.create_task(hub.runs.sample(OWNER, SampleBody(targets=["lamp.on"], duration_s=10)))
    await asyncio.sleep(0.05)
    await hub.kernel.stop_all(OTHER, "agent stop")
    ended = await until_done(hub, run["run_id"])
    assert (ended["status"], ended["stop"]["code"]) == ("cancelled", "stopped")
    assert ended["message"].startswith("Ended by a stop.")
    assert (await wait)["status"] == "stopped"
    assert (await sample)["status"] == "stopped"
    after = await hub.runs.start(CLAUDE, body(blink()[:1]))
    assert (after["status"], after["stop"]["code"]) == ("blocked", "stopped")
    watch = await hub.runs.start(CLAUDE, body([{"kind": "read", "targets": ["lamp.on"]}]))
    assert watch["status"] == "done", "a run that only reads still runs while the hub is stopped"
    by_claude = [entry for entry in hub.audit.entries(event="write", limit=100) if entry.principal == "agent:claude"]
    assert [entry.status for entry in by_claude] == ["done"]
    assert [value for *_rest, value in mock(hub, "lamp").hardware_writes()] == [True, False], "then the safe state"


async def test_a_revoked_token_ends_its_runs(hub: Hub, clock: FakeClock) -> None:
    gated(hub, clock)
    token, info = hub.tokens.create("claude", "agent", "control_medium")
    person = hub.tokens.create("owner", "human")[0]
    run = await hub.runs.start(CLAUDE, body(blink(), wait_s=0))
    transport = httpx.ASGITransport(app=create_app(hub), client=("127.0.0.1", 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:7420") as client:
        response = await client.delete(f"/v1/tokens/{info.token_id}", headers={"Authorization": f"Bearer {person}"})
        assert response.json() == {"ok": True}
        assert (await client.get("/v1/runs", headers={"Authorization": f"Bearer {token}"})).status_code == 401
    ended = await until_done(hub, run["run_id"])
    assert (ended["status"], ended["stop"]["code"]) == ("cancelled", "token_revoked")


async def test_a_run_ends_at_its_time_cap(hub: Hub, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> None:
    hub.config.runs = hub.config.runs.model_copy(update={"max_seconds": 2.0})
    read = hub.kernel.read

    async def slow_read(*args: Any) -> Any:
        clock.advance(1)
        return await read(*args)

    monkeypatch.setattr(hub.kernel, "read", slow_read)
    reads = [{"kind": "read", "targets": ["lamp.on"]}] * 3
    capped = await hub.runs.start(CLAUDE, body(reads))
    assert (capped["status"], capped["stop"]["code"], capped["done_steps"]) == ("cancelled", "time_cap", 2)
    waited = await hub.runs.start(CLAUDE, body([reads[0], {"kind": "wait", "seconds": 1.5}]))
    assert (waited["stop"]["code"], waited["results"][-1]["status"]) == ("time_cap", "cancelled")
    never = {"kind": "wait_until", "condition": "lamp.brightness > 99 %", "timeout_s": 2}
    cut = await hub.runs.start(CLAUDE, body([reads[0], never, *blink()[:1]]))
    assert (cut["status"], cut["stop"]["code"], cut["done_steps"]) == ("cancelled", "time_cap", 2)
    assert mock(hub, "lamp").hardware_writes() == []


async def test_a_wait_until_step_gates_the_steps_after_it(hub: Hub) -> None:
    never = {"kind": "wait_until", "condition": "lamp.brightness > 99 %", "timeout_s": 2}
    run = await hub.runs.start(CLAUDE, body([never, *blink()]))
    assert (run["status"], run["stop"]["code"]) == ("failed", "condition_timeout")
    assert run["results"][0]["held"] is False
    assert mock(hub, "lamp").hardware_writes() == []
    held = {"kind": "wait_until", "condition": "lamp.on == false", "timeout_s": 2}
    assert (await hub.runs.start(CLAUDE, body([held, *blink()])))["status"] == "done"


async def test_a_stop_during_a_check_or_a_command_ends_the_run(
    hub: Hub, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    read = hub.kernel.read

    async def stopping_read(*args: Any) -> Any:
        await hub.kernel.stop_all(OTHER, "stop mid read")
        return await read(*args)

    monkeypatch.setattr(hub.kernel, "read", stopping_read)
    wait = await hub.runs.wait_until(CLAUDE, WaitBody(condition="lamp.on == true", timeout_s=5))
    assert wait["status"] == "stopped"
    sample = await hub.runs.sample(CLAUDE, SampleBody(targets=["lamp.on"], duration_s=3))
    assert (sample["status"], sample["series"][0]["count"]) == ("stopped", 1)
    hub.kernel.unlock(OWNER, "unlock")
    reads = [{"kind": "read", "targets": ["lamp.on"]}] * 2
    run = await hub.runs.start(CLAUDE, body(reads))
    assert (run["status"], run["stop"]["code"], run["done_steps"]) == ("cancelled", "stopped", 1)
    hub.kernel.unlock(OWNER, "unlock")
    execute = hub.kernel.execute

    async def stopping_execute(*args: Any, **kwargs: Any) -> Any:
        decision = await execute(*args, **kwargs)
        await hub.kernel.stop_all(OTHER, "stop after a command")
        return decision

    monkeypatch.setattr(hub.kernel, "read", read)
    monkeypatch.setattr(hub.kernel, "execute", stopping_execute)
    run = await hub.runs.start(CLAUDE, body(blink()))
    assert (run["status"], run["stop"]["code"], run["done_steps"]) == ("cancelled", "stopped", 1)


async def test_action_steps_count_against_max_runs_in_the_plan(hub: Hub) -> None:
    flash = {"kind": "action", "device": "lamp", "action": "flash", "args": {"length": {"value": 50, "unit": "ms"}}}
    run = await hub.runs.start(CLAUDE, body([flash, {"kind": "wait", "seconds": 1}], repeat=3))
    assert (run["status"], run["stop"]["code"], run["stop"]["iteration"]) == ("blocked", "rate_limited", 2)
    assert mock(hub, "lamp").hardware_writes() == []
    twice = await hub.runs.start(CLAUDE, body([flash], repeat=2))
    assert twice["status"] == "done"
    assert twice["results"][0]["value"] == {"length": {"value": 50, "unit": "ms"}}
    assert len(mock(hub, "lamp").hardware_writes()) == 2


async def test_a_cancel_during_a_wait_until_step_ends_the_run(hub: Hub, clock: FakeClock) -> None:
    release = gated(hub, clock)
    never = {"kind": "wait_until", "condition": "lamp.brightness > 99 %", "timeout_s": 30}
    run = await hub.runs.start(CLAUDE, body([never, *blink()], wait_s=0))
    cancel = asyncio.create_task(hub.runs.cancel(CLAUDE, run["run_id"]))
    ended = await cancel
    release.set()
    assert (ended["status"], ended["stop"]["code"], ended["results"][0]["status"]) == (
        "cancelled",
        "cancelled",
        "cancelled",
    )
    assert mock(hub, "lamp").hardware_writes() == []


async def test_closing_the_hub_cancels_a_command_that_never_returns(
    tmp_path: Path, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    hub = Hub(HubConfig(home=tmp_path), clock=clock, in_memory=True)
    hub.add_device(loads(LAMP))
    await hub.start(load_devices=False)

    async def hangs(*args: Any, **kwargs: Any) -> Any:
        await asyncio.Event().wait()

    monkeypatch.setattr(hub.kernel, "execute", hangs)
    monkeypatch.setattr("openhal.hub.runs.END_WAIT_S", 0.01)
    run = await hub.runs.start(CLAUDE, body(blink(), wait_s=0))
    await hub.close()
    assert hub.runs.runs[run["run_id"]].stop == {
        "kind": "run",
        "code": "hub_closed",
        "message": "Ended because the hub shut down.",
    }


async def test_after_a_wait_until_a_live_block_is_left_to_the_kernel(hub: Hub) -> None:
    gate = {"kind": "wait_until", "condition": "desk-fan.fan_speed >= 30 %", "timeout_s": 3}
    heat = {"kind": "write", "device": "heater", "channel": "power", "value": 10, "unit": "W"}
    ungated = await hub.runs.start(CLAUDE, body([heat]))
    assert (ungated["status"], ungated["stop"]["code"]) == ("blocked", "interlock")
    never = await hub.runs.start(CLAUDE, body([gate, heat]))
    assert (never["status"], never["stop"]["code"]) == ("failed", "condition_timeout")
    assert never["plan"]["checked_when_run"] == [1]
    assert mock(hub, "heater").hardware_writes() == []
    mock(hub, "desk-fan").values["fan_speed"] = 40
    held = await hub.runs.start(CLAUDE, body([gate, heat]))
    assert held["status"] == "done", held["message"]
    assert mock(hub, "heater").hardware_writes() == [("write", "power", 10.0)]
    too_hot = await hub.runs.start(CLAUDE, body([gate, {**heat, "value": 100}]))
    assert (too_hot["status"], too_hot["stop"]["code"]) == ("blocked", "above_max")


async def test_a_lower_time_cap_ends_a_run_that_already_started(hub: Hub, clock: FakeClock) -> None:
    async def sleep(seconds: float) -> None:
        clock.advance(seconds)
        await asyncio.sleep(0.01)

    hub.runs._sleep = sleep
    run = await hub.runs.start(CLAUDE, body([{"kind": "wait", "seconds": 500}, *blink()[:1]], wait_s=0))
    await asyncio.sleep(0.05)
    hub.runs.set_caps(OWNER, CapsBody(max_seconds=10))
    ended = await until_done(hub, run["run_id"])
    assert (ended["status"], ended["stop"]["code"]) == ("cancelled", "time_cap")
    assert ended["elapsed_s"] < 500
    assert mock(hub, "lamp").hardware_writes() == []


async def test_a_device_removed_during_a_run_reads_as_a_failed_reading(hub: Hub, clock: FakeClock) -> None:
    release = gated(hub, clock)
    read = {"kind": "read", "targets": ["warmer.temp"]}
    run = await hub.runs.start(CLAUDE, body([read, {"kind": "wait", "seconds": 1}, read], wait_s=0))
    await hub._remove_device("warmer")
    release.set()
    ended = await until_done(hub, run["run_id"])
    assert ended["status"] == "done"
    last = ended["results"][-1]["readings"][0]
    assert (last["ok"], last["error"]) == (False, "There is no device 'warmer'.")


async def test_a_long_read_ends_when_its_client_goes_away() -> None:
    finished: list[bool] = []

    async def work() -> dict[str, Any]:
        try:
            await asyncio.sleep(10)
        finally:
            finished.append(True)
        return {}

    class Gone:
        async def is_disconnected(self) -> bool:
            return True

    with pytest.raises(HTTPException) as gone:
        await while_connected(Gone(), work(), poll_s=0.01)  # type: ignore[arg-type]
    assert gone.value.status_code == 499
    assert finished == [True]


async def test_a_bug_in_the_plan_check_runs_nothing(hub: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("bug")

    monkeypatch.setattr(hub.kernel, "evaluate", broken)
    hub.config.runs = hub.config.runs.model_copy(update={"per_agent": 1})
    run = await hub.runs.start(CLAUDE, body(blink()))
    assert (run["status"], run["stop"]["code"]) == ("failed", "internal_error")
    assert mock(hub, "lamp").hardware_writes() == []
    assert (await hub.runs.start(CLAUDE, body([{"kind": "wait", "seconds": 1}])))["status"] == "done", "freed"


async def test_a_bug_in_a_step_fails_the_run_closed(hub: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("bug")

    monkeypatch.setattr(hub.kernel, "execute", broken)
    run = await hub.runs.start(CLAUDE, body(blink()))
    assert (run["status"], run["stop"]["code"]) == ("failed", "internal_error")
    assert "RuntimeError" in run["message"]


async def test_closing_the_hub_ends_running_runs(tmp_path: Path, clock: FakeClock) -> None:
    hub = Hub(HubConfig(home=tmp_path), clock=clock, in_memory=True)
    hub.add_device(loads(LAMP))
    await hub.start(load_devices=False)
    gated(hub, clock)
    run = await hub.runs.start(CLAUDE, body(blink(), wait_s=0))
    await hub.close()
    assert (hub.runs.runs[run["run_id"]].status, hub.runs.runs[run["run_id"]].reason) == ("cancelled", "hub_closed")


async def test_a_run_task_cancelled_from_outside_records_why(hub: Hub, clock: FakeClock) -> None:
    gated(hub, clock)
    run = await hub.runs.start(CLAUDE, body(blink(), wait_s=0))
    task = hub.runs.runs[run["run_id"]].task
    assert task is not None
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert hub.runs.runs[run["run_id"]].stop == {
        "kind": "run",
        "code": "hub_closed",
        "message": "Ended because the hub shut down.",
    }


async def test_finished_runs_are_kept_up_to_a_limit(hub: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("openhal.hub.runs.KEPT_RUNS", 3)
    ids = [(await hub.runs.start(CLAUDE, body([{"kind": "wait", "seconds": 1}])))["run_id"] for _ in range(5)]
    assert list(hub.runs.runs) == ids[-3:]


async def test_only_a_person_changes_caps_and_raising_takes_the_phrase(hub: Hub) -> None:
    with pytest.raises(RunError, match="human principal") as agent_tried:
        hub.runs.set_caps(CLAUDE, CapsBody(max_steps=10))
    assert agent_tried.value.status == 403
    lowered = hub.runs.set_caps(OWNER, CapsBody(max_steps=10, per_agent=2))
    assert lowered["changed"] == {"max_steps": {"from": 200, "to": 10}}
    with pytest.raises(RunError, match="Raising max_seconds, max_steps takes the typed phrase confirm"):
        hub.runs.set_caps(OWNER, CapsBody(max_steps=20, max_seconds=900))
    raised = hub.runs.set_caps(OWNER, CapsBody(max_steps=20, max_seconds=900, phrase=" Confirm "))
    assert (raised["max_steps"], raised["max_seconds"], raised["max_points"]) == (20, 900.0, MAX_POINTS)
    assert [entry.status for entry in hub.audit.entries(event="run_caps")] == ["done", "blocked", "done", "blocked"]


async def test_caps_are_saved_in_config_yaml(tmp_path: Path) -> None:
    hub = Hub(HubConfig(home=tmp_path))
    try:
        hub.runs.set_caps(OWNER, CapsBody(per_agent=1))
        assert load_config(tmp_path).runs.per_agent == 1
    finally:
        hub.audit.close()
        hub.tokens.close()


async def test_the_routes(hub: Hub, clock: FakeClock) -> None:
    claude = hub.tokens.create("claude", "agent", "control_medium")[0]
    person = hub.tokens.create("owner", "human")[0]
    transport = httpx.ASGITransport(app=create_app(hub), client=("127.0.0.1", 50000))
    as_claude = {"Authorization": f"Bearer {claude}"}
    as_person = {"Authorization": f"Bearer {person}"}
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:7420") as client:
        run = (await client.post("/v1/runs", json={"steps": blink(), "repeat": 2}, headers=as_claude)).json()
        assert run["status"] == "done"
        got = await client.get(f"/v1/runs/{run['run_id']}", params={"last": 2, "wait_s": 1}, headers=as_claude)
        assert len(got.json()["results"]) == 2
        assert [item["run_id"] for item in (await client.get("/v1/runs", headers=as_claude)).json()] == [run["run_id"]]
        cancelled = await client.post(f"/v1/runs/{run['run_id']}/cancel", headers=as_claude)
        assert cancelled.json()["status"] == "done"
        assert (await client.get("/v1/runs/run-nope", headers=as_claude)).status_code == 404
        assert (await client.post("/v1/runs/run-nope/cancel", headers=as_claude)).status_code == 404
        unknown = {"steps": [{"kind": "unlock", "phrase": "unlock"}]}
        assert (await client.post("/v1/runs", json=unknown, headers=as_claude)).status_code == 422
        too_many = {"steps": blink(), "repeat": 60}
        assert (await client.post("/v1/runs", json=too_many, headers=as_claude)).status_code == 400
        waited = await client.post("/v1/wait_until", json={"condition": "lamp.on == false"}, headers=as_claude)
        assert waited.json()["held"] is True
        assert (await client.post("/v1/wait_until", json={"condition": "x"}, headers=as_claude)).status_code == 400
        sampled = await client.post("/v1/sample", json={"targets": ["lamp.on"], "duration_s": 1}, headers=as_claude)
        assert sampled.json()["series"][0]["count"] == 2
        assert (
            await client.post("/v1/sample", json={"targets": ["lamp.x"], "duration_s": 1}, headers=as_claude)
        ).status_code == 404
        assert (await client.get("/v1/runs/caps", headers=as_claude)).json()["max_steps"] == 200
        assert (await client.post("/v1/runs/caps", json={"max_steps": 5}, headers=as_claude)).status_code == 403
        lowered = await client.post("/v1/runs/caps", json={"max_steps": 5}, headers=as_person)
        assert lowered.json()["max_steps"] == 5
