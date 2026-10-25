"""MCP client setup for init. Every config file lives in a temporary HOME."""

from __future__ import annotations

import json
import shlex
import stat
from pathlib import Path

import pytest

from openhal.service import clients
from openhal.service.runner import Runner

TOKEN = Path("/home/pi/.openhal/agent.token")
COMMAND = ["/home/pi/.local/bin/openhal"]


def client(home: Path, key: str) -> clients.McpClient:
    return clients.client_for(key, home, "macos")


def test_each_client_has_its_config_path(tmp_path: Path) -> None:
    mac = {item.key: item.path for item in clients.known_clients(tmp_path, "macos")}
    linux = {item.key: item.path for item in clients.known_clients(tmp_path, "linux")}
    assert (
        mac["claude-desktop"] == tmp_path / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    )
    assert linux["claude-desktop"] == tmp_path / ".config" / "Claude" / "claude_desktop_config.json"
    assert mac["claude-code"] == linux["claude-code"] == tmp_path / ".claude.json"
    assert mac["cursor"] == tmp_path / ".cursor" / "mcp.json"
    with pytest.raises(clients.ClientConfigError, match="no MCP client"):
        clients.client_for("vim", tmp_path, "macos")


def test_setup_text_uses_a_token_file(tmp_path: Path) -> None:
    desktop = client(tmp_path, "claude-desktop")
    shown = json.loads(clients.setup_text(desktop, clients.server_entry(desktop, COMMAND, TOKEN)))
    assert shown == {"mcpServers": {"openhal": {"command": COMMAND[0], "args": ["mcp", "--token-file", str(TOKEN)]}}}
    code = client(tmp_path, "claude-code")
    words = shlex.split(clients.setup_text(code, clients.server_entry(code, COMMAND, TOKEN)))
    assert words[:7] == ["claude", "mcp", "add", "openhal", "--scope", "user", "--"]
    assert words[7:] == [*COMMAND, "mcp", "--token-file", str(TOKEN)]


def test_a_python_command_keeps_its_module(tmp_path: Path) -> None:
    cursor = client(tmp_path, "cursor")
    entry = clients.server_entry(cursor, ["/usr/bin/python3", "-m", "openhal.cli.main"], TOKEN)
    assert entry["args"] == ["-m", "openhal.cli.main", "mcp", "--token-file", str(TOKEN)]


def test_writing_merges_and_keeps_a_backup(tmp_path: Path) -> None:
    cursor = client(tmp_path, "cursor")
    cursor.path.parent.mkdir()
    original = json.dumps({"mcpServers": {"other": {"command": "other"}}, "theme": "dark"})
    cursor.path.write_text(original)
    cursor.path.chmod(0o644)
    backup = clients.write_config(cursor, clients.server_entry(cursor, COMMAND, TOKEN), Runner())
    data = json.loads(cursor.path.read_text())
    assert set(data["mcpServers"]) == {"other", "openhal"}
    assert data["theme"] == "dark"
    assert stat.S_IMODE(cursor.path.stat().st_mode) == 0o644
    assert backup is not None
    assert backup.read_text() == original
    assert backup.name.startswith("mcp.json.openhal-backup-")


def test_a_new_file_is_private_and_needs_no_backup(tmp_path: Path) -> None:
    code = client(tmp_path, "claude-code")
    assert clients.write_config(code, clients.server_entry(code, COMMAND, TOKEN), Runner()) is None
    data = json.loads(code.path.read_text())
    assert data["mcpServers"]["openhal"]["type"] == "stdio"
    assert stat.S_IMODE(code.path.stat().st_mode) == 0o600


@pytest.mark.parametrize("text", ["{ not json", "[1, 2]", '{"mcpServers": []}'])
def test_a_file_it_cannot_read_is_left_alone(tmp_path: Path, text: str) -> None:
    cursor = client(tmp_path, "cursor")
    cursor.path.parent.mkdir()
    cursor.path.write_text(text)
    with pytest.raises(clients.ClientConfigError, match="left as it is"):
        clients.write_config(cursor, clients.server_entry(cursor, COMMAND, TOKEN), Runner())
    assert cursor.path.read_text() == text
    assert list(cursor.path.parent.iterdir()) == [cursor.path]


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    lines: list[str] = []
    cursor = client(tmp_path, "cursor")
    clients.write_config(cursor, clients.server_entry(cursor, COMMAND, TOKEN), Runner(dry_run=True, echo=lines.append))
    assert not cursor.path.exists()
    assert lines == [f"would write  {cursor.path}"]
