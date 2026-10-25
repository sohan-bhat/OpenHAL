"""Commands and decisions. What a client asks for, and what the kernel answers."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["allowed", "blocked", "needs_confirmation", "done", "pending", "failed"]

BLOCK_CODES = (
    "bad_request",
    "unknown_target",
    "stopped",
    "read_only_file",
    "device_unavailable",
    "not_permitted",
    "bad_unit",
    "bad_value",
    "below_min",
    "above_max",
    "bad_step",
    "rate_limited",
    "interlock",
    "duration_exceeded",
    "busy",
    "needs_confirmation",
    "cannot_loosen",
    "internal_error",
    "driver_error",
    "expired",
    "rejected",
    "queue_full",
    "misconfigured",
)


class Write(BaseModel):
    """Set one write channel. A number carries its unit, in `unit` or as a `{value, unit}` mapping."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["write"] = "write"
    device: str = Field(min_length=1, max_length=48)
    channel: str = Field(min_length=1, max_length=48)
    value: str | bool | dict[str, Any] | int | float
    unit: str | None = Field(default=None, min_length=1, max_length=40)

    @property
    def target(self) -> str:
        return f"write:{self.channel}"


class Action(BaseModel):
    """Run one action with typed arguments."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["action"] = "action"
    device: str = Field(min_length=1, max_length=48)
    action: str = Field(min_length=1, max_length=48)
    args: dict[str, Any] = {}

    @property
    def target(self) -> str:
        return f"action:{self.action}"


Command = Write | Action


class Decision(BaseModel):
    """The kernel's answer to one command. Messages are stable and say what to do next."""

    model_config = ConfigDict(frozen=True)

    status: Status
    code: str | None = None
    message: str
    device: str
    target: str
    value: Any = None
    unit: str | None = None
    limit: dict[str, Any] | None = None
    request_id: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in ("allowed", "done")
