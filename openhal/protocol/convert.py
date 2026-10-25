"""Hub and kernel objects as protocol messages, and kernel blocks as registry errors.

Text that came from a device, a driver or a device file's notes is wrapped as data exactly as the
REST views wrap it (openhal/hub/views.py). The hub keeps epoch seconds and the kernel keeps its own
monotonic clock. Both become RFC 3339 strings in UTC here.
"""

from __future__ import annotations

import datetime as dt
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from openhal.drivers.base import Reading as DriverReading
from openhal.hub import views
from openhal.kernel.commands import Action, Command, Decision, Write
from openhal.kernel.confirmations import Request
from openhal.protocol import messages as m
from openhal.protocol.errors import RpcError, from_kernel
from openhal.spec.models import Confirmation, DeviceFile
from openhal.spec.units import UnitError, convert, format_quantity, parse_quantity

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
    """The device file's name, for example desk-fan.hal.yaml, when the device came from a file."""
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


def limit_text(kernel_code: str | None, limit: dict[str, Any] | None) -> str | None:
    """The limit that applied as a quantity string, `100 %` for a max or `20 %/s` for a rate."""
    key = _LIMIT_KEYS.get(kernel_code or "")
    if key is None or not limit or not isinstance(limit.get(key), int | float) or not limit.get("unit"):
        return None
    text = format_quantity(float(limit[key]), str(limit["unit"]))
    return f"{text}/s" if key == "rate_per_s" else text


def requested(file: DeviceFile | None, channel: str | None, raw: Any) -> str | None:
    """The requested value in the channel's unit, as `150 %`, or as sent when it can't be converted."""
    if raw is None:
        return None
    spec = file.write.get(channel) if file is not None and channel is not None else None
    if spec is not None and spec.type == "number" and spec.unit and isinstance(raw, str | dict):
        try:
            return format_quantity(convert(parse_quantity(raw), spec.unit), spec.unit)
        except UnitError:
            return str(raw)
    if isinstance(raw, bool):
        return str(raw).lower()
    return str(raw)


def _file_limit(file: DeviceFile, channel: str, kernel_code: str) -> dict[str, Any] | None:
    spec = file.write.get(channel)
    key = _LIMIT_KEYS.get(kernel_code)
    if spec is None or spec.unit is None or key not in _SPEC_KEYS:
        return None
    value = getattr(spec, _SPEC_KEYS[key])
    return None if value is None else {key: value, "unit": spec.unit}


def _is_session_limit(file: DeviceFile, channel: str | None, limit: dict[str, Any] | None) -> bool:
    """True when the limit that applied is tighter than the file's own, so a principal set it."""
    if channel is None or not limit:
        return False
    spec = file.write.get(channel)
    if spec is None:
        return False
    for key, attribute in _SPEC_KEYS.items():
        own = getattr(spec, attribute)
        if key in limit and own is not None and limit[key] != own:
            return True
    return False


def target_parts(target: str | None) -> tuple[str | None, str | None]:
    """`write:fan_speed` and `read:fan_speed` as (fan_speed, None), and `action:spin_test` as (None, spin_test)."""
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
    """A registry error for a kernel block, with every data field the hub can fill in.

    `limit` is the kernel's limit, when the decision carried one. Without it the file's own limit is
    used. `principal` is the label of whoever sent the command, named when its session limit applied.
    """
    channel, action = target_parts(target)
    runtime = hub.kernel.devices.get(device or "")
    file = runtime.file if runtime is not None else None
    if file is not None and channel is not None and limit is None and kernel_code:
        limit = _file_limit(file, channel, kernel_code)
    data: dict[str, Any] = {
        "kernelMessage": kernel_message,
        "device": device,
        "channel": channel,
        "action": action,
        "requested": requested(file, channel, raw_value),
        "limit": limit_text(kernel_code, limit),
        "requestId": request_id,
    }
    name = from_kernel(kernel_code).name
    if file is not None and name in PROVENANCE_NAMES:
        if _is_session_limit(file, channel, limit):
            data["tightenedBy"] = principal_name(principal) or "this client"
        else:
            confirmed = confirmation(file, channel, action)
            data["file"] = file_name(hub, file.device_id)
            data["confirmedBy"] = confirmed.by if confirmed is not None else None
            data["confirmedAt"] = when(confirmed.at) if confirmed is not None else None
    return from_kernel(kernel_code, data)


def raw_value(command: Command | None) -> Any:
    if isinstance(command, Write):
        return command.value
    return None


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
        raw_value=raw_value(command),
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
    return m.Decision(
        status=kernel.status,
        device=kernel.device,
        target=kernel.target,
        value=kernel.value,
        unit=unit,
        error=error,
        request_id=kernel.request_id,
    )


def wire_value(value: Any) -> m.Value:
    """A command value as the protocol sends it. A REST quantity mapping becomes a quantity string."""
    if isinstance(value, dict):
        return f"{value.get('value')} {value.get('unit')}"
    if isinstance(value, str | bool | int | float):
        return value
    return str(value)


def command(kernel: Command) -> m.Write | m.Action:
    if isinstance(kernel, Write):
        return m.Write(device=kernel.device, channel=kernel.channel, value=wire_value(kernel.value))
    args = {name: wire_value(value) for name, value in kernel.args.items()}
    return m.Action(device=kernel.device, action=kernel.action, args=args)


def kernel_command(message: m.Write | m.Action) -> Command:
    if isinstance(message, m.Write):
        return Write(device=message.device, channel=message.channel, value=message.value)
    return Action(device=message.device, action=message.action, args=dict(message.args))


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
            require=spec.require,
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
        value=views.device_value(file, device_id, item.channel, item.value),
        unit=item.unit,
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
