"""`openhal service`, the hub as a background service that starts at login.

macOS gets a launchd agent in ~/Library/LaunchAgents, loaded with launchctl. Linux gets a systemd
user unit in ~/.config/systemd/user, enabled with systemctl --user. `--dry-run` prints every file
and command and changes nothing.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.markup import escape

from openhal._brand import DAEMON_NAME
from openhal.cli._common import EXIT_FAILED, console, fail, home
from openhal.service.background import PLATFORMS, Platform, Service, ServiceError, this_platform
from openhal.service.runner import RunError, Runner

app = typer.Typer(
    help="Run the hub in the background. A launchd agent on macOS, a systemd user unit on Linux.",
    no_args_is_help=True,
)

DRY_RUN = typer.Option(False, "--dry-run", help="Print every file and command, and change nothing.")


def runner_for(dry_run: bool) -> Runner:
    return Runner(dry_run=dry_run, echo=lambda line: console.print(escape(line), style="dim"))


def build_service(dry_run: bool = False, platform: Platform | None = None) -> Service:
    """The service for this person and this install. Raises ServiceError on other systems."""
    chosen = platform or this_platform()
    return Service(chosen, runner_for(dry_run), Path.home(), home().expanduser().absolute())


def _service(dry_run: bool = False, platform: Platform | None = None) -> Service:
    try:
        return build_service(dry_run, platform)
    except ServiceError as exc:
        fail(str(exc))


@app.command()
def install(dry_run: bool = DRY_RUN) -> None:
    """Install the service and start the hub now. The hub then starts again at every login."""
    service = _service(dry_run)
    try:
        notes = service.install()
    except RunError as exc:
        fail(str(exc))
    if dry_run:
        return
    console.print(f"[green]installed[/green]  {escape(str(service.path))}, the hub is starting")
    for note in notes:
        console.print(escape(note))


@app.command()
def uninstall(dry_run: bool = DRY_RUN) -> None:
    """Stop the service and remove its file. The config folder and devices stay."""
    service = _service(dry_run)
    try:
        installed = service.uninstall()
    except RunError as exc:
        fail(str(exc))
    if dry_run:
        return
    if installed:
        console.print(f"[green]removed[/green]  {escape(str(service.path))}")
    else:
        console.print("The service was not installed.")


@app.command()
def restart(dry_run: bool = DRY_RUN) -> None:
    """Restart the hub, for example so the hub loads new device files."""
    service = _service(dry_run)
    try:
        service.restart()
    except (RunError, ServiceError) as exc:
        fail(str(exc))
    if not dry_run:
        console.print("[green]restarted[/green]  the hub")


@app.command()
def status() -> None:
    """Show whether the service is installed and running. Exits 1 if the service isn't running."""
    service = _service()
    state = service.status()
    console.print(f"service  {escape(str(service.path))} {'installed' if state.installed else 'not installed'}")
    if state.installed:
        pid = f", pid {state.pid}" if state.pid else ""
        console.print(f"state    {escape(state.detail)}{pid}")
    if not state.running:
        hint = "openhal service install" if not state.installed else f"openhal service restart, or {DAEMON_NAME}"
        console.print(f"Start the hub with {hint}.")
        raise typer.Exit(EXIT_FAILED)


@app.command("print")
def print_file(
    platform: str = typer.Option(None, "--platform", help="macos or linux. Default this machine."),
) -> None:
    """Print the launchd plist or systemd unit that install would write."""
    if platform is not None and platform not in PLATFORMS:
        fail(f"--platform is macos or linux, not {platform}.")
    chosen: Platform | None = "macos" if platform == "macos" else "linux" if platform == "linux" else None
    typer.echo(_service(platform=chosen).render(), nl=False)
