"""Hub and kernel objects as protocol messages, and kernel blocks as registry errors.

Text that came from a device, a driver or a device file's notes is wrapped as data exactly as the
REST views wrap it (openhal/hub/views.py). The hub keeps epoch seconds and the kernel keeps its own
monotonic clock. Both become RFC 3339 strings in UTC here.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from openhal.drivers.base import Reading as DriverReading
from openhal.hub import views
from openhal.kernel.commands import Action, Command, Decision, Write
from openhal.kernel.confirmations import Request
from openhal.protocol import messages as m
from openhal.protocol.errors import RpcError, from_kernel
from openhal.spec.models import Confirmation, DeviceFile
from openhal.spec.units import UnitError, convert, parse_quantity, wire_unit

if TYPE_CHECKING:
    from openhal.audit.log import Entry
    from openhal.hub.hub import Hub

PROVENANCE_NAMES = frozenset(
    {"LIMIT_EXCEEDED", "RATE_LIMITED", "INVALID_VALUE", "UNIT_INVALID", "INTERLOCK_BLOCKED", "WATCHDOG_TRIPPED"}
)
"""Errors about a device file's rules. Their data names the file and who confirmed it."""

_LIMIT_KEYS = {"above_max": "max", "below_min": "min", "bad_step": "step", "rate_limited": "rate_per_s"}
_SPEC_KEYS = {"max": "max", "min": "min", "rate_per_s": "max_change_per_s"}


def timestamp(epoch: float) -> str:
    """Epoch seconds as RFC 3339 in UTC, `2026-10-24T14:02:00Z`, with milliseconds when there are any."""
    moment = dt.datetime.fromtimestamp(epoch, dt.UTC)
    spec = "milliseconds" if moment.microsecond // 1000 else "seconds"
    return moment.isoformat(timespec=spec).replace("+00:00", "Z")


def kernel_time(hub: Hub, monotonic: float) -> str:
    """A time on the kernel's clock as RFC 3339, measured back from now."""
    return timestamp(time.time() - (hub.kernel.clock() - monotonic))


def when(value: dt.date | dt.datetime | None) -> str | None:
    """A confirmation date as `2026-10-24`."""
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    return value.isoformat()


def file_name(hub: Hub, device_id: str) -> str | None:
    """The device file's name, for example printer.hal.yaml, when the device came from a file."""
    info = hub.info.get(device_id)
    if info is None or not info.path:
        return None
    return Path(info.path).name


def confirmation(file: DeviceFile, channel: str | None = None, action: str | None = None) -> Confirmation | None:
    """Who confirmed the limits of one channel or action, falling back to the file-level confirmation."""
    entry: Any = None
    if channel is not None:
        entry = file.write.get(channel)
    elif action is not None:
        entry = file.actions.get(action)
    found: Confirmation | None = entry.confirmed if entry is not None else None
    return found if found is not None else file.confirmed


def window(seconds: float) -> dict[str, Any]:
    """A max_runs window in the largest unit that keeps it whole, `{"value": 1, "unit": "h"}` for 3600 s."""
    for unit, size in (("d", 86400.0), ("h", 3600.0), ("min", 60.0)):
        if seconds >= size and (seconds / size).is_integer():
            return views.quantity(seconds / size, unit)
    return views.quantity(seconds, "s")


def limit_quantity(kernel_code: str | None, limit: dict[str, Any] | None) -> dict[str, Any] | None:
    """The limit that applied, `{"value": 100, "unit": "%"}` for a max or `{"value": 20, "unit": "%/s"}` for a rate."""
    key = _LIMIT_KEYS.get(kernel_code or "")
    if key is None or not limit or not isinstance(limit.get(key), int | float) or not limit.get("unit"):
        return None
    unit = str(limit["unit"])
    return views.quantity(float(limit[key]), f"{unit}/s" if key == "rate_per_s" else unit)


@dataclass(frozen=True, slots=True)
class Facts:
    """What a device file says about one target, enough to build its errors away from the hub.

    `limits` holds the file's own `max`, `min` and `rate_per_s` in `unit`. The MCP server fills this
    from hal/devices/describe, the hub fills it from the loaded file.
    """

    file: str | None = None
    confirmed_by: str | None = None
    confirmed_at: str | None = None
    unit: str | None = None
    number: bool = False
    limits: dict[str, float] = field(default_factory=dict)


def requested(raw: Any, unit: str | None, *, number: bool) -> Any:
    """The requested value. A number becomes a Quantity in `unit`, anything else is returned as sent."""
    if raw is None:
        return None
    if number and unit and isinstance(raw, str | dict | int | float) and not isinstance(raw, bool):
        try:
            return views.quantity(convert(parse_quantity(raw), unit), unit)
        except UnitError:
            return raw if isinstance(raw, str) else None
    if isinstance(raw, str | bool | int | float):
        return raw
    return None


