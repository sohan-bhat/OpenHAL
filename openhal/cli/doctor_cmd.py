"""`openhal doctor`, which checks the setup and says how to fix each problem."""

from __future__ import annotations

import importlib.util
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

import typer
from rich.markup import escape
from rich.table import Table

from openhal._brand import DAEMON_NAME
from openhal.cli import _common
from openhal.cli._common import EXIT_FAILED, OPTIONS, console, home
from openhal.client.settings import TOKEN_ENV, human_token_path


@dataclass
class Check:
    name: str
    result: str
    detail: str


def _private(path: Path, mode: int) -> bool:
    return stat.S_IMODE(path.stat().st_mode) & ~mode == 0


def _files() -> list[Check]:
    checks: list[Check] = []
    folder = home()
    if not folder.exists():
        return [Check("config folder", "fail", f"{folder} does not exist. Run openhal init.")]
    if _private(folder, 0o700):
        checks.append(Check("config folder", "ok", f"{folder} is private"))
    else:
        checks.append(Check("config folder", "fail", f"{folder} is readable by others. Run chmod 700 {folder}"))
    for name, required in (("human.token", True), ("approval.key", False), ("hub.db", False)):
        path = folder / name
        if not path.exists():
            if required:
                checks.append(Check(name, "fail", f"{path} is missing. Run openhal init."))
            continue
        if _private(path, 0o600):
            checks.append(Check(name, "ok", f"{path} is readable by you only"))
        else:
            checks.append(Check(name, "fail", f"{path} is readable by others. Run chmod 600 {path}"))
    config_file = folder / "config.yaml"
    if config_file.exists():
        from openhal.hub.config import load_config

        try:
            config = load_config(folder)
        except (ValueError, OSError) as exc:
            checks.append(Check("config.yaml", "fail", f"{config_file} is invalid. {exc}"))
        else:
            lan = "LAN access is on" if config.api.allow_lan else "local connections only"
            tty = "" if config.confirm.require_tty else ", confirm.require_tty is off"
            checks.append(Check("config.yaml", "ok" if not config.api.allow_lan else "warn", f"{lan}{tty}"))
    return checks


def _hub() -> list[Check]:
    from openhal.client import Client, HubNotRunning, OpenHALError, Unauthorized

    checks: list[Check] = []
    if os.environ.get(TOKEN_ENV):
        checks.append(Check("token", "warn", f"{TOKEN_ENV} is set, so the CLI uses it instead of {human_token_path()}"))
    try:
        with Client(OPTIONS.url, transport=_common.TRANSPORT) as client:
            status = client.status()
            url = client.url
    except HubNotRunning as exc:
        return [*checks, Check("hub", "fail", f"{exc} Start it with {DAEMON_NAME}.")]
    except Unauthorized as exc:
        return [*checks, Check("hub", "ok", "the hub answers"), Check("token", "fail", str(exc))]
    except OpenHALError as exc:
        return [*checks, Check("hub", "fail", str(exc))]
    checks.append(Check("hub", "ok", f"{status.product} {status.version} at {url}"))
    you = status.you
    if you.kind == "human":
        checks.append(Check("token", "ok", f"human token for {you.name}"))
    else:
        checks.append(
            Check("token", "warn", f"{you.kind} token {you.name}. Confirm, unlock and enable need the human token")
        )
    checks.append(Check("devices", "ok", f"{status.connected} of {status.devices} connected"))
    for problem in status.load_problems:
        checks.append(Check("device file", "fail", f"{problem.path} did not load. {' '.join(problem.problems)}"))
    if status.stopped:
        checks.append(Check("stop", "warn", f"the hub is stopped ({status.stop_reason}). Run openhal unlock"))
    return checks


def _software() -> list[Check]:
    from openhal.drivers import registry

    checks = [Check("python", "ok", sys.version.split()[0])]
    for module, purpose in (
        ("httpx", "the client"),
        ("fastapi", "the hub API"),
        ("uvicorn", "the hub server"),
        ("mcp", "openhal mcp"),
        ("websockets", "live events"),
    ):
        if importlib.util.find_spec(module) is None:
            checks.append(Check(module, "fail", f"missing, needed by {purpose}. Install openhal-hub[hub]"))
    for name in registry.names():
        try:
            registry.load(name)
        except registry.UnknownDriver as exc:
            checks.append(Check(f"driver {name}", "warn", str(exc)))
        else:
            checks.append(Check(f"driver {name}", "ok", "installed"))
    return checks


def register(app: typer.Typer) -> None:
    @app.command()
    def doctor() -> None:
        """Check the hub, the token, config permissions and installed driver extras."""
        checks = [*_files(), *_hub(), *_software()]
        table = Table("check", "result", "detail", box=None, pad_edge=False)
        style = {"ok": "green", "warn": "yellow", "fail": "red"}
        for check in checks:
            table.add_row(escape(check.name), f"[{style[check.result]}]{check.result}[/]", escape(check.detail))
        console.print(table)
        failed = sum(check.result == "fail" for check in checks)
        if failed:
            console.print(f"{failed} problems found.")
            raise typer.Exit(EXIT_FAILED)
        console.print("No problems found.")
