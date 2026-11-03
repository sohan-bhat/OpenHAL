"""`openhal risk` shows and changes risk levels (ADR 0023) and follows the CLI's rules (ADR 0020).

A bare `openhal risk` shows each device's levels. Raising applies at once, lowering in a terminal
takes the typed phrase confirm, and with no terminal it waits for a person. Without a terminal a
left-out argument names the valid values and one command to copy.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openhal.cli import _common
from openhal.cli.main import app
from openhal.spec import risk
from openhal.spec.loader import load
from tests.interfaces.conftest import SyncHub
from tests.terminal import person_at_terminal

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="pseudo-terminals are POSIX only")

runner = CliRunner()

BOARD = """\
openhal: "0.1"
device: Bench board
id: bench
connect: { mock: bench }
write:
  brightness: { unit: percent, min: 0, max: 100, suggested: true }
  heater: { unit: percent, min: 0, max: 100, suggested: true }
provenance: { source: self-described }
"""


def run(*args: str) -> tuple[int, str]:
    result = runner.invoke(app, list(args))
    return result.exit_code, result.output


@pytest.fixture
def board(sync_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(_common, "TRANSPORT", sync_hub.transport)
    monkeypatch.setenv("OPENHAL_TOKEN", sync_hub.tokens.human)
    path = sync_hub.hub.config.devices_dir / "bench.hal.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(BOARD)
    sync_hub.runner.run(sync_hub.hub.load_device_file(path))
    return path


def level(path: Path, name: str) -> str:
    return risk.level(load(path), f"write:{name}")


def test_bare_risk_shows_each_device_and_a_command(board: Path) -> None:
    code, out = run("risk")
    assert code == 0, out
    assert "1 low, 1 high, 1 read-only" in out
    assert "See why with openhal risk show" in out
    assert "or change one with openhal risk set" in out


def test_show_lists_levels_and_reasons(board: Path) -> None:
    code, out = run("risk", "show", "bench", "--why")
    assert code == 0, out
    assert "heater" in out
    assert "read-only" in out
    assert "heater names heat" in out
    code, out = run("risk", "show", "bench.heatr")
    assert code == 2
    assert "Did you mean heater?" in out


def test_raising_applies_at_once(board: Path) -> None:
    code, out = run("risk", "set", "bench.brightness", "medium")
    assert code == 0, out
    assert "low to medium" in out
    assert level(board, "brightness") == "medium"


def test_lowering_in_a_terminal_takes_the_phrase(board: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with person_at_terminal(monkeypatch, ["confirm"]) as person:
        code, out = run("risk", "set", "bench.heater", "medium")
    assert code == 0, out
    assert "lower this risk level" in person.shown
    assert level(board, "heater") == "medium"


def test_lowering_with_no_terminal_waits_for_a_person(board: Path) -> None:
    code, out = run("risk", "set", "bench.heater", "low")
    assert code == 0, out
    assert "Held for a person" in out
    assert level(board, "heater") == "high"
    code, out = run("confirm", "list")
    assert "risk bench" in out
    assert "high to low" in out


def test_without_a_terminal_a_left_out_part_names_the_values(board: Path) -> None:
    code, out = run("risk", "set")
    assert code == 2
    assert "openhal risk set needs a device." in out
    assert "bench" in out
    code, out = run("risk", "set", "bench")
    assert code == 2
    assert "brightness, heater" in out
    assert "openhal risk set bench.brightness high" in out
    code, out = run("risk", "set", "bench.heater")
    assert code == 2
    assert "low, medium" in out
    code, out = run("risk", "set", "bench.heater", "extreme")
    assert code == 2
    assert "low, medium or high" in out
