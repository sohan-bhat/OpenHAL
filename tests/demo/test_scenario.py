"""The canonical scenario. docs/demo/scenario.yaml must be exactly what a real hub answers today."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from openhal import images
from openhal.cli import log_cmd
from openhal.cli.main import app
from openhal.demo import scenario, trace
from openhal.demo.scenario import exchange
from openhal.drivers.moonraker.simulator import AMBIENT_C, COOLING_S
from openhal.spec import load

RECORD = scenario.read()
STORY = ["first-layer", "bed-warmer", "nozzle-too-hot", "come-loose", "paused", "cancel-waits", "owner-approves"]


async def test_the_recorded_scenario_is_what_the_hub_answers() -> None:
    fresh = yaml.safe_load(scenario.dump(await scenario.run()))
    assert fresh == RECORD, "Run uv run openhal demo --record docs/demo/scenario.yaml"


def test_the_story_runs_in_order() -> None:
    assert [entry["id"] for entry in RECORD["exchanges"]] == STORY
    methods = [entry["request"]["method"] for entry in RECORD["exchanges"]]
    assert methods == [
        "hal/read",
        "hal/write",
        "hal/write",
        "hal/read",
        "hal/action",
        "hal/action",
        "hal/confirmations/approve",
    ]
    assert RECORD["principals"] == {"agent": "agent:claude", "person": "human:owner"}
    assert [entry["by"] for entry in RECORD["exchanges"]] == ["agent:claude"] * 6 + ["human:owner"]


def test_every_exchange_has_a_reason_line() -> None:
    assert all(entry["before"] == scenario.BEFORE[entry["id"]] for entry in RECORD["exchanges"])
    assert exchange(RECORD, "nozzle-too-hot")["before"] == "a hotter nozzle might help the corner stick"


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


def test_the_owner_approves_the_cancel_over_the_protocol() -> None:
    approved = exchange(RECORD, "owner-approves")
    assert approved["request"] == {"method": "hal/confirmations/approve", "params": {"requestId": scenario.REQUEST_ID}}
    assert approved["result"] == {
        "status": "done",
        "device": "printer",
        "target": "action:cancel",
        "value": {},
        "unit": None,
    }
    assert approved["masked"] == ["requestId"]
    assert approved["kernel"]["approved_by"] == "human:owner"
    assert approved["kernel"]["checks"] == dict.fromkeys(scenario.CHECKS, "ok")
    assert approved["kernel"]["grant"] == "issued"
    assert approved["printer_received"] == ["printer.print.cancel"]
    assert approved["printer"]["state"] == "cancelled"


def test_the_kernel_facts_follow_each_answer() -> None:
    kernel = {entry["id"]: entry["kernel"] for entry in RECORD["exchanges"]}
    for name in ("first-layer", "come-loose"):
        assert kernel[name]["checks"] == {"channel": "ok", "device": "ok"}
        assert kernel[name]["grant"] == "not needed"
    for name in ("bed-warmer", "paused"):
        assert kernel[name]["checks"] == {**dict.fromkeys(scenario.CHECKS, "ok"), "confirmation": "not needed"}
        assert kernel[name]["grant"] == "issued"
    assert kernel["nozzle-too-hot"]["checks"] == {"units": "ok", "range": "blocked"}
    assert kernel["nozzle-too-hot"]["grant"] == "none"
    assert kernel["cancel-waits"]["checks"] == {**dict.fromkeys(scenario.CHECKS, "ok"), "confirmation": "required"}
    assert kernel["cancel-waits"]["grant"] == "none"
    logged = [seq for name in STORY for seq in kernel[name]["logged"]]
    assert logged == sorted(logged) == [entry["seq"] for entry in reversed(RECORD["audit"]["entries"])]


def test_the_printer_receives_each_granted_command() -> None:
    received = {entry["id"]: entry.get("printer_received") for entry in RECORD["exchanges"]}
    assert received == {
        "first-layer": None,
        "bed-warmer": ["SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET=70.0"],
        "nozzle-too-hot": [],
        "come-loose": None,
        "paused": ["printer.print.pause"],
        "cancel-waits": [],
        "owner-approves": ["printer.print.cancel"],
    }


def test_the_printer_panel_shows_the_nozzle_at_each_step() -> None:
    nozzle = {"value": 215, "unit": "degC"}
    states = [entry["printer"]["state"] for entry in RECORD["exchanges"]]
    assert states == ["printing"] * 4 + ["paused", "paused", "cancelled"]
    for entry in RECORD["exchanges"]:
        assert set(entry["printer"]) == set(scenario.PANEL)
        assert entry["printer"]["extruder_temp"] == nozzle, "the nozzle starts to cool once the cancel has run"
    held = RECORD["exchanges"][:-1]
    assert all(entry["printer"]["extruder_target"] == nozzle for entry in held)
    assert [entry["printer"]["bed_target"]["value"] for entry in held] == [60] + [70] * 5


def test_the_nozzle_cools_after_the_owner_approves_the_cancel() -> None:
    approved = exchange(RECORD, "owner-approves")
    cooling = approved["cooling"]
    assert [item["after"] for item in cooling] == [{"value": seconds, "unit": "s"} for seconds in scenario.COOLED_FOR_S]
    nozzle = [approved["printer"]["extruder_temp"]["value"]]
    for item in cooling:
        assert set(item["printer"]) == set(scenario.PANEL)
        assert item["printer"]["state"] == "cancelled"
        assert item["printer"]["extruder_temp"]["unit"] == "degC"
        nozzle.append(item["printer"]["extruder_temp"]["value"])
        cooled = AMBIENT_C + (scenario.NOZZLE_PRINTING - AMBIENT_C) * math.exp(
            -item["after"]["value"] / COOLING_S["extruder"]
        )
        assert nozzle[-1] == pytest.approx(cooled, abs=0.01)
    assert nozzle == sorted(set(nozzle), reverse=True)
    assert nozzle[0] == scenario.NOZZLE_PRINTING > nozzle[-1] > AMBIENT_C


def test_the_hub_reads_the_targets_again_only_when_the_cancel_lists_them() -> None:
    """Without `effects` on the cancel, the hub shows the targets it read last, though Klipper set them to 0."""
    file = load(scenario.example(scenario.FOLDER, scenario.FILES[scenario.DEVICE]))
    read_again = set(file.actions["cancel"].effects)
    held = exchange(RECORD, "cancel-waits")["printer"]
    approved = exchange(RECORD, "owner-approves")
    for panel in [approved["printer"], *(item["printer"] for item in approved["cooling"])]:
        for channel in ("extruder_target", "bed_target"):
            assert panel[channel] == ({"value": 0, "unit": "degC"} if channel in read_again else held[channel])


def test_the_audit_log_holds_the_story() -> None:
    audit = RECORD["audit"]
    assert audit["request"] == {"method": "hal/audit/query", "params": {}}
    assert audit["counts"] == {"requests": 6, "refused": 1, "confirmed_by_a_person": 1}
    assert audit["printed_with"] == f"uv run openhal log -n {len(audit['entries'])}"
    events = [(entry["event"], entry["who"], entry["status"]) for entry in audit["entries"]]
    assert events[:3] == [
        ("action", "agent:claude", "done"),
        ("confirm", "human:owner", "done"),
        ("action", "agent:claude", "pending"),
    ]
    rows = [{**entry, "seq": str(entry["seq"]), "time": scenario.TIME} for entry in audit["entries"]]
    assert audit["lines"] == log_cmd.lines(rows)
    assert audit["lines"][0].split() == list(log_cmd.COLUMNS)
    assert audit["masked"] == ["time"]
    assert trace.counts(RECORD) == "6 requests, 1 refused, 1 confirmed by a person"


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
    assert sum(line.startswith("→ hal/") for line in lines) == 7
    assert "← error -32010 LIMIT_EXCEEDED" in lines
    assert "  extruder_target 300 degC exceeds the limit of 260 degC" in lines
    assert '                "width": 640, "height": 480, "data": "…" } }' in lines
    assert '← result      { "status": "pending", "requestId": "REQUEST_ID",' in lines
    assert '→ hal/confirmations/approve { "requestId": "REQUEST_ID" }' in lines
    assert all(len(line) <= trace.WIDTH for line in lines)
    assert "# the print has come loose" in lines
    assert "# a hotter nozzle might help the corner stick" in lines
    assert lines[-3:] == ["# the owner approves the cancel", lines[-2], '← result      { "status": "done" }']


def test_the_outcome_names_the_recorded_numbers() -> None:
    assert trace.outcome(RECORD) == (
        "You'll see the agent raise the bed target from 60 °C to 70 °C, have a request for a nozzle temperature of "
        "300 °C refused at the nozzle limit of 260 °C and pause the print when the camera shows the print has come "
        "loose. "
        "The owner then approves the cancel, and the printer's state becomes cancelled."
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
    assert "-> hal/confirmations/approve" in result.output
    assert "REQUEST_ID" not in result.output, "the live demo shows the hub's real request id"
    assert "The demo hub's audit log, newest first" in result.output
    assert "6 requests, 1 refused, 1 confirmed by a person." in result.output
    assert "The camera frames are line drawings." in result.output
    assert scenario.read(target) == RECORD
