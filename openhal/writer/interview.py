"""The limits interview (driver writer, step 7).

Questions cover every write channel and action: unit, min, max, rate, safe value and confirmation
tier for channels, argument limits, requirements, a run limit and the tier for actions, plus the
device's hazard class, the action that makes the device safe and its interlocks. Each question
carries a conservative suggestion and the reason for the suggestion. The engine checks that a human
principal gave the answers, and the draft gets a `confirmed` entry bound to the hash of its limits
once every question is answered. A draft an agent proposes still goes through every question.
"""

from __future__ import annotations

import copy
import datetime as dt
import re
from dataclasses import dataclass
from typing import Any, Final

from openhal.spec.loader import DeviceFileError, from_data
from openhal.spec.units import UnitError, convert, normalize_unit, parse_quantity

TIERS: Final = ("none", "confirm", "confirm-each-time")
HAZARDS: Final = ("low", "medium", "high")
_DEFAULT_TIER: Final = {"low": "none", "medium": "confirm", "high": "confirm-each-time"}
_INTERLOCK: Final = re.compile(r"^\s*if\s+(?P<condition>.+?)\s+require\s+(?P<require>.+?)\s*$", re.I)
_REQUIREMENT: Final = re.compile(r"^\s*(?P<condition>.+?)(?:\s+because\s+(?P<message>.+?))?\s*$", re.I)
_RUNS: Final = re.compile(r"^\s*(?P<count>\d+)\s*(?:times?\s+)?(?:per|every|in)\s+(?P<per>.+?)\s*$", re.I)
_SAFE_ACTION_NAMES: Final = ("stop", "off", "halt", "abort", "park", "disable", "home")
_NONE: Final = ("none", "no", "")


@dataclass(frozen=True)
class Question:
    id: str
    prompt: str
    suggested: Any
    reason: str
    channel: str | None = None
    field: str | None = None
    unit: str | None = None

    def view(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "channel": self.channel,
            "field": self.field,
            "prompt": self.prompt,
            "suggested": self.suggested,
            "unit": self.unit,
            "reason": self.reason,
        }


class AnswerError(ValueError):
    """An answer could not be applied. The message names the question and what to fix."""


def _safe_values(draft: dict[str, Any]) -> dict[str, Any]:
    safe = draft.get("safe_state")
    if isinstance(safe, dict):
        return dict(safe)
    values: dict[str, Any] = {}
    for step in safe or []:
        if isinstance(step, dict) and "action" not in step:
            values.update(step.get("values", step))
    return values


def _source_reason(draft: dict[str, Any]) -> str:
    source = (draft.get("provenance") or {}).get("source", "hand-written")
    return {
        "self-described": "The board reports this limit itself.",
        "driver-describe": "The driver read this from the device.",
        "sketch": "The sketch's code suggests this value.",
        "manual": "The manual suggests this value.",
    }.get(source, "The draft suggests this value.")


def _requirements_text(spec: dict[str, Any]) -> str:
    lines = []
    for item in spec.get("require") or []:
        if isinstance(item, dict):
            message = item.get("message")
            lines.append(f"{item['condition']} because {message}" if message else str(item["condition"]))
        else:
            lines.append(str(item))
    return "\n".join(lines) or "none"


def _runs_text(spec: dict[str, Any]) -> str:
    runs = spec.get("max_runs")
    if isinstance(runs, dict) and "count" in runs and "per" in runs:
        return f"{runs['count']} per {runs['per']}"
    return "none"


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


