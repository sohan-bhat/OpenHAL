"""Reference models for OpenHAL device files (spec/SPEC.md, version 0.1).

These Pydantic models are the normative implementation of the spec. The JSON Schema in
spec/schema/device-file.schema.json is generated from them, so the two can't drift.

Every limit is stored as a float in its channel's declared unit. Shorthands allowed by the spec
(a string `device`, `connect` shorthand, unit strings in limits) are expanded by `before`
validators, so the rest of OpenHAL only ever sees the full form.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Annotated, Any, Final, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    WithJsonSchema,
    field_validator,
    model_validator,
)

from openhal._brand import SPEC_VERSION
from openhal.spec import expressions
from openhal.spec.units import UnitError, convert, parse_duration, parse_quantity, parse_rate, parse_unit

NAME_PATTERN: Final = r"^[a-z][a-z0-9_]{0,47}$"
ID_PATTERN: Final = r"^[a-z][a-z0-9-]{0,47}$"
KNOWN_DRIVERS: Final = frozenset(
    {
        "serial",
        "firmata",
        "openhal-firmware",
        "scpi",
        "moonraker",
        "octoprint",
        "marlin",
        "homeassistant",
        "esphome",
        "rpi-gpio",
        "rpi-camera",
        "mqtt",
        "modbus",
        "ble",
        "midi",
        "hid",
        "uvc",
        "http",
        "grbl",
        "ros2",
        "opcua",
        "sila2",
        "indi",
        "alpaca",
        "onvif",
        "pylabrobot",
        "lerobot",
        "mock",
    }
)
"""Driver names recognised by the `connect` shorthand. Drivers are registered under these names."""

Hazard = Literal["low", "medium", "high"]
ConfirmTier = Literal["none", "confirm", "confirm-each-time"]
ChannelType = Literal["number", "bool", "string", "enum", "image"]
WriteType = Literal["number", "bool", "string", "enum"]
Source = Literal["library", "self-described", "bridge", "driver-describe", "sketch", "manual", "hand-written"]
VerificationStatus = Literal["unverified", "tested-reads", "verified-on-hardware"]

_DURATION_SCHEMA: Final = {
    "type": "string",
    "description": "A duration with a unit, for example 5 s, 500ms or 10 min.",
}
_LIMIT_SCHEMA: Final = {
    "anyOf": [{"type": "number"}, {"type": "string"}],
    "description": "A number in the channel unit, or a quantity string such as '30 degC'.",
}

Seconds = Annotated[float, BeforeValidator(parse_duration), WithJsonSchema(_DURATION_SCHEMA)]
Limit = Annotated[float, WithJsonSchema(_LIMIT_SCHEMA)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


def _check_regex(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) > 256:
        raise ValueError("Patterns may be at most 256 characters.")
    try:
        re.compile(value)
    except re.error as exc:
        raise ValueError(f"Invalid pattern: {exc}.") from exc
    return value


Pattern = Annotated[str, BeforeValidator(_check_regex)]


class Confirmation(_Strict):
    """A human confirmed limits. Only the human side of the limits interview or a human edit adds it."""

    by: str = Field(min_length=1, max_length=80)
    at: dt.datetime | dt.date


class Verification(_Strict):
    status: VerificationStatus = "unverified"
    report: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _report_required(self) -> Verification:
        if self.status == "verified-on-hardware" and not self.report:
            raise ValueError("verified-on-hardware needs a report.")
        return self


class Provenance(_Strict):
    source: Source = "hand-written"
    by: str | None = Field(default=None, max_length=120)
    at: dt.datetime | dt.date | None = None
    from_: str | None = Field(default=None, alias="from", max_length=300)
    tool: str | None = Field(default=None, max_length=80)
    verification: Verification = Verification()


class Identity(_Strict):
    name: str = Field(min_length=1, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    manufacturer: str | None = Field(default=None, max_length=120)


class Match(_Strict):
    usb: list[Annotated[str, Field(pattern=r"^[0-9a-fA-F]{4}:[0-9a-fA-F]{4}$")]] = []
    usb_class: Literal["cdc", "hid", "audio", "video", "midi", "usbtmc", "vendor"] | None = None
    serial_number: Pattern | None = None
    scpi_idn: Pattern | None = None
    ble_services: list[Annotated[str, Field(pattern=r"^[0-9a-fA-F-]{4,36}$")]] = []
    ble_name: Pattern | None = None
    mdns: Annotated[str, Field(pattern=r"^_[a-z0-9-]+\._(tcp|udp)$")] | None = None
    modbus_id: Annotated[int, Field(ge=1, le=247)] | None = None
    homeassistant: Annotated[str, Field(max_length=120)] | None = None
    moonraker: dict[str, str] = {}
    esphome: dict[str, str] = {}
    firmware: dict[str, str] = {}


class Connect(_Strict):
    """Which driver talks to the device, and its parameters (validated by the driver itself)."""

    driver: str
    params: dict[str, Any] = {}

    @model_validator(mode="before")
    @classmethod
    def _expand(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            raise ValueError("connect must be a mapping.")
        if "params" in data and set(data) <= {"driver", "params"}:
            return data
        raw = dict(data)
        driver = raw.pop("driver", None)
        if driver is None:
            for key in list(raw):
                if key in KNOWN_DRIVERS:
                    driver = key
                    primary = raw.pop(key)
                    raw = {_PRIMARY_PARAM.get(key, "target"): primary, **raw}
                    break
        if driver is None:
            raise ValueError("connect must name a driver, for example driver: serial or serial: auto.")
        return {"driver": driver, "params": raw}

    @field_validator("driver")
    @classmethod
    def _known(cls, value: str) -> str:
        if value not in KNOWN_DRIVERS and not value.startswith("x-"):
            raise ValueError(f"Unknown driver {value!r}. Known drivers are {', '.join(sorted(KNOWN_DRIVERS))}.")
        return value

    @field_validator("params")
    @classmethod
    def _no_secrets(cls, value: dict[str, Any]) -> dict[str, Any]:
        for key in value:
            if (
                any(word in key.lower() for word in ("password", "secret", "apikey", "api_key"))
                or key.lower() == "token"
            ):
                raise ValueError(
                    f"Device files must not hold secrets. Use {key}_env with an environment variable name."
                )
        return value


_PRIMARY_PARAM: Final = {
    "serial": "port",
    "firmata": "port",
    "openhal-firmware": "port",
    "marlin": "port",
    "grbl": "port",
    "scpi": "resource",
    "moonraker": "host",
    "octoprint": "host",
    "homeassistant": "host",
    "esphome": "host",
    "http": "base_url",
    "mqtt": "host",
    "modbus": "transport",
    "ble": "address",
    "midi": "name",
    "hid": "name",
    "uvc": "name",
    "rpi-gpio": "pins",
    "rpi-camera": "camera",
    "ros2": "host",
    "opcua": "endpoint",
    "sila2": "host",
    "indi": "host",
    "alpaca": "host",
    "onvif": "host",
    "pylabrobot": "backend",
    "lerobot": "robot",
    "mock": "name",
}


def _to_unit(value: Any, unit: str | None, what: str) -> Any:
    """Convert a limit written as a quantity string into the channel unit."""
    if value is None or unit is None or isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return parse_quantity(value, default_unit=unit).magnitude
    try:
        return convert(parse_quantity(value, default_unit=unit), unit)
    except UnitError as exc:
        raise ValueError(f"{what}: {exc}") from exc


class _ValueSpec(_Strict):
    """Fields shared by write channels and action arguments."""

    type: WriteType = "number"
    unit: str | None = None
    min: Limit | None = None
    max: Limit | None = None
    step: Limit | None = None
    values: list[str] = []
    max_length: Annotated[int, Field(ge=1, le=4096)] | None = None
    pattern: Pattern | None = None

    @model_validator(mode="before")
    @classmethod
    def _convert_limits(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        unit = data.get("unit")
        if isinstance(unit, str):
            try:
                parse_unit(unit)
            except UnitError as exc:
                raise ValueError(str(exc)) from exc
        converted = dict(data)
        for key in ("min", "max", "step"):
            if key in converted:
                converted[key] = _to_unit(converted[key], unit, key)
        if "max_change_per_s" in converted and isinstance(unit, str):
            try:
                converted["max_change_per_s"] = parse_rate(converted["max_change_per_s"], unit)
            except UnitError as exc:
                raise ValueError(f"max_change_per_s: {exc}") from exc
        return converted

    @model_validator(mode="after")
    def _consistent(self) -> _ValueSpec:
        if self.type == "number":
            if not self.unit:
                raise ValueError("Number values need a unit. Use dimensionless for plain counts.")
            if self.min is None or self.max is None:
                raise ValueError("Number values need both min and max.")
            if self.min > self.max:
                raise ValueError(f"min ({self.min:g}) is above max ({self.max:g}).")
            if self.step is not None and self.step <= 0:
                raise ValueError("step must be greater than zero.")
        elif self.type == "enum":
            if not self.values:
                raise ValueError("Enum values need a non-empty values list.")
            if len(set(self.values)) != len(self.values):
                raise ValueError("Enum values must be unique.")
        elif self.type == "string" and self.max_length is None:
            raise ValueError("String values need max_length.")
        if self.type != "number" and any(v is not None for v in (self.min, self.max, self.step)):
            raise ValueError("min, max and step only apply to number values.")
        return self


class ReadChannel(_Strict):
    type: ChannelType = "number"
    unit: str | None = None
    every: Seconds | None = None
    stream: bool = False
    range: tuple[Limit, Limit] | None = None
    values: list[str] = []
    map: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def _convert_range(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("range"), list | tuple) and isinstance(data.get("unit"), str):
            data = dict(data)
            data["range"] = [_to_unit(item, data["unit"], "range") for item in data["range"]]
        return data

    @model_validator(mode="after")
    def _consistent(self) -> ReadChannel:
        if self.type == "number" and not self.unit:
            raise ValueError("Number channels need a unit. Use dimensionless for plain counts.")
        if self.every is not None and self.every < 0.05:
            raise ValueError("every must be at least 50 ms.")
        if self.range is not None and self.range[0] > self.range[1]:
            raise ValueError("range must be written low then high.")
        if self.type == "enum" and not self.values:
            raise ValueError("Enum channels need a values list.")
        return self


class WriteChannel(_ValueSpec):
    max_change_per_s: Limit | None = None
    confirm: ConfirmTier = "none"
    confirmed: Confirmation | None = None
    suggested: bool = False
    every: Seconds | None = None
    map: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _rate(self) -> WriteChannel:
        if self.max_change_per_s is not None:
            if self.type != "number":
                raise ValueError("max_change_per_s only applies to number channels.")
            if self.max_change_per_s <= 0:
                raise ValueError("max_change_per_s must be greater than zero.")
        return self


class ArgSpec(_ValueSpec):
    """One typed action argument."""


class Action(_Strict):
    args: dict[Annotated[str, Field(pattern=NAME_PATTERN)], ArgSpec] = {}
    require: list[str] = []
    confirm: ConfirmTier = "none"
    confirmed: Confirmation | None = None
    suggested: bool = False
    effects: list[str] = []
    description: str | None = Field(default=None, max_length=500)
    map: dict[str, Any] | None = None


class SafeStep(_Strict):
    """One step of a safe state, either channel values or an action."""

    values: dict[str, Any] = {}
    action: str | None = None
    args: dict[str, Any] = {}

    @model_validator(mode="before")
    @classmethod
    def _expand(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            raise ValueError("Each safe state step must be a mapping.")
        if "action" in data:
            extra = set(data) - {"action", "args"}
            if extra:
                raise ValueError(f"An action step can only have action and args, not {', '.join(sorted(extra))}.")
            return data
        if "values" in data and set(data) == {"values"}:
            return data
        return {"values": dict(data)}

    @model_validator(mode="after")
    def _not_empty(self) -> SafeStep:
        if not self.values and self.action is None:
            raise ValueError("A safe state step can't be empty.")
        return self


class Interlock(_Strict):
    if_: str = Field(alias="if", max_length=expressions.MAX_LENGTH)
    require: str = Field(max_length=expressions.MAX_LENGTH)
    message: str | None = Field(default=None, max_length=300)


class MaxDuration(_Strict):
    when: str = Field(max_length=expressions.MAX_LENGTH)
    for_: Seconds = Field(alias="for")
    then: Literal["safe_state"] | dict[str, Any] = "safe_state"
    reset_after: Seconds | None = None


class Watchdog(_Strict):
    heartbeat: Seconds = 5.0
    on_loss: Literal["safe_state", "hold"] | None = None
    max_duration: list[MaxDuration] = []

    @field_validator("heartbeat")
    @classmethod
    def _heartbeat(cls, value: float) -> float:
        if not 0.1 <= value <= 3600:
            raise ValueError("heartbeat must be between 100 ms and 1 h.")
        return value


class Approval(_Strict):
    routine: str = Field(pattern=ID_PATTERN)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    by: str = Field(min_length=1, max_length=80)
    at: dt.datetime
    signature: str = Field(pattern=r"^[0-9a-f]{64}$")


class DeviceFile(_Strict):
    """One device, as described by a `.hal.yaml` file."""

    openhal: str = SPEC_VERSION
    device: Identity
    id: Annotated[str, Field(pattern=ID_PATTERN)] | None = None
    match: Match = Match()
    connect: Connect
    read: dict[Annotated[str, Field(pattern=NAME_PATTERN)], ReadChannel] = {}
    write: dict[Annotated[str, Field(pattern=NAME_PATTERN)], WriteChannel] = {}
    actions: dict[Annotated[str, Field(pattern=NAME_PATTERN)], Action] = {}
    safe_state: list[SafeStep] = []
    safe_state_note: str | None = Field(default=None, max_length=500)
    interlocks: list[Interlock] = []
    watchdog: Watchdog = Watchdog()
    hazard: Hazard | None = None
    approvals: list[Approval] = []
    notes: str | None = Field(default=None, max_length=4000)
    provenance: Provenance = Provenance()
    confirmed: Confirmation | None = None
    extensions: dict[str, Any] = Field(default={}, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _expand(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            raise ValueError("A device file must be a mapping at the top level.")
        raw = dict(data)
        raw["extensions"] = {key: raw.pop(key) for key in list(raw) if isinstance(key, str) and key.startswith("x-")}
        device = raw.get("device")
        if isinstance(device, str):
            device = {"name": device}
        if isinstance(device, dict):
            device = dict(device)
            for key in ("model", "manufacturer"):
                if key in raw:
                    device.setdefault(key, raw.pop(key))
            raw["device"] = device
        safe_state = raw.get("safe_state")
        if isinstance(safe_state, dict):
            raw["safe_state"] = [safe_state]
        return raw

    @field_validator("openhal")
    @classmethod
    def _version(cls, value: str) -> str:
        if not re.fullmatch(r"\d+\.\d+(\.\d+)?", str(value)):
            raise ValueError("openhal must be a version such as 0.1.")
        if str(value).split(".")[0] != SPEC_VERSION.split(".")[0]:
            raise ValueError(f"This hub supports spec {SPEC_VERSION}. The file is version {value}.")
        return str(value)

    @property
    def device_id(self) -> str:
        """The file's id, or one derived from the device name."""
        if self.id:
            return self.id
        slug = re.sub(r"[^a-z0-9]+", "-", self.device.name.lower()).strip("-")
        if not slug or not slug[0].isalpha():
            slug = f"device-{slug}".strip("-")
        return slug[:48].rstrip("-")

    @property
    def effective_hazard(self) -> Hazard:
        """The declared hazard, or medium for writable devices and low for read-only ones."""
        if self.hazard is not None:
            return self.hazard
        return "medium" if (self.write or self.actions) else "low"

    def unconfirmed(self) -> list[str]:
        """Write channels and actions whose limits no human has confirmed yet."""
        missing: list[str] = []
        for kind, entries in (("write", self.write), ("actions", self.actions)):
            for name, entry in entries.items():
                if entry.suggested or (entry.confirmed is None and self.confirmed is None):
                    missing.append(f"{kind}.{name}")
        return missing

    @property
    def writable(self) -> bool:
        """True when every limit is confirmed by a human (spec section 12)."""
        return not self.unconfirmed()

    def channel_unit(self, name: str) -> str | None:
        """The unit of a read or write channel, if it has one."""
        if name in self.write:
            return self.write[name].unit
        if name in self.read:
            return self.read[name].unit
        return None

    def _enum_values(self, name: str) -> list[str]:
        if name in self.write:
            return self.write[name].values
        if name in self.read:
            return self.read[name].values
        return []

    def _check_expression(self, text: str, where: str) -> None:
        try:
            tree = expressions.parse(text)
        except expressions.ExpressionError as exc:
            raise ValueError(f"{where}: {exc}") from exc
        known = set(self.read) | set(self.write)
        words = {value for name in known for value in self._enum_values(name)}
        for ref in expressions.references(tree):
            if ref.device is None and ref.name not in known and ref.name not in words:
                raise ValueError(f"{where}: {ref.name!r} is not a channel of this device.")

        def unit_of(ref: expressions.Ref) -> str | None:
            return self.channel_unit(ref.name) if ref.device is None else None

        try:
            expressions.check_units(tree, unit_of)
        except (expressions.ExpressionError, UnitError) as exc:
            raise ValueError(f"{where}: {exc}") from exc

    def _check_value(self, channel: str, value: Any, where: str) -> None:
        spec = self.write.get(channel)
        if spec is None:
            raise ValueError(f"{where}: {channel!r} is not a write channel.")
        if spec.type == "number":
            magnitude = _to_unit(value, spec.unit, where)
            if not isinstance(magnitude, float | int) or isinstance(magnitude, bool):
                raise ValueError(f"{where}: {channel} needs a number.")
            if spec.min is None or spec.max is None or not spec.min <= magnitude <= spec.max:
                raise ValueError(f"{where}: {value} is outside {channel}'s limits.")
        elif spec.type == "bool" and not isinstance(value, bool):
            raise ValueError(f"{where}: {channel} needs true or false.")
        elif spec.type == "enum" and value not in spec.values:
            raise ValueError(f"{where}: {value!r} is not one of {', '.join(spec.values)}.")

    @model_validator(mode="after")
    def _cross_checks(self) -> DeviceFile:
        names = list(self.read) + list(self.write) + list(self.actions)
        duplicates = {name for name in names if names.count(name) > 1}
        if duplicates:
            raise ValueError(f"Channel and action names must be unique. Repeated: {', '.join(sorted(duplicates))}.")
        for name, action in self.actions.items():
            for effect in action.effects:
                if effect not in self.write:
                    raise ValueError(f"actions.{name}.effects: {effect!r} is not a write channel.")
            for index, condition in enumerate(action.require):
                self._check_expression(condition, f"actions.{name}.require[{index}]")
        for index, interlock in enumerate(self.interlocks):
            self._check_expression(interlock.if_, f"interlocks[{index}].if")
            self._check_expression(interlock.require, f"interlocks[{index}].require")
        for index, rule in enumerate(self.watchdog.max_duration):
            self._check_expression(rule.when, f"watchdog.max_duration[{index}].when")
            if isinstance(rule.then, dict):
                for channel, value in rule.then.items():
                    self._check_value(channel, value, f"watchdog.max_duration[{index}].then")
        for index, step in enumerate(self.safe_state):
            if step.action is not None and step.action not in self.actions:
                raise ValueError(f"safe_state[{index}]: {step.action!r} is not an action of this device.")
            for channel, value in step.values.items():
                self._check_value(channel, value, f"safe_state[{index}]")
        return self
