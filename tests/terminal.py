"""A person at a real pseudo-terminal, for the commands that read answers from the terminal itself.

`Person` opens a pseudo-terminal and points openhal/cli/_tty.py at it. Each time the command writes
the prompt mark, the person types the next line, so the answers arrive the way they do at a real
terminal, one at a time, after each question. A `Keys` step waits for its text to show, such as a
picker's question, and then presses its keys, such as arrow keys, letters to filter and Enter. The
person also answers the cursor position requests prompt_toolkit sends, as a real terminal does.

A command can wait at a prompt that no step answers, for example when a test expects other text.
When the screen stays still for `IDLE_S` while the command runs, the person presses Control and C at
a picker or a typed answer and Enter at a typed phrase, and the test fails with the screen and the
steps left instead of hanging.
"""

from __future__ import annotations

import fcntl
import os
import re
import select
import struct
import termios
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import pytest

from openhal.cli import _pick, _tty

UP = "\x1b[A"
DOWN = "\x1b[B"
ENTER = "\r"
CONTROL_C = "\x03"
CLEAR = "\x15"
"""Control and U, which empties a typed answer in prompt_toolkit."""
CURSOR_REQUEST = "\x1b[6n"
CURSOR_REPLY = b"\x1b[1;1R"
ESCAPES = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][A-Z0-9]|\x1b[=>]")
ROWS, COLUMNS = 40, 160
IDLE_S = 30.0
"""How long the screen may stay still while the command runs before the person gives up."""


@dataclass(frozen=True)
class Keys:
    """Press `send` once `after` shows on the screen."""

    after: str
    send: str


Step = str | Keys


class Person:
    def __init__(self, steps: list[Step], idle_s: float = IDLE_S) -> None:
        self.steps = [step if isinstance(step, Keys) else Keys(_tty.MARK.strip(), step + "\n") for step in steps]
        self.idle_s = idle_s
        self.controller, self.terminal = os.openpty()
        fcntl.ioctl(self.terminal, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLUMNS, 0, 0))
        self.shown = ""
        self.typed: list[str] = []
        self.pressed: list[Keys] = []
        self.stuck = False
        self._done = threading.Event()
        self._thread = threading.Thread(target=self._watch, name="person-at-terminal", daemon=True)

    @property
    def text(self) -> str:
        """What the terminal showed, without escape codes."""
        return ESCAPES.sub("", self.shown)

    def _watch(self) -> None:
        position = 0
        replied = 0
        still_since = time.monotonic()
        while not self._done.is_set():
            ready, _, _ = select.select([self.controller], [], [], 0.05)
            if ready:
                try:
                    chunk = os.read(self.controller, 4096)
                except OSError:
                    return
                self.shown += chunk.decode("utf-8", errors="replace")
                still_since = time.monotonic()
            while replied < self.shown.count(CURSOR_REQUEST):
                os.write(self.controller, CURSOR_REPLY)
                replied += 1
            while self.steps:
                found = self.shown.find(self.steps[0].after, position)
                if found < 0:
                    break
                step = self.steps.pop(0)
                position = found + len(step.after)
                os.write(self.controller, step.send.encode("utf-8"))
                self.pressed.append(step)
                still_since = time.monotonic()
                if step.after == _tty.MARK.strip():
                    self.typed.append(step.send.removesuffix("\n"))
            if time.monotonic() - still_since > self.idle_s:
                self.stuck = True
                os.write(self.controller, self._give_up())
                still_since = time.monotonic()

    def _give_up(self) -> bytes:
        """Control and C for a prompt_toolkit prompt in raw mode, Enter for a line read in canonical mode.

        Control and C in canonical mode would raise SIGINT, so a line read gets Enter alone.
        """
        canonical = termios.tcgetattr(self.terminal)[3] & termios.ICANON
        return b"\n" if canonical else CONTROL_C.encode()

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._done.set()
        self._thread.join(2)
        os.close(self.controller)
        os.close(self.terminal)

    def report(self) -> str:
        left = [step.after for step in self.steps]
        return (
            f"The command waited at the terminal for {self.idle_s:g} s. Steps left {left}. Screen\n{self.text[-3000:]}"
        )


@contextmanager
def person_at_terminal(
    monkeypatch: pytest.MonkeyPatch, steps: list[Step], *, idle_s: float = IDLE_S
) -> Iterator[Person]:
    """A pseudo-terminal the command reads from. A line is typed at each prompt mark, and `Keys` press keys.

    The terminal stands in only inside the block, so a command run after the block has no terminal.
    """
    person = Person(steps, idle_s)
    with monkeypatch.context() as patch:
        patch.setattr(_tty, "TTY", os.ttyname(person.terminal))
        patch.setattr(_pick, "device", lambda: os.ttyname(person.terminal))
        patch.setattr(_tty, "interactive", lambda: True)
        person.start()
        try:
            yield person
        except BaseException as exc:
            if person.stuck:
                exc.add_note(person.report())
            raise
        finally:
            person.close()
    if person.stuck:
        pytest.fail(person.report())
