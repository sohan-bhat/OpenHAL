"""The Python client against a real embedded hub, sync and async, for every route the hub serves."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from openhal.client import (
    Action,
    AsyncClient,
    BadRequest,
    Client,
    HubNotRunning,
    NotFound,
    Refused,
    Unauthorized,
    Write,
    aconnect,
    connect,
    split_target,
)
from openhal.client.settings import resolve_token, resolve_url
from openhal.hub.hub import Hub
from tests.interfaces.conftest import BASE_URL, SyncHub, Tokens
from tests.kernel.conftest import FakeClock


def aclient(transport: httpx.AsyncBaseTransport, token: str | None) -> AsyncClient:
    return AsyncClient(BASE_URL, token, transport=transport, use_human_token_file=False)


async def test_status_devices_and_reads(async_transport: httpx.ASGITransport, tokens: Tokens) -> None:
    async with aclient(async_transport, tokens.agent) as hub:
        status = await hub.status()
        assert status.devices == 2
        assert status.you.kind == "agent"
        assert (await hub.whoami()).scope == "control_low"
        assert {device.id for device in await hub.devices()} == {"desk-fan", "heater"}
        fan = await hub.device("desk-fan")
        assert fan.write["fan_speed"].max == 100
        assert fan.write["fan_speed"].unit == "percent"
        heater = await hub.device("heater")
        assert heater.interlocks[0].if_ == "power > 0 W"
        reading = await hub.read("desk-fan.temperature")
        assert reading.ok
        assert reading.unit == "degC"
        many = await hub.read_many(["desk-fan.temperature", ("heater", "temp")])
        assert [item.ok for item in many] == [True, True]
        with pytest.raises(NotFound, match="no device"):
            await hub.device("nope")
        with pytest.raises(NotFound):
            await hub.read("desk-fan", "nope")


async def test_write_action_and_dry_run(async_transport: httpx.ASGITransport, tokens: Tokens) -> None:
    async with aclient(async_transport, tokens.agent) as hub:
        blocked = await hub.write("desk-fan", "fan_speed", "150 %")
        assert blocked.status == "blocked"
        assert blocked.code == "above_max"
        assert not blocked.ok
        done = await hub.write("desk-fan", "fan_speed", "20 %")
        assert done.ok
        assert (await hub.read("desk-fan", "fan_speed")).value == 20.0
        decisions = await hub.dry_run(
            [
                Write(device="desk-fan", channel="fan_speed", value="20 %"),
                {"device": "desk-fan", "channel": "fan_speed", "value": "300 %"},
                Action(device="heater", action="purge"),
            ]
        )
        assert [decision.status for decision in decisions][:2] == ["allowed", "blocked"]
        with pytest.raises(BadRequest, match="value"):
            await hub.call(_bad_write())


def _bad_write() -> object:
    from openhal.client import models
    from openhal.client.calls import Call, _as

    return Call("POST", "/v1/write", _as(models.Decision), {"device": "desk-fan", "channel": "fan_speed"})


async def test_confirmations_tighten_and_stop(async_transport: httpx.ASGITransport, tokens: Tokens, hub: Hub) -> None:
    clock: FakeClock = hub.kernel.clock  # type: ignore[assignment]
    async with aclient(async_transport, tokens.medium) as agent, aclient(async_transport, tokens.human) as human:
        for speed in ("20 %", "40 %"):
            await agent.write("desk-fan", "fan_speed", speed)
            clock.advance(1)
        pending = await agent.action("heater", "purge")
        assert pending.pending
        assert pending.request_id
        assert [request.id for request in await agent.confirmations()] == [pending.request_id]
        assert (await agent.confirmation(pending.request_id)).status == "pending"
        with pytest.raises(Refused, match="Only a human"):
            await agent.approve(pending.request_id)
        approved = await human.approve(pending.request_id)
        assert approved.status == "done"
        with pytest.raises(Refused):
            await human.approve(pending.request_id)
        assert len(await human.confirmations(include_done=True)) == 1
        again = await agent.action("heater", "purge")
        rejected = await human.reject(again.request_id or "", "not now")
        assert rejected.status == "rejected"

        tightened = await agent.tighten("desk-fan", "fan_speed", max="50 %")
        assert tightened.ok
        assert tightened.limits == {"max": 50.0}
        loosened = await agent.tighten("desk-fan", "fan_speed", max="90 %")
        assert loosened.code == "cannot_loosen"

        report = await agent.stop("test")
        assert {item.status for item in report.devices} == {"safe"}
        assert (await agent.status()).stopped
        with pytest.raises(Refused):
            await agent.unlock("unlock")
        with pytest.raises(BadRequest, match="unlock"):
            await human.unlock("nope")
        assert (await human.unlock("unlock")).ok


async def test_audit_drivers_and_pair(async_transport: httpx.ASGITransport, tokens: Tokens, hub: Hub) -> None:
    async with aclient(async_transport, tokens.agent) as client:
        await client.tighten("desk-fan", "fan_speed", max="50 %")
        entries = await client.audit(event="tighten")
        assert [entry.status for entry in entries] == ["done"]
        assert all(entry.hash for entry in entries)
        assert (await client.verify_audit()).ok
        assert any(driver.name == "mock" and driver.installed for driver in await client.drivers())
        code = hub.tokens.new_pairing_code()
        assert (await client.pair(code)).ok
        with pytest.raises(Refused, match="pairing code"):
            await client.pair(code)


async def test_errors_are_specific(async_transport: httpx.ASGITransport, tokens: Tokens) -> None:
    async with aclient(async_transport, None) as anonymous:
        with pytest.raises(Unauthorized, match="openhal init"):
            await anonymous.status()
    async with aclient(async_transport, "ohal_wrong") as wrong:
        with pytest.raises(Unauthorized, match="did not accept"):
            await wrong.status()
    async with aclient(async_transport, tokens.human) as human:
        with pytest.raises(NotFound, match="no driver writer session"):
            await human.writer_session("s1")
    async with AsyncClient("http://127.0.0.1:9", "ohal_x", use_human_token_file=False, timeout=2) as nobody:
        with pytest.raises(HubNotRunning, match="openhald"):
            await nobody.status()


async def test_aconnect_checks_the_token(async_transport: httpx.ASGITransport, tokens: Tokens) -> None:
    client = await aconnect(BASE_URL, tokens.reader, transport=async_transport)
    assert (await client.whoami()).name == "viewer"
    await client.aclose()
    with pytest.raises(Unauthorized):
        await aconnect(BASE_URL, "ohal_wrong", transport=async_transport)


async def test_ramp_to_passes_the_rate_limit(async_transport: httpx.ASGITransport, tokens: Tokens, hub: Hub) -> None:
    clock: FakeClock = hub.kernel.clock  # type: ignore[assignment]

    async def sleep(seconds: float) -> None:
        clock.advance(seconds)

    async with aclient(async_transport, tokens.agent) as client:
        assert (await client.write("desk-fan", "fan_speed", "0 %")).ok
        assert (await client.write("desk-fan", "fan_speed", "80 %")).code == "rate_limited"
        decisions = await client.ramp_to("desk-fan", "fan_speed", "80 %", sleep=sleep)
        assert all(decision.ok for decision in decisions), [d.message for d in decisions]
        assert len(decisions) > 1
        assert (await client.read("desk-fan", "fan_speed")).value == 80.0


def test_sync_client_against_the_hub(sync_hub: SyncHub) -> None:
    clock: FakeClock = sync_hub.hub.kernel.clock  # type: ignore[assignment]
    with connect(BASE_URL, sync_hub.tokens.agent, transport=sync_hub.transport) as hub:
        assert hub.status().devices == 2
        assert hub.whoami().name == "claude"
        assert len(hub.devices()) == 2
        assert hub.device("heater").actions["pulse"].confirm == "confirm"
        assert hub.read("desk-fan", "temperature").ok
        assert len(hub.read_many(["desk-fan.temperature"])) == 1
        assert hub.write("desk-fan", "fan_speed", "20 %").ok
        assert hub.dry_run([Write(device="desk-fan", channel="fan_speed", value="200 %")])[0].code == "above_max"
        assert hub.action("heater", "pulse", seconds="2 s").status in ("blocked", "pending")
        assert hub.tighten("desk-fan", "fan_speed", max="60 %").ok
        decisions = hub.ramp_to("desk-fan", "fan_speed", "50 %", sleep=clock.advance)
        assert decisions[-1].ok
        assert hub.audit(limit=5)
        assert hub.verify_audit().ok
        assert hub.drivers()
        assert hub.confirmations() is not None
        with pytest.raises(NotFound):
            hub.confirmation("nope")
        assert hub.stop("sync test").devices
    with connect(BASE_URL, sync_hub.tokens.human, transport=sync_hub.transport) as human:
        assert human.unlock("unlock").ok
        with pytest.raises(Refused):
            human.approve("nope")
        with pytest.raises(Refused):
            human.reject("nope")
        with pytest.raises(Refused):
            human.pair("000001")


def test_sync_connect_fails_fast() -> None:
    with pytest.raises(HubNotRunning, match=r"not running at http://127\.0\.0\.1:9"):
        connect("http://127.0.0.1:9", "ohal_x", timeout=2)


def test_token_and_url_lookup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "custom"
    home.mkdir()
    assert resolve_token(home=home).token is None
    (home / "human.token").write_text("ohal_from_file\n")
    assert resolve_token(home=home).token == "ohal_from_file"
    assert resolve_token(home=home, use_human_file=False).token is None
    monkeypatch.setenv("OPENHAL_TOKEN", "ohal_from_env")
    assert resolve_token(home=home).token == "ohal_from_env"
    assert resolve_token("ohal_explicit", home=home).token == "ohal_explicit"

    assert resolve_url(home=home) == "http://127.0.0.1:7420"
    (home / "config.yaml").write_text("api: { host: 0.0.0.0, port: 7500, allow_lan: true }\n")
    assert resolve_url(home=home) == "http://127.0.0.1:7500"
    (home / "config.yaml").write_text("api: [broken\n")
    assert resolve_url(home=home) == "http://127.0.0.1:7420"
    monkeypatch.setenv("OPENHAL_URL", "http://localhost:7999/")
    assert resolve_url(home=home) == "http://localhost:7999"
    assert resolve_url("http://[::1]:7420", home=home) == "http://[::1]:7420"


def test_split_target() -> None:
    assert split_target("desk-fan.fan_speed") == ("desk-fan", "fan_speed")
    with pytest.raises(ValueError, match=r"device\.channel"):
        split_target("desk-fan")


def test_client_ignores_proxy_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.example:3128")
    client = Client("http://127.0.0.1:9", "ohal_x")
    assert client._http._mounts == {}
    client.close()
