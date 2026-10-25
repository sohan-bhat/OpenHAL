"""GRBL message parsing, without a port."""

from __future__ import annotations

import pytest

from openhal.drivers.grbl import protocol


def test_idle_report_with_machine_position_and_speed() -> None:
    status = protocol.parse_status("<Idle|MPos:1.000,-2.500,3.250|FS:0,0|WCO:0.000,0.000,0.000>")
    assert status.state == "idle"
    assert status.mpos == (1.0, -2.5, 3.25)
    assert status.wpos is None
    assert status.wco == (0.0, 0.0, 0.0)
    assert (status.feed, status.spindle) == (0.0, 0.0)


def test_hold_report_with_every_optional_field() -> None:
    line = "<Hold:1|WPos:0.000,0.000,0.000,5.000|Bf:15,128|Ln:42|F:250|Pn:XP|Ov:110,100,90|A:SF>"
    status = protocol.parse_status(line)
    assert (status.state, status.substate) == ("hold", 1)
    assert status.wpos == (0.0, 0.0, 0.0, 5.0)
    assert status.buffer == (15, 128)
    assert status.line == 42
    assert status.feed == 250.0
    assert status.spindle is None
    assert status.pins == "XP"
    assert status.overrides == (110, 100, 90)
    assert status.accessories == "SF"
    assert status.raw == line


@pytest.mark.parametrize(
    "line",
    [
        "Idle|MPos:0,0,0",
        "<Flying|MPos:0,0,0>",
        "<Idle|FS:0,0>",
        "<Idle|MPos:a,b,c>",
        "<Idle|MPos:nan,0,0>",
        "<Idle|MPos:0,0,0|FS:1>",
        "<Idle|MPos:0,0,0|Ov:100,100>",
        "<Idle|MPos:0,0,0|Bf:15>",
        "<Idle|MPos>",
        "<Hold:x|MPos:0,0,0>",
        "<" + "Idle|" * 200 + ">",
    ],
)
def test_malformed_reports_raise(line: str) -> None:
    with pytest.raises(ValueError, match=r"."):
        protocol.parse_status(line)


def test_brackets_settings_and_banner() -> None:
    assert protocol.parse_bracket("[GC:G0 G54 G17]") == ("GC", "G0 G54 G17")
    assert protocol.parse_bracket("[MSG:Caution: Unlocked]") == ("MSG", "Caution: Unlocked")
    assert protocol.parse_bracket("[PRB:0.000,0.000,0.000:0]") == ("PRB", "0.000,0.000,0.000:0")
    assert protocol.parse_bracket("ok") is None
    assert protocol.parse_setting("$130=300.000") == (130, "300.000")
    assert protocol.parse_setting("$N0=") is None
    banner = protocol.BANNER.match("Grbl 1.1h ['$' for help]")
    assert banner is not None
    assert banner.group(1) == "1.1h"
    hal = protocol.BANNER.match("GrblHAL 1.1f ['$' or '$HELP' for help]")
    assert hal is not None
    assert hal.group(1) == "1.1f"


def test_parser_state_words() -> None:
    modes = protocol.parse_modes("G1 G55 G17 G20 G91 G94 M0 M3 M7 M8 T2 F600 S12000")
    assert modes["motion"] == "G1"
    assert modes["wcs"] == "G55"
    assert modes["units"] == "G20"
    assert modes["distance"] == "G91"
    assert modes["spindle"] == "M3"
    assert modes["coolant"] == "M7 M8"
    assert modes["tool"] == "T2"
    assert (modes["feed"], modes["speed"]) == (600.0, 12000.0)
    assert protocol.parse_modes("G0 M5 M9")["coolant"] == "M9"
    with pytest.raises(ValueError, match="bad F"):
        protocol.parse_modes("G0 Fabc")


def test_numbers_and_code_texts() -> None:
    assert protocol.number(12.0) == "12"
    assert protocol.number(-0.00001) == "0"
    assert protocol.number(1.23456) == "1.2346"
    assert protocol.number(-3.5) == "-3.5"
    assert "alarm" in protocol.error_text(9)
    assert protocol.error_text(99) == "an error code this driver does not know"
    assert "hard limit" in protocol.alarm_text(1)
    assert protocol.alarm_text(42).startswith("an alarm code")
