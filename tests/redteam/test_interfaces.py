"""Attack family 1. An agent tries the four forbidden moves through every interface.

The moves are a write above a confirmed limit, approving a request, unlocking after a stop, and
loosening a limit. Every interface must refuse all four, and no mock transport may see a byte.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from openhal.client import AsyncClient, OpenHALError
from openhal.hub.hub import Hub
from openhal.kernel import Action, agent, human
from openhal.mcp import TOOL_NAMES, Tools
from tests.protocol.conftest import Connect
from tests.redteam.conftest import CliHub, Rest, Tokens, done_by_clients, run_cli, value, writes

ABOVE = {"device": "desk-fan", "channel": "fan_speed", "value": 150, "unit": "%"}
OK30 = {"device": "desk-fan", "channel": "fan_speed", "value": 30, "unit": "%"}
SPIN = {"device": "desk-fan", "action": "spin_test", "args": {"seconds": {"value": 2, "unit": "s"}}}


async def queue_request(hub: Hub) -> str:
    """An agent asks for an action that needs a person, so a request waits in the queue."""
    decision = await hub.kernel.execute(Action(**SPIN), agent("claude", "control_medium"))
    assert decision.status == "pending", decision
    assert decision.request_id is not None
    return decision.request_id


def untouched(hub: Hub) -> None:
    """Nothing but the safe state reached the fan, and no principal but the hub itself changed anything."""
    assert all(entry == ("write", "fan_speed", 0.0) for entry in writes(hub, "desk-fan"))
    assert value(hub, "desk-fan", "fan_speed") in (20, 0.0)
    assert done_by_clients(hub) == []


async def test_rest_refuses_all_four(hub: Hub, rest: Rest, tokens: Tokens) -> None:
    request_id = await queue_request(hub)
    async with rest(tokens.agent) as client:
        blocked = (await client.post("/v1/write", json=ABOVE)).json()
        assert (blocked["status"], blocked["code"]) == ("blocked", "above_max")
        assert (await client.post(f"/v1/confirmations/{request_id}/approve")).status_code == 403
        assert (await client.post(f"/v1/confirmations/{request_id}/reject", json={})).status_code == 403
        assert (await client.post("/v1/stop", json={"reason": "agent stop"})).status_code == 200
        assert (await client.post("/v1/unlock", json={"phrase": "unlock"})).status_code == 403
        loosen = await client.post(
            "/v1/tighten",
            json={"device": "desk-fan", "channel": "fan_speed", "max": {"value": 150, "unit": "%"}},
        )
        assert loosen.json()["code"] == "cannot_loosen"
    assert hub.kernel.stopped
    assert hub.kernel.queue.get(request_id).status == "cancelled"
    untouched(hub)


async def test_rest_without_a_token_gets_nothing(hub: Hub, rest: Rest) -> None:
    async with rest() as client:
        assert (await client.post("/v1/write", json=ABOVE)).status_code == 401
        assert (await client.post("/v1/stop", json={})).status_code == 401
    async with rest("ohal_forged-token-that-was-never-issued") as client:
        assert (await client.post("/v1/write", json=OK30)).status_code == 401
    untouched(hub)


async def test_rest_read_only_token_cannot_write(hub: Hub, rest: Rest, tokens: Tokens) -> None:
    async with rest(tokens.reader) as client:
        decision = (await client.post("/v1/write", json=OK30)).json()
    assert (decision["status"], decision["code"]) == ("blocked", "not_permitted")
    untouched(hub)


async def test_python_client_refuses_all_four(
    hub: Hub, python_client: Callable[[str], AsyncClient], tokens: Tokens
) -> None:
    request_id = await queue_request(hub)
    async with python_client(tokens.agent) as client:
        decision = await client.write("desk-fan", "fan_speed", 150, "%")
        assert (decision.status, decision.code) == ("blocked", "above_max")
        with pytest.raises(OpenHALError):
            await client.approve(request_id)
        await client.stop("agent stop")
        with pytest.raises(OpenHALError):
            await client.unlock("unlock")
        result = await client.tighten("desk-fan", "fan_speed", max={"value": 150, "unit": "%"})
        assert (result.ok, result.code) == (False, "cannot_loosen")
        ramp = await client.write("desk-fan", "fan_speed", 101, "%")
        assert ramp.code == "stopped"
    assert hub.kernel.stopped
    untouched(hub)


async def test_mcp_tools_refuse_all_four(hub: Hub, mcp_tools: Callable[[str], Tools], tokens: Tokens) -> None:
    tools = mcp_tools(tokens.agent)
    decision = await tools.write("desk-fan", "fan_speed", 150, "%")
    assert (decision.status, decision.code) == ("blocked", "above_max")
    assert decision.error is not None
    assert decision.error.name == "LIMIT_EXCEEDED"
    powers = ("approve", "confirm_", "reject", "unlock", "token", "pair", "answer", "finish", "enable_python")
    assert not [name for name in TOOL_NAMES if name.startswith(powers) or name.endswith(powers)]
    loosen = await tools.tighten_limits("desk-fan", "fan_speed", max={"value": 150, "unit": "%"})
    assert (loosen.ok, loosen.code) == (False, "cannot_loosen")
    report = await tools.stop_all("agent stop")
    assert report.by == "agent:claude"
    assert hub.kernel.stopped
    untouched(hub)


async def test_mcp_refuses_to_run_as_a_human(hub: Hub, mcp_tools: Callable[[str], Tools], tokens: Tokens) -> None:
    tools = mcp_tools(tokens.human)
    with pytest.raises(ToolError, match="human token"):
        await tools.write("desk-fan", "fan_speed", 30, "%")
    untouched(hub)


async def test_protocol_refuses_all_four(transport: Connect, hub: Hub, tokens: Tokens) -> None:
    request_id = await queue_request(hub)
    async with transport() as rpc:
        await rpc.initialize(tokens.agent)
        error = await rpc.error("hal/write", ABOVE)
        assert error["data"]["name"] == "LIMIT_EXCEEDED"
        error = await rpc.error("hal/confirmations/approve", {"requestId": request_id})
        assert error["data"]["name"] == "SCOPE_DENIED"
        error = await rpc.error("hal/confirmations/reject", {"requestId": request_id})
        assert error["data"]["name"] == "SCOPE_DENIED"
        await rpc.call("hal/stop", {"reason": "agent stop"})
        error = await rpc.error("hal/unlock", {"phrase": "unlock"})
        assert error["data"]["name"] == "SCOPE_DENIED"
        for method in ("hal/tighten", "hal/limits/set", "hal/devices/update", "hal/tokens/create"):
            error = await rpc.error(method, {"device": "desk-fan", "channel": "fan_speed", "max": "150 %"})
            assert error["data"]["name"] == "METHOD_NOT_FOUND"
    assert hub.kernel.stopped
    untouched(hub)


async def test_protocol_token_in_params_cannot_override_a_header(transport: Connect, hub: Hub, tokens: Tokens) -> None:
    async with transport(tokens.reader) as rpc:
        result = await rpc.initialize(tokens.human)
        assert result["principal"]["kind"] == "agent"
        error = await rpc.error("hal/write", OK30)
        assert error["data"]["name"] == "SCOPE_DENIED"
    untouched(hub)


async def test_protocol_refused_header_does_not_fall_back(transport: Connect, hub: Hub, tokens: Tokens) -> None:
    async with transport("ohal_not-a-real-token") as rpc:
        response = await rpc.request(
            "hal/initialize",
            {"protocolVersion": "2026-10-24", "clientInfo": {"name": "x", "version": "1"}, "token": tokens.human},
        )
        assert response["error"]["data"]["name"] == "UNAUTHORIZED"
        error = await rpc.error("hal/write", OK30)
        assert error["data"]["name"] == "NOT_INITIALIZED"
    untouched(hub)


def test_cli_refuses_all_four(cli: CliHub, monkeypatch: pytest.MonkeyPatch) -> None:
    from openhal.cli import _tty

    request_id = cli.run(queue_request(cli.hub))
    code, out = run_cli("write", "desk-fan.fan_speed", "150 %")
    assert code == 1
    assert "above_max" in out
    code, out = run_cli("confirm", "approve", request_id)
    assert code != 0
    typed = ["approve", "unlock"]
    monkeypatch.setattr(_tty, "interactive", lambda: True)
    monkeypatch.setattr(_tty, "read_phrase", lambda prompt: typed.pop(0))
    code, out = run_cli("confirm", "approve", request_id)
    assert code != 0
    assert cli.hub.kernel.queue.get(request_id).status == "pending"
    code, out = run_cli("stop")
    assert cli.hub.kernel.stopped
    code, out = run_cli("unlock")
    assert code != 0
    assert cli.hub.kernel.stopped
    untouched(cli.hub)


def test_cli_human_powers_need_a_terminal(cli: CliHub, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHAL_TOKEN", cli.tokens.human)
    request_id = cli.run(queue_request(cli.hub))
    for attempt in (("confirm", "approve", request_id), ("confirm", "approve", request_id, "--phrase", "approve")):
        code, out = run_cli(*attempt, input="approve\n")
        assert code == 1, out
    assert cli.hub.kernel.queue.get(request_id).status == "pending"
    cli.run(cli.hub.kernel.stop_all(human(), "operator"))
    for attempt in (("unlock",), ("unlock", "--phrase", "unlock")):
        code, out = run_cli(*attempt, input="unlock\n")
        assert code == 1, out
        assert cli.hub.kernel.stopped


async def test_writer_routes_refuse_an_agent(hub: Hub, rest: Rest, tokens: Tokens) -> None:
    draft = """
