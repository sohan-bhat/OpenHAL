"""`openhal start` runs the hub, and `openhald` stays an alias nobody is shown (ADR 0018)."""

from __future__ import annotations

import sys

import pytest
from typer.testing import CliRunner

from openhal.cli.main import app
from openhal.hub import daemon

runner = CliRunner()


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str | None, int | None, bool]]:
    calls: list[tuple[str | None, int | None, bool]] = []

    def run(host: str | None = None, port: int | None = None, *, verbose: bool = False) -> None:
        calls.append((host, port, verbose))

    monkeypatch.setattr(daemon, "run", run)
    return calls


def test_openhal_start_runs_the_hub_with_the_same_options(started: list[tuple[str | None, int | None, bool]]) -> None:
    result = runner.invoke(app, ["start"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["start", "--host", "127.0.0.1", "--port", "4441", "--verbose"])
    assert result.exit_code == 0, result.output
    assert started == [(None, None, False), ("127.0.0.1", 4441, True)]


def test_the_old_daemon_name_still_starts_the_same_hub(
    started: list[tuple[str | None, int | None, bool]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["openhald", "--port", "4442"])
    daemon.main()
    assert started == [(None, 4442, False)]


def test_help_names_one_command() -> None:
    result = runner.invoke(app, ["--help"])
    assert "start" in result.output
    assert "openhald" not in result.output
    result = runner.invoke(app, ["start", "--help"])
    assert "Run OpenHAL in the foreground" in result.output
