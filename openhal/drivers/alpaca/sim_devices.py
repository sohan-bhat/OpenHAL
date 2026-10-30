"""Simulated Alpaca devices. A telescope, a focuser, a camera, a switch and a dome.

Each follows the members and errors of its ASCOM interface (ITelescopeV3, IFocuserV3, ICameraV3,
ISwitchV2, IDomeV2) as the Alpaca API reference lists them. Motion takes simulated time scaled by
the server's `time_scale`. Members other than the common identity ones return NotConnected
(0x407) until `connected` is set.
"""

from __future__ import annotations

import time
from typing import Any, Protocol

from openhal.drivers.alpaca.client import (
    INVALID_OPERATION,
    INVALID_VALUE,
    INVALID_WHILE_PARKED,
    NOT_CONNECTED,
    NOT_IMPLEMENTED,
)


class Clock(Protocol):
    time_scale: float


COMMON = frozenset({"connected", "name", "description", "driverinfo", "driverversion", "interfaceversion"})


class SimError(Exception):
    def __init__(self, number: int, message: str) -> None:
        super().__init__(message)
        self.number = number


class BadRequest(Exception):  # noqa: N818
    """Returned as HTTP 400."""


def _number(params: dict[str, str], name: str) -> float:
    if name not in params:
        raise BadRequest(f"missing parameter {name}")
    try:
        return float(params[name])
    except ValueError:
        raise BadRequest(f"{name} is not a number") from None


def _flag(params: dict[str, str], name: str) -> bool:
    text = params.get(name)
    if text not in ("True", "False", "true", "false"):
        raise BadRequest(f"{name} must be True or False")
    return text.lower() == "true"


class SimDevice:
    kind = ""
    interface = 1
    abilities: frozenset[str] = frozenset()

    def __init__(self, sim: Clock, name: str) -> None:
        self.sim = sim
        self.name = name
        self.connected = False

    def now(self) -> float:
        return time.monotonic() * self.sim.time_scale

    def get(self, member: str, params: dict[str, str]) -> Any:
        common = {
            "connected": self.connected,
            "name": self.name,
            "description": f"Simulated {self.kind}",
            "driverinfo": "OpenHAL Alpaca simulator",
            "driverversion": "1.0",
            "interfaceversion": self.interface,
            "supportedactions": [],
        }
        if member in common:
            return common[member]
        self._need_connection(member)
        if member.startswith("can") and member != "canwrite":
            return member in self.abilities
        handler = getattr(self, f"get_{member}", None)
        if handler is None:
            raise SimError(NOT_IMPLEMENTED, f"{member} is not implemented")
        return handler(params)

    def put(self, member: str, params: dict[str, str]) -> Any:
        if member == "connected":
            self.connected = _flag(params, "Connected")
            return None
        self._need_connection(member)
        handler = getattr(self, f"put_{member}", None)
        if handler is None:
            raise SimError(NOT_IMPLEMENTED, f"{member} is not implemented")
        return handler(params)

    def _need_connection(self, member: str) -> None:
        if not self.connected and member not in COMMON:
            raise SimError(NOT_CONNECTED, f"{self.name} is not connected")


