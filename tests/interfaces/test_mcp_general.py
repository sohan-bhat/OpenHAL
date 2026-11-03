"""The general MCP tools. find, wait_until, sample and runs work on any device the hub has."""

from __future__ import annotations

import httpx
import pytest
from mcp import Client as McpClient
from mcp.server.mcpserver.exceptions import ToolError

from openhal.client import AsyncClient
from openhal.drivers.mock import MockDriver
from openhal.hub.hub import Hub
from openhal.mcp import TOOL_NAMES, build_server, prompts
from openhal.mcp.server import INSTRUCTIONS
from openhal.mcp.tools import DeviceId, RunStep
from openhal.spec import loads
from tests.interfaces.conftest import BASE_URL, Tokens
from tests.interfaces.test_mcp import SIGN, tools_for

MODES = [
    RunStep(kind="write", device="heater", channel="mode", value="eco"),
    RunStep(kind="wait", seconds=0.01),
    RunStep(kind="write", device="heater", channel="mode", value="off"),
]
GENERAL = ("find", "wait_until", "sample", "run_steps", "get_run", "list_runs", "cancel_run")


def test_the_general_tools_are_listed() -> None:
    assert set(GENERAL) <= set(TOOL_NAMES)


def test_no_tool_text_names_one_device_as_if_every_hub_had_it() -> None:
    from openhal.mcp import tools

    texts = [tools.Tools.__dict__[name].__doc__ or "" for name in TOOL_NAMES]
    texts += [INSTRUCTIONS, prompts.WRITE_ROUTINE, prompts.SET_UP_DEVICE, str(DeviceId)]
    for text in texts:
        for word in ("printer", "bed_temp", "plant", "waterer", "pause-when"):
            assert word not in text
    assert "'60 %'" not in INSTRUCTIONS
    assert "<device>.<channel>" in prompts.WRITE_ROUTINE


async def test_find_wait_and_sample(async_transport: httpx.ASGITransport, tokens: Tokens, hub: Hub) -> None:
    await hub.add_and_start(loads(SIGN))
    tools = tools_for(async_transport, tokens.reader)
    found = await tools.find(kind="writable", unit="%")
    assert [match.target for match in found.matches] == ["desk-fan.fan_speed"]
    status = (await tools.find(text="status")).matches[0]
    assert isinstance(status.value, str)
    assert status.value.startswith('<device-data source="sign.status reading">')
    held = await tools.wait_until("desk-fan.temperature > -40 degC and sign.status != 'idle'", timeout_s=2)
    assert held.held
    assert held.readings[1].value.startswith("<device-data")  # type: ignore[union-attr]
    sampled = await tools.sample(["sign.status", "heater.temp"], duration_s=0.2, interval_s=0.2)
    text, number = sampled.series
    assert text.points[0].value.startswith("<device-data")
    assert number.mean is not None
    with pytest.raises(ToolError, match="UNKNOWN_TARGET"):
        await tools.wait_until("ghost.temp > 1 degC")


def test_run_steps_take_only_their_own_fields() -> None:
    assert RunStep(kind="wait", seconds=1).body() == {"kind": "wait", "seconds": 1}
    step = RunStep(kind="write", device="d", channel="c", value=0, unit="%", increment=5).body()
    assert step == {"kind": "write", "device": "d", "channel": "c", "value": 0, "unit": "%", "increment": 5}
    flash = RunStep(kind="action", device="d", action="go", args={"t": {"value": 2, "unit": "s"}}).body()
    assert flash["args"] == {"t": {"value": 2, "unit": "s"}}
    with pytest.raises(ToolError, match="A wait_until step needs timeout_s and doesn't take device"):
        RunStep(kind="wait_until", condition="d.c > 1 %", device="d").body()
    with pytest.raises(ToolError, match="A read step needs targets"):
        RunStep(kind="read").body()


