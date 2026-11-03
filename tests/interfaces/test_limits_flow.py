"""`openhal limits` for a person who doesn't know what to type next.

A bare `openhal limits` shows every limit and one change to copy. At a real pseudo-terminal a
missing device or channel opens a picker, and `openhal limits set` alone walks through the device,
the channel and the new value before the same checks as before. Without a terminal each missing
part gets an error with the valid values and one command to copy, and the exit code stays 2.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openhal.cli import _common
from openhal.cli.main import app
from openhal.spec import loads
from tests.interfaces.conftest import SyncHub
from tests.interfaces.test_limits_cli import brightness_max, confirmed
from tests.terminal import CLEAR, DOWN, ENTER, Keys, person_at_terminal

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="pseudo-terminals are POSIX only")

runner = CliRunner()
SWITCH = """
device: Wall switch
id: switch
connect: { mock: switch }
write:
  state: { type: bool }
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""


def run(*args: str) -> tuple[int, str]:
    """The exit code and the output with every run of spaces as one, so table columns read as words."""
    result = runner.invoke(app, list(args))
    return result.exit_code, " ".join(result.output.split())


@pytest.fixture
def lamp(sync_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(_common, "TRANSPORT", sync_hub.transport)
    monkeypatch.setenv("OPENHAL_TOKEN", sync_hub.tokens.human)
    path = sync_hub.hub.config.devices_dir / "desk-lamp.hal.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(confirmed())
    sync_hub.runner.run(sync_hub.hub.load_device_file(path))
    return path


def test_a_bare_limits_shows_every_limit_and_one_change_to_copy(lamp: Path) -> None:
    code, out = run("limits")
    assert code == 0, out
    assert "desk-fan fan_speed" in out
    assert "desk-lamp brightness 0 % to 80 %" in out
    assert "heater power" in out
    assert 'Change a limit with openhal limits set desk-fan.fan_speed --max "75 %"' in out
    assert "or pick each step with openhal limits set" in out
    data = json.loads(run("limits", "--json")[1])
    assert [item["device"] for item in data] == ["desk-fan", "heater", "desk-lamp"]


def test_show_without_a_device_lists_the_devices_and_one_command(lamp: Path) -> None:
    code, out = run("limits", "show")
    assert code == 2
    assert "openhal limits show needs a device." in out
    assert "devices desk-fan, heater, desk-lamp" in out
    assert "run openhal limits show desk-fan" in out
    code, out = run("limits", "show", "--json")
    assert code == 2


def test_show_with_a_picker_at_a_terminal(lamp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with person_at_terminal(monkeypatch, [Keys("Pick a device", "lamp" + ENTER)]) as person:
        code, out = run("limits", "show")
    assert code == 0, out
    assert "Desk lamp" in person.text
    assert "0 % to 80 %" in out


def test_set_alone_walks_through_device_channel_and_value(lamp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    steps = [
        Keys("Pick a device", "lamp" + ENTER),
        Keys("Pick a channel of desk-lamp", ENTER),
        Keys("Pick the limit to change on desk-lamp.brightness", ENTER),
        Keys("New max for desk-lamp.brightness", CLEAR + "60 %" + ENTER),
    ]
    with person_at_terminal(monkeypatch, steps) as person:
        code, out = run("limits", "set")
    assert code == 0, out
    assert "device reports 0 % to 100 %" in person.text
    assert "The device reports 0 % to 100 %." in person.text
    assert "max 80 % to 60 %" in out
    assert 'The same change in one line is openhal limits set desk-lamp.brightness --max "60 %"' in out
    assert brightness_max(lamp) == 60


def test_a_walked_widening_still_takes_the_typed_phrase(lamp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    steps = [
        Keys("Pick a channel of desk-lamp", ENTER),
        Keys("Pick the limit to change", ENTER),
        Keys("New max for desk-lamp.brightness", CLEAR + "90" + ENTER),
        Keys("needs a number with a unit", " %" + ENTER),
        "yes",
    ]
    with person_at_terminal(monkeypatch, steps) as person:
        code, out = run("limits", "set", "desk-lamp")
    assert code == 1
    assert "Type confirm and press Enter to widen these limits." in person.text
    assert "did not match confirm" in out
    assert brightness_max(lamp) == 80
    steps = [
        Keys("Pick the limit to change", DOWN + DOWN + ENTER),
        Keys("New rate", CLEAR + "15 %/s" + ENTER),
        "confirm",
    ]
    with person_at_terminal(monkeypatch, steps):
        code, out = run("limits", "set", "desk-lamp.brightness")
    assert code == 0, out
    assert "rate" in out


def test_set_without_a_terminal_names_each_missing_part(lamp: Path) -> None:
    code, out = run("limits", "set")
    assert code == 2
    assert "openhal limits set needs a device." in out
    assert "devices desk-fan, heater, desk-lamp" in out
    assert 'run openhal limits set desk-fan.fan_speed --max "75 %"' in out
    code, out = run("limits", "set", "desk-lamp")
    assert code == 2
    assert "openhal limits set needs a channel of desk-lamp." in out
    assert "channels brightness" in out
    assert 'run openhal limits set desk-lamp.brightness --max "60 %"' in out
    code, out = run("limits", "set", "desk-lamp.brightness")
    assert code == 2
    assert "openhal limits set needs --min, --max or --rate." in out
    assert "now 0 % to 80 %, max change 10 %/s, device reports 0 % to 100 %" in out
    assert brightness_max(lamp) == 80


def test_a_mistyped_device_or_channel_gets_the_nearest_names(lamp: Path) -> None:
    code, out = run("limits", "show", "desk-lmap")
    assert code == 1
    assert "There is no device 'desk-lmap'. Did you mean desk-lamp" in out
    code, out = run("limits", "show", "desk-lamp.brightnes")
    assert code == 2
    assert "Did you mean brightness?" in out
    code, out = run("limits", "set", "desk-lamp.volume", "--max", "1 %")
    assert code == 2
    assert "Channels with limits are brightness." in out


def test_no_devices_and_no_channels(sync_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_common, "TRANSPORT", sync_hub.transport)
    monkeypatch.setenv("OPENHAL_TOKEN", sync_hub.tokens.human)
    for device in list(sync_hub.hub.kernel.devices):
        sync_hub.runner.run(sync_hub.hub._remove_device(device))
    code, out = run("limits")
    assert (code, "The hub has no devices yet." in out) == (0, True)
    code, out = run("limits", "show")
    assert "The hub has no devices yet." in out
    assert "run openhal limits show DEVICE" in out
    sync_hub.hub.add_device(loads(SWITCH))
    code, out = run("limits")
    assert (code, "No device has a number channel with limits." in out) == (0, True)
    code, out = run("limits", "set")
    assert code == 2
    assert "The hub has no device with a number channel that has limits." in out
    assert "run openhal limits set DEVICE.CHANNEL --max VALUE" in out
    code, out = run("limits", "set", "switch")
    assert "switch has no number channel with limits." in out
