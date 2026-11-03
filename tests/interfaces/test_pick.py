"""The picker and the typed answer, driven through a real pseudo-terminal with arrow keys and typing."""

from __future__ import annotations

import os
import sys

import pytest
import typer

from openhal.cli import _pick, _tty
from tests.terminal import CONTROL_C, DOWN, ENTER, Keys, person_at_terminal

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="pseudo-terminals are POSIX only")

LAMPS = [_pick.Option("desk-lamp", "Desk lamp, connected"), _pick.Option("plant-waterer", "Plant waterer")]


def test_arrow_keys_move_and_enter_picks(monkeypatch: pytest.MonkeyPatch) -> None:
    with person_at_terminal(monkeypatch, [Keys("Pick a device", DOWN + ENTER)]) as person:
        assert _pick.choose("Pick a device", LAMPS) == "plant-waterer"
    assert "desk-lamp      Desk lamp, connected" in person.text
    assert _pick.PICK_HINT in person.text


def test_typing_filters_the_list(monkeypatch: pytest.MonkeyPatch) -> None:
    with person_at_terminal(monkeypatch, [Keys("Pick a device", "plant" + ENTER)]):
        assert _pick.choose("Pick a device", LAMPS) == "plant-waterer"


def test_control_c_cancels_with_nothing_picked(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with person_at_terminal(monkeypatch, [Keys("Pick a device", CONTROL_C)]), pytest.raises(typer.Exit) as stopped:
        _pick.choose("Pick a device", LAMPS)
    assert stopped.value.exit_code == 1
    assert "Nothing was picked, so nothing changed." in capsys.readouterr().err


def test_a_typed_answer_is_checked_until_the_answer_stands(monkeypatch: pytest.MonkeyPatch) -> None:
    def check(text: str) -> str | None:
        return None if text.endswith("%") else "Add the unit, for example 60 %."

    steps = [Keys("New max", "60" + ENTER), Keys("Add the unit", " %" + ENTER)]
    with person_at_terminal(monkeypatch, steps) as person:
        assert _pick.ask("New max", check, hint="with its unit") == "60 %"
    assert "with its unit" in person.text


def test_enter_keeps_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    with person_at_terminal(monkeypatch, [Keys("New max", ENTER)]):
        assert _pick.ask("New max", lambda text: None, default="80 %") == "80 %"


def test_a_prompt_that_no_step_answers_fails_instead_of_hanging(monkeypatch: pytest.MonkeyPatch) -> None:
    with (
        pytest.raises(pytest.fail.Exception, match="waited at the terminal for 1 s"),
        person_at_terminal(monkeypatch, [Keys("Another question", ENTER)], idle_s=1),
        pytest.raises(typer.Exit),
    ):
        _pick.choose("Pick a device", LAMPS)
    with (
        pytest.raises(AssertionError) as failed,
        person_at_terminal(monkeypatch, [], idle_s=1),
    ):
        assert _tty.read_phrase("Type approve\n" + _tty.MARK) == "approve"
    assert "Steps left []" in str(failed.value.__notes__)


def test_the_picker_opens_the_device_behind_standard_input(monkeypatch: pytest.MonkeyPatch) -> None:
    controller, terminal = os.openpty()
    try:
        monkeypatch.setattr(sys, "stdin", type("Input", (), {"fileno": lambda self: terminal})())
        assert _pick.device() == os.ttyname(terminal)
    finally:
        os.close(controller)
        os.close(terminal)


def test_no_picker_without_a_terminal_or_with_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_tty, "interactive", lambda: False)
    assert not _pick.available()
    monkeypatch.setattr(_tty, "interactive", lambda: True)
    assert _pick.available()
    assert not _pick.available(as_json=True)
