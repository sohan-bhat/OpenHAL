"""The risk table (openhal/spec/risk.py, ADR 0023). Every rule, and the ways it must never go down."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from openhal.spec import risk
from openhal.spec.loader import from_data, load
from openhal.spec.models import DeviceFile

ROOT = Path(__file__).resolve().parents[2]


def device(name: str = "Board", **sections: Any) -> DeviceFile:
    return from_data({"device": name, "connect": {"driver": "mock"}, **sections})


def write(name: str, unit: str = "percent", maximum: float = 100, **extra: Any) -> dict[str, Any]:
    return {name: {"unit": unit, "min": 0, "max": maximum, **extra}}


def level(file: DeviceFile, target: str) -> str:
    return risk.level(file, target)


@pytest.mark.parametrize(
    ("channel", "spec", "expected"),
    [
        ("brightness", {"unit": "percent", "min": 0, "max": 100}, "low"),
        ("status_led", {"type": "bool"}, "low"),
        ("message", {"type": "string", "max_length": 20}, "low"),
        ("buzzer", {"type": "bool"}, "low"),
        ("fan_speed", {"unit": "percent", "min": 0, "max": 100}, "medium"),
        ("pump", {"type": "bool"}, "medium"),
        ("angle", {"unit": "deg", "min": 0, "max": 180}, "medium"),
        ("heater_power", {"unit": "percent", "min": 0, "max": 100}, "high"),
        ("target", {"unit": "degC", "min": 0, "max": 250}, "high"),
        ("relay", {"type": "bool"}, "high"),
        ("x_position", {"unit": "mm", "min": 0, "max": 200}, "high"),
        ("level", {"unit": "N", "min": 0, "max": 10}, "high"),
        ("output", {"unit": "percent", "min": 0, "max": 100}, "medium"),
        ("output", {"type": "bool"}, "medium"),
        ("lamp", {"unit": "lux", "min": 0, "max": 500}, "low"),
        ("dose", {"unit": "mL", "min": 0, "max": 50}, "medium"),
        ("heatbed", {"type": "bool"}, "high"),
    ],
)
def test_the_table(channel: str, spec: dict[str, Any], expected: str) -> None:
    assert level(device(write={channel: spec}), f"write:{channel}") == expected


def test_reading_is_always_low() -> None:
    file = device(read={"heater_temp": {"unit": "degC"}, "relay_state": {"type": "bool"}}, hazard="high")
    assert {level(file, f"read:{name}") for name in file.read} == {"low"}


@pytest.mark.parametrize(
    ("unit", "maximum", "expected"),
    [("W", 60, "medium"), ("W", 150, "high"), ("V", 30, "medium"), ("V", 230, "high"), ("A", 5, "medium")],
)
def test_electrical_units_go_high_above_their_threshold(unit: str, maximum: float, expected: str) -> None:
    assert level(device(write=write("setting", unit, maximum)), "write:setting") == expected


def test_the_threshold_converts_units() -> None:
    assert level(device(write=write("setting", "kW", 0.5)), "write:setting") == "high"
    assert level(device(write=write("setting", "mA", 900)), "write:setting") == "medium"


def test_the_hazard_field_is_a_floor() -> None:
    file = device(write=write("brightness"), hazard="high")
    assert level(file, "write:brightness") == "high"
    assert level(device(write=write("relay_led"), hazard="low"), "write:relay_led") == "high"


def test_the_device_name_decides_when_the_channel_name_says_nothing() -> None:
    assert level(device("Curing heater", write=write("power")), "write:power") == "high"
    assert level(device("LED strip", write=write("level")), "write:level") == "low"
    assert level(device("LED strip", write=write("fan_speed")), "write:fan_speed") == "medium"


def test_a_model_number_letter_says_nothing() -> None:
    file = from_data(
        {"device": {"name": "Supply", "model": "SPD3303X"}, "connect": {"driver": "mock"}, "write": write("output")}
    )
    assert level(file, "write:output") == "medium"


def test_three_motion_axes_make_a_machine() -> None:
    joints = {name: {"unit": "deg", "min": -90, "max": 90} for name in ("a", "b", "c")}
    file = device(write=joints)
    assert {level(file, f"write:{name}") for name in joints} == {"high"}
    two = device(write={name: {"unit": "deg", "min": 0, "max": 90} for name in ("pan", "tilt")})
    assert level(two, "write:pan") == "medium"


def test_arm_joints_are_high_whatever_driver_reads_them() -> None:
    file = device("Arm", write={"shoulder_pan_goal": {"unit": "deg", "min": -90, "max": 90}})
    assert level(file, "write:shoulder_pan_goal") == "high"


def test_an_unknown_target_is_high() -> None:
    assert level(device(write=write("brightness")), "write:nothing") == "high"


class TestUnitsOnlyRaise:
    """A missing or odd unit goes up a level and never down (red team, a fooled classifier)."""

    def test_a_missing_unit_goes_up(self) -> None:
        assert level(device(write=write("brightness", "dimensionless", 255)), "write:brightness") == "medium"
        assert level(device(write=write("output", "dimensionless", 255)), "write:output") == "high"

    def test_an_odd_unit_goes_up(self) -> None:
        assert level(device(write=write("brightness", "mol", 1)), "write:brightness") == "medium"
        assert level(device(write=write("fan_speed", "Wb", 8)), "write:fan_speed") == "high"

    @pytest.mark.parametrize("unit", ["dimensionless", "mol", "Wb", "percent", "s", "Hz", "lux", "count"])
    @pytest.mark.parametrize("name", ["heater", "relay", "joint_one", "target_temperature"])
    def test_a_high_name_stays_high_under_any_unit(self, name: str, unit: str) -> None:
        assert level(device(write=write(name, unit, 1)), f"write:{name}") == "high"

    @pytest.mark.parametrize("name", ["brightness", "fan_speed", "output", "pump"])
    def test_no_unit_lowers_a_channel_below_percent(self, name: str) -> None:
        plain = level(device(write=write(name)), f"write:{name}")
        for unit in ("dimensionless", "mol", "Wb", "count", "s", "Hz"):
            assert risk.RANK[level(device(write=write(name, unit, 1)), f"write:{name}")] >= risk.RANK[plain]


def test_descriptions_and_enum_values_only_raise() -> None:
    action = {"description": "Blinks the status led and shows a message", "args": {}}
    file = device("Curing heater", actions={"cycle": action})
    assert level(file, "action:cycle") == "high"
    enum = {"mode": {"type": "enum", "values": ["off", "led", "heat"]}}
    assert level(device(write=enum), "write:mode") == "high"


def test_an_action_takes_its_arguments_and_effects() -> None:
    file = device(
        write={"brightness": {"unit": "percent", "min": 0, "max": 100}, "heater": {"type": "bool"}},
        actions={
            "go": {"args": {"x": {"unit": "mm", "min": 0, "max": 10}}},
            "flash": {"effects": ["brightness"]},
            "warm": {"effects": ["heater"]},
            "water": {"args": {"duration": {"unit": "s", "min": 1, "max": 30}}},
        },
    )
    assert [level(file, f"action:{name}") for name in ("go", "flash", "warm", "water")] == [
        "high",
        "medium",
        "high",
        "medium",
    ]


def test_an_action_moving_three_axes_is_high() -> None:
    args = {name: {"unit": "deg", "min": 0, "max": 90} for name in ("a", "b", "c")}
    assert level(device(actions={"pose": {"args": args}}), "action:pose") == "high"


class TestPins:
    def test_a_bare_pin_is_medium_even_on_a_lamp(self) -> None:
        pin = {"pin5": {"type": "bool", "map": {"pin": 5}}}
        assert level(device("Lamp board", write=pin), "write:pin5") == "medium"

    def test_a_pin_shared_with_a_heater_is_high(self) -> None:
        file = device(
            write={
                "heater": {"unit": "percent", "min": 0, "max": 100, "map": {"pin": 5}},
                "pin5": {"type": "bool", "map": {"pin": 5}},
                "pin5_pwm": {"unit": "percent", "min": 0, "max": 100, "map": {"pin": 5, "mode": "pwm"}},
                "pin6": {"type": "bool", "map": {"pin": 6}},
            }
        )
        assert [level(file, f"write:{name}") for name in ("heater", "pin5", "pin5_pwm", "pin6")] == [
            "high",
            "high",
            "high",
            "medium",
        ]
        assert set(risk.assess(file)["write:pin5"].shared_with) == {"write:heater", "write:pin5_pwm"}

    def test_a_person_lowering_a_pin_doesnt_lower_its_heater_twin(self) -> None:
        file = device(
            write={
                "heater": {"type": "bool", "map": {"pin": 5}},
                "pin5": {
                    "type": "bool",
                    "map": {"pin": 5},
                    "risk": {"level": "low", "by": "owner", "at": "2026-11-03"},
                },
            }
        )
        assert level(file, "write:pin5") == "high"


class TestOverrides:
    def test_raising_needs_no_record(self) -> None:
        file = device(write=write("brightness", risk="high"))
        assert level(file, "write:brightness") == "high"
        assert risk.assess(file)["write:brightness"].override_applied

    def test_lowering_without_a_person_only_raises(self) -> None:
        file = device(write={"heater": {"type": "bool", "risk": "low"}})
        found = risk.assess(file)["write:heater"]
        assert found.level == "high"
        assert not found.override_applied

    def test_a_person_may_lower(self) -> None:
        file = device(
            write={"heater": {"type": "bool", "risk": {"level": "medium", "by": "owner", "at": "2026-11-03"}}}
        )
        found = risk.assess(file)["write:heater"]
        assert (found.level, found.classified, found.override_by) == ("medium", "high", "owner")

    def test_risk_stays_out_of_the_limits_hash(self) -> None:
        plain = device(write=write("brightness"))
        raised = device(write=write("brightness", risk={"level": "high", "by": "owner", "at": "2026-11-03"}))
        assert plain.limits_sha256() == raised.limits_sha256()

    def test_a_person_needs_a_date(self) -> None:
        with pytest.raises(ValueError, match="needs at"):
            device(write=write("brightness", risk={"level": "low", "by": "owner"}))

    def test_the_short_form_round_trips(self) -> None:
        file = device(write=write("brightness", risk="high"))
        assert file.model_dump(mode="json")["write"]["brightness"]["risk"] == "high"


class TestPolicy:
    def test_a_low_channel_ignores_a_suggested_rate(self) -> None:
        file = device(write=write("brightness", max_change_per_s=25, suggested=True))
        assert not risk.own_rate(file, "brightness")
        assert risk.own_rate(device(write=write("brightness", max_change_per_s=25)), "brightness")
        assert risk.own_rate(device(write=write("fan_speed", max_change_per_s=25, suggested=True)), "fan_speed")

    def test_a_high_action_that_cant_be_undone_waits_for_a_person(self) -> None:
        file = device(
            write={"heater": {"type": "bool"}},
            actions={"ignite": {}, "warm": {"effects": ["heater"]}, "off": {}, "blink": {}},
            safe_state=[{"action": "off"}],
        )
        assert risk.tier(file, "action:ignite", "none") == "confirm"
        assert risk.tier(file, "action:warm", "none") == "none"
        assert (
            risk.tier(
                device("Curing heater", actions={"off": {}}, safe_state=[{"action": "off"}]), "action:off", "none"
            )
            == "none"
        )
        assert risk.tier(file, "action:blink", "none") == "none"
        assert risk.tier(file, "action:ignite", "confirm-each-time") == "confirm-each-time"

    def test_a_high_hazard_device_holds_every_command(self) -> None:
        file = device(write=write("brightness"), hazard="high")
        assert risk.tier(file, "write:brightness", "none") == "confirm-each-time"

    def test_scope_follows_the_hazard_or_a_lower_target(self) -> None:
        file = device(write={**write("brightness"), **write("fan_speed")})
        assert risk.scope_level(file, "write:brightness") == "low"
        assert risk.scope_level(file, "write:fan_speed") == "medium"
        declared = device(write=write("brightness"), hazard="medium")
        assert risk.scope_level(declared, "write:brightness") == "medium"


class TestUnconfirmed:
    def test_low_and_medium_need_no_confirmation(self) -> None:
        file = device(write={**write("brightness", suggested=True), **write("fan_speed", suggested=True)})
        assert file.unconfirmed() == []
        assert file.writable

    def test_high_needs_a_person(self) -> None:
        file = device(write={**write("brightness", suggested=True), "heater": {"type": "bool", "suggested": True}})
        assert file.unconfirmed() == ["write.heater"]
        assert file.read_only("write:heater") == ["write.heater"]
        assert file.read_only("write:brightness") == []

    def test_file_level_limits_guard_high_targets(self) -> None:
        file = device(write={"heater": {"type": "bool", "confirmed": {"by": "x", "at": "2026-11-03"}}}, hazard="medium")
        assert file.read_only("write:heater") == ["file (interlocks, watchdog, safe state and hazard)"]


def _library_files() -> list[Path]:
    return sorted([*ROOT.joinpath("library").rglob("*.hal.yaml"), *ROOT.joinpath("examples").rglob("*.hal.yaml")])


@pytest.mark.parametrize("path", _library_files(), ids=lambda path: path.name)
def test_no_shipped_file_goes_below_its_hazard(path: Path) -> None:
    file = load(path)
    floor = risk.RANK[file.hazard] if file.hazard else 0
    for target, found in risk.assess(file).items():
        if not target.startswith("read:"):
            assert risk.RANK[found.level] >= floor


def test_the_table_names_no_maker_or_product() -> None:
    names: set[str] = {"esp", "arduino", "uno", "lerobot", "mujoco"}
    for path in _library_files():
        names |= {word for word in risk.tokens(load(path).device.manufacturer) if len(word) >= risk.DEVICE_WORD_MIN}
    words = {word for row in risk.WORDS for word in row.words} | {stem for row in risk.WORDS for stem in row.stems}
    assert not words & names


def test_a_low_word_on_a_device_named_for_something_high_is_high() -> None:
    assert level(device("Reptile heat lamp", write=write("lamp")), "write:lamp") == "high"
    assert level(device("Desk fan", write=write("status_led")), "write:status_led") == "low"


def test_a_bipolar_range_counts_by_its_far_end() -> None:
    supply = device(write={"output": {"unit": "V", "min": -200, "max": 5}})
    assert level(supply, "write:output") == "high"
    sink = device(actions={"sink": {"args": {"current": {"unit": "A", "min": -30, "max": 0}}}})
    assert level(sink, "action:sink") == "high"


def test_the_unit_signal_fails_closed() -> None:
    assert risk.unit_signal(None, None) == risk.UnitSignal(None, None)
    assert risk.unit_signal("no such unit", 1).odd
    assert risk.unit_signal("W", float("inf")).level == "high", "a power that can't be converted counts as high"


def test_a_pin_must_be_a_number_or_a_name_to_share() -> None:
    odd = device(write={"a": {"type": "bool", "map": {"pin": True}}, "b": {"type": "bool", "map": {"pin": True}}})
    assert risk.assess(odd)["write:a"].shared_with == ()
    found = risk.assess(device(write=write("brightness")))["write:brightness"]
    assert (found.kind, found.name) == ("write", "brightness")


def test_an_action_with_its_opposite_can_be_undone() -> None:
    printer = device(
        "Printer",
        actions={"pause_print": {}, "resume_print": {}, "cancel": {}, "start": {}, "stop": {}},
    )
    assert risk.undoable(printer, "pause_print")
    assert risk.undoable(printer, "resume_print")
    assert not risk.undoable(printer, "cancel")
    assert not risk.undoable(printer, "start"), "a stop doesn't undo a start"
    assert risk.tier(printer, "action:pause_print", "none") == "none"
    assert risk.tier(printer, "action:cancel", "none") == "confirm"
