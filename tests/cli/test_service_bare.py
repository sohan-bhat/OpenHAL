"""A bare `openhal service` shows the state and the next step, and exits 0 whatever the state."""

from __future__ import annotations

from typer.testing import CliRunner

from openhal.cli.main import app
from tests.cli.conftest import Machine

runner = CliRunner()


def test_a_bare_service_shows_the_state_and_the_next_step(machine: Machine) -> None:
    result = runner.invoke(app, ["service"])
    assert result.exit_code == 0, result.output
    assert "not installed" in result.output
    assert "Start OpenHAL with openhal service install." in result.output
    runner.invoke(app, ["service", "install"])
    machine.runner.answers["launchctl print"] = (0, "gui/501/org.openhal.hub = {\n\tstate = running\n\tpid = 4242\n}")
    result = runner.invoke(app, ["service"])
    assert result.exit_code == 0, result.output
    assert "running, pid 4242" in result.output
