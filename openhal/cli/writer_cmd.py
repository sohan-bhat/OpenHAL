"""`openhal writer`, the driver writer for devices OpenHAL doesn't support yet (ADR 0006).

A bare `openhal writer` lists the unknown devices discovery found, each with the command that
starts a session for the device (ADR 0020). The hub keeps no list of sessions, so a command without
a session id names `openhal writer start`, which prints the id.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import typer
from rich.markup import escape

from openhal.cli import _choices, _tty
from openhal.cli._choices import Need
from openhal.cli._common import config, console, fail, handled, hub, parse_pairs, print_json, show, styled
from openhal.client.models import WriterSession

app = typer.Typer(help="Draft a device file for an unknown device and confirm its limits.")

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


@app.callback(invoke_without_command=True)
@handled
def overview(ctx: typer.Context, as_json: bool = typer.Option(False, "--json", help="Print JSON.")) -> None:
    """The unknown devices discovery found, and how to start a session for one."""
    if ctx.invoked_subcommand is not None:
        return
    with hub() as client:
        unknown = client.unknown_devices()
    if as_json:
        print_json(unknown)
        return
    for item in unknown:
        console.print(
            f"[yellow]unknown[/yellow]  {escape(item.id)}  {escape(item.label or '')} at {escape(item.address)}. "
            f"Start the driver writer with openhal writer start --unknown {escape(item.id)}"
        )
    if not unknown:
        console.print(
            "No unknown devices. Search with openhal discover, or start from the device's sketch with "
            "openhal writer start --sketch PATH"
        )


def _session(command: str, session_id: str | None) -> str:
    if session_id:
        return session_id
    spec = Need(
        command,
        "a session id",
        "sessions",
        placeholder="SESSION_ID",
        empty="openhal writer start prints the id of a new session.",
    )
    _choices.missing(spec, [])


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
    session_id: str = typer.Argument(None, help="The session id that openhal writer start prints."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Show a session with what was detected, the draft and open problems."""
    session_id = _session("openhal writer show", session_id)
    with hub() as client:
        session = client.writer_session(session_id)
    print_json(session) if as_json else _print_session(session)


@app.command()
@handled
def propose(
    session_id: str = typer.Argument(None, help="The session id that openhal writer start prints."),
    file: Path = typer.Option(..., "--file", "-f", exists=True, dir_okay=False, help="A draft device file."),  # noqa: B008
) -> None:
    """Send a draft device file. Every limit in the draft is stored as suggested until the interview."""
    session_id = _session("openhal writer propose", session_id)
    with hub() as client:
        session = client.propose(session_id, file.read_text(encoding="utf-8"))
    _print_session(session)


def _ask(question_text: str, require_tty: bool) -> str:
    if require_tty:
        return _tty.read_phrase(question_text + " ")
    answer: str = typer.prompt(question_text, default="", show_default=False)
    return answer


@app.command()
@handled
def interview(session_id: str = typer.Argument(None, help="The session id that openhal writer start prints.")) -> None:
    """Answer the limits interview. Enter keeps a suggestion. Each limit needs your own answer and the human token."""
    session_id = _session("openhal writer interview", session_id)
    require_tty = config().confirm.require_tty
    if require_tty and not _tty.interactive():
        fail("Run the interview yourself in an interactive terminal. confirm.require_tty is true.")
    held: dict[str, str] = {}
    with hub() as client:
        questions = client.interview(session_id).questions
        if not questions:
            console.print("No open questions.")
            return
        console.print("Press Enter to keep a suggestion, or type a value to replace it.")
        while questions:
            answers: dict[str, Any] = {}
            for index, question in enumerate(questions, start=1):
                suggestion = show(question.suggested, question.unit) if question.suggested is not None else None
                offer = f" Suggested {suggestion}." if suggestion else ""
                console.print(f"\n[bold]{index} of {len(questions)}  {escape(question.prompt)}[/bold]{escape(offer)}")
                if question.id in held:
                    console.print(f"[yellow]again[/yellow]  {escape(held[question.id])}")
                if question.reason:
                    console.print(escape(question.reason), style="dim")
                answer = ""
                while not answer:
                    answer = _ask(_tty.MARK.strip(), require_tty).strip() or (suggestion or "")
                if question.unit and _BARE_NUMBER.match(answer):
                    answer = f"{answer} {question.unit}"
                answers[question.id] = answer
            session = client.answer(session_id, answers)
            held = dict(getattr(session, "answer_problems", None) or {})
            questions = [question for question in client.interview(session_id).questions if question.id in held]
    _print_session(session)
    if session.status == "ready":
        console.print(f"Every limit is answered. Save the device file with openhal writer finish {escape(session_id)}")


@app.command()
@handled
def finish(
    session_id: str = typer.Argument(None, help="The session id that openhal writer start prints."),
    save_as: str = typer.Option(None, "--save-as", help="File name for the device file in the devices folder."),
    phrase: str = typer.Option(None, "--phrase", help="Only when confirm.require_tty is false."),
) -> None:
    """Save the confirmed device file into the devices folder. Needs the human token and the phrase save."""
    session_id = _session("openhal writer finish", session_id)
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
    session_id: str = typer.Argument(None, help="The session id that openhal writer start prints."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Show the staged write test plan, smallest safe values first."""
    session_id = _session("openhal writer plan", session_id)
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
