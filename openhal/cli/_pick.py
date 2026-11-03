"""Pickers and typed answers at the terminal, for a person who leaves out a device, a channel or an id.

A picker lists the real choices, moves with the arrow keys and filters the list as the person types
(ADR 0020). A picker shows only where `_tty.interactive()` holds, so a script, an agent's shell or
a command run with `--json` never gets one. The keys come from the terminal device behind standard
input, because kqueue on macOS returns an error for /dev/tty.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import typer

from openhal.cli import _tty
from openhal.cli._common import EXIT_FAILED, err

QMARK = "?"
PICK_HINT = "(arrow keys move, typing filters the list, Enter picks)"


@dataclass(frozen=True)
class Option:
    """One choice in a picker. The command gets `value`, and the person also reads `detail`."""

    value: str
    detail: str = ""


def available(as_json: bool = False) -> bool:
    """True when a picker can show, which takes an interactive terminal and no --json."""
    return not as_json and _tty.interactive()


def _style() -> Any:
    from questionary import Style

    return Style(
        [
            ("qmark", "noinherit bold"),
            ("question", "noinherit bold"),
            ("pointer", "noinherit bold"),
            ("highlighted", "noinherit bold"),
            ("answer", "noinherit bold"),
            ("instruction", "noinherit"),
            ("search_success", "noinherit"),
            ("search_none", "noinherit"),
        ]
    )


def device() -> str:
    """The terminal device behind standard input, such as /dev/ttys003.

    kqueue on macOS returns an error for /dev/tty, the alias for the controlling terminal, so the
    asyncio loop under prompt_toolkit can't register the alias, and the picker opens the device.
    """
    return os.ttyname(sys.stdin.fileno())


@contextmanager
def _terminal() -> Iterator[dict[str, Any]]:
    """The terminal as prompt_toolkit's input and output."""
    from prompt_toolkit.input import create_input
    from prompt_toolkit.output import create_output

    path = device()
    with open(path, encoding="utf-8") as typed, open(path, "w", encoding="utf-8") as shown:
        yield {"input": create_input(typed), "output": create_output(shown)}


def _answer(question: Any) -> Any:
    try:
        answer = question.unsafe_ask()
    except (KeyboardInterrupt, EOFError):
        answer = None
    if answer is None:
        err.print("[yellow]cancelled[/yellow]  Nothing was picked, so nothing changed.")
        raise typer.Exit(EXIT_FAILED)
    return answer


def choose(message: str, options: Sequence[Option]) -> str:
    """Show a picker of `options` and return the value the person picks. Control and C or D cancels."""
    import questionary

    width = max(len(option.value) for option in options)
    choices = [
        questionary.Choice(f"{option.value:<{width}}  {option.detail}".rstrip(), value=option.value)
        for option in options
    ]
    with _terminal() as streams:
        question = questionary.select(
            message,
            choices,
            qmark=QMARK,
            instruction=PICK_HINT,
            style=_style(),
            use_search_filter=True,
            use_jk_keys=False,
            **streams,
        )
        return str(_answer(question))


def ask(message: str, check: Callable[[str], str | None], *, default: str = "", hint: str = "") -> str:
    """A typed answer. `check` returns why an answer can't stand, and the person types again."""
    import questionary

    def validate(text: str) -> bool | str:
        return check(text.strip()) or True

    with _terminal() as streams:
        question = questionary.text(
            message,
            default=default,
            validate=validate,
            qmark=QMARK,
            instruction=hint or None,
            style=_style(),
            **streams,
        )
        return str(_answer(question)).strip()
