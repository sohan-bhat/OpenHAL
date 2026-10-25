"""`openhal init` as a wizard, with --yes and from a script.

Discovery is faked, and the self-describing boards are the firmware simulator behind `sim:` ports.
Every client config and service file lands in a temporary HOME, and a fake runner stands in for
launchctl and systemctl. No test runs real discovery or touches a real config.
"""

from __future__ import annotations

import json
import shutil
import stat
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openhal.cli import _tty
from openhal.cli.main import app
from openhal.demo.scenario import example_file
from openhal.drivers.openhal_firmware.simulator import SIMULATORS, FirmwareSimulator
from openhal.hub import discovery
from openhal.hub.tokens import TokenStore
from openhal.service import clients, devices
from openhal.service.background import LABEL
from openhal.spec.loader import load
from tests.cli.conftest import Machine

runner = CliRunner()
PLATFORM = "macos" if sys.platform == "darwin" else "linux"


def run(*args: str, input: str | None = None) -> tuple[int, str]:
    result = runner.invoke(app, list(args), input=input)
    return result.exit_code, result.output


@pytest.fixture(autouse=True)
def no_real_discovery(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Refuse real discovery. Tests that want devices found install a fake with `fake_discovery`."""

    async def refuse(drivers: list[str] | None, registered: set[str]) -> discovery.DiscoveryResult:
        raise AssertionError("A test ran real discovery.")

    monkeypatch.setattr(devices, "_discover", refuse)
    yield
    SIMULATORS.clear()


@pytest.fixture
def library_file(tmp_path: Path) -> Path:
    """A library file that still carries its author's confirmation, which init must drop."""
    path = tmp_path / "library" / "plant-waterer.hal.yaml"
    path.parent.mkdir()
    shutil.copy(example_file(), path)
    assert "confirmed:" in path.read_text()
    return path


@pytest.fixture
def fake_discovery(monkeypatch: pytest.MonkeyPatch, library_file: Path) -> list[set[str]]:
    seen: list[set[str]] = []

    async def fake(drivers: list[str] | None, registered: set[str]) -> discovery.DiscoveryResult:
        seen.append(set(registered))
        return discovery.DiscoveryResult(
            matched=[
                discovery.Match(
                    "/dev/ttyACM0",
                    "openhal-firmware",
                    {"firmware.product": "plant-waterer"},
                    "OpenHAL board plant-waterer",
                    str(library_file),
                    "plant-waterer",
                    4,
                )
            ],
            unknown=[
                discovery.Unknown("a1", "sim:desk-fan", "openhal-firmware", {}, "OpenHAL board desk-fan"),
                discovery.Unknown("b2", "/dev/ttyUSB0", "serial", {"usb": "0403:6001"}, "USB serial"),
            ],
            errors=[
                {"driver": "ble", "error": "The ble driver needs an optional dependency that isn't installed (bleak)."},
                {"driver": "mqtt", "error": "TimeoutError: no broker answered"},
            ],
        )

    monkeypatch.setattr(devices, "_discover", fake)
    return seen


def read_only(path: Path) -> None:
    text = path.read_text()
    assert "confirmed" not in text, "init must never confirm limits for the person"
    file = load(path)
    assert not file.writable
    assert all(entry.suggested for entry in [*file.write.values(), *file.actions.values()])


def test_a_script_run_does_only_the_first_steps(machine: Machine) -> None:
    code, out = run("init")
    assert code == 0, out
    assert (machine.config / "human.token").exists()
    assert not (machine.config / "agent.token").exists()
    assert "openhal token create --agent" in out
    assert "Look for devices with openhal init --yes" in out
    assert "MCP clients" not in out
    assert machine.runner.commands == []


def test_yes_adds_found_devices_read_only(machine: Machine, fake_discovery: list[set[str]]) -> None:
    code, out = run("init", "--yes")
    assert code == 0, out
    assert fake_discovery == [{"plant-waterer"}], "discovery leaves out devices that have a file"
    folder = machine.config / "devices"
    fan = folder / "desk-fan.hal.yaml"
    read_only(fan)
    assert load(fan).provenance.source == "self-described"
    assert load(fan).connect.params["port"] == "sim:desk-fan"
    waterer = folder / "plant-waterer-2.hal.yaml"
    read_only(waterer)
    library = load(waterer)
    assert library.device_id == "plant-waterer-2"
    assert library.connect.params["port"] == "/dev/ttyACM0"
    assert library.provenance.tool == "openhal init"
    assert "unknown        USB serial at /dev/ttyUSB0 (serial)" in out
    assert "openhal writer start --driver serial" in out
    assert "mqtt  TimeoutError" in out
    assert "1 skipped, their extras aren't installed" in out
    assert "agent token" in out
    assert "scope read" in out
    for client in clients.known_clients(machine.home, PLATFORM):
        assert client.title in out
        assert not client.path.exists(), "--yes never writes a client config"
    assert not (machine.home / "Library" / "LaunchAgents" / f"{LABEL}.plist").exists()
    assert machine.runner.commands == []

    code, out = run("init", "--yes")
    assert code == 0, out
    assert "kept           openhal-firmware at sim:desk-fan" in out
    assert sorted(path.name for path in folder.iterdir()) == [
        "desk-fan.hal.yaml",
        "plant-waterer-2.hal.yaml",
        "plant-waterer.hal.yaml",
    ]


def test_named_devices_and_id_collisions(machine: Machine) -> None:
    code, out = run(
        "init",
        "--yes",
        "--no-discover",
        "--no-sample",
        "--device",
        "openhal-firmware=sim:desk-fan",
        "--device",
        "openhal-firmware=sim:default",
        "--device",
        "serial=/dev/ttyUSB0",
    )
    assert code == 0, out
    folder = machine.config / "devices"
    ids = sorted(load(path).device_id for path in folder.iterdir())
    assert ids == ["desk-fan", "desk-fan-2"]
    for path in folder.iterdir():
        read_only(path)
    assert "only self-describing devices can be added by address" in out
    code, out = run("init", "--device", "no-equals-sign")
    assert code == 2


def test_a_device_that_does_not_answer_is_skipped(machine: Machine) -> None:
    SIMULATORS["mute"] = FirmwareSimulator(product="mute", silent=True)
    code, out = run("init", "--yes", "--no-discover", "--no-sample", "--device", "openhal-firmware=sim:mute")
    assert code == 0, out
    assert "skipped" in out
    assert "openhal writer start --driver openhal-firmware --param port=sim:mute" in out
    assert list((machine.config / "devices").iterdir()) == []


def test_the_wizard_asks(machine: Machine, fake_discovery: list[set[str]], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_tty, "interactive", lambda: True)
    answers = "\n".join(["", "n", "y", "control_low", "cursor", "n"]) + "\n"
    code, out = run("init", input=answers)
    assert code == 0, out
    folder = machine.config / "devices"
    assert (folder / "desk-fan.hal.yaml").exists()
    assert not (folder / "plant-waterer-2.hal.yaml").exists()
    store = TokenStore(machine.config / "hub.db")
    principal = store.principal((machine.config / "agent.token").read_text().strip())
    store.close()
    assert principal is not None
    assert (principal.kind, principal.scope) == ("agent", "control_low")
    cursor = json.loads((machine.home / ".cursor" / "mcp.json").read_text())
    server = cursor["mcpServers"]["openhal"]
    assert server["args"][-3:] == ["mcp", "--token-file", str(machine.config / "agent.token")]
    assert machine.runner.commands == []


def test_a_broken_client_config_is_left_alone(machine: Machine) -> None:
    client = clients.client_for("claude-desktop", machine.home, PLATFORM)
    client.path.parent.mkdir(parents=True)
    client.path.write_text("{ not json")
    code, out = run("init", "--yes", "--no-discover", "--client", "claude-desktop")
    assert code == 1
    assert "not valid JSON" in out
    assert client.path.read_text() == "{ not json"
    assert list(client.path.parent.iterdir()) == [client.path]
    code, out = run("init", "--client", "cursor")
    assert code == 1
    assert "--client needs an agent token" in out


def test_the_agent_token_is_kept_until_its_scope_changes(machine: Machine) -> None:
    run("init", "--yes", "--no-discover")
    token_file = machine.config / "agent.token"
    first = token_file.read_text()
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
    code, out = run("init", "--yes", "--no-discover")
    assert "agent.token kept" in out
    assert token_file.read_text() == first
    code, out = run("init", "--yes", "--no-discover", "--agent-scope", "control_low")
    assert code == 0, out
    assert "rotated, scope control_low" in out
    code, out = run("init", "--agent-scope", "everything")
    assert code == 2


def test_service_flag_installs_through_the_runner(machine: Machine) -> None:
    code, out = run("init", "--yes", "--no-discover", "--service")
    assert code == 0, out
    plist = machine.home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    assert plist.exists()
    assert machine.runner.commands[-1].startswith("launchctl bootstrap")
    assert "Check the hub with openhal status" in out
    code, out = run("init", "--yes", "--no-discover", "--device", "openhal-firmware=sim:desk-fan")
    assert code == 0, out
    assert "openhal service restart" in out
