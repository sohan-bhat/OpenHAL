"""The hub as a background service. A launchd agent on macOS and a systemd user unit on Linux.

The service runs `python -m openhal.hub.daemon` with the Python that installed it and the same
config folder, so it starts the hub the CLI talks to. It runs as the person, never as root, and the
hub keeps its own rule of listening on loopback only. Every command and file change goes through a
`Runner`, so `--dry-run` and tests change nothing.
"""

from __future__ import annotations

import getpass
import os
import plistlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal

from openhal._brand import CONFIG_DIR_ENV, DAEMON_NAME, PACKAGE_NAME, PRODUCT_NAME
from openhal.service.runner import Runner

Platform = Literal["macos", "linux"]
PLATFORMS: Final[tuple[Platform, ...]] = ("macos", "linux")
LABEL: Final = f"org.{PACKAGE_NAME}.hub"
UNIT: Final = f"{DAEMON_NAME}.service"
LOG_NAME: Final = f"{DAEMON_NAME}.log"


class ServiceError(RuntimeError):
    """The service can't be set up here. The message says what to do instead."""


def this_platform() -> Platform:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    raise ServiceError(f"The background service runs on macOS and Linux. Start {DAEMON_NAME} yourself on this system.")


def daemon_command() -> list[str]:
    """The hub, started with this Python so the service uses this install."""
    return [sys.executable, "-m", "openhal.hub.daemon"]


def _systemd_quote(word: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_@%+=:,./-]+", word):
        return word
    escaped = word.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


@dataclass
class Status:
    installed: bool
    running: bool
    pid: int | None = None
    detail: str = ""


@dataclass
class Service:
    """One hub service for one person, on one platform."""

    platform: Platform
    runner: Runner
    user_home: Path
    config_home: Path
    command: list[str] = field(default_factory=daemon_command)
    uid: int = field(default_factory=os.getuid)
    user: str = field(default_factory=getpass.getuser)

    @property
    def path(self) -> Path:
        if self.platform == "macos":
            return self.user_home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
        return self.user_home / ".config" / "systemd" / "user" / UNIT

    @property
    def log_path(self) -> Path:
        return self.config_home / LOG_NAME

    @property
    def target(self) -> str:
        return f"gui/{self.uid}/{LABEL}"

    def render(self) -> str:
        """The plist or unit file this service installs."""
        if self.platform == "macos":
            plist = {
                "Label": LABEL,
                "ProgramArguments": self.command,
                "EnvironmentVariables": {CONFIG_DIR_ENV: str(self.config_home)},
                "WorkingDirectory": str(self.config_home),
                "RunAtLoad": True,
                "KeepAlive": {"SuccessfulExit": False},
                "StandardOutPath": str(self.log_path),
                "StandardErrorPath": str(self.log_path),
            }
            return plistlib.dumps(plist, sort_keys=False).decode("utf-8")
        environment = _systemd_quote(f"{CONFIG_DIR_ENV}={self.config_home}")
        return "\n".join(
            [
                "[Unit]",
                f"Description={PRODUCT_NAME} hub",
                "",
                "[Service]",
                "Type=simple",
                f"ExecStart={' '.join(_systemd_quote(word) for word in self.command)}",
                f"Environment={environment}",
                f"WorkingDirectory={_systemd_quote(str(self.config_home))}",
                "Restart=on-failure",
                "RestartSec=2",
                "",
                "[Install]",
                "WantedBy=default.target",
                "",
            ]
        )

    def install(self) -> list[str]:
        """Write the service file and start it now. Returns notes for the person."""
        if not self.runner.dry_run:
            self.config_home.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.platform == "macos":
            self.runner.run(["launchctl", "bootout", self.target], check=False)
            self.runner.write(self.path, self.render())
            self.runner.run(["launchctl", "bootstrap", f"gui/{self.uid}", str(self.path)])
            return [f"Logs go to {self.log_path}."]
        self.runner.write(self.path, self.render())
        self.runner.run(["systemctl", "--user", "daemon-reload"])
        self.runner.run(["systemctl", "--user", "enable", UNIT])
        self.runner.run(["systemctl", "--user", "restart", UNIT])
        notes = [f"Logs are in journalctl --user -u {DAEMON_NAME}."]
        linger = self.runner.run(["loginctl", "show-user", self.user, "--property=Linger", "--value"], check=False)
        if linger.ok and linger.output.strip() == "no":
            notes.append(f"Run sudo loginctl enable-linger {self.user} so the hub keeps running after you log out.")
        return notes

    def uninstall(self) -> bool:
        """Stop the service and remove its file. Returns False if it wasn't installed."""
        installed = self.path.exists()
        if self.platform == "macos":
            self.runner.run(["launchctl", "bootout", self.target], check=False)
            self.runner.remove(self.path)
            return installed
        self.runner.run(["systemctl", "--user", "disable", "--now", UNIT], check=False)
        self.runner.remove(self.path)
        self.runner.run(["systemctl", "--user", "daemon-reload"], check=False)
        return installed

    def restart(self) -> None:
        if not self.path.exists():
            raise ServiceError("The service is not installed. Install it with openhal service install.")
        if self.platform == "macos":
            self.runner.run(["launchctl", "kickstart", "-k", self.target])
        else:
            self.runner.run(["systemctl", "--user", "restart", UNIT])

    def status(self) -> Status:
        if not self.path.exists():
            return Status(False, False, detail="not installed")
        if self.platform == "macos":
            shown = self.runner.run(["launchctl", "print", self.target], check=False)
            if not shown.ok:
                return Status(True, False, detail="installed, not loaded")
            found_state = re.search(r"^\s*state = (.+?)\s*$", shown.output, re.M)
            found_pid = re.search(r"^\s*pid = (\d+)", shown.output, re.M)
            launchd_state = found_state.group(1) if found_state else "loaded"
            launchd_pid = int(found_pid.group(1)) if found_pid else None
            return Status(True, launchd_state == "running", launchd_pid, launchd_state)
        active = self.runner.run(["systemctl", "--user", "is-active", UNIT], check=False)
        state = active.output.strip() or "unknown"
        main_pid = self.runner.run(["systemctl", "--user", "show", UNIT, "--property=MainPID", "--value"], check=False)
        number = main_pid.output.strip()
        pid = int(number) if number.isdigit() and int(number) > 0 else None
        return Status(True, state == "active", pid, state)
