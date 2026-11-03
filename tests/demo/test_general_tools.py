"""An agent uses the general MCP tools over a real stdio session, and docs/demo/general-tools.yaml is what it records.

The hub runs on a free loopback port with a mock lamp and a mock warming plate, and `openhal mcp`
runs as a subprocess with an agent token. The session runs once per module.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from openhal.demo import general, rig


@pytest.fixture(scope="module")
def record() -> dict[str, Any]:
    return asyncio.run(general.run())


def step(record: dict[str, Any], step_id: str) -> dict[str, Any]:
    found: dict[str, Any] = next(item for item in record["steps"] if item["id"] == step_id)
    return found


def test_find_names_targets_the_agent_never_saw(record: dict[str, Any]) -> None:
    assert step(record, "find-temperature")["targets"] == ["warmer.temp"]
    assert step(record, "find-writable-percent")["targets"] == ["lamp.brightness"]


def test_the_lamp_blinks_five_times_through_the_kernel(record: dict[str, Any]) -> None:
    blink = step(record, "blink-five-times")
    assert blink["run"]["status"] == "done"
    assert blink["lamp_received"] == [True, False] * 5


def test_the_wait_holds_once_the_plate_passes_the_value(record: dict[str, Any]) -> None:
    waited = step(record, "wait-until-warm")
    assert waited["held"] is True
    assert waited["readings"][0]["value"] > 28
    series = step(record, "sample-the-plate")["series"]
    assert (series["count"], series["unit"]) == (6, "degC")
    assert series["min"] < series["mean"] < series["max"]


def test_a_run_past_a_limit_stops_at_that_step_and_a_stop_ends_a_long_run(record: dict[str, Any]) -> None:
    blocked = step(record, "run-past-a-limit")["run"]
    assert (blocked["status"], blocked["done_steps"], blocked["stop"]["step"]) == ("blocked", 0, 2)
    assert blocked["error"]["name"] == "LIMIT_EXCEEDED"
    assert "confirmed by owner" in blocked["error"]["message"]
    assert step(record, "start-a-long-run")["run"]["status"] == "running"
    assert step(record, "stop-everything")["devices"] == {"lamp": "safe", "warmer": "safe"}
    ended = step(record, "the-long-run-ended")
    assert (ended["run"]["status"], ended["run"]["code"]) == ("cancelled", "stopped")


def test_the_saved_transcript_is_what_the_session_records_today(record: dict[str, Any]) -> None:
    assert general.read() == record, f"Run {general.RECORDED_WITH}"


def test_main_saves_the_transcript(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def recorded() -> dict[str, Any]:
        return {"recorded_with": general.RECORDED_WITH, "steps": []}

    monkeypatch.setattr(general, "run", recorded)
    target = tmp_path / "general.yaml"
    general.main(["--record", str(target)])
    assert general.read(target) == {"recorded_with": general.RECORDED_WITH, "steps": []}
    general.main([])


def test_an_unexpected_outcome_stops_the_session() -> None:
    with pytest.raises(rig.DemoError, match="the lamp did not blink"):
        general._expect(False, "the lamp did not blink")