def questions(draft: dict[str, Any]) -> list[Question]:
    """Every question the draft needs answered, in a stable order."""
    asked: list[Question] = []
    hazard = hazard_of(draft)
    source = _source_reason(draft)
    asked.append(
        Question(
            "device.hazard",
            "What hazard class is this device? low, medium or high.",
            hazard,
            "High means it can burn, cut, shock or move with force. Medium means it can damage itself or "
            "its work. Low means the worst case is a nuisance.",
            field="hazard",
        )
    )
    safe = _safe_values(draft)
    for name, spec in (draft.get("write") or {}).items():
        kind = spec.get("type", "number")
        if kind == "number":
            unit = spec.get("unit") or "dimensionless"
            if unit == "dimensionless":
                asked.append(
                    Question(
                        f"{name}.unit",
                        f"What unit is {name} in? For example percent, degC, V, rpm or dimensionless.",
                        unit,
                        "The draft could not tell. Limits and rates are written in this unit.",
                        name,
                        "unit",
                    )
                )
            low, high = spec.get("min"), spec.get("max")
            asked.append(
                Question(
                    f"{name}.min",
                    f"What is the lowest safe {name}?",
                    low,
                    source if low is not None else "Nothing in the sources gives a minimum.",
                    name,
                    "min",
                    unit,
                )
            )
            asked.append(
                Question(
                    f"{name}.max",
                    f"What is the highest safe {name}?",
                    high,
                    source if high is not None else "Nothing in the sources gives a maximum.",
                    name,
                    "max",
                    unit,
                )
            )
            rate = spec.get("max_change_per_s")
            if rate is None and isinstance(low, int | float) and isinstance(high, int | float) and high > low:
                rate = round((high - low) / 10, 6)
                rate_reason = "A slow default. A tenth of the range per second leaves time to stop it."
            else:
                rate_reason = source if rate is not None else "Leave it as none if the value may jump."
            asked.append(
                Question(
                    f"{name}.max_change_per_s",
                    f"How fast may {name} change, per second? Answer none for no limit.",
                    rate,
                    rate_reason,
                    name,
                    "max_change_per_s",
                    unit,
                )
            )
            safe_value = safe.get(name, low)
            unit_for_safe: str | None = unit
        elif kind == "bool":
            safe_value = safe.get(name, False)
            unit_for_safe = None
        elif kind == "enum":
            values = spec.get("values") or []
            safe_value = safe.get(name, values[0] if values else None)
            unit_for_safe = None
        else:
            safe_value = None
            unit_for_safe = None
        if kind != "string":
            asked.append(
                Question(
                    f"{name}.safe",
                    f"What value of {name} is safe when OpenHAL stops everything?",
                    safe_value,
                    "Off or lowest is the usual safe value. Check that it really is safe for this device.",
                    name,
                    "safe",
                    unit_for_safe,
                )
            )
        asked.append(
            Question(
                f"{name}.confirm",
                f"Should changes to {name} need a person's approval? none, confirm or confirm-each-time.",
                spec.get("confirm", _DEFAULT_TIER[hazard]),
                f"The usual tier for a {hazard} hazard device. High hazard devices always ask each time.",
                name,
                "confirm",
            )
        )
    for name, spec in (draft.get("actions") or {}).items():
        for arg, arg_spec in (spec.get("args") or {}).items():
            if arg_spec.get("type", "number") != "number":
                continue
            unit = arg_spec.get("unit")
            for field in ("min", "max"):
                asked.append(
                    Question(
                        f"{name}.{arg}.{field}",
                        f"What is the {'lowest' if field == 'min' else 'highest'} safe {arg} for {name}?",
                        arg_spec.get(field),
                        source if arg_spec.get(field) is not None else "Nothing in the sources gives one.",
                        name,
                        f"args.{arg}.{field}",
                        unit,
                    )
                )
        asked.append(
            Question(
                f"{name}.require",
                f"What must hold before {name} runs? One per line as <condition>, or <condition> because "
                "<reason>. Answer none for none.",
                _requirements_text(spec),
                "The hub checks these before the command reaches the device, for example tank == ok because "
                "pump can't run while tank is empty.",
                name,
                "require",
            )
        )
        asked.append(
            Question(
                f"{name}.max_runs",
                f"How often may {name} run? Answer like 3 per 1 h, or none for no limit.",
                _runs_text(spec),
                "A run limit caps how often an agent or a routine can repeat it, even when every run is allowed.",
                name,
                "max_runs",
            )
        )
        asked.append(
            Question(
                f"{name}.confirm",
                f"Should {name} need a person's approval? none, confirm or confirm-each-time.",
                spec.get("confirm", "confirm"),
                "Actions often do more than one thing, so confirm is the default.",
                name,
                "confirm",
            )
        )
    if draft.get("actions"):
        asked.append(
            Question(
                "device.safe_action",
                "Which action makes the device safe when OpenHAL stops everything? Name one, or none.",
                _safe_action(draft),
                "It runs after the safe channel values. Pick one that takes no arguments, such as stop.",
                field="safe_state",
            )
        )
    asked.append(
        Question(
            "device.interlocks",
            "Any interlocks? One per line as: if <condition> require <condition>. Answer none for none.",
            "none",
            "An interlock blocks a change unless a condition holds, for example "
            "if brightness > 60 % require current_draw < 2 A.",
            field="interlocks",
        )
    )
    return asked


def _number(text: Any, unit: str, question: str) -> float:
    try:
        quantity = parse_quantity(text, default_unit=unit)
        return convert(quantity, unit)
    except UnitError as exc:
        raise AnswerError(f"{question}. {exc}") from exc


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


def _bool(text: Any, question: str) -> bool:
    if isinstance(text, bool):
        return text
    lowered = str(text).strip().lower()
    if lowered in ("true", "on", "yes", "1", "open"):
        return True
    if lowered in ("false", "off", "no", "0", "closed"):
        return False
    raise AnswerError(f"{question}. Answer true or false.")


