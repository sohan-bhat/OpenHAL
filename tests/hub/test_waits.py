"""wait_until and sample, against a real embedded hub with mock devices and a fake clock."""

from __future__ import annotations

from typing import Any

import pytest

from openhal.hub.hub import Hub
from openhal.hub.runs import MAX_POINTS, RunError, SampleBody, WaitBody, series
from openhal.kernel.commands import Write
from tests.hub.test_runs import CLAUDE
from tests.hub.test_runs import clock as clock
from tests.hub.test_runs import hub as hub
from tests.kernel.conftest import FakeClock


async def test_wait_until_returns_the_readings_that_held(hub: Hub) -> None:
    await hub.kernel.execute(Write(device="warmer", channel="power", value=20, unit="W"), CLAUDE, wire=True)
    held = await hub.runs.wait_until(CLAUDE, WaitBody(condition="warmer.temp > 35 degC", timeout_s=30, interval_s=1))
    assert held["status"] == "held"
    assert held["held"] is True
    assert held["readings"][0]["value"] > 35
    assert held["checks"] >= 2
    assert hub.audit.entries(event="wait_until")[0].status == "held"


async def test_wait_until_times_out_with_the_last_readings(hub: Hub, clock: FakeClock) -> None:
    result = await hub.runs.wait_until(
        CLAUDE, WaitBody(condition="lamp.on == true and lamp.brightness > 50 %", timeout_s=3, interval_s=1)
    )
    assert (result["status"], result["held"], result["result"]) == ("timeout", False, False)
    assert result["checks"] == 4
    assert [reading["channel"] for reading in result["readings"]] == ["brightness", "on"]
    assert result["waited_s"] == 3


async def test_a_wait_never_reads_faster_than_the_poll_floor(hub: Hub) -> None:
    result = await hub.runs.wait_until(CLAUDE, WaitBody(condition="lamp.on == true", timeout_s=1, interval_s=0.01))
    assert result["interval_s"] == hub.config.poll_floor_s


async def test_bad_conditions_name_the_problem(hub: Hub) -> None:
    for condition, status, text in (
        ("lamp.on ==", 400, "doesn't parse"),
        ("true", 400, "names no channel"),
        ("lamp.glow == true", 404, "has no channel 'glow'"),
        ("ghost.on == true", 404, "no device 'ghost'"),
    ):
        with pytest.raises(RunError, match=text) as caught:
            await hub.runs.wait_until(CLAUDE, WaitBody(condition=condition))
        assert caught.value.status == status
    with pytest.raises(RunError, match="longer than the 600 s") as too_long:
        await hub.runs.wait_until(CLAUDE, WaitBody(condition="lamp.on == true", timeout_s=601))
    assert too_long.value.status == 400


async def test_sample_returns_series_with_min_max_and_mean(hub: Hub) -> None:
    result = await hub.runs.sample(
        CLAUDE, SampleBody(targets=["desk-fan.temperature", "lamp.on"], duration_s=2, interval_s=0.5)
    )
    temperature, lamp = result["series"]
    assert (temperature["count"], lamp["count"]) == (5, 5)
    assert temperature["unit"] == "degC"
    assert temperature["min"] <= temperature["mean"] <= temperature["max"]
    assert "mean" not in lamp
    assert lamp["first"] is False
    assert result["status"] == "done"
    assert result["duration_s"] == 2
    reads = [entry for entry in hub.audit.entries(event="read", limit=100) if entry.principal == "agent:claude"]
    assert len(reads) == 10


def test_series_counts_failed_readings() -> None:
    points = [
        {"ok": True, "value": 2, "at": 1.0, "unit": "W"},
        {"ok": False, "error": "no reply", "at": None},
        {"ok": True, "value": 4.0, "at": 3.0, "unit": "W"},
    ]
    found = series("x.y", points)
    assert (found["count"], found["failed"], found["min"], found["max"], found["mean"]) == (3, 1, 2.0, 4.0, 3.0)
    assert found["points"][1] == {"at": None, "ok": False, "value": None, "error": "no reply"}
    assert series("x.y", [])["first"] is None


async def test_sample_limits(hub: Hub) -> None:
    with pytest.raises(RunError, match=f"at most {MAX_POINTS}"):
        await hub.runs.sample(CLAUDE, SampleBody(targets=["lamp.on"], duration_s=500, interval_s=0.2))
    with pytest.raises(RunError, match="longer than"):
        await hub.runs.sample(CLAUDE, SampleBody(targets=["lamp.on"], duration_s=700))
    with pytest.raises(RunError, match="no channel"):
        await hub.runs.sample(CLAUDE, SampleBody(targets=["lamp.glow"], duration_s=1))


async def test_a_value_the_hub_cant_compare_is_unknown(hub: Hub) -> None:
    result = await hub.runs.wait_until(CLAUDE, WaitBody(condition="lamp.frame == true", timeout_s=1))
    assert (result["status"], result["result"]) == ("timeout", None)
    assert result["readings"][0]["value"]["bytes"] == 0


async def test_a_sample_slower_than_its_interval_ends_on_time(
    hub: Hub, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    read = hub.kernel.read

    async def slow_read(*args: Any) -> Any:
        clock.advance(1)
        return await read(*args)

    monkeypatch.setattr(hub.kernel, "read", slow_read)
    result = await hub.runs.sample(CLAUDE, SampleBody(targets=["lamp.on"], duration_s=2.5, interval_s=0.5))
    assert (result["status"], result["series"][0]["count"]) == ("done", 3)
