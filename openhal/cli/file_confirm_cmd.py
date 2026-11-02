"""`openhal file confirm`, a person confirming every limit in a device file (spec section 12).

A file that still has suggested limits gets the limits interview inline. Either way the command
writes a top-level `confirmed` with the person's name, today's date and the hash of the file's
limits, so any later change to a limit makes the file read-only again. The command needs an
interactive terminal and the typed phrase confirm, like every other human-only command, and then
asks a running OpenHAL to load the file, so no restart is needed.
"""

from __future__ import annotations

import datetime as dt
import getpass
import json
from pathlib import Path

import typer
import yaml
from rich.markup import escape

from openhal.cli import _interview, _live, _tty
from openhal.cli._common import console, fail


def _without_confirmed(text: str) -> list[str]:
    """Drop a top-level `confirmed:` entry, in flow or block form, keeping every other line."""
    kept: list[str] = []
    skipping = False
    for line in text.splitlines():
        if line.startswith("confirmed:"):
            skipping = True
            continue
        if skipping and (line.startswith((" ", "\t")) or not line.strip()):
            continue
        skipping = False
        kept.append(line)
    while kept and not kept[-1].strip():
        kept.pop()
    return kept


def confirm(
    path: Path = typer.Argument(..., exists=True, dir_okay=False, help="The device file to confirm."),  # noqa: B008
    by: str = typer.Option(None, "--by", help="Your name for the record. Defaults to your user name."),
    phrase: str = typer.Option(None, "--phrase", help="Only when confirm.require_tty is false."),
) -> None:
    """Answer each limit of a device file and confirm the limits. A running OpenHAL loads the file at once."""
    from openhal.spec.loader import DeviceFileError, load, parse_yaml

    try:
        device = load(path)
    except DeviceFileError as exc:
        fail(f"{path} is not valid. " + " ".join(exc.problems))
    who = (by or getpass.getuser() or "owner").strip()[:80]
    suggested = any(entry.suggested for entry in device.write.values()) or any(
        entry.suggested for entry in device.actions.values()
    )
    if suggested:
        require_tty = _interview.require_person(phrase)
        draft = parse_yaml(path.read_text(encoding="utf-8"))
        confirmed = _interview.confirm(draft, by=who, require_tty=require_tty, phrase=phrase)
        path.write_text(yaml.safe_dump(confirmed, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")
    else:
        _interview.summary(device)
        _tty.require_phrase(_interview.PHRASE, _interview.WHAT, given=phrase)
        line = (
            f"confirmed: {{ by: {json.dumps(who)}, at: {dt.date.today().isoformat()}, "
            f"sha256: {device.limits_sha256()} }}"
        )
        lines = _without_confirmed(path.read_text(encoding="utf-8"))
        path.write_text("\n".join([*lines, line]) + "\n", encoding="utf-8")
    again = load(path)
    remaining = again.unconfirmed()
    if remaining:
        fail(f"Still unconfirmed after saving {path}. {', '.join(remaining)}")
    loaded = _live.load(path, again.device_id)
    console.print(
        f"[green]confirmed[/green]  {escape(str(path))} by {escape(who)}. "
        f"{escape(_live.sentence(loaded, writable=again.writable))}"
    )
