"""`openhal read`, `write`, `action`, `dry-run`, `stop` and `unlock`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
import yaml
from rich.markup import escape
from rich.table import Table

from openhal.cli import _tty
from openhal.cli._common import (
    EXIT_FAILED,
    console,
    exit_for,
    fail,
    handled,
    hub,
    parse_pairs,
    parse_quantity_text,
    print_decision,
    print_json,
    show,
    styled,
    typed,
)
from openhal.client import Client, split_target
from openhal.client.models import DeviceView


def _write_value(view: DeviceView, channel: str, words: list[str]) -> Any:
    """The typed words as the hub takes them. `60 %` becomes `{"value": 60, "unit": "%"}`."""
    text = " ".join(words).strip()
    if not text:
        raise ValueError("Give a value, with a unit for numbers, for example 60 % or 25 degC.")
    spec = view.write.get(channel)
    return typed(text, spec.type if spec is not None else None, channel)


def _shaped(client: Client, command: dict[str, Any]) -> dict[str, Any]:
    """A command from a plan file with typed numbers such as `60 %` split into number and unit."""
    view = client.device(str(command.get("device", "")))
    kind = command.get("kind") or ("action" if "action" in command else "write")
    if kind == "write":
        spec = view.write.get(str(command.get("channel", "")))
        value = command.get("value")
        if spec is not None and spec.type == "number" and isinstance(value, str):
            return {**command, "kind": "write", "value": parse_quantity_text(value, str(command["channel"]))}
        return {**command, "kind": "write"}
    args = dict(command.get("args") or {})
    specs = view.actions[str(command["action"])].args if command.get("action") in view.actions else {}
    for name, value in args.items():
        if str(specs.get(name, {}).get("type", "number")) == "number" and isinstance(value, str):
            args[name] = parse_quantity_text(value, name)
    return {**command, "kind": "action", "args": args}


def _command(client: Client, target: str, rest: list[str]) -> dict[str, Any]:
    """Build a write or an action from `device.name` and the remaining words."""
    device, name = split_target(target)
    view = client.device(device)
    if name in view.write:
        return {"kind": "write", "device": device, "channel": name, "value": _write_value(view, name, rest)}
    if name in view.actions:
        types = {arg: str(spec.get("type", "number")) for arg, spec in view.actions[name].args.items()}
        return {"kind": "action", "device": device, "action": name, "args": parse_pairs(rest, types)}
    known = sorted([*view.write, *view.actions])
    raise ValueError(f"{device} has no control channel or action {name!r}. It has {', '.join(known) or 'none'}.")


def register(app: typer.Typer) -> None:
    @app.command()
    @handled
    def read(
        targets: list[str] = typer.Argument(..., help="One or more device.channel, such as plant-waterer.tank."),  # noqa: B008
        as_json: bool = typer.Option(False, "--json", help="Print JSON."),
    ) -> None:
        """Read channels now."""
        with hub() as client:
            readings = client.read_many(targets) if len(targets) > 1 else [client.read(targets[0])]
        if as_json:
            print_json(readings)
            return
        for reading in readings:
            label = f"{reading.device}.{reading.channel}"
            if reading.ok:
                suspect = "  [yellow](suspect)[/yellow]" if reading.suspect else ""
                console.print(f"{escape(label)}  {escape(show(reading.value, reading.unit))}{suspect}")
            else:
                console.print(f"{escape(label)}  [red]failed[/red]  {escape(reading.error or '')}")
        if any(not reading.ok for reading in readings):
            raise typer.Exit(EXIT_FAILED)

    @app.command()
    @handled
    def write(
        target: str = typer.Argument(..., help="device.channel, for example led-strip.brightness."),
        value: list[str] = typer.Argument(..., help="The value with a unit, for example 60 % or 25 degC."),  # noqa: B008
        as_json: bool = typer.Option(False, "--json", help="Print the decision as JSON."),
    ) -> None:
        """Set a control channel. The hub's safety kernel decides."""
        device, channel = split_target(target)
        with hub() as client:
            view = client.device(device)
            decision = client.write(device, channel, _write_value(view, channel, value))
        print_json(decision) if as_json else print_decision(decision)
        exit_for(decision)

    @app.command()
    @handled
    def action(
        target: str = typer.Argument(..., help="device.action, for example printer.home."),
        args: list[str] = typer.Argument(None, help="Arguments as key=value, for example seconds=2s."),  # noqa: B008
        as_json: bool = typer.Option(False, "--json", help="Print the decision as JSON."),
    ) -> None:
        """Run a device action. The hub's safety kernel decides."""
        device, name = split_target(target)
        with hub() as client:
            view = client.device(device)
            if name not in view.actions:
                raise ValueError(f"{device} has no action {name!r}. It has {', '.join(view.actions) or 'none'}.")
            types = {arg: str(spec.get("type", "number")) for arg, spec in view.actions[name].args.items()}
            decision = client.action(device, name, parse_pairs(args or [], types))
        print_json(decision) if as_json else print_decision(decision)
        exit_for(decision)

    @app.command("dry-run")
    @handled
    def dry_run(
        target: str = typer.Argument(None, help="device.channel or device.action."),
        rest: list[str] = typer.Argument(None, help="The value, or key=value action arguments."),  # noqa: B008
        plan: Path = typer.Option(None, "--file", "-f", help="A YAML or JSON list of commands to check in order."),  # noqa: B008
        as_json: bool = typer.Option(False, "--json", help="Print the decisions as JSON."),
    ) -> None:
        """Check commands against the current state without running them. Nothing reaches a device."""
        with hub() as client:
            if plan is not None:
                loaded = yaml.safe_load(plan.read_text(encoding="utf-8"))
                if not isinstance(loaded, list) or not all(isinstance(item, dict) for item in loaded):
                    raise ValueError(f"{plan} must hold a list of commands.")
                commands = [_shaped(client, item) for item in loaded]
            elif target:
                commands = [_command(client, target, rest or [])]
            else:
                raise ValueError(
                    "Give a target such as plant-waterer.water duration=20s, or --file with a list of commands."
                )
            decisions = client.dry_run(commands)
        if as_json:
            print_json(decisions)
        else:
            for index, decision in enumerate(decisions):
                print_decision(decision, prefix=f"{index + 1}. " if len(decisions) > 1 else "")
        if any(decision.status in ("blocked", "failed") for decision in decisions):
            raise typer.Exit(EXIT_FAILED)

    @app.command()
    @handled
    def stop(
        reason: str = typer.Option("stop from the command line", "--reason", "-r", help="Recorded in the audit log."),
        as_json: bool = typer.Option(False, "--json", help="Print the report as JSON."),
    ) -> None:
        """Stop everything. Every device goes to its safe state and commands are refused until openhal unlock."""
        with hub() as client:
            report = client.stop(reason)
        if as_json:
            print_json(report)
        else:
            table = Table("device", "result", "detail", box=None, pad_edge=False)
            for item in report.devices:
                table.add_row(escape(item.device), styled(item.status), escape(item.detail))
            console.print(table)
            console.print(
                f"Stopped by {escape(report.by)}. {report.cancelled_requests} pending requests cancelled. "
                "Commands are refused until a person runs openhal unlock."
            )
        if any(item.status in ("failed", "partial") for item in report.devices):
            raise typer.Exit(EXIT_FAILED)

    @app.command()
    @handled
    def unlock(
        phrase: str = typer.Option(None, "--phrase", help="Only when confirm.require_tty is false."),
    ) -> None:
        """Lift the stop lock. Needs the human token and the typed phrase unlock."""
        with hub() as client:
            status = client.status()
            if not status.stopped:
                console.print("The hub is not stopped. Nothing to unlock.")
                return
            console.print(f"The hub is stopped ({escape(status.stop_reason or 'no reason given')}).")
            typed = _tty.require_phrase("unlock", "lift the stop lock", given=phrase)
            result = client.unlock(typed)
        if result.stopped:
            fail("The hub is still stopped.")
        console.print(
            "[green]unlocked[/green]  Commands are allowed again. Devices stay in their safe state until changed."
        )
