"""The local API. Auth, network guard, CSRF, every route, and that it only ever talks to the kernel."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from openhal.hub.api import CSRF_HEADER, SESSION_COOKIE, create_app
from openhal.hub.config import HubConfig
from openhal.hub.hub import Hub
from openhal.spec import loads
from tests.kernel.conftest import FAN, HEATER, FakeClock


@pytest.fixture
async def hub(tmp_path: Path) -> AsyncIterator[Hub]:
    clock = FakeClock()
    hub = Hub(HubConfig(home=tmp_path), clock=clock, in_memory=True)
    hub.add_device(loads(FAN))
    hub.add_device(loads(HEATER))
    await hub.start(load_devices=False)
    clock.advance(60)
    yield hub
    await hub.close()


@pytest.fixture
async def client(hub: Hub) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(hub), client=("127.0.0.1", 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:7420") as client:
        yield client


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_requires_token(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/status")
    assert response.status_code == 401
    assert "openhal token create" in response.json()["detail"]
    assert (await client.get("/v1/status", headers=bearer("ohal_nope"))).status_code == 401


async def test_status_and_devices(client: httpx.AsyncClient, hub: Hub) -> None:
    token, _ = hub.tokens.create("claude", "agent", "control_low")
    status = (await client.get("/v1/status", headers=bearer(token))).json()
    assert status["devices"] == 2
    assert status["you"] == {"kind": "agent", "name": "claude", "scope": "control_low"}
    devices = (await client.get("/v1/devices", headers=bearer(token))).json()
    assert {device["id"] for device in devices} == {"desk-fan", "heater"}
    fan = (await client.get("/v1/devices/desk-fan", headers=bearer(token))).json()
    assert fan["write"]["fan_speed"]["max"] == 100
    assert fan["write"]["fan_speed"]["known"] is True
    assert (await client.get("/v1/devices/nope", headers=bearer(token))).status_code == 404


async def test_write_is_decided_by_the_kernel(client: httpx.AsyncClient, hub: Hub) -> None:
    token, _ = hub.tokens.create("claude", "agent", "control_low")
    blocked = await client.post(
        "/v1/write",
        json={"device": "desk-fan", "channel": "fan_speed", "value": 150, "unit": "%"},
        headers=bearer(token),
    )
    assert blocked.json()["code"] == "above_max"
    assert blocked.json()["message"] == "Blocked. The fan_speed limit is 100 % (max). Asked for 150 %."
    done = await client.post(
        "/v1/write",
        json={"device": "desk-fan", "channel": "fan_speed", "value": 20, "unit": "%"},
        headers=bearer(token),
    )
    assert done.json()["status"] == "done"
    reading = await client.post("/v1/read", json={"device": "desk-fan", "channel": "fan_speed"}, headers=bearer(token))
    assert reading.json()["value"] == 20.0
    bad = await client.post("/v1/write", json={"device": "desk-fan", "channel": "fan_speed"}, headers=bearer(token))
    assert bad.status_code == 422


async def test_read_only_token(client: httpx.AsyncClient, hub: Hub) -> None:
    token, _ = hub.tokens.create("viewer", "agent", "read")
    response = await client.post(
        "/v1/write",
        json={"device": "desk-fan", "channel": "fan_speed", "value": 10, "unit": "%"},
        headers=bearer(token),
    )
    assert response.json()["code"] == "not_permitted"
    many = await client.post(
        "/v1/read_many",
        json={"items": [{"device": "desk-fan", "channel": "temperature"}, {"device": "heater", "channel": "temp"}]},
        headers=bearer(token),
    )
    assert [item["ok"] for item in many.json()] == [True, True]
    missing = await client.post("/v1/read", json={"device": "desk-fan", "channel": "nope"}, headers=bearer(token))
    assert missing.status_code == 404


async def test_confirmations_need_a_human(client: httpx.AsyncClient, hub: Hub) -> None:
    agent_token, _ = hub.tokens.create("claude", "agent", "control_medium")
    other_token, _ = hub.tokens.create("other", "agent", "control_medium")
    human_token, _ = hub.tokens.create("owner", "human")
    clock: FakeClock = hub.kernel.clock  # type: ignore[assignment]
    for speed in (20, 40):
        await client.post(
            "/v1/write",
            json={"device": "desk-fan", "channel": "fan_speed", "value": speed, "unit": "%"},
            headers=bearer(agent_token),
        )
        clock.advance(1)
    pending = (
        await client.post("/v1/action", json={"device": "heater", "action": "purge"}, headers=bearer(agent_token))
    ).json()
    assert pending["status"] == "pending"
    request_id = pending["request_id"]
    assert len((await client.get("/v1/confirmations", headers=bearer(agent_token))).json()) == 1
    assert (await client.get("/v1/confirmations", headers=bearer(other_token))).json() == []
    assert (await client.get(f"/v1/confirmations/{request_id}", headers=bearer(other_token))).status_code == 404
    refused = await client.post(f"/v1/confirmations/{request_id}/approve", headers=bearer(agent_token))
    assert refused.status_code == 403
    approved = await client.post(f"/v1/confirmations/{request_id}/approve", headers=bearer(human_token))
    assert approved.json()["status"] == "done"
    again = await client.post(f"/v1/confirmations/{request_id}/approve", headers=bearer(human_token))
    assert again.status_code == 409


async def test_stop_and_unlock(client: httpx.AsyncClient, hub: Hub) -> None:
    agent_token, _ = hub.tokens.create("claude", "agent", "control_low")
    human_token, _ = hub.tokens.create("owner", "human")
    report = (await client.post("/v1/stop", json={"reason": "test"}, headers=bearer(agent_token))).json()
    assert {item["status"] for item in report["devices"]} == {"safe"}
    assert (await client.post("/v1/unlock", json={"phrase": "unlock"}, headers=bearer(agent_token))).status_code == 403
    assert (await client.post("/v1/unlock", json={"phrase": "no"}, headers=bearer(human_token))).status_code == 400
    assert (await client.post("/v1/unlock", json={"phrase": "unlock"}, headers=bearer(human_token))).json()["ok"]


async def test_dry_run_tighten_audit_and_drivers(client: httpx.AsyncClient, hub: Hub) -> None:
    token, _ = hub.tokens.create("claude", "agent", "control_low")
    plan = {
        "commands": [
            {"kind": "write", "device": "desk-fan", "channel": "fan_speed", "value": 20, "unit": "%"},
            {"kind": "write", "device": "desk-fan", "channel": "fan_speed", "value": 120, "unit": "%"},
        ]
    }
    decisions = (await client.post("/v1/dry_run", json=plan, headers=bearer(token))).json()
    assert [decision["status"] for decision in decisions] == ["allowed", "blocked"]
    tightened = (
        await client.post(
            "/v1/tighten",
            json={"device": "desk-fan", "channel": "fan_speed", "max": {"value": 50, "unit": "%"}},
            headers=bearer(token),
        )
    ).json()
    assert tightened == {"ok": True, "limits": {"max": 50.0}}
    loosened = (
        await client.post(
            "/v1/tighten",
            json={"device": "desk-fan", "channel": "fan_speed", "max": {"value": 90, "unit": "%"}},
            headers=bearer(token),
        )
    ).json()
    assert loosened["code"] == "cannot_loosen"
    assert (
        await client.post("/v1/tighten", json={"device": "x", "channel": "y"}, headers=bearer(token))
    ).status_code == 404
    entries = (await client.get("/v1/audit?event=tighten", headers=bearer(token))).json()
    assert [entry["status"] for entry in entries] == ["blocked", "done"]
    assert (await client.get("/v1/audit/verify", headers=bearer(token))).json()["ok"] is True
    drivers = (await client.get("/v1/drivers", headers=bearer(token))).json()
    assert any(driver["name"] == "mock" for driver in drivers)
    assert (await client.get("/v1/whoami", headers=bearer(token))).json()["name"] == "claude"


async def test_network_guard(hub: Hub) -> None:
    app = create_app(hub)
    token, _ = hub.tokens.create("claude", "agent", "read")
    remote = httpx.ASGITransport(app=app, client=("192.168.1.50", 50000))
    async with httpx.AsyncClient(transport=remote, base_url="http://127.0.0.1:7420") as client:
        assert (await client.get("/v1/status", headers=bearer(token))).status_code == 403
    local = httpx.ASGITransport(app=app, client=("127.0.0.1", 50000))
    async with httpx.AsyncClient(transport=local, base_url="http://evil.example:7420") as client:
        response = await client.get("/v1/status", headers=bearer(token))
        assert response.status_code == 403, "a rebinding Host header must be refused"


async def test_pairing_and_csrf(client: httpx.AsyncClient, hub: Hub) -> None:
    assert (await client.post("/v1/pair", json={"code": "000000"})).status_code in (403, 422)
    code = hub.tokens.new_pairing_code()
    paired = await client.post("/v1/pair", json={"code": code})
    assert paired.status_code == 200
    assert SESSION_COOKIE in paired.cookies
    assert (await client.post("/v1/pair", json={"code": code})).status_code == 403, "codes work once"
    assert (await client.get("/v1/whoami")).json()["kind"] == "human"
    no_header = await client.post("/v1/stop", json={"reason": "x"})
    assert no_header.status_code == 403
    with_header = await client.post("/v1/stop", json={"reason": "x"}, headers={CSRF_HEADER: "1"})
    assert with_header.status_code == 200


async def test_inspector_assets_are_compressed_and_cached_for_good(client: httpx.AsyncClient) -> None:
    from openhal.hub.api import STATIC_DIR

    script = next((STATIC_DIR / "assets").glob("index-*.js"))
    response = await client.get(f"/assets/{script.name}", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    page = await client.get("/")
    assert page.headers["cache-control"] == "no-store"
    missing = await client.get("/assets/nothing-here.js")
    assert missing.status_code == 404
    assert missing.headers["cache-control"] == "no-store"


async def test_security_headers(client: httpx.AsyncClient, hub: Hub) -> None:
    token, _ = hub.tokens.create("claude", "agent", "read")
    response = await client.get("/v1/status", headers=bearer(token))
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
