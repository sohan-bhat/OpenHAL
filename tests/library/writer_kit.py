"""The driver writer path a person follows for a lab instrument with a manual, as the library tests run it.

A session starts from the manual's command list and the serial driver's settings, the person's
agent proposes the library file as the draft, a person answers the limits interview with the
suggested answers, and the file is saved. Nothing reaches a real port. The serial settings name
pyserial's loopback, so the writer's read-only describe step opens no device.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from openhal.hub.api import create_app
from openhal.hub.config import HubConfig
from openhal.hub.hub import Hub
from openhal.spec import load
from openhal.spec.models import DeviceFile
from tests.kernel.conftest import FakeClock


@pytest.fixture
async def hub(tmp_path: Path) -> AsyncIterator[Hub]:
    hub = Hub(HubConfig(home=tmp_path), clock=FakeClock(), in_memory=True)
    hub.config.devices_dir.mkdir(parents=True)
    await hub.start(load_devices=False)
    yield hub
    await hub.close()


@pytest.fixture
async def client(hub: Hub) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(hub), client=("127.0.0.1", 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:7420") as client:
        yield client


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def unwrap(block: str) -> str:
    """The text inside a device-data block, which is how the writer returns what a manual said."""
    return block.splitlines()[-2]


def as_proposal(path: Path) -> dict[str, Any]:
    """A library file as the agent proposes it, keeping the manual as the draft's source."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["provenance"] = {"source": "manual", "tool": "openhal driver writer"}
    return data


async def write_from_manual(
    client: httpx.AsyncClient, hub: Hub, manual: str, params: dict[str, Any], library_file: Path, save_as: str
) -> tuple[dict[str, dict[str, Any]], dict[str, Any], DeviceFile]:
    """Run the writer from a manual to a saved file. Returns the extracted commands, the first draft and the file."""
    agent, _ = hub.tokens.create("claude", "agent", "control_low")
    person, _ = hub.tokens.create("me", "human")
    started = await client.post(
        "/v1/writer/sessions",
        json={"manual_text": manual, "driver": "serial", "params": {"port": "loop://", **params}},
        headers=bearer(agent),
    )
    session = started.json()
    assert started.status_code == 200, session
    assert session["draft_yaml"] is not None, session["problems"]
    commands = {unwrap(command["command"]): command for command in session["detected"]["manual_commands"]}
    first = yaml.safe_load(session["draft_yaml"])
    proposed = await client.post(
        f"/v1/writer/sessions/{session['id']}/propose",
        json={"draft_yaml": yaml.safe_dump(as_proposal(library_file))},
        headers=bearer(agent),
    )
    assert proposed.status_code == 200, proposed.json()
    questions = (await client.get(f"/v1/writer/sessions/{session['id']}/interview", headers=bearer(agent))).json()
    answers = {question["id"]: question["suggested"] for question in questions["questions"]}
    answered = (
        await client.post(
            f"/v1/writer/sessions/{session['id']}/answers", json={"answers": answers}, headers=bearer(person)
        )
    ).json()
    assert answered["status"] == "ready", answered["problems"]
    saved = (
        await client.post(
            f"/v1/writer/sessions/{session['id']}/finish", json={"save_as": save_as}, headers=bearer(person)
        )
    ).json()
    file = load(saved["path"])
    assert file.provenance.source == "manual"
    assert file.writable
    library = load(library_file)
    assert (set(file.read), set(file.write), set(file.actions)) == (
        set(library.read),
        set(library.write),
        set(library.actions),
    )
    return commands, first, file
