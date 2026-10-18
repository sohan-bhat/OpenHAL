"""Pure value checks used by the kernel. Units, types, ranges, steps and enums.

Every function here is deterministic and raises `Block` with a stable code and a message that
names the rule, the limit and what to do (docs/SAFETY.md, checks 6 to 9).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from openhal.spec.models import ArgSpec, WriteChannel
from openhal.spec.units import UnitError, convert, format_quantity, parse_quantity


@dataclass
class Block(Exception):  # noqa: N818
    """A command is blocked. `code` is one of commands.BLOCK_CODES."""

    code: str
    message: str
    limit: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class Limits:
    """The effective numeric limits for one channel, after any session tightening."""

    min: float
    max: float
    rate: float | None


def effective_limits(spec: WriteChannel | ArgSpec, tightened: dict[str, float] | None = None) -> Limits:
    """Combine a channel's file limits with session limits, which can only narrow them."""
    assert spec.min is not None
    assert spec.max is not None
    low, high = spec.min, spec.max
    rate = spec.max_change_per_s if isinstance(spec, WriteChannel) else None
    if tightened:
        low = max(low, tightened.get("min", low))
        high = min(high, tightened.get("max", high))
        if "rate" in tightened:
            rate = tightened["rate"] if rate is None else min(rate, tightened["rate"])
    return Limits(low, high, rate)


def normalize(
    name: str,
    spec: WriteChannel | ArgSpec,
    raw: Any,
    *,
    tightened: dict[str, float] | None = None,
) -> float | bool | str:
    """Convert a raw value into the channel's unit and type and check it against every static limit."""
    if spec.type == "bool":
        if not isinstance(raw, bool):
            raise Block("bad_value", f"{name} needs true or false.")
        return raw
    if spec.type == "enum":
        if not isinstance(raw, str) or raw not in spec.values:
            raise Block("bad_value", f"{name} must be one of {', '.join(spec.values)}.", {"values": spec.values})
        return raw
    if spec.type == "string":
        if not isinstance(raw, str):
            raise Block("bad_value", f"{name} needs text.")
        assert spec.max_length is not None
        if len(raw) > spec.max_length:
            raise Block("bad_value", f"{name} may be at most {spec.max_length} characters.")
        if spec.pattern is not None and not re.fullmatch(spec.pattern, raw):
            raise Block("bad_value", f"{name} doesn't match the allowed pattern.")
        return raw
    return _number(name, spec, raw, tightened)


def _number(name: str, spec: WriteChannel | ArgSpec, raw: Any, tightened: dict[str, float] | None) -> float:
    unit = spec.unit
    assert unit is not None
    if isinstance(raw, bool) or not isinstance(raw, str | dict | int | float):
        raise Block("bad_unit", f"{name} needs a number with a unit, for example {format_quantity(1, unit)}.")
    if isinstance(raw, int | float):
        raise Block("bad_unit", f"{name} needs a unit. Send {format_quantity(float(raw), unit)} rather than {raw}.")
    try:
        value = convert(parse_quantity(raw), unit)
    except UnitError as exc:
        raise Block("bad_unit", f"{name}: {exc}") from exc
    if not math.isfinite(value):  # pragma: no cover (convert already refuses non-finite values, kept as a backstop)
        raise Block("bad_unit", f"{name} must be a finite number.")
    limits = effective_limits(spec, tightened)
    asked = format_quantity(value, unit)
    if value < limits.min and not math.isclose(value, limits.min, rel_tol=1e-12, abs_tol=1e-12):
        raise Block(
            "below_min",
            f"Blocked. The {name} limit is {format_quantity(limits.min, unit)} (min). Asked for {asked}.",
            {"min": limits.min, "unit": unit},
        )
    if value > limits.max and not math.isclose(value, limits.max, rel_tol=1e-12, abs_tol=1e-12):
        raise Block(
            "above_max",
            f"Blocked. The {name} limit is {format_quantity(limits.max, unit)} (max). Asked for {asked}.",
            {"max": limits.max, "unit": unit},
        )
    if spec.step is not None:
        steps = (value - (spec.min or 0.0)) / spec.step
        if not math.isclose(steps, round(steps), rel_tol=0, abs_tol=1e-6):
            raise Block(
                "bad_step",
                f"Blocked. {name} moves in steps of {format_quantity(spec.step, unit)} from "
                f"{format_quantity(spec.min or 0.0, unit)}. Asked for {asked}.",
                {"step": spec.step, "unit": unit},
            )
    return value


def check_rate(
    name: str,
    unit: str,
    rate: float | None,
    new: float,
    reference: float | None,
    elapsed_s: float,
) -> None:
    """Block a change bigger than `rate` times the elapsed time since the reference value."""
    if rate is None or reference is None:
        return
    elapsed = min(max(elapsed_s, 0.0), 3600.0)
    allowed = rate * elapsed
    change = abs(new - reference)
    if change > allowed and not math.isclose(change, allowed, rel_tol=1e-9, abs_tol=1e-9):
        low = reference - allowed
        high = reference + allowed
        wait = (change - allowed) / rate
        raise Block(
            "rate_limited",
            f"Blocked. {name} may change by {format_quantity(rate, unit)} per second. "
            f"Right now it can go from {format_quantity(low, unit)} to {format_quantity(high, unit)}. "
            f"Asked for {format_quantity(new, unit)}, which is possible in {wait:.1f} s, or use small steps.",
            {"rate_per_s": rate, "unit": unit, "from": low, "to": high, "wait_s": wait},
        )
