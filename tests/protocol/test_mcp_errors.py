"""MCP tool results carry the same error names, numbers and reasons as the protocol (ADR 0015, MCP mapping)."""

from __future__ import annotations

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from openhal.client import AsyncClient
from openhal.hub.api import create_app
from openhal.hub.hub import Hub
from openhal.mcp.tools import Step, Tools
from tests.kernel.conftest import FakeClock
from tests.protocol.conftest import websocket_client

REASON = "fan_speed 150 % exceeds the limit of 100 % (desk-fan.hal.yaml, confirmed by sohan 2026-10-24)"


async def test_mcp_and_protocol_errors_match(base_url: str, tokens: dict[str, str]) -> None:
    tools = Tools(AsyncClient(base_url, tokens["agent"], use_human_token_file=False))
    blocked = await tools.write("desk-fan", "fan_speed", 150, "%")
    assert (blocked.status, blocked.code) == ("blocked", "above_max")
    assert blocked.error is not None
    assert (blocked.error.code, blocked.error.name, blocked.error.message) == (-32010, "LIMIT_EXCEEDED", REASON)
    async with websocket_client(base_url, tokens["agent"]) as rpc:
        await rpc.initialize()
        protocol = await rpc.error(
            "hal/write", {"device": "desk-fan", "channel": "fan_speed", "value": 150, "unit": "%"}
        )
    assert blocked.error.data == protocol["data"]
    assert blocked.error.message == protocol["message"]
    dry = await tools.dry_run("desk-fan", channel="fan_speed", value=150, unit="%")
    assert dry.error is not None
    assert dry.error.message == REASON
    plan = await tools.plan_check(
        [
            Step(device="desk-fan", channel="fan_speed", value=40, unit="%"),
            Step(device="desk-fan", channel="fan_speed", value=150, unit="%"),
        ]
    )
    assert [(block.step, block.name) for block in plan.blocked] == [(1, "LIMIT_EXCEEDED")]
    assert plan.decisions[0].error is None


async def test_mcp_names_session_limits(base_url: str, tokens: dict[str, str], clock: FakeClock) -> None:
    tools = Tools(AsyncClient(base_url, tokens["agent"], use_human_token_file=False))
    assert (await tools.tighten_limits("desk-fan", "fan_speed", max={"value": 70, "unit": "%"})).ok
    clock.advance(10)
    blocked = await tools.write("desk-fan", "fan_speed", 80, "%")
    assert blocked.error is not None
    assert blocked.error.message == "fan_speed 80 % exceeds the session limit of 70 % (tightened by claude)"


async def test_mcp_in_process_falls_back_to_the_rest_view(hub: Hub, tokens: dict[str, str]) -> None:
    transport = httpx.ASGITransport(app=create_app(hub), client=("127.0.0.1", 50000))
    tools = Tools(
        AsyncClient("http://127.0.0.1:7420", tokens["agent"], transport=transport, use_human_token_file=False)
    )
    assert tools.errors.use_socket is False
    blocked = await tools.write("desk-fan", "fan_speed", 150, "%")
    assert blocked.error is not None
    assert blocked.error.name == "LIMIT_EXCEEDED"
    assert blocked.error.message == "fan_speed 150 % exceeds the limit of 100 % (desk-fan.hal.yaml)"
    done = await tools.write("desk-fan", "fan_speed", 60, "%")
    assert (done.status, done.error) == ("done", None)


async def test_refused_tool_calls_lead_with_the_registry_name(hub: Hub, tokens: dict[str, str]) -> None:
    transport = httpx.ASGITransport(app=create_app(hub), client=("127.0.0.1", 50000))
    tools = Tools(
        AsyncClient("http://127.0.0.1:7420", tokens["agent"], transport=transport, use_human_token_file=False)
    )
    with pytest.raises(ToolError, match=r"^UNKNOWN_TARGET \(-32004\)\. "):
        await tools.get_confirmation_status("feedface")
