"""`openhal routine`, automations that run without a model (ADR 0007).

A bare `openhal routine` lists the routines. At a terminal, a command without a routine id shows a
picker of the routines (ADR 0020). Enabling, running, approving and deleting are steps for a
person, so their picker shows only with the human token, and each still takes its typed phrase.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.markup import escape
from rich.table import Table

from openhal.cli import _choices, _tty
from openhal.cli._choices import Need
from openhal.cli._common import EXIT_FAILED, console, handled, hub, print_json, styled, when
from openhal.cli._pick import Option
from openhal.client.models import Routine, RoutineDryRun, RoutineSummary, Run, StepDecision

app = typer.Typer(help="List, draft, dry run, enable, disable and run routines.")
NO_ROUTINES = "No routines. Draft one with openhal routine new <id> --file <path>."


def _print_step(step: StepDecision, prefix: str) -> None:
    if step.status is not None:
        code = f" [dim]{escape(step.code)}[/dim]" if step.code and step.status != "done" else ""
        console.print(f"{prefix}{styled(step.status)}{code}  {escape(step.message or '')}")
        return
    extra = step.model_extra or {}
    shown = ", ".join(f"{key} {value}" for key, value in extra.items())
    console.print(f"{prefix}[dim]{escape(shown or step.message or '')}[/dim]")


def _print_dry_run(result: RoutineDryRun) -> None:
    verdict = "[green]passes[/green]" if result.ok else "[red]does not pass[/red]"
    console.print(f"dry run {verdict}")
    for index, decision in enumerate(result.decisions, start=1):
        _print_step(decision, f"  {index}. ")
    for problem in result.problems:
        console.print(f"  [red]problem[/red]  {escape(problem)}")


def _print_run(run: Run) -> None:
    console.print(f"run {escape(run.run_id)}  {styled(run.status)}  {escape(run.message or '')}")
    for index, step in enumerate(run.steps, start=1):
        _print_step(step, f"  {index}. ")


def _print_routine(routine: Routine) -> None:
    state = "[green]enabled[/green]" if routine.enabled else "[yellow]disabled[/yellow]"
    console.print(f"[bold]{escape(routine.id)}[/bold]  {escape(routine.kind)}  {state}")
    console.print(
        f"devices {escape(', '.join(routine.devices) or 'none')}, highest hazard {escape(routine.max_hazard or '')}"
    )
    console.print(f"triggers {escape(', '.join(routine.triggers) or 'manual only')}")
    console.print(f"sha256 {escape(routine.sha256)}")
    if routine.drafted_by:
        console.print(f"drafted by {escape(routine.drafted_by)}")
    if routine.enabled_by and routine.enabled:
        console.print(f"enabled by {escape(routine.enabled_by)}")
    if routine.disabled_reason and not routine.enabled:
        console.print(f"disabled because {escape(routine.disabled_reason)}")
    console.print(escape(routine.source_raw or routine.source), style="dim")
    if routine.last_dry_run:
        _print_dry_run(routine.last_dry_run)
    for run in routine.history[-5:]:
        _print_run(run)


def _list(as_json: bool) -> list[RoutineSummary]:
    with hub() as client:
        routines = client.routines()
    if as_json:
        print_json(routines)
        return []
    if not routines:
        console.print(NO_ROUTINES)
        return []
    table = Table("id", "kind", "state", "devices", "hazard", "triggers", "last run", box=None, pad_edge=False)
    for routine in routines:
        last = routine.last_run
        table.add_row(
            escape(routine.id),
            escape(routine.kind),
            "[green]enabled[/green]" if routine.enabled else "[yellow]disabled[/yellow]",
            escape(", ".join(routine.devices)),
            escape(routine.max_hazard or ""),
            escape(", ".join(routine.triggers)),
            f"{styled(last.status)} {when(last.finished_at)}" if last else "",
        )
    console.print(table)
    return routines


@app.callback(invoke_without_command=True)
@handled
def overview(ctx: typer.Context, as_json: bool = typer.Option(False, "--json", help="Print JSON.")) -> None:
    """The routines, and how to look at one."""
    if ctx.invoked_subcommand is not None:
        return
    routines = _list(as_json)
    if routines:
        console.print(
            f"Show one with openhal routine show {escape(routines[0].id)}, or pick one with openhal routine show"
        )


@app.command("list")
@handled
def list_routines(as_json: bool = typer.Option(False, "--json", help="Print JSON.")) -> None:
    """List routines."""
    _list(as_json)


def _routines() -> list[Option]:
    with hub() as client:
        routines = client.routines()
    return [
        Option(item.id, f"{'enabled' if item.enabled else 'disabled'}, {', '.join(item.devices) or 'no devices'}")
        for item in routines
    ]


def _routine(command: str, *, person: bool = False, as_json: bool = False, then: str = "") -> str:
    spec = Need(
        command,
        "a routine",
        "routines",
        example=lambda value: f"{command} {value}{then}",
        empty=NO_ROUTINES,
        every="openhal routine list",
        person=person,
    )
    return _choices.need(spec, _routines, as_json=as_json)


HELP_ID = "The routine id. A terminal shows a picker."
HELP_PERSON_ID = "The routine id. A terminal with the human token shows a picker."


@app.command()
@handled
def show(
    routine_id: str = typer.Argument(None, help=HELP_ID),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Show a routine with its source, last dry run and recent runs."""
    routine_id = routine_id or _routine("openhal routine show", as_json=as_json)
    with hub() as client:
        routine = client.routine(routine_id)
    print_json(routine) if as_json else _print_routine(routine)


