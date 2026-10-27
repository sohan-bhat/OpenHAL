"""The canonical scenario. docs/demo/scenario.yaml must be exactly what a real hub answers today."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from openhal import images
from openhal.cli.main import app
from openhal.demo import scenario, trace
from openhal.demo.scenario import exchange
from openhal.spec import load

RECORD = scenario.read()


async def test_the_recorded_scenario_is_what_the_hub_answers() -> None:
    fresh = yaml.safe_load(scenario.dump(await scenario.run()))
    assert fresh == RECORD, "Run uv run openhal demo --record docs/demo/scenario.yaml"


def test_the_story_runs_in_order() -> None:
    assert [entry["id"] for entry in RECORD["exchanges"]] == [
        "first-layer",
        "bed-warmer",
        "nozzle-too-hot",
        "come-loose",
        "paused",
        "cancel-waits",
    ]
    methods = [entry["request"]["method"] for entry in RECORD["exchanges"]]
    assert methods == ["hal/read", "hal/write", "hal/write", "hal/read", "hal/action", "hal/action"]


def test_the_camera_reads_carry_the_frames_without_their_pixels() -> None:
    for name, frame in (("first-layer", "first-layer"), ("come-loose", "come-loose")):
        entry = exchange(RECORD, name)
        data = scenario.frame(frame)
        assert entry["frame"] == f"examples/print-babysitter/frames/{frame}.jpg"
        assert entry["result"]["value"] == images.describe(data)
        assert "data" not in entry["result"]["value"]
        assert "at" not in entry["result"]


def test_the_kernel_moments() -> None:
    warmer = exchange(RECORD, "bed-warmer")
    assert warmer["result"]["status"] == "done"
    assert warmer["bed_target"] == {"before": {"value": 60, "unit": "degC"}, "after": {"value": 70, "unit": "degC"}}
    refused = exchange(RECORD, "nozzle-too-hot")["error"]
    assert (refused["code"], refused["data"]["name"]) == (-32010, "LIMIT_EXCEEDED")
    assert refused["message"] == (
        "extruder_target 300 degC exceeds the limit of 260 degC (printer.hal.yaml, confirmed by owner 2026-10-24)"
    )
    assert exchange(RECORD, "paused")["result"]["status"] == "done"
    waiting = exchange(RECORD, "cancel-waits")
    assert waiting["result"] == {"status": "pending", "requestId": scenario.REQUEST_ID, "expiresInS": 300}
    assert waiting["masked"] == ["requestId"]


def test_the_devices_are_the_example_files() -> None:
    printer, camera = RECORD["devices"]
    file = load(scenario.example(scenario.FOLDER, "printer.hal.yaml"))
    assert (printer["id"], printer["driver"], printer["hazard"], printer["file"]) == (
        "printer",
        "moonraker",
        "medium",
        "printer.hal.yaml",
    )
    assert printer["confirmed"] == {"by": "owner", "at": "2026-10-24"}
    for name, limits in printer["limits"].items():
        spec = file.write[name]
        assert (limits["min"]["value"], limits["max"]["value"]) == (spec.min, spec.max)
        assert limits["max_change_per_s"]["value"] == spec.max_change_per_s
    assert printer["actions"]["cancel"] == {"confirm": "confirm-each-time"}
    assert (camera["id"], camera["driver"], camera["read"]) == ("printer-cam", "http", ["frame"])


def test_the_trace_shows_every_exchange() -> None:
    lines = trace.lines(RECORD)
    assert sum(line.startswith("→ hal/") for line in lines) == 6
    assert "← error -32010 LIMIT_EXCEEDED" in lines
    assert "  extruder_target 300 degC exceeds the limit of 260 degC" in lines
    assert '                "width": 640, "height": 480, "data": "…" } }' in lines
    assert '← result      { "status": "pending", "requestId": "REQUEST_ID",' in lines
    assert all(len(line) <= trace.WIDTH for line in lines)
    assert "# the print has come loose" in lines


def test_the_outcome_names_the_recorded_numbers() -> None:
    assert trace.outcome(RECORD) == (
        "You'll see the agent warm the bed from 60 °C to 70 °C, have a 300 °C nozzle refused at the 260 °C limit, "
        "pause the print when it comes loose and wait for a person to approve the cancel."
    )


@pytest.mark.parametrize("name", scenario.FRAMES)
def test_the_frames_are_the_drawings(name: str) -> None:
    cv2 = pytest.importorskip("cv2")
    numpy = pytest.importorskip("numpy")
    from openhal.demo import frames

    shown = cv2.imdecode(numpy.frombuffer(scenario.frame(name), dtype=numpy.uint8), cv2.IMREAD_COLOR)
    drawn = frames.draw(name)
    assert shown.shape == (frames.HEIGHT, frames.WIDTH, 3)
    assert float(numpy.abs(shown.astype(int) - drawn.astype(int)).mean()) < 1.5, "Run python -m openhal.demo.frames"


def test_openhal_demo_prints_the_trace_and_can_record_it(tmp_path: Path) -> None:
    target = tmp_path / "scenario.yaml"
    result = CliRunner().invoke(app, ["demo", "--record", str(target)])
    assert result.exit_code == 0, result.output
    assert "<- error -32010 LIMIT_EXCEEDED" in result.output
    assert '"status": "pending"' in result.output
    assert "REQUEST_ID" not in result.output, "the live demo shows the hub's real request id"
    assert "The camera frames are line drawings." in result.output
    assert scenario.read(target) == RECORD
