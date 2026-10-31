"""How GRBL device file channels and actions map onto the controller, and what describe() proposes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from openhal.drivers.base import DriverError
from openhal.drivers.grbl import protocol
from openhal.spec.models import Action, DeviceFile
from openhal.spec.units import Quantity, UnitError, convert, parse_unit

COMMANDS = ("home", "jog", "move", "set_work_zero", "cancel_jog", "hold", "resume", "clear_alarm", "reset")
ZERO_AXES = {"x": "X0", "y": "Y0", "z": "Z0", "a": "A0", "xy": "X0 Y0", "xyz": "X0 Y0 Z0", "all": "X0 Y0 Z0"}
BOOL_SETTINGS = frozenset({4, 5, 6, 13, 20, 21, 22, 32})


class ReadMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["state", "alarm", "x", "y", "z", "a", "feed", "spindle", "pins"] | None = None
    frame: Literal["machine", "work"] = "machine"
    setting: int | None = Field(default=None, ge=0, le=255)

    @model_validator(mode="after")
    def _one(self) -> ReadMap:
        if (self.status is None) == (self.setting is None):
            raise ValueError("give exactly one of status or setting.")
        return self


class WriteMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    spindle: Literal["cw", "ccw"] | None = None
    laser: Literal["dynamic", "constant"] | None = None
    coolant: Literal["flood", "mist"] | None = None

    @model_validator(mode="after")
    def _one(self) -> WriteMap:
        if sum(item is not None for item in (self.spindle, self.laser, self.coolant)) != 1:
            raise ValueError("give exactly one of spindle, laser or coolant.")
        return self


class ActionMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command: Literal["home", "jog", "move", "set_work_zero", "cancel_jog", "hold", "resume", "clear_alarm", "reset"]
    distance: Literal["relative", "absolute"] | None = None
    frame: Literal["work", "machine"] = "work"
    rapid: bool = False


READ_DEFAULTS: dict[str, dict[str, Any]] = {
    "state": {"status": "state"},
    "alarm": {"status": "alarm"},
    "feed_rate": {"status": "feed"},
    "spindle_speed": {"status": "spindle"},
    "pins": {"status": "pins"},
    **{f"position_{axis}": {"status": axis, "frame": "machine"} for axis in protocol.AXES},
    **{f"work_{axis}": {"status": axis, "frame": "work"} for axis in protocol.AXES},
}
WRITE_DEFAULTS: dict[str, dict[str, Any]] = {
    "spindle_speed": {"spindle": "cw"},
    "laser_power": {"laser": "dynamic"},
    "flood": {"coolant": "flood"},
    "mist": {"coolant": "mist"},
}


def validate(model: type[BaseModel], raw: dict[str, Any] | None, default: dict[str, Any] | None, where: str) -> Any:
    data = raw if raw is not None else default
    if data is None:
        raise DriverError(f"{where} is not a GRBL channel the driver supports. Add a map, see docs/drivers/grbl.md.")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'map'}: {e['msg']}" for e in exc.errors())
        raise DriverError(f"{where}.map is not valid for the GRBL driver ({problems}).") from exc


def to_unit(value: float, source: str, target: str, where: str) -> float:
    try:
        return convert(Quantity(value, parse_unit(source)), target)
    except UnitError as exc:
        raise DriverError(f"{where}: {exc}") from exc


def convertible(unit: str | None, wanted: str, where: str) -> None:
    try:
        convert(Quantity(1.0, parse_unit(unit or "")), wanted)
    except UnitError:
        raise DriverError(f"{where} needs a unit that converts to {wanted}, not {unit!r}.") from None


def check_read(name: str, kind: str, unit: str | None, values: list[str], read_map: ReadMap) -> None:
    where = f"read.{name}"
    if read_map.setting is not None:
        if read_map.setting in BOOL_SETTINGS and kind == "bool":
            return
        if kind != "number":
            raise DriverError(f"{where}: ${read_map.setting} is read as a number.")
        known = protocol.SETTING_UNITS.get(read_map.setting)
        if known:
            convertible(unit, known, where)
        return
    status = read_map.status
    if status == "state":
        if kind not in ("enum", "string"):
            raise DriverError(f"{where}: the machine state is an enum or a string.")
        unknown = set(values) - set(protocol.STATES)
        if unknown:
            raise DriverError(f"{where}: GRBL never reports {sorted(unknown)}. Use {', '.join(protocol.STATES)}.")
    elif status == "pins":
        if kind != "string":
            raise DriverError(f"{where}: pins is a string such as XYZP.")
    elif kind != "number":
        raise DriverError(f"{where}: {status} is a number.")
    elif status in protocol.AXES:
        convertible(unit, "mm", where)
    elif status == "feed":
        convertible(unit, "mm/min", where)
    elif status == "spindle":
        convertible(unit, "rpm", where)


def check_write(name: str, kind: str, unit: str | None, write_map: WriteMap) -> None:
    where = f"write.{name}"
    if write_map.coolant is not None:
        if kind != "bool":
            raise DriverError(f"{where}: coolant channels are true or false.")
    elif kind != "number":
        raise DriverError(f"{where}: spindle and laser channels are numbers.")
    elif write_map.spindle is not None:
        convertible(unit, "rpm", where)
    elif unit not in ("percent", "%"):
        raise DriverError(f"{where}: laser power is in percent.")


def check_action(name: str, action_map: ActionMap, action: Action) -> None:
    where = f"actions.{name}"
    command, args = action_map.command, action.args
    if command in ("jog", "move"):
        extra = set(args) - {*protocol.AXES, "feed"}
        if extra:
            raise DriverError(f"{where}: {command} takes axis arguments x, y, z, a and feed, not {sorted(extra)}.")
        if not set(args) & set(protocol.AXES):
            raise DriverError(f"{where}: {command} needs at least one axis argument.")
        if "feed" not in args and not (command == "move" and action_map.rapid):
            raise DriverError(
                f"{where}: {command} needs a feed argument (GRBL returns an error for moves without a feed)."
            )
        for arg, spec in args.items():
            if spec.type != "number":
                raise DriverError(f"{where}.args.{arg} must be a number.")
            convertible(spec.unit, "mm/min" if arg == "feed" else "mm", f"{where}.args.{arg}")
    elif command == "set_work_zero":
        if set(args) - {"axes"}:
            raise DriverError(f"{where}: set_work_zero takes only an axes argument.")
        axes = args.get("axes")
        if axes is not None and (axes.type != "enum" or set(axes.values) - set(ZERO_AXES)):
            raise DriverError(f"{where}.args.axes must be an enum of {', '.join(ZERO_AXES)}.")
    elif args:
        raise DriverError(f"{where}: {command} takes no arguments.")


def build(device: DeviceFile) -> tuple[dict[str, ReadMap], dict[str, WriteMap], dict[str, ActionMap]]:
    """Check every channel and action in the file and return their maps."""
    reads: dict[str, ReadMap] = {}
    writes: dict[str, WriteMap] = {}
    actions: dict[str, ActionMap] = {}
    for name, spec in device.read.items():
        read_map = validate(ReadMap, spec.map, READ_DEFAULTS.get(name), f"read.{name}")
        check_read(name, spec.type, spec.unit, spec.values, read_map)
        reads[name] = read_map
    for name, write_spec in device.write.items():
        write_map = validate(WriteMap, write_spec.map, WRITE_DEFAULTS.get(name), f"write.{name}")
        check_write(name, write_spec.type, write_spec.unit, write_map)
        writes[name] = write_map
    for name, action in device.actions.items():
        known = {"command": name} if name in COMMANDS else None
        action_map = validate(ActionMap, action.map, known, f"actions.{name}")
        check_action(name, action_map, action)
        actions[name] = action_map
    return reads, writes, actions


def proposal(grbl: dict[int, float], build_info: dict[str, str], length: str) -> dict[str, Any]:
    """Device file sections proposed from `$$`. Every write and action is marked suggested."""
    laser = grbl.get(32) == 1
    travel = {axis: grbl.get(130 + index, 0.0) for index, axis in enumerate("xyz")}
    rate = min(grbl.get(110 + index, 500.0) for index in range(3))
    each = {"confirm": "confirm-each-time", "suggested": True}
    read: dict[str, Any] = {
        "state": {"type": "enum", "values": list(protocol.STATES), "every": "500 ms"},
        "alarm": {"unit": "dimensionless"},
        **{f"position_{axis}": {"unit": length} for axis in "xyz"},
        "feed_rate": {"unit": f"{length}/min"},
    }
    output = "laser_power" if laser else "spindle_speed"
    write: dict[str, Any] = {
        output: {"unit": "percent", "min": 0, "max": 100, **each}
        if laser
        else {"unit": "rpm", "min": 0, "max": grbl.get(30, 1000.0), **each},
        "flood": {"type": "bool", **each},
    }
    jog_args: dict[str, Any] = {
        axis: {"unit": "mm", "min": -(travel[axis] or 10.0), "max": travel[axis] or 10.0} for axis in "xyz"
    }
    jog_args["feed"] = {"unit": "mm/min", "min": 1, "max": rate}
    actions: dict[str, Any] = {
        "jog": {"args": jog_args, "require": ["state == idle"], **each},
        "cancel_jog": {"suggested": True},
        "hold": {"suggested": True},
        "resume": {"require": ["state == hold"], **each},
        "clear_alarm": {"require": ["state == alarm"], **each},
    }
    if grbl.get(22) == 1:
        actions["home"] = {"require": ["state != run"], **each}
    if grbl.get(20) == 1 and all(travel.values()):
        move_args: dict[str, Any] = {axis: {"unit": "mm", "min": -travel[axis], "max": 0} for axis in "xyz"}
        move_args["feed"] = {"unit": "mm/min", "min": 1, "max": rate}
        actions["move"] = {"args": move_args, "map": {"command": "move", "frame": "machine"}, **each}
    return {
        "device": {"name": f"GRBL {build_info.get('version', '1.1')} controller"},
        "read": read,
        "write": write,
        "actions": actions,
        "safe_state": [{output: 0, "flood": False}],
        "notes": (
            "Proposed from $$. The spindle maximum is $30, jog and move limits come from $130 to $132 and "
            "$110 to $112. Lower them for your work. GRBL machines are high hazard, so keep confirm-each-time."
        ),
    }
