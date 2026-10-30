"""`openhal library`, the starter device files the hub matches discovered devices against.

The files live where discovery searches for them (openhal/hub/discovery.py), in `library/` of a source
checkout or `openhal/library_data` of an installed wheel. A file is named by its file name without
the suffix, such as `rigol-dp832`. `add` copies the file into the hub's devices folder byte for byte,
so it never adds a confirmation, and it never overwrites a file that is already there.

Run this module to regenerate library/README.md, `uv run python -m openhal.cli.library_cmd`.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
from rich.markup import escape
from rich.table import Table

from openhal._brand import CLI_NAME, DAEMON_NAME, DEVICE_FILE_SUFFIX
from openhal.cli._common import EXIT_USAGE, config, console, fail, print_json, show
from openhal.spec.loader import DeviceFileError, load
from openhal.spec.models import DeviceFile, Match

app = typer.Typer(help="Browse the device library and copy its files into the hub.", no_args_is_help=True)

FAMILIES: dict[str, str] = {
    "openhal-firmware": "Arduino and ESP32 boards running the OpenHAL firmware",
    "scpi": "SCPI instruments",
    "marlin": "Marlin printers over USB",
    "moonraker": "Klipper printers through Moonraker",
    "rpi-gpio": "Raspberry Pi GPIO boards",
    "rpi-camera": "Raspberry Pi cameras",
    "esphome": "ESPHome devices",
    "mqtt": "MQTT sensors",
    "homeassistant": "Home Assistant plugs and lights",
    "modbus": "Modbus energy meters",
    "midi": "MIDI controllers",
    "ble": "Bluetooth LE sensors",
    "alpaca": "Telescope mounts through ASCOM Alpaca",
}
"""README section titles by driver, in the order they appear."""


@dataclass(frozen=True)
class Entry:
    name: str
    path: Path
    file: DeviceFile


def name_for(path: str | Path) -> str:
    """The library name of a device file, its file name without the suffix."""
    return Path(path).name.removesuffix(DEVICE_FILE_SUFFIX)


def roots() -> list[Path]:
    from openhal.hub.discovery import library_paths

    return library_paths()


def entries(paths: list[Path] | None = None) -> list[Entry]:
    """Every valid library file, the first one found for each name, ordered by driver and name."""
    found: dict[str, Entry] = {}
    for root in roots() if paths is None else paths:
        for path in sorted(root.rglob(f"*{DEVICE_FILE_SUFFIX}")):
            name = name_for(path)
            if name in found:
                continue
            try:
                found[name] = Entry(name, path, load(path))
            except (DeviceFileError, OSError):
                continue
    order = {driver: index for index, driver in enumerate(FAMILIES)}
    return sorted(found.values(), key=lambda entry: (order.get(entry.file.connect.driver, len(order)), entry.name))


def find(name: str) -> Entry:
    wanted = name_for(name.rsplit("/", 1)[-1])
    known = entries()
    for entry in known:
        if entry.name == wanted:
            return entry
    close = difflib.get_close_matches(wanted, [entry.name for entry in known], n=3)
    hint = f" Did you mean {', '.join(close)}?" if close else f" Run {CLI_NAME} library list to see every file."
    fail(f"The library has no file named {wanted}.{hint}", EXIT_USAGE)


def _confirmed(file: DeviceFile) -> bool:
    writes = any(spec.confirmed is not None for spec in file.write.values())
    actions = any(action.confirmed is not None for action in file.actions.values())
    return file.confirmed is not None or writes or actions


def _match_text(match: Match) -> list[str]:
    out: list[str] = []
    for key, value in match.model_dump(mode="json", exclude_defaults=True).items():
        if isinstance(value, list):
            out.extend(f"{key} {item}" for item in value)
        elif isinstance(value, dict):
            out.extend(f"{key}.{field} {item}" for field, item in value.items())
        else:
            out.append(f"{key} {value}")
    return out


def view(entry: Entry, *, detail: bool = False) -> dict[str, Any]:
    """An entry as JSON. With detail, limits take the shape hal/devices/describe uses, a unit beside numbers."""
    file = entry.file
    data: dict[str, Any] = {
        "name": entry.name,
        "id": file.device_id,
        "device": file.device.name,
        "manufacturer": file.device.manufacturer,
        "model": file.device.model,
        "driver": file.connect.driver,
        "hazard": file.effective_hazard,
        "verification": file.provenance.verification.status,
        "match": file.match.model_dump(mode="json", exclude_defaults=True),
        "read": sorted(file.read),
        "write": sorted(file.write),
        "actions": sorted(file.actions),
        "path": str(entry.path),
    }
    if detail:
        high = file.effective_hazard == "high"
        limits = {"type", "unit", "min", "max", "step", "max_change_per_s", "values", "max_length", "pattern"}
        data["write"] = {
            name: {
                **spec.model_dump(include=limits, exclude_none=True),
                "confirm": "confirm-each-time" if high else spec.confirm,
                "suggested": spec.suggested,
            }
            for name, spec in file.write.items()
        }
        data["actions"] = {
            name: {
                "description": action.description,
                "args": {arg: spec.model_dump(exclude_none=True) for arg, spec in action.args.items()},
                "require": [condition for condition, _message in action.conditions],
                "confirm": "confirm-each-time" if high else action.confirm,
                "suggested": action.suggested,
            }
            for name, action in file.actions.items()
        }
        data["notes"] = file.notes
    return data


def _controls(file: DeviceFile) -> str:
    parts = []
    if file.write:
        parts.append(f"{len(file.write)} control{'s' if len(file.write) != 1 else ''}")
    if file.actions:
        parts.append(f"{len(file.actions)} action{'s' if len(file.actions) != 1 else ''}")
    return ", ".join(parts) or "reads only"


@app.command("list")
def list_files(
    driver: str = typer.Option(None, "--driver", "-d", help="Only files for this driver, such as scpi."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """List the library's device files."""
    found = [entry for entry in entries() if driver is None or entry.file.connect.driver == driver]
    if as_json:
        print_json([view(entry) for entry in found])
        return
    if not found:
        console.print(
            f"The library has no files for the {escape(driver)} driver." if driver else "The library is empty."
        )
        return
    table = Table(box=None, pad_edge=False)
    table.add_column("name", no_wrap=True)
    table.add_column("device")
    table.add_column("driver", no_wrap=True)
    table.add_column("hazard", no_wrap=True)
    table.add_column("controls")
    for entry in found:
        file = entry.file
        table.add_row(
            escape(entry.name),
            escape(file.device.name),
            escape(file.connect.driver),
            escape(file.effective_hazard),
            escape(_controls(file)),
        )
    console.print(table)
    console.print(f"{len(found)} files, all unverified. Add one with {CLI_NAME} library add NAME.")


