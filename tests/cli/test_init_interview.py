"""`openhal init` offers the limits interview for each device it adds, at a real pseudo-terminal.

The board is the firmware simulator behind `sim:bench-heater`, which reports heater from 0 to 100 %.
A heater is high risk, so init offers the interview for it (ADR 0023).
Yes or no questions come from standard input and every limit answer and the phrase from the
terminal, as for a person at a real terminal. Nothing here runs discovery or touches a real config.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator

import pytest
from typer.testing import CliRunner

from openhal.cli import _tty
from openhal.cli.main import app
from openhal.drivers.openhal_firmware.simulator import SIMULATORS
from openhal.spec.loader import load
from tests.cli.conftest import Machine
from tests.terminal import person_at_terminal

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="pseudo-terminals are POSIX only")

runner = CliRunner()
INIT = ("init", "--no-discover", "--no-sample", "--no-service", "--device", "openhal-firmware=sim:bench-heater")
ANSWERS = ["", "", "120", "60", "", "", "", "", "confirm"]
"""Hazard, min, max typed past the board's 100 % then 60, rate, safe value, tier, interlocks, the phrase."""


@pytest.fixture(autouse=True)
def fresh_simulators() -> Iterator[None]:
    yield
    SIMULATORS.clear()


def run(*args: str, input: str | None = None) -> tuple[int, str]:
    result = runner.invoke(app, list(args), input=input)
    return result.exit_code, result.output


def test_init_walks_the_interview_and_saves_the_board_writable(
    machine: Machine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with person_at_terminal(monkeypatch, ANSWERS) as person:
        code, out = run(*INIT, input="\nskip\n")
    assert code == 0, out + person.shown
    path = machine.config / "devices" / "bench-heater.hal.yaml"
    file = load(path)
    assert file.writable
    assert file.write["heater"].max == 60
    assert person.typed == ANSWERS
    assert "Answer the high risk limits of Bench heater now?" in out
    assert "120 % is above 100 %, the most the device reports." in out
    assert f"confirmed      {path} by pi, writable" in out
    assert "Answer the high risk limits of bench-heater" not in out
    assert "restart" not in out.lower()


def test_declining_keeps_the_file_read_only_and_says_how_to_answer_later(
    machine: Machine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with person_at_terminal(monkeypatch, []) as person:
        code, out = run(*INIT, input="n\nskip\n")
    assert code == 0, out
    assert person.typed == []
    path = machine.config / "devices" / "bench-heater.hal.yaml"
    assert not load(path).writable
    assert f"Answer the high risk limits of bench-heater with openhal file confirm {path}" in out


def test_a_wrong_phrase_keeps_the_file_read_only_and_init_goes_on(
    machine: Machine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with person_at_terminal(monkeypatch, [*ANSWERS[:-1], "ok"]):
        code, out = run(*INIT, input="\nskip\n")
    assert code == 0, out
    path = machine.config / "devices" / "bench-heater.hal.yaml"
    assert not load(path).writable
    assert "kept read-only" in out
    assert "Next steps" in out


def test_yes_and_scripts_never_answer_a_limit(machine: Machine, monkeypatch: pytest.MonkeyPatch) -> None:
    with person_at_terminal(monkeypatch, ANSWERS) as person:
        code, out = run(*INIT, "--yes")
    assert code == 0, out
    assert person.typed == []
    assert not load(machine.config / "devices" / "bench-heater.hal.yaml").writable
    (machine.config / "devices" / "bench-heater.hal.yaml").unlink()
    monkeypatch.setattr(_tty, "interactive", lambda: False)
    SIMULATORS.clear()
    code, out = run(*INIT)
    assert code == 0, out
    assert "Answer each limit" not in out.split("Next steps")[0]
    assert not load(machine.config / "devices" / "bench-heater.hal.yaml").writable