class Telescope(SimDevice):
    kind = "telescope"
    interface = 3
    abilities = frozenset(
        {"canpark", "canunpark", "canfindhome", "canslewasync", "canslewaltazasync", "cansettracking"}
    )

    def __init__(self, sim: Clock) -> None:
        super().__init__(sim, "Sim Mount")
        self.ra, self.dec = 5.5, 22.0
        self.alt, self.az = 45.0, 180.0
        self.tracking = False
        self.parked = False
        self.home = False
        self.slew_s = 1.0
        self._slew: tuple[float, dict[str, float]] | None = None

    def _step(self) -> None:
        if self._slew is not None and self.now() >= self._slew[0]:
            for key, value in self._slew[1].items():
                setattr(self, key, value)
            self._slew = None

    def _start(self, target: dict[str, float]) -> None:
        self._slew = (self.now() + self.slew_s, target)

    def get_rightascension(self, _: dict[str, str]) -> float:
        self._step()
        return self.ra

    def get_declination(self, _: dict[str, str]) -> float:
        self._step()
        return self.dec

    def get_altitude(self, _: dict[str, str]) -> float:
        self._step()
        return self.alt

    def get_azimuth(self, _: dict[str, str]) -> float:
        self._step()
        return self.az

    def get_siderealtime(self, _: dict[str, str]) -> float:
        return 6.25

    def get_slewing(self, _: dict[str, str]) -> bool:
        self._step()
        return self._slew is not None

    def get_atpark(self, _: dict[str, str]) -> bool:
        self._step()
        return self.parked

    def get_athome(self, _: dict[str, str]) -> bool:
        return self.home

    def get_tracking(self, _: dict[str, str]) -> bool:
        return self.tracking

    def put_tracking(self, params: dict[str, str]) -> None:
        tracking = _flag(params, "Tracking")
        if tracking and self.parked:
            raise SimError(INVALID_WHILE_PARKED, "the mount is parked")
        self.tracking = tracking

    def put_abortslew(self, _: dict[str, str]) -> None:
        if self.parked:
            raise SimError(INVALID_WHILE_PARKED, "the mount is parked")
        self._slew = None

    def put_park(self, _: dict[str, str]) -> None:
        self.tracking = False
        self.home = False
        self._start({"alt": 0.0, "az": 0.0, "parked": True})

    def put_unpark(self, _: dict[str, str]) -> None:
        self.parked = False

    def put_findhome(self, _: dict[str, str]) -> None:
        if self.parked:
            raise SimError(INVALID_WHILE_PARKED, "the mount is parked")
        self._start({"alt": 90.0, "az": 0.0, "home": True})

    def put_slewtocoordinatesasync(self, params: dict[str, str]) -> None:
        ra, dec = _number(params, "RightAscension"), _number(params, "Declination")
        if self.parked:
            raise SimError(INVALID_WHILE_PARKED, "the mount is parked")
        if not self.tracking:
            raise SimError(INVALID_OPERATION, "tracking must be on for an equatorial slew")
        if not (0 <= ra < 24 and -90 <= dec <= 90):
            raise SimError(INVALID_VALUE, f"RightAscension {ra} or Declination {dec} is out of range")
        self.home = False
        self._start({"ra": ra, "dec": dec})

    def put_slewtoaltazasync(self, params: dict[str, str]) -> None:
        az, alt = _number(params, "Azimuth"), _number(params, "Altitude")
        if self.parked:
            raise SimError(INVALID_WHILE_PARKED, "the mount is parked")
        if self.tracking:
            raise SimError(INVALID_OPERATION, "tracking must be off for an alt-az slew")
        if not (0 <= az < 360 and -90 <= alt <= 90):
            raise SimError(INVALID_VALUE, f"Azimuth {az} or Altitude {alt} is out of range")
        self.home = False
        self._start({"az": az, "alt": alt})


class Focuser(SimDevice):
    kind = "focuser"
    interface = 3

    def __init__(self, sim: Clock) -> None:
        super().__init__(sim, "Sim Focuser")
        self.position = 10000
        self.target = 10000
        self.started = 0.0
        self.steps_per_s = 2000.0
        self.max_step = 50000

    def _current(self) -> int:
        travelled = (self.now() - self.started) * self.steps_per_s
        if abs(self.target - self.position) <= travelled:
            self.position = self.target
            return self.position
        direction = 1 if self.target > self.position else -1
        return int(self.position + direction * travelled)

    def get_position(self, _: dict[str, str]) -> int:
        return self._current()

    def get_ismoving(self, _: dict[str, str]) -> bool:
        return self._current() != self.target

    def get_temperature(self, _: dict[str, str]) -> float:
        return 12.5

    def get_maxstep(self, _: dict[str, str]) -> int:
        return self.max_step

    def get_maxincrement(self, _: dict[str, str]) -> int:
        return self.max_step

    def get_absolute(self, _: dict[str, str]) -> bool:
        return True

    def put_move(self, params: dict[str, str]) -> None:
        raw = params.get("Position", "")
        if not raw.lstrip("-").isdigit():
            raise BadRequest("Position must be an integer")
        target = int(raw)
        if not 0 <= target <= self.max_step:
            raise SimError(INVALID_VALUE, f"Position {target} is outside 0 to {self.max_step}")
        self.position = self._current()
        self.target = target
        self.started = self.now()

    def put_halt(self, _: dict[str, str]) -> None:
        self.position = self._current()
        self.target = self.position


