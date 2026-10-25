"""`openhal demo`, the plant waterer against a real hub, with nothing to set up.

The plain demo sends three commands as an agent. `--full` runs the whole system end to end.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.markup import escape

from openhal.cli._common import console, fail


def _show(lines: list[str], indent: str) -> None:
    for line in lines:
        text = escape(line)
        if line.startswith("<- error"):
            text = f"[bold]{text}[/bold]"
        elif line.startswith(indent) and not line.startswith(indent * 2):
            text = f"[dim]{text}[/dim]"
        console.print(text)


def register(app: typer.Typer) -> None:
    @app.command()
    def demo(
        record: Path = typer.Option(  # noqa: B008
            None,
            "--record",
            help="Save the result as YAML, as docs/demo/scenario.yaml, or docs/demo/e2e.yaml with --full.",
        ),
        real_time: bool = typer.Option(False, "--real-time", help="Run the simulated board at real speed."),
        full: bool = typer.Option(
            False, "--full", help="Run the whole system, from discovery to an MCP agent and a routine."
        ),
    ) -> None:
        """Start a hub with the simulated plant waterer and send it three commands as an agent.

        With --full the hub starts empty and runs the whole system, from discovery to an MCP agent and a routine.

        Nothing touches hardware. The board speaks the real firmware protocol and the kernel decides every command.
        """
        from openhal.demo import e2e, e2e_trace, rig, scenario, trace

        speed = 1.0 if real_time else (e2e.SPEED if full else scenario.SPEED)
        console.print("[dim]Starting a hub with the simulated plant waterer...[/dim]")
        if full:
            try:
                result = asyncio.run(e2e.run(speed=speed))
            except rig.DemoError as exc:
                fail(str(exc))
            lines = e2e_trace.lines(result, trace.ASCII_ARROWS)
            text = e2e.dump(result)
        else:
            result = asyncio.run(scenario.run(speed=speed))
            lines = trace.lines(result, trace.ASCII_ARROWS)
            text = scenario.dump(result)
        console.print()
        _show(lines, trace.INDENT)
        console.print()
        if not real_time:
            console.print(f"[dim]The simulated board ran {speed:g} times faster than real time.[/dim]")
        if record is not None:
            record.parent.mkdir(parents=True, exist_ok=True)
            record.write_text(text, encoding="utf-8")
            console.print(f"[green]recorded[/green]  {escape(str(record))}")
