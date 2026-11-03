"""`openhal mcp` starts and lists its tools with no token and no hub.

MCP directories and clients start the server before anyone has set OpenHAL up, and they list the
tools to show what the server does. The server starts in that state, and every tool call returns
the next step instead of crashing. With no token the error names `openhal init` and `openhal start`.
With a token and no hub the error names `openhal start`.
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import TextContent

from openhal.client import AsyncClient
from openhal.mcp import TOOL_NAMES, Tools
from openhal.mcp.tools import NOT_SET_UP
from tests.no_hardware import NO_HUB_URL

ROOT = Path(__file__).resolve().parents[2]


@asynccontextmanager
async def server(home: Path, token: str | None) -> AsyncIterator[Client]:
    """The real `openhal mcp --no-start` process with no hub at its address."""
    env = {key: value for key, value in os.environ.items() if key != "OPENHAL_TOKEN"}
    env |= {"OPENHAL_URL": NO_HUB_URL, "OPENHAL_HOME": str(home), "PYTHONPATH": str(ROOT)}
    if token is not None:
        env["OPENHAL_TOKEN"] = token
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "openhal.cli.main", "mcp", "--no-start"], env=env
    )
    with (home.parent / "mcp.log").open("w", encoding="utf-8") as log:
        async with Client(stdio_client(params, errlog=log), read_timeout_seconds=120) as client:
            yield client


def text_of(result: object) -> str:
    content = getattr(result, "content", [])
    return " ".join(block.text for block in content if isinstance(block, TextContent))


@pytest.mark.parametrize("token", [None, "${OPENHAL_TOKEN}"], ids=["no token", "unexpanded placeholder"])
async def test_with_no_token_and_no_hub_the_server_lists_every_tool(tmp_path: Path, token: str | None) -> None:
    async with server(tmp_path / "home", token=token) as client:
        listed = await client.list_tools()
        assert {tool.name for tool in listed.tools} == set(TOOL_NAMES)
        result = await client.call_tool("list_devices", {})
    assert result.is_error
    message = text_of(result)
    assert "openhal init" in message
    assert "openhal start" in message
    assert not (tmp_path / "home" / "openhal.log").exists(), "the server starts no hub without a token"


async def test_with_a_token_and_no_hub_a_tool_names_openhal_start(tmp_path: Path) -> None:
    async with server(tmp_path / "home", token="ohal_agent_example") as client:
        listed = await client.list_tools()
        assert {tool.name for tool in listed.tools} == set(TOOL_NAMES)
        result = await client.call_tool("hub_status", {})
    assert result.is_error
    assert "openhal start" in text_of(result)


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("hub_status", {}),
        ("list_devices", {}),
        ("read", {"device": "fan", "channel": "speed"}),
        ("stop_all", {"reason": "smoke"}),
    ],
)
async def test_a_tool_without_a_token_names_the_setup_steps(name: str, args: dict[str, str]) -> None:
    tools = Tools(AsyncClient(NO_HUB_URL, None, use_human_token_file=False))
    with pytest.raises(ToolError) as raised:
        await getattr(tools, name)(**args)
    assert str(raised.value) == NOT_SET_UP