@app.command()
@handled
def new(
    routine_id: str = typer.Argument(None, help="Lowercase id with dashes, for example keep-room-cool."),
    file: Path = typer.Option(None, "--file", "-f", exists=True, dir_okay=False, help="The routine source."),  # noqa: B008
    kind: str = typer.Option(None, "--kind", help="yaml or python. Taken from the file suffix when left out."),
) -> None:
    """Store a routine. A new routine stays disabled until you dry run and enable the routine."""
    if routine_id is None or file is None:
        name = routine_id or "keep-room-cool"
        spec = Need(
            "openhal routine new",
            "a new routine id and --file with the routine source",
            "routines",
            example=lambda _: f"openhal routine new {name} --file {file or name + '.routine.yaml'}",
        )
        _choices.missing(spec, [])
    chosen = kind or ("python" if file.suffix == ".py" else "yaml")
    if chosen not in ("yaml", "python"):
        raise ValueError("--kind must be yaml or python.")
    with hub() as client:
        routine = client.create_routine(routine_id, file.read_text(encoding="utf-8"), kind=chosen)
    console.print(f"stored {escape(routine.id)}, disabled. Next run openhal routine dry-run {escape(routine.id)}")


@app.command("dry-run")
@handled
def dry_run(
    routine_id: str = typer.Argument(None, help=HELP_ID),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Check every step of a routine against the current state without touching a device."""
    routine_id = routine_id or _routine("openhal routine dry-run", as_json=as_json)
    with hub() as client:
        result = client.routine_dry_run(routine_id)
    print_json(result) if as_json else _print_dry_run(result)
    if not result.ok:
        raise typer.Exit(EXIT_FAILED)


@app.command()
@handled
def enable(
    routine_id: str = typer.Argument(None, help=HELP_PERSON_ID),
    phrase: str = typer.Option(None, "--phrase", help="Only when confirm.require_tty is false."),
) -> None:
    """Enable a routine after reading its dry run. Needs the human token and the typed phrase enable."""
    routine_id = routine_id or _routine("openhal routine enable", person=True)
    with hub() as client:
        routine = client.routine(routine_id)
        _print_routine(routine)
        result = client.routine_dry_run(routine_id)
        _print_dry_run(result)
        if not result.ok:
            console.print("Fix the routine until the dry run passes, then enable it.")
            raise typer.Exit(EXIT_FAILED)
        _tty.require_phrase("enable", "let this routine run on its own", given=phrase)
        enabled = client.enable_routine(routine_id)
    console.print(f"[green]enabled[/green]  {escape(enabled.id)}")


@app.command()
@handled
def disable(routine_id: str = typer.Argument(None, help=HELP_ID)) -> None:
    """Disable a routine. Its triggers stop firing."""
    routine_id = routine_id or _routine("openhal routine disable")
    with hub() as client:
        routine = client.disable_routine(routine_id)
    console.print(f"[yellow]disabled[/yellow]  {escape(routine.id)}")


@app.command()
@handled
def run(
    routine_id: str = typer.Argument(None, help=HELP_PERSON_ID),
    phrase: str = typer.Option(None, "--phrase", help="Only when confirm.require_tty is false."),
) -> None:
    """Run a routine once now. Needs the human token and the typed phrase run."""
    routine_id = routine_id or _routine("openhal routine run", person=True)
    _tty.require_phrase("run", f"run {routine_id} now", given=phrase)
    with hub() as client:
        result = client.run_routine(routine_id)
    _print_run(result)
    if result.status in ("blocked", "failed"):
        raise typer.Exit(EXIT_FAILED)


@app.command()
@handled
def delete(
    routine_id: str = typer.Argument(None, help=HELP_PERSON_ID),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the prompt."),
) -> None:
    """Delete a routine. Needs the human token."""
    routine_id = routine_id or _routine("openhal routine delete", person=True)
    if not yes:
        typer.confirm(f"Delete {routine_id}?", abort=True)
    with hub() as client:
        client.delete_routine(routine_id)
    console.print(f"deleted {escape(routine_id)}")


def _device(routine_id: str) -> str:
    """The device a routine approval is for, picked from the devices the routine drives."""

    def options() -> list[Option]:
        with hub() as client:
            routine = client.routine(routine_id)
        return [Option(device) for device in routine.devices]

    spec = Need(
        f"openhal routine approve {routine_id}",
        "--device with the high hazard device the approval is for",
        "devices",
        placeholder="DEVICE",
        example=lambda device: f"openhal routine approve {routine_id} --device {device}",
        empty=f"{routine_id} drives no device.",
        person=True,
    )
    return _choices.need(spec, options)


@app.command()
@handled
def approve(
    routine_id: str = typer.Argument(None, help=HELP_PERSON_ID),
    device: str = typer.Option(None, "--device", "-d", help="The high hazard device the approval is for."),
    phrase: str = typer.Option(None, "--phrase", help="Only when confirm.require_tty is false."),
) -> None:
    """Sign an approval so this exact routine can drive a high hazard device."""
    routine_id = routine_id or _routine("openhal routine approve", person=True, then=" --device DEVICE")
    device = device or _device(routine_id)
    with hub() as client:
        _print_routine(client.routine(routine_id))
        _tty.require_phrase("approve", f"let this routine drive {device}", given=phrase)
        approval = client.approve_routine(routine_id, device)
    console.print(
        f"[green]approved[/green]  {escape(routine_id)} on {escape(device)} "
        f"for sha256 {escape(approval.sha256 or '')}. "
        "Any change to the routine voids the approval."
    )
