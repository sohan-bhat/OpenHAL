"""`openhal log`, the audit log.

`cells()`, `table()` and `lines()` lay out entries the way `openhal log` prints them. The demo uses
the same three, so the audit lines in docs/demo/scenario.yaml are what this command prints.
"""

from __future__ import annotations

import io
from collections.abc import Iterable, Mapping
from typing import Final

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from openhal.cli._common import EXIT_FAILED, console, handled, hub, print_json, styled, when
from openhal.client.models import AuditEntry

COLUMNS: Final = ("seq", "time", "event", "who", "target", "status", "message")
WIDE: Final = 240
"""The width `lines()` lays the table out at, so no row wraps."""


def cells(entry: AuditEntry) -> dict[str, str]:
    """One entry as the text of each column, by column name."""
    target = ".".join(part for part in (entry.device, (entry.target or "").split(":")[-1]) if part)
    message = entry.details.get("message") or entry.code or ""
    return {
        "seq": str(entry.seq),
        "time": when(entry.at),
        "event": entry.event,
        "who": entry.principal,
        "target": target,
        "status": entry.status or "",
        "message": str(message),
    }


def table(rows: Iterable[Mapping[str, str]]) -> Table:
    """The table `openhal log` prints, with the status word in its color."""
    shown = Table(*COLUMNS, box=None, pad_edge=False)
    for row in rows:
        shown.add_row(*(styled(row[name]) if name == "status" else escape(row[name]) for name in COLUMNS))
    return shown


def lines(rows: Iterable[Mapping[str, str]]) -> list[str]:
    """The same table as plain text, one string per printed line, without color."""
    buffer = io.StringIO()
    Console(file=buffer, width=WIDE, color_system=None, highlight=False).print(table(rows))
    return [line.rstrip() for line in buffer.getvalue().splitlines()]


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
        console.print(table(cells(entry) for entry in entries))