class Camera(SimDevice):
    kind = "camera"
    interface = 3
    abilities = frozenset({"cansetccdtemperature", "canabortexposure", "canstopexposure"})

    def __init__(self, sim: Clock) -> None:
        super().__init__(sim, "Sim Camera")
        self.cooler = False
        self.setpoint = 0.0
        self.gain = 100
        self.exposure: tuple[float, float] | None = None
        self.ready = False

    def _state(self) -> int:
        if self.exposure is None:
            return 0
        start, duration = self.exposure
        if self.now() >= start + duration:
            self.exposure = None
            self.ready = True
            return 0
        return 2

    def get_camerastate(self, _: dict[str, str]) -> int:
        return self._state()

    def get_ccdtemperature(self, _: dict[str, str]) -> float:
        return self.setpoint if self.cooler else 18.0

    def get_coolerpower(self, _: dict[str, str]) -> float:
        return 35.0 if self.cooler else 0.0

    def get_cooleron(self, _: dict[str, str]) -> bool:
        return self.cooler

    def put_cooleron(self, params: dict[str, str]) -> None:
        self.cooler = _flag(params, "CoolerOn")

    def get_setccdtemperature(self, _: dict[str, str]) -> float:
        return self.setpoint

    def put_setccdtemperature(self, params: dict[str, str]) -> None:
        value = _number(params, "SetCCDTemperature")
        if not -50 <= value <= 30:
            raise SimError(INVALID_VALUE, f"SetCCDTemperature {value} is out of range")
        self.setpoint = value

    def get_gain(self, _: dict[str, str]) -> int:
        return self.gain

    def put_gain(self, params: dict[str, str]) -> None:
        raw = params.get("Gain", "")
        if not raw.isdigit():
            raise BadRequest("Gain must be an integer")
        self.gain = int(raw)

    def get_imageready(self, _: dict[str, str]) -> bool:
        self._state()
        return self.ready

    def get_percentcompleted(self, _: dict[str, str]) -> float:
        if self._state() != 2 or self.exposure is None:
            return 100.0 if self.ready else 0.0
        start, duration = self.exposure
        return min(100.0, (self.now() - start) / duration * 100.0)

    def put_startexposure(self, params: dict[str, str]) -> None:
        duration = _number(params, "Duration")
        _flag(params, "Light")
        if duration < 0:
            raise SimError(INVALID_VALUE, "Duration must not be negative")
        if self._state() != 0:
            raise SimError(INVALID_OPERATION, "an exposure is already running")
        self.ready = False
        self.exposure = (self.now(), max(duration, 0.001))

    def put_abortexposure(self, _: dict[str, str]) -> None:
        self.exposure = None

    def put_stopexposure(self, _: dict[str, str]) -> None:
        if self._state() == 2:
            self.exposure = None
            self.ready = True


