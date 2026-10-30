"""How device file channels and actions map onto Alpaca members, with conventions per device type.

A map names the Alpaca member and how its value relates to the channel.

    read    { property: rightascension, unit: deg, scale: 15 }
            { property: shutterstatus, states: [open, closed, opening, closing, error] }
            { switch: 2 }                       getswitch or getswitchvalue with Id=2
    write   { property: tracking, param: Tracking }
            { method: move, param: Position, integer: true, readback: position }
            { switch: 2 }                       setswitch or setswitchvalue with Id=2
    action  { method: slewtocoordinatesasync,
              params: { right_ascension: { name: RightAscension, unit: deg, scale: 15 } } }

`scale` turns the protocol value into the map's unit. Alpaca gives right ascension and
sidereal time in hours, and 1 hour of right ascension is 15 degrees. Any map may name another
`device` and `number` on the same server.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from openhal.drivers.base import DriverError

MEMBER = r"^[a-z][a-z0-9]{1,63}$"
PARAM = r"^[A-Z][A-Za-z0-9]{0,63}$"
DEVICE_TYPES: Final = (
    "telescope",
    "focuser",
    "camera",
    "switch",
    "dome",
    "filterwheel",
    "rotator",
    "covercalibrator",
    "safetymonitor",
    "observingconditions",
)


class _Map(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    device: str | None = Field(default=None, pattern=r"^[a-z]+$")
    number: int | None = Field(default=None, ge=0, le=999)

    @field_validator("device")
    @classmethod
    def _known(cls, value: str | None) -> str | None:
        if value is not None and value not in DEVICE_TYPES:
            raise ValueError(f"unknown Alpaca device type, use one of {', '.join(DEVICE_TYPES)}")
        return value


class ReadMap(_Map):
    property: str | None = Field(default=None, pattern=MEMBER)
    switch: int | None = Field(default=None, ge=0, le=255)
    unit: str | None = None
    scale: float = 1.0
    states: list[str] | None = None

    @model_validator(mode="after")
    def _one(self) -> ReadMap:
        if (self.property is None) == (self.switch is None):
            raise ValueError("give exactly one of property or switch.")
        return self


class WriteMap(_Map):
    property: str | None = Field(default=None, pattern=MEMBER)
    method: str | None = Field(default=None, pattern=MEMBER)
    switch: int | None = Field(default=None, ge=0, le=255)
    param: str | None = Field(default=None, pattern=PARAM)
    readback: str | None = Field(default=None, pattern=MEMBER)
    unit: str | None = None
    scale: float = 1.0
    integer: bool = False

    @model_validator(mode="after")
    def _one(self) -> WriteMap:
        if sum(item is not None for item in (self.property, self.method, self.switch)) != 1:
            raise ValueError("give exactly one of property, method or switch.")
        if self.switch is None and self.param is None:
            raise ValueError("give param, the Alpaca parameter name, for example Tracking.")
        if self.method is not None and self.readback is None:
            raise ValueError("a method write needs readback, the property to read the value from.")
        return self


class ParamMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=PARAM)
    unit: str | None = None
    scale: float = 1.0
    integer: bool = False


class ActionMap(_Map):
    method: str = Field(pattern=MEMBER)
    params: dict[str, ParamMap] = {}
    wait: str | None = Field(default=None, pattern=MEMBER)
    """A boolean property that is true while the action runs, such as slewing or ismoving."""


DEG_FROM_HOURS: Final = {"unit": "deg", "scale": 15.0}
STATES: Final = {
    "camerastate": ["idle", "waiting", "exposing", "reading", "download", "error"],
    "shutterstatus": ["open", "closed", "opening", "closing", "error"],
    "coverstate": ["not_present", "closed", "moving", "open", "unknown", "error"],
    "calibratorstate": ["not_present", "off", "not_ready", "ready", "unknown", "error"],
}

READS: Final[dict[str, dict[str, dict[str, Any]]]] = {
    "telescope": {
        "right_ascension": {"property": "rightascension", **DEG_FROM_HOURS},
        "declination": {"property": "declination", "unit": "deg"},
        "altitude": {"property": "altitude", "unit": "deg"},
        "azimuth": {"property": "azimuth", "unit": "deg"},
        "sidereal_time": {"property": "siderealtime", **DEG_FROM_HOURS},
        "slewing": {"property": "slewing"},
        "at_park": {"property": "atpark"},
        "at_home": {"property": "athome"},
        "tracking": {"property": "tracking"},
    },
    "focuser": {
        "is_moving": {"property": "ismoving"},
        "temperature": {"property": "temperature", "unit": "degC"},
        "max_step": {"property": "maxstep", "unit": "dimensionless"},
    },
    "camera": {
        "ccd_temperature": {"property": "ccdtemperature", "unit": "degC"},
        "camera_state": {"property": "camerastate", "states": STATES["camerastate"]},
        "image_ready": {"property": "imageready"},
        "percent_completed": {"property": "percentcompleted", "unit": "percent"},
        "cooler_power": {"property": "coolerpower", "unit": "percent"},
    },
    "dome": {
        "azimuth": {"property": "azimuth", "unit": "deg"},
        "altitude": {"property": "altitude", "unit": "deg"},
        "shutter": {"property": "shutterstatus", "states": STATES["shutterstatus"]},
        "slewing": {"property": "slewing"},
        "at_park": {"property": "atpark"},
        "at_home": {"property": "athome"},
    },
    "switch": {},
}
WRITES: Final[dict[str, dict[str, dict[str, Any]]]] = {
    "telescope": {"tracking": {"property": "tracking", "param": "Tracking"}},
    "focuser": {
        "position": {
            "method": "move",
            "param": "Position",
            "integer": True,
            "readback": "position",
            "unit": "dimensionless",
        },
    },
    "camera": {
        "cooler": {"property": "cooleron", "param": "CoolerOn"},
        "target_temperature": {"property": "setccdtemperature", "param": "SetCCDTemperature", "unit": "degC"},
        "gain": {"property": "gain", "param": "Gain", "integer": True, "unit": "dimensionless"},
    },
    "dome": {},
    "switch": {},
}
ACTIONS: Final[dict[str, dict[str, dict[str, Any]]]] = {
    "telescope": {
        "abort_slew": {"method": "abortslew"},
        "park": {"method": "park", "wait": "slewing"},
        "unpark": {"method": "unpark"},
        "find_home": {"method": "findhome", "wait": "slewing"},
        "slew_to_coordinates": {
            "method": "slewtocoordinatesasync",
            "wait": "slewing",
            "params": {
                "right_ascension": {"name": "RightAscension", **DEG_FROM_HOURS},
                "declination": {"name": "Declination", "unit": "deg"},
            },
        },
        "slew_to_alt_az": {
            "method": "slewtoaltazasync",
            "wait": "slewing",
            "params": {"azimuth": {"name": "Azimuth", "unit": "deg"}, "altitude": {"name": "Altitude", "unit": "deg"}},
        },
    },
    "focuser": {"halt": {"method": "halt"}},
    "camera": {
        "start_exposure": {
            "method": "startexposure",
            "params": {"duration": {"name": "Duration", "unit": "s"}, "light": {"name": "Light"}},
        },
        "abort_exposure": {"method": "abortexposure"},
        "stop_exposure": {"method": "stopexposure"},
    },
    "dome": {
        "abort_slew": {"method": "abortslew"},
        "park": {"method": "park", "wait": "slewing"},
        "find_home": {"method": "findhome", "wait": "slewing"},
        "open_shutter": {"method": "openshutter"},
        "close_shutter": {"method": "closeshutter"},
        "slew_to_azimuth": {
            "method": "slewtoazimuth",
            "wait": "slewing",
            "params": {"azimuth": {"name": "Azimuth", "unit": "deg"}},
        },
    },
    "switch": {},
}
SAFE_METHODS: Final[dict[str, tuple[str, ...]]] = {
    "telescope": ("abortslew",),
    "dome": ("abortslew",),
    "focuser": ("halt",),
    "camera": ("abortexposure",),
}
"""The native safe state per device type. Switches have none, the file's own steps apply."""


def _switch_default(name: str) -> dict[str, Any] | None:
    prefix, _, number = name.partition("_")
    return {"switch": int(number)} if prefix == "switch" and number.isdigit() else None


def default_read(device_type: str, name: str) -> dict[str, Any] | None:
    found = READS.get(device_type, {}).get(name)
    return found if found is not None else (_switch_default(name) if device_type == "switch" else None)


def default_write(device_type: str, name: str) -> dict[str, Any] | None:
    found = WRITES.get(device_type, {}).get(name)
    return found if found is not None else (_switch_default(name) if device_type == "switch" else None)


def default_action(device_type: str, name: str) -> dict[str, Any] | None:
    return ACTIONS.get(device_type, {}).get(name)


def validate(model: type[BaseModel], raw: dict[str, Any] | None, default: dict[str, Any] | None, where: str) -> Any:
    data = raw if raw is not None else default
    if data is None:
        raise DriverError(
            f"{where} is not an Alpaca member the driver supports. Add a map, see docs/drivers/alpaca.md."
        )
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'map'}: {e['msg']}" for e in exc.errors())
        raise DriverError(f"{where}.map is not valid for the Alpaca driver ({problems}).") from exc
