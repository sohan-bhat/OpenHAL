"""The files MCP directories and clients read agree with the package.

Gemini CLI reads gemini-extension.json, Claude Code reads .claude-plugin/marketplace.json and the
plugin it names, Glama reads glama.json, and Cline's marketplace reads llms-install.md. Each one
runs `openhal mcp` from the halkit package at the version in pyproject.toml.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any, Final

from openhal._brand import CLI_NAME, DISTRIBUTION_NAME

ROOT: Final = Path(__file__).resolve().parents[2]
VERSION: Final = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
RUN_FROM_PYPI: Final = {"command": "uvx", "args": ["--from", DISTRIBUTION_NAME, CLI_NAME, "mcp"]}


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def server(entry: dict[str, Any]) -> dict[str, Any]:
    return {"command": entry["command"], "args": entry["args"]}


def test_the_gemini_extension_runs_this_version() -> None:
    extension = read(ROOT / "gemini-extension.json")
    assert extension["version"] == VERSION
    assert server(extension["mcpServers"]["openhal"]) == RUN_FROM_PYPI
    assert [setting["envVar"] for setting in extension["settings"]] == ["OPENHAL_TOKEN"]
    assert extension["settings"][0]["sensitive"] is True


def test_the_claude_code_marketplace_names_a_plugin_that_runs_this_version() -> None:
    marketplace = read(ROOT / ".claude-plugin" / "marketplace.json")
    [entry] = marketplace["plugins"]
    assert entry["source"].startswith("./")
    plugin = read(ROOT / entry["source"] / ".claude-plugin" / "plugin.json")
    assert plugin["name"] == entry["name"]
    assert plugin["version"] == VERSION
    assert "version" not in entry, "the plugin's own version wins, so the entry leaves the version out"
    openhal = plugin["mcpServers"]["openhal"]
    assert server(openhal) == RUN_FROM_PYPI
    token = openhal["env"]["OPENHAL_TOKEN"].removeprefix("${user_config.").removesuffix("}")
    assert plugin["userConfig"][token]["sensitive"] is True


def test_glama_lists_a_maintainer() -> None:
    assert read(ROOT / "glama.json")["maintainers"]


def test_the_install_steps_for_agents_name_the_package_and_the_command() -> None:
    text = (ROOT / "llms-install.md").read_text(encoding="utf-8")
    assert f"--from {DISTRIBUTION_NAME} {CLI_NAME} mcp" in text
    assert '"args": ["mcp"]' in text


def test_the_logo_is_a_400_pixel_square_png() -> None:
    data = (ROOT / "docs" / "assets" / "logo-400.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    assert (width, height) == (400, 400)
