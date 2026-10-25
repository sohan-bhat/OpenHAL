"""The Inspector's test hub. Real kernel, mock devices, and the message log the Inspector reads."""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import uvicorn

from openhal.hub.api import STATIC_DIR
from openhal.protocol.client import ProtocolClient, ProtocolError
from tests.inspector.harness import Harness, start


@pytest.fixture
async def harness(tmp_path: Path) -> AsyncIterator[Harness]:
    started = await start(tmp_path)
    yield started
    await started.hub.close()


@pytest.fixture
async def base_url(harness: Harness) -> AsyncIterator[str]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    config = uvicorn.Config(harness.app, log_level="warning", lifespan="off", timeout_graceful_shutdown=2)
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve(sockets=[listener]))
    while not server.started:  # noqa: ASYNC110
        await asyncio.sleep(0.01)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    await task
    listener.close()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_devices_are_the_mock_fan_heater_and_lamp(base_url: str, harness: Harness) -> None:
    async with httpx.AsyncClient(base_url=base_url, headers=bearer(harness.human_token)) as client:
        devices = (await client.get("/v1/devices")).json()
        fan = (await client.get("/v1/devices/desk-fan")).json()
    assert {device["id"]: device["driver"] for device in devices} == {
        "bench-lamp": "mock",
        "curing-heater": "mock",
        "desk-fan": "mock",
    }
    assert fan["write"]["fan_speed"]["value"] == 20
    assert fan["write"]["fan_speed"]["max"] == 100
    lamp = next(device for device in devices if device["id"] == "bench-lamp")
    assert lamp["writable"] is False


async def test_the_blocked_write_reaches_the_message_log(base_url: str, harness: Harness) -> None:
    async with ProtocolClient(base_url, harness.agent_token, client_name="bench-agent") as rpc:
        with pytest.raises(ProtocolError) as blocked:
            await rpc.call("hal/write", {"device": "desk-fan", "channel": "fan_speed", "value": "150 %"})
        pending = await rpc.call(
            "hal/action", {"device": "desk-fan", "action": "spin_test", "args": {"seconds": "5 s"}}
        )
    assert blocked.value.code == -32010
    assert blocked.value.name == "LIMIT_EXCEEDED"
    assert blocked.value.reason == (
        "fan_speed 150 % exceeds the limit of 100 % (desk-fan.hal.yaml, confirmed by sohan 2026-10-24)"
    )
    assert pending["status"] == "pending"

    async with httpx.AsyncClient(base_url=base_url) as client:
        log = (await client.get("/v1/rpc/log", headers=bearer(harness.human_token))).json()
        refused = await client.get("/v1/rpc/log", headers=bearer(harness.agent_token))
    assert refused.status_code == 403
    errors = [entry for entry in log if entry["direction"] == "out" and "error" in entry["message"]]
    assert errors[0]["message"]["error"]["data"]["name"] == "LIMIT_EXCEEDED"
    assert all(harness.agent_token not in json.dumps(entry) for entry in log)


async def test_the_hub_serves_the_built_inspector(base_url: str) -> None:
    if not (STATIC_DIR / "index.html").exists():
        pytest.skip("The Inspector is not built.")
    async with httpx.AsyncClient(base_url=base_url) as client:
        page = await client.get("/")
    assert page.status_code == 200
    assert "OpenHAL Inspector" in page.text
