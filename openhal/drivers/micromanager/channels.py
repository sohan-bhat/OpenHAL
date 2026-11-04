"""How micromanager device file channels and actions map onto Micro-Manager devices.

A channel's `map` names one thing in the loaded configuration. Channel names cover the usual
cases without a map, so `x`, `y`, `z`, `exposure`, `image`, `pixel_size`, `shutter` and `busy` need
none.

    { stage: xy, axis: x | y }       the XY stage, in um. `device` picks a stage other than the core's
    { stage: focus }                 the focus drive, in um. `device` picks another Z stage, such as a piezo
    { state: Objective }             a state device, read and set by label, or by index as a number
    { group: Channel }               a configuration group, read and set by preset name
    { camera: image }                a snapped frame, as a JPEG or PNG image
    { camera: exposure }             the camera's exposure, in ms
    { camera: pixel_size }           the pixel size at the sample for the current objective, in um
    { shutter: current }             the core's shutter, or a shutter's label
    { device: LED, property: Level } any device property, such as a light source's intensity
    { status: busy }                 true while any device is moving
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from openhal.drivers.base import DriverError
from openhal.spec.models import Action, DeviceFile
from openhal.spec.units import Quantity, UnitError, convert, parse_quantity, parse_unit

Label = Field(default=None, min_length=1, max_length=100)
Kind = Literal["stage", "state", "group", "camera", "shutter", "property", "status"]
READ_ONLY = frozenset({("camera", "image"), ("camera", "pixel_size"), ("status", "busy")})
STAGE_TYPES = {"xy": "XYStage", "focus": "Stage"}


class ChannelMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    stage: Literal["xy", "focus"] | None = None
    axis: Literal["x", "y"] | None = None
    device: str | None = Label
    state: str | None = Label
    group: str | None = Label
    camera: Literal["image", "exposure", "pixel_size"] | None = None
    shutter: str | None = Label
    prop: str | None = Field(default=None, alias="property", min_length=1, max_length=100)
    status: Literal["busy"] | None = None

    @model_validator(mode="after")
    def _one(self) -> ChannelMap:
        fields = ("stage", "state", "group", "camera", "shutter", "prop", "status")
        kinds = [name for name in fields if getattr(self, name)]
        if len(kinds) != 1:
            raise ValueError("give exactly one of stage, state, group, camera, shutter, property or status.")
        if (self.stage == "xy") != (self.axis is not None):
            raise ValueError("an xy stage channel needs axis x or y, and only an xy stage channel takes axis.")
        if self.prop is not None and self.device is None:
            raise ValueError("a property channel needs the device that has the property.")
        if self.device is not None and self.stage is None and self.prop is None:
            raise ValueError("device goes with stage or property.")
        return self

    @property
    def kind(self) -> Kind:
        kinds: tuple[tuple[str, Kind], ...] = (
            ("stage", "stage"),
            ("state", "state"),
            ("group", "group"),
            ("camera", "camera"),
            ("shutter", "shutter"),
            ("prop", "property"),
        )
        for field, kind in kinds:
            if getattr(self, field) is not None:
                return kind
        return "status"

    @property
    def read_only(self) -> bool:
        detail = self.camera if self.kind == "camera" else self.status
        return (self.kind, detail) in READ_ONLY


class ActionMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command: Literal["autofocus", "home", "stop", "move_xy"]
    stage: Literal["xy", "focus", "all"] = "all"
    method: Literal["auto", "device", "image"] = "auto"
    span: float = Field(default=40.0, gt=0, le=2000, description="Image autofocus sweep in um.")
    steps: int = Field(default=9, ge=3, le=41)

    @field_validator("span", mode="before")
    @classmethod
    def _span(cls, value: Any) -> float:
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
        try:
            return convert(parse_quantity(value), "um")
        except UnitError as exc:
            raise ValueError(f"span needs a length such as 40 um ({exc}).") from None


CHANNEL_DEFAULTS: dict[str, dict[str, Any]] = {
    "x": {"stage": "xy", "axis": "x"},
    "y": {"stage": "xy", "axis": "y"},
    "z": {"stage": "focus"},
    "focus": {"stage": "focus"},
    "exposure": {"camera": "exposure"},
    "image": {"camera": "image"},
    "snapshot": {"camera": "image"},
    "frame": {"camera": "image"},
    "pixel_size": {"camera": "pixel_size"},
    "shutter": {"shutter": "current"},
    "busy": {"status": "busy"},
}
ACTION_DEFAULTS: dict[str, dict[str, Any]] = {
    "autofocus": {"command": "autofocus"},
    "home": {"command": "home", "stage": "all"},
    "home_xy": {"command": "home", "stage": "xy"},
    "home_focus": {"command": "home", "stage": "focus"},
    "stop": {"command": "stop"},
    "move_xy": {"command": "move_xy"},
}


def validate(model: type[BaseModel], raw: dict[str, Any] | None, default: dict[str, Any] | None, where: str) -> Any:
    data = raw if raw is not None else default
    if data is None:
        raise DriverError(f"{where} needs a map, see docs/drivers/micromanager.md.")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'map'}: {e['msg']}" for e in exc.errors())
        raise DriverError(f"{where}.map is not valid for the micromanager driver ({problems}).") from exc


def convertible(unit: str | None, wanted: str, where: str) -> None:
    try:
        convert(Quantity(1.0, parse_unit(unit or "")), wanted)
    except UnitError:
        raise DriverError(f"{where} needs a unit that converts to {wanted}, not {unit!r}.") from None


def to_unit(value: float, source: str, target: str) -> float:
    return convert(Quantity(value, parse_unit(source)), target)


def check_channel(name: str, kind: str, unit: str | None, channel: ChannelMap, where: str) -> None:
    """Check that a channel's type and unit fit what its map reads."""
    if channel.kind == "stage":
        if kind != "number":
            raise DriverError(f"{where}: a stage position is a number.")
        convertible(unit, "um", where)
    elif channel.kind == "camera":
        wanted = {"image": "image", "exposure": "number", "pixel_size": "number"}[channel.camera or "image"]
        if kind != wanted:
            raise DriverError(
                f"{where}: the camera's {channel.camera} is {'an' if wanted == 'image' else 'a'} {wanted}."
            )
        if channel.camera == "exposure":
            convertible(unit, "ms", where)
        elif channel.camera == "pixel_size":
            convertible(unit, "um", where)
    elif channel.kind in ("shutter", "status"):
        if kind != "bool":
            raise DriverError(f"{where}: {channel.kind} is true or false.")
    elif channel.kind in ("state", "group"):
        if kind not in ("enum", "string") and not (channel.kind == "state" and kind == "number"):
            raise DriverError(f"{where}: a {channel.kind} is a label, so make the channel an enum or a string.")
    elif kind == "image":
        raise DriverError(f"{where}: a device property is never an image.")


