"""Per-device state the kernel keeps. Last values, rate-limit references, watchdog budgets."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from openhal.drivers.base import Driver
from openhal.spec import expressions
from openhal.spec.models import DeviceFile, MaxDuration


@dataclass
class Sample:
    """A value and when it was observed, on the kernel's monotonic clock."""

    value: Any
    at: float
    commanded: bool = False


@dataclass
class RuleState:
    """Watchdog bookkeeping for one max_duration rule."""

    rule: MaxDuration
    tree: expressions.Node
    active_since: float | None = None
    false_since: float | None = None
    exhausted: bool = False


@dataclass
class DeviceRuntime:
    """Everything the kernel knows about one registered device."""

    file: DeviceFile
    driver: Driver
    connected: bool = False
    connected_at: float = 0.0
    faulted: str | None = None
    applying_safe_state: bool = False
    reads: dict[str, Sample] = field(default_factory=dict)
    accepted: dict[str, Sample] = field(default_factory=dict)
    rules: list[RuleState] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def device_id(self) -> str:
        return self.file.device_id

    @property
    def stale_after_s(self) -> float:
        return max(10.0, 3.0 * self.file.watchdog.heartbeat)

    def latest(self, channel: str, now: float) -> Sample | None:
        """The newest known value for a channel, or None if it is unknown or stale."""
        read = self.reads.get(channel)
        written = self.accepted.get(channel)
        candidates = [sample for sample in (read, written) if sample is not None]
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
