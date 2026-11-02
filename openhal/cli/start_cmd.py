"""`openhal start`, which runs OpenHAL in the foreground (ADR 0018)."""

from __future__ import annotations

import typer


def register(app: typer.Typer) -> None:
    @app.command()
    def start(
        host: str = typer.Option(None, "--host", help="Listen on this address. Default from config.yaml."),
        port: int = typer.Option(None, "--port", help="Listen on this port. Default from config.yaml."),
        verbose: bool = typer.Option(False, "--verbose", help="Log every step of the hub."),
    ) -> None:
        """Run OpenHAL in the foreground until Control and C. The background service runs the same command."""
        from openhal.hub import daemon

        daemon.run(host, port, verbose=verbose)
