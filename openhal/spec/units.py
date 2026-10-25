"""The one unit registry OpenHAL uses, and helpers to parse quantities and durations.

Every numeric value the hub handles is converted through this registry (ADR 0005). The registry
is created once with pint's default definitions and never loads user definitions.
"""

from __future__ import annotations

import math
import re
from typing import Any, Final

import pint

ureg: Final = pint.UnitRegistry(autoconvert_offset_to_baseunit=False, cache_folder=None)
Quantity = ureg.Quantity

_COMPACT_DURATION: Final = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*(ms|s|min|h)\s*$")
_UNIT_ALIASES: Final = {"%": "percent", "%/s": "percent / second"}
MAX_UNIT_LENGTH: Final = 40
"""The longest unit name the hub parses. pint's parser slows down sharply on long names (red team RT-01)."""
MAX_QUANTITY_LENGTH: Final = 80


class UnitError(ValueError):
    """A value has no unit, an unknown unit, or a unit that can't be converted."""


def normalize_unit(unit: str) -> str:
    """Return a pint-parsable unit string, mapping `%` to `percent`."""
    text = unit.strip()
    if text in _UNIT_ALIASES:
        return _UNIT_ALIASES[text]
    return text.replace("%", "percent")


def parse_unit(unit: str) -> pint.Unit:
    """Parse a unit name such as `degC`, `percent` or `V`."""
    if not isinstance(unit, str) or not unit.strip():
        raise UnitError("A unit is required, for example degC, percent or V.")
    if len(unit) > MAX_UNIT_LENGTH:
        raise UnitError(f"A unit may be at most {MAX_UNIT_LENGTH} characters.")
    try:
        parsed = ureg.parse_units(normalize_unit(unit))
    except (pint.errors.UndefinedUnitError, pint.errors.DefinitionSyntaxError, ValueError) as exc:
        raise UnitError(f"Unknown unit {unit!r}.") from exc
    return parsed


def _finite(value: float, what: str) -> float:
    if not math.isfinite(value):
        raise UnitError(f"{what} must be a finite number.")
    return value


def parse_quantity(value: Any, *, default_unit: str | None = None) -> pint.Quantity:
    """Parse `"30 degC"`, `{"value": 30, "unit": "degC"}` or a number with a default unit.

    A bare number is accepted only when `default_unit` is given. Commands from clients never
    pass a default unit, so bare numbers in commands are rejected.
    """
    if isinstance(value, bool):
        raise UnitError("Expected a number with a unit, got a boolean.")
    if isinstance(value, int | float):
        if default_unit is None:
            raise UnitError("This value needs a unit, for example 30 degC or 50 %.")
        return Quantity(_finite(float(value), "Value"), parse_unit(default_unit))
    if isinstance(value, dict):
        if set(value) != {"value", "unit"}:
            raise UnitError("A quantity mapping must have exactly the keys value and unit.")
        raw = value["value"]
        if isinstance(raw, bool) or not isinstance(raw, int | float):
            raise UnitError("The value of a quantity must be a number.")
        return Quantity(_finite(float(raw), "Value"), parse_unit(value["unit"]))
    if isinstance(value, str):
        text = value.strip()
        if len(text) > MAX_QUANTITY_LENGTH:
            raise UnitError(f"A quantity may be at most {MAX_QUANTITY_LENGTH} characters, such as 30 degC.")
        match = re.match(r"^([+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)\s*(.*)$", text)
        if not match:
            raise UnitError(f"Could not read {value!r} as a number with a unit.")
        number, unit = match.group(1), match.group(2)
        if not unit:
            if default_unit is None:
                raise UnitError(f"{value!r} needs a unit, for example {number} degC.")
            unit = default_unit
        return Quantity(_finite(float(number), "Value"), parse_unit(unit))
    raise UnitError(f"Expected a number with a unit, got {type(value).__name__}.")


def convert(quantity: pint.Quantity, unit: str) -> float:
    """Convert a quantity to `unit` and return the magnitude, checking it is finite."""
    target = parse_unit(unit)
    try:
        converted = quantity.to(target)
    except (pint.errors.DimensionalityError, pint.errors.OffsetUnitCalculusError) as exc:
        raise UnitError(f"{quantity:~P} can't be converted to {unit}.") from exc
    return _finite(float(converted.magnitude), "Converted value")


def rate_unit(unit: str) -> str:
    """Return the unit of a rate of change for a channel unit, using delta units for offsets."""
    parsed = parse_unit(unit)
    text = str(parsed)
    offset_units = {"degree_Celsius": "delta_degree_Celsius", "degree_Fahrenheit": "delta_degree_Fahrenheit"}
    text = offset_units.get(text, text)
    return f"({text}) / second"


def parse_rate(value: Any, channel_unit: str) -> float:
    """Parse a rate limit and return it in channel units per second."""
    target = rate_unit(channel_unit)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return _finite(float(value), "Rate")
    text = value
    if isinstance(value, str):
        text = value.replace("%/s", "percent / second")
    quantity = parse_quantity(text, default_unit=target)
    return convert_rate(quantity, channel_unit)


def convert_rate(quantity: pint.Quantity, channel_unit: str) -> float:
    """Convert a rate quantity into channel units per second."""
    target = rate_unit(channel_unit)
    unit_text = str(quantity.units)
    for absolute, delta in (
        ("degree_Celsius", "delta_degree_Celsius"),
        ("degree_Fahrenheit", "delta_degree_Fahrenheit"),
    ):
        if absolute in unit_text and delta not in unit_text:
            quantity = Quantity(quantity.magnitude, unit_text.replace(absolute, delta))
            break
    try:
        return _finite(float(quantity.to(target).magnitude), "Rate")
    except pint.errors.DimensionalityError as exc:
        raise UnitError(f"{quantity:~P} is not a rate in {channel_unit} per second.") from exc


def parse_duration(value: Any) -> float:
    """Parse a duration (`5 s`, `500ms`, `10min`, `2 h`) and return seconds."""
    if isinstance(value, str):
        compact = _COMPACT_DURATION.match(value)
        if compact:
            value = f"{compact.group(1)} {compact.group(2)}"
    if isinstance(value, int | float) and not isinstance(value, bool):
        raise UnitError("A duration needs a unit, for example 5 s or 10 min.")
    seconds = convert(parse_quantity(value), "second")
    if seconds < 0:
        raise UnitError("A duration can't be negative.")
    return seconds


def format_quantity(magnitude: float, unit: str) -> str:
    """Format a magnitude and unit for messages, for example `100 %` or `29.4 degC`."""
    text = f"{magnitude:.6g}"
    shown = "%" if normalize_unit(unit) == "percent" else unit
    return f"{text} {shown}"


_QUANTITY_TEXT = re.compile(r"^\s*(?P<number>[-+]?[0-9][0-9.eE+-]{0,30})\s*(?P<unit>[^\s0-9].{0,39}?)\s*$")


def split_quantity(text: str) -> dict[str, Any] | None:
    """Split typed text such as `60%`, `60 %` or `1.5 V` into a Quantity mapping `{value, unit}`.

    Returns None when the text isn't one finite number followed by a unit. The unit isn't checked
    here, the hub converts and checks it.
    """
    found = _QUANTITY_TEXT.match(text)
    if not found:
        return None
    try:
        magnitude = float(found["number"])
    except ValueError:
        return None
    if not math.isfinite(magnitude):
        return None
    number: float | int = int(magnitude) if magnitude.is_integer() else magnitude
    return {"value": number, "unit": found["unit"]}
