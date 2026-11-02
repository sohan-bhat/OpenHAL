"""The typed phrase read from a real terminal, a pseudo-terminal standing in for the person's."""

from __future__ import annotations

import os
import sys

import pytest

from openhal.cli import _tty

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="pseudo-terminals are POSIX only")


def test_read_phrase_writes_the_prompt_and_reads_the_typed_line_from_the_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, terminal = os.openpty()
    try:
        monkeypatch.setattr(_tty, "TTY", os.ttyname(terminal))
        os.write(controller, b"confirm\n")
        assert _tty.read_phrase("Type confirm and press Enter to confirm these limits.\n\u203a ") == "confirm"
        shown = os.read(controller, 1024).decode()
        assert "Type confirm and press Enter to confirm these limits." in shown
        assert "\u203a " in shown
    finally:
        os.close(controller)
        os.close(terminal)


def test_the_phrase_prompt_says_what_typing_does_and_waits_on_its_own_line(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(_tty, "interactive", lambda: True)
    monkeypatch.setattr(_tty, "read_phrase", lambda prompt: seen.append(prompt) or "confirm")
    monkeypatch.setattr(_tty, "config", lambda: type("C", (), {"confirm": type("R", (), {"require_tty": True})()})())
    assert _tty.require_phrase("confirm", "confirm these limits as safe for this device") == "confirm"
    lines = seen[0].split("\n")
    assert lines[-2] == (
        "Type confirm and press Enter to confirm these limits as safe for this device. Anything else cancels."
    )
    assert lines[-1] == _tty.MARK
