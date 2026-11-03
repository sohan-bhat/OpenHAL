"""find, wait_until, sample and runs through the Python client, sync and async, against a real hub."""

from __future__ import annotations

import httpx
import pytest

from openhal.client import Action, AsyncClient, BadRequest, Refused, Write, calls, connect
from openhal.hub.hub import Hub
from tests.interfaces.conftest import BASE_URL, SyncHub, Tokens

MODES = [
    Write(device="heater", channel="mode", value="eco"),
    {"kind": "wait", "seconds": 0.01},
    {"device": "heater", "channel": "mode", "value": "off"},
]


def aclient(transport: httpx.AsyncBaseTransport, token: str) -> AsyncClient:
    return AsyncClient(BASE_URL, token, transport=transport, use_human_token_file=False)


async def test_find_wait_and_sample(async_transport: httpx.ASGITransport, tokens: Tokens) -> None:
    async with aclient(async_transport, tokens.reader) as hub:
        found = await hub.find(kind="writable", unit="%")
        assert [match.target for match in found.matches] == ["desk-fan.fan_speed"]
        assert found.matches[0].max == 100
        hot = await hub.find("temperature", connected=True, limit=1)
        assert (hot.count, len(hot.matches)) == (2, 1)
        assert (await hub.find(hazard="medium", kind="action")).count == 2
        held = await hub.wait_until("desk-fan.temperature > -50 degC", timeout_s=2)
        assert held.held
        assert held.readings[0].unit == "degC"
        sampled = await hub.sample(["heater.temp"], duration_s=0.4, interval_s=0.2)
        assert sampled.series[0].count == 3
        assert sampled.series[0].mean is not None
        with pytest.raises(BadRequest, match="doesn't parse"):
            await hub.wait_until("heater.temp >")


async def test_runs_and_caps(async_transport: httpx.ASGITransport, tokens: Tokens, hub: Hub) -> None:
    async with aclient(async_transport, tokens.medium) as agent:
        run = await agent.run_steps(MODES, repeat=2)
        assert run.ok
        assert not run.running
        assert [result.value for result in run.results if result.kind == "write"] == ["eco", "off", "eco", "off"]
        again = await agent.run(run.run_id, wait_s=1, last=1)
        assert len(again.results) == 1
        assert [item.run_id for item in await agent.runs()] == [run.run_id]
        assert (await agent.cancel_run(run.run_id)).status == "done"
        blocked = await agent.run_steps(
            [{"kind": "write", "device": "desk-fan", "channel": "fan_speed", "value": 500, "unit": "%"}]
        )
        assert blocked.stop is not None
        assert blocked.stop.decision is not None
        assert blocked.stop.decision.code == "above_max"
        assert (await agent.run_caps()).max_points == 1000
        with pytest.raises(Refused, match="human principal"):
            await agent.set_run_caps(max_steps=5)
    async with aclient(async_transport, tokens.human) as person:
        lowered = await person.set_run_caps(per_agent=1)
        assert lowered.changed == {"per_agent": {"from": 2, "to": 1}}
        with pytest.raises(BadRequest, match="phrase confirm"):
            await person.set_run_caps(per_agent=3)
        assert (await person.set_run_caps(per_agent=3, phrase="confirm")).per_agent == 3


def test_waiting_calls_get_their_own_timeout() -> None:
    assert calls.wait_until("a.b == true", timeout_s=40).timeout == 70
    assert calls.sample(["a.b"], duration_s=10).timeout == 40
    assert calls.start_run([], wait_s=5).timeout == 35
    assert calls.run("run-x", wait_s=2).timeout == 32
    assert calls.find().timeout is None
    assert calls.find(connected=False).params == {"limit": 50, "connected": "false"}
    assert calls.step_body(Action(device="d", action="go")) == {
        "kind": "action",
        "device": "d",
        "action": "go",
        "args": {},
    }
    assert calls.step_body({"kind": "wait", "seconds": 1}) == {"kind": "wait", "seconds": 1}
    assert calls.step_body({"kind": "write", "device": "d", "channel": "c", "value": {"value": 5, "unit": "%"}}) == {
        "kind": "write",
        "device": "d",
        "channel": "c",
        "value": 5,
        "unit": "%",
    }
    assert calls.set_run_caps(max_seconds=60, phrase="confirm").json == {"max_seconds": 60, "phrase": "confirm"}


def test_the_sync_client_runs_steps(sync_hub: SyncHub) -> None:
    with connect(BASE_URL, sync_hub.tokens.medium, transport=sync_hub.transport) as hub:
        assert hub.find("fan").count == 2
        run = hub.run_steps(MODES)
        assert run.ok
        assert hub.run(run.run_id).done_steps == 3
        assert hub.runs()[0].run_id == run.run_id
        assert hub.cancel_run(run.run_id).status == "done"
        assert hub.wait_until("heater.mode == off", timeout_s=1).held
        assert hub.sample(["heater.mode"], duration_s=0.2, interval_s=0.2).series[0].last == "off"
        assert hub.run_caps().per_agent == 2
        with pytest.raises(Refused):
            hub.set_run_caps(per_agent=1)
