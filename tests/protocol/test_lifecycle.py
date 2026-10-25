"""Lifecycle ordering, version negotiation, auth and malformed messages, over both transports."""

from __future__ import annotations

import asyncio
import json

from openhal.protocol import messages as m
from openhal.protocol.version import PROTOCOL_VERSIONS, negotiate
from tests.protocol.conftest import VERSION, Connect


async def test_initialize_answers_the_hub_and_principal(transport: Connect, tokens: dict[str, str]) -> None:
    async with transport() as rpc:
        result = await rpc.initialize(tokens["agent"])
    assert result == {
        "protocolVersion": VERSION,
        "hubInfo": result["hubInfo"],
        "conformance": "full",
        "principal": {"kind": "agent", "name": "claude", "scope": "control_medium"},
        "capabilities": {"notifications": list(m.NOTIFICATIONS)},
    }
    assert result["hubInfo"]["name"] == "OpenHAL"


async def test_methods_before_initialize_are_not_initialized(transport: Connect, tokens: dict[str, str]) -> None:
    async with transport(tokens["agent"]) as rpc:
        for method in ("hal/devices/list", "hal/write", "hal/stop", "hal/unlock"):
            error = await rpc.error(method, {})
            assert error["code"] == -32001
            assert error["data"]["name"] == "NOT_INITIALIZED"
        assert (await rpc.initialize())["principal"]["name"] == "claude"
        assert "devices" in await rpc.call("hal/devices/list")


async def test_no_notification_before_initialized(transport: Connect, tokens: dict[str, str]) -> None:
    async with transport() as rpc:
        await rpc.call(
            "hal/initialize",
            {"protocolVersion": VERSION, "clientInfo": {"name": "pytest", "version": "1"}, "token": tokens["agent"]},
        )
        await rpc.error("hal/write", {"device": "desk-fan", "channel": "fan_speed", "value": "150 %"})
        await asyncio.sleep(0.3)
        await rpc.call("hal/devices/list")
        assert rpc.notes == []
        await rpc.notify("hal/initialized")
        await rpc.error("hal/write", {"device": "desk-fan", "channel": "fan_speed", "value": "150 %"})
        blocked = await rpc.note("hal/blocked", device="desk-fan")
        assert blocked["params"]["error"]["data"]["name"] == "LIMIT_EXCEEDED"


async def test_shutdown_stops_notifications(transport: Connect, tokens: dict[str, str]) -> None:
    async with transport(tokens["agent"]) as rpc:
        await rpc.initialize()
        await rpc.notify("hal/shutdown")
        await asyncio.sleep(0.2)
        assert all(note["method"] != "hal/blocked" for note in rpc.notes)


async def test_version_negotiation(transport: Connect, tokens: dict[str, str]) -> None:
    assert negotiate(VERSION) == VERSION
    assert negotiate("2099-01-01") == PROTOCOL_VERSIONS[-1]
    assert negotiate("2020-01-01") == PROTOCOL_VERSIONS[-1]
    async with transport(tokens["agent"]) as rpc:
        result = await rpc.initialize(version="2099-01-01")
        assert result["protocolVersion"] == VERSION
    async with transport(tokens["agent"]) as rpc:
        error = await rpc.error(
            "hal/initialize", {"protocolVersion": "latest", "clientInfo": {"name": "pytest", "version": "1"}}
        )
        assert error["data"]["name"] == "INVALID_PARAMS"


async def test_initialize_twice_is_refused(transport: Connect, tokens: dict[str, str]) -> None:
    async with transport(tokens["agent"]) as rpc:
        await rpc.initialize()
        error = await rpc.error(
            "hal/initialize", {"protocolVersion": VERSION, "clientInfo": {"name": "pytest", "version": "1"}}
        )
        assert error["data"]["name"] == "INVALID_REQUEST"


async def test_unauthorized(transport: Connect, tokens: dict[str, str]) -> None:
    params = {"protocolVersion": VERSION, "clientInfo": {"name": "pytest", "version": "1"}}
    async with transport() as rpc:
        error = await rpc.error("hal/initialize", params)
        assert (error["code"], error["data"]["name"]) == (-32002, "UNAUTHORIZED")
        error = await rpc.error("hal/initialize", params | {"token": "ohal_nope"})
        assert error["data"]["name"] == "UNAUTHORIZED"
        assert (await rpc.call("hal/initialize", params | {"token": tokens["reader"]}))["principal"]["scope"] == "read"
    async with transport("ohal_wrong") as rpc:
        error = await rpc.error("hal/initialize", params | {"token": tokens["agent"]})
        assert error["data"]["name"] == "UNAUTHORIZED"


async def test_malformed_json_is_a_parse_error(transport: Connect) -> None:
    async with transport() as rpc:
        await rpc.send_text("{not json")
        response = await rpc.response(None)
    assert response == {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": -32700, "message": "The message is not valid JSON", "data": {"name": "PARSE_ERROR"}},
    }


async def test_batches_and_bad_envelopes_are_invalid_requests(transport: Connect) -> None:
    batch = [{"jsonrpc": "2.0", "id": 1, "method": "hal/devices/list"}]
    async with transport() as rpc:
        await rpc.send_text(json.dumps(batch))
        response = await rpc.response(None)
        assert response["error"]["code"] == -32600
        assert response["error"]["data"]["name"] == "INVALID_REQUEST"
        assert response["error"]["message"] == "Batches are not supported in this version"
        await rpc.send_text(json.dumps({"jsonrpc": "1.0", "id": 7, "method": "hal/devices/list"}))
        assert (await rpc.response(7))["error"]["data"]["name"] == "INVALID_REQUEST"
        await rpc.send_text(json.dumps({"jsonrpc": "2.0", "id": 8}))
        assert (await rpc.response(8))["error"]["data"]["name"] == "INVALID_REQUEST"
        await rpc.send_text(json.dumps("hello"))
        assert (await rpc.response(None))["error"]["data"]["name"] == "INVALID_REQUEST"


async def test_unknown_methods_and_bad_params(transport: Connect, tokens: dict[str, str]) -> None:
    async with transport(tokens["agent"]) as rpc:
        await rpc.initialize()
        error = await rpc.error("hal/teleport", {})
        assert (error["code"], error["data"]["name"]) == (-32601, "METHOD_NOT_FOUND")
        error = await rpc.error("hal/read", {"device": "desk-fan"})
        assert (error["code"], error["data"]["name"]) == (-32602, "INVALID_PARAMS")
        assert error["data"]["problems"] == ["channel field required"]
        error = await rpc.error("hal/read", {"device": "desk-fan", "channel": "fan_speed", "extra": 1})
        assert error["data"]["name"] == "INVALID_PARAMS"
        response = await rpc.request("hal/devices/list", None)
        assert "result" in response
