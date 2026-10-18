"""Declarative YAML routines (ADR 0007).

A routine is data. Triggers say when it runs, steps say what it does, and every write or action a
step produces goes through the safety kernel like any other command.

    id: keep-cool
    triggers:
      - every: 30 s
      - when: "desk-fan.temperature > 28 degC"
    steps:
      - if: "desk-fan.temperature > 28 degC"
        then:
          - write: { device: desk-fan, channel: fan_speed, value: 60 % }
        else:
          - write: { device: desk-fan, channel: fan_speed, value: 20 % }
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from openhal.spec import expressions
from openhal.spec.models import ID_PATTERN, Seconds

MAX_STEPS: Final = 200
MAX_DEPTH: Final = 4


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class WriteStep(_Strict):
    write: dict[str, Any]

    @model_validator(mode="after")
    def _shape(self) -> WriteStep:
        if set(self.write) != {"device", "channel", "value"}:
            raise ValueError("A write step needs exactly device, channel and value.")
        return self


class ActionStep(_Strict):
    action: dict[str, Any]

    @model_validator(mode="after")
    def _shape(self) -> ActionStep:
        if not {"device", "action"} <= set(self.action) <= {"device", "action", "args"}:
            raise ValueError("An action step needs device and action, and may have args.")
        return self


class WaitStep(_Strict):
    wait: Seconds

    @model_validator(mode="after")
    def _bounded(self) -> WaitStep:
        if self.wait > 3600:
            raise ValueError("A wait can be at most 1 h.")
        return self


class LogStep(_Strict):
    log: str = Field(max_length=300)


class IfStep(_Strict):
    if_: str = Field(alias="if", max_length=expressions.MAX_LENGTH)
    then: list[Step] = []
    else_: list[Step] = Field(default=[], alias="else")

    @model_validator(mode="after")
    def _parse(self) -> IfStep:
        try:
            expressions.parse(self.if_)
        except expressions.ExpressionError as exc:
            raise ValueError(f"if: {exc}") from exc
        return self


Step = WriteStep | ActionStep | WaitStep | LogStep | IfStep


class EveryTrigger(_Strict):
    every: Seconds


class AtTrigger(_Strict):
    at: Annotated[str, Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]


class WhenTrigger(_Strict):
    when: str = Field(max_length=expressions.MAX_LENGTH)

    @model_validator(mode="after")
    def _parse(self) -> WhenTrigger:
        try:
            expressions.parse(self.when)
        except expressions.ExpressionError as exc:
            raise ValueError(f"when: {exc}") from exc
        return self


class ManualTrigger(_Strict):
    manual: Literal[True]


Trigger = EveryTrigger | AtTrigger | WhenTrigger | ManualTrigger


class Routine(_Strict):
    """A YAML routine."""

    id: Annotated[str, Field(pattern=ID_PATTERN)]
    description: str | None = Field(default=None, max_length=500)
    triggers: list[Trigger] = Field(default=[ManualTrigger(manual=True)], min_length=1, max_length=20)
    steps: list[Step] = Field(min_length=1)
    on_block: Literal["stop", "continue"] = "stop"
    max_runtime: Seconds = 600.0

    @model_validator(mode="after")
    def _limits(self) -> Routine:
        count, depth = _count(self.steps, 1)
        if count > MAX_STEPS:
            raise ValueError(f"A routine may have at most {MAX_STEPS} steps.")
        if depth > MAX_DEPTH:
            raise ValueError(f"if steps may nest at most {MAX_DEPTH} levels.")
        for trigger in self.triggers:
            if isinstance(trigger, EveryTrigger) and trigger.every < 1:
                raise ValueError("every must be at least 1 s.")
        return self

    def devices(self) -> set[str]:
        """Every device the routine writes to or runs actions on."""
        return {device for device, _ in _targets(self.steps)}


def _count(steps: list[Step], depth: int) -> tuple[int, int]:
    total, deepest = 0, depth
    for step in steps:
        total += 1
        if isinstance(step, IfStep):
            for branch in (step.then, step.else_):
                count, inner = _count(branch, depth + 1)
                total += count
                deepest = max(deepest, inner)
    return total, deepest


def _targets(steps: list[Step]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for step in steps:
        if isinstance(step, WriteStep):
            found.append((str(step.write["device"]), f"write:{step.write['channel']}"))
        elif isinstance(step, ActionStep):
            found.append((str(step.action["device"]), f"action:{step.action['action']}"))
        elif isinstance(step, IfStep):
            found.extend(_targets(step.then))
            found.extend(_targets(step.else_))
    return found


def content_sha256(kind: str, source: str) -> str:
    """The hash an approval is bound to. YAML is hashed after parsing, so comments don't matter."""
    if kind == "yaml":
        from openhal.spec.loader import parse_yaml

        parsed = parse_yaml(source)
        canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(f"yaml:{canonical}".encode()).hexdigest()
    return hashlib.sha256(f"python:{source}".encode()).hexdigest()


PYTHON_RUN: Final = re.compile(r"^async def run\(ctx\)", re.MULTILINE)


IfStep.model_rebuild()
Routine.model_rebuild()
