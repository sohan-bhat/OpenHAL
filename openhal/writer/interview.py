"""The limits interview, the one set of questions every way of confirming limits asks.

`openhal init`, `openhal file confirm`, the driver writer and the Inspector all ask these
questions and check each answer with `problem`, so a value outside what the device reports is
refused the same way everywhere. Questions cover every high risk write channel and action (ADR 0023),
because low and medium ones take commands within the device's own range with no interview. A draft
from a manual, a sketch or an agent has no range the device reported, so it gets every question, and
the driver writer and the Inspector's review, which a person starts on purpose, ask every question. For a
channel they ask the unit, min, max, rate, safe value and confirmation tier, and for an action its
argument limits, requirements, a run limit and the tier. Then they ask the device's hazard class,
the action that makes the device safe and its interlocks. A draft that doesn't load as a device file
yet gets every question, since its levels can't be told. Each question carries a suggestion and the
reason for the suggestion. The callers check that a human principal gave the answers, and the file
gets a `confirmed` entry bound to the hash of its limits once every question is answered. A draft an
agent proposes still goes through every question.
"""

from __future__ import annotations

import copy
import datetime as dt
import math
import re
from dataclasses import dataclass
from typing import Any, Final

from openhal.spec import risk
from openhal.spec.loader import DeviceFileError, from_data
from openhal.spec.units import (
    Quantity,
    UnitError,
    convert,
    convert_rate,
    format_quantity,
    normalize_unit,
    parse_quantity,
)

TIERS: Final = ("none", "confirm", "confirm-each-time")
HAZARDS: Final = ("low", "medium", "high")
DEVICE_LIMITS: Final = "x-device-limits"
"""Where a device file keeps the range each channel and argument has on the device itself."""
REPORTING_SOURCES: Final = ("self-described", "driver-describe")
RANGE_SOURCES: Final = risk.RANGE_SOURCES
"""Drafts whose ranges came from the device itself or the curated library. Only these skip low and medium questions."""
_DEFAULT_TIER: Final = {"low": "none", "medium": "confirm", "high": "confirm-each-time"}
_INTERLOCK: Final = re.compile(
    r"^\s*if\s+(?P<condition>.+?)\s+require\s+(?P<require>.+?)(?:\s+because\s+(?P<message>.+?))?\s*$", re.I
)
_REQUIREMENT: Final = re.compile(r"^\s*(?P<condition>.+?)(?:\s+because\s+(?P<message>.+?))?\s*$", re.I)
_RUNS: Final = re.compile(r"^\s*(?P<count>\d+)\s*(?:times?\s+)?(?:per|every|in)\s+(?P<per>.+?)\s*$", re.I)
_BARE_NUMBER: Final = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
_SAFE_ACTION_NAMES: Final = ("stop", "off", "halt", "abort", "park", "disable", "home")
_NONE: Final = ("none", "no", "")
_TIER_REASON: Final = (
    "confirm holds a change until a person approves, and one approval covers repeats for 10 minutes. "
    "confirm-each-time needs an approval every time."
)


@dataclass(frozen=True)
class Question:
    id: str
    prompt: str
    suggested: Any
    reason: str
    channel: str | None = None
    field: str | None = None
    unit: str | None = None
    kind: str = "text"
    range: tuple[float, float] | None = None
    choices: tuple[str, ...] = ()

    def view(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "channel": self.channel,
            "field": self.field,
            "prompt": self.prompt,
            "suggested": self.suggested,
            "unit": self.unit,
            "reason": self.reason,
            "kind": self.kind,
            "range": list(self.range) if self.range is not None else None,
        }


class AnswerError(ValueError):
    """An answer could not be applied. The message names the question and what to fix."""


def shown(value: float, unit: str | None) -> str:
    """A number with its unit as a person reads it, such as 100 % or 2.5 degC."""
    if unit is None or unit == "dimensionless":
        return f"{value:.6g}"
    return format_quantity(value, unit)


def suggestion_text(question: Question) -> str | None:
    """The suggestion as the text a person would type, or None when there is no suggestion."""
    value = question.suggested
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float) and question.unit:
        return shown(float(value), question.unit)
    return str(value)


