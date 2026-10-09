"""Checks for the marking rules.

Each test corresponds to a case where an exam board's published rules and a
naive three-number scheme diverge.  All of these were real defects before the
rules were split out of scoring.
"""
from __future__ import annotations

import pytest

from omr_mcq import MarkingScheme
from omr_mcq.marking import apply_scheme

NEET = MarkingScheme(correct=4, wrong=-1, blank=0, ambiguous_policy="wrong")


def q(num: int, marked=None, status="ok", **extra) -> dict:
    return {"q": num, "subject": "Physics", "marked": marked,
            "status": status, **extra}


# --- Multiple marks ---------------------------------------------------------

def test_multiple_mark_is_penalised_not_free():
    """NEET and JEE treat a double mark as an incorrect response.

    Scoring it as blank hands back a mark for over-marking, which a student
    could exploit by shading two bubbles on every uncertain question.
    """
    sheet = apply_scheme([q(1, None, "multiple")], {1: "A"}, NEET)
    assert sheet.outcomes[0].status == "invalid"
    assert sheet.outcomes[0].marks == -1
    assert sheet.invalid == 1


@pytest.mark.parametrize("policy,marks", [
    ("wrong", -1.0), ("blank", 0.0), ("zero", 0.0), ("review", 0.0),
])
def test_ambiguous_policy_is_configurable(policy: str, marks: float):
    scheme = MarkingScheme(correct=4, wrong=-1, blank=0,
                           ambiguous_policy=policy, floor_at_zero=False)
    sheet = apply_scheme([q(1, None, "multiple")], {1: "A"}, scheme)
    assert sheet.outcomes[0].marks == marks


def test_unknown_policy_is_rejected_at_construction():
    """A typo in a stored scheme must fail loudly, not score silently wrong."""
    with pytest.raises(ValueError):
        MarkingScheme(ambiguous_policy="ignore")


def test_double_marks_are_counted_apart_from_blanks():
    """Ten double-marks must not look identical to ten empty questions."""
    key = {i: "A" for i in range(1, 11)}
    doubles = apply_scheme([q(i, None, "multiple") for i in range(1, 11)], key, NEET)
    blanks = apply_scheme([q(i, None, "none") for i in range(1, 11)], key, NEET)
    assert (doubles.invalid, doubles.unattempted) == (10, 0)
    assert (blanks.unattempted, blanks.invalid) == (10, 0)


# --- Answer key coverage ----------------------------------------------------

def test_question_outside_the_key_is_unscored_not_wrong():
    """A half-entered answer key must not deduct marks."""
    sheet = apply_scheme([q(i, "A") for i in range(1, 6)], {1: "A", 2: "A"}, NEET)
    assert sheet.correct == 2
    assert sheet.wrong == 0
    assert sheet.unscored == 3
    # The ceiling must shrink to what was actually scorable, or the student is
    # measured against marks they had no way to earn.
    assert sheet.max_score == 8


# --- Totals -----------------------------------------------------------------

def test_total_is_floored_at_zero_by_default():
    all_wrong = [q(i, "B") for i in range(1, 11)]
    key = {i: "A" for i in range(1, 11)}
    assert apply_scheme(all_wrong, key, NEET).total == 0
    unfloored = MarkingScheme(correct=4, wrong=-1, blank=0,
                              ambiguous_policy="wrong", floor_at_zero=False)
    assert apply_scheme(all_wrong, key, unfloored).total == -10


def test_fractional_marks_do_not_drift():
    """Totals get read aloud to students; binary float drift is not acceptable."""
    scheme = MarkingScheme(correct=0.1, wrong=-0.05, blank=0,
                           ambiguous_policy="zero")
    sheet = apply_scheme([q(1, "A"), q(2, "B")], {1: "A", 2: "A"}, scheme)
    assert sheet.total == 0.05
    assert sheet.subject_scores["Physics"] == 0.05


def test_subject_totals_sum_to_the_overall_total():
    per_q = ([q(i, "A") for i in range(1, 6)]
             + [{"q": i, "subject": "Chemistry", "marked": "B", "status": "ok"}
                for i in range(6, 11)])
    scheme = MarkingScheme(correct=4, wrong=-1, blank=0,
                           ambiguous_policy="wrong", floor_at_zero=False)
    sheet = apply_scheme(per_q, {i: "A" for i in range(1, 11)}, scheme)
    assert sum(sheet.subject_scores.values()) == sheet.total


# --- Low-confidence reads ---------------------------------------------------

def test_low_confidence_read_is_scored_but_flagged():
    """A shaky read still earns its marks, but must be visible to a reviewer.

    Withholding the marks would penalise the student for the camera; hiding
    the doubt would let a disputed mark pass unnoticed.
    """
    sheet = apply_scheme([q(1, "A", needs_review=True)], {1: "A"}, NEET)
    assert sheet.outcomes[0].status == "correct"
    assert sheet.outcomes[0].marks == 4
    assert sheet.review_questions == [1]


def test_scheme_loads_from_a_legacy_three_number_dict():
    """Schemes stored before the newer fields existed must still score."""
    scheme = MarkingScheme.from_dict({"correct": 4, "wrong": -1, "blank": 0})
    sheet = apply_scheme([q(1, "A"), q(2, "B")], {1: "A", 2: "A"}, scheme)
    assert sheet.total == 3


def test_scheme_ignores_unknown_keys():
    scheme = MarkingScheme.from_dict({"correct": 2, "nonsense": True})
    assert scheme.correct == 2
