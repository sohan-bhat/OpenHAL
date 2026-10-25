"""The interview's action questions: requirements, run limits and the action that makes a device safe."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from openhal.spec.loader import from_data, load
from openhal.writer import interview, sketch

SKETCH = Path(__file__).resolve().parents[2] / "examples" / "plant-waterer" / "plant-waterer.ino"
MOCK = Path(__file__).resolve().parents[2] / "examples" / "plant-waterer" / "mock" / "plant-waterer.hal.yaml"


def waterer() -> dict[str, Any]:
    draft = sketch.draft(sketch.parse(SKETCH.read_text(encoding="utf-8")))
    return {**draft, "device": "Plant waterer", "id": "plant-waterer", "connect": {"mock": "waterer"}}


def answers(**changes: str) -> dict[str, str]:
    given = {question.id: str(question.suggested) for question in interview.questions(waterer())}
    given.update({"device.hazard": "low", "water.confirm": "none", "stop.confirm": "none"})
    given.update(changes)
    return given


def test_actions_are_asked_for_requirements_runs_and_a_safe_action() -> None:
    asked = {question.id: question for question in interview.questions(waterer())}
    assert asked["water.require"].suggested == "none"
    assert asked["water.max_runs"].suggested == "none"
    assert asked["device.safe_action"].suggested == "stop"
    assert "tank == ok" in asked["water.require"].reason


def test_the_interview_gives_the_plant_waterer_its_hand_written_limits() -> None:
    confirmed = interview.apply(
        waterer(),
        answers(
            **{
                "water.require": "tank == ok because pump can't run while tank is empty",
                "water.max_runs": "3 per 1 h",
            }
        ),
        by="sohan",
    )
    file = from_data(confirmed)
    assert file.writable
    water = file.actions["water"]
    assert water.conditions == [("tank == ok", "pump can't run while tank is empty")]
    assert water.max_runs is not None
    assert (water.max_runs.count, water.max_runs.per) == (3, 3600.0)
    assert confirmed["safe_state"] == [{"action": "stop"}]
    mock = load(MOCK)
    assert water.conditions == mock.actions["water"].conditions
    assert water.max_runs == mock.actions["water"].max_runs


def test_plain_requirements_and_none_clear_them() -> None:
    draft = waterer()
    draft["actions"]["water"]["require"] = ["tank == ok"]
    draft["actions"]["water"]["max_runs"] = {"count": 2, "per": "10 min"}
    asked = {question.id: question for question in interview.questions(draft)}
    assert asked["water.require"].suggested == "tank == ok"
    assert asked["water.max_runs"].suggested == "2 per 10 min"
    given = {question.id: str(question.suggested) for question in interview.questions(draft)}
    given.update({"device.hazard": "low", "water.require": "none", "water.max_runs": "none"})
    confirmed = interview.apply(draft, given, by="sohan")
    assert "require" not in confirmed["actions"]["water"]
    assert "max_runs" not in confirmed["actions"]["water"]


def test_no_safe_action_leaves_no_safe_state() -> None:
    confirmed = interview.apply(waterer(), answers(**{"device.safe_action": "none"}), by="sohan")
    assert "safe_state" not in confirmed


@pytest.mark.parametrize(
    ("question", "answer", "message"),
    [
        ("water.max_runs", "often", "like 3 per 1 h"),
        ("water.max_runs", "3 per 30 days", "between 1 s and 7 days"),
        ("water.require", "tank ===", "invalid device file"),
        ("device.safe_action", "drain", "isn't an action"),
        ("device.safe_action", "water", "takes arguments"),
    ],
)
def test_bad_action_answers_are_refused(question: str, answer: str, message: str) -> None:
    with pytest.raises(interview.AnswerError, match=message):
        interview.apply(waterer(), answers(**{question: answer}), by="sohan")
