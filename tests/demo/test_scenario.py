"""The canonical scenario. docs/demo/scenario.yaml must be exactly what a real hub answers today."""

from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from openhal.cli.main import app
from openhal.demo import scenario, trace


async def test_the_recorded_scenario_is_what_the_hub_answers() -> None:
    recorded = scenario.read()
    fresh = yaml.safe_load(scenario.dump(await scenario.run(speed=80.0)))
    assert fresh == recorded, "Run uv run openhal demo --record docs/demo/scenario.yaml"


def test_the_reasons_cite_the_limit_and_who_confirmed_it() -> None:
    too_long, empty, watered = scenario.read()["exchanges"]
    assert too_long["error"]["data"]["name"] == "LIMIT_EXCEEDED"
    assert too_long["error"]["message"] == (
        "water duration 120 s exceeds the limit of 30 s (plant-waterer.hal.yaml, confirmed by owner 2026-10-24)"
    )
    assert empty["error"]["data"]["name"] == "INTERLOCK_BLOCKED"
    assert empty["error"]["message"] == "pump can't run while tank is empty"
    assert watered["result"]["status"] == "done"
    assert watered["soil_moisture"] == {"before": {"value": 31, "unit": "%"}, "after": {"value": 46, "unit": "%"}}


def test_the_trace_shows_three_exchanges() -> None:
    lines = trace.lines(scenario.read())
    assert sum(line.startswith("→ hal/action") for line in lines) == 3
    assert "← error -32010 LIMIT_EXCEEDED" in lines
    assert "← error -32012 INTERLOCK_BLOCKED" in lines
    assert "← hal/value   soil_moisture rises from 31 % to 46 %" in lines


def test_openhal_demo_prints_the_trace_and_can_record_it(tmp_path: Path) -> None:
    target = tmp_path / "scenario.yaml"
    result = CliRunner().invoke(app, ["demo", "--record", str(target)])
    assert result.exit_code == 0, result.output
    assert "pump can't run while tank is empty" in result.output
    assert scenario.read(target) == scenario.read()
