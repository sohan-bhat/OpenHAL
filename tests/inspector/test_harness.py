"""The Inspector's test hub. Real kernel, mock devices, and the message log the Inspector reads."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from openhal.hub.api import STATIC_DIR
from tests.inspector.harness import Harness, start
from tests.inspector.rpc_shim import Connection, Shim


@pytest.fixture
async def harness(tmp_path: Path) -> AsyncIterator[Harness]:
    started = await start(tmp_path)
    yield started
    await started.hub.close()


@pytest.fixture
async def client(harness: Harness) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=harness.app, client=("127.0.0.1", 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:7431") as client:
        yield client


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def exchange(connection: Connection, ident: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
    await connection.receive(json.dumps({"jsonrpc": "2.0", "id": ident, "method": method, "params": params}))
    while True:
        message = connection.outbox.get_nowait()
        connection.shim.log.record("out", connection.client, connection.label, message)
        if message.get("id") == ident:
            return message


async def test_devices_are_the_mock_fan_heater_and_lamp(client: httpx.AsyncClient, harness: Harness) -> None:
    devices = (await client.get("/v1/devices", headers=bearer(harness.human_token))).json()
    assert {device["id"]: device["driver"] for device in devices} == {
        "bench-lamp": "mock",
        "curing-heater": "mock",
        "desk-fan": "mock",
    }
    fan = (await client.get("/v1/devices/desk-fan", headers=bearer(harness.human_token))).json()
    assert fan["write"]["fan_speed"]["value"] == 20
    assert fan["write"]["fan_speed"]["max"] == 100
    lamp = next(device for device in devices if device["id"] == "bench-lamp")
    assert lamp["writable"] is False


async def test_the_blocked_write_reads_as_in_the_specification(client: httpx.AsyncClient, harness: Harness) -> None:
    if harness.log_mode != "fixture":
        pytest.skip("The hub serves the real message log, which the protocol tests cover.")
    shim: Shim = harness.app.state.rpc_shim
    connection = Connection(shim, None, None)
    early = await exchange(connection, 1, "hal/devices/list", {})
    assert early["error"]["data"]["name"] == "NOT_INITIALIZED"
    hello = await exchange(
        connection,
        2,
        "hal/initialize",
        {"protocolVersion": "2026-10-24", "clientInfo": {"name": "bench-agent"}, "token": harness.agent_token},
    )
    assert hello["result"]["principal"]["kind"] == "agent"
    blocked = await exchange(
        connection, 3, "hal/write", {"device": "desk-fan", "channel": "fan_speed", "value": "150 %"}
    )
    assert blocked["error"]["code"] == -32010
    assert blocked["error"]["data"]["name"] == "LIMIT_EXCEEDED"
    assert blocked["error"]["message"] == (
        "fan_speed 150 % exceeds the limit of 100 % (desk-fan.hal.yaml, confirmed by sohan 2026-10-24)"
    )
    pending = await exchange(
        connection, 4, "hal/action", {"device": "desk-fan", "action": "spin_test", "args": {"seconds": "5 s"}}
    )
    assert pending["result"]["status"] == "pending"

    log = (await client.get("/v1/rpc/log", headers=bearer(harness.human_token))).json()["entries"]
    assert [entry["direction"] for entry in log[:2]] == ["in", "out"]
    initialize = next(entry for entry in log if entry["message"].get("method") == "hal/initialize")
    assert initialize["message"]["params"]["token"] == "[redacted]"
    assert all(harness.agent_token not in json.dumps(entry) for entry in log)
    refused = await client.get("/v1/rpc/log", headers=bearer(harness.agent_token))
    assert refused.status_code == 403


async def test_text_that_is_not_json_gets_parse_error(harness: Harness) -> None:
    if harness.log_mode != "fixture":
        pytest.skip("The hub serves the real message log, which the protocol tests cover.")
    connection = Connection(harness.app.state.rpc_shim, None, None)
    await connection.receive("{not json")
    assert connection.outbox.get_nowait()["error"]["code"] == -32700


async def test_the_hub_serves_the_built_inspector(client: httpx.AsyncClient) -> None:
    if not (STATIC_DIR / "index.html").exists():
        pytest.skip("The Inspector is not built.")
    page = await client.get("/")
    assert page.status_code == 200
    assert "OpenHAL Inspector" in page.text
