"""`openhal demo --full` runs the whole system on mocks. docs/demo/e2e.yaml is what it records today.

The full demo runs once per module at simulator speed, and every test checks one part of it.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from openhal.cli.main import app
from openhal.demo import e2e, e2e_trace, plant
from openhal.routines.engine import parse
from openhal.spec import load

ROOT = Path(__file__).resolve().parents[2]
ROUTINES_SPEC = ROOT / "spec" / "2026-10-24" / "routines.md"
SPEED = 80.0


@pytest.fixture(scope="module")
def record() -> dict[str, Any]:
    return asyncio.run(e2e.run(speed=SPEED))


def step(record: dict[str, Any], step_id: str) -> dict[str, Any]:
    return e2e.step(record, step_id)


def test_discovery_finds_the_simulated_board_as_an_openhal_firmware_device(record: dict[str, Any]) -> None:
    found = step(record, "discovery")
    assert found["actor"] == "human:owner"
    assert found["found"]["driver"] == "openhal-firmware"
    assert found["found"]["address"] == "sim:plant-waterer"
    assert found["found"]["identifiers"]["firmware.product"] == "plant-waterer"
    assert found["board_received"] == ["HELLO"]


def test_the_driver_writer_reads_the_board_and_the_sketch(record: dict[str, Any]) -> None:
    writer = step(record, "writer")
    assert writer["args"]["sketch_path"] == "examples/plant-waterer/plant-waterer.ino"
    assert writer["sources"] == ["openhal-firmware identity", "sketch plant-waterer.ino"]
    assert writer["status"] == "interview"
    assert writer["problems"] == []
    draft = writer["draft"]
    assert draft["connect"] == {"openhal-firmware": "sim:plant-waterer"}
    assert draft["actions"]["water"]["args"]["duration"] == {"unit": "s", "min": 1.0, "max": 30.0}
    assert all(action["suggested"] for action in draft["actions"].values())
    assert "confirmed" not in draft
    assert writer["board_received"] == ["HELLO", "DESC"]


def test_the_scripted_person_answers_every_question_and_confirms(record: dict[str, Any]) -> None:
    interview = step(record, "interview")
    assert {item["question"]: item["answer"] for item in interview["answers"]} == e2e.ANSWERS
    assert all(item["prompt"] for item in interview["answers"])
    assert interview["status"] == "ready"
    assert interview["unconfirmed"] == []
    saved = step(record, "save")
    assert saved["saved"] == "plant-waterer.hal.yaml"
    assert saved["writable"] is True
    assert saved["confirmed"]["by"] == "owner"
    assert record["confirmed"] == saved["confirmed"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", saved["confirmed"]["at"])


def test_the_restarted_hub_loads_the_saved_file(record: dict[str, Any]) -> None:
    devices = step(record, "restart")["devices"]
    assert devices == [{"id": "plant-waterer", "writable": True, "connected": True, "hazard": "low"}]


def test_the_agent_reads_soil_moisture_and_drafts_a_disabled_routine(record: dict[str, Any]) -> None:
    read = step(record, "agent-reads")
    assert (read["actor"], read["via"], read["tool"]) == ("agent:claude", "openhal mcp --no-start", "read")
    assert read["result"] == {"value": 31, "unit": "%"}
    drafted = step(record, "agent-drafts")
    assert drafted["arguments"] == {"routine_id": "water-when-dry", "source": e2e.ROUTINE}
    assert drafted["result"]["enabled"] is False
    assert drafted["result"]["drafted_by"] == "agent:claude"
    assert drafted["result"]["triggers"] == ["when plant-waterer.soil_moisture < 40 %"]
    checked = step(record, "agent-dry-runs")["result"]
    assert checked == {
        "ok": True,
        "decisions": [{"step": "steps[0]", "status": "allowed", "target": "action:water"}],
        "problems": [],
    }


def test_the_person_enables_the_routine_and_it_waters_the_plant(record: dict[str, Any]) -> None:
    enabled = step(record, "person-enables")
    assert enabled["actor"] == "human:owner"
    assert enabled["result"] == {"enabled": True, "enabled_by": "human:owner"}
    ran = step(record, "routine-runs")
    assert ran["status"] == "ok"
    assert ran["trigger"] == "when plant-waterer.soil_moisture < 40 %"
    assert ran["commands"] == [{"target": "action:water", "status": "done"}]
    assert ran["board_received"] == ["ACT water duration 20"]
    soil = step(record, "agent-reads-again")["soil_moisture"]
    assert soil == {"before": {"value": 31, "unit": "%"}, "after": {"value": 46, "unit": "%"}}


def test_a_watering_over_the_limit_never_reaches_the_board(record: dict[str, Any]) -> None:
    refused = step(record, "too-long")
    assert refused["actor"] == "agent:claude"
    assert refused["arguments"]["args"] == {"duration": {"value": 120, "unit": "s"}}
    assert refused["result"]["status"] == "blocked"
    assert refused["result"]["code"] == "above_max"
    error = refused["result"]["error"]
    assert (error["code"], error["name"]) == (-32010, "LIMIT_EXCEEDED")
    assert error["data"]["confirmedBy"] == "owner"
    assert refused["board_received"] == []


def test_the_record_agrees_with_the_plant_waterer_mock_file(record: dict[str, Any]) -> None:
    mock = load(plant.example_file())
    duration = mock.actions["water"].args["duration"]
    assert record["file"] == plant.FILE_NAME
    assert record["device"] == mock.device_id == plant.DEVICE
    assert record["limits"]["water_duration"] == {
        "min": {"value": duration.min, "unit": "s"},
        "max": {"value": duration.max, "unit": "s"},
    }
    error = step(record, "too-long")["result"]["error"]
    assert error["message"] == (
        f"water duration 120 s exceeds the limit of {duration.max:g} s "
        f"({plant.FILE_NAME}, confirmed by {record['confirmed']['by']} {record['confirmed']['at']})"
    )
    assert error["data"]["limit"] == {"value": duration.max, "unit": "s"}


def test_the_committed_record_matches_a_fresh_run(record: dict[str, Any]) -> None:
    assert e2e.stable(e2e.read()) == e2e.stable(record), f"Run {e2e.RECORDED_WITH}"


def test_the_only_time_in_the_record_is_the_confirmation_date(record: dict[str, Any]) -> None:
    masked = e2e.dump(e2e.stable(record))
    assert record["confirmed"]["at"] not in masked
    assert not re.search(r"\d{4}-\d{2}-\d{2}T|\d{2}:\d{2}:\d{2}", masked)
    assert masked.count(e2e.DATE_MASK) == 4


def test_the_trace_names_each_part(record: dict[str, Any]) -> None:
    lines = e2e_trace.lines(record)
    assert "found OpenHAL board plant-waterer at sim:plant-waterer, driver openhal-firmware" in "\n".join(lines)
    assert "  soil_moisture rises from 31 % to 46 %" in lines
    assert "← error -32010 LIMIT_EXCEEDED" in lines
    assert "  the board got nothing" in lines


def test_the_spec_shows_the_routine_this_demo_uses() -> None:
    text = ROUTINES_SPEC.read_text(encoding="utf-8")
    blocks = re.findall(r"^```(yaml|python)\n(.*?)^```", text, re.MULTILINE | re.DOTALL)
    yaml_source = next(body for language, body in blocks if language == "yaml")
    assert yaml.safe_load(yaml_source) == yaml.safe_load(e2e.ROUTINE)
    python_source = next(body for language, body in blocks if language == "python")
    _, triggers = parse("water-when-dry", "python", python_source)
    assert [trigger.model_dump() for trigger in triggers] == [{"when": "plant-waterer.soil_moisture < 40 %"}]
    assert "desk-fan" not in text


def test_openhal_demo_full_prints_the_run_and_records_it(tmp_path: Path) -> None:
    target = tmp_path / "e2e.yaml"
    result = CliRunner().invoke(app, ["demo", "--full", "--record", str(target)])
    assert result.exit_code == 0, result.output
    assert "<- error -32010 LIMIT_EXCEEDED" in result.output
    assert "soil_moisture rises from 31 % to 46 %" in result.output
    assert e2e.stable(e2e.read(target)) == e2e.stable(e2e.read())
