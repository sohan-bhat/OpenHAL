"""A review session answers the limits interview for a device file the hub already loaded.

Only a human principal starts, answers or finishes a review, the typed phrase comes last, a value
past what the device reports is held back with the reason, and the confirmed file loads at once.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from openhal.hub.api import create_app
from openhal.hub.config import HubConfig
from openhal.hub.hub import Hub
from openhal.spec.loader import load

LAMP = """\
openhal: "0.1"
device: Desk lamp
id: desk-lamp
connect: { mock: desk-lamp }
write:
  brightness: { unit: percent, min: 0, max: 100, suggested: true }
provenance: { source: self-described, tool: openhal init }
"""


@pytest.fixture
async def hub(tmp_path: Path) -> AsyncIterator[Hub]:
    (tmp_path / "devices").mkdir()
    (tmp_path / "devices" / "desk-lamp.hal.yaml").write_text(LAMP)
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


def answers(questions: list[dict[str, Any]], **changes: str) -> dict[str, str]:
    given = {}
    for question in questions:
        value = question["suggested"]
        given[question["id"]] = f"{value} %" if question["unit"] == "percent" else str(value)
    given.update(changes)
    return given


async def test_a_person_reviews_a_read_only_file_and_the_hub_loads_it_writable(
    hub: Hub, client: httpx.AsyncClient
) -> None:
    person, _ = hub.tokens.create("owner", "human")
    started = await client.post("/v1/writer/sessions", json={"device": "desk-lamp"}, headers=bearer(person))
    assert started.status_code == 200, started.text
    session = started.json()
    assert session["status"] == "interview"
    assert session["device"] == "desk-lamp"
    path = f"/v1/writer/sessions/{session['id']}"
    questions = (await client.get(f"{path}/interview", headers=bearer(person))).json()["questions"]
    maximum = next(question for question in questions if question["id"] == "brightness.max")
    assert maximum["range"] == [0.0, 100.0]
    assert maximum["prompt"] == "brightness, in percent. The most an agent may set."

    held = (
        await client.post(
            f"{path}/answers",
            json={"answers": answers(questions, **{"brightness.max": "120 %"})},
            headers=bearer(person),
        )
    ).json()
    assert held["status"] == "interview"
    assert "120 % is above 100 %, the most the device reports" in held["answer_problems"]["brightness.max"]
    still = (await client.get(f"{path}/interview", headers=bearer(person))).json()["questions"]
    assert [question["id"] for question in still] == ["brightness.max"]

    ready = (
        await client.post(f"{path}/answers", json={"answers": {"brightness.max": "60 %"}}, headers=bearer(person))
    ).json()
    assert ready["status"] == "ready", ready
    assert ready["answer_problems"] == {}

    unsaid = await client.post(f"{path}/finish", json={}, headers=bearer(person))
    assert unsaid.status_code == 400
    assert "Type confirm" in unsaid.json()["detail"]
    wrong = await client.post(f"{path}/finish", json={"phrase": "yes"}, headers=bearer(person))
    assert wrong.status_code == 400
    assert not hub.kernel.devices["desk-lamp"].file.writable

    saved = await client.post(f"{path}/finish", json={"phrase": "confirm"}, headers=bearer(person))
    assert saved.status_code == 200, saved.text
    assert saved.json() == {
        "path": str(hub.config.devices_dir / "desk-lamp.hal.yaml"),
        "device_id": "desk-lamp",
        "writable": True,
        "loaded": True,
    }
    runtime = hub.kernel.devices["desk-lamp"]
    assert runtime.file.writable
    assert runtime.file.write["brightness"].max == 60
    on_disk = load(hub.config.devices_dir / "desk-lamp.hal.yaml")
    assert on_disk.writable
    assert on_disk.confirmed is not None
    assert on_disk.confirmed.by == "owner"


async def test_an_agent_can_never_start_answer_or_finish_a_review(hub: Hub, client: httpx.AsyncClient) -> None:
    agent, _ = hub.tokens.create("claude", "agent", "control_medium")
    person, _ = hub.tokens.create("owner", "human")
    refused = await client.post("/v1/writer/sessions", json={"device": "desk-lamp"}, headers=bearer(agent))
    assert refused.status_code == 403
    session = (await client.post("/v1/writer/sessions", json={"device": "desk-lamp"}, headers=bearer(person))).json()
    path = f"/v1/writer/sessions/{session['id']}"
    questions = (await client.get(f"{path}/interview", headers=bearer(agent))).json()["questions"]
    answered = await client.post(f"{path}/answers", json={"answers": answers(questions)}, headers=bearer(agent))
    assert answered.status_code == 403
    await client.post(f"{path}/answers", json={"answers": answers(questions)}, headers=bearer(person))
    finished = await client.post(f"{path}/finish", json={"phrase": "confirm"}, headers=bearer(agent))
    assert finished.status_code == 403
    proposed = await client.post(f"{path}/propose", json={"draft_yaml": LAMP}, headers=bearer(agent))
    assert proposed.status_code == 400
    assert not hub.kernel.devices["desk-lamp"].file.writable
    assert "suggested: true" in (hub.config.devices_dir / "desk-lamp.hal.yaml").read_text()


async def test_a_file_changed_during_the_review_is_left_alone(hub: Hub, client: httpx.AsyncClient) -> None:
    person, _ = hub.tokens.create("owner", "human")
    session = (await client.post("/v1/writer/sessions", json={"device": "desk-lamp"}, headers=bearer(person))).json()
    path = f"/v1/writer/sessions/{session['id']}"
    questions = (await client.get(f"{path}/interview", headers=bearer(person))).json()["questions"]
    await client.post(f"{path}/answers", json={"answers": answers(questions)}, headers=bearer(person))
    edited = LAMP.replace("max: 100", "max: 90")
    (hub.config.devices_dir / "desk-lamp.hal.yaml").write_text(edited)
    saved = await client.post(f"{path}/finish", json={"phrase": "confirm"}, headers=bearer(person))
    assert saved.status_code == 400
    assert "changed after the review started" in saved.json()["detail"]
    assert (hub.config.devices_dir / "desk-lamp.hal.yaml").read_text() == edited


async def test_a_device_without_a_file_has_nothing_to_review(hub: Hub, client: httpx.AsyncClient) -> None:
    person, _ = hub.tokens.create("owner", "human")
    missing = await client.post("/v1/writer/sessions", json={"device": "nobody"}, headers=bearer(person))
    assert missing.status_code == 404
