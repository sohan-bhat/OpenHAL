"""The CLI against a real embedded hub, with the human-only commands and their terminal checks."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openhal.cli import _common, _tty
from openhal.cli.main import app
from openhal.spec.loader import load, validate_path
from tests.interfaces.conftest import SyncHub
from tests.kernel.conftest import FakeClock

runner = CliRunner()


def run(*args: str, input: str | None = None) -> tuple[int, str]:
    result = runner.invoke(app, list(args), input=input)
    return result.exit_code, result.output


@pytest.fixture
def cli_hub(sync_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> SyncHub:
    monkeypatch.setattr(_common, "TRANSPORT", sync_hub.transport)
    monkeypatch.setenv("OPENHAL_TOKEN", sync_hub.tokens.human)
    return sync_hub


@pytest.fixture
def terminal(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Pretend to be an interactive terminal. Append the phrases the person types."""
    typed: list[str] = []
    monkeypatch.setattr(_tty, "interactive", lambda: True)
    monkeypatch.setattr(_tty, "read_phrase", lambda prompt: typed.pop(0))
    return typed


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_init_sets_up_the_config_folder(isolated_env: Path) -> None:
    code, out = run("init")
    assert code == 0, out
    assert mode(isolated_env) == 0o700
    token_file = isolated_env / "human.token"
    assert mode(token_file) == 0o600
    assert token_file.read_text().startswith("ohal_")
    sample = isolated_env / "devices" / "plant-waterer.hal.yaml"
    report = validate_path(sample)
    assert report.ok, report.problems
    assert report.file is not None
    assert not report.file.writable, "init must not confirm limits on the person's behalf"
    assert "openhal token create --agent" in out
    first = token_file.read_text()
    code, out = run("init")
    assert "kept" in out
    assert token_file.read_text() == first
    run("init", "--new-token")
    assert token_file.read_text() != first


def test_file_confirm_binds_the_limits(isolated_env: Path, terminal: list[str]) -> None:
    run("init")
    sample = isolated_env / "devices" / "plant-waterer.hal.yaml"
    terminal.append("confirm")
    code, out = run("file", "confirm", str(sample), "--by", "sohan")
    assert code == 0, out
    confirmed = load(sample)
    assert confirmed.writable
    assert confirmed.confirmed is not None
    assert confirmed.confirmed.sha256 == confirmed.limits_sha256()
    terminal.append("confirm")
    run("file", "confirm", str(sample))
    assert sample.read_text().count("confirmed:") == 1
    sample.write_text(sample.read_text().replace("max: 30", "max: 25"))
    assert not load(sample).writable, "a changed limit unconfirms the file"


def test_human_commands_need_a_terminal(isolated_env: Path, cli_hub: SyncHub) -> None:
    run("stop")
    code, out = run("unlock")
    assert code == 1
    assert "interactive terminal" in out
    code, out = run("unlock", "--phrase", "unlock")
    assert code == 1
    assert "--phrase can't be used" in out
    sample = isolated_env / "devices" / "x.hal.yaml"
    run("init")
    code, out = run("file", "confirm", str(isolated_env / "devices" / "plant-waterer.hal.yaml"))
    assert code == 1
    assert not sample.exists()


def test_phrase_flag_when_tty_is_off(isolated_env: Path, cli_hub: SyncHub) -> None:
    isolated_env.mkdir(parents=True, exist_ok=True)
    (isolated_env / "config.yaml").write_text("confirm: { require_tty: false }\n")
    run("stop")
    code, out = run("unlock", "--phrase", "nope")
    assert code == 1
    assert "did not match" in out
    code, out = run("unlock", "--phrase", "unlock")
    assert code == 0, out
    assert "unlocked" in out


def test_status_devices_read_write(cli_hub: SyncHub) -> None:
    code, out = run("status")
    assert code == 0, out
    assert "you are human:owner" in out
    assert "devices 2 of 2 connected" in out
    code, out = run("status", "--json")
    assert json.loads(out)["devices"] == 2
    code, out = run("devices")
    assert "desk-fan" in out
    assert "heater" in out
    code, out = run("devices", "heater")
    assert "pulse" in out
    assert "interlock" in out
    assert json.loads(run("devices", "--json")[1])[0]["id"] in ("desk-fan", "heater")
    code, out = run("read", "desk-fan.temperature")
    assert code == 0
    assert "degC" in out
    code, out = run("read", "desk-fan.temperature", "heater.temp", "--json")
    assert len(json.loads(out)) == 2
    code, out = run("write", "desk-fan.fan_speed", "150", "%")
    assert code == 1
    assert "above_max" in out
    code, out = run("write", "desk-fan.fan_speed", "20 %")
    assert code == 0
    assert "done" in out
    code, out = run("write", "heater.enabled", "on", "--json")
    assert json.loads(out)["status"] == "done"
    code, out = run("write", "desk-fan", "1 %")
    assert code == 2
    assert "device.channel" in out