device: Desk fan twin
id: desk-fan-twin
connect: { mock: twin }
write:
  fan_speed: { unit: "%", min: 0, max: 400, confirmed: { by: sohan, at: 2026-10-24 } }
hazard: low
confirmed: { by: sohan, at: 2026-10-24 }
"""
    async with rest(tokens.agent) as client:
        session = (await client.post("/v1/writer/sessions", json={"manual_text": "SPEED <n> sets the fan"})).json()
        proposed = await client.post(f"/v1/writer/sessions/{session['id']}/propose", json={"draft_yaml": draft})
        assert proposed.status_code == 200
        assert "confirmed" not in proposed.json()["draft_yaml"]
        assert {"device.hazard", "fan_speed.max"} <= set(proposed.json()["unconfirmed"])
        questions = (await client.get(f"/v1/writer/sessions/{session['id']}/interview")).json()["questions"]
        answers = {question["id"]: question["suggested"] or "1" for question in questions}
        answered = await client.post(f"/v1/writer/sessions/{session['id']}/answers", json={"answers": answers})
        assert answered.status_code == 403
        finished = await client.post(f"/v1/writer/sessions/{session['id']}/finish", json={})
        assert finished.status_code == 403
    assert "desk-fan-twin" not in hub.kernel.devices
    assert not list(hub.config.devices_dir.glob("*.hal.yaml"))


async def test_inspector_routes_are_for_people(hub: Hub, rest: Rest, tokens: Tokens) -> None:
    async with rest(tokens.agent) as client:
        assert (await client.get("/v1/rpc/log")).status_code == 403
        assert (await client.post("/v1/tokens", json={"name": "me", "kind": "human"})).status_code == 403
        assert (await client.post("/v1/pair/code")).status_code == 403
        assert (await client.get("/v1/tokens")).status_code == 403
    async with rest(tokens.human) as client:
        log = await client.get("/v1/rpc/log")
        assert log.status_code == 200


async def test_inspector_live_log_refuses_an_agent(base_url: str, tokens: Tokens) -> None:
    from websockets.asyncio.client import connect
    from websockets.exceptions import ConnectionClosed, InvalidStatus

    url = base_url.replace("http://", "ws://") + "/v1/rpc/log/live"
    for headers, query in (({"Authorization": f"Bearer {tokens.agent}"}, ""), ({}, f"?token={tokens.agent}")):
        with pytest.raises((ConnectionClosed, InvalidStatus)):
            async with connect(url + query, additional_headers=headers) as socket:
                await socket.recv()


async def test_rest_write_with_extra_fields_is_refused(hub: Hub, rest: Rest, tokens: Tokens) -> None:
    async with rest(tokens.agent) as client:
        for body in (
            {**OK30, "approved": True},
            {**OK30, "principal": {"kind": "human", "name": "sohan"}},
            {**OK30, "request": {"status": "approved"}},
        ):
            response = await client.post("/v1/write", json=body)
            assert response.status_code == 422
        laser_body = {"device": "laser", "channel": "power", "value": 10, "unit": "%"}
        laser = await client.post("/v1/write", json=laser_body, headers={"X-Principal": "human"})
        assert laser.json()["status"] == "pending"
    assert writes(hub, "laser") == []


async def test_agent_cannot_mint_a_session_cookie(hub: Hub, rest: Rest, tokens: Tokens) -> None:
    async with rest(tokens.agent) as client:
        assert (await client.post("/v1/pair", json={"code": "000000"})).status_code == 403
    async with rest(cookie=tokens.agent, headers={"X-OpenHAL-Request": "1"}) as client:
        await client.post("/v1/stop", json={"reason": "agent stop"})
        response = await client.post("/v1/unlock", json={"phrase": "unlock"})
        assert response.status_code == httpx.codes.FORBIDDEN
    assert hub.kernel.stopped
