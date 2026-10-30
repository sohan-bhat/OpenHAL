"""`openhal writer`, the driver writer for devices OpenHAL doesn't support yet (ADR 0006)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import typer
from rich.markup import escape

from openhal.cli import _tty
from openhal.cli._common import config, console, fail, handled, hub, parse_pairs, print_json, show, styled
from openhal.client.models import WriterSession

app = typer.Typer(help="Draft a device file for an unknown device and confirm its limits.", no_args_is_help=True)

_BARE_NUMBER = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


def _print_session(session: WriterSession) -> None:
    console.print(f"session {escape(session.id)}  {styled(session.status)}")
    for key, value in session.detected.items():
        console.print(f"detected {escape(str(key))} {escape(str(value))}")
    for problem in session.problems:
        console.print(f"[red]problem[/red]  {escape(problem)}")
    if session.unconfirmed:
        console.print(f"[yellow]unconfirmed[/yellow]  {escape(', '.join(session.unconfirmed))}")
    if session.draft_yaml:
        console.print("draft device file", style="bold")
        console.print(escape(session.draft_yaml), style="dim")


@app.command()
@handled
def start(
    unknown: str = typer.Option(None, "--unknown", "-u", help="An id from openhal discover."),
    driver: str = typer.Option(None, "--driver", "-d", help="A driver to connect to the device with."),
    params: list[str] = typer.Option(None, "--param", "-p", help="Driver parameter as key=value. Repeat for more."),  # noqa: B008
    sketch: Path = typer.Option(None, "--sketch", exists=True, dir_okay=False, help="The device's Arduino sketch."),  # noqa: B008
    manual: Path = typer.Option(None, "--manual", exists=True, dir_okay=False, help="A text file with the manual."),  # noqa: B008
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Start a driver writer session. The hub detects with read-only commands and parses any sketch."""
    if not (unknown or driver or sketch or manual):
        raise ValueError("Give --unknown, --driver, --sketch or --manual so the writer has something to start from.")
    with hub() as client:
        session = client.start_writer(
            unknown_id=unknown,
            driver=driver,
            params=parse_pairs(params) if params else None,
            sketch_path=str(sketch.resolve()) if sketch else None,
            manual_text=manual.read_text(encoding="utf-8") if manual else None,
        )
    if as_json:
        print_json(session)
        return
    _print_session(session)
    console.print(
        f"Next draft the device file with your MCP client, or write it yourself and run "
        f"openhal writer propose {escape(session.id)} --file draft.hal.yaml"
    )


@app.command("show")
@handled
def show_session(
    session_id: str = typer.Argument(..., help="The session id."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Show a session with what was detected, the draft and open problems."""
    with hub() as client:
        session = client.writer_session(session_id)
    print_json(session) if as_json else _print_session(session)


@app.command()
@handled
def propose(
    session_id: str = typer.Argument(..., help="The session id."),
    file: Path = typer.Option(..., "--file", "-f", exists=True, dir_okay=False, help="A draft device file."),  # noqa: B008
) -> None:
    """Send a draft device file. Every limit in the draft is stored as suggested until the interview."""
    with hub() as client:
        session = client.propose(session_id, file.read_text(encoding="utf-8"))
    _print_session(session)


def _ask(question_text: str, require_tty: bool) -> str:
    if require_tty:
        return _tty.read_phrase(question_text + " ")
    answer: str = typer.prompt(question_text)
    return answer


@app.command()
@handled
def interview(session_id: str = typer.Argument(..., help="The session id.")) -> None:
    """Answer the limits interview. Each limit needs your own answer. Needs the human token."""
    require_tty = config().confirm.require_tty
    if require_tty and not _tty.interactive():
        fail("Run the interview yourself in an interactive terminal. confirm.require_tty is true.")
    with hub() as client:
        questions = client.interview(session_id).questions
        if not questions:
            console.print("No open questions.")
            return
        answers: dict[str, Any] = {}
        for index, question in enumerate(questions, start=1):
            console.print(f"\n[bold]{index}. {escape(question.prompt)}[/bold]")
            if question.suggested is not None:
                console.print(f"suggested {escape(show(question.suggested, question.unit))}", style="dim")
            if question.reason:
                console.print(f"why {escape(question.reason)}", style="dim")
            answer = ""
            while not answer:
                answer = _ask("your answer" + (f" in {question.unit}" if question.unit else ""), require_tty).strip()
            if question.unit and _BARE_NUMBER.match(answer):
                answer = f"{answer} {question.unit}"
            answers[question.id] = answer
        session = client.answer(session_id, answers)
    _print_session(session)
    if session.status == "ready":
        console.print(f"Every limit is answered. Save the device file with openhal writer finish {escape(session_id)}")


@app.command()
@handled
def finish(
    session_id: str = typer.Argument(..., help="The session id."),
    save_as: str = typer.Option(None, "--save-as", help="File name for the device file in the devices folder."),
    phrase: str = typer.Option(None, "--phrase", help="Only when confirm.require_tty is false."),
) -> None:
    """Save the confirmed device file into the devices folder. Needs the human token and the phrase save."""
    with hub() as client:
        _print_session(client.writer_session(session_id))
        _tty.require_phrase("save", "save this device file", given=phrase)
        result = client.finish(session_id, save_as)
    mode = "writable" if result.writable else "read-only until every limit is confirmed"
    console.print(f"[green]saved[/green]  {escape(result.device_id)} at {escape(result.path)}, {mode}")
    console.print(f"Walk through the staged test plan with openhal writer plan {escape(session_id)}")


@app.command()
@handled
def plan(
    session_id: str = typer.Argument(..., help="The session id."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Show the staged write test plan, smallest safe values first."""
    with hub() as client:
        result = client.test_plan(session_id)
    if as_json:
        print_json(result)
        return
    for step in result.steps:
        approval = "needs approval" if step.needs_approval else "no approval needed"
        console.print(f"{step.step}. {escape(str(step.command))}  [dim]{approval}[/dim]")
        if step.expected:
            console.print(f"   expect {escape(step.expected)}", style="dim")
