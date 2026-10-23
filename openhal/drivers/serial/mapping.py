"""Text value mapping shared by drivers whose device files describe a text protocol.

A channel's `map` says how the device writes a value as text and how to turn it into the
channel's type and unit. The serial and scpi drivers use these helpers. Nothing here imports a
protocol library.

Number conversion, in both directions.

    channel value = convert(raw * scale + offset, from map.unit to the channel unit)
    raw           = (convert(value, from the channel unit to map.unit) - offset) / scale

`raw` is the number the device sends or expects. Without `map.unit` the device is taken to use
the channel unit already.
"""

from __future__ import annotations

import math
import re
import string
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

from openhal.drivers.base import DriverError
from openhal.spec.models import ReadChannel, WriteChannel
from openhal.spec.units import Quantity, UnitError, convert, parse_duration, parse_unit

TRUE_WORDS: Final = frozenset({"1", "on", "true", "high", "yes", "enabled"})
FALSE_WORDS: Final = frozenset({"0", "off", "false", "low", "no", "disabled"})
MAX_TEMPLATE: Final = 200

# Unit symbols that home automation systems report (Home Assistant, ESPHome), by registry name.
# None marks a unit that is known but has no registry equivalent.
DEVICE_UNITS: Final[dict[str, str | None]] = {
    "°C": "degC",
    "°F": "degF",
    "K": "K",
    "%": "percent",
    "lx": "lux",
    "W": "W",
    "kW": "kW",
    "Wh": "Wh",
    "kWh": "kWh",
    "V": "V",
    "mV": "mV",
    "A": "A",
    "mA": "mA",
    "Pa": "Pa",
    "hPa": "hPa",
    "kPa": "kPa",
    "mbar": "mbar",
    "bar": "bar",
    "ppm": "ppm",
    "s": "s",
    "min": "min",
    "h": "h",
    "m": "m",
    "cm": "cm",
    "mm": "mm",
    "L": "L",
    "m³": "m**3",
    "Hz": "Hz",
    "dBm": None,
}


def device_unit(text: Any) -> str | None:
    """A unit symbol a device or bridge reported, as a unit the OpenHAL registry knows, if any."""
    if not isinstance(text, str) or not text:
        return None
    if text in DEVICE_UNITS:
        return DEVICE_UNITS[text]
    try:
        parse_unit(text)
    except UnitError:
        return None
    return text


def duration(value: Any) -> float:
    """A parameter duration, written as a quantity (`2 s`, `500 ms`). Bare numbers are refused."""
    return parse_duration(value)


def check_regex(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) > 256:
        raise ValueError("Patterns may be at most 256 characters.")
    try:
        re.compile(value)
    except re.error as exc:
        raise ValueError(f"Invalid pattern {value!r} ({exc}).") from exc
    return value


