"""Marking rules: how a read answer becomes marks.

Kept apart from the reader because "what did the student write" and "what is
that worth" are different questions with different owners.  The reader decides
the first from pixels; an exam board decides the second, and its rules change
per exam without the vision code changing at all.

What a scheme has to express
----------------------------
The three numbers a naive scheme carries -- correct, wrong, blank -- cannot
express the rules these exams actually publish:

* **Multiple marks are not blanks.**  NEET and JEE treat a double-marked
  question as an incorrect response and apply the negative mark.  Scoring it
  as blank hands back a mark for over-marking, which is the opposite of the
  intent and is exploitable by a student who shades two bubbles on every
  question they are unsure of.
* **Unreadable is not the same as unanswered.**  A question the reader could
  not resolve is a *measurement* failure, not a student choice.  Scoring it
  either way silently decides a disputed mark by accident; it should be held
  for review under an explicit policy.
* **Negative totals are usually floored.**  Most boards report 0 rather than
  a negative aggregate.
* **A question outside the answer key is not wrong.**  It is unscored.  A
  partially-entered key must not subtract marks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

# How to score a question whose bubbles could not be read confidently
# (LOW_CONFIDENCE / MULTIPLE_MARK / INVALID).
#
#   "wrong"   - treat as an incorrect response (NEET/JEE double-mark rule)
#   "blank"   - treat as unattempted
#   "zero"    - award nothing, but do not deduct either
#   "review"  - award nothing and flag; marks land once a human resolves it
AMBIGUOUS_POLICIES = ("wrong", "blank", "zero", "review")


@dataclass(frozen=True)
class MarkingScheme:
    """One exam's rules, defaulting to the common +4/-1 pattern."""

    correct: float = 4.0
    wrong: float = -1.0
    blank: float = 0.0
    # What a multiple mark is worth.  Defaults to the wrong-answer penalty
    # because that is what NEET and JEE specify; set 0.0 for a board that
    # merely voids the question.
    multiple: float | None = None
    ambiguous_policy: str = "wrong"
    # Report 0 rather than a negative aggregate, per subject and overall.
    floor_at_zero: bool = True
    # Marks are quantised to this step so repeated addition of values like
    # 0.33 cannot drift.  A total gets read aloud to a student and must be
    # reproducible to the last decimal; binary floating point is not.
    quantum: float = 0.01

    def __post_init__(self) -> None:
        if self.ambiguous_policy not in AMBIGUOUS_POLICIES:
            raise ValueError(
                f"ambiguous_policy must be one of {AMBIGUOUS_POLICIES}, "
                f"got {self.ambiguous_policy!r}")

    @classmethod
    def from_dict(cls, raw: dict | None) -> "MarkingScheme":
        """Build from a plain dict, ignoring keys this version does not know.

        Tolerant on purpose: a scheme stored before a field existed must still
        load and score rather than crashing a grading run.
        """
        if not raw:
            return cls()
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in raw.items() if k in known})

    @property
    def multiple_marks(self) -> float:
        return self.wrong if self.multiple is None else self.multiple

    def quantise(self, value: float) -> float:
        """Snap *value* to the scheme's quantum, half-up."""
        if self.quantum <= 0:
            return float(value)
        step = Decimal(str(self.quantum))
        return float((Decimal(str(value)) / step).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP) * step)


# Boards that deduct for a wrong answer also count a double mark as wrong.
NEGATIVE_MARKING = MarkingScheme(correct=4, wrong=-1, blank=0,
                                 ambiguous_policy="wrong")
# Boards without negative marking void an ambiguous question instead.
NO_NEGATIVE_MARKING = MarkingScheme(correct=1, wrong=0, blank=0,
                                    ambiguous_policy="zero")


@dataclass
class QuestionOutcome:
    """What one question was worth, and why."""

    q: int
    subject: str | None
    marked: str | None
    expected: str | None
    status: str      # correct | wrong | unattempted | invalid | unscored
    marks: float
    needs_review: bool = False
    note: str | None = None


_ATTEMPTED = ("correct", "wrong")


