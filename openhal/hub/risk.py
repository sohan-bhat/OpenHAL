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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml

from openhal.hub.limits import APPLY_PHRASE, APPROVE_PHRASE, HeldChanges, HeldRequest, LimitError, device_file
from openhal.kernel.principals import Principal
from openhal.spec import risk
from openhal.spec.loader import DeviceFileError, from_data

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
class RiskRequest(HeldRequest):
    """A lowering held until a person approves it."""

    change: RiskChange


class RiskChanges(HeldChanges[RiskRequest]):
    """Risk level changes for one hub, with the pending lowerings a person approves."""

    EVENT = "risk_change"
    NOUN = "risk change"

    def _target(self, change: RiskChange) -> str:
        return change.target

    def _read(self, device_id: str) -> tuple[Path, dict[str, Any]]:
        path, data, _file = device_file(self.hub, device_id)
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
        self._make_room(who)
        now = self.hub.kernel.clock()
        request = RiskRequest(f"risk-{secrets.token_hex(6)}", change, who, now, now + self.hub.config.confirm.ttl_s)
        return self._filed(request, before=change.before, after=change.after)

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
