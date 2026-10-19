"""The OpenHAL MCP server. Tools and prompts that forward to the hub. Start it with `openhal mcp`."""

from __future__ import annotations

from openhal.mcp.server import build_server, run
from openhal.mcp.tools import TOOL_NAMES, Tools

__all__ = ["TOOL_NAMES", "Tools", "build_server", "run"]