def _is_session_limit(facts: Facts, limit: dict[str, Any] | None) -> bool:
    """True when the limit that applied is tighter than the file's own, so a principal set it."""
    if not limit:
        return False
    return any(key in limit and own != limit[key] for key, own in facts.limits.items())


def target_parts(target: str | None) -> tuple[str | None, str | None]:
    """`write:bed_target` as (bed_target, None), `read:state` as (state, None) and `action:pause` as (None, pause)."""
    kind, _, name = (target or "").partition(":")
    if kind in ("write", "read"):
        return name or None, None
    if kind == "action":
        return None, name or None
    return None, None


def principal_name(label: str | None) -> str | None:
    """`agent:claude` as `claude`."""
    if not label:
        return None
    return label.partition(":")[2] or label


def build_error(
    kernel_code: str | None,
    *,
    device: str | None,
    target: str | None = None,
    facts: Facts | None = None,
    kernel_message: str | None = None,
    raw_value: Any = None,
    limit: dict[str, Any] | None = None,
    request_id: str | None = None,
    principal: str | None = None,
) -> RpcError:
    """A registry error for a kernel block, from plain facts. The hub and the MCP server both use it.

    `limit` is the kernel's limit, when the decision carried one. Without it the file's own limit is
    used. `principal` is the label of whoever sent the command, named when its session limit applied.
    """
    channel, action = target_parts(target)
    key = _LIMIT_KEYS.get(kernel_code or "")
    if limit is None and facts is not None and key in ("max", "min") and key in facts.limits:
        limit = {key: facts.limits[key], "unit": facts.unit}
    argument = (limit or {}).get("argument")
    data: dict[str, Any] = {
        "kernelMessage": kernel_message,
        "device": device,
        "channel": channel,
        "action": action,
        "argument": argument,
        "requested": _requested(kernel_code, facts, raw_value, limit, about=channel or argument),
        "limit": limit_quantity(kernel_code, limit),
        "requestId": request_id,
    }
    if limit and "runs" in limit and isinstance(limit.get("per_s"), int | float):
        data["runs"] = limit["runs"]
        data["per"] = window(float(limit["per_s"]))
    if limit and limit.get("interlock"):
        data["interlock"] = str(limit["interlock"])
    if limit and isinstance(limit.get("expected"), dict):
        data["expected"] = limit["expected"]
    if facts is not None and from_kernel(kernel_code).name in PROVENANCE_NAMES:
        if _is_session_limit(facts, limit):
            data["tightenedBy"] = principal_name(principal) or "this client"
        else:
            data["file"] = facts.file
            data["confirmedBy"] = facts.confirmed_by
            data["confirmedAt"] = facts.confirmed_at
    return from_kernel(kernel_code, data)


def _requested(
    kernel_code: str | None, facts: Facts | None, raw: Any, limit: dict[str, Any] | None, *, about: str | None
) -> Any:
    """The requested value for an error about one channel or argument. A refused shape is shown as sent."""
    if about is None or raw is None:
        return None
    if kernel_code == "bad_unit":
        return raw if isinstance(raw, str | bool | int | float) else None
    unit = (limit or {}).get("unit") or (facts.unit if facts is not None else None)
    number = bool((limit or {}).get("unit")) or (facts is not None and facts.number)
    return requested(raw, unit, number=number)


def facts_for(hub: Hub, device: str | None, target: str | None) -> Facts | None:
    """The facts for one target of a registered device."""
    runtime = hub.kernel.devices.get(device or "")
    if runtime is None:
        return None
    file = runtime.file
    channel, action = target_parts(target)
    confirmed = confirmation(file, channel, action)
    spec = file.write.get(channel) if channel is not None else None
    limits: dict[str, float] = {}
    if spec is not None:
        for key, attribute in _SPEC_KEYS.items():
            value = getattr(spec, attribute)
            if value is not None:
                limits[key] = value
    return Facts(
        file=file_name(hub, file.device_id),
        confirmed_by=confirmed.by if confirmed is not None else None,
        confirmed_at=when(confirmed.at) if confirmed is not None else None,
        unit=spec.unit if spec is not None else None,
        number=spec is not None and spec.type == "number",
        limits=limits,
    )


def kernel_error(
    hub: Hub,
    kernel_code: str | None,
    *,
    device: str | None,
    target: str | None = None,
    kernel_message: str | None = None,
    raw_value: Any = None,
    limit: dict[str, Any] | None = None,
    request_id: str | None = None,
    principal: str | None = None,
) -> RpcError:
    """A registry error for a kernel block, with every data field the hub can fill in."""
    return build_error(
        kernel_code,
        device=device,
        target=target,
        facts=facts_for(hub, device, target),
        kernel_message=kernel_message,
        raw_value=raw_value,
        limit=limit,
        request_id=request_id,
        principal=principal,
    )


