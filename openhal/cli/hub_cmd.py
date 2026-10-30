"""`openhal status`, `devices` and `discover`."""

from __future__ import annotations

import typer
from rich.markup import escape
from rich.table import Table

from openhal.cli import library_cmd
from openhal.cli._common import console, handled, hub, print_json, show, when
from openhal.client.models import DeviceView
from openhal.protocol.version import label


def _limits(spec_min: float | None, spec_max: float | None, unit: str | None) -> str:
    if spec_min is None and spec_max is None:
        return ""
    low = show(spec_min, unit) if spec_min is not None else ""
    high = show(spec_max, unit) if spec_max is not None else ""
    return f"{low} to {high}"


def _print_device(view: DeviceView) -> None:
    mode = "writable" if view.writable else "read-only"
    state = "connected" if view.connected else "not connected"
    console.print(f"[bold]{escape(view.name)}[/bold]  {escape(view.id)}")
    console.print(f"driver {escape(view.driver)}, {escape(view.hazard)} hazard, {mode}, {state}")
    if view.unavailable:
        console.print(f"[yellow]unavailable[/yellow]  {escape(view.unavailable)}")
    if view.last_error:
        console.print(f"[red]last error[/red]  {escape(view.last_error)}")
    if view.unconfirmed:
        console.print(f"[yellow]unconfirmed limits[/yellow]  {escape(', '.join(view.unconfirmed))}")
    if view.read:
        table = Table("read", "value", "unit", "every", box=None, pad_edge=False, title_justify="left")
        for name, spec in view.read.items():
            table.add_row(
                escape(name), escape(show(spec.value)), escape(spec.unit or spec.type), show(spec.every_s, "s")
            )
        console.print(table)
    if view.write:
        table = Table("write", "value", "limits", "max change", "confirm", box=None, pad_edge=False)
        for name, write_spec in view.write.items():
            limits = _limits(write_spec.min, write_spec.max, write_spec.unit)
            if write_spec.values:
                limits = " | ".join(write_spec.values)
            rate = f"{show(write_spec.max_change_per_s, write_spec.unit)}/s" if write_spec.max_change_per_s else ""
            table.add_row(
                escape(name),
                escape(show(write_spec.value, write_spec.unit) if write_spec.known else "unknown"),
                escape(limits or write_spec.type),
                escape(rate),
                escape(write_spec.confirm or ""),
            )
        console.print(table)
    if view.actions:
        table = Table("action", "arguments", "confirm", box=None, pad_edge=False)
        for name, action in view.actions.items():
            args = ", ".join(f"{arg} ({spec.get('unit') or spec.get('type', '')})" for arg, spec in action.args.items())
            table.add_row(escape(name), escape(args), escape(action.confirm or ""))
        console.print(table)
    for interlock in view.interlocks:
        condition = f"if {interlock.if_} " if interlock.if_ else ""
        console.print(f"interlock  {escape(condition)}require {escape(interlock.require)}")
    if view.notes:
        console.print("notes, as the device file states them", style="dim")
        console.print(escape(view.notes), style="dim")


def register(app: typer.Typer) -> None:
    @app.command()
    @handled
    def status(as_json: bool = typer.Option(False, "--json", help="Print JSON.")) -> None:
        """Show whether the hub runs, who you are, devices, stop state and pending confirmations."""
        with hub() as client:
            result = client.status()
            url = client.url
        if as_json:
            print_json(result)
            return
        spec = label(result.protocol_version or result.spec)
        console.print(f"{escape(result.product)} hub {escape(result.version)} at {escape(url)}, spec {escape(spec)}")
        console.print(f"you are {escape(result.you.kind)}:{escape(result.you.name)} ({escape(result.you.scope)})")
        console.print(f"devices {result.connected} of {result.devices} connected")
        console.print(f"pending confirmations {result.pending_confirmations}")
        if result.started_at:
            console.print(f"started {when(result.started_at)}")
        if result.stopped:
            console.print(
                f"[red]stopped[/red]  {escape(result.stop_reason or '')}. Commands are blocked until openhal unlock."
            )
        for problem in result.load_problems:
            console.print(f"[yellow]not loaded[/yellow]  {escape(problem.path)}")
            for line in problem.problems:
                console.print(f"  {escape(line)}")

    @app.command()
    @handled
    def devices(
        device: str = typer.Argument(None, help="Show one device in detail."),
        as_json: bool = typer.Option(False, "--json", help="Print JSON."),
    ) -> None:
        """List devices, or describe one with its channels, limits and actions."""
        with hub() as client:
            if device:
                view = client.device(device)
                print_json(view) if as_json else _print_device(view)
                return
            found = client.devices()
        if as_json:
            print_json(found)
            return
        if not found:
            console.print("No devices. Put device files in the devices folder, or run openhal discover.")
            return
        table = Table("id", "name", "driver", "hazard", "mode", "state", box=None, pad_edge=False)
        for item in found:
            state = "[green]connected[/green]" if item.connected else "[red]not connected[/red]"
            mode = "writable" if item.writable else "[yellow]read-only[/yellow]"
            table.add_row(escape(item.id), escape(item.name), escape(item.driver), escape(item.hazard), mode, state)
        console.print(table)

    @app.command()
    @handled
    def discover(
        drivers: list[str] = typer.Option(None, "--driver", "-d", help="Only probe with this driver. Repeat for more."),  # noqa: B008
        as_json: bool = typer.Option(False, "--json", help="Print JSON."),
    ) -> None:
        """Search for devices. Probing sends only read-only identify commands."""
        with hub() as client:
            result = client.discover(drivers or None)
        if as_json:
            print_json(result)
            return
        for match in result.matched:
            known = f"as {match.device_id}" if match.device_id else "with no device file yet"
            console.print(f"[green]matched[/green]  {escape(match.label or match.address)} {escape(known)}")
            if match.library_file:
                name = library_cmd.name_for(match.library_file)
                console.print(
                    f"  The library has {escape(name)}, and the hub has no device file for this device yet. "
                    f"Add the library file with openhal library add {escape(name)}"
                )
        for unknown in result.unknown:
            console.print(
                f"[yellow]unknown[/yellow]  {escape(unknown.id)}  {escape(unknown.label or '')} at "
                f"{escape(unknown.address)}. Start the driver writer with "
                f"openhal writer start --unknown {escape(unknown.id)}"
            )
        for problem in result.errors:
            console.print(f"[red]error[/red]  {escape(problem.driver)}  {escape(problem.error)}")
        if not (result.matched or result.unknown):
            console.print("Nothing found.")