def _safe_values(draft: dict[str, Any]) -> dict[str, Any]:
    safe = draft.get("safe_state")
    if isinstance(safe, dict):
        return dict(safe)
    values: dict[str, Any] = {}
    for step in safe or []:
        if isinstance(step, dict) and "action" not in step:
            values.update(step.get("values", step))
    return values


def _source(draft: dict[str, Any]) -> str:
    provenance = draft.get("provenance")
    source = provenance.get("source") if isinstance(provenance, dict) else None
    return str(source or "hand-written")


def _source_reason(draft: dict[str, Any]) -> str:
    return {
        "self-described": "The board reports this limit itself.",
        "driver-describe": "The driver read this from the device.",
        "sketch": "The sketch's code suggests this value.",
        "manual": "The manual suggests this value.",
        "library": "The device library suggests this value.",
    }.get(_source(draft), "The device file suggests this value.")


def _pair(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, list | tuple) or len(value) != 2:
        return None
    low, high = value
    numbers = (int, float)
    if isinstance(low, bool) or isinstance(high, bool) or not (isinstance(low, numbers) and isinstance(high, numbers)):
        return None
    return (float(low), float(high)) if low <= high else None


def device_limits(draft: dict[str, Any]) -> dict[str, tuple[float, float]]:
    """The range of each channel and action argument on the device itself, by `channel` or `action.arg`.

    A file keeps them in `x-device-limits`. A draft the device described itself, and that has no such
    entry yet, takes them from the min and max of each entry still marked suggested, which are what
    the device reported. A confirmed min or max is the person's own limit, so it says nothing about
    the device.
    """
    kept = draft.get(DEVICE_LIMITS)
    if isinstance(kept, dict):
        return {str(key): pair for key, value in kept.items() if (pair := _pair(value)) is not None}
    if _source(draft) not in REPORTING_SOURCES:
        return {}
    found: dict[str, tuple[float, float]] = {}
    for name, spec in (draft.get("write") or {}).items():
        if isinstance(spec, dict) and spec.get("suggested") and spec.get("type", "number") == "number":
            pair = _pair([spec.get("min"), spec.get("max")])
            if pair is not None:
                found[name] = pair
    for name, spec in (draft.get("actions") or {}).items():
        if not (spec or {}).get("suggested"):
            continue
        for arg, arg_spec in ((spec or {}).get("args") or {}).items():
            if isinstance(arg_spec, dict) and arg_spec.get("type", "number") == "number":
                pair = _pair([arg_spec.get("min"), arg_spec.get("max")])
                if pair is not None:
                    found[f"{name}.{arg}"] = pair
    return found


def _requirements_text(spec: dict[str, Any]) -> str:
    lines = []
    for item in spec.get("require") or []:
        if isinstance(item, dict):
            message = item.get("message")
            lines.append(f"{item['condition']} because {message}" if message else str(item["condition"]))
        else:
            lines.append(str(item))
    return "; ".join(lines) or "none"


def _runs_text(spec: dict[str, Any]) -> str:
    runs = spec.get("max_runs")
    if isinstance(runs, dict) and "count" in runs and "per" in runs:
        return f"{runs['count']} per {runs['per']}"
    return "none"


def _interlocks_text(draft: dict[str, Any]) -> str:
    lines = []
    for item in draft.get("interlocks") or []:
        if isinstance(item, dict) and "require" in item:
            line = f"if {item.get('if') or 'true'} require {item['require']}"
            lines.append(f"{line} because {item['message']}" if item.get("message") else line)
    return "; ".join(lines) or "none"


def _safe_action(draft: dict[str, Any]) -> str:
    actions = draft.get("actions") or {}
    safe = draft.get("safe_state")
    for step in safe if isinstance(safe, list) else []:
        if isinstance(step, dict) and step.get("action") in actions:
            return str(step["action"])
    for name in _SAFE_ACTION_NAMES:
        if name in actions and not (actions[name] or {}).get("args"):
            return name
    return "none"


def hazard_of(draft: dict[str, Any]) -> str:
    hazard = draft.get("hazard")
    return hazard if hazard in HAZARDS else "medium"


