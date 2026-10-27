"""`openhal confirm`, the queue of commands that wait for a person."""

from __future__ import annotations

import json

import typer
from rich.markup import escape
from rich.table import Table

from openhal.cli import _tty
from openhal.cli._common import console, exit_for, handled, hub, print_decision, print_json, styled
from openhal.client.models import ConfirmationRequest

app = typer.Typer(help="List, approve and reject commands that wait for a person.", no_args_is_help=True)


def _describe(command: dict[str, object]) -> str:
    device = command.get("device")
    if command.get("kind") == "action":
        args = command.get("args") or {}
        shown = " ".join(f"{key}={value}" for key, value in dict(args).items()) if isinstance(args, dict) else ""
        return f"{device}.{command.get('action')} {shown}".strip()
    return f"{device}.{command.get('channel')} = {json.dumps(command.get('value'))}"


def _print_request(request: ConfirmationRequest) -> None:
    console.print(f"request {escape(request.id)}  {styled(request.status)}")
    console.print(f"command {escape(_describe(request.command))}")
    console.print(f"asked by {escape(request.requested_by)}")
    console.print(f"dry run when asked  {styled(request.dry_run.status)}  {escape(request.dry_run.message)}")
    if request.decided_by:
        console.print(f"decided by {escape(request.decided_by)}")
    if request.result:
        print_decision(request.result, prefix="result  ")


@app.command("list")
@handled
def list_requests(
    show_all: bool = typer.Option(False, "--all", help="Include approved, rejected and expired requests."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """List requests waiting for a person."""
    with hub() as client:
        requests = client.confirmations(include_done=show_all)
    if as_json:
        print_json(requests)
        return
    if not requests:
        console.print("Nothing waits for approval.")
        return
    table = Table("id", "status", "command", "asked by", "dry run", box=None, pad_edge=False)
    for request in requests:
        table.add_row(
            escape(request.id),
            styled(request.status),
            escape(_describe(request.command)),
            escape(request.requested_by),
            styled(request.dry_run.status),
        )
    console.print(table)


@app.command()
@handled
def show(
    request_id: str = typer.Argument(..., help="The request id."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Show one request with its command and the dry run at the time it was asked."""
    with hub() as client:
        request = client.confirmation(request_id)
    print_json(request) if as_json else _print_request(request)


@app.command()
@handled
def approve(
    request_id: str = typer.Argument(..., help="The request id."),
    phrase: str = typer.Option(None, "--phrase", help="Only when confirm.require_tty is false."),
) -> None:
    """Approve a request. The kernel checks the request again against the current state before the command runs."""
    with hub() as client:
        request = client.confirmation(request_id)
        _print_request(request)
        if request.status != "pending":
            console.print(f"This request is {escape(request.status)}, so there is nothing to approve.")
            raise typer.Exit(1)
        _tty.require_phrase("approve", "run this command", given=phrase)
        decision = client.approve(request_id)
    print_decision(decision)
    exit_for(decision)


@app.command()
@handled
def reject(
    request_id: str = typer.Argument(..., help="The request id."),
    reason: str = typer.Option("", "--reason", "-r", help="Recorded in the audit log."),
) -> None:
    """Reject a request. The command does not run."""
    with hub() as client:
        request = client.reject(request_id, reason)
    console.print(f"{styled(request.status)}  {escape(_describe(request.command))}")
