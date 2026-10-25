"""Integer fields inside a byte payload, shared by the can and pi-i2c-spi drivers.

A field names where a value sits in a payload and how to turn it into a channel value.

    raw          = bits `bit` to `bit + bits - 1` of the integer read from `length` bytes at `byte`
    device value = raw * scale + offset, in `unit` (the channel unit when `unit` is not given)
    channel value = device value converted to the channel's unit

Bit 0 is the least significant bit of the integer, after the bytes are read in `endian` order.
Writes run the same steps backwards. A value is rounded to the nearest raw step, and a value
the field can't hold raises DriverError. Nothing is clamped. Nothing here imports a protocol
library.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from openhal.drivers.base import DriverError
from openhal.spec.models import ReadChannel, WriteChannel
from openhal.spec.units import Quantity, UnitError, convert, parse_unit

MAX_PAYLOAD = 64


class BitField(BaseModel):
    """Where one value sits in a payload and how its raw integer maps to the channel value."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    byte: int = Field(default=0, ge=0, lt=MAX_PAYLOAD)
    length: int = Field(default=1, ge=1, le=8)
    endian: Literal["big", "little"] = "big"
    signed: bool = False
    bit: int = Field(default=0, ge=0, le=63)
    bits: int | None = Field(default=None, ge=1, le=64)
    scale: float = 1.0
    offset: float = 0.0
    unit: str | None = None
    on: int = 1
    off: int = 0
    lookup: dict[int, str] = {}

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

    @model_validator(mode="after")
    def _fits(self) -> BitField:
        if self.width < 1 or self.bit + self.width > self.length * 8:
            raise ValueError(
                f"bit {self.bit} and bits {self.width} don't fit in {self.length} byte(s). "
                "Use a longer length or fewer bits."
            )
        if self.byte + self.length > MAX_PAYLOAD:
            raise ValueError(f"byte {self.byte} plus length {self.length} runs past {MAX_PAYLOAD} bytes.")
        return self

    @property
    def width(self) -> int:
        """The number of bits the raw value uses."""
        return self.bits if self.bits is not None else self.length * 8 - self.bit

    @property
    def end(self) -> int:
        """The first byte after this field."""
        return self.byte + self.length

    def raw_range(self) -> tuple[int, int]:
        """The smallest and largest raw integer the field holds."""
        if self.signed:
            return -(1 << (self.width - 1)), (1 << (self.width - 1)) - 1
        return 0, (1 << self.width) - 1


def extract(data: bytes, field: BitField, where: str) -> int:
    """Read the field's raw integer from a payload. A payload too short for it raises DriverError."""
    if len(data) < field.end:
        raise DriverError(
            f"{where} carried {len(data)} byte(s), too short for a field at byte {field.byte} "
            f"with length {field.length}. Check the map against the device's documentation."
        )
    whole = int.from_bytes(data[field.byte : field.end], field.endian, signed=False)
    raw = (whole >> field.bit) & ((1 << field.width) - 1)
    if field.signed and raw & (1 << (field.width - 1)):
        raw -= 1 << field.width
    return raw


def insert(data: bytearray, field: BitField, raw: int, where: str) -> None:
    """Write a raw integer into a payload in place. A raw value the field can't hold raises DriverError."""
    low, high = field.raw_range()
    if not low <= raw <= high:
        raise DriverError(f"{where} needs raw value {raw}, but the field holds only {low} to {high}. Nothing was sent.")
    if len(data) < field.end:
        data.extend(bytes(field.end - len(data)))
    whole = int.from_bytes(data[field.byte : field.end], field.endian, signed=False)
    mask = ((1 << field.width) - 1) << field.bit
    whole = (whole & ~mask) | ((raw & ((1 << field.width) - 1)) << field.bit)
    data[field.byte : field.end] = whole.to_bytes(field.length, field.endian)


def check_channel(name: str, spec: Any, field: BitField, *, sends: bool) -> None:
    """Refuse a map that can't carry the channel's or argument's type and unit. Raises DriverError.

    `sends` is true for write channels and action arguments, whose enum values all need a raw value.
    """
    if spec.type in ("string", "image"):
        raise DriverError(f"{name} is a {spec.type} channel. Integer fields carry number, bool and enum channels.")
    if spec.type == "number" and field.unit and spec.unit:
        try:
            convert(Quantity(1.0, parse_unit(field.unit)), spec.unit)
        except UnitError:
            raise DriverError(f"{name}: map.unit {field.unit} doesn't convert to the channel's {spec.unit}.") from None
    if spec.type == "enum":
        missing = [value for value in spec.values if value not in field.lookup.values()]
        if sends and missing:
            raise DriverError(f"{name}: map.lookup has no raw value for {', '.join(missing)}.")
        strays = [word for word in field.lookup.values() if word not in spec.values]
        if strays:
            raise DriverError(f"{name}: map.lookup names {', '.join(strays)}, which the channel's values don't list.")
        if not field.lookup:
            raise DriverError(f"{name} is an enum channel and needs map.lookup from raw numbers to its values.")


def to_value(raw: int, spec: ReadChannel | WriteChannel, field: BitField, where: str) -> float | bool | str:
    """Turn a raw integer into a value of the channel's type, in the channel's unit."""
    if spec.type == "bool":
        if raw == field.on:
            return True
        if raw == field.off:
            return False
        raise DriverError(f"{where} carried raw {raw}, which is neither on ({field.on}) nor off ({field.off}).")
    if spec.type == "enum":
        word = field.lookup.get(raw)
        if word is None:
            raise DriverError(f"{where} carried raw {raw}, which map.lookup doesn't name.")
        return word
    value = raw * field.scale + field.offset
    if field.unit and spec.unit and field.unit != spec.unit:
        value = convert(Quantity(value, parse_unit(field.unit)), spec.unit)
    return value


def to_raw(value: Any, spec: WriteChannel | Any, field: BitField, where: str) -> tuple[int, float | bool | str]:
    """Turn a checked channel value into a raw integer and the value that raw integer stands for."""
    kind = getattr(spec, "type", "number")
    if kind == "bool":
        return (field.on if value else field.off), bool(value)
    if kind == "enum":
        for raw, word in field.lookup.items():
            if word == value:
                return raw, word
        raise DriverError(f"{where}: map.lookup has no raw value for {value!r}.")
    number = float(value)
    unit = getattr(spec, "unit", None)
    if field.unit and unit and field.unit != unit:
        number = convert(Quantity(number, parse_unit(unit)), field.unit)
    raw = round((number - field.offset) / field.scale)
    sent = raw * field.scale + field.offset
    if field.unit and unit and field.unit != unit:
        sent = convert(Quantity(sent, parse_unit(field.unit)), unit)
    return raw, sent


def suspect(value: Any, spec: ReadChannel | WriteChannel) -> bool:
    """True for a number outside the read channel's declared range."""
    limits = getattr(spec, "range", None)
    return bool(limits is not None and isinstance(value, float) and not limits[0] <= value <= limits[1])
