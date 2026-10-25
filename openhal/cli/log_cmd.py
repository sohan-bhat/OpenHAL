"""`openhal log`, the audit log."""

from __future__ import annotations

import typer
from rich.markup import escape
from rich.table import Table

from openhal.cli._common import EXIT_FAILED, console, handled, hub, print_json, styled, when


def register(app: typer.Typer) -> None:
    @app.command()
    @handled
    def log(
        device: str = typer.Option(None, "--device", "-d", help="Only this device."),
        status: str = typer.Option(None, "--status", "-s", help="Only this status, for example blocked."),
        event: str = typer.Option(None, "--event", "-e", help="Only this event, for example action or stop."),
        since: int = typer.Option(0, "--since", help="Only entries after this sequence number."),
        limit: int = typer.Option(50, "--limit", "-n", min=1, max=1000, help="Most entries to show."),
        verify: bool = typer.Option(False, "--verify", help="Check the hash chain instead of listing entries."),
        as_json: bool = typer.Option(False, "--json", help="Print JSON."),
    ) -> None:
        """Show the audit log, newest first, or verify its hash chain."""
        with hub() as client:
            if verify:
                result = client.verify_audit()
                if as_json:
                    print_json(result)
                elif result.ok:
                    console.print(f"[green]intact[/green]  The audit chain verifies. Head {escape(result.head or '')}")
                else:
                    console.print(f"[red]broken[/red]  The audit chain breaks at entry {result.broken_at}.")
                if not result.ok:
                    raise typer.Exit(EXIT_FAILED)
                return
            entries = client.audit(device=device, status=status, event=event, since=since, limit=limit)
        if as_json:
            print_json(entries)
            return
        if not entries:
            console.print("No entries match.")
            return
        table = Table("seq", "time", "event", "who", "target", "status", "message", box=None, pad_edge=False)
        for entry in entries:
            target = ".".join(part for part in (entry.device, (entry.target or "").split(":")[-1]) if part)
            message = entry.details.get("message") or entry.code or ""
            table.add_row(
                str(entry.seq),
                when(entry.at),
                escape(entry.event),
                escape(entry.principal),
                escape(target),
                styled(entry.status),
                escape(str(message)),
            )
        console.print(table)
