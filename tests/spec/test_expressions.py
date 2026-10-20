"""The interlock expression language. Parsing, limits and three-valued evaluation."""

from __future__ import annotations

import pytest

from openhal.spec import expressions as ex
from openhal.spec.expressions import ExpressionError, Ref, Value


def resolver(values: dict[str, Value]) -> ex.Resolver:
    def resolve(ref: Ref) -> Value | None:
        return values.get(str(ref))

    return resolve


LOCAL = {"door_closed", "state", "temp"}

STATE = resolver(
    {
        "fan.speed": Value(40.0, "percent"),
        "heater.power": Value(10.0, "W"),
        "door_closed": Value(True),
        "state": Value("idle"),
        "temp": Value(30.0, "degC"),
    }
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("fan.speed >= 30 %", True),
        ("fan.speed > 40 %", False),
        ("fan.speed == 0.4 dimensionless", True),
        ("heater.power > 0 W and fan.speed >= 30 %", True),
        ("heater.power > 0 W and fan.speed >= 50 %", False),
        ("not door_closed == true", False),
        ("door_closed", True),
        ("state == idle", True),
        ("state != 'printing'", True),
        ("temp < 90 degF", True),
        ("temp <= 303.15 K", True),
        ("(state == idle or state == paused) and door_closed == true", True),
        ("fan.speed > 10 % or missing.value > 1 V", True),
    ],
)
def test_evaluates(text: str, expected: bool) -> None:
    assert ex.evaluate(ex.parse(text, LOCAL), STATE) is expected


@pytest.mark.parametrize(
    "text",
    [
        "missing.value > 1 V",
        "fan.speed > 10 % and missing.value > 1 V",
        "not missing.flag",
        "fan.speed > 10 V",
        "door_closed > true",
    ],
)
def test_unknown_values_stay_unknown(text: str) -> None:
    assert ex.evaluate(ex.parse(text, LOCAL), STATE) is None


@pytest.mark.parametrize(
    "text",
    ["guard_open != true", "guard_open == false", "not guard_open", "mode != jammed", "mode == idle", "moving == true"],
)
def test_unknown_local_channels_are_never_words(text: str) -> None:
    """Review finding F01. An unknown channel must stay unknown, not turn into the word of its name."""
    channels = {"guard_open", "mode", "moving"}
    assert ex.evaluate(ex.parse(text, channels), resolver({})) is None


def test_bare_names_split_into_channels_and_words() -> None:
    tree = ex.parse("mode == idle and other.state == busy", {"mode"})
    assert {str(ref) for ref in ex.references(tree)} == {"mode", "other.state"}
    assert [word for word, _ in ex.words(tree)] == ["idle", "busy"]
    assert ex.words(ex.parse("mode == 'idle'", {"mode"})) == []


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "fan.speed >=",
        "(fan.speed > 1 %",
        "fan.speed > 1 % extra",
        "a == b == c",
        "fan.speed $ 3",
        "and",
        "1 %)",
    ],
)
def test_parse_errors(text: str) -> None:
    with pytest.raises(ExpressionError):
        ex.parse(text)


def test_length_and_depth_limits() -> None:
    with pytest.raises(ExpressionError, match="at most 256"):
        ex.parse("a == 1 V or " * 30 + "a == 1 V")
    with pytest.raises(ExpressionError, match="nest"):
        ex.parse("(" * 20 + "a" + ")" * 20)


def test_references() -> None:
    tree = ex.parse("heater.power > 0 W and fan.speed >= 30 % and door_closed")
    assert {str(ref) for ref in ex.references(tree)} == {"heater.power", "fan.speed", "door_closed"}


def test_check_units_requires_unit_against_quantity_channel() -> None:
    def unit_of(ref: Ref) -> str | None:
        return "percent" if ref.name == "speed" else None

    with pytest.raises(ExpressionError, match="needs a unit"):
        ex.check_units(ex.parse("speed > 30"), unit_of)
    with pytest.raises(ExpressionError, match="can't be compared"):
        ex.check_units(ex.parse("speed > 30 V"), unit_of)
    ex.check_units(ex.parse("speed > 30 %"), unit_of)


def test_no_code_execution() -> None:
    with pytest.raises(ExpressionError):
        ex.parse("__import__('os').system('true')")