@dataclass
class ScoreSheet:
    """Aggregate result of applying a scheme to a whole sheet."""

    outcomes: list[QuestionOutcome] = field(default_factory=list)
    correct: int = 0
    wrong: int = 0
    unattempted: int = 0
    invalid: int = 0
    unscored: int = 0
    subject_scores: dict[str, float] = field(default_factory=dict)
    total: float = 0.0
    max_score: float = 0.0
    review_questions: list[int] = field(default_factory=list)

    @property
    def attempted(self) -> int:
        return sum(1 for o in self.outcomes if o.status in _ATTEMPTED)

    def as_dict(self) -> dict:
        return {
            "correct": self.correct,
            "wrong": self.wrong,
            "unattempted": self.unattempted,
            "invalid": self.invalid,
            "unscored": self.unscored,
            "attempted": self.attempted,
            "subject_scores": self.subject_scores,
            "total": self.total,
            "max": self.max_score,
            "review_questions": self.review_questions,
        }


def apply_scheme(per_question: list, answer_key: dict,
                 scheme: MarkingScheme) -> ScoreSheet:
    """Score every question under *scheme*.

    *per_question* is the reader's output: dicts carrying ``q``, ``subject``,
    ``marked``, ``status`` and, optionally, ``needs_review``.
    """
    sheet = ScoreSheet()

    for pq in per_question:
        q = int(pq["q"])
        subject = pq.get("subject")
        marked = pq.get("marked")
        expected = answer_key.get(q, answer_key.get(str(q)))
        flagged = bool(pq.get("needs_review"))

        status, marks, note = _decide(marked, expected, pq.get("status"),
                                       flagged, scheme)
        marks = scheme.quantise(marks)

        sheet.outcomes.append(QuestionOutcome(
            q=q, subject=subject, marked=marked, expected=expected,
            status=status, marks=marks, needs_review=flagged, note=note))

        if status == "correct":
            sheet.correct += 1
        elif status == "wrong":
            sheet.wrong += 1
        elif status == "invalid":
            sheet.invalid += 1
        elif status == "unscored":
            sheet.unscored += 1
        else:
            sheet.unattempted += 1

        if flagged:
            sheet.review_questions.append(q)

        key = subject or "General"
        sheet.subject_scores[key] = scheme.quantise(
            sheet.subject_scores.get(key, 0.0) + marks)

    # A question with no entry in the answer key cannot be marked either way,
    # so it is excluded from the maximum too -- otherwise a half-entered key
    # reports a ceiling the student had no way to reach.
    scorable = sum(1 for o in sheet.outcomes if o.status != "unscored")
    sheet.max_score = scheme.quantise(scorable * scheme.correct)
    sheet.total = scheme.quantise(sum(o.marks for o in sheet.outcomes))

    if scheme.floor_at_zero:
        sheet.total = max(0.0, sheet.total)
        sheet.subject_scores = {k: max(0.0, v)
                                for k, v in sheet.subject_scores.items()}
    return sheet


def _decide(marked: str | None, expected: str | None, reader_status: str | None,
            flagged: bool, scheme: MarkingScheme) -> tuple[str, float, str | None]:
    """Map one read question onto (status, marks, note)."""
    # No key entry: the question is outside what this test scores.  Falling
    # through to "wrong" here would make an incomplete answer key lower every
    # student's mark.
    if expected is None:
        return "unscored", 0.0, "no answer key for this question"

    if reader_status == "multiple":
        policy = scheme.ambiguous_policy
        if policy == "wrong":
            return "invalid", scheme.multiple_marks, "multiple marks scored as wrong"
        if policy == "blank":
            return "unattempted", scheme.blank, "multiple marks scored as blank"
        if policy == "zero":
            return "invalid", 0.0, "multiple marks voided"
        return "invalid", 0.0, "multiple marks held for review"

    if marked is None:
        return "unattempted", scheme.blank, None

    if flagged:
        # A resolved-but-uncertain read.  Scored on its merits and flagged, so
        # a reviewer can see the mark riding on a shaky measurement.
        status = "correct" if marked == expected else "wrong"
        return status, (scheme.correct if marked == expected else scheme.wrong), \
            "low-confidence read"

    if marked == expected:
        return "correct", scheme.correct, None
    return "wrong", scheme.wrong, None
