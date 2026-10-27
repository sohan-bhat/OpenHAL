"""`openhal routine`, automations that run without a model (ADR 0007)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.markup import escape
from rich.table import Table

from openhal.cli import _tty
from openhal.cli._common import EXIT_FAILED, console, handled, hub, print_json, styled, when
from openhal.client.models import Routine, RoutineDryRun, Run, StepDecision

app = typer.Typer(help="List, draft, dry run, enable, disable and run routines.", no_args_is_help=True)


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


@app.command("list")
@handled
def list_routines(as_json: bool = typer.Option(False, "--json", help="Print JSON.")) -> None:
    """List routines."""
    with hub() as client:
        routines = client.routines()
    if as_json:
        print_json(routines)
        return
    if not routines:
        console.print("No routines. Draft one with openhal routine new <id> --file <path>.")
        return
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


@app.command()
@handled
def show(
    routine_id: str = typer.Argument(..., help="The routine id."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Show a routine with its source, last dry run and recent runs."""
    with hub() as client:
        routine = client.routine(routine_id)
    print_json(routine) if as_json else _print_routine(routine)


@app.command()
@handled
def new(
    routine_id: str = typer.Argument(..., help="Lowercase id with dashes, for example keep-room-cool."),
    file: Path = typer.Option(..., "--file", "-f", exists=True, dir_okay=False, help="The routine source."),  # noqa: B008
    kind: str = typer.Option(None, "--kind", help="yaml or python. Taken from the file suffix when left out."),
) -> None:
    """Store a routine. A new routine stays disabled until you dry run and enable the routine."""
    chosen = kind or ("python" if file.suffix == ".py" else "yaml")
    if chosen not in ("yaml", "python"):
        raise ValueError("--kind must be yaml or python.")
    with hub() as client:
        routine = client.create_routine(routine_id, file.read_text(encoding="utf-8"), kind=chosen)
    console.print(f"stored {escape(routine.id)}, disabled. Next run openhal routine dry-run {escape(routine.id)}")


@app.command("dry-run")
@handled
def dry_run(
    routine_id: str = typer.Argument(..., help="The routine id."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Check every step of a routine against the current state without touching a device."""
    with hub() as client:
        result = client.routine_dry_run(routine_id)
    print_json(result) if as_json else _print_dry_run(result)
    if not result.ok:
        raise typer.Exit(EXIT_FAILED)


@app.command()
@handled
def enable(
    routine_id: str = typer.Argument(..., help="The routine id."),
    phrase: str = typer.Option(None, "--phrase", help="Only when confirm.require_tty is false."),
) -> None:
    """Enable a routine after reading its dry run. Needs the human token and the typed phrase enable."""
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
def disable(routine_id: str = typer.Argument(..., help="The routine id.")) -> None:
    """Disable a routine. Its triggers stop firing."""
    with hub() as client:
        routine = client.disable_routine(routine_id)
    console.print(f"[yellow]disabled[/yellow]  {escape(routine.id)}")


@app.command()
@handled
def run(
    routine_id: str = typer.Argument(..., help="The routine id."),
    phrase: str = typer.Option(None, "--phrase", help="Only when confirm.require_tty is false."),
) -> None:
    """Run a routine once now. Needs the human token and the typed phrase run."""
    _tty.require_phrase("run", f"run {routine_id} now", given=phrase)
    with hub() as client:
        result = client.run_routine(routine_id)
    _print_run(result)
    if result.status in ("blocked", "failed"):
        raise typer.Exit(EXIT_FAILED)


@app.command()
@handled
def delete(
    routine_id: str = typer.Argument(..., help="The routine id."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Don't ask."),
) -> None:
    """Delete a routine. Needs the human token."""
    if not yes:
        typer.confirm(f"Delete {routine_id}?", abort=True)
    with hub() as client:
        client.delete_routine(routine_id)
    console.print(f"deleted {escape(routine_id)}")


@app.command()
@handled
def approve(
    routine_id: str = typer.Argument(..., help="The routine id."),
    device: str = typer.Option(..., "--device", "-d", help="The high hazard device the approval is for."),
    phrase: str = typer.Option(None, "--phrase", help="Only when confirm.require_tty is false."),
) -> None:
    """Sign an approval that lets this exact routine drive a high hazard device."""
    with hub() as client:
        _print_routine(client.routine(routine_id))
        _tty.require_phrase("approve", f"let this routine drive {device}", given=phrase)
        approval = client.approve_routine(routine_id, device)
    console.print(
        f"[green]approved[/green]  {escape(routine_id)} on {escape(device)} "
        f"for sha256 {escape(approval.sha256 or '')}. "
        "Any change to the routine voids the approval."
    )
