"""How device file channels and actions map onto ROS 2 topics, services and actions.

    read    { topic: /battery_state, type: sensor_msgs/msg/BatteryState, field: percentage, unit: dimensionless }
    write   { topic: /cmd_vel, type: geometry_msgs/msg/Twist, field: linear.x, unit: m/s }
            { service: /set_lamp, type: std_srvs/srv/SetBool, field: data }
    action  { service: /reset_odometry, type: std_srvs/srv/Trigger }
            { action: /navigate, type: turtle_msgs/action/Navigate, args: { x: pose.x, y: { field: pose.y, unit: m } } }
            { topic: /goal, type: geometry_msgs/msg/Point, args: { x: x, y: y } }

`field` is a dotted path into the message, with numbers for list items (`ranges.0`). `base`
holds the rest of the message, so a change to `linear.x` publishes a whole Twist with zeros
elsewhere. `unit` is the unit ROS uses for the field (REP 103 specifies SI) and `scale` multiplies the
ROS value into it. `integer: true` sends whole numbers for int fields.
"""

from __future__ import annotations

import copy
import math
import re
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from openhal.drivers.base import DriverError

NAME: Final = r"^/[A-Za-z0-9_/~]{0,254}$"
TYPE: Final = r"^[A-Za-z][A-Za-z0-9_]*/(msg|srv|action)/[A-Za-z][A-Za-z0-9_]*$"
PATH: Final = r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+){0,15}$"


class _Endpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    topic: str | None = Field(default=None, pattern=NAME)
    service: str | None = Field(default=None, pattern=NAME)
    action: str | None = Field(default=None, pattern=NAME)
    type: str | None = Field(default=None, pattern=TYPE)
    base: dict[str, Any] = {}

    def _one(self, allowed: tuple[str, ...]) -> None:
        given = [name for name in ("topic", "service", "action") if getattr(self, name) is not None]
        if len(given) != 1 or given[0] not in allowed:
            raise ValueError(f"give exactly one of {', '.join(allowed)}.")


class ReadMap(_Endpoint):
    field: str = Field(pattern=PATH)
    unit: str | None = None
    scale: float = 1.0

    @model_validator(mode="after")
    def _shape(self) -> ReadMap:
        self._one(("topic",))
        return self


class WriteMap(_Endpoint):
    field: str = Field(pattern=PATH)
    unit: str | None = None
    scale: float = 1.0
    integer: bool = False

    @model_validator(mode="after")
    def _shape(self) -> WriteMap:
        self._one(("topic", "service"))
        if self.topic is not None and self.type is None:
            raise ValueError("publishing needs type, for example geometry_msgs/msg/Twist.")
        return self


class ArgMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str = Field(pattern=PATH)
    unit: str | None = None
    scale: float = 1.0
    integer: bool = False


class ActionMap(_Endpoint):
    args: dict[str, ArgMap | str] = {}

    @model_validator(mode="after")
    def _shape(self) -> ActionMap:
        self._one(("topic", "service", "action"))
        if (self.topic is not None or self.action is not None) and self.type is None:
            raise ValueError("topics and actions need type, for example nav2_msgs/action/NavigateToPose.")
        for name, arg in self.args.items():
            if isinstance(arg, str) and not re.match(PATH, arg):
                raise ValueError(f"args.{name} must be a field path such as pose.x.")
        return self

    def arg(self, name: str) -> ArgMap:
        raw = self.args[name]
        return ArgMap(field=raw) if isinstance(raw, str) else raw


def validate(model: type[BaseModel], raw: dict[str, Any] | None, where: str) -> Any:
    if raw is None:
        raise DriverError(f"{where} needs a map naming its ROS topic, service or action. See docs/drivers/ros2.md.")
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'map'}: {e['msg']}" for e in exc.errors())
        raise DriverError(f"{where}.map is not valid for the ROS 2 driver ({problems}).") from exc


def get_field(message: Any, path: str) -> Any:
    """Follow a dotted path into a message. Raises KeyError when it isn't there."""
    current = message
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise KeyError(path)
    return current


def with_field(base: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    """A copy of `base` with one field set, creating the objects on the way."""
    message = copy.deepcopy(base)
    current: Any = message
    parts = path.split(".")
    for part in parts[:-1]:
        if isinstance(current, list) and part.isdigit():
            current = current[int(part)]
            continue
        current = current.setdefault(part, {})
        if not isinstance(current, dict | list):
            raise DriverError(f"{path}: {part} in the base message is not an object.")
    last = parts[-1]
    if isinstance(current, list) and last.isdigit():
        current[int(last)] = value
    else:
        current[last] = value
    return message


def finite(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise DriverError(f"{where}: ROS sent {value!r}, not a finite number.")
    return float(value)
