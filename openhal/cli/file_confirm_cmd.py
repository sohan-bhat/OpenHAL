"""`openhal file confirm`, a person confirming every limit in a device file (spec section 12).

The command writes a top-level `confirmed` with the person's name, today's date and the hash of the
file's limits, so any later change to a limit makes the file read-only again. The command needs an
interactive terminal and the typed phrase confirm, like every other human-only command.
"""

from __future__ import annotations

import datetime as dt
import getpass
import json
from pathlib import Path

import typer
from rich.markup import escape

from openhal.cli import _tty
from openhal.cli._common import console, fail, show


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
    """Confirm every limit in a device file after reading the file. The hub then loads the file writable."""
    from openhal.spec.loader import DeviceFileError, load

    try:
        device = load(path)
    except DeviceFileError as exc:
        fail(f"{path} is not valid. " + " ".join(exc.problems))
    suggested = [
        f"{kind}.{name}"
        for kind, entries in (("write", device.write), ("actions", device.actions))
        for name, entry in entries.items()
        if entry.suggested
    ]
    if suggested:
        fail(
            f"{', '.join(suggested)} are still marked suggested. Answer the limits interview, or edit each one "
            "and remove suggested: true once you have checked it."
        )
    console.print(
        f"[bold]{escape(device.device.name)}[/bold]  {escape(device.device_id)}, {device.effective_hazard} hazard"
    )
    for name, spec in device.write.items():
        limits = f"{show(spec.min, spec.unit)} to {show(spec.max, spec.unit)}" if spec.unit else ""
        limits = limits or ", ".join(spec.values or []) or spec.type
        rate = f", at most {show(spec.max_change_per_s, spec.unit)}/s" if spec.max_change_per_s else ""
        console.print(f"control {escape(name)}  {escape(limits)}{escape(rate)}")
    for name in device.actions:
        console.print(f"action  {escape(name)}")
    for interlock in device.interlocks:
        console.print(f"interlock  if {escape(interlock.if_ or 'always')} require {escape(interlock.require)}")
    for step in device.safe_state:
        console.print(f"safe state  {escape(str(step.model_dump(exclude_none=True)))}")
    _tty.require_phrase("confirm", "confirm these limits as safe for this device", given=phrase)
    who = (by or getpass.getuser() or "owner").strip()[:80]
    line = (
        f"confirmed: {{ by: {json.dumps(who)}, at: {dt.date.today().isoformat()}, sha256: {device.limits_sha256()} }}"
    )
    lines = _without_confirmed(path.read_text(encoding="utf-8"))
    path.write_text("\n".join([*lines, line]) + "\n", encoding="utf-8")
    again = load(path)
    remaining = again.unconfirmed()
    if remaining:
        fail(f"Still unconfirmed after saving {path}. {', '.join(remaining)}")
    console.print(f"[green]confirmed[/green]  {escape(str(path))} by {escape(who)}. Restart openhald to load the file.")
