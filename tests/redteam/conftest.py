"""Fixtures for the red team. A real embedded hub with mock devices and a client for every interface.

The hub has a low hazard fan with a rate limit, a medium hazard heater with an interlock on the fan,
a high hazard laser, and a draft lamp whose limits nobody confirmed. Every driver is the in-memory
mock, so nothing here touches hardware. `writes(hub, device)` lists what reached a mock transport.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Callable, Coroutine, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from openhal.cli import _common
from openhal.cli.main import app as cli_app
from openhal.client import AsyncClient
from openhal.drivers.mock import MockDriver
from openhal.hub.api import create_app
from openhal.hub.config import HubConfig
from openhal.hub.hub import Hub
from openhal.mcp import Tools
from openhal.spec import loads
from tests.interfaces.conftest import BridgeTransport, LoopThread
from tests.kernel.conftest import AddDevice as AddDevice
from tests.kernel.conftest import FakeClock
from tests.kernel.conftest import add as add
from tests.kernel.conftest import kernel as kernel
from tests.protocol.conftest import base_url, transport  # noqa: F401

BASE_URL = "http://127.0.0.1:7420"
CLIENT_ADDR = ("127.0.0.1", 50000)

FAN = """
device: Desk fan
id: desk-fan
connect: { mock: fan, initial: { fan_speed: 20, temperature: 24.0 } }
read:
  temperature: { unit: degC, every: 1 s }
  status: { type: string }
write:
  fan_speed: { unit: "%", min: 0, max: 100, step: 1, max_change_per_s: 20 }
actions:
  spin_test:
    args:
      seconds: { unit: s, min: 1, max: 30 }
    confirm: confirm
safe_state: { fan_speed: 0 }
hazard: low
notes: Mounted on the desk.
confirmed: { by: sohan, at: 2026-10-24 }
"""

HEATER = """
device: Curing heater
id: heater
connect: { mock: heater }
read:
  temp: { unit: degC, every: 1 s }
write:
  power: { unit: W, min: 0, max: 60 }
  setpoint: { unit: degC, min: 0, max: 30 }
  current: { unit: A, min: 0, max: 2 }
  duty: { unit: dimensionless, min: 0, max: 0.5 }
  mode: { type: enum, values: [off, eco, full] }
  enabled: { type: bool }
  label: { type: string, max_length: 8, pattern: "^[a-z]+$" }
actions:
  pulse:
    args:
      seconds: { unit: s, min: 1, max: 10 }
    require: ["enabled == true"]
    confirm: confirm
  purge: { confirm: confirm-each-time, effects: [power] }
safe_state: { power: 0 }
interlocks:
  - if: "power > 0 W"
    require: "desk-fan.fan_speed >= 30 %"
    message: "The heater needs the fan at 30 % or more."
hazard: medium
confirmed: { by: sohan, at: 2026-10-24 }
"""

LASER = """
device: Laser cutter
id: laser
connect: { mock: laser, initial: { door_closed: true } }
read:
  door_closed: { type: bool }
write:
  power: { unit: "%", min: 0, max: 30 }
actions:
  home: {}
safe_state: { power: 0 }
interlocks:
  - if: "power > 0 %"
    require: "door_closed == true"
hazard: high
confirmed: { by: sohan, at: 2026-10-24 }
"""

DRAFT = """
device: Draft lamp
id: draft-lamp
connect: { mock: lamp }
write:
  brightness: { unit: "%", min: 0, max: 100 }
