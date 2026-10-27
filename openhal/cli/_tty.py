"""Typed confirmation phrases for the commands that need a person (ADR 0012).

With `confirm.require_tty: true` (the default), these commands need an interactive terminal and
read the phrase from the terminal itself, not from standard input. A program that runs shell
commands as the user, such as an agent, can't pipe the phrase in.
"""

from __future__ import annotations

import sys

import typer

from openhal.cli._common import EXIT_FAILED, config, err, fail


def interactive() -> bool:
    """True when standard input and output are a terminal and the process has a controlling terminal."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    try:
        with open("/dev/tty", "rb"):
            return True
    except OSError:
        return False


def read_phrase(prompt: str) -> str:
    """Read one line straight from the controlling terminal."""
    with open("/dev/tty", "r+", encoding="utf-8") as tty:
        tty.write(prompt)
        tty.flush()
        return tty.readline().strip()


def require_phrase(phrase: str, what: str, *, given: str | None = None) -> str:
    """Ask the person to type `phrase` before `what`. Returns the phrase they typed.

    `given` is a phrase passed on the command line. It is accepted only when
    `confirm.require_tty` is false.
    """
    require_tty = config().confirm.require_tty
    if require_tty:
        if given is not None:
            fail(f"--phrase can't be used while confirm.require_tty is true. Run this in a terminal and type {phrase}.")
        if not interactive():
            fail(
                f"To {what}, run this command yourself in an interactive terminal. confirm.require_tty is true, "
                "so the phrase can't come from a script or an agent."
            )
        typed = read_phrase(f"Type {phrase} to {what}. ")
    elif given is not None:
        typed = given
    else:
        typed = typer.prompt(f"Type {phrase} to {what}")
    if typed.strip().lower() != phrase:
        err.print(f"[red]cancelled[/red]  The phrase did not match {phrase}. Nothing was changed.")
        raise typer.Exit(EXIT_FAILED)
    return typed.strip().lower()
