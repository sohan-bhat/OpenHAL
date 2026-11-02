"""The running hub loads a confirmed device file on request, with no restart, and only for a person."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import yaml

from openhal.hub.api import create_app
from openhal.hub.config import HubConfig
from openhal.hub.hub import Hub
from openhal.spec.loader import parse_yaml
from openhal.writer import interview

LAMP = """\
openhal: "0.1"
device: Desk lamp
id: desk-lamp
connect: { mock: desk-lamp }
write:
  brightness: { unit: percent, min: 0, max: 100, suggested: true }
provenance: { source: self-described }
"""


def confirmed_text() -> str:
    draft = parse_yaml(LAMP)
    answers = {q.id: interview.suggestion_text(q) or "none" for q in interview.questions(draft)}
    answers["brightness.max"] = "80 %"
    return yaml.safe_dump(interview.apply(draft, answers, by="owner"), sort_keys=False)


@pytest.fixture
async def hub(tmp_path: Path) -> AsyncIterator[Hub]:
    devices = tmp_path / "devices"
    devices.mkdir()
    (devices / "desk-lamp.hal.yaml").write_text(LAMP)
    hub = Hub(HubConfig(home=tmp_path), in_memory=True)
    await hub.start()
    yield hub
    await hub.close()


@pytest.fixture
async def client(hub: Hub) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(hub), client=("127.0.0.1", 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:4441") as client:
        yield client


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def device_tasks(hub: Hub, device_id: str) -> list[str]:
    return sorted(task.get_name() for task in hub._tasks if task.get_name().endswith(device_id) and not task.done())


async def test_a_confirmed_file_loads_writable_without_a_restart(hub: Hub, client: httpx.AsyncClient) -> None:
    person, _ = hub.tokens.create("owner", "human")
    path = hub.config.devices_dir / "desk-lamp.hal.yaml"
    assert not hub.kernel.devices["desk-lamp"].file.writable
    path.write_text(confirmed_text())
    loaded = await client.post("/v1/device_files/load", json={"path": str(path)}, headers=bearer(person))
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["status"] == "reloaded"
    assert loaded.json()["writable"] is True
    runtime = hub.kernel.devices["desk-lamp"]
    assert runtime.file.writable
    assert runtime.file.write["brightness"].max == 80
    assert device_tasks(hub, "desk-lamp") == ["openhal-heartbeat-desk-lamp"]
    again = await client.post("/v1/device_files/load", json={"path": str(path)}, headers=bearer(person))
    assert again.json()["status"] == "unchanged"
    entries = hub.audit.entries(event="device_file_loaded")
    assert [entry.principal for entry in entries] == ["human:owner"]


async def test_a_new_file_is_added(hub: Hub, client: httpx.AsyncClient) -> None:
    person, _ = hub.tokens.create("owner", "human")
    path = hub.config.devices_dir / "shelf-lamp.hal.yaml"
    path.write_text(LAMP.replace("desk-lamp", "shelf-lamp"))
    loaded = await client.post("/v1/device_files/load", json={"path": str(path)}, headers=bearer(person))
    assert loaded.json()["status"] == "added"
    assert "shelf-lamp" in hub.kernel.devices
    assert not hub.kernel.devices["shelf-lamp"].file.writable


async def test_only_a_person_can_load_a_file(hub: Hub, client: httpx.AsyncClient) -> None:
    agent, _ = hub.tokens.create("claude", "agent", "control_medium")
    path = hub.config.devices_dir / "desk-lamp.hal.yaml"
    path.write_text(confirmed_text())
    refused = await client.post("/v1/device_files/load", json={"path": str(path)}, headers=bearer(agent))
    assert refused.status_code == 403
    assert not hub.kernel.devices["desk-lamp"].file.writable


@pytest.mark.parametrize(
    ("name", "text", "code"),
    [
        ("elsewhere", None, 409),
        ("missing.hal.yaml", None, 404),
        ("broken.hal.yaml", "device: [", 400),
        ("twin.hal.yaml", LAMP, 409),
    ],
)
async def test_files_that_cannot_load_say_why(
    hub: Hub, client: httpx.AsyncClient, tmp_path: Path, name: str, text: str | None, code: int
) -> None:
    person, _ = hub.tokens.create("owner", "human")
    path = tmp_path / "outside.hal.yaml" if name == "elsewhere" else hub.config.devices_dir / name
    if text is not None or name == "elsewhere":
        path.write_text(text or LAMP)
    loaded = await client.post("/v1/device_files/load", json={"path": str(path)}, headers=bearer(person))
    assert loaded.status_code == code, loaded.text
    assert sorted(hub.kernel.devices) == ["desk-lamp"]


async def test_a_config_folder_reached_through_a_symlink_reloads_its_own_file(tmp_path: Path) -> None:
    real = tmp_path / "real"
    (real / "devices").mkdir(parents=True)
    (real / "devices" / "desk-lamp.hal.yaml").write_text(LAMP)
    linked = tmp_path / "linked"
    linked.symlink_to(real)
    hub = Hub(HubConfig(home=linked), in_memory=True)
    await hub.start()
    try:
        (linked / "devices" / "desk-lamp.hal.yaml").write_text(confirmed_text())
        status, file = await hub.load_device_file(linked / "devices" / "desk-lamp.hal.yaml")
        assert (status, file.writable) == ("reloaded", True)
        assert sorted(hub.kernel.devices) == ["desk-lamp"]
    finally:
        await hub.close()
