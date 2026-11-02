"""Changing a limit through the hub, never by editing the device file.

Narrowing applies at once. Widening needs a person: the typed phrase confirm applies it, and any
other request is held until a person approves it with the phrase approve. An agent can ask but never
approve, and nothing goes past the range the device reports.
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
from openhal.spec.loader import load, parse_yaml
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


def confirmed() -> str:
    draft = parse_yaml(LAMP)
    answers = {q.id: interview.suggestion_text(q) or "none" for q in interview.questions(draft)}
    answers.update({"brightness.max": "80 %", "brightness.confirm": "none", "device.hazard": "low"})
    return yaml.safe_dump(interview.apply(draft, answers, by="owner"), sort_keys=False)


@pytest.fixture
async def hub(tmp_path: Path) -> AsyncIterator[Hub]:
    (tmp_path / "devices").mkdir()
    (tmp_path / "devices" / "desk-lamp.hal.yaml").write_text(confirmed())
    hub = Hub(HubConfig(home=tmp_path), in_memory=True)
    await hub.start()
    yield hub
    await hub.close()


@pytest.fixture
async def client(hub: Hub) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(hub), client=("127.0.0.1", 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:4441") as client:
        yield client


@pytest.fixture
def tokens(hub: Hub) -> dict[str, str]:
    return {
        "person": hub.tokens.create("owner", "human")[0],
        "agent": hub.tokens.create("claude", "agent", "control_low")[0],
        "reader": hub.tokens.create("viewer", "agent", "read")[0],
    }


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def lamp_file(hub: Hub) -> Any:
    return load(hub.config.devices_dir / "desk-lamp.hal.yaml")


async def change(client: httpx.AsyncClient, token: str, **body: Any) -> dict[str, Any]:
    response = await client.post(
        "/v1/limits", json={"device": "desk-lamp", "channel": "brightness", **body}, headers=bearer(token)
    )
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


async def test_a_person_narrows_a_limit_in_the_file_at_once(
    hub: Hub, client: httpx.AsyncClient, tokens: dict[str, str]
) -> None:
    result = await change(client, tokens["person"], max={"value": 60, "unit": "%"})
    assert (result["status"], result["scope"]) == ("done", "file")
    assert result["changes"] == {"max": {"from": "80 %", "to": "60 %"}}
    file = lamp_file(hub)
    assert file.writable
    assert file.write["brightness"].max == 60
    assert file.confirmed.by == "owner"
    assert hub.kernel.devices["desk-lamp"].file.write["brightness"].max == 60
    entries = hub.audit.entries(event="limit_change", status="done")
    assert [entry.principal for entry in entries] == ["human:owner"]


async def test_an_agent_narrows_its_own_session_and_the_file_stays(
    hub: Hub, client: httpx.AsyncClient, tokens: dict[str, str]
) -> None:
    result = await change(client, tokens["agent"], max={"value": 50, "unit": "%"})
    assert (result["status"], result["scope"]) == ("done", "session")
    assert lamp_file(hub).write["brightness"].max == 80
    tried = await client.post(
        "/v1/dry_run",
        json={
            "commands": [
                {"kind": "write", "device": "desk-lamp", "channel": "brightness", "value": {"value": 55, "unit": "%"}}
            ]
        },
        headers=bearer(tokens["agent"]),
    )
    assert tried.json()[0]["code"] == "above_max"


async def test_widening_from_an_agent_waits_for_a_person_who_types_approve(
    hub: Hub, client: httpx.AsyncClient, tokens: dict[str, str]
) -> None:
    held = await change(client, tokens["agent"], max={"value": 100, "unit": "%"}, phrase="confirm")
    assert held["status"] == "pending"
    assert held["loosens"] == ["max"]
    request_id = held["request_id"]
    assert lamp_file(hub).write["brightness"].max == 80
    listed = (await client.get("/v1/confirmations", headers=bearer(tokens["person"]))).json()
    limit = next(item for item in listed if item["id"] == request_id)
    assert limit["command"]["kind"] == "limits"
    assert limit["requested_by"] == "agent:claude"
    assert limit["dry_run"]["status"] == "needs_confirmation"
    mine = (await client.get("/v1/confirmations", headers=bearer(tokens["agent"]))).json()
    assert [item["id"] for item in mine] == [request_id]

    approve = f"/v1/confirmations/{request_id}/approve"
    by_agent = await client.post(approve, json={"phrase": "approve"}, headers=bearer(tokens["agent"]))
    assert by_agent.status_code == 403
    unsaid = await client.post(approve, headers=bearer(tokens["person"]))
    assert unsaid.status_code == 400
    assert "Type approve" in unsaid.json()["detail"]
    assert lamp_file(hub).write["brightness"].max == 80

    done = await client.post(approve, json={"phrase": "approve"}, headers=bearer(tokens["person"]))
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "done"
    assert lamp_file(hub).write["brightness"].max == 100
    assert lamp_file(hub).confirmed.by == "owner"
    assert hub.kernel.devices["desk-lamp"].file.write["brightness"].max == 100
    again = await client.post(approve, json={"phrase": "approve"}, headers=bearer(tokens["person"]))
    assert again.status_code == 409


async def test_a_person_widens_at_once_with_the_phrase_and_waits_without_it(
    hub: Hub, client: httpx.AsyncClient, tokens: dict[str, str]
) -> None:
    wrong = await change(client, tokens["person"], max={"value": 90, "unit": "%"}, phrase="yes")
    assert wrong["status"] == "blocked"
    held = await change(client, tokens["person"], max={"value": 90, "unit": "%"})
    assert held["status"] == "pending"
    done = await change(client, tokens["person"], max={"value": 90, "unit": "%"}, rate="none", phrase="confirm")
    assert done["status"] == "done"
    assert set(done["loosens"]) == {"max", "rate"}
    assert lamp_file(hub).write["brightness"].max == 90
    assert lamp_file(hub).write["brightness"].max_change_per_s is None


async def test_nothing_goes_past_the_range_the_device_reports(
    hub: Hub, client: httpx.AsyncClient, tokens: dict[str, str]
) -> None:
    result = await change(client, tokens["person"], max={"value": 120, "unit": "%"}, phrase="confirm")
    assert result["status"] == "blocked"
    assert result["code"] == "above_max"
    assert "120 % is above 100 %, the most desk-lamp reports for brightness" in result["message"]
    held = await change(client, tokens["agent"], max={"value": 120, "unit": "%"})
    assert held["status"] == "blocked"
    assert lamp_file(hub).write["brightness"].max == 80


async def test_a_file_saved_without_the_device_range_takes_the_range_from_the_device(
    hub: Hub, client: httpx.AsyncClient, tokens: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = hub.config.devices_dir / "desk-lamp.hal.yaml"
    data = parse_yaml(confirmed())
    data.pop(interview.DEVICE_LIMITS)
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    await hub.load_device_file(path)
    driver = hub.kernel.devices["desk-lamp"].driver

    async def described() -> dict[str, Any]:
        return {"write": {"brightness": {"unit": "percent", "min": 0, "max": 100}}}

    monkeypatch.setattr(driver, "describe", described)
    shown = (await client.get("/v1/devices/desk-lamp/limits", headers=bearer(tokens["person"]))).json()
    assert shown["channels"]["brightness"]["device_range"] == [0, 100]
    result = await change(client, tokens["person"], max={"value": 120, "unit": "%"}, phrase="confirm")
    assert (result["status"], result["code"]) == ("blocked", "above_max")
    assert "the most desk-lamp reports for brightness" in result["message"]
    done = await change(client, tokens["person"], max={"value": 100, "unit": "%"}, phrase="confirm")
    assert done["status"] == "done"
    assert lamp_file(hub).write["brightness"].max == 100


async def test_a_read_only_token_and_a_read_only_file_change_nothing(
    hub: Hub, client: httpx.AsyncClient, tokens: dict[str, str]
) -> None:
    reader = await change(client, tokens["reader"], max={"value": 100, "unit": "%"})
    assert (reader["status"], reader["code"]) == ("blocked", "not_permitted")
    path = hub.config.devices_dir / "desk-lamp.hal.yaml"
    path.write_text(LAMP)
    await hub.load_device_file(path)
    result = await change(client, tokens["person"], max={"value": 60, "unit": "%"})
    assert (result["status"], result["code"]) == ("blocked", "read_only_file")
    assert "openhal file confirm" in result["message"]


async def test_a_stop_cancels_and_a_changed_file_blocks_a_pending_change(
    hub: Hub, client: httpx.AsyncClient, tokens: dict[str, str]
) -> None:
    first = await change(client, tokens["agent"], max={"value": 100, "unit": "%"})
    await client.post("/v1/stop", json={"reason": "test"}, headers=bearer(tokens["agent"]))
    shown = (await client.get(f"/v1/confirmations/{first['request_id']}", headers=bearer(tokens["person"]))).json()
    assert shown["status"] == "cancelled"
    await client.post("/v1/unlock", json={"phrase": "unlock"}, headers=bearer(tokens["person"]))

    second = await change(client, tokens["agent"], max={"value": 100, "unit": "%"})
    await change(client, tokens["person"], rate={"value": 4, "unit": "%/s"})
    approved = await client.post(
        f"/v1/confirmations/{second['request_id']}/approve",
        json={"phrase": "approve"},
        headers=bearer(tokens["person"]),
    )
    assert approved.json()["status"] == "blocked"
    assert "changed after the request" in approved.json()["message"]
    assert lamp_file(hub).write["brightness"].max == 80

    third = await change(client, tokens["agent"], max={"value": 90, "unit": "%"})
    rejected = await client.post(
        f"/v1/confirmations/{third['request_id']}/reject", json={"reason": "not now"}, headers=bearer(tokens["person"])
    )
    assert rejected.json()["status"] == "rejected"


async def test_a_dry_run_says_what_widens_and_show_gives_the_device_range(
    client: httpx.AsyncClient, tokens: dict[str, str]
) -> None:
    planned = await change(client, tokens["agent"], max={"value": 90, "unit": "%"}, dry_run=True)
    assert planned["status"] == "allowed"
    assert planned["loosens"] == ["max"]
    shown = (await client.get("/v1/devices/desk-lamp/limits", headers=bearer(tokens["agent"]))).json()
    assert shown["channels"]["brightness"]["device_range"] == [0.0, 100.0]
    assert shown["channels"]["brightness"]["max"] == 80
    assert shown["writable"] is True


async def test_a_range_that_leaves_out_the_safe_value_is_blocked(
    hub: Hub, client: httpx.AsyncClient, tokens: dict[str, str]
) -> None:
    result = await change(client, tokens["person"], min={"value": 10, "unit": "%"})
    assert result["status"] == "blocked"
    assert "The safe value 0 % would sit outside 10 % to 80 %" in result["message"]
    assert lamp_file(hub).write["brightness"].min == 0