def _channel_questions(
    name: str, spec: dict[str, Any], safe: dict[str, Any], hazard: str, source: str, bounds: dict[str, Any]
) -> list[Question]:
    asked: list[Question] = []
    kind = spec.get("type", "number")
    safe_value: Any = None
    if kind == "number":
        unit = spec.get("unit") or "dimensionless"
        if unit == "dimensionless":
            asked.append(
                Question(
                    f"{name}.unit",
                    f"{name}, its unit, such as percent, degC, V or rpm.",
                    unit,
                    "The draft gives no unit. Limits and rates use this unit.",
                    name,
                    "unit",
                    kind="unit",
                )
            )
        low, high = spec.get("min"), spec.get("max")
        reported = bounds.get(name)
        unit_words = f"in {unit}" if unit != "dimensionless" else "a plain number"
        for field, value, words in (("min", low, "least"), ("max", high, "most")):
            asked.append(
                Question(
                    f"{name}.{field}",
                    f"{name}, {unit_words}. The {words} an agent may set.",
                    value,
                    source if value is not None else f"Nothing in the sources gives a {field}imum.",
                    name,
                    field,
                    unit,
                    "number",
                    reported,
                )
            )
        rate = spec.get("max_change_per_s")
        if rate is None and isinstance(low, int | float) and isinstance(high, int | float) and high > low:
            rate = round((high - low) / 10, 6)
            rate_reason = "A slow default. A tenth of the range per second leaves time to stop."
        else:
            rate_reason = source if rate is not None else "Answer none if the value may jump."
        asked.append(
            Question(
                f"{name}.max_change_per_s",
                f"{name}, {unit_words} per second. The most {name} may change in one second, or none.",
                rate,
                rate_reason,
                name,
                "max_change_per_s",
                unit,
                "rate",
            )
        )
        asked.append(
            Question(
                f"{name}.safe",
                f"{name}, {unit_words}. The value OpenHAL sets when everything stops.",
                safe.get(name, low),
                "Off or lowest is the usual safe value. Check that the value really is safe for this device.",
                name,
                "safe",
                unit,
                "number",
                reported,
            )
        )
    elif kind == "bool":
        safe_value = safe.get(name, False)
        asked.append(
            Question(
                f"{name}.safe",
                f"{name}, true or false. The value OpenHAL sets when everything stops.",
                safe_value,
                "Off is the usual safe value. Check that the value really is safe for this device.",
                name,
                "safe",
                kind="bool",
            )
        )
    elif kind == "enum":
        values = tuple(str(value) for value in spec.get("values") or [])
        safe_value = safe.get(name, values[0] if values else None)
        asked.append(
            Question(
                f"{name}.safe",
                f"{name}, one of {', '.join(values)}. The value OpenHAL sets when everything stops.",
                safe_value,
                "Check that the value really is safe for this device.",
                name,
                "safe",
                kind="enum",
                choices=values,
            )
        )
    asked.append(
        Question(
            f"{name}.confirm",
            f"{name}. Whether a person approves each change, none, confirm or confirm-each-time.",
            spec.get("confirm", _DEFAULT_TIER[hazard]),
            f"{_TIER_REASON} The usual choice for a {hazard} hazard device.",
            name,
            "confirm",
            kind="tier",
            choices=TIERS,
        )
    )
    return asked


