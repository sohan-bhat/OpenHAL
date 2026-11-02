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
        assert _tty.read_phrase("Type confirm to confirm these limits. ") == "confirm"
        shown = os.read(controller, 1024).decode()
        assert "Type confirm to confirm these limits. " in shown
    finally:
        os.close(controller)
        os.close(terminal)
