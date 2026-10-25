"""The onvif driver's parameters, channel maps and the PTZ operations its actions name."""

from __future__ import annotations

import math
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from openhal.spec.units import UnitError, parse_duration, parse_unit

INFO_FIELDS: Final = {
    "manufacturer": "Manufacturer",
    "model": "Model",
    "firmware": "FirmwareVersion",
    "serial": "SerialNumber",
    "hardware_id": "HardwareId",
}
TEXT_FIELDS: Final = (*INFO_FIELDS, "profile", "stream_uri", "snapshot_uri")
AXES: Final = ("pan", "tilt", "zoom")
OPERATIONS: Final = {
    "move": ("ContinuousMove", {"pan", "tilt", "zoom", "duration"}),
    "step": ("RelativeMove", {"pan", "tilt", "zoom"}),
    "go_to": ("AbsoluteMove", {"pan", "tilt", "zoom"}),
    "goto_preset": ("GotoPreset", {"preset"}),
    "home": ("GotoHomePosition", set()),
    "stop": ("Stop", set()),
}


def _seconds(value: Any) -> Any:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return parse_duration(value)


Duration = Annotated[float, BeforeValidator(_seconds), Field(gt=0, le=60)]


class OnvifParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=80, ge=1, le=65535)
    scheme: Literal["http", "https"] = "http"
    username: str | None = Field(default=None, max_length=64)
    token_env: str | None = Field(default=None, pattern=r"^[A-Z_][A-Z0-9_]{0,63}$")
    profile: str | None = Field(default=None, max_length=64)
    device_path: str = Field(default="/onvif/device_service", pattern=r"^/\S*$")
    move_timeout: Duration = 1.0
    timeout: Duration = 5.0


class ReadMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: Literal[
        "manufacturer",
        "model",
        "firmware",
        "serial",
        "hardware_id",
        "profile",
        "stream_uri",
        "snapshot_uri",
        "pan",
        "tilt",
        "zoom",
        "moving",
    ]
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


class ActionMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: Literal["move", "step", "go_to", "goto_preset", "home", "stop"]