def _action_questions(name: str, spec: dict[str, Any], source: str, bounds: dict[str, Any]) -> list[Question]:
    asked: list[Question] = []
    for arg, arg_spec in (spec.get("args") or {}).items():
        if arg_spec.get("type", "number") != "number":
            continue
        unit = arg_spec.get("unit") or "dimensionless"
        for field, words in (("min", "least"), ("max", "most")):
            value = arg_spec.get(field)
            asked.append(
                Question(
                    f"{name}.{arg}.{field}",
                    f"{arg} of {name}, in {unit}. The {words} an agent may send.",
                    value,
                    source if value is not None else "Nothing in the sources gives one.",
                    name,
                    f"args.{arg}.{field}",
                    unit,
                    "number",
                    bounds.get(f"{name}.{arg}"),
                )
            )
    asked.append(
        Question(
            f"{name}.require",
            f"{name}. What must hold before {name} runs, one condition per line, or none.",
            _requirements_text(spec),
            "Write each as a condition, or a condition then because and the reason, for example tank == ok "
            "because pump can't run while tank is empty.",
            name,
            "require",
            kind="require",
        )
    )
    asked.append(
        Question(
            f"{name}.max_runs",
            f"{name}. How often {name} may run, such as 3 per 1 h, or none.",
            _runs_text(spec),
            "A run limit caps how often an agent or a routine can repeat the action, even when every run is allowed.",
            name,
            "max_runs",
            kind="runs",
        )
    )
    asked.append(
        Question(
            f"{name}.confirm",
            f"{name}. Whether a person approves each run, none, confirm or confirm-each-time.",
            spec.get("confirm", "confirm"),
            f"{_TIER_REASON} Actions often do more than one thing, so confirm is the usual choice.",
            name,
            "confirm",
            kind="tier",
            choices=TIERS,
        )
    )
    return asked


def targets(draft: dict[str, Any], *, every: bool = False) -> set[str] | None:
    """The `write:<name>` and `action:<name>` targets the interview asks about, the high risk ones.

    None means every target. A draft gets every question when `every` is set, as the driver writer
    and the Inspector's review do for a person who chose to review a draft, when it doesn't load yet,
    so its levels can't be told, or when its ranges came from a manual, a sketch, an agent or a
    hand-written file rather than from the device or the library.
    """
    if every or _source(draft) not in RANGE_SOURCES:
        return None
    try:
        file = from_data(draft)
    except DeviceFileError:
        return None
    return {target for target, found in risk.assess(file).items() if found.level == "high"}


def questions(draft: dict[str, Any], *, every: bool = False) -> list[Question]:
    """Every question the draft needs answered, in a stable order. None when nothing is high risk."""
    high = targets(draft, every=every)
    if high is not None and not high:
        return []
    hazard = hazard_of(draft)
    source = _source_reason(draft)
    bounds = device_limits(draft)
    asked = [
        Question(
            "device.hazard",
            "The device's hazard class, low, medium or high.",
            hazard,
            "High means the device can burn, cut, shock or move with force. Medium means the device can damage "
            "itself or its work. Low means the worst case is a nuisance.",
            field="hazard",
            kind="hazard",
            choices=HAZARDS,
        )
    ]
    safe = _safe_values(draft)
    for name, spec in (draft.get("write") or {}).items():
        if high is None or f"write:{name}" in high:
            asked.extend(_channel_questions(name, spec, safe, hazard, source, bounds))
    for name, spec in (draft.get("actions") or {}).items():
        if high is None or f"action:{name}" in high:
            asked.extend(_action_questions(name, spec, source, bounds))
    if draft.get("actions"):
        asked.append(
            Question(
                "device.safe_action",
                "The action OpenHAL runs when everything stops, or none.",
                _safe_action(draft),
                "OpenHAL runs the action after the safe values. Pick one that takes no arguments, such as stop.",
                field="safe_state",
                kind="safe_action",
                choices=tuple(draft.get("actions") or {}),
            )
        )
    asked.append(
        Question(
            "device.interlocks",
            "Interlocks, one per line as if <condition> require <condition>, or none.",
            _interlocks_text(draft),
            "An interlock blocks a change unless a condition holds, for example "
            "if brightness > 60 % require current_draw < 2 A.",
            field="interlocks",
            kind="interlocks",
        )
    )
    return asked


def _tidy(value: float) -> float | int:
    """A whole number as an int, so a saved file reads max: 60 and not max: 60.0."""
    return int(value) if float(value).is_integer() else value


def _number(text: Any, unit: str, question: str) -> float:
    answer = str(text).strip()
    if unit != "dimensionless":
        answer = re.sub(r"\s*dimensionless$", "", answer)
    try:
        return convert(parse_quantity(answer, default_unit=unit), unit)
    except UnitError as exc:
        raise AnswerError(f"{question}. {exc}") from exc