def body_value(body: dict[str, Any] | None, limit: dict[str, Any] | None = None) -> Any:
    """What a command body asked for on its channel, or on the action argument a limit names, with its unit."""
    if not body:
        return None
    if body.get("kind", "write") == "write":
        value, unit = body.get("value"), body.get("unit")
        return value if unit is None else {"value": value, "unit": unit}
    if limit and limit.get("argument"):
        return (body.get("args") or {}).get(str(limit["argument"]))
    return None


def raw_value(command: Command | None, limit: dict[str, Any] | None = None) -> Any:
    """What a kernel command asked for, as `body_value` reads it."""
    return body_value(command.model_dump() if command is not None else None, limit)


def decision_error(
    hub: Hub, decision: Decision, command: Command | None = None, principal: str | None = None
) -> RpcError:
    """The registry error for a blocked, failed or waiting decision."""
    return kernel_error(
        hub,
        decision.code,
        device=decision.device,
        target=decision.target,
        kernel_message=decision.message,
        raw_value=raw_value(command, decision.limit),
        limit=decision.limit,
        request_id=decision.request_id,
        principal=principal,
    )


def decision(
    hub: Hub,
    kernel: Decision,
    command: Command | None = None,
    *,
    principal: str | None = None,
    cannot_wait: bool = False,
) -> m.Decision:
    """A kernel decision as a protocol Decision. Blocked and failed ones carry their registry error.

    `cannot_wait` is for callers that can't hold a pending request, such as hal/planCheck. A step
    there that needs a person carries CONFIRMATION_REQUIRED.
    """
    error = None
    if kernel.status in ("blocked", "failed") or (cannot_wait and kernel.status == "needs_confirmation"):
        error = m.ErrorObject.model_validate(decision_error(hub, kernel, command, principal).to_object())
    unit = kernel.unit
    channel, _ = target_parts(kernel.target)
    runtime = hub.kernel.devices.get(kernel.device)
    if unit is None and channel is not None and runtime is not None and channel in runtime.file.write:
        unit = runtime.file.write[channel].unit
    _, action = target_parts(kernel.target)
    value = kernel.value
    if action is not None:
        value = action_args(hub, kernel.device, action, value) if value is not None else None
    return m.Decision(
        status=kernel.status,
        device=kernel.device,
        target=kernel.target,
        value=value,
        unit=wire_unit(unit),
        error=error,
        request_id=kernel.request_id,
    )


def wire_value(value: Any, unit: str | None = None) -> tuple[m.Value, str | None]:
    """A kernel command value as the protocol sends it, a number and its unit apart."""
    if isinstance(value, dict) and "value" in value:
        return wire_value(value["value"], str(value.get("unit") or "") or None)
    if isinstance(value, str | bool | int | float):
        return value, unit
    return str(value), None


def wire_argument(value: Any) -> m.Argument:
    """An action argument as the protocol sends it. Numbers become Quantity objects."""
    if isinstance(value, dict) and "value" in value and value.get("unit"):
        return m.Quantity(value=value["value"], unit=str(value["unit"]))
    if isinstance(value, str | bool):
        return value
    return str(value)


def command(kernel: Command) -> m.Write | m.Action:
    if isinstance(kernel, Write):
        value, unit = wire_value(kernel.value, kernel.unit)
        return m.Write(device=kernel.device, channel=kernel.channel, value=value, unit=unit)
    args = {name: wire_argument(value) for name, value in kernel.args.items()}
    return m.Action(device=kernel.device, action=kernel.action, args=args)


def kernel_args(args: dict[str, m.Argument]) -> dict[str, Any]:
    """Protocol action arguments as the kernel takes them. Quantity objects become `{value, unit}` mappings."""
    return {name: value.model_dump() if isinstance(value, m.Quantity) else value for name, value in args.items()}


def kernel_command(message: m.Write | m.Action) -> Command:
    if isinstance(message, m.Write):
        return Write(device=message.device, channel=message.channel, value=message.value, unit=message.unit)
    return Action(device=message.device, action=message.action, args=kernel_args(message.args))


def action_args(hub: Hub, device: str, action: str, args: Any) -> dict[str, Any]:
    """The arguments an action ran with, numbers as Quantity objects in the argument's unit."""
    runtime = hub.kernel.devices.get(device)
    return views.action_args(runtime.file if runtime is not None else None, action, args)


