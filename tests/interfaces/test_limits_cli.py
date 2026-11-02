"""`openhal limits` and the MCP tool change a limit with no device file to edit.

Narrowing applies at once. Widening in a terminal takes the typed phrase confirm through a real
pseudo-terminal. A script, an agent's shell or an agent token gets a pending change instead, which
only a person approves with `openhal confirm approve` and the phrase approve.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest
import yaml
from typer.testing import CliRunner

from openhal.cli import _common
from openhal.cli.main import app
from openhal.client import AsyncClient
from openhal.hub.hub import Hub
from openhal.mcp import Tools
from openhal.spec.loader import load, parse_yaml
from openhal.writer import interview
from tests.interfaces.conftest import BASE_URL, SyncHub, Tokens
from tests.terminal import person_at_terminal

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="pseudo-terminals are POSIX only")

runner = CliRunner()

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


def run(*args: str, input: str | None = None) -> tuple[int, str]:
    result = runner.invoke(app, list(args), input=input)
    return result.exit_code, result.output


@pytest.fixture
def lamp(sync_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(_common, "TRANSPORT", sync_hub.transport)
    monkeypatch.setenv("OPENHAL_TOKEN", sync_hub.tokens.human)
    path = sync_hub.hub.config.devices_dir / "desk-lamp.hal.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(confirmed())
    sync_hub.runner.run(sync_hub.hub.load_device_file(path))
    return path


def brightness_max(path: Path) -> float:
    return float(load(path).write["brightness"].max or 0)


def test_show_lists_each_limit_with_the_device_range(lamp: Path) -> None:
    code, out = run("limits", "show", "desk-lamp")
    assert code == 0, out
    assert "0 % to 80 %" in out
    assert "0 % to 100 %" in out
    assert "confirmed by owner" in out


def test_narrowing_applies_at_once_with_no_phrase(lamp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with person_at_terminal(monkeypatch, []) as person:
        code, out = run("limits", "set", "desk-lamp.brightness", "--max", "60 %")
    assert code == 0, out
    assert person.typed == []
    assert "max   80 % to 60 %" in out
    assert brightness_max(lamp) == 60


def test_widening_in_a_terminal_takes_the_typed_phrase(lamp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with person_at_terminal(monkeypatch, ["confirm"]) as person:
        code, out = run("limits", "set", "desk-lamp.brightness", "--max", "100 %")
    assert code == 0, out
    assert "Type confirm and press Enter to widen these limits. Anything else cancels." in person.shown
    assert "max   80 % to 100 %" in out
    assert brightness_max(lamp) == 100


def test_a_wrong_phrase_changes_nothing(lamp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with person_at_terminal(monkeypatch, ["yes"]):
        code, out = run("limits", "set", "desk-lamp.brightness", "--max", "100 %")
    assert code == 1
    assert "did not match confirm" in out
    assert brightness_max(lamp) == 80


def test_widening_with_no_terminal_waits_for_a_person_to_approve(
    lamp: Path, sync_hub: SyncHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, out = run("limits", "set", "desk-lamp.brightness", "--max", "100 %")
    assert code == 0, out
    assert "pending" in out
    assert "Held for a person" in out
    assert brightness_max(lamp) == 80
    request_id = next(iter(sync_hub.hub.limits.requests))
    code, out = run("confirm", "list")
    assert request_id in out
    code, out = run("confirm", "show", request_id)
    assert "command limits desk-lamp.brightness max 80 % to 100 %" in out
    code, out = run("confirm", "approve", request_id)
    assert code == 1, "approving takes a terminal too"
    with person_at_terminal(monkeypatch, ["approve"]):
        code, out = run("confirm", "approve", request_id)
    assert code == 0, out
    assert brightness_max(lamp) == 100


def test_the_phrase_flag_widens_nothing_while_a_terminal_is_required(lamp: Path) -> None:
    code, out = run("limits", "set", "desk-lamp.brightness", "--max", "100 %", "--phrase", "confirm")
    assert code == 1
    assert "--phrase can't be used while confirm.require_tty is true" in out
    assert brightness_max(lamp) == 80


def test_an_agent_token_can_ask_but_never_approve(
    lamp: Path, sync_hub: SyncHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENHAL_TOKEN", sync_hub.tokens.agent)
    with person_at_terminal(monkeypatch, ["approve", "approve"]) as person:
        code, out = run("limits", "set", "desk-lamp.brightness", "--max", "100 %")
        assert code == 0, out
        assert "pending" in out
        assert person.typed == [], "an agent token never gets the phrase prompt"
        request_id = next(iter(sync_hub.hub.limits.requests))
        code, out = run("confirm", "approve", request_id)
    assert code != 0
    assert brightness_max(lamp) == 80


def test_nothing_goes_past_the_device_range(lamp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with person_at_terminal(monkeypatch, ["confirm"]) as person:
        code, out = run("limits", "set", "desk-lamp.brightness", "--max", "120 %")
    assert code == 1
    assert "120 % is above 100 %, the most desk-lamp reports for brightness" in out
    assert person.typed == []
    assert brightness_max(lamp) == 80


async def test_the_mcp_tool_narrows_at_once_and_files_a_widening_for_a_person(
    hub: Hub, tokens: Tokens, async_transport: httpx.ASGITransport
) -> None:
    path = hub.config.devices_dir / "desk-lamp.hal.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(confirmed())
    await hub.load_device_file(path)
    tools = Tools(AsyncClient(BASE_URL, tokens.agent, transport=async_transport, use_human_token_file=False))
    narrowed = await tools.request_limit_change("desk-lamp", "brightness", max={"value": 50, "unit": "%"})
    assert (narrowed["status"], narrowed["scope"]) == ("done", "session")
    held = await tools.request_limit_change("desk-lamp", "brightness", max={"value": 100, "unit": "%"})
    assert held["status"] == "pending"
    assert "a person approves the change" in held["message"]
    assert brightness_max(path) == 80
    async with httpx.AsyncClient(transport=async_transport, base_url=BASE_URL) as http:
        refused = await http.post(
            f"/v1/confirmations/{held['request_id']}/approve",
            json={"phrase": "approve"},
            headers={"Authorization": f"Bearer {tokens.agent}"},
        )
    assert refused.status_code == 403
    assert brightness_max(path) == 80
