"""The driver writer end to end through the API, with the firmware simulator as the unknown board."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from openhal.drivers.openhal_firmware.simulator import SIMULATORS
from openhal.hub.api import create_app
from openhal.hub.config import HubConfig
from openhal.hub.hub import Hub
from openhal.spec import load
from openhal.spec.loader import parse_yaml
from openhal.writer import interview, plan
from tests.kernel.conftest import FakeClock

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
async def hub(tmp_path: Path) -> AsyncIterator[Hub]:
    SIMULATORS.pop("writer", None)
    hub = Hub(HubConfig(home=tmp_path), clock=FakeClock(), in_memory=True)
    hub.config.devices_dir.mkdir(parents=True)
    await hub.start(load_devices=False)
    yield hub
    await hub.close()
    SIMULATORS.pop("writer", None)


@pytest.fixture
async def client(hub: Hub) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(hub), client=("127.0.0.1", 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:7420") as client:
        yield client


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def suggested_answers(questions: list[dict[str, Any]]) -> dict[str, Any]:
    answers = {}
    for question in questions:
        value = question["suggested"]
        if value is None:
            value = "none"
        elif question["unit"] and isinstance(value, int | float) and not isinstance(value, bool):
            value = f"{value} {question['unit']}"
        answers[question["id"]] = value
    return answers


async def test_unknown_board_to_confirmed_file(client: httpx.AsyncClient, hub: Hub) -> None:
    agent, _ = hub.tokens.create("claude", "agent", "control_low")
    person, _ = hub.tokens.create("me", "human")

    started = await client.post(
        "/v1/writer/sessions",
        json={"driver": "openhal-firmware", "params": {"port": "sim:writer", "timeout_s": 0.5}},
        headers=bearer(agent),
    )
    session = started.json()
    assert started.status_code == 200, session
    assert session["status"] == "interview"
    assert session["detected"]["source"] == "self-described"
    product = session["detected"]["identity"]["product"]
    assert product.startswith("<device-data"), "a product name the device reported is data, not a fact"
    assert "\nwriter\n" in product
    draft = parse_yaml(session["draft_yaml"])
    assert draft["write"]["fan_speed"]["suggested"] is True
    assert "confirmed" not in draft
    assert all(source.startswith("<device-data ") for source in session["sources"])

    draft["write"]["fan_speed"]["max"] = 1000
    draft["confirmed"] = {"by": "claude", "at": "2026-10-24"}
    draft["write"]["fan_speed"]["confirmed"] = {"by": "claude", "at": "2026-10-24"}
    import yaml

    proposed = await client.post(
        f"/v1/writer/sessions/{session['id']}/propose",
        json={"draft_yaml": yaml.safe_dump(draft)},
        headers=bearer(agent),
    )
    proposed_draft = parse_yaml(proposed.json()["draft_yaml"])
    assert "confirmed" not in proposed_draft
    assert "confirmed" not in proposed_draft["write"]["fan_speed"]
    assert proposed_draft["write"]["fan_speed"]["suggested"] is True

    questions = (await client.get(f"/v1/writer/sessions/{session['id']}/interview", headers=bearer(agent))).json()
    ids = [question["id"] for question in questions["questions"]]
    assert {"device.hazard", "fan_speed.min", "fan_speed.max", "fan_speed.safe", "fan_speed.confirm"} <= set(ids)
    answers = suggested_answers(questions["questions"])
    answers["fan_speed.max"] = "100 %"
    answers["device.hazard"] = "low"

    refused = await client.post(
        f"/v1/writer/sessions/{session['id']}/answers", json={"answers": answers}, headers=bearer(agent)
    )
    assert refused.status_code == 403
    assert "Answering the limits interview takes a human principal" in refused.json()["detail"]

    answered = (
        await client.post(
            f"/v1/writer/sessions/{session['id']}/answers", json={"answers": answers}, headers=bearer(person)
        )
    ).json()
    assert answered["status"] == "ready", answered["problems"]
    assert answered["unconfirmed"] == []
    confirmed = parse_yaml(answered["draft_yaml"])
    assert confirmed["write"]["fan_speed"]["max"] == 100
    assert "suggested" not in confirmed["write"]["fan_speed"]
    assert len(confirmed["confirmed"]["sha256"]) == 64

    test_plan = (await client.get(f"/v1/writer/sessions/{session['id']}/test_plan", headers=bearer(agent))).json()
    assert test_plan["problems"] == []
    writes = [
        step for step in test_plan["steps"] if isinstance(step["command"], dict) and step["command"]["kind"] == "write"
    ]
    assert writes
    assert all(step["needs_approval"] for step in writes)
    assert writes[0]["command"]["value"] == "1 percent"

    refused = await client.post(f"/v1/writer/sessions/{session['id']}/finish", json={}, headers=bearer(agent))
    assert refused.status_code == 403
    saved = (
        await client.post(
            f"/v1/writer/sessions/{session['id']}/finish", json={"save_as": "bench-fan"}, headers=bearer(person)
        )
    ).json()
    assert saved["writable"] is True
    file = load(saved["path"])
    assert file.writable
    assert file.provenance.source == "self-described"
    assert file.provenance.verification.status == "unverified"
    assert (Path(saved["bundle"]) / "TEST-REPORT.md").exists()

    hub.kernel.clock.advance(60)  # type: ignore[attr-defined]
    device = saved["device_id"]
    blocked = await client.post(
        "/v1/write", json={"device": device, "channel": "fan_speed", "value": 150, "unit": "%"}, headers=bearer(agent)
    )
    assert blocked.json()["code"] == "above_max"
    events = [entry.event for entry in hub.audit.entries(limit=200)]
    assert {"writer_start", "writer_propose", "writer_answer", "writer_finish"} <= set(events)

    again = await client.post(
        f"/v1/writer/sessions/{session['id']}/finish", json={"save_as": "bench-fan"}, headers=bearer(person)
    )
    assert again.status_code == 400


async def test_read_only_agent_cannot_start(client: httpx.AsyncClient, hub: Hub) -> None:
    viewer, _ = hub.tokens.create("viewer", "agent", "read")
    response = await client.post("/v1/writer/sessions", json={"manual_text": "VOLT <v>  Set"}, headers=bearer(viewer))
    assert response.status_code == 403


async def test_sketch_session(client: httpx.AsyncClient, hub: Hub) -> None:
    person, _ = hub.tokens.create("me", "human")
    session = (
        await client.post(
            "/v1/writer/sessions", json={"sketch_path": str(FIXTURES / "fan_text.ino")}, headers=bearer(person)
        )
    ).json()
    assert session["status"] == "interview"
    assert session["detected"]["sketch"]["baud"] == 115200
    assert "void loop()" in session["sources"][0]
    questions = (await client.get(f"/v1/writer/sessions/{session['id']}/interview", headers=bearer(person))).json()
    assert "fan.unit" in [question["id"] for question in questions["questions"]]


async def test_sketch_path_must_be_a_sketch(client: httpx.AsyncClient, hub: Hub, tmp_path: Path) -> None:
    person, _ = hub.tokens.create("me", "human")
    secret = tmp_path / "notes.txt"
    secret.write_text("private")
    response = await client.post("/v1/writer/sessions", json={"sketch_path": str(secret)}, headers=bearer(person))
    assert response.status_code == 400
    assert "not a sketch file" in response.json()["detail"]


async def test_unknown_session_is_404(client: httpx.AsyncClient, hub: Hub) -> None:
    person, _ = hub.tokens.create("me", "human")
    assert (await client.get("/v1/writer/sessions/nope", headers=bearer(person))).status_code == 404


def test_interview_rejects_bad_answers() -> None:
    draft = {
        "device": "Fan",
        "connect": {"mock": "x"},
        "write": {"speed": {"unit": "percent", "min": 0, "max": 100, "suggested": True}},
    }
    answers = {
        "device.hazard": "low",
        "speed.min": "50 %",
        "speed.max": "10 %",
        "speed.max_change_per_s": "none",
        "speed.safe": "0 %",
        "speed.confirm": "none",
        "device.interlocks": "none",
    }
    with pytest.raises(interview.AnswerError, match="above"):
        interview.apply(draft, answers, by="me")
    with pytest.raises(interview.AnswerError, match="still need"):
        interview.apply(draft, {"device.hazard": "low"}, by="me")
    answers.update({"speed.min": "0 %", "speed.max": "100 %", "speed.safe": "150 %"})
    with pytest.raises(interview.AnswerError, match="between"):
        interview.apply(draft, answers, by="me")
    answers.update({"speed.safe": "0 %", "speed.confirm": "sometimes"})
    with pytest.raises(interview.AnswerError, match="confirm"):
        interview.apply(draft, answers, by="me")
    answers.update({"speed.confirm": "none", "device.interlocks": "fan must be on"})
    with pytest.raises(interview.AnswerError, match="if <condition> require"):
        interview.apply(draft, answers, by="me")
    answers.update({"device.interlocks": "if speed > 50 % require speed < 90 %"})
    confirmed = interview.apply(draft, answers, by="me")
    assert confirmed["interlocks"] == [{"if": "speed > 50 %", "require": "speed < 90 %"}]


async def test_plan_validation_catches_a_step_the_kernel_would_block() -> None:
    from openhal.spec.loader import from_data

    file = from_data(
        {
            "device": "Fan",
            "connect": {"mock": "x"},
            "write": {"speed": {"unit": "percent", "min": 0, "max": 100, "max_change_per_s": 5}},
            "safe_state": {"speed": 0},
            "confirmed": {"by": "me", "at": "2026-10-24"},
        }
    )
    steps = plan.build(file)
    assert await plan.validate(file, steps) == []
    bad = [
        *steps,
        plan.TestStep(99, {"kind": "write", "device": "fan", "channel": "speed", "value": 150, "unit": "%"}, "", True),
    ]
    problems = await plan.validate(file, bad)
    assert problems
    assert problems[0].startswith("Step 99 would be blocked")


async def test_python_client_matches_the_real_writer_routes(hub: Hub) -> None:
    """The client was built against a fake. This walks the same flow against the real hub."""
    from openhal.client import AsyncClient
    from openhal.client.errors import Refused

    transport = httpx.ASGITransport(app=create_app(hub), client=("127.0.0.1", 50000))
    agent, _ = hub.tokens.create("claude", "agent", "control_low")
    person, _ = hub.tokens.create("me", "human")
    base = "http://127.0.0.1:7420"
    async with (
        AsyncClient(base, agent, transport=transport, use_human_token_file=False) as ai,
        AsyncClient(base, person, transport=transport, use_human_token_file=False) as me,
    ):
        session = await ai.start_writer(driver="openhal-firmware", params={"port": "sim:writer", "timeout_s": 0.5})
        assert session.status == "interview"
        questions = (await ai.interview(session.id)).questions
        answers = suggested_answers([question.model_dump() for question in questions])
        answers["device.hazard"] = "low"
        with pytest.raises(Refused):
            await ai.answer(session.id, answers)
        ready = await me.answer(session.id, answers)
        assert ready.status == "ready"
        assert (await ai.test_plan(session.id)).steps
        saved = await me.finish(session.id, "client-fan")
        assert saved.writable
        assert (await ai.writer_session(session.id)).status == "saved"
