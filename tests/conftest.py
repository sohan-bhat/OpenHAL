"""Settings for the whole test session.

Typer forces a color terminal when GITHUB_ACTIONS, FORCE_COLOR or PY_COLORS is set, so CLI output in
CI carried escape codes that tests comparing text don't expect. Tests run with a plain terminal on
every machine, and so do the CLI processes they start.

No test finds the machine's own MCP clients. `openhal init` registers OpenHAL with the Claude Code,
Claude Desktop and Cursor it finds, so every test sees no client program on PATH, no app folder and
no client in the real home folder. Tests that check registration use a temporary home.

No test reaches real hardware or the machine's own hub (tests/no_hardware.py). Serial port listing,
`openhal-firmware: auto` and every other driver's discovery find no real device, the hub's home is
a temporary folder and the hub address is a loopback port nothing listens on.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from openhal.service import clients
from tests import no_hardware

for variable in ("GITHUB_ACTIONS", "FORCE_COLOR", "PY_COLORS"):
    os.environ.pop(variable, None)

no_hardware.isolate_environment()

REAL_HOME = Path(os.path.expanduser("~")).resolve()
FIND_CLIENTS = clients.installed


def _installed_outside_the_real_home(user_home: Path, platform: str) -> list[clients.McpClient]:
    return [] if user_home.resolve() == REAL_HOME else FIND_CLIENTS(user_home, platform)


@pytest.fixture(autouse=True)
def no_real_mcp_clients(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(clients, "find_program", lambda name: None)
    monkeypatch.setattr(clients, "APPLICATION_DIRS", (tmp_path / "no-applications",))
    monkeypatch.setattr(clients, "installed", _installed_outside_the_real_home)


@pytest.fixture(autouse=True)
def no_real_hardware(monkeypatch: pytest.MonkeyPatch) -> None:
    no_hardware.guard(monkeypatch)