def request(hub: Hub, item: Request) -> m.ConfirmationRequest:
    return m.ConfirmationRequest(
        request_id=item.request_id,
        status=item.status,
        command=command(item.command),
        requested_by=item.principal.label,
        created_at=kernel_time(hub, item.created_at),
        expires_at=kernel_time(hub, item.expires_at),
        decided_by=item.decided_by,
    )


def summary(hub: Hub, device_id: str) -> m.DeviceSummary:
    runtime = hub.kernel.devices[device_id]
    file = runtime.file
    return m.DeviceSummary(
        id=device_id,
        name=file.device.name,
        model=file.device.model,
        manufacturer=file.device.manufacturer,
        driver=file.connect.driver,
        hazard=file.effective_hazard,
        writable=file.writable,
        connected=runtime.connected,
        conformance=runtime.driver.info.conformance,
        verification=file.provenance.verification.status,
        unavailable=runtime.available,
    )


def _confirmed(item: Confirmation | None) -> m.Confirmed | None:
    if item is None:
        return None
    return m.Confirmed(by=item.by, at=when(item.at) or "")


def description(hub: Hub, device_id: str) -> m.DeviceDescription:
    """Everything a client needs before a write, including who confirmed the limits and when."""
    runtime = hub.kernel.devices[device_id]
    file = runtime.file
    high = file.effective_hazard == "high"
    read = {
        name: m.ReadChannelInfo(
            type=spec.type,
            unit=spec.unit,
            every_s=spec.every,
            stream=spec.stream,
            range=list(spec.range) if spec.range else None,
            values=spec.values or None,
        )
        for name, spec in file.read.items()
    }
    write = {
        name: m.WriteChannelInfo(
            type=spec.type,
            unit=spec.unit,
            min=spec.min,
            max=spec.max,
            step=spec.step,
            max_change_per_s=spec.max_change_per_s,
            values=spec.values or None,
            max_length=spec.max_length,
            pattern=spec.pattern,
            confirm="confirm-each-time" if high else spec.confirm,
            suggested=spec.suggested,
            confirmed=_confirmed(confirmation(file, channel=name)),
        )
        for name, spec in file.write.items()
    }
    actions = {
        name: m.ActionInfo(
            description=spec.description,
            args={arg: arg_spec.model_dump(exclude_none=True) for arg, arg_spec in spec.args.items()},
            require=[condition for condition, _message in spec.conditions],
            effects=spec.effects,
            confirm="confirm-each-time" if high else spec.confirm,
            suggested=spec.suggested,
            confirmed=_confirmed(confirmation(file, action=name)),
        )
        for name, spec in file.actions.items()
    }
    watchdog = m.WatchdogInfo(
        heartbeat_s=file.watchdog.heartbeat,
        on_loss=file.watchdog.on_loss,
        max_duration=[
            m.MaxDurationInfo(when=rule.when, for_s=rule.for_, reset_after_s=rule.reset_after, then=rule.then)
            for rule in file.watchdog.max_duration
        ],
    )
    return m.DeviceDescription(
        **summary(hub, device_id).model_dump(),
        read=read,
        write=write,
        actions=actions,
        safe_state=[step.model_dump(mode="json") for step in file.safe_state],
        interlocks=[
            m.InterlockInfo.model_validate({"if": item.if_, "require": item.require, "message": item.message})
            for item in file.interlocks
        ],
        watchdog=watchdog,
        confirmed=_confirmed(file.confirmed),
        unconfirmed=file.unconfirmed(),
        file=file_name(hub, device_id),
        notes=views.data_block(f"device file {device_id} notes", file.notes),
    )


def reading(hub: Hub, device_id: str, item: DriverReading) -> m.Reading:
    file = hub.kernel.devices[device_id].file
    return m.Reading(
        device=device_id,
        channel=item.channel,
        value=views.device_value(file, device_id, item.channel, item.value, image_data=True),
        unit=wire_unit(item.unit),
        at=timestamp(item.at),
        suspect=item.suspect,
    )


def routine_summary(view: dict[str, Any]) -> m.RoutineSummary:
    """The routine engine's summary in the protocol's shape."""
    return m.RoutineSummary(
        id=view["id"],
        kind=view["kind"],
        enabled=view["enabled"],
        sha256=view["sha256"],
        devices=list(view["devices"]),
        max_hazard=view.get("max_hazard"),
        triggers=[str(trigger) for trigger in view.get("triggers", [])],
        disabled_reason=view.get("disabled_reason"),
    )


def audit_entry(entry: Entry) -> m.AuditEntry:
    return m.AuditEntry(
        seq=entry.seq,
        at=timestamp(entry.at),
        event=entry.event,
        principal=entry.principal,
        device=entry.device,
        target=entry.target,
        status=entry.status,
        code=entry.code,
        body=views.audit_details(entry.device, entry.body.get("details", {})),
        hash=entry.hash,
    )
