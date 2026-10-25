"""What the Zigbee2MQTT and zwave-js-server links share. Channel maps, value descriptions and conversion.

A link reports a `Feature` for every value it knows, taken from the Zigbee2MQTT `exposes` list or
the zwave-js value metadata. Conversion uses it.

    channel value = convert(raw * scale + offset, from the bridge unit to the channel unit)

Changes run it backwards and round to the bridge's step, or to whole numbers when the bridge's
limits are whole numbers, as Zigbee2MQTT brightness and Z-Wave levels are.

`map.unit` names the bridge unit when the bridge doesn't report one. Bridge units are mapped to
registry names the way Home Assistant units are (`°C` is `degC`, `%` is `percent`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from openhal.drivers.base import DriverError
from openhal.drivers.serial import mapping
from openhal.spec.units import Quantity, UnitError, convert, parse_unit

Kind = Literal["number", "bool", "enum", "string", "unknown"]


@dataclass(frozen=True)
class Feature:
    """What the bridge says about one value."""

    kind: Kind
    unit: str | None = None
    readable: bool = True
    writable: bool = False
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    on: Any = True
    off: Any = False
    states: dict[str, str] = field(default_factory=dict)
    values: tuple[str, ...] = ()
    label: str = ""


UNKNOWN = Feature("unknown")


class ChannelMap(BaseModel):
    """Where one channel's value lives on the bridge. Zigbee uses `property`. Z-Wave uses all of them."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    property: str | None = Field(default=None, min_length=1, max_length=128)
    command_class: int | None = Field(default=None, ge=0, le=0xFFFF)
    endpoint: int = Field(default=0, ge=0, le=255)
    property_key: str | int | None = None
    target: str | None = Field(default=None, min_length=1, max_length=128)
    scale: float = 1.0
    offset: float = 0.0
    unit: str | None = None

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


def bridge_unit(feature: Feature, channel_map: ChannelMap) -> str | None:
    """The unit the bridge's raw numbers are in, as a registry name, if anyone says."""
    return channel_map.unit or mapping.device_unit(feature.unit)


def decode(raw: Any, spec: Any, feature: Feature, channel_map: ChannelMap, where: str) -> float | bool | str | None:
    """Turn a bridge value into a value of the channel's type, in the channel's unit."""
    if raw is None:
        return None
    kind = spec.type
    if kind == "number":
        if isinstance(raw, bool) or not isinstance(raw, int | float):
            try:
                raw = float(raw)
            except (TypeError, ValueError):
                raise DriverError(f"{where} reported {str(raw)[:60]!r}, which is not a number.") from None
        value = float(raw) * channel_map.scale + channel_map.offset
        if not math.isfinite(value):
            raise DriverError(f"{where} reported a value that is not a finite number.")
        source = bridge_unit(feature, channel_map)
        if source and spec.unit and source != spec.unit:
            try:
                value = convert(Quantity(value, parse_unit(source)), spec.unit)
            except UnitError:
                raise DriverError(f"{where} reports {source}, which doesn't convert to {spec.unit}.") from None
        return value
    if kind == "bool":
        if raw == feature.on or raw is True:
            return True
        if raw == feature.off or raw is False:
            return False
        raise DriverError(f"{where} reported {str(raw)[:60]!r}, which is neither {feature.on!r} nor {feature.off!r}.")
    text = feature.states.get(str(raw), str(raw)) if not isinstance(raw, bool) else str(raw).lower()
    if kind == "enum" and text not in spec.values:
        raise DriverError(f"{where} reported {text[:60]!r}, which is not one of {', '.join(spec.values)}.")
    return text


def encode(value: float | bool | str, spec: Any, feature: Feature, channel_map: ChannelMap, where: str) -> Any:
    """Turn a checked channel value into what the bridge expects."""
    kind = spec.type
    if kind == "bool":
        return feature.on if value else feature.off
    if kind == "enum":
        for raw_key, label in feature.states.items():
            if label == value:
                return int(raw_key) if raw_key.lstrip("-").isdigit() else raw_key
        return str(value)
    if kind == "string":
        return str(value)
    number = float(value)
    target = bridge_unit(feature, channel_map)
    if target and spec.unit and target != spec.unit:
        try:
            number = convert(Quantity(number, parse_unit(spec.unit)), target)
        except UnitError:
            raise DriverError(f"{where}: {spec.unit} doesn't convert to the bridge's {target}.") from None
    raw = (number - channel_map.offset) / channel_map.scale
    if feature.step:
        base = feature.minimum or 0.0
        raw = base + round((raw - base) / feature.step) * feature.step
    elif _whole(feature.minimum) and _whole(feature.maximum):
        return round(raw)
    nearest = round(raw)
    if abs(raw - nearest) <= 1e-6 * max(1.0, abs(raw)):
        return int(nearest)
    return round(raw, 6)


def _whole(limit: float | None) -> bool:
    return isinstance(limit, int) and not isinstance(limit, bool)


def suspect(value: Any, spec: Any) -> bool:
    """True for a number outside a read channel's declared range."""
    limits = getattr(spec, "range", None)
    return bool(limits is not None and isinstance(value, float) and not limits[0] <= value <= limits[1])


def check(name: str, spec: Any, feature: Feature, channel_map: ChannelMap, *, sends: bool, where: str) -> None:
    """Refuse a channel the bridge can't serve the way the device file asks. Raises DriverError."""
    if feature is UNKNOWN:
        raise DriverError(f"{name}: {where} doesn't have this value. Check the map against describe().")
    if sends and not feature.writable:
        raise DriverError(f"{name}: {where} says this value can't be set. Move it under read.")
    if not sends and not feature.readable:
        raise DriverError(f"{name}: {where} says this value can't be read. Move it under write with a state map.")
    expected = {"number": "number", "bool": "bool", "enum": "enum", "string": "string"}.get(feature.kind)
    if expected == "number" and spec.type not in ("number",):
        raise DriverError(f"{name}: {where} reports a number, so the channel needs type number.")
    if expected == "bool" and spec.type != "bool":
        raise DriverError(f"{name}: {where} reports on and off, so the channel needs type bool.")
    if expected == "enum" and spec.type not in ("enum", "string"):
        raise DriverError(f"{name}: {where} reports a fixed list of words, so the channel needs type enum.")
    if spec.type == "enum":
        known = set(feature.states.values()) | set(feature.values)
        unknown = [value for value in spec.values if known and value not in known]
        if unknown:
            raise DriverError(
                f"{name}: {where} doesn't know {', '.join(unknown)}. It knows {', '.join(sorted(known))}."
            )
    source = bridge_unit(feature, channel_map)
    if spec.type == "number" and spec.unit and source and source != spec.unit:
        try:
            convert(Quantity(1.0, parse_unit(source)), spec.unit)
        except UnitError:
            raise DriverError(
                f"{name}: {where} reports {feature.unit}, which doesn't convert to {spec.unit}."
            ) from None
