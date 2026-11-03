"""Changing a channel's or action's risk level, by a person, with no device file to edit (ADR 0020).

Raising a level gives an agent less, so a person's raise applies at once. Lowering gives an agent
more, so it needs a person who typed the phrase confirm, under the same terminal and human token
rules as widening a limit. Any other lowering becomes a pending change that only a person approves,
with the phrase approve. Agents see every level and change none.

Each change is written into the device file as the entry's `risk`, with the person and the date,
recorded in the audit log, and applied to the running hub at once. A level a person sets back to the
table's own level drops the entry's `risk`. A stop cancels every pending change.
"""

from __future__ import annotations

import asyncio
import copy
import datetime as dt
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import yaml

from openhal.hub.limits import APPLY_PHRASE, APPROVE_PHRASE, MAX_PENDING, PER_PRINCIPAL, LimitError, Status
from openhal.kernel.principals import Principal
from openhal.spec import risk
from openhal.spec.loader import DeviceFileError, from_data, parse_yaml

if TYPE_CHECKING:
    from openhal.hub.hub import Hub

KINDS: Final = {"write": "write", "action": "actions"}


@dataclass(frozen=True)
class RiskChange:
    """One target's level before and after. `target` is `write:<name>` or `action:<name>`."""

    device: str
    target: str
    before: risk.Level
    after: risk.Level
    classified: risk.Level

    @property
    def name(self) -> str:
        return self.target.partition(":")[2]

    @property
    def lowers(self) -> bool:
        return risk.RANK[self.after] < risk.RANK[self.before]

    def said(self) -> str:
        return f"{self.device}.{self.name} risk {self.before} to {self.after}"

    def view(self) -> dict[str, Any]:
        return {
            "device": self.device,
            "target": self.target,
            "name": self.name,
            "before": self.before,
            "after": self.after,
            "classified": self.classified,
            "lowers": self.lowers,
        }


@dataclass
class RiskRequest:
    """A lowering held until a person approves it."""

    request_id: str
    change: RiskChange
    principal: Principal
    created_at: float
    expires_at: float
    status: Status = "pending"
    decided_by: str | None = None
    result: str | None = None
    history: list[str] = field(default_factory=list)


