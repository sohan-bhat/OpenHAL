"""`openhal demo`, the plant waterer scenario against a real hub, with nothing to set up."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.markup import escape

from openhal.cli._common import console


def register(app: typer.Typer) -> None:
    @app.command()
    def demo(
        record: Path = typer.Option(None, "--record", help="Write the result as YAML, as docs/demo/scenario.yaml."),  # noqa: B008
        real_time: bool = typer.Option(False, "--real-time", help="Run the simulated board at real speed."),
    ) -> None:
        """Start a hub with the simulated plant waterer and send it three commands as an agent.

        Nothing touches hardware. The board speaks the real firmware protocol and the hub's safety
        kernel decides every command, exactly as it would for a real board.
        """
        from openhal.demo import scenario, trace

        speed = 1.0 if real_time else scenario.SPEED
        console.print("[dim]Starting a hub with the simulated plant waterer...[/dim]")
        result = asyncio.run(scenario.run(speed=speed))
        console.print()
        for line in trace.lines(result):
            style = "dim" if line.startswith(trace.INDENT) and not line.startswith(trace.INDENT * 2) else ""
            text = escape(line)
            if line.startswith("← error"):
                text = f"[bold]{text}[/bold]"
            console.print(f"[{style}]{text}[/{style}]" if style else text)
        console.print()
        if not real_time:
            console.print(f"[dim]The simulated board ran {speed:g} times faster than real time.[/dim]")
        if record is not None:
            record.parent.mkdir(parents=True, exist_ok=True)
            record.write_text(scenario.dump(result), encoding="utf-8")
            console.print(f"[green]recorded[/green]  {escape(str(record))}")