def apply(draft: dict[str, Any], answers: dict[str, Any], *, by: str, today: dt.date | None = None) -> dict[str, Any]:
    """Apply a complete set of answers to a copy of the draft and confirm it. Raises AnswerError."""
    asked = {question.id: question for question in questions(draft)}
    missing = [question_id for question_id in asked if str(answers.get(question_id, "")).strip() == ""]
    if missing:
        raise AnswerError(f"These questions still need an answer. {', '.join(missing)}")
    unknown = sorted(set(answers) - set(asked))
    if unknown:
        raise AnswerError(f"There are no questions {', '.join(unknown)}.")

    data = copy.deepcopy(draft)
    data.pop("confirmed", None)
    hazard = str(answers["device.hazard"]).strip().lower()
    if hazard not in HAZARDS:
        raise AnswerError("device.hazard. Answer low, medium or high.")
    data["hazard"] = hazard

    safe: dict[str, Any] = {}
    for name, spec in (data.get("write") or {}).items():
        spec.pop("suggested", None)
        spec.pop("confirmed", None)
        kind = spec.get("type", "number")
        if kind == "number":
            unit_answer = answers.get(f"{name}.unit")
            if unit_answer is not None:
                try:
                    spec["unit"] = normalize_unit(str(unit_answer).strip())
                except UnitError as exc:
                    raise AnswerError(f"{name}.unit. {exc}") from exc
            unit = spec.get("unit") or "dimensionless"

            def number(question_id: str, unit: str = unit) -> float:
                text = str(answers[question_id]).strip()
                text = re.sub(r"\s*dimensionless$", "", text) if unit != "dimensionless" else text
                return _number(text, unit, question_id)

            spec["min"], spec["max"] = number(f"{name}.min"), number(f"{name}.max")
            if spec["min"] > spec["max"]:
                raise AnswerError(f"{name}.min is above {name}.max.")
            rate = str(answers[f"{name}.max_change_per_s"]).strip().lower()
            if rate in ("none", "no", "no limit"):
                spec.pop("max_change_per_s", None)
            else:
                spec["max_change_per_s"] = number(f"{name}.max_change_per_s")
                if spec["max_change_per_s"] <= 0:
                    raise AnswerError(f"{name}.max_change_per_s must be more than zero, or none.")
            safe[name] = number(f"{name}.safe")
            if not spec["min"] <= safe[name] <= spec["max"]:
                raise AnswerError(f"{name}.safe must be between its min and max.")
        elif kind == "bool":
            safe[name] = _bool(answers[f"{name}.safe"], f"{name}.safe")
        elif kind == "enum":
            value = str(answers[f"{name}.safe"]).strip()
            if value not in (spec.get("values") or []):
                raise AnswerError(f"{name}.safe must be one of {', '.join(spec.get('values') or [])}.")
            safe[name] = value
        tier = str(answers[f"{name}.confirm"]).strip().lower()
        if tier not in TIERS:
            raise AnswerError(f"{name}.confirm. Answer none, confirm or confirm-each-time.")
        spec["confirm"] = tier

    for name, spec in (data.get("actions") or {}).items():
        spec.pop("suggested", None)
        spec.pop("confirmed", None)
        for arg, arg_spec in (spec.get("args") or {}).items():
            arg_spec.pop("suggested", None)
            if arg_spec.get("type", "number") != "number":
                continue
            for field in ("min", "max"):
                arg_spec[field] = _number(
                    answers[f"{name}.{arg}.{field}"], arg_spec.get("unit") or "dimensionless", f"{name}.{arg}.{field}"
                )
        tier = str(answers[f"{name}.confirm"]).strip().lower()
        if tier not in TIERS:
            raise AnswerError(f"{name}.confirm. Answer none, confirm or confirm-each-time.")
        spec["confirm"] = tier
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

    existing = data.get("safe_state")
    action_steps = [step for step in existing or [] if isinstance(step, dict) and "action" in step]
    if "device.safe_action" in asked:
        chosen = str(answers["device.safe_action"]).strip()
        actions = data.get("actions") or {}
        if chosen.lower() in _NONE:
            action_steps = []
        elif chosen not in actions:
            raise AnswerError(f"device.safe_action. {chosen} isn't an action of this device.")
        else:
            kept = [step for step in action_steps if step.get("action") == chosen]
            if not kept and (actions[chosen] or {}).get("args"):
                raise AnswerError(f"device.safe_action. {chosen} takes arguments. Name one that takes none.")
            action_steps = kept or [{"action": chosen}]
    if safe or action_steps:
        data["safe_state"] = [*([safe] if safe else []), *action_steps] if action_steps else safe
    elif "device.safe_action" in asked:
        data.pop("safe_state", None)

    interlocks_text = str(answers["device.interlocks"]).strip()
    if interlocks_text.lower() not in ("none", "no", ""):
        data["interlocks"] = []
        for line in re.split(r"[\n;]+", interlocks_text):
            if not line.strip():
                continue
            match = _INTERLOCK.match(line)
            if match is None:
                raise AnswerError(f"device.interlocks. Write each as if <condition> require <condition>, not {line!r}.")
            data["interlocks"].append({"if": match.group("condition"), "require": match.group("require")})

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
    remaining = confirmed.unconfirmed()
    if remaining:
        raise AnswerError(f"Still unconfirmed after the interview. {', '.join(remaining)}")
    return data
