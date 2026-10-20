"""The Python client against a fake of the driver writer routes and the proposed token routes."""

from __future__ import annotations

import httpx
import pytest

from openhal.client import AsyncClient, Client, NotFound, Refused
from tests.interfaces.conftest import BASE_URL
from tests.interfaces.fake_hub import AGENT, HUMAN, FakeHub


def sync_client(fake: FakeHub, token: str) -> Client:
    return Client(BASE_URL, token, transport=httpx.MockTransport(fake.handle), use_human_token_file=False)


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


async def test_tokens(fake: FakeHub) -> None:
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
        with pytest.raises(Refused):
            await agent.create_token("sneaky", kind="human")


def test_sync_tokens(fake: FakeHub) -> None:
    with sync_client(fake, HUMAN) as human:
        created = human.create_token("cursor", scope="read")
        assert human.tokens()[0].scope == "read"
        assert human.revoke_token(created.token_id).ok
        session = human.start_writer(driver="scpi", params={"address": "TCPIP::1"}, manual_text="VOLT 0 to 30")
        assert human.writer_session(session.id).detected["driver"] == "scpi"
        assert human.propose(session.id, "device: x\n").status == "interview"
        assert human.interview(session.id).questions
        assert human.answer(session.id, {"q1": 10}).status == "ready"
        assert human.finish(session.id).device_id == "desk-fan"
        assert human.test_plan(session.id).steps
