"""The Inspector's test hub. Real kernel, mock devices, and the message log the Inspector reads."""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn

from openhal.hub.api import STATIC_DIR
from openhal.kernel.principals import human
from openhal.protocol.client import ProtocolClient, ProtocolError
from tests.inspector.harness import SIMULATED_BOARD, Harness, start


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


async def test_devices_are_the_plant_waterer_and_the_mock_heater_and_lamp(base_url: str, harness: Harness) -> None:
    async with httpx.AsyncClient(base_url=base_url, headers=bearer(harness.human_token)) as client:
        devices = (await client.get("/v1/devices")).json()
        waterer = (await client.get("/v1/devices/plant-waterer")).json()
    assert {device["id"]: device["driver"] for device in devices} == {
        "bench-lamp": "mock",
        "curing-heater": "mock",
        "plant-waterer": "openhal-firmware",
    }
    assert waterer["read"]["tank"]["values"] == ["empty", "ok"]
    assert waterer["actions"]["water"]["args"]["duration"]["max"] == 30
    lamp = next(device for device in devices if device["id"] == "bench-lamp")
    assert lamp["writable"] is False


async def tank_reads(client: httpx.AsyncClient, wanted: str) -> None:
    for _ in range(100):
        view = (await client.get("/v1/devices/plant-waterer")).json()
        if view["read"]["tank"]["value"] == wanted:
            return
        await asyncio.sleep(0.1)
    raise AssertionError(f"The tank never read {wanted}.")


def water(seconds: int) -> dict[str, Any]:
    return {"device": "plant-waterer", "action": "water", "args": {"duration": {"value": seconds, "unit": "s"}}}


async def test_the_demo_scenario_reaches_the_message_log(base_url: str, harness: Harness) -> None:
    async with (
        httpx.AsyncClient(base_url=base_url, headers=bearer(harness.human_token)) as client,
        ProtocolClient(base_url, harness.agent_token, client_name="bench-agent") as rpc,
    ):
        with pytest.raises(ProtocolError) as too_long:
            await rpc.call("hal/action", water(120))
        await client.post("/_harness/plant-waterer/drain")
        await tank_reads(client, "empty")
        with pytest.raises(ProtocolError) as empty:
            await rpc.call("hal/action", water(20))
        await client.post("/_harness/plant-waterer/refill")
        await tank_reads(client, "ok")
        done = await rpc.call("hal/action", water(20))
        log = (await client.get("/v1/rpc/log")).json()
        refused = await client.get("/v1/rpc/log", headers=bearer(harness.agent_token))
    assert too_long.value.name == "LIMIT_EXCEEDED"
    assert too_long.value.reason == (
        "water duration 120 s exceeds the limit of 30 s (plant-waterer.hal.yaml, confirmed by sohan 2026-10-24)"
    )
    assert empty.value.name == "INTERLOCK_BLOCKED"
    assert empty.value.reason == "pump can't run while tank is empty"
    assert done["status"] == "done"
    assert refused.status_code == 403
    errors = [entry for entry in log if entry["direction"] == "out" and "error" in entry["message"]]
    assert [entry["message"]["error"]["data"]["name"] for entry in errors] == ["LIMIT_EXCEEDED", "INTERLOCK_BLOCKED"]
    assert all(harness.agent_token not in json.dumps(entry) for entry in log)


async def test_the_unknown_board_drafts_as_a_waterer_no_library_file_matches(harness: Harness) -> None:
    session = await harness.hub.writer.start(human("sohan"), unknown_id=SIMULATED_BOARD.id)
    draft = session.draft or {}
    registered = set(harness.hub.kernel.devices)
    assert SIMULATED_BOARD.identifiers["firmware.product"] == "herb-waterer"
    assert session.status == "interview"
    assert draft["device"] == "Herb waterer"
    assert set(draft["read"]) == {"soil_moisture", "tank"}
    assert draft["actions"]["water"]["args"]["duration"]["max"] == 30
    assert "fan_speed" not in str(draft)
    assert "herb-waterer" not in registered
    assert all(
        harness.hub.kernel.devices[device].file.match.firmware.get("product") != "herb-waterer" for device in registered
    )


async def test_the_hub_serves_the_built_inspector(base_url: str) -> None:
    if not (STATIC_DIR / "index.html").exists():
        pytest.skip("The Inspector is not built.")
    async with httpx.AsyncClient(base_url=base_url) as client:
        page = await client.get("/")
    assert page.status_code == 200
    assert "OpenHAL Inspector" in page.text
