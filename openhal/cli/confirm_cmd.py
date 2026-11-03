"""`openhal confirm`, the queue of commands and limit changes held for a person.

A bare `openhal confirm` lists the pending requests. At a terminal, `show`, `approve` and `reject`
without an id show a picker of the pending requests (ADR 0020). Approving and rejecting are steps
for a person, so their picker shows only with the human token, and approving still takes the
typed phrase approve.
"""

from __future__ import annotations

import json
from urllib.parse import quote

import typer
from rich.markup import escape
from rich.table import Table

from openhal.cli import _choices, _tty
from openhal.cli._choices import Need
from openhal.cli._common import console, exit_for, handled, hub, print_decision, print_json, styled
from openhal.cli._pick import Option
from openhal.client.calls import Call
from openhal.client.models import ConfirmationRequest, Decision

app = typer.Typer(help="List, approve and reject commands and limit changes held for a person.")
NONE_PENDING = "No request is pending approval."


def _describe(command: dict[str, object]) -> str:
    device = command.get("device")
    if command.get("kind") == "limits":
        changes = command.get("changes") or {}
        steps = changes.items() if isinstance(changes, dict) else []
        shown = ", ".join(f"{name} {step['from']} to {step['to']}" for name, step in steps)
        return f"limits {device}.{command.get('channel')} {shown}".strip()
    if command.get("kind") == "risk":
        return f"risk {device}.{command.get('name')} {command.get('before')} to {command.get('after')}"
    if command.get("kind") == "action":
        args = command.get("args") or {}
        shown = " ".join(f"{key}={value}" for key, value in dict(args).items()) if isinstance(args, dict) else ""
        return f"{device}.{command.get('action')} {shown}".strip()
    return f"{device}.{command.get('channel')} = {json.dumps(command.get('value'))}"


def _print_request(request: ConfirmationRequest) -> None:
    console.print(f"request {escape(request.id)}  {styled(request.status)}")
    console.print(f"command {escape(_describe(request.command))}")
    console.print(f"requested by {escape(request.requested_by)}")
    console.print(f"dry run at request time  {styled(request.dry_run.status)}  {escape(request.dry_run.message)}")
    if request.decided_by:
        console.print(f"decided by {escape(request.decided_by)}")
    if request.result:
        print_decision(request.result, prefix="result  ")


def _table(requests: list[ConfirmationRequest]) -> None:
    table = Table("id", "status", "command", "requested by", "dry run", box=None, pad_edge=False)
    for request in requests:
        table.add_row(
            escape(request.id),
            styled(request.status),
            escape(_describe(request.command)),
            escape(request.requested_by),
            styled(request.dry_run.status),
        )
    console.print(table)


@app.callback(invoke_without_command=True)
@handled
def overview(ctx: typer.Context, as_json: bool = typer.Option(False, "--json", help="Print JSON.")) -> None:
    """The pending requests, and how to approve one."""
    if ctx.invoked_subcommand is not None:
        return
    with hub() as client:
        requests = client.confirmations()
    if as_json:
        print_json(requests)
        return
    if not requests:
        console.print(NONE_PENDING)
        return
    _table(requests)
    console.print(
        f"Approve one with openhal confirm approve {escape(requests[0].id)}, or pick one with openhal confirm approve"
    )


@app.command("list")
@handled
def list_requests(
    show_all: bool = typer.Option(False, "--all", help="Include approved, rejected and expired requests."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """List requests held for a person."""
    with hub() as client:
        requests = client.confirmations(include_done=show_all)
    if as_json:
        print_json(requests)
        return
    if not requests:
        console.print(NONE_PENDING)
        return
    _table(requests)


def _pending() -> list[Option]:
    with hub() as client:
        requests = client.confirmations()
    return [Option(request.id, f"{_describe(request.command)}, from {request.requested_by}") for request in requests]


def _request(command: str, *, person: bool = False, as_json: bool = False) -> str:
    spec = Need(
        command, "a pending request", "pending", empty=NONE_PENDING, every="openhal confirm list", person=person
    )
    return _choices.need(spec, _pending, as_json=as_json)


@app.command()
@handled
def show(
    request_id: str = typer.Argument(None, help="The request id. A terminal shows a picker."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Show one request with its command and the dry run at the time of the request."""
    request_id = request_id or _request("openhal confirm show", as_json=as_json)
    with hub() as client:
        request = client.confirmation(request_id)
    print_json(request) if as_json else _print_request(request)


@app.command()
@handled
def approve(
    request_id: str = typer.Argument(None, help="The request id. A terminal with the human token shows a picker."),
    phrase: str = typer.Option(None, "--phrase", help="Only when confirm.require_tty is false."),
) -> None:
    """Approve a request. The kernel checks the request again against the current state before the command runs."""
    request_id = request_id or _request("openhal confirm approve", person=True)
    with hub() as client:
        request = client.confirmation(request_id)
        _print_request(request)
        if request.status != "pending":
            console.print(f"This request is {escape(request.status)}, so there is nothing to approve.")
            raise typer.Exit(1)
        kind = request.command.get("kind")
        if kind in ("limits", "risk"):
            what = "widen these limits" if kind == "limits" else "lower this risk level"
            typed = _tty.require_phrase("approve", what, given=phrase)
            decision = client.call(
                Call(
                    "POST",
                    f"/v1/confirmations/{quote(request_id, safe='')}/approve",
                    Decision.model_validate,
                    json={"phrase": typed},
                )
            )
        else:
            _tty.require_phrase("approve", "run this command", given=phrase)
            decision = client.approve(request_id)
    print_decision(decision)
    exit_for(decision)


@app.command()
@handled
def reject(
    request_id: str = typer.Argument(None, help="The request id. A terminal with the human token shows a picker."),
    reason: str = typer.Option("", "--reason", "-r", help="Recorded in the audit log."),
) -> None:
    """Reject a request. The command does not run."""
    request_id = request_id or _request("openhal confirm reject", person=True)
    with hub() as client:
        request = client.reject(request_id, reason)
    console.print(f"{styled(request.status)}  {escape(_describe(request.command))}")
