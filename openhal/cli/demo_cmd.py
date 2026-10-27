"""`openhal demo`, an agent babysitting a 3D print against a real hub, with nothing to set up.

The plain demo connects an agent and the owner to a hub with a simulated Klipper printer and its
camera. The agent sends six requests, the owner approves the cancel, and the demo prints the hub's
audit log (openhal/demo/scenario.py). `--full` runs the whole system end to end with the Arduino
plant waterer (openhal/demo/e2e.py).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.markup import escape

from openhal.cli import log_cmd
from openhal.cli._common import console, fail


def _show(lines: list[str], indent: str) -> None:
    for line in lines:
        text = escape(line)
        if line.startswith("<- error"):
            text = f"[bold]{text}[/bold]"
        elif line.startswith("#") or (line.startswith(indent) and not line.startswith(indent * 2)):
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
        real_time: bool = typer.Option(
            False, "--real-time", help="With --full, run the simulated plant waterer at real speed."
        ),
        full: bool = typer.Option(
            False, "--full", help="Run the whole system with the plant waterer, from discovery to an MCP agent."
        ),
    ) -> None:
        """Watch an agent babysit a 3D print on a simulated Klipper printer and its camera.

        The agent warms the bed, is refused a nozzle over the limit, pauses the print and asks to cancel.
        The owner approves the cancel, and the demo ends with the hub's audit log.

        With --full the hub starts empty and runs the whole system with the Arduino plant waterer.

        Nothing touches hardware. The kernel decides every command.
        """
        from openhal.demo import e2e, e2e_trace, rig, scenario, trace

        if full:
            speed = 1.0 if real_time else e2e.SPEED
            console.print("[dim]Starting a hub with the simulated plant waterer...[/dim]")
            try:
                result = asyncio.run(e2e.run(speed=speed))
            except rig.DemoError as exc:
                fail(str(exc))
            lines = e2e_trace.lines(result, trace.ASCII_ARROWS)
            text = e2e.dump(result)
        else:
            console.print("[dim]Starting a hub with a simulated Klipper printer and its camera...[/dim]")
            result = asyncio.run(scenario.run())
            lines = trace.lines(result, trace.ASCII_ARROWS)
            text = scenario.dump(result)
        console.print()
        _show(lines, trace.INDENT)
        console.print()
        if full and not real_time:
            console.print(f"[dim]The simulated board ran {speed:g} times faster than real time.[/dim]")
        if not full:
            console.print("The demo hub's audit log, newest first")
            console.print(log_cmd.table(result["audit"]["entries"]))
            console.print(f"{escape(trace.counts(result))}.")
            console.print()
            console.print("[dim]Demo data from simulated devices. The camera frames are line drawings.[/dim]")
        if record is not None:
            record.parent.mkdir(parents=True, exist_ok=True)
            record.write_text(text, encoding="utf-8")
            console.print(f"[green]recorded[/green]  {escape(str(record))}")
