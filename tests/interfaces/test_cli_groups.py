"""The routine, writer, token, doctor and mcp commands. Routines run on the real hub, the writer and
token routes on the fake."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openhal.cli import _common, _tty
from openhal.cli.main import app
from tests.interfaces.conftest import SplitTransport, SyncHub
from tests.interfaces.fake_hub import FakeHub
from tests.interfaces.test_client_routines import KEEP_COOL

runner = CliRunner()


def run(*args: str, input: str | None = None) -> tuple[int, str]:
    result = runner.invoke(app, list(args), input=input)
    return result.exit_code, result.output


def run_json(*args: str) -> object:
    return json.loads(runner.invoke(app, list(args)).stdout)


@pytest.fixture
def split(sync_hub: SyncHub, fake: FakeHub, monkeypatch: pytest.MonkeyPatch) -> SyncHub:
    fake.add_token(sync_hub.tokens.human, "human", "owner")
    fake.add_token(sync_hub.tokens.agent, "agent", "claude", "control_low")
    monkeypatch.setattr(_common, "TRANSPORT", SplitTransport(fake, real_sync=sync_hub.transport))
    monkeypatch.setenv("OPENHAL_TOKEN", sync_hub.tokens.human)
    return sync_hub


@pytest.fixture
def terminal(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    typed: list[str] = []
    monkeypatch.setattr(_tty, "interactive", lambda: True)
    monkeypatch.setattr(_tty, "read_phrase", lambda prompt: typed.pop(0))
    return typed


def test_routine_commands(split: SyncHub, tmp_path: Path, terminal: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "keep-cool.routine.yaml"
    source.write_text(KEEP_COOL)
    monkeypatch.setenv("OPENHAL_TOKEN", split.tokens.agent)
    code, out = run("routine", "new", "keep-cool", "--file", str(source))
    assert code == 0, out
    assert "disabled" in out
    code, out = run("routine", "dry-run", "keep-cool")
    assert code == 0, out
    assert "passes" in out
    terminal.append("enable")
    code, out = run("routine", "enable", "keep-cool")
    assert code == 1
    assert "human" in out

    monkeypatch.setenv("OPENHAL_TOKEN", split.tokens.human)
    code, out = run("routine", "list")
    assert "keep-cool" in out
    assert "disabled" in out
    terminal.append("enable")
    code, out = run("routine", "enable", "keep-cool")
    assert code == 0, out
    assert "enabled" in out
    code, out = run("routine", "show", "keep-cool")
    assert "every 30 s" in out
    assert "enabled by" in out
    terminal.append("run")
    code, out = run("routine", "run", "keep-cool")
    assert code == 0, out
    assert "ok" in out
    code, out = run("routine", "disable", "keep-cool")
    assert "disabled" in out
    terminal.append("approve")
    code, out = run("routine", "approve", "keep-cool", "--device", "heater")
    assert code == 0, out
    assert "voids the approval" in out
    code, out = run("routine", "show", "keep-cool", "--json")
    assert json.loads(out)["id"] == "keep-cool"
    code, out = run("routine", "delete", "keep-cool", "--yes")
    assert code == 0
    code, out = run("routine", "show", "keep-cool")
    assert code == 1
    assert "no routine" in out


def test_routine_run_needs_a_terminal(split: SyncHub) -> None:
    code, out = run("routine", "run", "keep-cool")
    assert code == 1
    assert "interactive terminal" in out


def test_writer_commands(split: SyncHub, tmp_path: Path, terminal: list[str]) -> None:
    sketch = tmp_path / "fan.ino"
    sketch.write_text("void setup() {}\n")
    code, out = run("writer", "start", "--sketch", str(sketch), "--param", "baud=115200")
    assert code == 0, out
    assert "session s1" in out
    draft = tmp_path / "draft.hal.yaml"
    draft.write_text("device: Fan\n")
    code, out = run("writer", "propose", "s1", "--file", str(draft))
    assert "unconfirmed" in out
    terminal.append("80")
    code, out = run("writer", "interview", "s1")
    assert code == 0, out
    assert "highest safe fan_speed" in out
    assert "openhal writer finish s1" in out
    terminal.append("save")
    code, out = run("writer", "finish", "s1", "--save-as", "desk-fan")
    assert code == 0, out
    assert "writable" in out
    code, out = run("writer", "plan", "s1")
    assert "needs approval" in out
    code, out = run("writer", "show", "s1", "--json")
    assert json.loads(out)["status"] == "saved"
    code, out = run("writer", "start")
    assert code == 2


def test_interview_answers_get_units(split: SyncHub, fake: FakeHub, terminal: list[str]) -> None:
    run("writer", "start", "--driver", "serial")
    terminal.append("80")
    run("writer", "interview", "s1")
    assert fake.sessions["s1"]["answers"] == {"q1": "80 percent"}


def test_token_commands_over_the_api(split: SyncHub, fake: FakeHub) -> None:
    code, out = run("token", "create", "--agent", "--scope", "control_low", "--name", "claude")
    assert code == 0, out
    assert out.strip().splitlines()[-1] == "ohal_new_t1"
    assert "only time" in out
    code, out = run("token", "list")
    assert "claude" in out
    code, out = run("token", "revoke", "t1")
    assert code == 0
    code, out = run("token", "list", "--all", "--json")
    assert json.loads(out)[0]["revoked"] is True
    code, out = run("token", "create", "--name", "x", "--scope", "everything")
    assert code == 2


def test_token_commands_without_a_hub(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code, out = run("--url", "http://127.0.0.1:9", "token", "list")
    assert code == 1
    assert "openhal init" in out
    run("init")
    code, out = run("--url", "http://127.0.0.1:9", "token", "create", "--name", "cursor", "--scope", "read")
    assert code == 0, out
    token = out.strip().splitlines()[-1]
    assert token.startswith("ohal_")
    from openhal.hub.tokens import TokenStore

    store = TokenStore(isolated_env / "hub.db")
    principal = store.principal(token)
    store.close()
    assert principal is not None
    assert (principal.kind, principal.scope) == ("agent", "read")
    listed = run_json("--url", "http://127.0.0.1:9", "token", "list", "--json")
    assert isinstance(listed, list)
    assert {item["name"] for item in listed} >= {"cursor"}
    cursor_id = next(item["token_id"] for item in listed if item["name"] == "cursor")
    code, out = run("--url", "http://127.0.0.1:9", "token", "revoke", cursor_id)
    assert code == 0, out
    code, out = run("--url", "http://127.0.0.1:9", "token", "revoke", cursor_id)
    assert code == 1


def test_doctor(isolated_env: Path, split: SyncHub, monkeypatch: pytest.MonkeyPatch) -> None:
    code, out = run("doctor")
    assert code == 1
    assert "openhal init" in out
    run("init")
    code, out = run("doctor")
    assert "config folder" in out
    assert "driver mock" in out
    assert "OPENHAL_TOKEN is set" in out
    assert code == 0, out
    (isolated_env / "human.token").chmod(0o644)
    code, out = run("doctor")
    assert code == 1
    assert "chmod 600" in out
    monkeypatch.setattr(_common, "TRANSPORT", None)
    code, out = run("--url", "http://127.0.0.1:9", "doctor")
    assert "Start the hub with openhald" in out


def test_mcp_needs_an_agent_token(isolated_env: Path) -> None:
    isolated_env.mkdir(parents=True, exist_ok=True)
    (isolated_env / "human.token").write_text("ohal_human\n")
    code, out = run("mcp", "--no-start")
    assert code == 4
    assert "agent token" in out


def test_discover_command(split: SyncHub) -> None:
    code, out = run("discover", "--driver", "mock")
    assert code == 0, out
    code, out = run("discover", "--driver", "mock", "--json")
    assert json.loads(out)["errors"] == []
