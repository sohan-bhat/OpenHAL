"""`openhal service` with a fake runner and a temporary HOME. Nothing real is loaded or enabled."""

from __future__ import annotations

import os
import plistlib
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openhal.cli import service_cmd
from openhal.cli.main import app
from openhal.service.background import LABEL, UNIT, Service
from openhal.service.runner import Runner
from tests.cli.conftest import Machine

runner = CliRunner()


def run(*args: str) -> tuple[int, str]:
    result = runner.invoke(app, list(args))
    return result.exit_code, result.output


def plist_path(m: Machine) -> Path:
    return m.home / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def test_print_macos_plist(machine: Machine) -> None:
    code, out = run("service", "print", "--platform", "macos")
    assert code == 0, out
    plist = plistlib.loads(out.encode())
    assert plist["Label"] == LABEL
    assert plist["ProgramArguments"] == [sys.executable, "-m", "openhal.hub.daemon"]
    assert plist["EnvironmentVariables"] == {"OPENHAL_HOME": str(machine.config)}
    assert plist["RunAtLoad"] is True
    assert plist["KeepAlive"] == {"SuccessfulExit": False}
    assert plist["StandardErrorPath"] == str(machine.config / "openhald.log")


def test_print_linux_unit(machine: Machine) -> None:
    code, out = run("service", "print", "--platform", "linux")
    assert code == 0, out
    assert f"ExecStart={sys.executable} -m openhal.hub.daemon" in out
    assert f"Environment=OPENHAL_HOME={machine.config}" in out
    assert "Restart=on-failure" in out
    assert "WantedBy=default.target" in out
    code, out = run("service", "print", "--platform", "windows")
    assert code == 1


def test_unit_quotes_paths_with_spaces(machine: Machine) -> None:
    service = Service(
        "linux", Runner(dry_run=True), machine.home, machine.home / "my hub", ["/opt/my py/python", "-m", "x"]
    )
    text = service.render()
    assert 'ExecStart="/opt/my py/python" -m x' in text
    assert f'Environment="OPENHAL_HOME={machine.home / "my hub"}"' in text


def test_install_on_macos_writes_the_agent_and_bootstraps_it(machine: Machine) -> None:
    code, out = run("service", "install")
    assert code == 0, out
    path = plist_path(machine)
    assert plistlib.loads(path.read_bytes())["Label"] == LABEL
    uid = os.getuid()
    assert machine.runner.commands == [
        f"launchctl bootout gui/{uid}/{LABEL}",
        f"launchctl bootstrap gui/{uid} {path}",
    ]
    assert "installed" in out


def test_install_on_linux_enables_the_user_unit(machine: Machine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_cmd, "this_platform", lambda: "linux")
    machine.runner.answers["loginctl show-user"] = (0, "no\n")
    code, out = run("service", "install")
    assert code == 0, out
    unit = machine.home / ".config" / "systemd" / "user" / UNIT
    assert "openhal.hub.daemon" in unit.read_text()
    assert machine.runner.commands == [
        "systemctl --user daemon-reload",
        f"systemctl --user enable {UNIT}",
        f"systemctl --user restart {UNIT}",
        "loginctl show-user pi --property=Linger --value",
    ]
    assert "sudo loginctl enable-linger pi" in out


def test_a_failed_command_fails_the_install(machine: Machine) -> None:
    machine.runner.answers["launchctl bootstrap"] = (5, "Bootstrap failed: 5: Input/output error")
    code, out = run("service", "install")
    assert code == 1
    assert "Bootstrap failed" in out


def test_dry_run_prints_and_changes_nothing(machine: Machine) -> None:
    code, out = run("service", "install", "--dry-run")
    assert code == 0, out
    assert not plist_path(machine).exists()
    assert machine.runner.commands == []
    assert "would run    launchctl bootstrap" in out
    assert f"would write  {plist_path(machine)}" in out
    code, out = run("service", "uninstall", "--dry-run")
    assert code == 0, out
    assert "would run    launchctl bootout" in out
    assert machine.runner.commands == []


def test_status_restart_and_uninstall(machine: Machine) -> None:
    code, out = run("service", "status")
    assert code == 1
    assert "not installed" in out
    code, out = run("service", "restart")
    assert code == 1
    assert "not installed" in out
    run("service", "install")
    machine.runner.answers["launchctl print"] = (0, "gui/501/org.openhal.hub = {\n\tstate = running\n\tpid = 4242\n}")
    code, out = run("service", "status")
    assert code == 0, out
    assert "running, pid 4242" in out
    machine.runner.answers["launchctl print"] = (0, "gui/501/org.openhal.hub = {\n\tstate = not running\n}")
    code, out = run("service", "status")
    assert code == 1
    assert "state    not running" in out
    code, out = run("service", "restart")
    assert code == 0, out
    assert machine.runner.commands[-1] == f"launchctl kickstart -k gui/{os.getuid()}/{LABEL}"
    code, out = run("service", "uninstall")
    assert code == 0, out
    assert not plist_path(machine).exists()
    code, out = run("service", "uninstall")
    assert "was not installed" in out


def test_linux_status_reads_systemctl(machine: Machine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_cmd, "this_platform", lambda: "linux")
    run("service", "install")
    machine.runner.answers["systemctl --user is-active"] = (3, "inactive\n")
    machine.runner.answers["systemctl --user show"] = (0, "0\n")
    code, out = run("service", "status")
    assert code == 1
    assert "inactive" in out
    machine.runner.answers["systemctl --user is-active"] = (0, "active\n")
    machine.runner.answers["systemctl --user show"] = (0, "917\n")
    code, out = run("service", "status")
    assert code == 0, out
    assert "active, pid 917" in out
