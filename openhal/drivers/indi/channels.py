"""How device file channels and actions map onto INDI properties, with conventions per device kind.

    read    { property: EQUATORIAL_EOD_COORD, element: RA, unit: deg, scale: 15 }
            { property: TELESCOPE_TRACK_STATE, element: TRACK_ON }      a switch member as a bool
            { property: ON_COORD_SET }                                   the On member as an enum
            { property: EQUATORIAL_EOD_COORD, state: true }              the vector state, or true while Busy
    write   { property: TELESCOPE_TRACK_STATE, element: TRACK_ON, off: TRACK_OFF }
            { property: ABS_FOCUS_POSITION, element: FOCUS_ABSOLUTE_POSITION }
    action  { property: TELESCOPE_ABORT_MOTION, element: ABORT }          turn one switch member on
            { property: EQUATORIAL_EOD_COORD, args: { ra: { element: RA, unit: deg, scale: 15 } },
              before: [{ property: ON_COORD_SET, element: TRACK }], wait: true }

`scale` turns the protocol value into the map's unit. INDI gives right ascension in hours, and
1 hour of right ascension is 15 degrees. Any map may name another `device` on the same server.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from openhal.drivers.base import DriverError

NAME = r"^[A-Za-z0-9_.\-]{1,64}$"
DEG_FROM_HOURS: Final = {"unit": "deg", "scale": 15.0}


class _Map(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    device: str | None = Field(default=None, min_length=1, max_length=128)
    property: str = Field(pattern=NAME)


class ReadMap(_Map):
    element: str | None = Field(default=None, pattern=NAME)
    state: bool = False
    unit: str | None = None
    scale: float = 1.0

    @model_validator(mode="after")
    def _shape(self) -> ReadMap:
        if self.state and self.element is not None:
            raise ValueError("give element or state, not both.")
        return self


class WriteMap(_Map):
    element: str | None = Field(default=None, pattern=NAME)
    off: str | None = Field(default=None, pattern=NAME)
    unit: str | None = None
    scale: float = 1.0


class ArgMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    element: str = Field(pattern=NAME)
    unit: str | None = None
    scale: float = 1.0


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    device: str | None = Field(default=None, min_length=1, max_length=128)
    property: str = Field(pattern=NAME)
    element: str = Field(pattern=NAME)


class ActionMap(_Map):
    element: str | None = Field(default=None, pattern=NAME)
    args: dict[str, ArgMap] = {}
    before: list[Step] = []
    wait: bool = False

    @model_validator(mode="after")
    def _shape(self) -> ActionMap:
        if (self.element is None) == (not self.args):
            raise ValueError("give element (a switch to turn on) or args (number or text members), not both.")
        return self


READS: Final[dict[str, dict[str, dict[str, Any]]]] = {
    "telescope": {
        "right_ascension": {"property": "EQUATORIAL_EOD_COORD", "element": "RA", **DEG_FROM_HOURS},
        "declination": {"property": "EQUATORIAL_EOD_COORD", "element": "DEC", "unit": "deg"},
        "altitude": {"property": "HORIZONTAL_COORD", "element": "ALT", "unit": "deg"},
        "azimuth": {"property": "HORIZONTAL_COORD", "element": "AZ", "unit": "deg"},
        "slewing": {"property": "EQUATORIAL_EOD_COORD", "state": True},
        "parked": {"property": "TELESCOPE_PARK", "element": "PARK"},
        "tracking": {"property": "TELESCOPE_TRACK_STATE", "element": "TRACK_ON"},
    },
    "focuser": {
        "position": {"property": "ABS_FOCUS_POSITION", "element": "FOCUS_ABSOLUTE_POSITION"},
        "moving": {"property": "ABS_FOCUS_POSITION", "state": True},
        "temperature": {"property": "FOCUS_TEMPERATURE", "element": "TEMPERATURE", "unit": "degC"},
    },
    "camera": {
        "ccd_temperature": {"property": "CCD_TEMPERATURE", "element": "CCD_TEMPERATURE_VALUE", "unit": "degC"},
        "cooler": {"property": "CCD_COOLER", "element": "COOLER_ON"},
        "exposure_left": {"property": "CCD_EXPOSURE", "element": "CCD_EXPOSURE_VALUE", "unit": "s"},
        "exposing": {"property": "CCD_EXPOSURE", "state": True},
    },
}
WRITES: Final[dict[str, dict[str, dict[str, Any]]]] = {
    "telescope": {"tracking": {"property": "TELESCOPE_TRACK_STATE", "element": "TRACK_ON", "off": "TRACK_OFF"}},
    "focuser": {"position": {"property": "ABS_FOCUS_POSITION", "element": "FOCUS_ABSOLUTE_POSITION"}},
    "camera": {
        "cooler": {"property": "CCD_COOLER", "element": "COOLER_ON", "off": "COOLER_OFF"},
        "target_temperature": {"property": "CCD_TEMPERATURE", "element": "CCD_TEMPERATURE_VALUE", "unit": "degC"},
    },
}
ACTIONS: Final[dict[str, dict[str, dict[str, Any]]]] = {
    "telescope": {
        "abort": {"property": "TELESCOPE_ABORT_MOTION", "element": "ABORT"},
        "park": {"property": "TELESCOPE_PARK", "element": "PARK", "wait": True},
        "unpark": {"property": "TELESCOPE_PARK", "element": "UNPARK", "wait": True},
        "slew_to_coordinates": {
            "property": "EQUATORIAL_EOD_COORD",
            "args": {
                "right_ascension": {"element": "RA", **DEG_FROM_HOURS},
                "declination": {"element": "DEC", "unit": "deg"},
            },
            "before": [{"property": "ON_COORD_SET", "element": "TRACK"}],
            "wait": True,
        },
    },
    "focuser": {"abort": {"property": "FOCUS_ABORT_MOTION", "element": "ABORT"}},
    "camera": {
        "start_exposure": {
            "property": "CCD_EXPOSURE",
            "args": {"duration": {"element": "CCD_EXPOSURE_VALUE", "unit": "s"}},
        },
        "abort_exposure": {"property": "CCD_ABORT_EXPOSURE", "element": "ABORT"},
    },
}
SAFE: Final[dict[str, tuple[str, str]]] = {
    "telescope": ("TELESCOPE_ABORT_MOTION", "ABORT"),
    "focuser": ("FOCUS_ABORT_MOTION", "ABORT"),
    "camera": ("CCD_ABORT_EXPOSURE", "ABORT"),
}
"""The native safe state per kind. A `generic` device has none, the file's own steps apply."""


def validate(model: type[BaseModel], raw: dict[str, Any] | None, default: dict[str, Any] | None, where: str) -> Any:
    data = raw if raw is not None else default
    if data is None:
        raise DriverError(f"{where} is not an INDI property the driver supports. Add a map, see docs/drivers/indi.md.")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'map'}: {e['msg']}" for e in exc.errors())
        raise DriverError(f"{where}.map is not valid for the INDI driver ({problems}).") from exc
