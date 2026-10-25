"""The error registry (ADR 0015, Error registry).

Each entry has a stable numeric code, the registry name clients branch on, the kernel block codes
it covers and a reason template. Reasons are formed from the error's `data`, never by hand, so the
same block reads the same on every transport. The kernel's own message stays in
`data.kernelMessage`.

Every kernel code maps to exactly one name. tests/protocol/test_errors.py checks this against every
code the kernel can emit.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Final

Data = dict[str, Any]
Template = Callable[[Data], str]


@dataclass(frozen=True, slots=True)
class ErrorSpec:
    """One row of the registry."""

    code: int
    name: str
    kernel_codes: tuple[str, ...]
    meaning: str
    template: Template = field(repr=False)


def _subject(data: Data) -> str:
    """What the error is about, for example `fan_speed 150 %` or `home on laser`."""
    if data.get("channel"):
        return " ".join(str(part) for part in (data["channel"], data.get("requested")) if part is not None)
    if data.get("action"):
        return f"{data['action']} on {data['device']}" if data.get("device") else str(data["action"])
    return str(data.get("device") or "The command")


def _provenance(data: Data) -> str:
    """The device file and who confirmed its limits, as `(desk-fan.hal.yaml, confirmed by sohan 2026-11-02)`."""
    parts = []
    if data.get("file"):
        parts.append(str(data["file"]))
    if data.get("confirmedBy"):
        confirmed = f"confirmed by {data['confirmedBy']}"
        if data.get("confirmedAt"):
            confirmed += f" {data['confirmedAt']}"
        parts.append(confirmed)
    return f" ({', '.join(parts)})" if parts else ""


def _limit_exceeded(data: Data) -> str:
    limit = data.get("limit") or {}
    if "max" in limit:
        text = f"{_subject(data)} exceeds the limit of {limit['max']}"
    elif "min" in limit:
        text = f"{_subject(data)} is below the limit of {limit['min']}"
    else:
        text = f"{_subject(data)} is outside its confirmed limits"
    return text + _provenance(data)


def _rate_limited(data: Data) -> str:
    limit = data.get("limit") or {}
    text = f"{_subject(data)} changes faster than allowed right now"
    if "ratePerS" in limit:
        text = f"{_subject(data)} changes faster than {limit['ratePerS']} allows right now"
    if "from" in limit and "to" in limit:
        text += f". It can go from {limit['from']} to {limit['to']}"
    return text + _provenance(data)


def _invalid_value(data: Data) -> str:
    limit = data.get("limit") or {}
    if "step" in limit:
        return f"{_subject(data)} is not a step of {limit['step']}{_provenance(data)}"
    if "values" in limit:
        return f"{_subject(data)} is not one of {', '.join(str(value) for value in limit['values'])}{_provenance(data)}"
    return f"{_subject(data)} is not a value it accepts{_provenance(data)}"


def _unknown_target(data: Data) -> str:
    device = data.get("device")
    if device and data.get("channel"):
        return f"{device} has no channel {data['channel']}"
    if device and data.get("action"):
        return f"{device} has no action {data['action']}"
    if device:
        return f"There is no device {device}"
    if data.get("requestId"):
        return f"There is no request {data['requestId']}"
    return "There is no such device, channel, action or routine"


def _with_device(text: str) -> Template:
    def template(data: Data) -> str:
        return text.format(device=data.get("device") or "The device")

    return template


def _fixed(text: str) -> Template:
    def template(_data: Data) -> str:
        return text

    return template


REGISTRY: Final[tuple[ErrorSpec, ...]] = (
    ErrorSpec(-32700, "PARSE_ERROR", (), "Invalid JSON", _fixed("The message is not valid JSON")),
    ErrorSpec(
        -32600, "INVALID_REQUEST", (), "Not a JSON-RPC request", _fixed("The message is not a JSON-RPC 2.0 request")
    ),
    ErrorSpec(
        -32601,
        "METHOD_NOT_FOUND",
        (),
        "Unknown method, or one above the hub's conformance level",
        _fixed("This hub has no such method"),
    ),
    ErrorSpec(
        -32602,
        "INVALID_PARAMS",
        ("bad_request",),
        "Params don't match the schema",
        _fixed("The params don't match the method's schema"),
    ),
    ErrorSpec(
        -32603,
        "INTERNAL_ERROR",
        ("internal_error",),
        "A bug in the hub",
        _fixed("The hub hit an unexpected error and nothing was sent to the device"),
    ),
    ErrorSpec(-32001, "NOT_INITIALIZED", (), "hal/initialize hasn't run", _fixed("Send hal/initialize first")),
    ErrorSpec(
        -32002,
        "UNAUTHORIZED",
        (),
        "Missing or unknown token",
        _fixed("A valid token is required. Create one with openhal token create"),
    ),
    ErrorSpec(
        -32003,
        "SCOPE_DENIED",
        ("not_permitted",),
        "The principal's token scope doesn't cover this device or method",
        lambda data: (
            f"This token's scope doesn't cover {data['device']}"
            if data.get("device")
            else "This token's scope doesn't cover this method"
        ),
    ),
    ErrorSpec(-32004, "UNKNOWN_TARGET", ("unknown_target",), "No such device, channel or action", _unknown_target),
    ErrorSpec(
        -32005,
        "DEVICE_UNAVAILABLE",
        ("device_unavailable",),
        "Disconnected or not ready",
        _with_device("{device} is disconnected or not ready"),
    ),
    ErrorSpec(
        -32010,
        "LIMIT_EXCEEDED",
        ("above_max", "below_min"),
        "Outside the device file's confirmed limits",
        _limit_exceeded,
    ),
    ErrorSpec(
        -32011, "RATE_LIMITED", ("rate_limited",), "Faster than max_change_per_s allows right now", _rate_limited
    ),
    ErrorSpec(
        -32012,
        "INTERLOCK_BLOCKED",
        ("interlock",),
        "An interlock or action requirement doesn't hold, or a value it needs is unknown",
        lambda data: (
            f"{_subject(data)} is held back by an interlock or requirement that doesn't hold" + _provenance(data)
        ),
    ),
    ErrorSpec(
        -32013,
        "CONFIRMATION_REQUIRED",
        ("needs_confirmation",),
        "Queued for a person, data.requestId names the request",
        lambda data: (
            f"{_subject(data)} waits for a person to approve request {data['requestId']}"
            if data.get("requestId")
            else f"{_subject(data)} needs a person to approve it"
        ),
    ),
    ErrorSpec(
        -32014,
        "STOPPED",
        ("stopped",),
        "The hub is stopped until a person unlocks",
        _fixed("The hub is stopped until a person unlocks it"),
    ),
    ErrorSpec(
        -32015,
        "UNVERIFIED_LIMITS",
        ("read_only_file",),
        "The device file's limits aren't confirmed by a person, so it is read-only",
        lambda data: (
            f"{data.get('device') or 'The device'} is read-only until a person confirms its limits" + _provenance(data)
        ),
    ),
    ErrorSpec(
        -32016, "INVALID_VALUE", ("bad_value", "bad_step"), "Wrong type, step, enum value or pattern", _invalid_value
    ),
    ErrorSpec(
        -32017,
        "WATCHDOG_TRIPPED",
        ("duration_exceeded",),
        "A watchdog budget is used up",
        lambda data: (
            f"A watchdog budget on {data.get('device') or 'the device'} is used up until it resets" + _provenance(data)
        ),
    ),
    ErrorSpec(
        -32018,
        "BUSY",
        ("busy",),
        "Another command holds the device",
        _with_device("{device} is busy with another command. Try again"),
    ),
    ErrorSpec(
        -32019,
        "QUEUE_FULL",
        ("queue_full",),
        "The confirmation queue is full",
        _fixed("The confirmation queue is full. Wait for pending requests to be decided"),
    ),
    ErrorSpec(
        -32020,
        "DRIVER_ERROR",
        ("driver_error",),
        "The device or its protocol failed, and the channel is unknown until a readback",
        lambda data: (
            f"{data.get('device') or 'The device'} didn't complete the command, so "
            f"{data.get('channel') or 'what it touched'} is unknown until a readback"
        ),
    ),
    ErrorSpec(
        -32021,
        "MISCONFIGURED",
        ("misconfigured", "cannot_loosen"),
        "The hub's device files are inconsistent, or a change would loosen a confirmed limit",
        lambda data: (
            f"{_subject(data)} can only be tightened, never loosened"
            if data.get("kernelCode") == "cannot_loosen"
            else "The hub's device files are inconsistent, so nothing can be written until they are fixed"
        ),
    ),
    ErrorSpec(
        -32022,
        "REQUEST_CLOSED",
        ("expired", "rejected"),
        "The confirmation request expired or was rejected",
        lambda data: f"Request {data['requestId']} is closed" if data.get("requestId") else "The request is closed",
    ),
    ErrorSpec(
        -32023,
        "UNIT_INVALID",
        ("bad_unit",),
        "A missing, unknown or incompatible unit, or a value that isn't finite",
        lambda data: f"{_subject(data)} needs a finite number with a unit it can convert" + _provenance(data),
    ),
)

BY_NAME: Final = {spec.name: spec for spec in REGISTRY}
BY_CODE: Final = {spec.code: spec for spec in REGISTRY}
BY_KERNEL_CODE: Final = {kernel: spec for spec in REGISTRY for kernel in spec.kernel_codes}


def spec_for_kernel_code(kernel_code: str | None) -> ErrorSpec:
    """The registry entry for a kernel block code. Unknown codes are a hub bug."""
    if kernel_code is None:
        return BY_NAME["INTERNAL_ERROR"]
    return BY_KERNEL_CODE.get(kernel_code, BY_NAME["INTERNAL_ERROR"])


class RpcError(Exception):
    """A JSON-RPC error with a registry name. Raised inside the dispatcher, answered as an error response."""

    def __init__(self, name: str, data: Data | None = None, *, message: str | None = None) -> None:
        spec = BY_NAME[name]
        self.spec = spec
        self.data: Data = {key: value for key, value in (data or {}).items() if value is not None}
        self.data["name"] = spec.name
        self.reason = message if message is not None else spec.template(self.data)
        super().__init__(self.reason)

    @property
    def code(self) -> int:
        return self.spec.code

    @property
    def name(self) -> str:
        return self.spec.name

    def to_object(self) -> dict[str, Any]:
        """The JSON-RPC `error` member, `{ code, message, data }`."""
        data = {"name": self.spec.name, **{key: value for key, value in self.data.items() if key != "name"}}
        return {"code": self.spec.code, "message": self.reason, "data": data}


def from_kernel(kernel_code: str | None, data: Data | None = None) -> RpcError:
    """An error for a kernel block code, with `kernelCode` set."""
    spec = spec_for_kernel_code(kernel_code)
    return RpcError(spec.name, {**(data or {}), "kernelCode": kernel_code})