class Switch(SimDevice):
    kind = "switch"
    interface = 2

    def __init__(self, sim: Clock) -> None:
        super().__init__(sim, "Sim Power Box")
        self.switches: list[dict[str, Any]] = [
            {"name": "Mount power", "min": 0.0, "max": 1.0, "step": 1.0, "value": 1.0, "write": True},
            {"name": "Dew heater", "min": 0.0, "max": 100.0, "step": 1.0, "value": 0.0, "write": True},
            {"name": "Input voltage", "min": 0.0, "max": 20.0, "step": 0.1, "value": 12.3, "write": False},
            {"name": "Camera power", "min": 0.0, "max": 1.0, "step": 1.0, "value": 0.0, "write": True},
        ]

    def _switch(self, params: dict[str, str]) -> dict[str, Any]:
        raw = params.get("id") or params.get("Id") or ""
        if not raw.isdigit():
            raise BadRequest("Id must be an integer")
        index = int(raw)
        if index >= len(self.switches):
            raise SimError(INVALID_VALUE, f"Id {index} is outside 0 to {len(self.switches) - 1}")
        return self.switches[index]

    def get_maxswitch(self, _: dict[str, str]) -> int:
        return len(self.switches)

    def get_getswitchname(self, params: dict[str, str]) -> str:
        return str(self._switch(params)["name"])

    def get_canwrite(self, params: dict[str, str]) -> bool:
        return bool(self._switch(params)["write"])

    def get_getswitch(self, params: dict[str, str]) -> bool:
        item = self._switch(params)
        return bool(item["value"] > item["min"])

    def get_getswitchvalue(self, params: dict[str, str]) -> float:
        return float(self._switch(params)["value"])

    def get_minswitchvalue(self, params: dict[str, str]) -> float:
        return float(self._switch(params)["min"])

    def get_maxswitchvalue(self, params: dict[str, str]) -> float:
        return float(self._switch(params)["max"])

    def get_switchstep(self, params: dict[str, str]) -> float:
        return float(self._switch(params)["step"])

    def put_setswitch(self, params: dict[str, str]) -> None:
        item = self._switch(params)
        if not item["write"]:
            raise SimError(NOT_IMPLEMENTED, f"{item['name']} is read only")
        item["value"] = item["max"] if _flag(params, "State") else item["min"]

    def put_setswitchvalue(self, params: dict[str, str]) -> None:
        item = self._switch(params)
        value = _number(params, "Value")
        if not item["write"]:
            raise SimError(NOT_IMPLEMENTED, f"{item['name']} is read only")
        if not item["min"] <= value <= item["max"]:
            raise SimError(INVALID_VALUE, f"Value {value} is outside {item['min']} to {item['max']}")
        item["value"] = value


class Dome(SimDevice):
    kind = "dome"
    interface = 2
    abilities = frozenset({"canpark", "canfindhome", "cansetshutter", "cansetazimuth"})

    def __init__(self, sim: Clock) -> None:
        super().__init__(sim, "Sim Dome")
        self.az = 90.0
        self.shutter = 1
        self.parked = False
        self.home = False
        self.move_s = 1.0
        self._slew: tuple[float, float] | None = None
        self._shutter: tuple[float, int] | None = None

    def _step(self) -> None:
        now = self.now()
        if self._slew is not None and now >= self._slew[0]:
            self.az = self._slew[1]
            self._slew = None
        if self._shutter is not None and now >= self._shutter[0]:
            self.shutter = self._shutter[1]
            self._shutter = None

    def get_azimuth(self, _: dict[str, str]) -> float:
        self._step()
        return self.az

    def get_altitude(self, _: dict[str, str]) -> float:
        return 0.0

    def get_shutterstatus(self, _: dict[str, str]) -> int:
        self._step()
        return self.shutter

    def get_slewing(self, _: dict[str, str]) -> bool:
        self._step()
        return self._slew is not None or self._shutter is not None

    def get_atpark(self, _: dict[str, str]) -> bool:
        self._step()
        return self.parked

    def get_athome(self, _: dict[str, str]) -> bool:
        return self.home

    def put_abortslew(self, _: dict[str, str]) -> None:
        self._slew = None
        if self._shutter is not None:
            self._shutter = None
            self.shutter = 4

    def put_slewtoazimuth(self, params: dict[str, str]) -> None:
        az = _number(params, "Azimuth")
        if not 0 <= az < 360:
            raise SimError(INVALID_VALUE, f"Azimuth {az} is out of range")
        self.parked = False
        self._slew = (self.now() + self.move_s, az)

    def put_park(self, _: dict[str, str]) -> None:
        self._slew = (self.now() + self.move_s, 180.0)
        self.parked = True

    def put_findhome(self, _: dict[str, str]) -> None:
        self._slew = (self.now() + self.move_s, 0.0)
        self.home = True

    def put_openshutter(self, _: dict[str, str]) -> None:
        self.shutter = 2
        self._shutter = (self.now() + self.move_s, 0)

    def put_closeshutter(self, _: dict[str, str]) -> None:
        self.shutter = 3
        self._shutter = (self.now() + self.move_s, 1)
