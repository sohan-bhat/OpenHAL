"""MCP client setup for Claude Desktop, Claude Code and Cursor (docs/interfaces/MCP.md).

`openhal init` prints the setup for every client, finds the clients this person has installed and
offers to register OpenHAL with each one. A config file is backed up before it changes, keeps every
other entry and is left as it is when it isn't valid JSON. Claude Code is registered at user scope
with its own `claude mcp add`, so every session gets the server. The client starts `openhal mcp`
with a token file, so no token goes into its config.
"""

from __future__ import annotations

import datetime as dt
import json
import shlex
import shutil
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from openhal._brand import CLI_NAME
from openhal.service.runner import Runner

SERVER_NAME: Final = CLI_NAME
CLIENT_KEYS: Final = ("claude-desktop", "claude-code", "cursor")
APPLICATION_DIRS: tuple[Path, ...] = (Path("/Applications"),)
"""Where macOS apps live besides ~/Applications. Tests point this at an empty folder."""
APPS: Final = {"claude-desktop": "Claude.app", "cursor": "Cursor.app"}
PROGRAMS: Final = {"claude-code": "claude", "cursor": "cursor"}


def find_program(name: str) -> str | None:
    """A program on PATH. Tests replace this so no real install is ever found."""
    return shutil.which(name)


class ClientConfigError(ValueError):
    """A client config file can't be changed safely. The message gives the reason."""


@dataclass(frozen=True, slots=True)
class McpClient:
    key: str
    title: str
    path: Path


def known_clients(user_home: Path, platform: str) -> list[McpClient]:
    """The three clients and where each keeps its config for this person."""
    if platform == "macos":
        desktop = user_home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    else:
        desktop = user_home / ".config" / "Claude" / "claude_desktop_config.json"
    return [
        McpClient("claude-desktop", "Claude Desktop", desktop),
        McpClient("claude-code", "Claude Code", user_home / ".claude.json"),
        McpClient("cursor", "Cursor", user_home / ".cursor" / "mcp.json"),
    ]


def installed(user_home: Path, platform: str) -> list[McpClient]:
    """The clients this person has, found by the program on PATH, the app or the client's config folder."""
    apps = [*APPLICATION_DIRS, user_home / "Applications"] if platform == "macos" else []
    found = []
    for client in known_clients(user_home, platform):
        program = PROGRAMS.get(client.key)
        app = APPS.get(client.key)
        present = (
            (program is not None and find_program(program) is not None)
            or (app is not None and any((folder / app).exists() for folder in apps))
            or (client.key != "claude-code" and client.path.parent.is_dir())
        )
        if present:
            found.append(client)
    return found


def client_for(key: str, user_home: Path, platform: str) -> McpClient:
    for client in known_clients(user_home, platform):
        if client.key == key:
            return client
    raise ClientConfigError(f"There is no MCP client {key!r}. Use {', '.join(CLIENT_KEYS)}.")


def cli_command() -> list[str]:
    """How a client starts this install's CLI. A full path, because clients may not use your PATH."""
    started = Path(sys.argv[0])
    if started.name == CLI_NAME and started.is_file():
        return [str(started.absolute())]
    found = shutil.which(CLI_NAME)
    if found:
        return [found]
    return [sys.executable, "-m", "openhal.cli.main"]


def server_entry(client: McpClient, command: list[str], token_file: Path) -> dict[str, Any]:
    entry: dict[str, Any] = {"command": command[0], "args": [*command[1:], "mcp", "--token-file", str(token_file)]}
    if client.key == "claude-code":
        return {"type": "stdio", **entry, "env": {}}
    return entry


def setup_text(client: McpClient, entry: dict[str, Any]) -> str:
    """What the person pastes or runs to add the server to this client."""
    if client.key == "claude-code":
        words = ["claude", "mcp", "add", SERVER_NAME, "--scope", "user", "--", entry["command"], *entry["args"]]
        return shlex.join(words)
    shown = {key: value for key, value in entry.items() if key in ("command", "args")}
    return json.dumps({"mcpServers": {SERVER_NAME: shown}}, indent=2)


def _backup(path: Path, runner: Runner) -> Path | None:
    if not path.exists():
        return None
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.openhal-backup-{stamp}")
    runner.copy(path, backup)
    return backup


def register(client: McpClient, entry: dict[str, Any], runner: Runner) -> tuple[Path | None, bool]:
    """Add the server to one client. Returns the backup's path and whether Claude Code's own CLI did it.

    Claude Code gets `claude mcp add` at user scope when `claude` is on PATH, after removing an older
    openhal entry at that scope. Every other client, and Claude Code without its CLI, gets its config
    file changed directly.
    """
    claude = find_program("claude") if client.key == "claude-code" else None
    if claude is None:
        return write_config(client, entry, runner), False
    backup = _backup(client.path, runner)
    runner.run([claude, "mcp", "remove", SERVER_NAME, "--scope", "user"], check=False)
    runner.run([claude, "mcp", "add", SERVER_NAME, "--scope", "user", "--", entry["command"], *entry["args"]])
    return backup, True


def write_config(client: McpClient, entry: dict[str, Any], runner: Runner) -> Path | None:
    """Add the server to the client's config. Returns the backup's path, or None for a new file."""
    path = client.path
    data: dict[str, Any] = {}
    backup: Path | None = None
    mode = 0o600
    if path.exists():
        text = path.read_text(encoding="utf-8")
        try:
            loaded = json.loads(text) if text.strip() else {}
        except json.JSONDecodeError as exc:
            raise ClientConfigError(f"{path} is not valid JSON ({exc.msg}), so it was left as it is.") from exc
        if not isinstance(loaded, dict):
            raise ClientConfigError(f"{path} is not a JSON object, so it was left as it is.")
        servers = loaded.get("mcpServers", {})
        if not isinstance(servers, dict):
            raise ClientConfigError(f"mcpServers in {path} is not an object, so the file was left as it is.")
        data = loaded
        mode = stat.S_IMODE(path.stat().st_mode)
        backup = _backup(path, runner)
    servers = data.setdefault("mcpServers", {})
    servers[SERVER_NAME] = entry
    runner.write(path, json.dumps(data, indent=2) + "\n", mode=mode)
    return backup
