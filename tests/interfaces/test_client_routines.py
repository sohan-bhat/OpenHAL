"""The Python client against the real routine, discovery and pairing code routes."""

from __future__ import annotations

import httpx
import pytest

from openhal.client import AsyncClient, BadRequest, NotFound, Refused, connect
from tests.interfaces.conftest import BASE_URL, SyncHub, Tokens

KEEP_COOL = """
id: keep-cool
triggers:
  - every: 30 s
steps:
  - if: "desk-fan.temperature > 28 degC"
    then:
      - write: { device: desk-fan, channel: fan_speed, value: 20 % }
    else:
      - write: { device: desk-fan, channel: fan_speed, value: 10 % }
"""


def aclient(transport: httpx.AsyncBaseTransport, token: str) -> AsyncClient:
    return AsyncClient(BASE_URL, token, transport=transport, use_human_token_file=False)


async def test_routines_follow_the_who_column(async_transport: httpx.ASGITransport, tokens: Tokens) -> None:
    async with (
        aclient(async_transport, tokens.agent) as agent,
        aclient(async_transport, tokens.human) as human,
        aclient(async_transport, tokens.reader) as reader,
    ):
        drafted = await agent.create_routine("keep-cool", KEEP_COOL)
        assert drafted.enabled is False
        assert drafted.drafted_by == "agent:claude"
        assert drafted.source.startswith("<device-data")
        assert drafted.source_raw == KEEP_COOL
        assert drafted.triggers == ["every 30 s"]
        summaries = await reader.routines()
        assert [item.id for item in summaries] == ["keep-cool"]
        assert summaries[0].devices == ["desk-fan"]
        dry = await agent.routine_dry_run("keep-cool")
        assert dry.ok, dry.problems
        assert {decision.status for decision in dry.decisions} == {"allowed"}
        with pytest.raises(Refused, match="human"):
            await agent.enable_routine("keep-cool")
        enabled = await human.enable_routine("keep-cool")
        assert enabled.enabled
        assert enabled.enabled_by
        with pytest.raises(Refused):
            await reader.disable_routine("keep-cool")
        disabled = await agent.disable_routine("keep-cool")
        assert disabled.enabled is False
        assert disabled.disabled_reason
        with pytest.raises(Refused):
            await agent.run_routine("keep-cool")
        run = await human.run_routine("keep-cool")
        assert run.routine_id == "keep-cool"
        assert run.trigger == "manual"
        assert run.status == "ok", run.message
        detail = await human.routine("keep-cool")
        assert detail.last_run is not None
        assert detail.history
        approval = await human.approve_routine("keep-cool", "heater")
        assert approval.routine == "keep-cool"
        assert approval.sha256 == detail.sha256
        with pytest.raises(Refused):
            await agent.approve_routine("keep-cool", "heater")
        with pytest.raises(Refused):
            await agent.delete_routine("keep-cool")
        assert (await human.delete_routine("keep-cool")).ok
        with pytest.raises(NotFound):
            await human.routine("keep-cool")
        with pytest.raises(BadRequest):
            await agent.create_routine("broken", "steps: [ { nope: 1 } ]")


async def test_discovery_and_pairing_code(async_transport: httpx.ASGITransport, tokens: Tokens) -> None:
    async with aclient(async_transport, tokens.agent) as agent, aclient(async_transport, tokens.human) as human:
        assert await agent.unknown_devices() == []
        result = await agent.discover(["mock"])
        assert result.errors == []
        assert len(await agent.unknown_devices()) == len(result.unknown)
        with pytest.raises(Refused):
            await agent.new_pairing_code()
        code = await human.new_pairing_code()
        assert code.code.isdigit()
        assert code.expires_in_s == 300
        assert (await agent.pair(code.code)).ok


def test_sync_routines(sync_hub: SyncHub) -> None:
    with (
        connect(BASE_URL, sync_hub.tokens.agent, transport=sync_hub.transport) as agent,
        connect(BASE_URL, sync_hub.tokens.human, transport=sync_hub.transport) as human,
    ):
        agent.create_routine("keep-cool", KEEP_COOL)
        assert agent.routines()[0].kind == "yaml"
        assert agent.routine("keep-cool").sha256
        assert agent.routine_dry_run("keep-cool").ok
        assert human.enable_routine("keep-cool").enabled
        assert agent.disable_routine("keep-cool").enabled is False
        assert human.run_routine("keep-cool").steps
        assert human.approve_routine("keep-cool", "heater").signature
        assert human.delete_routine("keep-cool").ok
        assert agent.discover(["mock"]).errors == []
        assert isinstance(agent.unknown_devices(), list)
        assert human.new_pairing_code().code.isdigit()
