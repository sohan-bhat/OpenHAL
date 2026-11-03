"""What a command does when a person leaves out an argument, and the nearest ids to a mistyped one.

`need` shows a picker of the real values at an interactive terminal (ADR 0020). Without a terminal,
or with `--json`, `need` prints an error that names what is missing, lists the valid values and
shows one exact command to copy, and exits 2, the usage error code. A person-only step gets a
picker only with the human token. `closest` adds the nearest real ids to the hub's message about
an id that doesn't exist.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, NoReturn

import typer
from rich.markup import escape

from openhal._brand import PRODUCT_NAME, START_COMMAND
from openhal.cli import _pick
from openhal.cli._common import EXIT_USAGE, err, hub
from openhal.cli._pick import Option

if TYPE_CHECKING:
    from openhal.client import Client

LISTED = 10
"""The most values an error lists before it names the command that lists every one."""

NO_DEVICES = "The hub has no devices yet. Browse starter device files with openhal library, or run openhal discover."
NOT_FOUND = re.compile(r"There is no (device|routine|request|run|active token) '?([^'\s]+?)'?\.")


@dataclass(frozen=True)
class Need:
    """What `command` needs, such as a device, and how to show the valid values in an error."""

    command: str
    what: str
    label: str
    placeholder: str = "ID"
    example: Callable[[str], str] | None = None
    empty: str = ""
    every: str = ""
    person: bool = False

    def run(self, value: str) -> str:
        return self.example(value) if self.example else f"{self.command} {value}"


def joined(words: Sequence[str], last: str = "and") -> str:
    """Words as a sentence list, such as `a, b and c`."""
    if len(words) <= 1:
        return "".join(words)
    return f"{', '.join(words[:-1])} {last} {words[-1]}"


def _gather(options: Callable[[], list[Option]]) -> tuple[list[Option], str]:
    from openhal.client import HubNotRunning, OpenHALError

    try:
        return options(), ""
    except HubNotRunning:
        return [], f"{PRODUCT_NAME} is not running, so no list can be shown. Start {PRODUCT_NAME} with {START_COMMAND}."
    except OpenHALError as exc:
        return [], str(exc)


def _not_human(spec: Need) -> str:
    """Why a person-only step shows no picker with this token, or an empty string for the human token.

    With no hub running, the only values to pick from are the owner's own files, such as the tokens
    in the hub database that only the config folder's owner can open, so no token is in play.
    """
    from openhal.client import HubNotRunning, OpenHALError

    try:
        with hub() as client:
            you = client.whoami()
    except HubNotRunning:
        return ""
    except OpenHALError as exc:
        return str(exc)
    if you.kind == "human":
        return ""
    return f"{spec.command} takes the human token, and this token is {you.kind}:{you.name}."


def need(spec: Need, options: Callable[[], list[Option]], *, as_json: bool = False) -> str:
    """The value the person picks at a terminal. Anywhere else, the error that lists the valid values."""
    found, note = _gather(options)
    if found and _pick.available(as_json):
        note = _not_human(spec) if spec.person else ""
        if not note:
            return _pick.choose(f"Pick {spec.what}", found)
    missing(spec, [option.value for option in found], note)


def missing(spec: Need, values: Sequence[str], note: str = "") -> NoReturn:
    """Name what `spec.command` needs, list up to LISTED valid values and show one command to copy."""
    sentence = f"{spec.command} needs {spec.what}."
    if note:
        sentence = f"{sentence} {note}"
    elif not values and spec.empty:
        sentence = f"{sentence} {spec.empty}"
    err.print(f"[red]error[/red]  {escape(sentence)}")
    rows: list[tuple[str, str]] = []
    if values:
        shown = ", ".join(values[:LISTED])
        if len(values) > LISTED:
            more = f", and {len(values) - LISTED} more"
            shown += f"{more}. {spec.every} lists every one" if spec.every else more
        rows.append((spec.label, shown))
    rows.append(("run", spec.run(values[0] if values else spec.placeholder)))
    width = max(len(label) for label, _ in rows)
    for label, text in rows:
        err.print(f"  {label:<{width}}  {escape(text)}")
    raise typer.Exit(EXIT_USAGE)


def _known(client: Client, kind: str) -> list[str]:
    if kind == "device":
        return [item.id for item in client.devices()]
    if kind == "routine":
        return [item.id for item in client.routines()]
    if kind == "request":
        return [item.id for item in client.confirmations(include_done=True)]
    if kind == "run":
        return [item.run_id for item in client.runs()]
    return [item.token_id for item in client.tokens() if not item.revoked]


def closest(message: str) -> str:
    """The hub's message about an id that doesn't exist, with the nearest real ids added."""
    from openhal.client import OpenHALError

    match = NOT_FOUND.search(message)
    if match is None:
        return message
    kind, wanted = match.groups()
    try:
        with hub() as client:
            known = _known(client, kind)
    except OpenHALError:
        return message
    near = difflib.get_close_matches(wanted, known, n=3)
    if near:
        return f"{message} Did you mean {joined(near, 'or')}?"
    if known:
        return f"{message} The hub has {joined(known[:LISTED])}."
    return message
