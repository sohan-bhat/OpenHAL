"""Hub and kernel objects as protocol messages, and kernel blocks as registry errors.

Text that came from a device, a driver or a device file's notes is wrapped as data exactly as the
REST views wrap it (openhal/hub/views.py).
"""

from __future__ import annotations

import datetime as dt
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

_LIMIT_KEYS = {"rate_per_s": "ratePerS", "wait_s": "waitS"}


def when(value: dt.date | dt.datetime | None) -> str | None:
    """A confirmation date as `2026-11-02`."""
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
    if entry is not None and entry.confirmed is not None:
        return entry.confirmed  # type: ignore[no-any-return]
    return file.confirmed


def format_limit(limit: dict[str, Any] | None) -> dict[str, Any] | None:
    """A kernel limit such as `{"max": 100.0, "unit": "percent"}` as `{"max": "100 %"}`."""
    if not limit:
        return None
    unit = limit.get("unit")
    shown: dict[str, Any] = {}
    for key, value in limit.items():
        if key == "unit":
            continue
        name = _LIMIT_KEYS.get(key, key)
        if key == "wait_s" and isinstance(value, int | float):
            shown[name] = f"{value:.1f} s"
        elif key == "rate_per_s" and isinstance(value, int | float) and unit:
            shown[name] = f"{format_quantity(float(value), unit)}/s"
        elif isinstance(value, int | float) and not isinstance(value, bool) and unit:
            shown[name] = format_quantity(float(value), unit)
        else:
            shown[name] = value
    return shown


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
    if spec is None or spec.unit is None:
        return None
    if kernel_code == "above_max" and spec.max is not None:
        return {"max": spec.max, "unit": spec.unit}
    if kernel_code == "below_min" and spec.min is not None:
        return {"min": spec.min, "unit": spec.unit}
    return None


def _is_file_limit(file: DeviceFile, channel: str | None, limit: dict[str, Any] | None) -> bool:
    """True unless the limit is a session limit tighter than the file's own."""
    if channel is None or not limit:
        return True
    spec = file.write.get(channel)
    if spec is None:
        return True
    for key in ("max", "min"):
        if key in limit and getattr(spec, key) is not None and limit[key] != getattr(spec, key):
            return False
    return True


def target_parts(target: str | None) -> tuple[str | None, str | None]:
    """`write:fan_speed` and `read:fan_speed` as (fan_speed, None), and `action:home` as (None, home)."""
    kind, _, name = (target or "").partition(":")
    if kind in ("write", "read"):
        return name or None, None
    if kind == "action":
        return None, name or None
    return None, None


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
) -> RpcError:
    """A registry error for a kernel block, with every data field the hub can fill in."""
    channel, action = target_parts(target)
    runtime = hub.kernel.devices.get(device or "")
    file = runtime.file if runtime is not None else None
    if file is not None and channel is not None and limit is None and kernel_code in ("above_max", "below_min"):
        limit = _file_limit(file, channel, kernel_code)
    data: dict[str, Any] = {
        "kernelMessage": kernel_message,
        "device": device,
        "channel": channel,
        "action": action,
        "requested": requested(file, channel, raw_value),
        "limit": format_limit(limit),
        "requestId": request_id,
    }
    error = from_kernel(kernel_code)
    if file is not None and error.name in PROVENANCE_NAMES and _is_file_limit(file, channel, limit):
        confirmed = confirmation(file, channel, action)
        data["file"] = file_name(hub, file.device_id)
        data["confirmedBy"] = confirmed.by if confirmed is not None else None
        data["confirmedAt"] = when(confirmed.at) if confirmed is not None else None
    return from_kernel(kernel_code, data)


def raw_value(command: Command | None) -> Any:
    if isinstance(command, Write):
        return command.value
    return None


def decision_error(hub: Hub, decision: Decision, command: Command | None = None) -> RpcError:
    """The registry error for a blocked or failed decision."""
    return kernel_error(
        hub,
        decision.code,
        device=decision.device,
        target=decision.target,
        kernel_message=decision.message,
        raw_value=raw_value(command),
        limit=decision.limit,
        request_id=decision.request_id,
    )


def decision(hub: Hub, kernel: Decision, command: Command | None = None, *, step: str | None = None) -> m.Decision:
    """A kernel decision as a protocol Decision. Blocked and failed ones carry their registry error."""
    error = None
    if kernel.status in ("blocked", "failed"):
        error = m.ErrorObject.model_validate(decision_error(hub, kernel, command).to_object())
    return m.Decision(
        status=kernel.status,
        device=kernel.device,
        target=kernel.target,
        value=kernel.value,
        unit=kernel.unit,
        request_id=kernel.request_id,
        step=step,
        error=error,
    )


def wire_value(value: Any) -> m.Value:
    """A command value as the protocol sends it. A REST quantity mapping becomes a quantity string."""
    if isinstance(value, dict):
        return f"{value.get('value')} {value.get('unit')}"
    if isinstance(value, str | bool | int | float):
        return value
    return str(value)


