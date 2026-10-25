"""The rig `openhal demo --full` runs on. A simulated board, a hub in a temporary home and an MCP session.

`plugged_in()` puts a simulated board behind `sim:<device>` and lists that port for discovery, as
a person would list a board's port in OPENHAL_FIRMWARE_PORTS. `running_hub()` serves a real hub on
a free loopback port. `mcp_session()` starts `openhal mcp` with an agent token and talks to it as
an MCP client over its stdio. `Board` reports what the simulated board received.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any, Final, TextIO

from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp_types import Implementation

import openhal
from openhal import __version__
from openhal.demo import scenario
from openhal.drivers.openhal_firmware.driver import PORTS_ENV
from openhal.drivers.openhal_firmware.protocol import ProtocolError, decode
from openhal.drivers.openhal_firmware.simulator import SIMULATORS, PlantWatererSimulator
from openhal.hub.config import HubConfig
from openhal.hub.hub import Hub
from openhal.hub.tokens import TokenStore, write_secret_file

MCP_COMMAND: Final = ("openhal", "mcp", "--no-start")
MCP_TIMEOUT_S: Final = 120.0
"""How long one MCP request may take. Starting `openhal mcp` on a busy machine can take a while."""
PACKAGE_ROOT: Final = Path(openhal.__file__).resolve().parents[1]
"""The folder holding the openhal package, put on the MCP server's import path."""
QUIET_VERBS: Final = frozenset({"HB", "READ"})
"""Heartbeats and reads, which the hub sends on its own schedule. Every other line is reported."""


class DemoError(RuntimeError):
    """The system didn't do what the demo expects. The message says which step and what happened."""


def set_up_home(home: Path, person: str) -> str:
    """A fresh home with the person's token, as `openhal init` makes it. Returns the token."""
    config = HubConfig(home=home)
    config.ensure_dirs()
    store = TokenStore(config.db_path)
    try:
        token, _ = store.create(person, "human")
    finally:
        store.close()
    write_secret_file(config.human_token_path, token)
    return token


@contextlib.contextmanager
def plugged_in(device: str, board: PlantWatererSimulator) -> Iterator[str]:
    """The simulated board behind `sim:<device>`, with that port listed for discovery. Yields the port."""
    port = f"sim:{device}"
    previous_board = SIMULATORS.get(device)
    previous_ports = os.environ.get(PORTS_ENV)
    SIMULATORS[device] = board
    os.environ[PORTS_ENV] = port
    try:
        yield port
    finally:
        if previous_board is None:
            SIMULATORS.pop(device, None)
        else:
            SIMULATORS[device] = previous_board
        if previous_ports is None:
            os.environ.pop(PORTS_ENV, None)
        else:
            os.environ[PORTS_ENV] = previous_ports


@contextlib.asynccontextmanager
async def running_hub(home: Path) -> AsyncIterator[str]:
    """A hub on `home`, served on a free loopback port. Yields its base URL."""
    hub = Hub(HubConfig(home=home))
    try:
        await hub.start()
        async with scenario.served(hub) as socket_url:
            yield "http" + socket_url.removeprefix("ws").removesuffix("/rpc")
    finally:
        await hub.close()


class Board:
    """What the simulated board received, as lines without their sequence number and checksum."""

    def __init__(self, simulator: PlantWatererSimulator) -> None:
        self.simulator = simulator
        self._mark = 0

    def mark(self) -> None:
        """Start a new step. `received()` reports lines from here on."""
        self._mark = len(self.simulator.received)

    def received(self) -> list[str]:
        found = []
        for line in self.simulator.received[self._mark :]:
            try:
                message = decode(line)
            except ProtocolError:
                continue
            if message.verb not in QUIET_VERBS:
                found.append(" ".join((message.verb, *message.args)).strip())
        return found

    async def settle(self, deadline: float) -> None:
        """Wait until the pump has stopped on its own."""
        while self.simulator.pumping:
            if time.monotonic() > deadline:
                raise DemoError("The pump kept running past the end of its watering.")
            await asyncio.sleep(max(self.simulator.remaining_s(), 0.01))


class Agent:
    """A real MCP client session with `openhal mcp`. A tool error stops the demo."""

    def __init__(self, client: Client) -> None:
        self.client = client

    async def call(self, tool: str, arguments: dict[str, Any]) -> Any:
        result = await self.client.call_tool(tool, arguments)
        if result.is_error:
            text = " ".join(getattr(block, "text", "") for block in result.content)
            raise DemoError(f"The MCP tool {tool} failed. {text}")
        data = result.structured_content
        if isinstance(data, dict) and set(data) == {"result"}:
            return data["result"]
        return data


@contextlib.asynccontextmanager
async def mcp_session(url: str, token: str, home: Path) -> AsyncIterator[Agent]:
    """Start `openhal mcp --no-start` with the agent token and open a client session over its stdio.

    The server gets the agent token in OPENHAL_TOKEN and this home in OPENHAL_HOME, so it never
    sees the person's token or a real home. What it writes to stderr goes to mcp.log in the home.
    """
    paths = [str(PACKAGE_ROOT), *filter(None, [os.environ.get("PYTHONPATH")])]
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "openhal.cli.main", *MCP_COMMAND[1:]],
        env={
            "OPENHAL_TOKEN": token,
            "OPENHAL_URL": url,
            "OPENHAL_HOME": str(home),
            "PYTHONPATH": os.pathsep.join(paths),
        },
    )
    log = await asyncio.to_thread((home / "mcp.log").open, "w", encoding="utf-8")
    try:
        async with Client(
            stdio_client(server, errlog=log),
            read_timeout_seconds=MCP_TIMEOUT_S,
            client_info=Implementation(name="openhal-demo", version=__version__),
        ) as client:
            yield Agent(client)
    except Exception as exc:
        inner = _innermost(exc)
        if isinstance(inner, DemoError):
            raise inner from exc
        raise DemoError(f"The agent's MCP session stopped ({type(inner).__name__}: {inner}). {_tail(log)}") from exc
    finally:
        log.close()


def _innermost(exc: BaseException) -> BaseException:
    while isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
        exc = exc.exceptions[0]
    return exc


def _tail(log: TextIO) -> str:
    log.flush()
    text = Path(log.name).read_text(encoding="utf-8").strip()
    return f"openhal mcp said {text[-600:]}" if text else "openhal mcp said nothing."