async def test_a_run_through_the_tools(async_transport: httpx.ASGITransport, tokens: Tokens, hub: Hub) -> None:
    tools = tools_for(async_transport, tokens.medium)
    run = await tools.run_steps(MODES, repeat=2)
    assert (run.status, run.done_steps, run.error) == ("done", 6, None)
    assert (await tools.get_run(run.run_id, last=1)).results[0].value == "off"
    assert [item.run_id for item in await tools.list_runs()] == [run.run_id]
    assert (await tools.cancel_run(run.run_id)).status == "done"
    stranger = tools_for(async_transport, tokens.agent)
    with pytest.raises(ToolError, match=r"UNKNOWN_TARGET \(-32004\). There is no run"):
        await stranger.get_run(run.run_id)
    with pytest.raises(ToolError, match="There is no run"):
        await stranger.cancel_run(run.run_id)

    reads = await tools.run_steps([RunStep(kind="read", targets=["heater.mode", "heater.temp"])])
    assert [reading.channel for reading in reads.results[0].readings or []] == ["mode", "temp"]


async def test_a_blocked_run_carries_the_registry_error(
    async_transport: httpx.ASGITransport, tokens: Tokens, hub: Hub
) -> None:
    tools = tools_for(async_transport, tokens.medium)
    fan = RunStep(kind="write", device="desk-fan", channel="fan_speed", value=50, unit="%", increment=60)
    planned = await tools.run_steps([fan, RunStep(kind="wait", seconds=10)], repeat=2)
    assert (planned.status, planned.stop.iteration if planned.stop else None) == ("blocked", 1)
    assert planned.error is not None
    assert planned.error.name == "LIMIT_EXCEEDED"
    assert planned.error.message.startswith("fan_speed 110 % exceeds the limit of 100 %")
    driver = hub.kernel.devices["heater"].driver
    assert isinstance(driver, MockDriver)
    driver.settings.fail_writes = True
    failed = await tools.run_steps(MODES)
    assert (failed.status, failed.error.name if failed.error else None) == ("failed", "DRIVER_ERROR")


async def test_a_stopped_hub_and_the_run_cap_reach_the_agent(
    async_transport: httpx.ASGITransport, tokens: Tokens, hub: Hub
) -> None:
    tools = tools_for(async_transport, tokens.medium)
    hub.config.runs = hub.config.runs.model_copy(update={"per_agent": 1})
    long = await tools.run_steps([RunStep(kind="wait", seconds=5)], wait_s=0)
    assert long.running
    with pytest.raises(ToolError, match="already has 1 runs") as busy:
        await tools.run_steps(MODES)
    assert "(-32" not in str(busy.value)
    await tools.stop_all("test")
    ended = await tools.get_run(long.run_id, wait_s=5)
    assert (ended.status, ended.stop.code if ended.stop else None) == ("cancelled", "stopped")
    blocked = await tools.run_steps(MODES)
    assert (blocked.status, blocked.error.name if blocked.error else None) == ("blocked", "STOPPED")


async def test_a_run_that_failed_inside_the_hub_carries_no_registry_error(
    async_transport: httpx.ASGITransport, tokens: Tokens, hub: Hub, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object, **kwargs: object) -> object:
        raise RuntimeError("bug")

    monkeypatch.setattr(hub.kernel, "evaluate", broken)
    run = await tools_for(async_transport, tokens.medium).run_steps(MODES)
    assert (run.status, run.stop.code if run.stop else None, run.error) == ("failed", "internal_error", None)


async def test_the_sdk_lists_the_general_tools(async_transport: httpx.ASGITransport, tokens: Tokens) -> None:
    server, _ = build_server(
        AsyncClient(BASE_URL, tokens.medium, transport=async_transport, use_human_token_file=False)
    )
    async with McpClient(server) as client:
        listed = {tool.name: tool for tool in (await client.list_tools()).tools}
        run = listed["run_steps"]
        assert run.annotations is not None
        assert run.annotations.destructive_hint is True
        assert listed["find"].annotations.read_only_hint is True  # type: ignore[union-attr]
        steps = run.input_schema["properties"]["steps"]
        assert steps["items"]["$ref"].endswith("RunStep")
        step = run.input_schema["$defs"]["RunStep"]
        assert step["properties"]["kind"]["enum"] == ["read", "write", "action", "wait", "wait_until"]
        for name in GENERAL:
            assert len((listed[name].description or "").split(". ")) >= 2, name
        result = await client.call_tool(
            "run_steps", {"steps": [{"kind": "write", "device": "heater", "channel": "mode", "value": "eco"}]}
        )
        assert result.structured_content is not None
        assert result.structured_content["status"] == "done"
