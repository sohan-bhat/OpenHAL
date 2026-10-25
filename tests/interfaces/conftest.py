"""Fixtures for the client, CLI and MCP tests.

`hub` runs a real embedded hub with two mock devices. `async_transport` serves its API in-process
over httpx's ASGI transport. `sync_hub` runs the same hub on a background event loop so blocking
code (the sync client and the CLI) can talk to it through `BridgeTransport`. `FakeHub` answers the
ADR 0014 routes the hub doesn't have yet. Nothing here opens a socket or touches hardware.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Coroutine, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest

from openhal.hub.api import create_app
from openhal.hub.config import HubConfig
from openhal.hub.hub import Hub
from openhal.spec import loads
from tests.interfaces.fake_hub import FakeHub
from tests.kernel.conftest import FAN, HEATER, FakeClock

BASE_URL = "http://127.0.0.1:7420"
CLIENT_ADDR = ("127.0.0.1", 50000)


async def make_hub(home: Path) -> Hub:
    clock = FakeClock()
    hub = Hub(HubConfig(home=home), clock=clock, in_memory=True)
    hub.add_device(loads(FAN))
    hub.add_device(loads(HEATER))
    await hub.start(load_devices=False)
    clock.advance(60)
    return hub


@dataclass
class Tokens:
    human: str
    agent: str
    reader: str
    medium: str


def make_tokens(hub: Hub) -> Tokens:
    return Tokens(
        human=hub.tokens.create("owner", "human")[0],
        agent=hub.tokens.create("claude", "agent", "control_low")[0],
        reader=hub.tokens.create("viewer", "agent", "read")[0],
        medium=hub.tokens.create("builder", "agent", "control_medium")[0],
    )


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every test gets its own OPENHAL_HOME and no token or URL from the real environment."""
    home = tmp_path / "home"
    monkeypatch.setenv("OPENHAL_HOME", str(home))
    monkeypatch.delenv("OPENHAL_TOKEN", raising=False)
    monkeypatch.delenv("OPENHAL_URL", raising=False)
    return home


@pytest.fixture
async def hub(tmp_path: Path) -> AsyncIterator[Hub]:
    hub = await make_hub(tmp_path)
    yield hub
    await hub.close()


@pytest.fixture
def tokens(hub: Hub) -> Tokens:
    return make_tokens(hub)


@pytest.fixture
def async_transport(hub: Hub) -> httpx.ASGITransport:
    return httpx.ASGITransport(app=create_app(hub), client=CLIENT_ADDR)


class LoopThread:
    """An event loop on a background thread, for running the hub under blocking code."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, name="hub-loop", daemon=True)
        self.thread.start()

    def run[T](self, coro: Coroutine[Any, Any, T], timeout: float = 30.0) -> T:
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def close(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)
        self.loop.close()


class BridgeTransport(httpx.BaseTransport):
    """A blocking transport that hands each request to an ASGI app running on a `LoopThread`."""

    def __init__(self, app: Any, runner: LoopThread) -> None:
        self.inner = httpx.ASGITransport(app=app, client=CLIENT_ADDR)
        self.runner = runner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        content = request.read()

        async def forward() -> httpx.Response:
            forwarded = httpx.Request(request.method, request.url, headers=request.headers, content=content)
            response = await self.inner.handle_async_request(forwarded)
            body = b"".join([chunk async for chunk in response.aiter_raw()])
            return httpx.Response(response.status_code, headers=response.headers, content=body)

        return self.runner.run(forward())


@dataclass
class SyncHub:
    hub: Hub
    runner: LoopThread
    transport: BridgeTransport
    tokens: Tokens


@pytest.fixture
def sync_hub(tmp_path: Path) -> Iterator[SyncHub]:
    runner = LoopThread()
    hub = runner.run(make_hub(tmp_path / "hub"))
    try:
        yield SyncHub(hub, runner, BridgeTransport(create_app(hub), runner), make_tokens(hub))
    finally:
        runner.run(hub.close())
        runner.close()


@pytest.fixture
def fake() -> FakeHub:
    return FakeHub()


class SplitTransport(httpx.BaseTransport, httpx.AsyncBaseTransport):
    """Send ADR 0014 and proposed routes to a `FakeHub` and everything else to the real hub."""

    def __init__(
        self,
        fake: FakeHub,
        real_sync: httpx.BaseTransport | None = None,
        real_async: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.fake = fake
        self.mock = httpx.MockTransport(fake.handle)
        self.real_sync = real_sync
        self.real_async = real_async

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if self.fake.handles(request.url.path) or self.real_sync is None:
            return self.mock.handle_request(request)
        return self.real_sync.handle_request(request)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self.fake.handles(request.url.path) or self.real_async is None:
            return await self.mock.handle_async_request(request)
        return await self.real_async.handle_async_request(request)
