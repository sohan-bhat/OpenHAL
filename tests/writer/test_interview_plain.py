"""The interview in plain words, with the device's own range as a hard edge for every answer."""

from __future__ import annotations

from typing import Any

import pytest

from openhal.spec.loader import from_data
from openhal.writer import interview


def lamp(source: str = "self-described", **extra: Any) -> dict[str, Any]:
    return {
        "device": "Bare board",
        "connect": {"openhal-firmware": "sim:bare"},
        "write": {"brightness": {"unit": "percent", "min": 0, "max": 100, "suggested": True, "risk": "high"}},
        "provenance": {"source": source},
        **extra,
    }


def asked(draft: dict[str, Any]) -> dict[str, interview.Question]:
    return {question.id: question for question in interview.questions(draft)}


def suggested(draft: dict[str, Any], **changes: str) -> dict[str, str]:
    answers = {question.id: interview.suggestion_text(question) or "none" for question in interview.questions(draft)}
    answers.update(changes)
    return answers


def test_each_question_is_one_plain_sentence_with_the_channel_and_its_unit() -> None:
    questions = asked(lamp())
    assert questions["brightness.max"].prompt == "brightness, in percent. The most an agent may set."
    assert interview.suggestion_text(questions["brightness.max"]) == "100 %"
    assert questions["brightness.min"].prompt == "brightness, in percent. The least an agent may set."
    for question in questions.values():
        for text in (question.prompt, question.reason):
            assert not any(mark in text for mark in (":", chr(0x2014), chr(0x2013), "!")), text


def test_a_value_past_what_the_device_reports_is_refused_with_the_reason() -> None:
    questions = asked(lamp())
    reason = interview.problem(questions["brightness.max"], "120 %")
    assert reason == "120 % is above 100 %, the most the device reports. Answer a value from 0 % to 100 %."
    assert interview.problem(questions["brightness.min"], "-5") is not None
    assert interview.problem(questions["brightness.max"], "80") is None
    with pytest.raises(interview.AnswerError, match="the most the device reports"):
        interview.apply(lamp(), suggested(lamp(), **{"brightness.max": "120 %"}), by="owner")


def test_a_library_file_has_no_device_range_to_hold_to() -> None:
    questions = asked(lamp(source="library"))
    assert questions["brightness.max"].range is None
    assert interview.problem(questions["brightness.max"], "120 %") is None


def test_a_confirmed_limit_is_the_person_s_and_never_taken_as_the_device_range() -> None:
    confirmed = lamp()
    confirmed["write"]["brightness"] = {"unit": "percent", "min": 0, "max": 60}
    assert interview.device_limits(confirmed) == {}
    assert interview.device_limits(lamp()) == {"brightness": (0.0, 100.0)}


def test_answers_are_checked_against_each_other_as_they_come() -> None:
    questions = asked(lamp())
    answers = {"brightness.min": "50 %"}
    assert "brightness.min is above brightness.max" in (
        interview.problem(questions["brightness.max"], "10", answers) or ""
    )
    answers["brightness.max"] = "80 %"
    assert "between its min and max" in (interview.problem(questions["brightness.safe"], "0 %", answers) or "")
    assert interview.problem(questions["brightness.max_change_per_s"], "20 %") is None
    assert interview.problem(questions["brightness.max_change_per_s"], "0") is not None
    assert interview.problem(questions["brightness.confirm"], "sometimes") is not None
    assert interview.problem(questions["device.hazard"], "") == "device.hazard needs an answer."


def test_the_confirmed_file_keeps_the_device_range_for_later_changes() -> None:
    confirmed = interview.apply(lamp(), suggested(lamp(), **{"brightness.max": "80 %"}), by="owner")
    assert confirmed[interview.DEVICE_LIMITS] == {"brightness": [0.0, 100.0]}
    assert confirmed["write"]["brightness"]["max"] == 80
    assert confirmed["write"]["brightness"]["max_change_per_s"] == 10
    file = from_data(confirmed)
    assert file.writable
    again = asked(confirmed)
    assert again["brightness.max"].range == (0.0, 100.0)
    assert interview.problem(again["brightness.max"], "100 %") is None


def test_interlocks_keep_their_reason_and_none_clears_them() -> None:
    draft = lamp(
        interlocks=[{"if": "brightness > 50 %", "require": "brightness < 90 %", "message": "keeps the lamp cool"}]
    )
    question = asked(draft)["device.interlocks"]
    assert question.suggested == "if brightness > 50 % require brightness < 90 % because keeps the lamp cool"
    kept = interview.apply(draft, suggested(draft), by="owner")
    assert kept["interlocks"] == draft["interlocks"]
    cleared = interview.apply(draft, suggested(draft, **{"device.interlocks": "none"}), by="owner")
    assert "interlocks" not in cleared
    typed = interview.apply(
        draft,
        suggested(draft, **{"device.interlocks": "if brightness > 10 % require brightness < 60 % because hot"}),
        by="me",
    )
    assert typed["interlocks"] == [{"if": "brightness > 10 %", "require": "brightness < 60 %", "message": "hot"}]


def test_a_low_or_medium_draft_has_nothing_to_ask() -> None:
    draft = lamp()
    draft["write"]["brightness"].pop("risk")
    assert interview.questions(draft) == []
    assert interview.apply(draft, {}, by="owner") == draft
    with pytest.raises(interview.AnswerError, match="no questions"):
        interview.apply(draft, {"device.hazard": "low"}, by="owner")


def test_only_high_risk_entries_are_asked_and_the_rest_stay_as_they_were() -> None:
    draft = lamp(safe_state={"brightness": 0, "heater": 0})
    draft["write"]["brightness"].pop("risk")
    draft["write"]["heater"] = {"unit": "percent", "min": 0, "max": 100, "suggested": True}
    questions = asked(draft)
    assert "heater.max" in questions
    assert not [name for name in questions if name.startswith("brightness.")]
    given = suggested(draft, **{"heater.max": "40 %", "device.hazard": "medium"})
    confirmed = interview.apply(draft, given, by="owner")
    assert confirmed["write"]["brightness"] == draft["write"]["brightness"]
    assert confirmed["write"]["heater"]["max"] == 40
    assert confirmed["safe_state"] == {"brightness": 0, "heater": 0}
    file = from_data(confirmed)
    assert file.writable
    assert file.write["brightness"].suggested


@pytest.mark.parametrize("source", ["manual", "sketch", "hand-written"])
def test_a_draft_with_no_range_from_the_device_gets_every_question(source: str) -> None:
    draft = lamp(source)
    draft["write"]["brightness"].pop("risk")
    assert "brightness.max" in asked(draft), "a range a manual or an agent wrote needs a person's check"
    library = lamp("library")
    library["write"]["brightness"].pop("risk")
    assert interview.questions(library) == []


def test_a_draft_that_doesnt_load_yet_gets_every_question() -> None:
    draft = lamp()
    draft["write"]["brightness"] = {"unit": "percent", "suggested": True}
    assert "brightness.max" in asked(draft)


def test_a_draft_cant_carry_a_person_lowering_a_level() -> None:
    from openhal.writer.engine import force_suggested

    draft = lamp()
    draft["write"]["brightness"]["risk"] = {"level": "low", "by": "owner", "at": "2026-11-03"}
    assert force_suggested(draft)["write"]["brightness"]["risk"] == "low"
