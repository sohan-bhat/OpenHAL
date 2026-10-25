"""MCP client setup for Claude Desktop, Claude Code and Cursor (docs/interfaces/MCP.md).

`openhal init` prints the setup for every client. It writes a client's config file only when the
person asks, backs the file up first, keeps every other entry in it and refuses a file that isn't
valid JSON. The client starts `openhal mcp` with a token file, so no token goes into its config.
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


class ClientConfigError(ValueError):
    """A client config file can't be changed safely. The message says why."""


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
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = path.with_name(f"{path.name}.openhal-backup-{stamp}")
        runner.copy(path, backup)
    servers = data.setdefault("mcpServers", {})
    servers[SERVER_NAME] = entry
    runner.write(path, json.dumps(data, indent=2) + "\n", mode=mode)
    return backup