@app.command("show")
def show_file(
    name: str = typer.Argument(..., help="A library name, such as rigol-dp832."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Show one library file, what it matches and every limit it suggests."""
    entry = find(name)
    if as_json:
        print_json(view(entry, detail=True))
        return
    file = entry.file
    console.print(f"[bold]{escape(file.device.name)}[/bold]  {escape(entry.name)}")
    status = file.provenance.verification.status
    console.print(f"driver {escape(file.connect.driver)}, {file.effective_hazard} hazard, {status}, loads read-only")
    for line in _match_text(file.match):
        console.print(f"match  {escape(line)}")

    def tier(confirm: str) -> str:
        return "confirm-each-time" if file.effective_hazard == "high" else confirm

    for channel, spec in file.write.items():
        limits = f"{show(spec.min, spec.unit)} to {show(spec.max, spec.unit)}" if spec.type == "number" else spec.type
        console.print(f"control  {escape(channel)}  {escape(limits)}, {tier(spec.confirm)}, suggested")
    for action_name, action in file.actions.items():
        console.print(f"action  {escape(action_name)}, {tier(action.confirm)}, suggested")
    console.print(f"file  {escape(str(entry.path))}")
    console.print(f"Add the file with {CLI_NAME} library add {escape(entry.name)}")
    typer.echo("")
    typer.echo(entry.path.read_text(encoding="utf-8").rstrip("\n"))


@app.command("add")
def add_file(name: str = typer.Argument(..., help="A library name, such as rigol-dp832.")) -> None:
    """Copy a library file into the hub's devices folder. The copy stays read-only until you confirm its limits."""
    entry = find(name)
    if _confirmed(entry.file):
        fail(f"{entry.path} carries a confirmation, and a library file never carries one, so the file was not added.")
    folder = config().devices_dir
    target = folder / entry.path.name
    if target.exists():
        fail(f"{target} already exists. The library never overwrites a device file. Edit that file instead.")
    for path in sorted(folder.glob(f"*{DEVICE_FILE_SUFFIX}")) if folder.exists() else []:
        try:
            existing = load(path)
        except (DeviceFileError, OSError):
            continue
        if existing.device_id == entry.file.device_id:
            fail(f"{path} already describes a device with id {existing.device_id}, so the library file was not added.")
    folder.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("xb") as handle:
            handle.write(entry.path.read_bytes())
    except FileExistsError:
        fail(f"{target} already exists. The library never overwrites a device file. Edit that file instead.")
    console.print(f"[green]added[/green]  {escape(str(target))}")
    console.print(
        "The file loads read-only. Set the connection for your device, check every limit and remove suggested: true "
        f"from each limit you checked. Then run {CLI_NAME} file confirm {escape(str(target))} and restart "
        f"{DAEMON_NAME}."
    )


README_PATH = Path(__file__).resolve().parents[2] / "library" / "README.md"


def readme(found: list[Entry]) -> str:
    """library/README.md, every file by family."""
    lines = [
        "# Device library",
        "",
        "Starter device files for real products. The hub offers a library file when discovery finds a device "
        "the file matches.",
        "Every file is unverified and loads read-only until a person checks and confirms the file's limits.",
        "[How the library works](../docs/guide/library.md).",
        "",
        "```",
        f"{CLI_NAME} library list",
        f"{CLI_NAME} library show rigol-dp832",
        f"{CLI_NAME} library add rigol-dp832",
        "```",
    ]
    drivers = list(dict.fromkeys(entry.file.connect.driver for entry in found))
    for driver in drivers:
        lines += ["", f"## {FAMILIES.get(driver, driver)}", ""]
        lines += ["| Name | Device | Hazard | Controls |", "|---|---|---|---|"]
        for entry in (item for item in found if item.file.connect.driver == driver):
            file = entry.file
            link = f"[`{entry.name}`]({entry.path.parent.name}/{entry.path.name})"
            lines.append(f"| {link} | {file.device.name} | {file.effective_hazard} | {_controls(file)} |")
    lines += [
        "",
        f"This list is generated from the files by `uv run python -m openhal.cli.library_cmd`. {len(found)} files.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    README_PATH.write_text(readme(entries([README_PATH.parent])), encoding="utf-8")


if __name__ == "__main__":
    main()
