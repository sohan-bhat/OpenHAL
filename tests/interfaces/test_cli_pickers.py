"""Pickers for a left-out id at a real pseudo-terminal, and the rules person-only steps keep.

A picker chooses which pending request, routine, run or token a command works on. Approving,
enabling, running and revoking still take the human token and the typed phrase, an agent token
never gets a picker for those steps, and without a terminal the error lists the valid ids.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openhal.cli import _common
from openhal.cli.main import app
from openhal.hub.runs import RunBody
from openhal.kernel.principals import agent
from tests.interfaces.conftest import SyncHub
from tests.interfaces.test_client_routines import KEEP_COOL
from tests.kernel.conftest import FakeClock
from tests.terminal import ENTER, Keys, person_at_terminal

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="pseudo-terminals are POSIX only")

runner = CliRunner()


def run(*args: str) -> tuple[int, str]:
    """The exit code and the output with every run of spaces as one, so table columns read as words."""
    result = runner.invoke(app, list(args))
    return result.exit_code, " ".join(result.output.split())


@pytest.fixture
def cli_hub(sync_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> SyncHub:
    monkeypatch.setattr(_common, "TRANSPORT", sync_hub.transport)
    monkeypatch.setenv("OPENHAL_TOKEN", sync_hub.tokens.human)
    return sync_hub


def held(cli_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> str:
    """A purge request an agent sent, held for a person. The fan runs at 40 % first, as the heater's interlock needs."""
    clock: FakeClock = cli_hub.hub.kernel.clock  # type: ignore[assignment]
    monkeypatch.setenv("OPENHAL_TOKEN", cli_hub.tokens.medium)
    run("write", "desk-fan.fan_speed", "20 %")
    clock.advance(1)
    run("write", "desk-fan.fan_speed", "40 %")
    request_id = json.loads(run("action", "heater.purge", "--json")[1])["request_id"]
    monkeypatch.setenv("OPENHAL_TOKEN", cli_hub.tokens.human)
    return str(request_id)


def status_of(cli_hub: SyncHub, request_id: str) -> str:
    return cli_hub.hub.kernel.queue.get(request_id).status


