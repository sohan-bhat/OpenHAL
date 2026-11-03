"""`read`, `write`, `action` and `dry-run` without a target, and mistyped names.

At a real pseudo-terminal a left-out target opens a picker of the devices and then of the channels
or actions, and a left-out value is typed with the limits in view. Without a terminal the error
lists what fits and one exact command built from the hub's own devices, with exit code 2.
"""

from __future__ import annotations

import sys

import pytest
from typer.testing import CliRunner

from openhal.cli import _common
from openhal.cli.main import app
from tests.interfaces.conftest import SyncHub
from tests.kernel.conftest import FakeClock
from tests.terminal import CLEAR, DOWN, ENTER, Keys, person_at_terminal

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="pseudo-terminals are POSIX only")

runner = CliRunner()


def run(*args: str) -> tuple[int, str]:
    """The exit code and the output with every run of spaces as one, so table columns read as words."""
    result = runner.invoke(app, list(args))
    return result.exit_code, " ".join(result.output.split())


@pytest.fixture
def cli_hub(sync_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> SyncHub:
    monkeypatch.setattr(_common, "TRANSPORT", sync_hub.transport)
    monkeypatch.setenv("OPENHAL_TOKEN", sync_hub.tokens.human)
    return sync_hub


def test_each_command_without_a_target_names_what_fits(cli_hub: SyncHub) -> None:
    code, out = run("read")
    assert code == 2
    assert "openhal read needs a device." in out
    assert "devices desk-fan, heater" in out
    assert "run openhal read desk-fan.temperature" in out
    code, out = run("write", "--json")
    assert code == 2
    assert "run openhal write desk-fan.fan_speed 0 %" in out
    code, out = run("action")
    assert code == 2
    assert "devices heater" in out
    assert "run openhal action heater.pulse seconds=1s" in out
    code, out = run("dry-run")
    assert code == 2
    assert "openhal dry-run needs a device, or --file with a list of commands." in out


def test_a_device_alone_names_its_channels(cli_hub: SyncHub) -> None:
    code, out = run("read", "heater")
    assert code == 2
    assert "openhal read needs a read channel of heater." in out
    assert "names temp" in out
    code, out = run("write", "heater")
    assert "names power, mode, enabled, label" in out
    assert "run openhal write heater.power 0 W" in out
    code, out = run("write", "heater.mode")
    assert code == 2
    assert "openhal write needs a value." in out
    assert "limits off | eco | full" in out
    code, out = run("action", "desk-fan")
    assert "openhal action needs an action of desk-fan. desk-fan has no action." in out
    code, out = run("dry-run", "heater.power")
    assert code == 2
    assert "openhal dry-run needs a value." in out


def test_mistyped_ids_and_names_get_the_nearest(cli_hub: SyncHub) -> None:
    code, out = run("devices", "heatr")
    assert code == 1
    assert "There is no device 'heatr'. Did you mean heater?" in out
    code, out = run("read", "nothing-like-it.temp")
    assert "The hub has desk-fan and heater." in out
    code, out = run("action", "heater.pulze")
    assert code == 2
    assert "heater has no action 'pulze'. Did you mean pulse" in out
    code, out = run("write", "heater.powr")
    assert code == 2
    assert "Did you mean power?" in out
    code, out = run("routine", "show", "keep-coll")
    assert code == 1
    assert "There is no routine 'keep-coll'." in out


def test_typos_in_commands_suggest_the_real_command() -> None:
    code, out = run("limts")
    assert code == 2
    assert "Did you mean 'limits'?" in out
    code, out = run("limits", "shwo")
    assert "Did you mean 'show'?" in out
    code, out = run("confirm", "aprove")
    assert "Did you mean 'approve'?" in out


def test_read_and_write_with_pickers(cli_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> None:
    with person_at_terminal(monkeypatch, [Keys("Pick a device", ENTER), Keys("Pick a read channel", ENTER)]) as person:
        code, out = run("read")
    assert code == 0, out
    assert "desk-fan.temperature" in out
    assert "Desk fan, temperature" in person.text
    steps = [Keys("Pick a device", "heater" + ENTER), Keys("Pick a write channel of heater", DOWN + ENTER)]
    steps.append(Keys("Value for heater.mode", "eco" + ENTER))
    with person_at_terminal(monkeypatch, steps) as person:
        code, out = run("write")
    assert code == 0, out
    assert "off | eco | full" in person.text
    assert "done" in out
    with person_at_terminal(
        monkeypatch, [Keys("Value for heater.enabled", "maybe" + ENTER), Keys("Use true", CLEAR + "on" + ENTER)]
    ):
        code, out = run("write", "heater.enabled")
    assert code == 0, out


def test_action_and_dry_run_take_each_argument(cli_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> None:
    clock: FakeClock = cli_hub.hub.kernel.clock  # type: ignore[assignment]
    run("write", "desk-fan.fan_speed", "20 %")
    clock.advance(1)
    run("write", "desk-fan.fan_speed", "40 %")
    run("write", "heater.enabled", "true")
    steps = [Keys("Pick an action of heater", ENTER), Keys("seconds for heater.pulse", "2" + ENTER)]
    steps.append(Keys("needs a number with a unit", " s" + ENTER))
    with person_at_terminal(monkeypatch, steps) as person:
        code, out = run("action", "heater")
    assert code == 0, out
    assert "in s, 1 s to 10 s" in person.text
    steps = [Keys("Pick a device", "heater" + ENTER), Keys("Pick a write channel or an action", "pulse" + ENTER)]
    steps.append(Keys("seconds for heater.pulse", ENTER))
    with person_at_terminal(monkeypatch, steps):
        code, out = run("dry-run")
    assert "seconds" in out
    with person_at_terminal(monkeypatch, [Keys("Value for heater.power", "10 W" + ENTER)]):
        code, out = run("dry-run", "heater.power")
    assert "allowed" in out
