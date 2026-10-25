"""`openhal file`, commands that work on device files without a running hub."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from openhal._brand import DEVICE_FILE_SUFFIX
from openhal.spec.loader import Report, validate_path
from openhal.spec.schema import device_file_schema

app = typer.Typer(help="Validate and confirm device files, and print the schema.", no_args_is_help=True)
console = Console(highlight=False)


def _expand(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(sorted(path.rglob(f"*{DEVICE_FILE_SUFFIX}")))
        else:
            found.append(path)
    return found


def _print_report(report: Report) -> None:
    if report.ok and report.file is not None:
        mode = "writable" if report.file.writable else "read-only"
        device = report.file
        summary = f"{device.device_id}, {device.effective_hazard} hazard, {mode}"
        console.print(f"[green]valid[/green]  {report.path}  ({summary})")
    else:
        console.print(f"[red]invalid[/red]  {report.path}")
    for problem in report.problems:
        console.print(f"  [red]error[/red]  {problem}")
    for warning in report.warnings:
        console.print(f"  [yellow]note[/yellow]   {warning}")


@app.command()
def validate(
    paths: list[Path] = typer.Argument(..., help="Device files, or folders to search for *.hal.yaml files."),  # noqa: B008
    as_json: bool = typer.Option(False, "--json", help="Print results as JSON."),
) -> None:
    """Check device files against the spec. Exits with status 1 if any file is invalid."""
    files = _expand(paths)
    if not files:
        console.print(f"No {DEVICE_FILE_SUFFIX} files found.")
        raise typer.Exit(1)
    reports = [validate_path(path) for path in files]
    if as_json:
        payload = [
            {
                "path": report.path,
                "valid": report.ok,
                "device_id": report.file.device_id if report.file else None,
                "writable": report.file.writable if report.file else False,
                "problems": report.problems,
                "warnings": report.warnings,
            }
            for report in reports
        ]
        typer.echo(json.dumps(payload, indent=2))
    else:
        for report in reports:
            _print_report(report)
        bad = sum(not report.ok for report in reports)
        console.print(f"{len(reports) - bad} valid, {bad} invalid.")
    if any(not report.ok for report in reports):
        raise typer.Exit(1)


@app.command()
def schema() -> None:
    """Print the device file JSON Schema."""
    typer.echo(json.dumps(device_file_schema(), indent=2, sort_keys=True))
