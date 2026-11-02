"""A person at a real pseudo-terminal, for the commands that read answers from the terminal itself.

`Person` opens a pseudo-terminal and points openhal/cli/_tty.py at it. Each time the command writes
the prompt mark, the person types the next line, so the answers arrive the way they do at a real
terminal, one at a time, after each question.
"""

from __future__ import annotations

import os
import select
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from openhal.cli import _tty


class Person:
    def __init__(self, lines: list[str]) -> None:
        self.lines = list(lines)
        self.controller, self.terminal = os.openpty()
        self.shown = ""
        self.typed: list[str] = []
        self._done = threading.Event()
        self._thread = threading.Thread(target=self._watch, name="person-at-terminal", daemon=True)

    def _watch(self) -> None:
        answered = 0
        while not self._done.is_set():
            ready, _, _ = select.select([self.controller], [], [], 0.05)
            if ready:
                try:
                    chunk = os.read(self.controller, 4096)
                except OSError:
                    return
                self.shown += chunk.decode("utf-8", errors="replace")
            while answered < self.shown.count(_tty.MARK.strip()) and self.lines:
                line = self.lines.pop(0)
                self.typed.append(line)
                os.write(self.controller, line.encode("utf-8") + b"\n")
                answered += 1

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._done.set()
        self._thread.join(2)
        os.close(self.controller)
        os.close(self.terminal)


@contextmanager
def person_at_terminal(monkeypatch: pytest.MonkeyPatch, lines: list[str]) -> Iterator[Person]:
    """A pseudo-terminal the command reads from, with `lines` typed one per prompt."""
    person = Person(lines)
    monkeypatch.setattr(_tty, "TTY", os.ttyname(person.terminal))
    monkeypatch.setattr(_tty, "interactive", lambda: True)
    person.start()
    try:
        yield person
    finally:
        person.close()