def _rate(text: Any, unit: str, question: str) -> float | None:
    answer = str(text).strip()
    if answer.lower() in (*_NONE, "no limit"):
        return None
    try:
        if _BARE_NUMBER.match(answer):
            value = float(answer)
        elif "/" in answer or " per " in answer:
            value = convert_rate(parse_quantity(answer.replace("%/s", "percent / second")), unit)
        else:
            amount = parse_quantity(answer, default_unit=unit)
            value = convert_rate(Quantity(amount.magnitude, f"({amount.units}) / second"), unit)
    except UnitError as exc:
        raise AnswerError(f"{question}. {exc}") from exc
    if not math.isfinite(value) or value <= 0:
        raise AnswerError(f"{question} must be more than zero, or none.")
    return value


def _requirements(text: Any, question: str) -> list[Any]:
    answer = str(text).strip()
    if answer.lower() in _NONE:
        return []
    found: list[Any] = []
    for line in re.split(r"[\n;]+", answer):
        if not line.strip():
            continue
        match = _REQUIREMENT.match(line)
        if match is None:
            raise AnswerError(f"{question}. Write each as <condition> or <condition> because <reason>.")
        message = match.group("message")
        condition = match.group("condition")
        found.append({"condition": condition, "message": message} if message else condition)
    return found


def _runs(text: Any, question: str) -> dict[str, Any] | None:
    answer = str(text).strip()
    if answer.lower() in (*_NONE, "no limit"):
        return None
    match = _RUNS.match(answer)
    if match is None:
        raise AnswerError(f"{question}. Answer like 3 per 1 h, or none.")
    return {"count": int(match.group("count")), "per": match.group("per")}


def _interlocks(text: Any) -> list[dict[str, Any]]:
    answer = str(text).strip()
    if answer.lower() in _NONE:
        return []
    found = []
    for line in re.split(r"[\n;]+", answer):
        if not line.strip():
            continue
        match = _INTERLOCK.match(line)
        if match is None:
            raise AnswerError(f"device.interlocks. Write each as if <condition> require <condition>, not {line!r}.")
        entry = {"if": match.group("condition"), "require": match.group("require")}
        if match.group("message"):
            entry["message"] = match.group("message")
        found.append(entry)
    return found


def _bool(text: Any, question: str) -> bool:
    if isinstance(text, bool):
        return text
    lowered = str(text).strip().lower()
    if lowered in ("true", "on", "yes", "1", "open"):
        return True
    if lowered in ("false", "off", "no", "0", "closed"):
        return False
    raise AnswerError(f"{question}. Answer true or false.")


def _within(question: Question, value: float) -> None:
    if question.range is None:
        return
    low, high = question.range
    unit = question.unit
    span = f"from {shown(low, unit)} to {shown(high, unit)}"
    if value > high + abs(high) * 1e-12:
        raise AnswerError(
            f"{shown(value, unit)} is above {shown(high, unit)}, the most the device reports. Answer a value {span}."
        )
    if value < low - abs(low) * 1e-12:
        raise AnswerError(
            f"{shown(value, unit)} is below {shown(low, unit)}, the least the device reports. Answer a value {span}."
        )


def _unit_of(question: Question, answers: dict[str, Any]) -> str:
    given = answers.get(f"{question.channel}.unit")
    if given is not None and str(given).strip():
        try:
            return normalize_unit(str(given).strip())
        except UnitError:
            return question.unit or "dimensionless"
    return question.unit or "dimensionless"


def problem(question: Question, answer: Any, answers: dict[str, Any] | None = None) -> str | None:
    """Why an answer can't stand, in one sentence, or None when it can.

    `answers` holds the answers given so far, so a max below its min or a safe value outside both is
    caught as soon as the person types it.
    """
    try:
        check(question, answer, answers or {})
    except AnswerError as exc:
        return str(exc)
    return None


