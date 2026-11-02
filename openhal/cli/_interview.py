"""The limits interview at a terminal, for `openhal init` and `openhal file confirm`.

The questions and the check of each answer come from openhal/writer/interview.py, the same ones
the hub and the Inspector use. With `confirm.require_tty: true` every answer and the typed phrase
come from the terminal itself, so a script or an agent can't answer for the person.
"""

from __future__ import annotations

from typing import Any

import typer
from rich.markup import escape

from openhal.cli import _tty
from openhal.cli._common import config, console, fail, show
from openhal.spec.models import DeviceFile
from openhal.writer import interview

PHRASE = "confirm"
WHAT = "confirm these limits as safe for this device"


def require_person(phrase: str | None) -> bool:
    """Stop before the first question when no person can answer here. Returns confirm.require_tty."""
    require_tty = config().confirm.require_tty
    if require_tty and phrase is not None:
        fail(f"--phrase can't be used while confirm.require_tty is true. Run this in a terminal and type {PHRASE}.")
    if require_tty and not _tty.interactive():
        fail(
            "To answer the limits interview, run this command yourself in an interactive terminal. "
            "confirm.require_tty is true, so the answers can't come from a script or an agent."
        )
    return require_tty


def _typed(require_tty: bool) -> str:
    if require_tty:
        return _tty.read_phrase(_tty.MARK)
    answer: str = typer.prompt(_tty.MARK.strip(), default="", show_default=False)
    return answer


def ask(draft: dict[str, Any], require_tty: bool) -> dict[str, str]:
    """Walk every question. Enter keeps the suggestion, and an answer that can't stand is asked again."""
    questions = interview.questions(draft)
    name = draft.get("device") if isinstance(draft.get("device"), str) else (draft.get("device") or {}).get("name")
    console.print(
        f"\n[bold]Limits for {escape(str(name or 'this device'))}[/bold]. "
        "Press Enter to keep a suggestion, or type a value to replace it."
    )
    answers: dict[str, str] = {}
    for index, question in enumerate(questions, start=1):
        suggestion = interview.suggestion_text(question)
        offer = f" Suggested {suggestion}." if suggestion is not None else ""
        console.print(f"\n{index} of {len(questions)}  {escape(question.prompt)}{escape(offer)}")
        if question.reason:
            console.print(escape(question.reason), style="dim")
        while True:
            answer = _typed(require_tty).strip() or suggestion or ""
            if not answer:
                console.print("This question has no suggestion, so type a value.")
                continue
            reason = interview.problem(question, answer, answers)
            if reason is None:
                answers[question.id] = answer
                break
            console.print(f"[yellow]again[/yellow]  {escape(reason)}")
    return answers


def summary(device: DeviceFile) -> None:
    """Every limit of a file, as the person confirms the limits."""
    console.print(
        f"\n[bold]{escape(device.device.name)}[/bold]  {escape(device.device_id)}, {device.effective_hazard} hazard"
    )
    for name, spec in device.write.items():
        limits = f"{show(spec.min, spec.unit)} to {show(spec.max, spec.unit)}" if spec.unit else ""
        limits = limits or ", ".join(spec.values or []) or spec.type
        rate = f", at most {show(spec.max_change_per_s, spec.unit)}/s" if spec.max_change_per_s else ""
        tier = f", confirm tier {spec.confirm}" if spec.confirm else ""
        console.print(f"control {escape(name)}  {escape(limits)}{escape(rate)}{escape(tier)}")
    for name in device.actions:
        console.print(f"action  {escape(name)}")
    for interlock in device.interlocks:
        console.print(f"interlock  if {escape(interlock.if_ or 'always')} require {escape(interlock.require)}")
    for step in device.safe_state:
        console.print(f"safe state  {escape(str(step.model_dump(exclude_none=True)))}")


def confirm(draft: dict[str, Any], *, by: str, require_tty: bool, phrase: str | None = None) -> dict[str, Any]:
    """The interview, the summary and the typed phrase. Returns the confirmed file's data.

    A wrong phrase raises typer.Exit with nothing saved.
    """
    from openhal.spec.loader import from_data

    answers = ask(draft, require_tty)
    try:
        confirmed = interview.apply(draft, answers, by=by)
    except interview.AnswerError as exc:
        fail(f"The answers don't make a valid device file, so nothing was saved. {exc}")
    summary(from_data(confirmed))
    _tty.require_phrase(PHRASE, WHAT, given=phrase)
    return confirmed
