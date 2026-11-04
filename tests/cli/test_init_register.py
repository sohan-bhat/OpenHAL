"""`openhal init` registers OpenHAL with the MCP clients a person has, in a temporary HOME.

The fake runner records `claude mcp add` instead of running it, and every config file lives in the
test's own HOME, so no test touches the machine's ~/.claude.json or any client's real config.
"""

from __future__ import annotations

import json
import shlex

import pytest
from typer.testing import CliRunner

from openhal.cli import _tty
from openhal.cli.main import app
from openhal.service import clients
from tests.cli.conftest import Machine

runner = CliRunner()


@pytest.fixture
def claude_on_path(monkeypatch: pytest.MonkeyPatch) -> str:
    program = "/opt/claude/bin/claude"
    monkeypatch.setattr(clients, "find_program", lambda name: program if name == "claude" else None)
    return program


def run(*args: str, input: str | None = None) -> tuple[int, str]:
    result = runner.invoke(app, list(args), input=input)
    return result.exit_code, result.output


def test_the_wizard_offers_each_client_it_finds_with_yes_as_the_default(
    machine: Machine, claude_on_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_tty, "interactive", lambda: True)
    (machine.home / ".cursor").mkdir()
    code, out = run("init", "--no-discover", "--no-service", input="read\n\nn\n")
    assert code == 0, out
    assert "Found Claude Code, Cursor" in out
    assert "Add OpenHAL to Claude Code? [Y/n]" in out
    token = machine.config / "agent.token"
    add = [claude_on_path, "mcp", "add", "openhal", "--scope", "user", "--", *clients.cli_command()]
    assert machine.runner.commands[-2:] == [
        f"{claude_on_path} mcp remove openhal --scope user",
        " ".join([*add, "mcp", "--token-file", str(token)]),
    ]
    assert "Claude Code updated at user scope with claude mcp add" in out
    assert not (machine.home / ".cursor" / "mcp.json").exists(), "the person said no to Cursor"
    assert shlex.join(["claude", "mcp", "add", "openhal", "--scope", "user", "--"]) in out


def test_yes_registers_every_client_found_and_names_the_backups(machine: Machine, claude_on_path: str) -> None:
    (machine.home / ".claude.json").write_text(json.dumps({"projects": {}}))
    cursor = machine.home / ".cursor" / "mcp.json"
    cursor.parent.mkdir()
    cursor.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
    code, out = run("init", "--yes", "--no-discover")
    assert code == 0, out
    assert any(line.startswith(f"{claude_on_path} mcp add openhal --scope user --") for line in machine.runner.commands)
    assert f"backup of {machine.home / '.claude.json'} at" in out
    assert set(json.loads(cursor.read_text())["mcpServers"]) == {"other", "openhal"}
    backups = sorted(path.name for path in cursor.parent.iterdir() if "openhal-backup" in path.name)
    assert len(backups) == 1
    assert f"{cursor} updated, backup at {cursor.parent / backups[0]}" in out


def test_nothing_is_registered_when_no_client_is_found(machine: Machine) -> None:
    code, out = run("init", "--yes", "--no-discover")
    assert code == 0, out
    assert "Found" not in out
    assert machine.runner.commands == []
    assert not (machine.home / ".claude.json").exists()


def test_no_clients_registers_nothing_even_with_yes(machine: Machine, claude_on_path: str) -> None:
    (machine.home / ".cursor").mkdir()
    code, out = run("init", "--yes", "--no-clients", "--no-discover")
    assert code == 0, out
    assert "Found" not in out
    assert machine.runner.commands == []
    assert not (machine.home / ".claude.json").exists()
    assert not (machine.home / ".cursor" / "mcp.json").exists()
    assert "Claude Code, run this" in out, "the setup for each client is still printed"


def test_a_named_client_is_still_written_with_no_clients(machine: Machine) -> None:
    code, out = run("init", "--yes", "--no-clients", "--no-discover", "--client", "cursor")
    assert code == 0, out
    assert "openhal" in json.loads((machine.home / ".cursor" / "mcp.json").read_text())["mcpServers"]
