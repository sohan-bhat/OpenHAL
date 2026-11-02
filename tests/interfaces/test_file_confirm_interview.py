"""`openhal file confirm` on a file with suggested limits walks the limits interview at the terminal.

Answers come through a real pseudo-terminal, one per question. Enter keeps a suggestion, a typed
value replaces it, a value past what the device reports is asked again, and the person types
confirm once. A script, an agent or `--phrase` while confirm.require_tty is true answers nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openhal.cli import _common
from openhal.cli.main import app
from openhal.spec.loader import load
from tests.interfaces.conftest import SyncHub
from tests.terminal import person_at_terminal

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="pseudo-terminals are POSIX only")

runner = CliRunner()

LAMP = """\
openhal: "0.1"
device: Desk lamp
id: desk-lamp
connect: { mock: desk-lamp }
write:
  brightness: { unit: percent, min: 0, max: 100, suggested: true }
provenance: { source: self-described, tool: openhal init }
"""

ANSWERS = ["", "", "150", "80", "", "", "", "", "confirm"]
"""Hazard, min, max typed past the device's 100 % then 80, rate, safe value, tier, interlocks, the phrase."""


def lamp_file(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "desk-lamp.hal.yaml"
    path.write_text(LAMP)
    return path


def run(*args: str, input: str | None = None) -> tuple[int, str]:
    result = runner.invoke(app, list(args), input=input)
    return result.exit_code, result.output


def test_the_interview_runs_inline_and_saves_a_writable_file(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = lamp_file(isolated_env / "devices")
    with person_at_terminal(monkeypatch, ANSWERS) as person:
        code, out = run("file", "confirm", str(path), "--by", "owner")
    assert code == 0, out + person.shown
    assert "Press Enter to keep a suggestion, or type a value to replace it." in out
    assert "3 of 7  brightness, in percent. The most an agent may set. Suggested 100 %." in out
    assert "150 % is above 100 %, the most the device reports. Answer a value from 0 % to 100 %." in out
    assert "Type confirm and press Enter to confirm these limits as safe for this device." in person.shown
    assert person.typed == ANSWERS
    file = load(path)
    assert file.writable
    assert file.write["brightness"].max == 80
    assert file.write["brightness"].confirm == "confirm"
    assert file.confirmed is not None
    assert file.confirmed.by == "owner"
    assert "suggested" not in path.read_text()
    assert "desk-lamp is writable once OpenHAL starts. Start OpenHAL with openhal start." in out
    assert "Restart" not in out


def test_a_wrong_phrase_saves_nothing(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = lamp_file(isolated_env / "devices")
    with person_at_terminal(monkeypatch, [*ANSWERS[:-1], "yes"]):
        code, out = run("file", "confirm", str(path))
    assert code == 1
    assert "did not match confirm" in out
    assert path.read_text() == LAMP


def test_a_script_with_no_terminal_answers_nothing(isolated_env: Path) -> None:
    path = lamp_file(isolated_env / "devices")
    code, out = run("file", "confirm", str(path), input="\n" * 20 + "confirm\n")
    assert code == 1
    assert "interactive terminal" in out
    assert "1 of" not in out, "no question is asked where no person can answer"
    assert path.read_text() == LAMP


def test_the_phrase_flag_answers_nothing_while_a_terminal_is_required(isolated_env: Path) -> None:
    path = lamp_file(isolated_env / "devices")
    code, out = run("file", "confirm", str(path), "--phrase", "confirm", input="\n" * 20)
    assert code == 1
    assert "--phrase can't be used while confirm.require_tty is true" in out
    assert path.read_text() == LAMP


def test_without_the_terminal_rule_answers_and_the_phrase_come_from_the_command(isolated_env: Path) -> None:
    path = lamp_file(isolated_env / "devices")
    (isolated_env / "config.yaml").write_text("confirm: { require_tty: false }\n")
    code, out = run("file", "confirm", str(path), "--phrase", "confirm", input="\n\n90\n\n\n\n\n")
    assert code == 0, out
    assert load(path).write["brightness"].max == 90


def test_a_running_hub_loads_the_confirmed_file_at_once(cli_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> None:
    path = lamp_file(cli_hub.hub.config.devices_dir)
    with person_at_terminal(monkeypatch, ANSWERS):
        code, out = run("file", "confirm", str(path))
    assert code == 0, out
    assert "desk-lamp is now writable." in out
    runtime = cli_hub.hub.kernel.devices["desk-lamp"]
    assert runtime.file.writable
    assert runtime.file.write["brightness"].max == 80


def test_an_agent_token_cannot_load_the_file_into_the_hub(cli_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHAL_TOKEN", cli_hub.tokens.agent)
    path = lamp_file(cli_hub.hub.config.devices_dir)
    with person_at_terminal(monkeypatch, ANSWERS):
        code, out = run("file", "confirm", str(path))
    assert code == 0, out
    assert "desk-lamp" not in cli_hub.hub.kernel.devices
    assert "loading the file now failed" in out
    assert "human principal" in out


@pytest.fixture
def cli_hub(sync_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> SyncHub:
    monkeypatch.setattr(_common, "TRANSPORT", sync_hub.transport)
    monkeypatch.setenv("OPENHAL_TOKEN", sync_hub.tokens.human)
    return sync_hub
