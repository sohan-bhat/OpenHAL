"""The Python client against a fake of the ADR 0014 routes and the proposed token and pairing routes."""

from __future__ import annotations

import httpx
import pytest

from openhal.client import AsyncClient, Client, NotFound, Refused
from tests.interfaces.conftest import BASE_URL
from tests.interfaces.fake_hub import AGENT, HUMAN, READER, FakeHub


def sync_client(fake: FakeHub, token: str) -> Client:
    return Client(BASE_URL, token, transport=httpx.MockTransport(fake.handle), use_human_token_file=False)


def test_discovery(fake: FakeHub) -> None:
    with sync_client(fake, AGENT) as hub:
        result = hub.discover(["mock", "serial"])
        assert result.matched[0].device_id == "desk-fan"
        assert result.errors[0].driver == "ble"
        assert hub.unknown_devices()[0].id == "u1"
    assert fake.calls[0] == ("POST", "/v1/discover", {"drivers": ["mock", "serial"]})


def test_routines_follow_the_who_column(fake: FakeHub) -> None:
    with sync_client(fake, AGENT) as agent, sync_client(fake, HUMAN) as human, sync_client(fake, READER) as reader:
        with pytest.raises(Refused):
            reader.create_routine("cool-room", "steps: []")
        drafted = agent.create_routine("cool-room", "steps: []")
        assert drafted.enabled is False
        assert drafted.drafted_by == "agent:claude"
        assert [routine.id for routine in agent.routines()] == ["cool-room"]
        assert agent.routine("cool-room").source == "steps: []"
        assert agent.routine_dry_run("cool-room").ok
        with pytest.raises(Refused, match="human"):
            agent.enable_routine("cool-room")
        assert human.enable_routine("cool-room").enabled
        assert agent.disable_routine("cool-room").enabled is False
        with pytest.raises(Refused):
            agent.run_routine("cool-room")
        run = human.run_routine("cool-room")
        assert run.status == "ok"
        assert run.steps[0].ok
        assert human.routine("cool-room").last_run is not None
        assert human.approve_routine("cool-room", "desk-fan").signature
        with pytest.raises(Refused):
            agent.delete_routine("cool-room")
        assert human.delete_routine("cool-room").ok
        with pytest.raises(NotFound):
            human.routine("cool-room")


def test_agent_enable_opt_in(fake: FakeHub) -> None:
    fake.agent_enable_low_hazard = True
    with sync_client(fake, AGENT) as agent:
        agent.create_routine("lights", "steps: []")
        assert agent.enable_routine("lights").enabled


async def test_driver_writer_async(fake: FakeHub) -> None:
    transport = httpx.MockTransport(fake.handle)
    async with (
        AsyncClient(BASE_URL, AGENT, transport=transport, use_human_token_file=False) as agent,
        AsyncClient(BASE_URL, HUMAN, transport=transport, use_human_token_file=False) as human,
    ):
        session = await agent.start_writer(unknown_id="u1", sketch_path="/tmp/fan.ino")
        assert session.status == "drafting"
        assert session.sources[0].startswith("<device-data")
        proposed = await agent.propose(session.id, "device: Fan\n")
        assert proposed.unconfirmed == ["write.fan_speed.max"]
        questions = (await agent.interview(session.id)).questions
        assert questions[0].unit == "percent"
        with pytest.raises(Refused):
            await agent.answer(session.id, {"q1": "80 %"})
        assert (await human.answer(session.id, {"q1": "80 %"})).status == "ready"
        with pytest.raises(Refused):
            await agent.finish(session.id)
        finished = await human.finish(session.id, save_as="desk-fan")
        assert finished.writable
        assert (await agent.writer_session(session.id)).status == "saved"
        assert (await agent.test_plan(session.id)).steps[0].needs_approval
        await agent.discover()
        assert (await agent.unknown_devices())[0].label == "Arduino Uno"
        assert len(await agent.routines()) == 0
        drafted = await agent.create_routine("night", "steps: []")
        assert (await agent.routine(drafted.id)).enabled is False
        assert (await agent.routine_dry_run("night")).ok
        assert (await human.enable_routine("night")).enabled
        assert (await agent.disable_routine("night")).enabled is False
        assert (await human.run_routine("night")).status == "ok"
        assert (await human.approve_routine("night", "desk-fan")).routine == "night"
        assert (await human.delete_routine("night")).ok


async def test_tokens_and_pairing(fake: FakeHub) -> None:
    transport = httpx.MockTransport(fake.handle)
    async with (
        AsyncClient(BASE_URL, HUMAN, transport=transport, use_human_token_file=False) as human,
        AsyncClient(BASE_URL, AGENT, transport=transport, use_human_token_file=False) as agent,
    ):
        created = await human.create_token("claude", kind="agent", scope="control_low")
        assert created.token.startswith("ohal_")
        assert [info.name for info in await human.tokens()] == ["claude"]
        assert (await human.revoke_token(created.token_id)).ok
        with pytest.raises(NotFound):
            await human.revoke_token(created.token_id)
        assert (await human.new_pairing_code()).code == "123456"
        with pytest.raises(Refused):
            await agent.create_token("sneaky", kind="human")
        with pytest.raises(Refused):
            await agent.new_pairing_code()


def test_sync_tokens(fake: FakeHub) -> None:
    with sync_client(fake, HUMAN) as human:
        created = human.create_token("cursor", scope="read")
        assert human.tokens()[0].scope == "read"
        assert human.revoke_token(created.token_id).ok
        assert human.new_pairing_code().expires_in_s == 300
        session = human.start_writer(driver="scpi", params={"address": "TCPIP::1"}, manual_text="VOLT 0 to 30")
        assert human.writer_session(session.id).detected["driver"] == "scpi"
        assert human.propose(session.id, "device: x\n").status == "interview"
        assert human.interview(session.id).questions
        assert human.answer(session.id, {"q1": 10}).status == "ready"
        assert human.finish(session.id).device_id == "desk-fan"
        assert human.test_plan(session.id).steps
