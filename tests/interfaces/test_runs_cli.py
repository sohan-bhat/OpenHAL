"""`openhal runs`. People see and cancel runs and set the caps, and raising a cap takes the typed phrase."""

from __future__ import annotations

import json
import sys

import pytest
from typer.testing import CliRunner

from openhal.cli import _common
from openhal.cli.main import app
from openhal.hub.runs import RunBody
from openhal.kernel.principals import agent
from tests.interfaces.conftest import SyncHub
from tests.terminal import person_at_terminal

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="pseudo-terminals are POSIX only")

runner = CliRunner()
STEPS = [
    {"kind": "write", "device": "heater", "channel": "mode", "value": "eco"},
    {"kind": "wait", "seconds": 0.01},
    {"kind": "read", "targets": ["heater.mode"]},
    {"kind": "wait_until", "condition": "heater.mode == eco", "timeout_s": 1},
]


def run(*args: str) -> tuple[int, str]:
    result = runner.invoke(app, list(args))
    return result.exit_code, result.output


@pytest.fixture
def person(sync_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> SyncHub:
    monkeypatch.setattr(_common, "TRANSPORT", sync_hub.transport)
    monkeypatch.setenv("OPENHAL_TOKEN", sync_hub.tokens.human)
    return sync_hub


def test_caps_show_and_lower_at_once(person: SyncHub, monkeypatch: pytest.MonkeyPatch) -> None:
    code, out = run("runs", "caps")
    assert code == 0, out
    assert "max_steps    200" in out
    assert "per_agent    2" in out
    with person_at_terminal(monkeypatch, []) as terminal:
        code, out = run("runs", "caps", "--max-steps", "50", "--per-agent", "1")
    assert code == 0, out
    assert terminal.typed == []
    assert "max_steps    200 to 50" in out
    assert person.hub.config.runs.per_agent == 1
    code, out = run("runs", "caps", "--json")
    assert json.loads(out)["max_steps"] == 50


def test_raising_a_cap_takes_the_typed_phrase(person: SyncHub, monkeypatch: pytest.MonkeyPatch) -> None:
    with person_at_terminal(monkeypatch, ["confirm"]) as terminal:
        code, out = run("runs", "caps", "--max-seconds", "900")
    assert code == 0, out
    assert "Type confirm and press Enter to raise these run caps." in terminal.shown
    assert "max_seconds  600 to 900" in out
    with person_at_terminal(monkeypatch, ["yes"]):
        code, out = run("runs", "caps", "--max-seconds", "1200")
    assert code == 1
    assert "did not match confirm" in out
    assert person.hub.config.runs.max_seconds == 900


def test_with_no_terminal_raising_a_cap_changes_nothing(person: SyncHub) -> None:
    code, out = run("runs", "caps", "--max-seconds", "1200")
    assert code == 1
    assert "takes the typed phrase confirm" in out
    assert person.hub.config.runs.max_seconds == 600


def test_an_agent_token_cant_change_caps(person: SyncHub, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHAL_TOKEN", person.tokens.medium)
    code, out = run("runs", "caps", "--max-steps", "5")
    assert code == 1
    assert "takes a human principal" in out
    assert person.hub.config.runs.max_steps == 200


def test_list_show_and_cancel(person: SyncHub) -> None:
    code, out = run("runs", "list")
    assert (code, out.strip()) == (0, "No runs yet.")
    started = person.runner.run(person.hub.runs.start(agent("builder", "control_medium"), RunBody(steps=STEPS)))
    run_id = started["run_id"]
    code, out = run("runs", "list")
    assert code == 0, out
    assert run_id in out
    assert "agent:builder" in out
    assert "4 of 4" in out
    code, out = run("runs", "show", run_id)
    assert code == 0, out
    assert "write      done  heater write:mode eco" in out
    assert "wait       done  0.01 s" in out
    assert "read       done  heater.mode" in out
    assert "wait_until held  heater.mode == eco" in out
    assert json.loads(run("runs", "show", run_id, "--json")[1])["status"] == "done"
    assert json.loads(run("runs", "list", "--json")[1])[0]["run_id"] == run_id
    code, out = run("runs", "cancel", run_id)
    assert code == 0, out
    assert out.startswith("done")
    code, out = run("runs", "show", "run-nope")
    assert code == 1
    assert "There is no run run-nope" in out
