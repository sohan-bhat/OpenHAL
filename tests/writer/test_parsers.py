"""Static sketch parsing and manual extraction. Nothing here runs or sends anything."""

from __future__ import annotations

from pathlib import Path

import pytest

from openhal.spec.loader import from_data
from openhal.writer import manual, sketch

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).resolve().parents[2] / "firmware" / "arduino" / "OpenHAL" / "examples"


def test_text_protocol_sketch() -> None:
    findings = sketch.parse((FIXTURES / "fan_text.ino").read_text())
    assert findings.baud == 115200
    commands = {command.text: command for command in findings.commands}
    assert set(commands) == {"TEMP?", "FAN ", "BEEP"}
    assert commands["FAN "].takes_value
    assert commands["FAN "].ranges == [(0.0, 255.0)]
    assert commands["TEMP?"].replies == ["T="]
    assert findings.pwm == ["9"]
    assert findings.analog_inputs == ["A0"]


def test_text_protocol_draft_is_read_only_until_confirmed() -> None:
    draft = sketch.draft(sketch.parse((FIXTURES / "fan_text.ino").read_text()))
    file = from_data(draft)
    assert file.connect.driver == "serial"
    assert file.connect.params["baud"] == 115200
    assert file.read["temp"].map == {"query": "TEMP?", "parse": r"^T=\s*(?P<value>[-0-9.]+)$"}
    assert file.write["fan"].suggested
    assert (file.write["fan"].min, file.write["fan"].max) == (0.0, 255.0)
    assert file.actions["beep"].confirm == "confirm"
    assert not file.writable
    assert file.provenance.source == "sketch"


@pytest.mark.parametrize("example", ["DeskFan", "LedStrip", "ServoArm", "SoilPump", "PlantWaterer"])
def test_openhal_library_sketches_describe_themselves_in_code(example: str) -> None:
    findings = sketch.parse((EXAMPLES / example / f"{example}.ino").read_text())
    assert findings.uses_openhal_library
    assert not findings.commands, "OpenHAL sketches are described by their declarations, not guessed commands"
    file = from_data(sketch.draft(findings))
    assert file.connect.driver == "openhal-firmware"
    assert file.write or file.actions
    assert all(entry.suggested for entry in [*file.write.values(), *file.actions.values()])
    assert not file.writable


def test_plant_waterer_sketch_offers_actions_and_hides_the_pump() -> None:
    draft = sketch.draft(sketch.parse((EXAMPLES / "PlantWaterer" / "PlantWaterer.ino").read_text()))
    assert draft["read"]["tank"] == {"type": "enum", "values": ["empty", "ok"], "stream": True, "every": "1 s"}
    assert draft["actions"]["water"]["args"] == {"duration": {"unit": "s", "min": 1.0, "max": 30.0}}
    assert draft["actions"]["stop"] == {"suggested": True}
    assert "write" not in draft


def test_desk_fan_sketch_limits_match_the_board() -> None:
    findings = sketch.parse((EXAMPLES / "DeskFan" / "DeskFan.ino").read_text())
    draft = sketch.draft(findings)
    assert draft["write"]["fan_speed"]["min"] == 0
    assert draft["write"]["fan_speed"]["max"] == 100
    assert draft["write"]["fan_speed"]["max_change_per_s"] == 20
    assert draft["read"]["temperature"]["range"] == [-20, 80]
    assert draft["match"] == {"firmware": {"product": "desk-fan"}}


def test_comments_are_not_commands() -> None:
    findings = sketch.parse('// if (line == "ERASE") wipe();\nvoid loop() {}\n/* line == "BOOM" */')
    assert not findings.commands
    assert findings.notes


def test_huge_sketch_is_refused() -> None:
    with pytest.raises(ValueError, match="larger than"):
        sketch.parse("x" * (sketch.MAX_SKETCH_BYTES + 1))


SCPI_MANUAL = """
Command reference

MEASure:VOLTage?        Returns the measured output voltage in volts.
MEASure:CURRent?        Returns the measured output current in amperes.
VOLTage <value>         Sets the output voltage setpoint.
CURRent <value>         Sets the current limit.
OUTPut <ON|OFF>         Turns the output on or off.
*RST                    Resets the instrument to factory defaults.
*IDN?                   Returns the identification string.
SYSTem:ERRor?           Reads the next error from the queue.
"""

GCODE_MANUAL = """
M104 S<temp>   Set hotend temperature
M105           Report temperatures
G28            Home all axes
M112           Emergency stop, needs a reset
"""


def test_scpi_manual() -> None:
    commands = {command.command: command for command in manual.extract(SCPI_MANUAL)}
    assert commands["MEASure:VOLTage?"].kind == "query"
    assert commands["VOLTage"].kind == "set"
    assert commands["VOLTage"].argument == "<value>"
    assert commands["*RST"].kind == "action"
    assert commands["*RST"].careful, "reset to factory defaults is flagged"
    assert all(view["confirmed"] is False for view in (command.view() for command in commands.values()))


def test_gcode_manual() -> None:
    commands = {command.command: command for command in manual.extract(GCODE_MANUAL)}
    assert commands["M104"].kind == "set"
    assert commands["M105"].kind == "action"
    assert commands["G28"].careful
    assert commands["M112"].careful


def test_manual_draft_never_makes_careful_commands_into_channels() -> None:
    sections = manual.draft_sections(manual.extract(SCPI_MANUAL))
    assert "measure_voltage" in sections["read"]
    assert "voltage" in sections["write"]
    assert "output" not in sections.get("write", {}), "output on is flagged, so it stays a note"
    assert "*RST" in sections["notes"]
    assert all(spec["suggested"] for spec in sections["write"].values())


def test_headings_are_not_commands() -> None:
    assert not manual.extract("INTRODUCTION\n\nSAFETY\nWARNINGS\n")
