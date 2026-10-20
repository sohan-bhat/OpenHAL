"""Per-device state the kernel keeps. Last values, unknowns, in-flight commands, watchdog budgets."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from openhal.drivers.base import Driver
from openhal.spec import expressions
from openhal.spec.models import DeviceFile, MaxDuration


@dataclass
class Sample:
    """A value and when it was observed, on the kernel's monotonic clock, in the channel's unit."""

    value: Any
    at: float
    commanded: bool = False


@dataclass
class RuleState:
    """Watchdog bookkeeping for one max_duration rule.

    `active_since` starts when the rule's expression is first true (or unknown) and only resets once
    the expression has been false for `reset_after`. A brief dip doesn't refill the budget.
    """

    rule: MaxDuration
    tree: expressions.Node
    active_since: float | None = None
    false_since: float | None = None
    exhausted: bool = False
    applied: bool = False
    failures: int = 0
    retry_at: float = 0.0


@dataclass
class DeviceRuntime:
    """Everything the kernel knows about one registered device."""

    file: DeviceFile
    driver: Driver
    connected: bool = False
    connected_at: float = 0.0
    faulted: str | None = None
    reference_problem: str | None = None
    applying_safe_state: bool = False
    reads: dict[str, Sample] = field(default_factory=dict)
    accepted: dict[str, Sample] = field(default_factory=dict)
    unknown_since: dict[str, float] = field(default_factory=dict)
    inflight: set[str] = field(default_factory=set)
    inflight_task: asyncio.Task[Any] | None = None
    rules: list[RuleState] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def device_id(self) -> str:
        return self.file.device_id

    @property
    def stale_after_s(self) -> float:
        return max(10.0, 3.0 * self.file.watchdog.heartbeat)

    def mark_unknown(self, channel: str, now: float) -> None:
        """Forget what we knew about a channel, until a fresh reading arrives."""
        self.unknown_since[channel] = now
        self.reads.pop(channel, None)
        self.accepted.pop(channel, None)

    def known_samples(self, channel: str) -> list[Sample]:
        """Samples newer than the last time the channel became unknown."""
        cutoff = self.unknown_since.get(channel)
        samples = [sample for sample in (self.reads.get(channel), self.accepted.get(channel)) if sample is not None]
        if cutoff is not None:
            samples = [sample for sample in samples if sample.at >= cutoff]
        return samples

    def latest(self, channel: str, now: float) -> Sample | None:
        """The newest known value for a channel, or None if it is unknown, stale or changing right now."""
        if channel in self.inflight:
            return None
        candidates = self.known_samples(channel)
        if not candidates:
            return None
        newest = max(candidates, key=lambda sample: sample.at)
        # A write channel is a setpoint the device holds while connected, so its last known value
        # stays valid. Sensor readings go stale.
        if channel not in self.file.write and not newest.commanded and now - newest.at > self.stale_after_s:
            return None
        return newest

    @property
    def available(self) -> str | None:
        """None if the device can take commands, otherwise the reason it can't."""
        if not self.connected:
            return "not connected"
        if self.faulted:
            return f"in a fault state ({self.faulted})"
        if self.applying_safe_state:
            return "applying its safe state"
        return None
