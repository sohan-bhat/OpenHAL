"""`openhal risk`, showing and changing the risk level of each channel and action (ADR 0023).

A bare `openhal risk` shows how many channels and actions of each device sit at each level and one
command to copy. Raising a level applies at once. Lowering a level gives an agent more, so in an
interactive terminal the command shows the change and takes the typed phrase confirm, as
`openhal limits set` does to widen a limit. Where no phrase can be typed, such as a script or an
agent's shell, the change is held as a pending change for a person to approve with openhal confirm
approve. At a terminal a left-out device, name or level opens a picker, and anywhere else the error
lists the valid values and one command to copy (ADR 0020).
"""

from __future__ import annotations

import difflib
import re
from typing import TYPE_CHECKING, Any

import typer
from rich.markup import escape
from rich.table import Table

from openhal.cli import _choices, _tty
from openhal.cli._choices import NO_DEVICES, Need
from openhal.cli._common import console, handled, hub, print_json, styled
from openhal.cli._pick import Option
from openhal.cli.limits_cmd import _person_can_type

if TYPE_CHECKING:
    from openhal.client.models import DeviceRisk, RiskLevel

app = typer.Typer(help="Show and change risk levels. Raising applies at once, lowering needs a person.")

PHRASE = "confirm"
WHAT = "lower this risk level"
LEVELS = ("low", "medium", "high")


def _order(pair: tuple[str, Any]) -> tuple[bool, list[Any]]:
    """Reads first, then names in natural order, so pin4 comes before pin12."""
    kind, _, name = pair[0].partition(":")
    parts = [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]
    return kind != "read", parts


def _split(target: str) -> tuple[str, str | None]:
    device, dot, name = target.partition(".")
    if not device or (dot and not name):
        raise ValueError(
            f"Give the target as DEVICE or DEVICE.NAME, for example bench-board.brightness. Got {target!r}."
        )
    return device, name or None


def _risk(device: str) -> DeviceRisk:
    with hub() as client:
        return client.risk(device)


def _counts(data: DeviceRisk) -> str:
    found = [item.level for key, item in data.targets.items() if not key.startswith("read:")]
    shown = ", ".join(f"{found.count(level)} {level}" for level in LEVELS if level in found)
    waiting = sum(1 for item in data.targets.values() if item.read_only)
    return f"{shown or 'nothing to control'}{f', {waiting} read-only' if waiting else ''}"


def _settable(data: DeviceRisk) -> dict[str, RiskLevel]:
    """Write channels and actions by name, the targets whose level can change."""
    ordered = sorted(data.targets.items(), key=_order)
    return {key.partition(":")[2]: item for key, item in ordered if not key.startswith("read:")}


def _example(device: str, data: DeviceRisk | None = None) -> str:
    """A level change to copy, raising the first target that isn't high already."""
    for name, item in _settable(data).items() if data is not None else []:
        if item.level != "high":
            return f"openhal risk set {device}.{name} high"
    return f"openhal risk set {device}.NAME high"


def _by(item: RiskLevel) -> str:
    return item.override_by if item.override_applied and item.override_by else "table"


@app.callback(invoke_without_command=True)
@handled
def overview(ctx: typer.Context, as_json: bool = typer.Option(False, "--json", help="Print JSON.")) -> None:
    """How many channels and actions of each device sit at each level, and one command to copy."""
    if ctx.invoked_subcommand is not None:
        return
    with hub() as client:
        every = [client.risk(item.id) for item in client.devices()]
    if as_json:
        print_json([data.model_dump() for data in every])
        return
    if not every:
        console.print(NO_DEVICES)
        return
    table = Table("device", "hazard", "levels", box=None, pad_edge=False)
    for data in every:
        table.add_row(escape(data.device), data.hazard, escape(_counts(data)))
    console.print(table)
    first = every[0]
    console.print(
        f"See why with openhal risk show {escape(first.device)} --why, "
        f"or change one with {escape(_example(first.device, first))}"
    )


def _devices() -> list[Option]:
    with hub() as client:
        return [Option(item.id, _counts(client.risk(item.id))) for item in client.devices()]


def _device(command: str, as_json: bool = False) -> str:
    spec = Need(
        command,
        "a device",
        "devices",
        placeholder="DEVICE",
        example=(lambda device: f"{command} {device}") if command.endswith("show") else _example,
        empty=NO_DEVICES,
        every="openhal devices",
    )
    return _choices.need(spec, _devices, as_json=as_json)


