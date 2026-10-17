"""Unit parsing and conversion, including the tricks the kernel must not fall for."""

from __future__ import annotations

import math

import pytest

from openhal.spec.units import (
    UnitError,
    convert,
    format_quantity,
    parse_duration,
    parse_quantity,
    parse_rate,
    parse_unit,
)


@pytest.mark.parametrize(
    ("text", "unit", "expected"),
    [
        ("30 degC", "degC", 30.0),
        ("86 degF", "degC", 30.0),
        ("303.15 K", "degC", 30.0),
        ("50 %", "percent", 50.0),
        ("50 percent", "percent", 50.0),
        ("0.5 dimensionless", "percent", 50.0),
        ("1.5 kW", "W", 1500.0),
        ("250 mA", "A", 0.25),
        ({"value": 12, "unit": "V"}, "V", 12.0),
    ],
)
def test_converts_to_channel_unit(text: object, unit: str, expected: float) -> None:
    assert math.isclose(convert(parse_quantity(text), unit), expected, rel_tol=1e-9)


@pytest.mark.parametrize("bad", [30, 30.0, "30", "", "  ", True, None, [30, "V"]])
def test_bare_numbers_and_junk_need_a_unit(bad: object) -> None:
    with pytest.raises(UnitError):
        parse_quantity(bad)


def test_default_unit_only_when_asked() -> None:
    assert parse_quantity(30, default_unit="degC").magnitude == 30
    assert parse_quantity("30", default_unit="degC").magnitude == 30


@pytest.mark.parametrize("bad", ["nan V", "inf V", "-inf degC", {"value": float("nan"), "unit": "V"}])
def test_non_finite_values_rejected(bad: object) -> None:
    with pytest.raises(UnitError):
        parse_quantity(bad)


def test_incompatible_units_rejected() -> None:
    with pytest.raises(UnitError, match="can't be converted"):
        convert(parse_quantity("3000 rpm"), "percent")
    with pytest.raises(UnitError):
        convert(parse_quantity("5 V"), "A")


def test_unknown_unit_rejected() -> None:
    with pytest.raises(UnitError, match="Unknown unit"):
        parse_unit("blorbs")


def test_quantity_mapping_needs_exact_keys() -> None:
    with pytest.raises(UnitError):
        parse_quantity({"value": 1, "unit": "V", "extra": 1})
    with pytest.raises(UnitError):
        parse_quantity({"value": "1", "unit": "V"})


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("5 s", 5.0), ("500ms", 0.5), ("10min", 600.0), ("2 h", 7200.0), ("1s", 1.0)],
)
def test_durations(text: str, seconds: float) -> None:
    assert parse_duration(text) == pytest.approx(seconds)


@pytest.mark.parametrize("bad", [5, "5", "-1 s", "5 V"])
def test_bad_durations(bad: object) -> None:
    with pytest.raises(UnitError):
        parse_duration(bad)


def test_rates_use_delta_units_for_temperature() -> None:
    assert parse_rate(2, "degC") == 2
    assert parse_rate("2 degC/s", "degC") == pytest.approx(2)
    assert parse_rate("3.6 degF/s", "degC") == pytest.approx(2)
    assert parse_rate("20 %/s", "percent") == pytest.approx(20)
    assert parse_rate("1200 percent/minute", "percent") == pytest.approx(20)


def test_format_quantity() -> None:
    assert format_quantity(100.0, "percent") == "100 %"
    assert format_quantity(29.444444, "degC") == "29.4444 degC"