def check_action(
    name: str, action_map: ActionMap, action: Action, file: DeviceFile, writes: dict[str, ChannelMap]
) -> None:
    where = f"actions.{name}"
    args = action.args
    if action_map.command == "move_xy":
        if set(args) != {"x", "y"}:
            raise DriverError(f"{where}: move_xy takes the arguments x and y.")
        for arg, spec in args.items():
            if spec.type != "number":
                raise DriverError(f"{where}.args.{arg} must be a number.")
            convertible(spec.unit, "um", f"{where}.args.{arg}")
    elif action_map.command == "autofocus":
        if set(args) - {"span"}:
            raise DriverError(f"{where}: autofocus takes only a span argument.")
        if "span" in args:
            if args["span"].type != "number":
                raise DriverError(f"{where}.args.span must be a number.")
            convertible(args["span"].unit, "um", f"{where}.args.span")
        if action_map.method == "image" and not any(item.stage == "focus" for item in writes.values()):
            raise DriverError(
                f"{where}: image autofocus moves the focus drive within a focus write channel's limits, "
                "so the file needs a write channel such as z: { unit: um, min: ..., max: ... }."
            )
    elif args:
        raise DriverError(f"{where}: {action_map.command} takes no arguments.")
    moved = stages_moved(action_map)
    needed = sorted(channel for channel, item in writes.items() if item.stage in moved)
    missing = [channel for channel in needed if channel not in action.effects]
    if missing:
        raise DriverError(
            f"{where} moves {', '.join(missing)}, so add {', '.join(missing)} to effects "
            "and the hub reads the new position back."
        )