def check(question: Question, answer: Any, answers: dict[str, Any]) -> None:
    """Raise AnswerError when an answer can't stand. The CLI, the hub and `apply` all use this check."""
    text = str(answer).strip()
    if not text:
        raise AnswerError(f"{question.id} needs an answer.")
    lowered = text.lower()
    if question.kind == "hazard" and lowered not in HAZARDS:
        raise AnswerError("device.hazard. Answer low, medium or high.")
    if question.kind == "tier" and lowered not in TIERS:
        raise AnswerError(f"{question.id}. Answer none, confirm or confirm-each-time.")
    if question.kind == "unit":
        try:
            normalize_unit(text)
        except UnitError as exc:
            raise AnswerError(f"{question.id}. {exc}") from exc
    if question.kind == "bool":
        _bool(text, question.id)
    if question.kind == "enum" and text not in question.choices:
        raise AnswerError(f"{question.id} must be one of {', '.join(question.choices)}.")
    if question.kind == "require":
        _requirements(text, question.id)
    if question.kind == "runs":
        _runs(text, question.id)
    if question.kind == "interlocks":
        _interlocks(text)
    if question.kind == "safe_action" and lowered not in _NONE and text not in question.choices:
        raise AnswerError(f"device.safe_action. {text} isn't an action of this device.")
    if question.kind == "rate":
        _rate(text, _unit_of(question, answers), question.id)
    if question.kind == "number":
        _check_number(question, text, answers)


def _check_number(question: Question, text: str, answers: dict[str, Any]) -> None:
    unit = _unit_of(question, answers)
    value = _number(text, unit, question.id)
    _within(question, value)
    base = question.id.rsplit(".", 1)[0]

    def given(field: str) -> float | None:
        other = answers.get(f"{base}.{field}")
        if other is None or not str(other).strip():
            return None
        try:
            return _number(other, unit, f"{base}.{field}")
        except AnswerError:
            return None

    low, high = given("min"), given("max")
    if question.field == "max" and low is not None and value < low:
        raise AnswerError(f"{base}.min is above {base}.max. The max must be at least {shown(low, unit)}.")
    if question.field == "min" and high is not None and value > high:
        raise AnswerError(f"{base}.min is above {base}.max. The min must be at most {shown(high, unit)}.")
    if question.field == "safe" and low is not None and high is not None and not low <= value <= high:
        raise AnswerError(
            f"{base}.safe must be between its min and max, from {shown(low, unit)} to {shown(high, unit)}."
        )


