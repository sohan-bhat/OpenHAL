"""`openhal driver`, the driver SDK: list drivers, run the conformance suite, scaffold a new driver.

New drivers start with an `x-` name and the status "experimental". They keep it until they pass the
conformance suite and a hardware test, and a maintainer adds the plain name to the spec's known
drivers.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import re
from pathlib import Path
from string import Template
from typing import Any

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from openhal.drivers import registry

app = typer.Typer(help="List drivers, run the conformance suite and scaffold new drivers.", no_args_is_help=True)
console = Console(highlight=False)

TEMPLATES = Path(__file__).parent / "templates" / "driver"
NAME = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
CATALOG = Path(__file__).resolve().parents[2] / "drivers" / "catalog.json"


def _catalog() -> dict[str, dict[str, Any]]:
    if not CATALOG.exists():
        return {}
    return {entry["name"]: entry for entry in json.loads(CATALOG.read_text())["drivers"]}


@app.command("list")
def list_drivers(as_json: bool = typer.Option(False, "--json", help="Print JSON.")) -> None:
    """Every driver with its protocols, hazard default, conformance level and status."""
    catalog = _catalog()
    rows: list[dict[str, Any]] = []
    for name in registry.names():
        entry = catalog.get(name, {})
        try:
            info = registry.load(name).info
        except Exception as exc:  # noqa: BLE001
            rows.append({"name": name, "installed": False, "detail": str(exc), "status": entry.get("status", "")})
            continue
        rows.append(
            {
                "name": name,
                "installed": True,
                "protocols": list(info.protocols),
                "hazard": info.hazard_default,
                "conformance": info.conformance,
                "status": entry.get("status", "experimental"),
            }
        )
    if as_json:
        typer.echo(json.dumps(rows, indent=2))
        return
    table = Table(box=None, pad_edge=False)
    for column in ("driver", "protocols", "hazard", "conformance", "status"):
        table.add_column(column)
    for row in rows:
        if not row["installed"]:
            table.add_row(row["name"], f"[yellow]not installed[/yellow] {escape(row['detail'])}", "", "", row["status"])
            continue
        table.add_row(
            row["name"], escape(", ".join(row["protocols"])), row["hazard"], row["conformance"], row["status"]
        )
    console.print(table)


@app.command("test")
def run_conformance(name: str = typer.Argument(..., help="The driver name, for example scpi.")) -> None:
    """Run the conformance suite against a driver at its declared level. Exits 1 on any failure."""
    from openhal.conformance import run

    package = registry.package_for(name)
    if package is None:
        console.print(f"[red]error[/red]  There is no driver {escape(name)!r}. Run openhal driver list.")
        raise typer.Exit(2)
    try:
        module = importlib.import_module(f"{package}.conformance")
    except ModuleNotFoundError as exc:
        console.print(f"[red]error[/red]  {escape(name)} has no conformance case ({escape(str(exc))}).")
        raise typer.Exit(1) from exc
    report = asyncio.run(run(module.case()))
    for result in report.results:
        mark = "[dim]skip[/dim]" if result.skipped else ("[green]ok[/green]  " if result.ok else "[red]fail[/red]")
        console.print(f"{mark}  {escape(result.name)}  [dim]{escape(result.detail)}[/dim]")
    passed = sum(1 for result in report.results if result.ok)
    skipped = sum(1 for result in report.results if result.skipped)
    console.print(f"{passed} passed, {skipped} skipped, {len(report.results) - passed - skipped} failed")
    if not report.ok:
        raise typer.Exit(1)


def _find_root(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if (candidate / "openhal" / "drivers" / "base.py").exists() and (candidate / "pyproject.toml").exists():
            return candidate
    return None


@app.command("new")
def new_driver(
    name: str = typer.Argument(..., help="The driver name in lowercase with dashes, for example acme-pump."),
    root: Path = typer.Option(None, "--root", help="An OpenHAL checkout. Default is the current directory."),  # noqa: B008
    title: str = typer.Option(None, "--title", help="A human name for the device family, for example Acme pump."),
) -> None:
    """Scaffold an experimental driver with a simulator, conformance case, tests and docs."""
    base = name.removeprefix("x-")
    if not NAME.match(base):
        console.print("[red]error[/red]  Use lowercase letters, digits and single dashes, for example acme-pump.")
        raise typer.Exit(2)
    target_root = (root or _find_root(Path.cwd()) or Path.cwd()).resolve()
    if not (target_root / "openhal" / "drivers").is_dir():
        where = escape(str(target_root))
        console.print(f"[red]error[/red]  {where} is not an OpenHAL checkout. Run this from one, or pass --root.")
        raise typer.Exit(2)
    driver_name = f"x-{base}"
    package = driver_name.replace("-", "_")
    values = {
        "name": driver_name,
        "slug": base,
        "pkg": package,
        "cls": "".join(part.capitalize() for part in base.split("-")) + "Driver",
        "title": title or base.replace("-", " ").capitalize(),
    }
    files = {
        f"openhal/drivers/{package}/__init__.py": "__init__.py.tmpl",
        f"openhal/drivers/{package}/driver.py": "driver.py.tmpl",
        f"openhal/drivers/{package}/simulator.py": "simulator.py.tmpl",
        f"openhal/drivers/{package}/conformance.py": "conformance.py.tmpl",
        f"openhal/drivers/{package}/catalog.json": "catalog.json.tmpl",
        f"openhal/drivers/{package}/examples/{base}.hal.yaml": "example.hal.yaml.tmpl",
        f"tests/drivers/{package}/__init__.py": None,
        f"tests/drivers/{package}/test_{package}.py": "test.py.tmpl",
        f"docs/drivers/{driver_name}.md": "doc.md.tmpl",
        f"docs/hardware-tests/{driver_name}.md": "hardware-test.md.tmpl",
    }
    existing = [path for path in files if (target_root / path).exists()]
    if existing:
        console.print(f"[red]error[/red]  These exist already, so nothing was created. {escape(', '.join(existing))}")
        raise typer.Exit(1)
    for relative, template in files.items():
        path = target_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        text = "" if template is None else Template((TEMPLATES / template).read_text()).substitute(values)
        path.write_text(text)
        console.print(f"[green]wrote[/green]  {escape(relative)}")
    console.print(
        f"Next, run uv run openhal driver test {driver_name}. Then replace the simulator transport in "
        f"openhal/drivers/{package}/driver.py with the real protocol, following docs/drivers/WRITING-A-DRIVER.md."
    )
