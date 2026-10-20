"""`openhal mcp`, the stdio MCP server for AI clients."""

from __future__ import annotations

from pathlib import Path

import typer

from openhal.cli._common import EXIT_TOKEN, OPTIONS, fail


def register(app: typer.Typer) -> None:
    @app.command()
    def mcp(
        token_file: Path = typer.Option(None, "--token-file", help="A file holding the agent token."),  # noqa: B008
        start: bool = typer.Option(True, "--start/--no-start", help="Start openhald if it is not running."),
    ) -> None:
        """Run the MCP server on stdio. Reads the agent token from OPENHAL_TOKEN or --token-file."""
        try:
            from openhal.mcp.server import SetupError, run
        except ImportError as exc:
            fail(f"openhal mcp needs the MCP SDK ({exc.name}). Install openhal-hub[hub].")
        try:
            run(token_file=token_file or OPTIONS.token_file, url=OPTIONS.url, start=start)
        except SetupError as exc:
            fail(str(exc), EXIT_TOKEN)