class ValueMap(BaseModel):
    """How one channel's value appears as text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    parse: str | None = Field(default=None, description="Regex. Group `value`, else group 1, else the match.")
    scale: float = 1.0
    offset: float = 0.0
    unit: str | None = Field(default=None, description="The unit the device uses, if not the channel unit.")
    on: str | None = Field(default=None, description="Device text for true.")
    off: str | None = Field(default=None, description="Device text for false.")
    lookup: dict[str, str] = Field(default={}, description="Device text to enum value.")

    @field_validator("parse")
    @classmethod
    def _regex(cls, value: str | None) -> str | None:
        return check_regex(value)

    @field_validator("scale")
    @classmethod
    def _scale(cls, value: float) -> float:
        if value == 0 or not math.isfinite(value):
            raise ValueError("scale must be a finite number other than zero.")
        return value

    @field_validator("unit")
    @classmethod
    def _unit(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                parse_unit(value)
            except UnitError as exc:
                raise ValueError(str(exc)) from exc
        return value


def check_template(template: str, allowed: set[str], where: str) -> None:
    """Allow only `{name}` and `{name:spec}` placeholders for the given names."""
    if len(template) > MAX_TEMPLATE:
        raise DriverError(f"{where}: the template is longer than {MAX_TEMPLATE} characters.")
    try:
        fields = list(string.Formatter().parse(template))
    except ValueError as exc:
        raise DriverError(f"{where}: {template!r} is not a valid template ({exc}).") from exc
    for _, name, spec, conversion in fields:
        if name is None:
            continue
        if name not in allowed:
            names = ", ".join("{" + item + "}" for item in sorted(allowed)) or "no placeholders"
            raise DriverError(f"{where}: {{{name}}} is not allowed in {template!r}. Use {names}.")
        if conversion is not None or (spec and "{" in spec):
            raise DriverError(f"{where}: placeholders can't use conversions or nested fields.")


def render(template: str, values: dict[str, Any], where: str) -> str:
    """Fill a checked template. Refuse values that would smuggle extra commands."""
    for name, value in values.items():
        if isinstance(value, str):
            plain_text(value, f"{where} {name}")
    try:
        text = template.format(**values)
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise DriverError(f"{where}: could not fill {template!r} ({exc}). Check the format spec.") from exc
    return plain_text(text, where)


def plain_text(value: str, where: str) -> str:
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise DriverError(f"{where}: control characters such as newlines are not allowed in commands.")
    return value


def extract(text: str, value_map: ValueMap, where: str) -> str:
    if value_map.parse is None:
        return text.strip()
    match = re.search(value_map.parse, text)
    if match is None:
        raise DriverError(f"{where}: the device replied {text!r}, which doesn't match {value_map.parse!r}.")
    if "value" in match.re.groupindex:
        found = match.group("value")
    elif match.re.groups:
        found = match.group(1)
    else:
        found = match.group(0)
    if found is None:
        raise DriverError(f"{where}: the pattern matched {text!r} but captured nothing.")
    return found.strip()


def decode(
    channel: str, text: str, spec: ReadChannel | WriteChannel, value_map: ValueMap, where: str
) -> float | bool | str:
    """Turn one reply into a value of the channel's type, in the channel's unit."""
    raw = extract(text, value_map, where)
    if spec.type == "number":
        try:
            number = float(raw)
        except ValueError:
            raise DriverError(f"{where}: expected a number from the device, got {raw!r}.") from None
        if not math.isfinite(number):
            raise DriverError(f"{where}: the device sent {raw!r}, which is not a finite number.")
        value = number * value_map.scale + value_map.offset
        if value_map.unit and spec.unit:
            try:
                value = convert(Quantity(value, parse_unit(value_map.unit)), spec.unit)
            except UnitError as exc:
                raise DriverError(f"{where}: {exc}") from exc
        return value
    if spec.type == "bool":
        word = raw.lower()
        trues = {value_map.on.lower()} if value_map.on is not None else TRUE_WORDS
        falses = {value_map.off.lower()} if value_map.off is not None else FALSE_WORDS
        if word in trues:
            return True
        if word in falses:
            return False
        raise DriverError(f"{where}: expected on or off from the device, got {raw!r}.")
    if spec.type == "enum":
        word = value_map.lookup.get(raw, raw)
        if word not in spec.values:
            raise DriverError(f"{where}: the device reported {raw!r}, which is not one of {', '.join(spec.values)}.")
        return word
    return raw


def encode(value: float | bool | str, spec: WriteChannel, value_map: ValueMap, where: str) -> float | str:
    """Turn a checked channel value into what the device expects in a template."""
    if spec.type == "number":
        assert isinstance(value, int | float)
        assert not isinstance(value, bool)
        number = float(value)
        if value_map.unit and spec.unit:
            try:
                number = convert(Quantity(number, parse_unit(spec.unit)), value_map.unit)
            except UnitError as exc:
                raise DriverError(f"{where}: {exc}") from exc
        return (number - value_map.offset) / value_map.scale
    if spec.type == "bool":
        if value:
            return value_map.on if value_map.on is not None else "1"
        return value_map.off if value_map.off is not None else "0"
    text = str(value)
    if spec.type == "enum":
        for device_text, enum_value in value_map.lookup.items():
            if enum_value == text:
                return device_text
    return text


def sample(spec: WriteChannel | Any) -> float | str:
    """A placeholder value used to test-render a template when the file loads."""
    return 0.0 if getattr(spec, "type", "number") == "number" else "x"
