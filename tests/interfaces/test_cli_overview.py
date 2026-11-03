"""A bare `openhal` in each state, and the bare groups that work without a hub.

Every run points at the in-process hub or at a loopback port nothing listens on, so no test reaches
a hub that runs on this machine outside the test.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openhal.cli import _common, _overview
from openhal.cli.init_cmd import CONFIG_TEMPLATE
from openhal.cli.main import app
from tests.interfaces.conftest import SyncHub
from tests.kernel.conftest import FakeClock
from tests.terminal import ENTER, Keys, person_at_terminal

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="pseudo-terminals are POSIX only")

runner = CliRunner()
NOWHERE = "http://127.0.0.1:9"


def run(*args: str) -> tuple[int, str]:
    """The exit code and the output with every run of spaces as one, so table columns read as words."""
    result = runner.invoke(app, list(args))
    return result.exit_code, " ".join(result.output.split())


@pytest.fixture
def cli_hub(sync_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> SyncHub:
    monkeypatch.setattr(_common, "TRANSPORT", sync_hub.transport)
    monkeypatch.setenv("OPENHAL_TOKEN", sync_hub.tokens.human)
    return sync_hub


def test_nothing_set_up_points_at_init(isolated_env: Path) -> None:
    code, out = run("--url", NOWHERE)
    assert code == 0, out
    assert "is not set up yet" in out
    assert f"not running at {NOWHERE}" in out
    assert "openhal init" in out
    assert "openhal demo" in out
    assert "openhal --help lists every command." in out
    assert "Usage" not in out


def test_set_up_with_no_hub_points_at_start(isolated_env: Path) -> None:
    run("init")
    code, out = run("--url", NOWHERE)
    assert code == 0, out
    assert "is set up" in out
    assert "openhal start" in out
    assert "openhal service install" in out
    assert "openhal init" not in out


def test_a_running_hub_shows_devices_and_the_next_commands(cli_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> None:
    code, out = run()
    assert code == 0, out
    assert "running at http://127.0.0.1:7420 as human:owner" in out
    assert "desk-fan and heater connected" in out
    assert "none held for a person" in out
    assert "openhal devices" in out
    assert "openhal limits" in out
    run("stop")
    code, out = run()
    assert "stopped" in out
    assert "openhal unlock" in out


def test_a_held_request_comes_first(cli_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> None:
    clock: FakeClock = cli_hub.hub.kernel.clock  # type: ignore[assignment]
    monkeypatch.setenv("OPENHAL_TOKEN", cli_hub.tokens.medium)
    run("write", "desk-fan.fan_speed", "20 %")
    clock.advance(1)
    run("write", "desk-fan.fan_speed", "40 %")
    run("action", "heater.purge")
    monkeypatch.setenv("OPENHAL_TOKEN", cli_hub.tokens.human)
    out = run()[1]
    assert "1 request held for a person" in out
    assert out.index("openhal confirm") < out.index("openhal devices")


def test_a_token_problem_points_at_doctor(
    cli_hub: SyncHub, isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_env.mkdir(parents=True, exist_ok=True)
    (isolated_env / "config.yaml").write_text(CONFIG_TEMPLATE)
    monkeypatch.setenv("OPENHAL_TOKEN", "ohal_wrong")
    code, out = run()
    assert code == 0, out
    assert "openhal doctor" in out


def test_the_steps_for_each_state() -> None:
    from openhal.client.models import DeviceSummary, HubStatus, Principal

    you = Principal(kind="human", name="owner", scope="control_medium")
    status = HubStatus(
        product="OpenHAL",
        version="0",
        spec="0.1",
        stopped=False,
        devices=0,
        connected=0,
        pending_confirmations=0,
        you=you,
    )
    empty = _overview.Standing(set_up=True, url="u", status=status)
    assert [command for command, _ in _overview.steps(empty)][:2] == ["openhal discover", "openhal library"]
    lamp = DeviceSummary(id="desk-lamp", name="Desk lamp", driver="mock", hazard="low", writable=False, connected=False)
    found = _overview.Standing(set_up=True, url="u", status=status, devices=[lamp])
    assert _overview.steps(found)[0] == ("openhal file confirm", "answer each limit of desk-lamp, read-only until then")
    assert "desk-lamp [yellow]not connected[/yellow]" in dict(_overview._rows(found))["devices"]
    many = [lamp.model_copy(update={"id": f"lamp-{n}", "connected": True}) for n in range(6)]
    assert _overview._names(many) == "lamp-0, lamp-1, lamp-2, lamp-3 and 2 more"
    assert _overview.folder(Path.home() / ".openhal") == "~/.openhal"
    assert _overview.folder(Path("/opt/openhal")) == "/opt/openhal"


def test_bare_file_library_and_driver(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code, out = run("file")
    assert code == 0, out
    assert "No device files in" in out
    run("init")
    code, out = run("file")
    assert "plant-waterer.hal.yaml" in out
    assert "Answer each limit of a read-only file with openhal file confirm" in out
    code, out = run("file", "validate")
    assert "1 valid, 0 invalid." in out
    code, out = run("file", "confirm")
    assert code == 2
    assert "files plant-waterer.hal.yaml" in out
    assert f"run openhal file confirm {isolated_env / 'devices' / 'plant-waterer.hal.yaml'}" in out
    code, out = run("library")
    assert code == 0, out
    assert "Add one with openhal library add" in out
    assert len(json.loads(run("library", "--json")[1])) > 10
    code, out = run("library", "add")
    assert code == 2
    assert "openhal library list lists every one" in out
    with person_at_terminal(monkeypatch, [Keys("Pick a library name", "rigol-dp832" + ENTER)]):
        code, out = run("library", "show")
    assert code == 0, out
    assert "rigol-dp832" in out
    code, out = run("driver")
    assert code == 0, out
    assert "Run the conformance suite on a driver with openhal driver test mock" in out
    assert any(item["name"] == "mock" for item in json.loads(run("driver", "--json")[1]))
    code, out = run("driver", "test")
    assert code == 2
    assert "drivers " in out
    code, out = run("driver", "test", "mok")
    assert code == 2
    assert "Did you mean mock?" in out
    code, out = run("driver", "new")
    assert code == 2
    assert "run openhal driver new acme-pump" in out


def test_file_confirm_picks_a_file_and_takes_the_phrase(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run("init")
    with person_at_terminal(monkeypatch, [Keys("Pick a device file", ENTER), "confirm"]) as person:
        code, out = run("file", "confirm", "--by", "owner")
    assert "plant-waterer.hal.yaml  read-only" in person.text
    assert code == 0, out
    assert "confirmed" in out


def test_bare_writer_lists_unknown_devices(cli_hub: SyncHub) -> None:
    code, out = run("writer")
    assert code == 0, out
    assert "No unknown devices." in out
    assert run("writer", "--json")[1].strip() == "[]"
    code, out = run("writer", "finish")
    assert code == 2
    assert "openhal writer finish needs a session id. openhal writer start prints the id of a new session." in out