def _apply_channels(data: dict[str, Any], answers: dict[str, Any], asked: set[str]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for name, spec in (data.get("write") or {}).items():
        if f"{name}.confirm" not in asked:
            continue
        spec.pop("suggested", None)
        spec.pop("confirmed", None)
        kind = spec.get("type", "number")
        if kind == "number":
            unit_answer = answers.get(f"{name}.unit")
            if unit_answer is not None:
                spec["unit"] = normalize_unit(str(unit_answer).strip())
            unit = spec.get("unit") or "dimensionless"
            spec["min"] = _tidy(_number(answers[f"{name}.min"], unit, f"{name}.min"))
            spec["max"] = _tidy(_number(answers[f"{name}.max"], unit, f"{name}.max"))
            rate = _rate(answers[f"{name}.max_change_per_s"], unit, f"{name}.max_change_per_s")
            if rate is None:
                spec.pop("max_change_per_s", None)
            else:
                spec["max_change_per_s"] = _tidy(rate)
            safe[name] = _tidy(_number(answers[f"{name}.safe"], unit, f"{name}.safe"))
        elif kind == "bool":
            safe[name] = _bool(answers[f"{name}.safe"], f"{name}.safe")
        elif kind == "enum":
            safe[name] = str(answers[f"{name}.safe"]).strip()
        spec["confirm"] = str(answers[f"{name}.confirm"]).strip().lower()
    return safe


def _apply_actions(data: dict[str, Any], answers: dict[str, Any], asked: set[str]) -> None:
    for name, spec in (data.get("actions") or {}).items():
        if f"{name}.confirm" not in asked:
            continue
        spec.pop("suggested", None)
        spec.pop("confirmed", None)
        for arg, arg_spec in (spec.get("args") or {}).items():
            arg_spec.pop("suggested", None)
            if arg_spec.get("type", "number") != "number":
                continue
            for field in ("min", "max"):
                arg_spec[field] = _tidy(
                    _number(
                        answers[f"{name}.{arg}.{field}"],
                        arg_spec.get("unit") or "dimensionless",
                        f"{name}.{arg}.{field}",
                    )
                )
            if arg_spec["min"] > arg_spec["max"]:
                raise AnswerError(f"{name}.{arg}.min is above {name}.{arg}.max.")
        spec["confirm"] = str(answers[f"{name}.confirm"]).strip().lower()
        requirements = _requirements(answers[f"{name}.require"], f"{name}.require")
        if requirements:
            spec["require"] = requirements
        else:
            spec.pop("require", None)
        runs = _runs(answers[f"{name}.max_runs"], f"{name}.max_runs")
        if runs is None:
            spec.pop("max_runs", None)
        else:
            spec["max_runs"] = runs


def _apply_safe_state(data: dict[str, Any], safe: dict[str, Any], answers: dict[str, Any], asked: set[str]) -> None:
    safe = {**_safe_values(data), **safe}
    existing = data.get("safe_state")
    action_steps = [step for step in existing or [] if isinstance(step, dict) and "action" in step]
    if "device.safe_action" in asked:
        chosen = str(answers["device.safe_action"]).strip()
        actions = data.get("actions") or {}
        if chosen.lower() in _NONE:
            action_steps = []
        else:
            kept = [step for step in action_steps if step.get("action") == chosen]
            if not kept and (actions[chosen] or {}).get("args"):
                raise AnswerError(f"device.safe_action. {chosen} takes arguments. Name one that takes none.")
            action_steps = kept or [{"action": chosen}]
    if safe or action_steps:
        data["safe_state"] = [*([safe] if safe else []), *action_steps] if action_steps else safe
    elif "device.safe_action" in asked:
        data.pop("safe_state", None)


def apply(
    draft: dict[str, Any],
    answers: dict[str, Any],
    *,
    by: str,
    today: dt.date | None = None,
    every: bool = False,
) -> dict[str, Any]:
    """Apply a complete set of answers to a copy of the draft and confirm it. Raises AnswerError.

    A draft with no high risk target has no questions, so it comes back as it was, unconfirmed.
    """
    ordered = questions(draft, every=every)
    if not ordered and not answers:
        return copy.deepcopy(draft)
    asked = {question.id: question for question in ordered}
    missing = [question_id for question_id in asked if str(answers.get(question_id, "")).strip() == ""]
    if missing:
        raise AnswerError(f"These questions still need an answer. {', '.join(missing)}")
    unknown = sorted(set(answers) - set(asked))
    if unknown:
        raise AnswerError(f"There are no questions {', '.join(unknown)}.")
    for question in ordered:
        check(question, answers[question.id], answers)

    bounds = device_limits(draft)
    data = copy.deepcopy(draft)
    data.pop("confirmed", None)
    data["hazard"] = str(answers["device.hazard"]).strip().lower()
    safe = _apply_channels(data, answers, set(asked))
    _apply_actions(data, answers, set(asked))
    _apply_safe_state(data, safe, answers, set(asked))

    interlocks_text = str(answers["device.interlocks"]).strip()
    if interlocks_text != asked["device.interlocks"].suggested:
        found = _interlocks(interlocks_text)
        if found:
            data["interlocks"] = found
        else:
            data.pop("interlocks", None)
    if bounds:
        data[DEVICE_LIMITS] = {key: [_tidy(low), _tidy(high)] for key, (low, high) in bounds.items()}

    try:
        unconfirmed_file = from_data(data)
    except DeviceFileError as exc:
        raise AnswerError("The answers make an invalid device file. " + " ".join(exc.problems)) from exc
    data["confirmed"] = {
        "by": by[:80],
        "at": (today or dt.date.today()).isoformat(),
        "sha256": unconfirmed_file.limits_sha256(),
    }
    try:
        confirmed = from_data(data)
    except DeviceFileError as exc:
        raise AnswerError("The confirmed file is invalid. " + " ".join(exc.problems)) from exc
    answered = {f"write.{name}" for name in data.get("write") or {} if f"{name}.confirm" in asked}
    answered |= {f"actions.{name}" for name in data.get("actions") or {} if f"{name}.confirm" in asked}
    remaining = [item for item in confirmed.unconfirmed() if item in answered or item.startswith("file ")]
    if remaining:
        raise AnswerError(f"Still unconfirmed after the interview. {', '.join(remaining)}")
    return data
