"""Notifications fan out from the hub's event stream, and the Inspector's message log keeps no tokens."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from openhal.hub.hub import Hub
from openhal.kernel.principals import human
from openhal.protocol.dispatch import Dispatcher
from openhal.protocol.log import LOG_SIZE, MessageLog, redact
from openhal.spec import loads
from tests.protocol.conftest import Connect, websocket_client

LAMP = """
device: Desk lamp
id: desk-lamp
connect: { mock: lamp }
write:
  on: { type: bool }
confirmed: { by: sohan, at: 2026-10-24 }
"""


async def test_values_and_device_changes(transport: Connect, tokens: dict[str, str], hub: Hub) -> None:
    async with transport(tokens["reader"]) as rpc:
        await rpc.initialize()
        value = await rpc.note("hal/value", wait_s=6.0, device="desk-fan", channel="temperature")
        assert set(value["params"]) == {"device", "channel", "value", "unit", "at", "suspect"}
        assert value["params"]["unit"] == "degC"
        await hub.add_and_start(loads(LAMP))
        added = await rpc.note("hal/deviceAdded")
        assert added["params"]["device"]["id"] == "desk-lamp"
        assert added["params"]["device"]["conformance"] == "control"
        hub.kernel.unregister("desk-lamp")
        removed = await rpc.note("hal/deviceRemoved")
        assert removed["params"] == {"device": "desk-lamp"}


async def test_blocks_from_rest_reach_protocol_clients(
    transport: Connect, tokens: dict[str, str], base_url: str
) -> None:
    async with transport(tokens["reader"]) as rpc:
        await rpc.initialize()
        async with httpx.AsyncClient(base_url=base_url) as rest:
            response = await rest.post(
                "/v1/write",
                json={"device": "desk-fan", "channel": "fan_speed", "value": "150 %"},
                headers={"Authorization": f"Bearer {tokens['agent']}"},
            )
        assert response.json()["code"] == "above_max"
        blocked = await rpc.note("hal/blocked", device="desk-fan")
        assert blocked["params"]["error"]["message"] == (
            "fan_speed 150 % exceeds the limit of 100 % (desk-fan.hal.yaml, confirmed by sohan 2026-10-24)"
        )


async def test_confirmation_requests_reach_people_and_the_requester_only(
    transport: Connect, tokens: dict[str, str]
) -> None:
    spin = {"device": "desk-fan", "action": "spin_test", "args": {"seconds": "5 s"}}
    async with transport(tokens["agent"]) as bench, transport(tokens["other"]) as other:
        await bench.initialize()
        await other.initialize()
        pending = await bench.call("hal/action", spin)
        note = await bench.note("hal/confirmationRequested")
        assert note["params"]["request"]["requestId"] == pending["requestId"]
        await other.call("hal/devices/list")
        await asyncio.sleep(0.2)
        assert all(item["method"] != "hal/confirmationRequested" for item in other.notes)


async def test_a_core_hub_answers_core_methods_only(hub: Hub, tokens: dict[str, str]) -> None:
    dispatcher = Dispatcher(hub, level="core")
    session = dispatcher.open(principal=hub.tokens.principal(tokens["human"]))
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "hal/initialize",
        "params": {"protocolVersion": "2026-10-24", "clientInfo": {"name": "pytest", "version": "1"}},
    }
    result = (await dispatcher.handle(session, initialize))["result"]  # type: ignore[index]
    assert result["conformance"] == "core"
    assert result["capabilities"]["notifications"] == ["hal/value", "hal/deviceAdded", "hal/deviceRemoved"]
    for method in ("hal/write", "hal/action", "hal/stop", "hal/confirmations/list"):
        response = await dispatcher.handle(session, {"jsonrpc": "2.0", "id": 2, "method": method, "params": {}})
        assert response is not None
        assert response["error"]["data"]["name"] == "METHOD_NOT_FOUND"
    response = await dispatcher.handle(session, {"jsonrpc": "2.0", "id": 3, "method": "hal/devices/list"})
    assert response is not None
    assert "result" in response
    assert await dispatcher.handle(session, {"jsonrpc": "2.0", "method": "hal/initialized"}) is None
    assert session.state == "ready"


async def test_the_message_log_is_for_people_and_never_holds_tokens(
    base_url: str, tokens: dict[str, str], hub: Hub
) -> None:
    async with websocket_client(base_url, None) as rpc:
        await rpc.initialize(tokens["agent"])
        await rpc.error("hal/write", {"device": "desk-fan", "channel": "fan_speed", "value": "150 %"})
    async with httpx.AsyncClient(base_url=base_url) as rest:
        refused = await rest.get("/v1/rpc/log", headers={"Authorization": f"Bearer {tokens['agent']}"})
        assert refused.status_code == 403
        entries = (await rest.get("/v1/rpc/log", headers={"Authorization": f"Bearer {tokens['human']}"})).json()
        later = await rest.get(
            "/v1/rpc/log", params={"since": entries[-1]["seq"]}, headers={"Authorization": f"Bearer {tokens['human']}"}
        )
    assert later.json() == []
    text = json.dumps(entries)
    assert tokens["agent"] not in text
    first = entries[0]
    assert set(first) == {"seq", "at", "direction", "client", "principal", "message"}
    assert first["direction"] == "in"
    assert first["message"]["params"]["token"] == "[redacted]"
    directions = [(entry["direction"], entry["message"].get("method") or "response") for entry in entries]
    assert ("in", "hal/write") in directions
    blocked = [entry for entry in entries if entry["direction"] == "out" and "error" in entry["message"]]
    assert blocked[0]["message"]["error"]["data"]["name"] == "LIMIT_EXCEEDED"
    assert blocked[0]["client"] == "pytest"
    assert blocked[0]["principal"] == "agent:claude"


async def test_the_live_log_streams_to_people(base_url: str, tokens: dict[str, str]) -> None:
    url = base_url.replace("http://", "ws://")
    with pytest.raises(InvalidStatus):
        async with connect(f"{url}/v1/rpc/log/live", additional_headers={"Authorization": f"Bearer {tokens['agent']}"}):
            pass
    headers = {"Authorization": f"Bearer {tokens['human']}"}
    async with connect(f"{url}/v1/rpc/log/live", additional_headers=headers) as live:
        async with websocket_client(base_url, tokens["agent"]) as rpc:
            await rpc.initialize()
        first = json.loads(await asyncio.wait_for(live.recv(), 5))
    assert first["direction"] == "in"
    assert first["message"]["method"] == "hal/initialize"


async def test_web_pages_cannot_open_the_socket(base_url: str, tokens: dict[str, str]) -> None:
    url = base_url.replace("http://", "ws://") + "/rpc"
    with pytest.raises(InvalidStatus):
        async with connect(url, origin="https://evil.example"):  # type: ignore[arg-type]
            pass
    async with connect(url, origin="http://localhost:5173") as socket:  # type: ignore[arg-type]
        await socket.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "hal/devices/list"}))
        reply = json.loads(await asyncio.wait_for(socket.recv(), 5))
    assert reply["error"]["data"]["name"] == "NOT_INITIALIZED"


def test_the_ring_buffer_keeps_the_last_2000() -> None:
    log = MessageLog()
    for index in range(LOG_SIZE + 5):
        log.record("in", None, None, {"n": index})
    kept = log.since(0)
    assert len(kept) == LOG_SIZE
    assert kept[0]["message"] == {"n": 5}
    assert redact("ohal_secretvalue123 in text") == "[redacted] in text"
    assert redact({"params": {"token": "x", "nested": ["ohal_abc"]}}) == {
        "params": {"token": "[redacted]", "nested": ["[redacted]"]}
    }


async def test_a_cookie_session_can_initialize(hub: Hub) -> None:
    dispatcher = Dispatcher(hub)
    session = dispatcher.open(fallback=human("sohan"))
    params = {"protocolVersion": "2026-10-24", "clientInfo": {"name": "inspector", "version": "1"}}
    response = await dispatcher.handle(
        session, {"jsonrpc": "2.0", "id": 1, "method": "hal/initialize", "params": params}
    )
    assert response is not None
    assert response["result"]["principal"]["kind"] == "human"
