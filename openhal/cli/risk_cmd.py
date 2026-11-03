"""`openhal risk`, showing and changing the risk level of each channel and action (ADR 0023).

Raising a level applies at once. Lowering a level gives an agent more, so in an interactive terminal
the command shows the change and takes the typed phrase confirm, as `openhal limits set` does to
widen a limit. Where no phrase can be typed, such as a script or an agent's shell, the change is held
as a pending change for a person to approve with openhal confirm approve.
"""

from __future__ import annotations

import re
from typing import Any

import typer
from rich.markup import escape
from rich.table import Table

from openhal.cli import _tty
from openhal.cli._common import console, handled, hub, print_json, styled
from openhal.cli.limits_cmd import _person_can_type

app = typer.Typer(help="Show and change risk levels. Raising applies at once, lowering needs a person.")

PHRASE = "confirm"
WHAT = "lower this risk level"
LEVELS = ("low", "medium", "high")


def _split(target: str, *, name_needed: bool) -> tuple[str, str | None]:
    device, dot, name = target.partition(".")
    if not device or (dot and not name) or (name_needed and not name):
        shape = "DEVICE.NAME" if name_needed else "DEVICE or DEVICE.NAME"
        raise ValueError(f"Give the target as {shape}, for example bench-board.brightness. Got {target!r}.")
    return device, name or None


def _post(body: dict[str, Any]) -> dict[str, Any]:
    from openhal.client.calls import Call

    with hub() as client:
        return client.call(Call("POST", "/v1/risk", dict, json=body))


def _order(pair: tuple[str, Any]) -> tuple[bool, list[Any]]:
    """Reads first, then names in natural order, so pin4 comes before pin12."""
    kind, _, name = pair[0].partition(":")
    parts = [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]
    return kind != "read", parts


@app.command("show")
@handled
def show_risk(
    target: str = typer.Argument(..., help="DEVICE, or DEVICE.NAME for one channel or action."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
    why: bool = typer.Option(False, "--why", help="Show the reasons behind each level."),
) -> None:
    """Show each channel's and action's risk level, and what is read-only."""
    device, name = _split(target, name_needed=False)
    with hub() as client:
        data = client.risk(device)
    targets = data.targets
    if name is not None:
        targets = {key: value for key, value in targets.items() if key.partition(":")[2] == name}
        if not targets:
            raise ValueError(f"{device} has no channel or action {name!r}.")
    if as_json:
        print_json({**data.model_dump(), "targets": {key: value.model_dump() for key, value in targets.items()}})
        return
    table = Table("name", "kind", "risk", "set by", "state", box=None, pad_edge=False)
    for key, item in sorted(targets.items(), key=_order):
        kind, _, shown = key.partition(":")
        by = item.override_by if item.override_applied and item.override_by else "table"
        state = "read-only" if item.read_only else ("reads only" if kind == "read" else "takes commands")
        table.add_row(escape(shown), kind, item.level, escape(by), state)
        if why:
            table.add_row("", "", "", "", escape("; ".join(item.reasons)), style="dim")
    console.print(table)
    for pending in data.pending:
        command = pending.get("command") or {}
        console.print(
            f"pending {escape(str(pending.get('id')))}  {escape(str(command.get('name')))} "
            f"{escape(str(command.get('before')))} to {escape(str(command.get('after')))}"
        )


@app.command("set")
@handled
def set_risk(
    target: str = typer.Argument(..., help="DEVICE.NAME, a write channel or an action."),
    level: str = typer.Argument(..., help="low, medium or high."),
    phrase: str = typer.Option(None, "--phrase", help="Only when confirm.require_tty is false."),
) -> None:
    """Change a level. Raising applies at once, and lowering takes a person's typed phrase or approval."""
    device, name = _split(target, name_needed=True)
    if level not in LEVELS:
        raise ValueError(f"A risk level is low, medium or high, not {level!r}.")
    body: dict[str, Any] = {"device": device, "name": name, "level": level}
    planned = _post({**body, "dry_run": True})
    if planned.get("status") == "blocked":
        console.print(
            f"{styled('blocked')} [dim]{escape(str(planned.get('code')))}[/dim]  {escape(planned['message'])}"
        )
        raise typer.Exit(1)
    console.print(f"[bold]{escape(device)}.{escape(str(name))}[/bold]  {planned['before']} to {planned['after']}")
    if planned.get("lowers"):
        with hub() as client:
            human = client.whoami().kind == "human"
        if human and _person_can_type(phrase):
            body["phrase"] = _tty.require_phrase(PHRASE, WHAT, given=phrase)
    result = _post(body)
    status = str(result.get("status"))
    code = f" [dim]{escape(str(result['code']))}[/dim]" if result.get("code") else ""
    console.print(f"{styled(status)}{code}  {escape(str(result.get('message', '')))}")
    if status == "blocked":
        raise typer.Exit(1)