def command(kernel: Command) -> m.WriteCommand | m.ActionCommand:
    if isinstance(kernel, Write):
        return m.WriteCommand(device=kernel.device, channel=kernel.channel, value=wire_value(kernel.value))
    args = {name: wire_value(value) for name, value in kernel.args.items()}
    return m.ActionCommand(device=kernel.device, action=kernel.action, args=args)


def kernel_command(message: m.WriteCommand | m.ActionCommand) -> Command:
    if isinstance(message, m.WriteCommand):
        return Write(device=message.device, channel=message.channel, value=message.value)
    return Action(device=message.device, action=message.action, args=dict(message.args))


def request(hub: Hub, item: Request) -> m.ConfirmationRequest:
    now = hub.kernel.clock()
    return m.ConfirmationRequest(
        request_id=item.request_id,
        status=item.status,
        command=command(item.command),
        requested_by=item.principal.label,
        expires_in_s=round(max(0.0, item.expires_at - now), 1) if item.status == "pending" else 0.0,
        dry_run=decision(hub, item.dry_run, item.command),
        decided_by=item.decided_by,
        result=decision(hub, item.result, item.command) if item.result is not None else None,
    )


def summary(hub: Hub, device_id: str) -> m.DeviceSummary:
    runtime = hub.kernel.devices[device_id]
    file = runtime.file
    info = hub.info.get(device_id)
    return m.DeviceSummary(
        id=device_id,
        name=file.device.name,
        model=file.device.model,
        manufacturer=file.device.manufacturer,
        driver=file.connect.driver,
        hazard=file.effective_hazard,
        writable=file.writable,
        connected=runtime.connected,
        unavailable=runtime.available or None,
        last_error=views.device_text(f"{device_id} driver error", info.last_error) if info else None,
        verification=file.provenance.verification.status,
        source=file.provenance.source,
        conformance=runtime.driver.info.conformance,
    )


def _confirmed(item: Confirmation | None) -> m.Confirmed | None:
    if item is None:
        return None
    return m.Confirmed(by=item.by, at=when(item.at) or "")


def _current(runtime: Any, channel: str, now: float) -> dict[str, Any]:
    sample = runtime.latest(channel, now)
    if sample is None:
        return {"value": None, "known": False, "age_s": None}
    value = views.device_value(runtime.file, runtime.file.device_id, channel, sample.value)
    return {"value": value, "known": True, "age_s": round(max(0.0, now - sample.at), 3)}


def description(hub: Hub, device_id: str) -> m.DeviceDescription:
    """Everything a client needs before a write, including where the limits come from."""
    runtime = hub.kernel.devices[device_id]
    file = runtime.file
    now = hub.kernel.clock()
    info = hub.info.get(device_id)
    high = file.effective_hazard == "high"
    read = {
        name: m.ReadChannelInfo(
            type=spec.type,
            unit=spec.unit,
            every_s=spec.every,
            stream=spec.stream,
            range=list(spec.range) if spec.range else None,
            values=spec.values or None,
            **_current(runtime, name, now),
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
            **_current(runtime, name, now),
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
    provenance = m.LimitsProvenance(
        file=file_name(hub, device_id),
        confirmed=_confirmed(file.confirmed),
        bound=file.confirmed is not None and file.confirmed.sha256 is not None,
        unconfirmed=file.unconfirmed(),
        source=file.provenance.source,
        by=file.provenance.by,
        at=when(file.provenance.at),
    )
    return m.DeviceDescription(
        **summary(hub, device_id).model_dump(),
        read=read,
        write=write,
        actions=actions,
        interlocks=[
            m.InterlockInfo.model_validate({"if": item.if_, "require": item.require, "message": item.message})
            for item in file.interlocks
        ],
        watchdog=watchdog,
        safe_state=[step.model_dump(mode="json") for step in file.safe_state],
        safe_state_support=runtime.driver.info.safe_state_support,
        notes=views.data_block(f"device file {device_id} notes", file.notes),
        warnings=info.warnings if info else [],
        limits_provenance=provenance,
    )


def reading(hub: Hub, device_id: str, item: DriverReading) -> m.Reading:
    file = hub.kernel.devices[device_id].file
    return m.Reading(
        device=device_id,
        channel=item.channel,
        value=views.device_value(file, device_id, item.channel, item.value),
        unit=item.unit,
        at=item.at,
        suspect=item.suspect,
    )


def audit_entry(entry: Entry) -> m.AuditEntry:
    return m.AuditEntry(
        seq=entry.seq,
        at=entry.at,
        event=entry.event,
        principal=entry.principal,
        device=entry.device,
        target=entry.target,
        status=entry.status,
        code=entry.code,
        details=views.audit_details(entry.device, entry.body.get("details", {})),
        hash=entry.hash,
    )