def stages_moved(action_map: ActionMap) -> set[str]:
    if action_map.command == "move_xy":
        return {"xy"}
    if action_map.command == "autofocus":
        return {"focus"}
    if action_map.command == "home":
        return {"xy", "focus"} if action_map.stage == "all" else {action_map.stage}
    return set()


def build(device: DeviceFile) -> tuple[dict[str, ChannelMap], dict[str, ChannelMap], dict[str, ActionMap]]:
    """Check every channel and action in the file and return their maps."""
    reads: dict[str, ChannelMap] = {}
    writes: dict[str, ChannelMap] = {}
    actions: dict[str, ActionMap] = {}
    for name, spec in device.read.items():
        channel = validate(ChannelMap, spec.map, CHANNEL_DEFAULTS.get(name), f"read.{name}")
        check_channel(name, spec.type, spec.unit, channel, f"read.{name}")
        reads[name] = channel
    for name, write_spec in device.write.items():
        channel = validate(ChannelMap, write_spec.map, CHANNEL_DEFAULTS.get(name), f"write.{name}")
        if channel.read_only:
            raise DriverError(f"write.{name}: {channel.camera or channel.status} can only be read.")
        check_channel(name, write_spec.type, write_spec.unit, channel, f"write.{name}")
        writes[name] = channel
    for name, action in device.actions.items():
        action_map = validate(ActionMap, action.map, ACTION_DEFAULTS.get(name), f"actions.{name}")
        check_action(name, action_map, action, device, writes)
        actions[name] = action_map
    return reads, writes, actions


def resolve(core: Any, channel: ChannelMap, where: str, values: list[str]) -> str:
    """The device label or group a channel reads, checked against the loaded configuration."""
    loaded = set(core.getLoadedDevices())
    if channel.kind == "stage":
        label = channel.device or (core.getXYStageDevice() if channel.stage == "xy" else core.getFocusDevice())
        kind = STAGE_TYPES[channel.stage or "focus"]
        if not label:
            raise DriverError(
                f"{where}: the configuration sets no {'XY stage' if channel.stage == 'xy' else 'focus device'}."
            )
        if label not in loaded or int(core.getDeviceType(label)) != device_type(kind):
            raise DriverError(f"{where}: {label!r} is not a loaded {kind} device.")
        return str(label)
    if channel.kind == "state":
        label = str(channel.state)
        if label not in core.getLoadedDevicesOfType(device_type("State")):
            states = ", ".join(core.getLoadedDevicesOfType(device_type("State"))) or "none"
            raise DriverError(f"{where}: {label!r} is not a loaded state device. State devices are {states}.")
        unknown = set(values) - set(core.getStateLabels(label))
        if unknown:
            raise DriverError(
                f"{where}: {label} has no states {sorted(unknown)}. It has {list(core.getStateLabels(label))}."
            )
        return label
    if channel.kind == "group":
        group = str(channel.group)
        if group not in core.getAvailableConfigGroups():
            raise DriverError(f"{where}: the configuration has no group {group!r}.")
        unknown = set(values) - set(core.getAvailableConfigs(group))
        if unknown:
            raise DriverError(f"{where}: group {group} has no presets {sorted(unknown)}.")
        return group
    if channel.kind == "camera":
        label = str(core.getCameraDevice())
        if not label:
            raise DriverError(f"{where}: the configuration sets no camera.")
        return label
    if channel.kind == "shutter":
        label = str(core.getShutterDevice()) if channel.shutter == "current" else str(channel.shutter)
        if not label or label not in core.getLoadedDevicesOfType(device_type("Shutter")):
            raise DriverError(f"{where}: {label or 'the core'!r} is not a loaded shutter.")
        return label
    if channel.kind == "property":
        label = str(channel.device)
        if label not in loaded or not core.hasProperty(label, channel.prop):
            raise DriverError(f"{where}: {label} has no property {channel.prop!r}.")
        return label
    return ""


def device_type(name: str) -> int:
    """The MMCore device type number for a name such as XYStage."""
    from pymmcore_plus import DeviceType

    return int(DeviceType[name])
