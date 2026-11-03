"""The mujoco driver's device file maps, and how channel units map onto the model's own units."""

from __future__ import annotations

import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, Literal

import mujoco
from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator, model_validator

from openhal.drivers.base import DriverError
from openhal.drivers.mujoco.simulator import Aim
from openhal.drivers.serial import mapping
from openhal.spec.models import Action, ArgSpec
from openhal.spec.units import Quantity, UnitError, convert, parse_quantity, parse_unit

Axis = Literal["x", "y", "z"]
AXES: tuple[Axis, Axis, Axis] = ("x", "y", "z")
ModelLoader = Callable[[], Any]
NAME = r"^[A-Za-z_][A-Za-z0-9_.\-]{0,99}$"


def _length(value: Any, what: str) -> float:
    try:
        return convert(parse_quantity(value), "m")
    except UnitError as exc:
        raise ValueError(f"{what} needs a length such as 1 mm ({exc}).") from exc


class MujocoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_env: str = Field(pattern=r"^[A-Z_][A-Z0-9_]{0,63}$")
    keyframe: str | None = Field(default=None, pattern=NAME)
    timestep: float | None = None
    action_wait: float = 8.0
    tolerance: float = 0.001
    aim_tolerance: float = math.radians(3)

    @field_validator("timestep", "action_wait", mode="before")
    @classmethod
    def _duration(cls, value: Any) -> Any:
        return None if value is None else mapping.duration(value)

    @field_validator("tolerance", mode="before")
    @classmethod
    def _tolerance(cls, value: Any) -> float:
        return _length(value, "tolerance")

    @field_validator("aim_tolerance", mode="before")
    @classmethod
    def _aim_tolerance(cls, value: Any) -> float:
        try:
            return convert(parse_quantity(value), "rad")
        except UnitError as exc:
            raise ValueError(f"aim_tolerance needs an angle such as 3 deg ({exc}).") from exc

    @model_validator(mode="after")
    def _ranges(self) -> MujocoParams:
        checks = (
            ("timestep", self.timestep, 1e-4, 0.05, "s"),
            ("action_wait", self.action_wait, 0.1, 9.0, "s"),
            ("tolerance", self.tolerance, 1e-4, 0.05, "m"),
            ("aim_tolerance", self.aim_tolerance, math.radians(0.1), math.radians(45), "rad"),
        )
        for name, value, low, high, unit in checks:
            if value is not None and not low <= value <= high:
                raise ValueError(f"{name} must be between {low:g} {unit} and {high:g} {unit}.")
        return self


class ReadMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    joint: str | None = Field(default=None, pattern=NAME)
    site: str | None = Field(default=None, pattern=NAME)
    body: str | None = Field(default=None, pattern=NAME)
    axis: Axis | None = None

    @model_validator(mode="after")
    def _one(self) -> ReadMap:
        given = [name for name in ("joint", "site", "body") if getattr(self, name) is not None]
        if len(given) != 1:
            raise ValueError("give exactly one of joint, site or body.")
        if (self.joint is None) != (self.axis is not None):
            raise ValueError("a site or a body needs an axis, x, y or z, and a joint takes none.")
        return self


class WriteMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    actuator: str = Field(pattern=NAME)
    unit: str | None = Field(default=None, max_length=40)


class Aiming(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    axis: tuple[float, float, float]
    toward: tuple[float, float, float]

    @field_validator("axis", "toward")
    @classmethod
    def _unit_vector(cls, value: tuple[float, float, float]) -> tuple[float, float, float]:
        size = math.sqrt(sum(part * part for part in value))
        if not math.isfinite(size) or size < 1e-9:
            raise ValueError("needs a direction, three numbers that aren't all zero.")
        x, y, z = (part / size for part in value)
        return x, y, z


class ActionMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command: Literal["move_to", "hold"]
    site: str | None = Field(default=None, pattern=NAME)
    axes: dict[str, Axis] = {}
    at: dict[Axis, float] = {}
    aim: Aiming | None = None
    joints: list[Annotated[str, Field(pattern=NAME)]] = Field(default=[], max_length=64)
    then: dict[str, float] = {}

    @field_validator("at", mode="before")
    @classmethod
    def _lengths(cls, value: Any, info: ValidationInfo) -> Any:
        if not isinstance(value, dict):
            return value
        return {axis: _length(raw, f"{info.field_name}.{axis}") for axis, raw in value.items()}

    @model_validator(mode="after")
    def _shape(self) -> ActionMap:
        moves = (self.site, self.axes, self.at, self.aim, self.joints, self.then)
        if self.command == "hold" and any(moves):
            raise ValueError("hold takes nothing but the command.")
        if self.command == "move_to" and self.site is None:
            raise ValueError("move_to needs the site to move.")
        return self


def validate(model: type[BaseModel], raw: dict[str, Any], where: str) -> Any:
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'map'}: {e['msg']}" for e in exc.errors())
        raise DriverError(f"{where}.map is not valid for the mujoco driver ({problems}).") from exc


def default_loader(variable: str) -> ModelLoader:
    """Load the MJCF file at the path in an environment variable. A device file never names a path."""

    def load() -> Any:
        path = os.environ.get(variable)
        if not path:
            raise DriverError(f"Set the {variable} environment variable to the path of the MJCF model.")
        try:
            return mujoco.MjModel.from_xml_path(os.path.expanduser(path))
        except ValueError as exc:
            raise DriverError(f"MuJoCo could not load the model named by {variable} ({exc}).") from exc

    return load


@dataclass(frozen=True)
class Scale:
    """A channel unit to the model's own unit, native = offset + factor * value."""

    factor: float
    offset: float

    def native(self, value: float) -> float:
        return self.offset + self.factor * value

    def channel(self, native: float) -> float:
        return (native - self.offset) / self.factor


def scale(unit: str | None, native: str, span: tuple[float, float] | None, where: str) -> Scale:
    """How a channel in `unit` maps onto a model value in `native`. Percent maps onto `span`."""
    if unit is None:
        return Scale(1.0, 0.0)
    if parse_unit(unit) == parse_unit("percent"):
        if span is None:
            raise DriverError(f"{where} is in percent, which needs a limited range in the model.")
        low, high = span
        return Scale((high - low) / 100.0, low)
    try:
        offset = convert(Quantity(0.0, parse_unit(unit)), native)
        factor = convert(Quantity(1.0, parse_unit(unit)), native) - offset
    except UnitError as exc:
        raise DriverError(f"{where} is in {native} in the model, which doesn't convert to {unit} ({exc}).") from exc
    return Scale(factor, offset)


@dataclass(frozen=True)
class Reader:
    kind: Literal["joint", "site", "body"]
    index: int
    axis: int
    scale: Scale


@dataclass(frozen=True)
class Writer:
    actuator: int
    scale: Scale
    speed: float | None
    low: float
    high: float


@dataclass(frozen=True)
class Plan:
    """A move_to resolved against the model."""

    site: int
    axes: dict[str, int]
    at: dict[int, float]
    aim: Aim | None
    chain: dict[int, str]
    then: dict[str, float]


def axes_of(action_map: ActionMap, spec: Action) -> dict[str, str]:
    """Which axis each argument sets. Arguments named x, y and z set their own axis unless map.axes says otherwise."""
    if action_map.axes:
        return dict(action_map.axes)
    return {arg: arg for arg in spec.args if arg in AXES}


def is_length(spec: ArgSpec) -> bool:
    assert spec.unit is not None
    try:
        convert(Quantity(1.0, parse_unit(spec.unit)), "m")
    except UnitError:
        return False
    return True