class RiskChanges:
    """Risk level changes for one hub, with the pending lowerings a person approves."""

    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.requests: dict[str, RiskRequest] = {}
        hub.kernel.on_stop(self._on_stop)

    def _on_stop(self, reason: str) -> None:
        for request in self.requests.values():
            if request.status == "pending":
                self._close(request, "cancelled", "system", f"cancelled by the stop, {reason}")

    def _read(self, device_id: str) -> tuple[Path, dict[str, Any]]:
        """The device's file as data, checked to be the file the hub runs."""
        runtime = self.hub.kernel.devices.get(device_id)
        info = self.hub.info.get(device_id)
        if runtime is None:
            raise KeyError(f"There is no device {device_id!r}.")
        if info is None or not info.path:
            raise LimitError("misconfigured", f"Blocked. {device_id} has no device file in the devices folder.")
        path = Path(info.path)
        try:
            data = parse_yaml(path.read_text(encoding="utf-8"))
            on_disk = from_data(data)
        except (OSError, DeviceFileError) as exc:
            raise LimitError("misconfigured", f"Blocked. {path.name} doesn't load. {exc}") from exc
        if on_disk.limits_sha256() != runtime.file.limits_sha256():
            raise LimitError(
                "misconfigured", f"Blocked. {path.name} changed on disk after the hub loaded the file. Load it first."
            )
        return path, data

    def show(self, device_id: str) -> dict[str, Any]:
        """Every target's level with the reasons, and the pending changes for the device."""
        runtime = self.hub.kernel.devices.get(device_id)
        if runtime is None:
            raise KeyError(f"There is no device {device_id!r}.")
        file = runtime.file
        info = self.hub.info.get(device_id)
        targets = {
            target: {**found.view(), "read_only": bool(file.read_only(target)) if found.kind != "read" else False}
            for target, found in risk.assess(file).items()
        }
        return {
            "device": device_id,
            "hazard": file.effective_hazard,
            "path": info.path if info else None,
            "targets": targets,
            "pending": [self.view(item) for item in self.pending() if item.change.device == device_id],
        }

    def plan(self, device_id: str, name: str, level: str) -> RiskChange:
        """The change a request names. Raises LimitError or KeyError."""
        runtime = self.hub.kernel.devices.get(device_id)
        if runtime is None:
            raise KeyError(f"There is no device {device_id!r}.")
        file = runtime.file
        if level not in risk.LEVELS:
            raise LimitError("bad_request", f"Blocked. A risk level is low, medium or high, not {level!r}.")
        if name in file.write:
            target = f"write:{name}"
        elif name in file.actions:
            target = f"action:{name}"
        elif name in file.read:
            raise LimitError("bad_request", f"Blocked. Reading {name} is always low, so its level never changes.")
        else:
            raise KeyError(f"{device_id} has no write channel or action {name!r}.")
        found = risk.assess(file)[target]
        if level == found.level:
            raise LimitError("bad_request", f"Blocked. {device_id}.{name} is {level} already.")
        return RiskChange(device_id, target, found.level, level, found.classified)

    async def apply(self, change: RiskChange, who: Principal) -> Path:
        """Write the level into the file and give it to the running hub. `who` is a human principal."""
        path, data = self._read(change.device)
        updated = copy.deepcopy(data)
        section = KINDS[change.target.partition(":")[0]]
        entry = updated[section][change.name]
        if change.after == change.classified:
            entry.pop("risk", None)
        else:
            entry["risk"] = {"level": change.after, "by": who.name[:80], "at": dt.date.today().isoformat()}
        try:
            file = from_data(updated)
        except DeviceFileError as exc:
            raise LimitError("bad_request", "Blocked. " + " ".join(exc.problems)) from exc
        if risk.level(file, change.target) != change.after:
            raise LimitError(
                "misconfigured",
                f"Blocked. {change.device}.{change.name} shares its pin with a higher target, so it stays "
                f"{risk.level(file, change.target)}. Change that one too.",
            )
        text = yaml.safe_dump(updated, sort_keys=False, allow_unicode=True, width=100)
        await asyncio.to_thread(path.write_text, text, "utf-8")
        runtime = self.hub.kernel.devices[change.device]
        async with runtime.lock:
            runtime.file = file
        self.hub.audit.append(
            "risk_change",
            who.label,
            device=change.device,
            target=change.target,
            status="done",
            before=change.before,
            after=change.after,
        )
        self.hub.notify_state(change.device)
        return path

    async def request(
        self, who: Principal, device_id: str, name: str, level: str, *, phrase: str | None = None
    ) -> dict[str, Any]:
        """Raise at once, apply a person's confirmed lowering, or hold any other lowering."""
        try:
            if who.kind != "human":
                raise LimitError(
                    "not_permitted", "Blocked. Only a person changes a risk level. describe_device shows every level."
                )
            self._read(device_id)
            change = self.plan(device_id, name, level)
            if not change.lowers:
                await self.apply(change, who)
                return self._result("done", change, f"Done. {change.said()}.")
            if phrase is not None:
                if phrase.strip().lower() != APPLY_PHRASE:
                    raise LimitError("bad_request", f"Blocked. Type {APPLY_PHRASE} to lower a risk level.")
                await self.apply(change, who)
                return self._result("done", change, f"Done. {change.said()}.")
            held = self.hold(change, who)
        except LimitError as error:
            self.hub.audit.append(
                "risk_change",
                who.label,
                device=device_id,
                target=name,
                status="blocked",
                code=error.code,
                message=error.message,
            )
            return {"status": "blocked", "code": error.code, "message": error.message, "device": device_id}
        message = (
            f"Held for a person. {change.said()} gives an agent more, so a person approves the change with "
            f"openhal confirm approve {held.request_id} or in the Inspector."
        )
        return {**self._result("pending", change, message), "request_id": held.request_id}

    @staticmethod
    def _result(status: str, change: RiskChange, message: str) -> dict[str, Any]:
        return {"status": status, "message": message, **change.view()}

    def hold(self, change: RiskChange, who: Principal) -> RiskRequest:
        self.expire()
        pending = [item for item in self.requests.values() if item.status == "pending"]
        mine = [item for item in pending if item.principal == who]
        if len(mine) >= PER_PRINCIPAL or len(pending) >= MAX_PENDING:
            raise LimitError("queue_full", "Blocked. Too many changes are waiting for a person already.")
        now = self.hub.kernel.clock()
        request = RiskRequest(f"risk-{secrets.token_hex(6)}", change, who, now, now + self.hub.config.confirm.ttl_s)
        self.requests[request.request_id] = request
        self.hub.audit.append(
            "risk_change",
            who.label,
            device=change.device,
            target=change.target,
            status="pending",
            request=request.request_id,
            before=change.before,
            after=change.after,
        )
        return request

    def get(self, request_id: str) -> RiskRequest | None:
        return self.requests.get(request_id)

    def expire(self) -> None:
        now = self.hub.kernel.clock()
        for request in self.requests.values():
            if request.status == "pending" and now > request.expires_at:
                self._close(request, "expired", "system", "expired")

    def _close(self, request: RiskRequest, status: Status, by: str, note: str) -> None:
        request.status = status
        request.decided_by = by if status in ("done", "rejected") else request.decided_by
        request.result = note
        request.history.append(note)
        self.hub.audit.append(
            "risk_change",
            by,
            device=request.change.device,
            target=request.change.target,
            status=status,
            request=request.request_id,
            message=note,
        )

    def pending(self) -> list[RiskRequest]:
        self.expire()
        return sorted((item for item in self.requests.values() if item.status == "pending"), key=_created)

    def recent(self, limit: int = 100) -> list[RiskRequest]:
        self.expire()
        return sorted(self.requests.values(), key=_created, reverse=True)[:limit]

    async def approve(self, request_id: str, who: Principal, phrase: str | None) -> RiskRequest:
        """A person approves a pending lowering. The level must still be what it was when it was asked for."""
        request = self.requests[request_id]
        self.expire()
        if request.status != "pending":
            raise LookupError(f"The risk change {request_id} is {request.status}, so there is nothing to approve.")
        if (phrase or "").strip().lower() != APPROVE_PHRASE:
            raise LimitError("bad_request", f"Blocked. Type {APPROVE_PHRASE} to approve this risk change.")
        asked = request.change
        try:
            change = self.plan(asked.device, asked.name, asked.after)
            if change.before != asked.before:
                raise LimitError("misconfigured", "Blocked. The level changed after the request. Ask again.")
            await self.apply(change, who)
        except (LimitError, KeyError) as error:
            self._close(request, "blocked", who.label, str(getattr(error, "message", error)))
            return request
        self._close(request, "done", who.label, f"Done. {change.said()}.")
        return request

    def reject(self, request_id: str, who: Principal, reason: str = "") -> RiskRequest:
        request = self.requests[request_id]
        self.expire()
        if request.status != "pending":
            raise LookupError(f"The risk change {request_id} is {request.status}, so there is nothing to reject.")
        self._close(request, "rejected", who.label, f"Rejected. {reason}".strip())
        return request

    def view(self, request: RiskRequest) -> dict[str, Any]:
        """A pending change in the shape of a held command, so every list of held requests shows both."""
        now = self.hub.kernel.clock()
        change = request.change
        held = {
            "status": "needs_confirmation",
            "code": "needs_confirmation",
            "message": f"{change.said()} gives an agent more, so a person approves the change.",
            "device": change.device,
            "target": f"risk:{change.name}",
            "value": change.after,
            "unit": None,
            "limit": None,
            "request_id": request.request_id,
        }
        result = None
        if request.status in ("done", "blocked"):
            result = {**held, "status": request.status, "code": None, "message": request.result or ""}
        return {
            "id": request.request_id,
            "status": request.status,
            "command": {"kind": "risk", **change.view()},
            "requested_by": request.principal.label,
            "created_at": request.created_at,
            "expires_at": request.expires_at,
            "expires_in_s": round(max(0.0, request.expires_at - now), 1) if request.status == "pending" else 0.0,
            "dry_run": held,
            "decided_by": request.decided_by,
            "result": result,
        }


def _created(request: RiskRequest) -> float:
    return request.created_at