def _name(device: str, data: DeviceRisk, name: str | None) -> str:
    """The write channel or action the person named or picks."""
    targets = _settable(data)
    if name is not None and name in targets:
        return name
    if name is not None:
        if f"read:{name}" in data.targets:
            raise ValueError(f"Reading {name} is always low, so its level never changes.")
        near = difflib.get_close_matches(name, list(targets), n=3)
        hint = f" Did you mean {_choices.joined(near, 'or')}?" if near else ""
        raise ValueError(f"{device} has no write channel or action {name!r}.{hint}")
    spec = Need(
        "openhal risk set",
        f"a channel or action of {device}",
        "names",
        placeholder="NAME",
        example=lambda picked: f"openhal risk set {device}.{picked} high",
        empty=f"{device} has no write channel or action.",
    )
    return _choices.need(
        spec, lambda: [Option(key, f"{item.level}, set by {_by(item)}") for key, item in targets.items()]
    )


def _level(device: str, name: str, now: str) -> str:
    def detail(level: str) -> str:
        if level == now:
            return "now"
        return "lowers, needs a person" if LEVELS.index(level) < LEVELS.index(now) else "raises at once"

    spec = Need(
        "openhal risk set",
        f"a level for {device}.{name}",
        "levels",
        placeholder="LEVEL",
        example=lambda level: f"openhal risk set {device}.{name} {level}",
    )
    return _choices.need(spec, lambda: [Option(level, detail(level)) for level in LEVELS if level != now])


@app.command("show")
@handled
def show_risk(
    target: str = typer.Argument(
        None, help="DEVICE, or DEVICE.NAME for one channel or action. A terminal shows a picker."
    ),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
    why: bool = typer.Option(False, "--why", help="Show the reasons behind each level."),
) -> None:
    """Show each channel's and action's risk level, and what is read-only."""
    device, name = _split(target or _device("openhal risk show", as_json))
    data = _risk(device)
    targets = data.targets
    if name is not None:
        targets = {key: value for key, value in targets.items() if key.partition(":")[2] == name}
        if not targets:
            near = difflib.get_close_matches(name, [key.partition(":")[2] for key in data.targets], n=3)
            hint = f" Did you mean {_choices.joined(near, 'or')}?" if near else ""
            raise ValueError(f"{device} has no channel or action {name!r}.{hint}")
    if as_json:
        print_json({**data.model_dump(), "targets": {key: value.model_dump() for key, value in targets.items()}})
        return
    table = Table("name", "kind", "risk", "set by", "state", box=None, pad_edge=False)
    for key, item in sorted(targets.items(), key=_order):
        kind, _, shown = key.partition(":")
        state = "read-only" if item.read_only else ("reads only" if kind == "read" else "takes commands")
        table.add_row(escape(shown), kind, item.level, escape(_by(item)), state)
        if why:
            table.add_row("", "", "", "", escape("; ".join(item.reasons)), style="dim")
    console.print(table)
    for pending in data.pending:
        command = pending.get("command") or {}
        console.print(
            f"pending {escape(str(pending.get('id')))}  {escape(str(command.get('name')))} "
            f"{escape(str(command.get('before')))} to {escape(str(command.get('after')))}"
        )


def _post(body: dict[str, Any]) -> dict[str, Any]:
    from openhal.client.calls import Call

    with hub() as client:
        return client.call(Call("POST", "/v1/risk", dict, json=body))


@app.command("set")
@handled
def set_risk(
    target: str = typer.Argument(None, help="DEVICE.NAME, a write channel or an action. A terminal shows a picker."),
    level: str = typer.Argument(None, help="low, medium or high. A terminal shows a picker."),
    phrase: str = typer.Option(None, "--phrase", help="Only when confirm.require_tty is false."),
) -> None:
    """Change a level. Raising applies at once, and lowering takes a person's typed phrase or approval."""
    walked = target is None or "." not in target or level is None
    device, name = _split(target or _device("openhal risk set"))
    data = _risk(device)
    name = _name(device, data, name)
    if level is not None and level not in LEVELS:
        raise ValueError(f"A risk level is low, medium or high, not {level!r}.")
    level = level or _level(device, name, _settable(data)[name].level)
    body: dict[str, Any] = {"device": device, "name": name, "level": level}
    planned = _post({**body, "dry_run": True})
    if planned.get("status") == "blocked":
        console.print(
            f"{styled('blocked')} [dim]{escape(str(planned.get('code')))}[/dim]  {escape(planned['message'])}"
        )
        raise typer.Exit(1)
    console.print(f"[bold]{escape(device)}.{escape(name)}[/bold]  {planned['before']} to {planned['after']}")
    if planned.get("lowers"):
        with hub() as client:
            human = client.whoami().kind == "human"
        if human and _person_can_type(phrase):
            body["phrase"] = _tty.require_phrase(PHRASE, WHAT, given=phrase)
    result = _post(body)
    status = str(result.get("status"))
    code = f" [dim]{escape(str(result['code']))}[/dim]" if result.get("code") else ""
    console.print(f"{styled(status)}{code}  {escape(str(result.get('message', '')))}")
    if walked:
        console.print(f"The same change in one line is openhal risk set {escape(device)}.{escape(name)} {level}")
    if status == "blocked":
        raise typer.Exit(1)
