"""Who is asking. Humans, agents, routines and the hub itself are different principals (ADR 0012)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

Kind = Literal["human", "agent", "routine", "system"]
Scope = Literal["read", "control_low", "control_medium"]

SCOPE_RANK: Final = {"read": 0, "control_low": 1, "control_medium": 2}
HAZARD_SCOPE: Final = {"low": "control_low", "medium": "control_medium", "high": "control_medium"}


@dataclass(frozen=True, slots=True)
class Principal:
    """The identity behind a command. `name` appears in the audit log."""

    kind: Kind
    name: str
    scope: Scope = "read"
    ref: str | None = None
    """For routines, the SHA-256 of the routine's canonical content. Approvals are bound to it."""

    @property
    def label(self) -> str:
        return f"{self.kind}:{self.name}"

    def covers(self, hazard: str) -> bool:
        """True if this principal's scope allows controlling a device of this hazard class."""
        if self.kind in ("human", "system"):
            return True
        needed = HAZARD_SCOPE[hazard]
        return SCOPE_RANK[self.scope] >= SCOPE_RANK[needed]


SYSTEM: Final = Principal("system", "kernel", "control_medium")
"""The hub acting on its own, for safe states and watchdog actions."""


def human(name: str = "owner") -> Principal:
    return Principal("human", name, "control_medium")


def agent(name: str, scope: Scope = "read") -> Principal:
    return Principal("agent", name, scope)


def routine(name: str, scope: Scope = "control_low", content_sha256: str | None = None) -> Principal:
    return Principal("routine", name, scope, content_sha256)
