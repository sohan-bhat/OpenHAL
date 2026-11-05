"""The /openhal command for Claude Code stays in step with the plugin and the MCP tools it names."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from openhal.mcp import TOOL_NAMES
from openhal.service import clients

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_SKILL = ROOT / "plugins" / "openhal" / "skills" / "openhal" / "SKILL.md"
SNAKE = re.compile(r"\b[a-z]+(?:_[a-z]+)+\b")


def test_the_plugin_ships_the_same_command_as_init() -> None:
    assert PLUGIN_SKILL.read_text(encoding="utf-8") == clients.SKILL_SOURCE.read_text(encoding="utf-8")


def test_the_command_is_named_openhal_and_takes_the_typed_words() -> None:
    text = clients.SKILL_SOURCE.read_text(encoding="utf-8")
    _, front, body = text.split("---", 2)
    meta = yaml.safe_load(front)
    assert meta["name"] == "openhal"
    assert meta["description"]
    assert "$ARGUMENTS" in body


def test_every_tool_the_command_names_exists() -> None:
    body = clients.SKILL_SOURCE.read_text(encoding="utf-8").split("---", 2)[2]
    named = set(SNAKE.findall(body)) - {"device_data"}
    assert named, "the command names the tools it uses"
    assert named <= set(TOOL_NAMES), sorted(named - set(TOOL_NAMES))
    for tool in re.findall(r"mcp__openhal__([a-z_]+)", body):
        assert tool in TOOL_NAMES