"""


@dataclass
class Tokens:
    """One token per kind of caller. `agent` and `other` are two different agents."""

    human: str
    agent: str
    low: str
    reader: str
    other: str


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
async def hub(tmp_path: Path, clock: FakeClock) -> AsyncIterator[Hub]:
    hub = Hub(HubConfig(home=tmp_path), clock=clock, in_memory=True)
    for text in (FAN, HEATER, LASER, DRAFT):
        hub.add_device(loads(text))
    await hub.start(load_devices=False)
    clock.advance(60)
    await fresh(hub)
    yield hub
    await hub.close()


async def fresh(hub: Hub) -> None:
    """Read every device again, so readings are current on the fake clock."""
    for device in hub.kernel.devices:
        await hub.kernel.snapshot(device)


@pytest.fixture
def tokens(hub: Hub) -> Tokens:
    return Tokens(
        human=hub.tokens.create("sohan", "human")[0],
        agent=hub.tokens.create("claude", "agent", "control_medium")[0],
        low=hub.tokens.create("helper", "agent", "control_low")[0],
        reader=hub.tokens.create("viewer", "agent", "read")[0],
        other=hub.tokens.create("other", "agent", "control_medium")[0],
    )


Rest = Callable[..., contextlib.AbstractAsyncContextManager[httpx.AsyncClient]]


@pytest.fixture
def rest(hub: Hub) -> Rest:
    """Open an HTTP client on the hub's REST API, as a bearer token, a session cookie or nobody."""
    app = create_app(hub)

    @contextlib.asynccontextmanager
    async def open_client(
        token: str | None = None, *, cookie: str | None = None, headers: dict[str, str] | None = None
    ) -> AsyncIterator[httpx.AsyncClient]:
        sent = dict(headers or {})
        if token is not None:
            sent["Authorization"] = f"Bearer {token}"
        cookies = {"openhal_session": cookie} if cookie is not None else None
        asgi = httpx.ASGITransport(app=app, client=CLIENT_ADDR)
        async with httpx.AsyncClient(transport=asgi, base_url=BASE_URL, headers=sent, cookies=cookies) as client:
            yield client

    return open_client


@pytest.fixture
def python_client(hub: Hub) -> Callable[[str], AsyncClient]:
    """The Python library's async client, as a given token, never falling back to the human token file."""
    app = create_app(hub)

    def make(token: str) -> AsyncClient:
        asgi = httpx.ASGITransport(app=app, client=CLIENT_ADDR)
        return AsyncClient(BASE_URL, token, transport=asgi, use_human_token_file=False)

    return make


@pytest.fixture
def mcp_tools(python_client: Callable[[str], AsyncClient]) -> Callable[[str], Tools]:
    """The MCP tools exactly as an agent calls them, bound to a token."""

    def make(token: str) -> Tools:
        return Tools(python_client(token))

    return make


@dataclass
class CliHub:
    """A hub on a background loop that the blocking CLI talks to, and a way to run hub code on that loop."""

    hub: Hub
    loop: LoopThread
    tokens: Tokens

    def run[T](self, coro: Coroutine[Any, Any, T]) -> T:
        return self.loop.run(coro)


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[CliHub]:
    """The CLI against a real hub, with OPENHAL_TOKEN set to the agent token and no human token file."""
    loop = LoopThread()
    clock = FakeClock()

    async def build() -> Hub:
        hub = Hub(HubConfig(home=tmp_path / "hub"), clock=clock, in_memory=True)
        for text in (FAN, HEATER, LASER, DRAFT):
            hub.add_device(loads(text))
        await hub.start(load_devices=False)
        clock.advance(60)
        await fresh(hub)
        return hub

    hub = loop.run(build())
    issued = Tokens(
        human=hub.tokens.create("sohan", "human")[0],
        agent=hub.tokens.create("claude", "agent", "control_medium")[0],
        low=hub.tokens.create("helper", "agent", "control_low")[0],
        reader=hub.tokens.create("viewer", "agent", "read")[0],
        other=hub.tokens.create("other", "agent", "control_medium")[0],
    )
    monkeypatch.setattr(_common, "TRANSPORT", BridgeTransport(create_app(hub), loop))
    monkeypatch.setenv("OPENHAL_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("OPENHAL_TOKEN", issued.agent)
    monkeypatch.delenv("OPENHAL_URL", raising=False)
    try:
        yield CliHub(hub, loop, issued)
    finally:
        loop.run(hub.close())
        loop.close()


def run_cli(*args: str, input: str | None = None) -> tuple[int, str]:
    result = CliRunner().invoke(cli_app, list(args), input=input)
    return result.exit_code, result.output


def driver(hub: Hub, device: str) -> MockDriver:
    found = hub.kernel.devices[device].driver
    assert isinstance(found, MockDriver)
    return found


def writes(hub: Hub, device: str) -> list[tuple[str, str, Any]]:
    """Every operation that would have changed hardware on one mock device."""
    return driver(hub, device).hardware_writes()


def value(hub: Hub, device: str, channel: str) -> Any:
    return driver(hub, device).values.get(channel)


def done_by_clients(hub: Hub) -> list[tuple[str, str | None, str | None]]:
    """Writes and actions that ran for any principal except the hub itself (safe states, watchdogs)."""
    return [
        (entry.principal, entry.device, entry.target)
        for entry in hub.audit.entries(limit=10_000)
        if entry.event in ("write", "action") and entry.status == "done" and entry.principal != "system:kernel"
    ]
