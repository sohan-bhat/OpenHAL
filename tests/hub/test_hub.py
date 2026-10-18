"""Hub lifecycle, device files on disk, locks, tokens, polling and heartbeats."""

from __future__ import annotations

import asyncio
import stat
from pathlib import Path

import pytest

from openhal.hub.config import HubConfig, load_config
from openhal.hub.hub import Hub
from openhal.hub.locks import DeviceLock, DeviceLocked
from openhal.hub.tokens import TokenStore, read_secret_file, write_secret_file
from openhal.spec import loads
from tests.kernel.conftest import FAN

POLLED = FAN.replace("every: 1 s", "every: 0.2 s").replace(
    "connect: { mock: fan }", "connect: { mock: fan, simulate: desk-fan }"
)


async def test_loads_device_files_and_reports_problems(tmp_path: Path) -> None:
    config = HubConfig(home=tmp_path)
    config.ensure_dirs()
    (config.devices_dir / "fan.hal.yaml").write_text(FAN)
    (config.devices_dir / "broken.hal.yaml").write_text("device: x\n")
    (config.devices_dir / "teleport.hal.yaml").write_text("device: x\nconnect: {driver: x-teleport}\n")
    hub = Hub(config)
    await hub.start()
    try:
        assert list(hub.kernel.devices) == ["desk-fan"]
        problems = {Path(item.path).name: item.problems for item in hub.load_problems}
        assert "broken.hal.yaml" in problems
        assert "No driver named 'x-teleport'" in problems["teleport.hal.yaml"][0]
        assert hub.kernel.devices["desk-fan"].connected
        assert stat.S_IMODE(config.approval_key_path.stat().st_mode) == 0o600
    finally:
        await hub.close()
    again = Hub(config)
    assert again.kernel._approval_key == hub.kernel._approval_key


async def test_device_lock_prevents_two_hubs(tmp_path: Path) -> None:
    config = HubConfig(home=tmp_path)
    config.ensure_dirs()
    first = Hub(config)
    first.add_device(loads(FAN))
    second = Hub(config)
    with pytest.raises(DeviceLocked):
        second.add_device(loads(FAN))
    await first.close()
    second.add_device(loads(FAN))
    await second.close()


def test_lock_release_is_idempotent(tmp_path: Path) -> None:
    lock = DeviceLock(tmp_path, "x")
    lock.acquire()
    lock.release()
    lock.release()


async def test_polling_emits_readings(tmp_path: Path) -> None:
    hub = Hub(HubConfig(home=tmp_path, poll_floor_s=0.05), in_memory=True)
    hub.add_device(loads(POLLED))
    events: list[dict[str, object]] = []
    unsubscribe = hub.subscribe(events.append)
    await hub.start(load_devices=False)
    await asyncio.sleep(0.5)
    unsubscribe()
    await hub.close()
    readings = [event for event in events if event["type"] == "reading"]
    assert readings, "the poll loop should read temperature every 0.2 s"
    assert {event["channel"] for event in readings} == {"temperature"}
    assert any(event["type"] == "audit" for event in events)


async def test_heartbeat_detects_loss_and_reconnects(tmp_path: Path) -> None:
    text = FAN.replace("hazard: low", "hazard: low\nwatchdog: { heartbeat: 0.1 s }")
    hub = Hub(HubConfig(home=tmp_path), in_memory=True)
    runtime = hub.add_device(loads(text))
    await hub.start(load_devices=False)
    driver = runtime.driver
    driver.connected = False  # type: ignore[attr-defined]
    await asyncio.sleep(0.35)
    assert not runtime.connected or hub.audit.entries(event="connection_lost")
    await asyncio.sleep(2.5)
    assert runtime.connected, "the hub reconnects with backoff"
    await hub.close()


async def test_failed_connect_is_recorded(tmp_path: Path) -> None:
    hub = Hub(HubConfig(home=tmp_path), in_memory=True)
    text = FAN.replace("connect: { mock: fan }", "connect: { mock: fan, fail_connect: true }")
    hub.add_device(loads(text))
    await hub.start(load_devices=False)
    assert "fail_connect" in (hub.info["desk-fan"].last_error or "")
    with pytest.raises(ValueError, match="already registered"):
        hub.add_device(loads(text))
    await hub.close()


def test_tokens(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "t.db")
    token, info = store.create("claude", "agent", "control_low")
    assert token.startswith("ohal_")
    principal = store.principal(token)
    assert principal is not None
    assert (principal.kind, principal.scope) == ("agent", "control_low")
    human_token, human = store.create("me", "human", "read")
    assert human.scope == "control_medium"
    assert store.principal(None) is None
    assert store.principal("not-a-token") is None
    assert store.revoke(info.token_id)
    assert not store.revoke(info.token_id)
    assert store.principal(token) is None
    assert [item.revoked for item in store.list()] == [True, False]
    raw = (tmp_path / "t.db").read_bytes()
    assert token.encode() not in raw, "tokens are stored hashed"
    assert human_token.encode() not in raw
    with pytest.raises(ValueError, match="kind must be"):
        store.create("x", "robot")
    store.close()


def test_secret_files(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "human.token"
    assert read_secret_file(path) is None
    write_secret_file(path, "ohal_x")
    assert read_secret_file(path) == "ohal_x"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_config_file(tmp_path: Path) -> None:
    assert load_config(tmp_path).api.port == 7420
    (tmp_path / "config.yaml").write_text("api: { port: 7500 }\nconfirm: { require_tty: false }\n")
    config = load_config(tmp_path)
    assert config.api.port == 7500
    assert not config.confirm.require_tty
    (tmp_path / "config.yaml").write_text("- nope\n")
    with pytest.raises(ValueError, match="mapping"):
        load_config(tmp_path)