def test_actions_dry_run_and_stop(cli_hub: SyncHub, tmp_path: Path) -> None:
    clock: FakeClock = cli_hub.hub.kernel.clock  # type: ignore[assignment]
    run("write", "desk-fan.fan_speed", "20 %")
    clock.advance(1)
    run("write", "desk-fan.fan_speed", "40 %")
    run("write", "heater.enabled", "true")
    code, out = run("action", "heater.pulse", "seconds=2 s")
    assert code == 0, out
    code, out = run("action", "heater.nope")
    assert code == 2
    assert "no action" in out
    code, out = run("dry-run", "desk-fan.fan_speed", "500 %")
    assert code == 1
    assert "above_max" in out
    code, out = run("dry-run", "heater.pulse", "seconds=3 s")
    assert "allowed" in out
    plan = tmp_path / "plan.yaml"
    plan.write_text("- { device: desk-fan, channel: fan_speed, value: 40 % }\n- { device: heater, action: purge }\n")
    code, out = run("dry-run", "--file", str(plan), "--json")
    assert [item["status"] for item in json.loads(out)] == ["allowed", "allowed"]
    code, out = run("dry-run", "desk-fan.nothing", "1 %")
    assert "no control channel or action" in out
    code, out = run("stop", "--reason", "cli test")
    assert code == 0, out
    assert "safe" in out
    assert "openhal unlock" in out
    code, out = run("status")
    assert "stopped" in out


def test_confirm_queue(cli_hub: SyncHub, monkeypatch: pytest.MonkeyPatch, terminal: list[str]) -> None:
    clock: FakeClock = cli_hub.hub.kernel.clock  # type: ignore[assignment]
    monkeypatch.setenv("OPENHAL_TOKEN", cli_hub.tokens.medium)
    run("write", "desk-fan.fan_speed", "20 %")
    clock.advance(1)
    run("write", "desk-fan.fan_speed", "40 %")
    code, out = run("action", "heater.purge", "--json")
    request_id = json.loads(out)["request_id"]
    terminal.append("approve")
    code, out = run("confirm", "approve", request_id)
    assert code == 1
    assert "Only a human" in out, "the hub refuses an agent even when the phrase is typed"
    second = json.loads(run("action", "heater.purge", "--json")[1])["request_id"]

    monkeypatch.setenv("OPENHAL_TOKEN", cli_hub.tokens.human)
    code, out = run("confirm", "list")
    assert request_id in out
    code, out = run("confirm", "show", request_id)
    assert "heater.purge" in out
    terminal.append("approve")
    code, out = run("confirm", "approve", request_id)
    assert code == 0, out
    assert "done" in out
    code, out = run("confirm", "approve", request_id)
    assert code == 1
    assert "nothing to approve" in out
    code, out = run("confirm", "reject", second, "--reason", "not now")
    assert "rejected" in out
    code, out = run("confirm", "list", "--all", "--json")
    assert {item["status"] for item in json.loads(out)} == {"done", "rejected"}


def test_wrong_phrase_cancels(cli_hub: SyncHub, terminal: list[str]) -> None:
    run("stop")
    terminal.append("yes")
    code, out = run("unlock")
    assert code == 1
    assert "cancelled" in out
    terminal.append("unlock")
    code, out = run("unlock")
    assert code == 0, out
    code, out = run("unlock")
    assert "not stopped" in out


def test_log_and_verify(cli_hub: SyncHub) -> None:
    run("write", "desk-fan.fan_speed", "150 %")
    code, out = run("log", "--status", "blocked")
    assert code == 0
    assert "blocked" in out
    code, out = run("log", "--json", "--limit", "3")
    assert len(json.loads(out)) == 3
    code, out = run("log", "--verify")
    assert code == 0
    assert "intact" in out
    code, out = run("log", "--device", "nobody")
    assert "No entries" in out


def test_errors_have_exit_codes(monkeypatch: pytest.MonkeyPatch, cli_hub: SyncHub) -> None:
    monkeypatch.setenv("OPENHAL_TOKEN", "ohal_wrong")
    code, out = run("status")
    assert code == 4
    assert "did not accept" in out
    monkeypatch.setattr(_common, "TRANSPORT", None)
    code, out = run("--url", "http://127.0.0.1:9", "status")
    assert code == 3
    assert "Start it with openhald" in out
    code, out = run("devices", "nope")
    assert code in (1, 3)


def test_pair_prints_a_code(cli_hub: SyncHub, monkeypatch: pytest.MonkeyPatch) -> None:
    code, out = run("pair")
    assert code == 0, out
    assert out.strip().splitlines()[-1].isdigit()
    monkeypatch.setenv("OPENHAL_TOKEN", cli_hub.tokens.agent)
    code, out = run("pair")
    assert code == 1
    assert "Only a human" in out


def test_token_file_option(cli_hub: SyncHub, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENHAL_TOKEN")
    file = tmp_path / "agent.token"
    file.write_text(cli_hub.tokens.reader + "\n")
    code, out = run("--token-file", str(file), "status")
    assert "agent:viewer" in out
    code, out = run("--token-file", str(tmp_path / "missing"), "status")
    assert code == 4
