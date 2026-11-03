"""A person changes a risk level through the hub, never by editing the device file (ADR 0023).

Raising applies at once. Lowering needs a person: the typed phrase confirm applies it, and any other
request is held until a person approves it with the phrase approve. Agents see every level and change
none, and each change lands in the device file and the audit log, so it survives a restart.
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
from openhal.kernel import Write, agent
from openhal.spec.loader import load

BOARD = """\
openhal: "0.1"
device: Bench board
id: board
connect: { mock: board }
read:
  uptime: { unit: s }
write:
  brightness: { unit: percent, min: 0, max: 100, suggested: true }
  heater: { unit: percent, min: 0, max: 100, suggested: true, map: { pin: 5 } }
  pin5: { type: bool, suggested: true, map: { pin: 5 } }
provenance: { source: self-described }
"""


@pytest.fixture
async def hub(tmp_path: Path) -> AsyncIterator[Hub]:
    (tmp_path / "devices").mkdir()
    (tmp_path / "devices" / "board.hal.yaml").write_text(BOARD)
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
        "agent": hub.tokens.create("claude", "agent", "control_medium")[0],
    }


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def change(client: httpx.AsyncClient, token: str, name: str, level: str, **extra: Any) -> dict[str, Any]:
    body = {"device": "board", "name": name, "level": level, **extra}
    response = await client.post("/v1/risk", json=body, headers=bearer(token))
    assert response.status_code == 200, response.text
    return dict(response.json())


def on_disk(hub: Hub) -> Any:
    return load(hub.config.devices_dir / "board.hal.yaml")


async def test_every_token_sees_every_level(client: httpx.AsyncClient, tokens: dict[str, str]) -> None:
    shown = (await client.get("/v1/devices/board/risk", headers=bearer(tokens["agent"]))).json()
    levels = {target: item["level"] for target, item in shown["targets"].items()}
    assert levels == {"read:uptime": "low", "write:brightness": "low", "write:heater": "high", "write:pin5": "high"}
    assert shown["targets"]["write:heater"]["read_only"] is True
    assert shown["targets"]["write:pin5"]["shared_with"] == ["write:heater"]
    view = (await client.get("/v1/devices/board", headers=bearer(tokens["agent"]))).json()
    assert (view["write"]["brightness"]["risk"], view["write"]["heater"]["read_only"]) == ("low", True)


async def test_an_agent_changes_no_level(hub: Hub, client: httpx.AsyncClient, tokens: dict[str, str]) -> None:
    for name, level in (("heater", "low"), ("brightness", "high")):
        result = await change(client, tokens["agent"], name, level)
        assert (result["status"], result["code"]) == ("blocked", "not_permitted")
    assert on_disk(hub).write["heater"].risk is None
    blocked = [entry.principal for entry in hub.audit.entries(event="risk_change") if entry.status == "blocked"]
    assert blocked == ["agent:claude", "agent:claude"]


async def test_raising_applies_at_once_and_lands_in_the_file(
    hub: Hub, client: httpx.AsyncClient, tokens: dict[str, str]
) -> None:
    claude = agent("claude", "control_medium")
    write = Write(device="board", channel="brightness", value="10 %")
    assert (await hub.kernel.execute(write, claude)).status == "done"
    result = await change(client, tokens["person"], "brightness", "high")
    assert (result["status"], result["before"], result["after"]) == ("done", "low", "high")
    assert (await hub.kernel.execute(write, claude)).code == "read_only_file"
    saved = on_disk(hub).write["brightness"].risk
    assert (saved.level, saved.by) == ("high", "owner")
    assert [entry.status for entry in hub.audit.entries(event="risk_change")] == ["done"]


async def test_lowering_needs_the_phrase_or_a_person_s_approval(
    hub: Hub, client: httpx.AsyncClient, tokens: dict[str, str]
) -> None:
    wrong = await change(client, tokens["person"], "heater", "medium", phrase="yes")
    assert (wrong["status"], wrong["code"]) == ("blocked", "bad_request")
    held = await change(client, tokens["person"], "pin5", "medium")
    assert held["status"] == "pending"
    listed = (await client.get("/v1/confirmations", headers=bearer(tokens["person"]))).json()
    assert [item["command"]["kind"] for item in listed] == ["risk"]
    assert (await client.get("/v1/confirmations", headers=bearer(tokens["agent"]))).json() == []
    approve = f"/v1/confirmations/{held['request_id']}/approve"
    refused = await client.post(approve, json={"phrase": "ok"}, headers=bearer(tokens["person"]))
    assert refused.status_code == 400
    approved = await client.post(approve, json={"phrase": "approve"}, headers=bearer(tokens["person"]))
    assert approved.json()["status"] == "blocked", "pin5 shares its pin with the heater, so it stays high"
    done = await change(client, tokens["person"], "heater", "medium", phrase="confirm")
    assert (done["status"], done["after"]) == ("done", "medium")
    shown = hub.risk.show("board")["targets"]
    assert (shown["write:heater"]["level"], shown["write:pin5"]["level"]) == ("medium", "medium")
    assert shown["write:heater"]["read_only"] is False


async def test_a_person_s_approval_applies_a_held_lowering(
    hub: Hub, client: httpx.AsyncClient, tokens: dict[str, str]
) -> None:
    await change(client, tokens["person"], "brightness", "high")
    held = await change(client, tokens["person"], "brightness", "low")
    approve = f"/v1/confirmations/{held['request_id']}/approve"
    approved = await client.post(approve, json={"phrase": "approve"}, headers=bearer(tokens["person"]))
    assert approved.json()["status"] == "done"
    assert on_disk(hub).write["brightness"].risk is None, "back to the table's own level drops the entry"


async def test_a_stop_cancels_and_a_reject_closes_a_held_lowering(
    hub: Hub, client: httpx.AsyncClient, tokens: dict[str, str]
) -> None:
    first = await change(client, tokens["person"], "heater", "low")
    rejected = await client.post(
        f"/v1/confirmations/{first['request_id']}/reject", json={"reason": "no"}, headers=bearer(tokens["person"])
    )
    assert rejected.json()["status"] == "rejected"
    second = await change(client, tokens["person"], "heater", "low")
    await hub.kernel.stop_all(agent("claude", "read"), "test")
    assert hub.risk.get(second["request_id"]).status == "cancelled"  # type: ignore[union-attr]


async def test_reading_stays_low_and_a_no_change_is_blocked(client: httpx.AsyncClient, tokens: dict[str, str]) -> None:
    reading = await change(client, tokens["person"], "uptime", "high")
    assert (reading["status"], reading["code"]) == ("blocked", "bad_request")
    same = await change(client, tokens["person"], "brightness", "low")
    assert same["code"] == "bad_request"
    missing = await client.post(
        "/v1/risk", json={"device": "board", "name": "nope", "level": "low"}, headers=bearer(tokens["person"])
    )
    assert missing.status_code == 404


async def test_a_level_survives_a_restart(hub: Hub, client: httpx.AsyncClient, tokens: dict[str, str]) -> None:
    await change(client, tokens["person"], "brightness", "medium")
    again = Hub(HubConfig(home=hub.config.home), in_memory=True)
    await again.start()
    try:
        assert again.risk.show("board")["targets"]["write:brightness"]["level"] == "medium"
    finally:
        await again.close()
