"""`openhal runs`, the runs of steps agents and people started, and the caps a person sets on them.

`list`, `show` and `cancel` work with any token, and an agent token sees only its own runs. `caps`
shows the caps and, given a new value, changes them, which takes the human token. A lower cap
applies at once. A higher cap takes the typed phrase confirm, as `openhal limits set` does to widen
a limit, so no script or agent's shell can raise a cap.
"""

from __future__ import annotations

from typing import Any

import typer
from rich.markup import escape
from rich.table import Table

from openhal.cli import _tty
from openhal.cli._common import console, handled, hub, print_json, styled
from openhal.cli.limits_cmd import _person_can_type

app = typer.Typer(help="See and cancel runs of steps, and set the caps on them.", no_args_is_help=True)

PHRASE = "confirm"
WHAT = "raise these run caps"
CAPS = ("max_steps", "max_seconds", "per_agent")


@app.command("list")
@handled
def list_runs(as_json: bool = typer.Option(False, "--json", help="Print JSON.")) -> None:
    """List the runs this token can see, newest first. The human token sees every run."""
    with hub() as client:
        runs = client.runs()
    if as_json:
        print_json(runs)
        return
    if not runs:
        console.print("No runs yet.")
        return
    table = Table("run", "owner", "status", "steps", "message", box=None, pad_edge=False)
    for run in runs:
        steps = f"{run.done_steps} of {run.total_steps}"
        table.add_row(escape(run.run_id), escape(run.owner), styled(run.status), steps, escape(run.message))
    console.print(table)


def _what(result: Any) -> str:
    if result.kind in ("write", "action"):
        shown = f"{result.device} {result.target}"
        return f"{shown} {result.value}" if result.value is not None else shown
    if result.kind == "wait":
        return f"{result.seconds:g} s"
    if result.kind == "wait_until":
        return f"{result.condition}, {result.waited_s:g} s"
    return ", ".join(f"{reading.device}.{reading.channel}" for reading in result.readings or [])


@app.command("show")
@handled
def show_run(
    run_id: str = typer.Argument(..., help="A run id from openhal runs list."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Show one run with every step it ran."""
    with hub() as client:
        run = client.run(run_id, last=10_000)
    if as_json:
        print_json(run)
        return
    console.print(f"[bold]{escape(run.run_id)}[/bold]  {styled(run.status)}  {escape(run.owner)}")
    console.print(escape(run.message))
    for result in run.results:
        number = f"{result.index:>4}"
        console.print(f"{number}  {result.kind:<10} {styled(result.status)}  {escape(_what(result))}")


@app.command("cancel")
@handled
def cancel_run(run_id: str = typer.Argument(..., help="A run id from openhal runs list.")) -> None:
    """End a run before its next step. The human token may end any run."""
    with hub() as client:
        run = client.cancel_run(run_id)
    console.print(f"{styled(run.status)}  {escape(run.message)}")


@app.command("caps")
@handled
def caps(
    max_steps: int = typer.Option(None, "--max-steps", help="Steps in one run, counting every repeat."),
    max_seconds: float = typer.Option(None, "--max-seconds", help="The longest run, wait or sample, in seconds."),
    per_agent: int = typer.Option(None, "--per-agent", help="Runs, waits and samples one token may have at once."),
    phrase: str = typer.Option(None, "--phrase", help="Only when confirm.require_tty is false."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Show the run caps, or change them. A lower cap applies at once, and a higher one takes the phrase confirm."""
    changes = {
        name: value
        for name, value in (("max_steps", max_steps), ("max_seconds", max_seconds), ("per_agent", per_agent))
        if value is not None
    }
    with hub() as client:
        current = client.run_caps()
        if changes:
            raised = [name for name, value in changes.items() if value > getattr(current, name)]
            if raised and client.whoami().kind == "human" and _person_can_type(phrase):
                phrase = _tty.require_phrase(PHRASE, WHAT, given=phrase)
            current = client.set_run_caps(
                max_steps=max_steps, max_seconds=max_seconds, per_agent=per_agent, phrase=phrase
            )
    if as_json:
        print_json(current)
        return
    for name in CAPS:
        value = getattr(current, name)
        before = current.changed.get(name)
        shown = f"{before['from']:g} to {value:g}" if before else f"{value:g}"
        console.print(f"{name:<12} {shown}")