def test_a_bare_confirm_lists_the_pending_requests(cli_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> None:
    code, out = run("confirm")
    assert (code, out.strip()) == (0, "No request is pending approval.")
    request_id = held(cli_hub, monkeypatch)
    code, out = run("confirm")
    assert code == 0, out
    assert "heater.purge" in out
    assert f"Approve one with openhal confirm approve {request_id}, or pick one with openhal confirm approve" in out
    assert json.loads(run("confirm", "--json")[1])[0]["id"] == request_id


def test_approve_without_a_terminal_lists_the_pending_ids(cli_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> None:
    request_id = held(cli_hub, monkeypatch)
    code, out = run("confirm", "approve")
    assert code == 2
    assert "openhal confirm approve needs a pending request." in out
    assert f"pending {request_id}" in out
    assert f"run openhal confirm approve {request_id}" in out
    assert status_of(cli_hub, request_id) == "pending"


def test_a_picked_request_still_takes_the_typed_phrase(cli_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> None:
    request_id = held(cli_hub, monkeypatch)
    with person_at_terminal(monkeypatch, [Keys("Pick a pending request", ENTER), "yes"]) as person:
        code, out = run("confirm", "approve")
    assert code == 1
    assert "heater.purge, from agent:builder" in person.text
    assert "did not match approve" in out
    assert status_of(cli_hub, request_id) == "pending"
    with person_at_terminal(monkeypatch, [Keys("Pick a pending request", ENTER), "approve"]):
        code, out = run("confirm", "approve")
    assert code == 0, out
    assert status_of(cli_hub, request_id) == "done"


def test_an_agent_token_never_gets_a_picker_for_a_person_step(
    cli_hub: SyncHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    request_id = held(cli_hub, monkeypatch)
    monkeypatch.setenv("OPENHAL_TOKEN", cli_hub.tokens.medium)
    shown = {}
    for command in (["confirm", "approve"], ["confirm", "reject"], ["routine", "enable"], ["token", "revoke"]):
        with person_at_terminal(monkeypatch, [Keys("Pick", ENTER), "approve"]) as person:
            code, shown[command[-1]] = run(*command)
        assert code == 2, command
        assert "Pick" not in person.text, command
        assert person.typed == [], command
    assert "openhal confirm approve takes the human token, and this token is agent:builder." in shown["approve"]
    assert f"pending {request_id}" in shown["approve"]
    assert "openhal confirm reject takes the human token, and this token is agent:builder." in shown["reject"]
    assert status_of(cli_hub, request_id) == "pending"


def test_show_and_reject_pick_a_request(cli_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> None:
    request_id = held(cli_hub, monkeypatch)
    with person_at_terminal(monkeypatch, [Keys("Pick a pending request", ENTER)]):
        code, out = run("confirm", "show")
    assert code == 0, out
    assert f"request {request_id}" in out
    with person_at_terminal(monkeypatch, [Keys("Pick a pending request", ENTER)]):
        code, out = run("confirm", "reject", "--reason", "not now")
    assert code == 0, out
    assert status_of(cli_hub, request_id) == "rejected"
    code, out = run("confirm", "show")
    assert code == 2
    assert "openhal confirm show needs a pending request. No request is pending approval." in out


def test_routines_list_pick_and_keep_their_phrases(
    cli_hub: SyncHub, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, out = run("routine")
    assert "No routines." in out
    code, out = run("routine", "new")
    assert code == 2
    assert "run openhal routine new keep-room-cool --file keep-room-cool.routine.yaml" in out
    source = tmp_path / "keep-cool.routine.yaml"
    source.write_text(KEEP_COOL)
    assert run("routine", "new", "keep-cool", "--file", str(source))[0] == 0
    code, out = run("routine")
    assert "Show one with openhal routine show keep-cool, or pick one with openhal routine show" in out
    code, out = run("routine", "enable")
    assert code == 2
    assert "routines keep-cool" in out
    for command in ("show", "dry-run"):
        with person_at_terminal(monkeypatch, [Keys("Pick a routine", ENTER)]):
            code, out = run("routine", command)
        assert code == 0, (command, out)
    with person_at_terminal(monkeypatch, [Keys("Pick a routine", ENTER), "enable"]) as person:
        code, out = run("routine", "enable")
    assert code == 0, out
    assert "keep-cool  disabled, desk-fan" in person.text
    assert "enabled keep-cool" in out
    for command, phrase in (("run", ["run"]), ("disable", [])):
        with person_at_terminal(monkeypatch, [Keys("Pick a routine", ENTER), *phrase]):
            code, out = run("routine", command)
        assert code == 0, (command, out)
    with person_at_terminal(monkeypatch, [Keys("Pick a routine", ENTER), Keys("Pick --device", ENTER), "approve"]):
        code, out = run("routine", "approve")
    assert code == 0, out
    assert "approved keep-cool on desk-fan" in out
    with person_at_terminal(monkeypatch, [Keys("Pick a routine", ENTER)]):
        code, out = run("routine", "delete", "--yes")
    assert code == 0, out
    assert "deleted keep-cool" in out


def test_runs_list_and_pick(cli_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> None:
    code, out = run("runs")
    assert (code, out.strip()) == (0, "No runs yet.")
    steps = [{"kind": "wait", "seconds": 0.01}]
    started = cli_hub.runner.run(cli_hub.hub.runs.start(agent("builder", "control_medium"), RunBody(steps=steps)))
    run_id = started["run_id"]
    code, out = run("runs")
    assert f"Show every step of one with openhal runs show {run_id}" in out
    code, out = run("runs", "show")
    assert code == 2
    assert f"runs {run_id}" in out
    with person_at_terminal(monkeypatch, [Keys("Pick a run", ENTER)]):
        code, out = run("runs", "show")
    assert code == 0, out
    assert run_id in out
    code, out = run("runs", "cancel")
    assert code == 2
    assert "openhal runs cancel needs a running run. No run is going now." in out


def test_tokens_list_and_revoke_with_a_picker(cli_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> None:
    code, out = run("token")
    assert code == 0, out
    assert "claude" in out
    assert "Create a token for an agent with openhal token create --name claude --scope control_low" in out
    assert {item["name"] for item in json.loads(run("token", "--json")[1])} >= {"owner", "claude"}
    code, out = run("token", "create")
    assert code == 2
    assert "run openhal token create --name claude" in out
    code, out = run("token", "create", "--human", "--scope", "control_low")
    assert "run openhal token create --name claude --human --scope control_low" in out
    code, out = run("token", "revoke")
    assert code == 2
    assert "openhal token revoke needs a token id." in out
    with person_at_terminal(monkeypatch, [Keys("Pick a token id", "viewer" + ENTER)]):
        code, out = run("token", "revoke")
    assert code == 0, out
    names = {item["name"] for item in json.loads(run("token", "list", "--json")[1])}
    assert "viewer" not in names
