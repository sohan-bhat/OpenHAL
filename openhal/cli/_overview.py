"""A bare `openhal`, which shows where the person stands and the next steps that fit (ADR 0020).

The view shows whether the config folder is set up, whether OpenHAL runs, which devices are
connected and how many requests are held for a person. The next steps follow from that state, so a
newcomer reads `openhal init` first, then `openhal start`, and then the commands for a running hub.
`openhal --help` lists every command.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rich.markup import escape
from rich.table import Table

from openhal import __version__
from openhal._brand import CLI_NAME, PRODUCT_NAME, START_COMMAND
from openhal.cli._choices import joined
from openhal.cli._common import console, home, hub
from openhal.client.models import DeviceSummary, HubStatus

NAMED = 4
"""The most device names a line shows before it counts the rest."""


@dataclass
class Standing:
    """What a bare `openhal` found. `problem` is set when the hub runs but did not answer the request."""

    set_up: bool
    url: str = ""
    status: HubStatus | None = None
    devices: list[DeviceSummary] = field(default_factory=list)
    problem: str = ""


def folder(path: Path) -> str:
    """A path under the home folder as `~/...`, the way a person reads the path."""
    try:
        return f"~/{path.relative_to(Path.home())}"
    except ValueError:
        return str(path)


def standing() -> Standing:
    from openhal.client import HubNotRunning, OpenHALError

    found = Standing(set_up=(home() / "config.yaml").exists())
    try:
        with hub() as client:
            found.url = client.url
            found.status = client.status()
            found.devices = client.devices()
    except HubNotRunning:
        pass
    except OpenHALError as exc:
        found.problem = str(exc)
    return found


def _names(devices: list[DeviceSummary]) -> str:
    names = [device.id for device in devices]
    if len(names) > NAMED:
        return f"{', '.join(names[:NAMED])} and {len(names) - NAMED} more"
    return joined(names)


def _rows(found: Standing) -> list[tuple[str, str]]:
    place = escape(folder(home()))
    rows = [
        (
            "setup",
            f"{place} is [green]set up[/green]" if found.set_up else f"{place} is [yellow]not set up[/yellow] yet",
        )
    ]
    url = escape(found.url)
    status = found.status
    if found.problem:
        rows.append(("hub", f"[green]running[/green] at {url}. {escape(found.problem)}"))
        return rows
    if status is None:
        rows.append(("hub", f"[yellow]not running[/yellow] at {url}"))
        return rows
    you = f"{status.you.kind}:{status.you.name}"
    rows.append(("hub", f"[green]running[/green] at {url} as {escape(you)}"))
    if status.stopped:
        rows.append(("stop", f"[red]stopped[/red], {escape(status.stop_reason or 'no reason given')}"))
    connected = [device for device in found.devices if device.connected]
    apart = [device for device in found.devices if not device.connected]
    shown = [f"{escape(_names(connected))} [green]connected[/green]"] if connected else []
    shown += [f"{escape(_names(apart))} [yellow]not connected[/yellow]"] if apart else []
    rows.append(("devices", ", ".join(shown) or "none yet"))
    pending = status.pending_confirmations
    held = f"{pending} request{'s' if pending != 1 else ''} [yellow]held[/yellow] for a person"
    rows.append(("requests", held if pending else "none held for a person"))
    return rows


def steps(found: Standing) -> list[tuple[str, str]]:
    """The next commands for this state, the most pressing first."""
    if not found.set_up and found.status is None:
        return [
            ("openhal init", "set up the config folder, the human token and a simulated plant waterer"),
            ("openhal demo", "watch an agent babysit a simulated 3D print, with nothing to set up"),
        ]
    if found.problem:
        return [("openhal doctor", "check the setup and show how to fix each problem")]
    status = found.status
    if status is None:
        return [
            (START_COMMAND, f"run {PRODUCT_NAME} in this terminal"),
            ("openhal service install", f"run {PRODUCT_NAME} in the background, starting at login"),
        ]
    found_steps: list[tuple[str, str]] = []
    if status.stopped:
        found_steps.append(("openhal unlock", "lift the stop lock, with the typed phrase unlock"))
    if status.pending_confirmations:
        found_steps.append(
            ("openhal confirm", "see each request held for a person, then approve or reject the request")
        )
    read_only = [device.id for device in found.devices if not device.writable]
    if read_only:
        found_steps.append(("openhal file confirm", f"answer each limit of {joined(read_only)}, read-only until then"))
    if not found.devices:
        found_steps.append(("openhal discover", "search for devices with read-only identify commands"))
        found_steps.append(("openhal library", "browse the starter device files for real products"))
    found_steps.append(("openhal devices", "list the devices and the channels of each"))
    found_steps.append(("openhal limits", "see and change each device's limits"))
    return found_steps[:3]


def _table(rows: list[tuple[str, str]]) -> Table:
    """Two columns, a label that never wraps and text that folds, so a long path is never cut."""
    table = Table(box=None, show_header=False, pad_edge=False)
    table.add_column(no_wrap=True)
    table.add_column(overflow="fold")
    for label, text in rows:
        table.add_row(label, text)
    return table


def show() -> None:
    """Print where the person stands and the next steps."""
    found = standing()
    console.print(f"[bold]{PRODUCT_NAME}[/bold] {escape(__version__)}\n")
    console.print(_table(_rows(found)))
    console.print("\n[bold]Next[/bold]")
    console.print(_table([(escape(command), escape(what)) for command, what in steps(found)]))
    console.print(f"\n{CLI_NAME} --help lists every command.")
