"""Live events over the WebSocket. Serves the embedded hub with uvicorn on a loopback port."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

import pytest
import uvicorn

from openhal.client import AsyncClient, Unauthorized
from openhal.hub.api import create_app
from openhal.hub.hub import Hub
from tests.interfaces.conftest import Tokens


@pytest.fixture
async def served(hub: Hub) -> AsyncIterator[str]:
    config = uvicorn.Config(create_app(hub), host="127.0.0.1", port=0, log_level="warning", lifespan="off")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:  # noqa: ASYNC110 (uvicorn exposes only a flag)
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, 5)


async def test_events_stream(served: str, tokens: Tokens) -> None:
    async with AsyncClient(served, tokens.agent, use_human_token_file=False) as client:
        events = client.events()
        hello = await asyncio.wait_for(anext(events), 5)
        assert hello == {"type": "hello", "you": {"kind": "agent", "name": "claude"}}
        await client.write("desk-fan", "fan_speed", "20 %")
        seen = []
        while not any(event.get("type") == "audit" and event.get("event") == "write" for event in seen):
            seen.append(await asyncio.wait_for(anext(events), 5))
        await events.aclose()


async def test_events_need_a_good_token(served: str) -> None:
    async with AsyncClient(served, "ohal_wrong", use_human_token_file=False) as client:
        with pytest.raises(Unauthorized):
            await asyncio.wait_for(anext(client.events()), 5)
    async with AsyncClient(served, None, use_human_token_file=False) as client:
        with pytest.raises(Unauthorized):
            await anext(client.events())
