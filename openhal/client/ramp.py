"""Plan a ramp to a target value in steps that each pass the channel's rate limit.

The kernel blocks a write whose change from the last accepted value exceeds `max_change_per_s`
times the elapsed time, and never ramps on its own (docs/SAFETY.md). `ramp_to` on the clients
uses this plan to send a series of writes, one per interval, each small enough to pass. The
kernel still checks every step.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from openhal.client.models import DeviceView
from openhal.spec.units import UnitError, convert, format_quantity, parse_quantity


@dataclass(frozen=True, slots=True)
class RampPlan:
    channel: str
    unit: str
    start: float
    target: float
    values: list[float]
    """Each value to send in `unit`, one interval apart."""
    interval_s: float


def plan_ramp(
    view: DeviceView,
    channel: str,
    target: str,
    *,
    interval_s: float = 1.0,
    margin: float = 0.9,
    start: float | None = None,
) -> RampPlan:
    """Work out the steps from the channel's current value to `target`.

    `start` overrides the current value the hub reports, for example right after a read.
    """
    if channel not in view.write:
        raise ValueError(f"{view.id} has no write channel {channel!r}.")
    spec = view.write[channel]
    if spec.unit is None or spec.type != "number":
        raise ValueError(f"{view.id}.{channel} is not a numeric channel, so there is nothing to ramp.")
    if not 0 < margin <= 1:
        raise ValueError("margin must be above 0 and at most 1.")
    if interval_s <= 0:
        raise ValueError("interval_s must be above 0.")
    unit = spec.unit
    try:
        goal = convert(parse_quantity(target), unit)
    except UnitError as exc:
        raise ValueError(f"{view.id}.{channel}: {exc}") from exc
    if start is None:
        if not spec.known or not isinstance(spec.value, int | float) or isinstance(spec.value, bool):
            raise ValueError(
                f"The hub doesn't know the current value of {view.id}.{channel} yet. Read it first, or pass start."
            )
        start = float(spec.value)
    rate = spec.max_change_per_s
    if rate is None or rate <= 0 or math.isclose(start, goal):
        return RampPlan(channel, unit, start, goal, [goal], interval_s)
    stride = rate * interval_s * margin
    if spec.step:
        stride = max(spec.step, math.floor(stride / spec.step) * spec.step)
        if stride > rate * interval_s:
            raise ValueError(
                f"{view.id}.{channel} moves in steps of {format_quantity(spec.step, unit)}, more than the rate "
                f"limit allows in {interval_s:g} s. Use a longer interval."
            )
    values: list[float] = []
    current = start
    direction = 1.0 if goal > start else -1.0
    while abs(goal - current) > stride and len(values) < 10_000:
        current += direction * stride
        values.append(_snap(current, spec.min, spec.step))
    values.append(goal)
    return RampPlan(channel, unit, start, goal, values, interval_s)


def _snap(value: float, low: float | None, step: float | None) -> float:
    if not step:
        return round(value, 9)
    base = low or 0.0
    return round(base + round((value - base) / step) * step, 9)
