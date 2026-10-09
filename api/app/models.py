"""Request bodies.  Responses are plain dicts built from DB rows."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, EmailStr, Field, field_validator

from .omr_engine import LAYOUT_NAMES

AMBIGUOUS = ("wrong", "blank", "zero", "review")


class SignUp(BaseModel):
    email: EmailStr
    # 8 is the floor; the 72-byte bcrypt ceiling is enforced in the route.
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    institution_name: str | None = Field(default=None, max_length=160)


class SignIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TestIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    subject: str | None = Field(default=None, max_length=120)
    exam_date: date | None = None
    layout: str = "neet"
    total_questions: int = Field(ge=1, le=1000)
    options: str = "A,B,C,D"
    marks_correct: float = 4
    marks_wrong: float = -1
    marks_blank: float = 0
    ambiguous_policy: str = "wrong"
    floor_at_zero: bool = True

    @field_validator("layout")
    @classmethod
    def _layout(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in LAYOUT_NAMES:
            raise ValueError(f"layout must be one of: {', '.join(LAYOUT_NAMES)}")
        return v

    @field_validator("ambiguous_policy")
    @classmethod
    def _policy(cls, v: str) -> str:
        if v not in AMBIGUOUS:
            raise ValueError(f"ambiguous_policy must be one of: {', '.join(AMBIGUOUS)}")
        return v


class AnswerKeyEntry(BaseModel):
    question_no: int = Field(ge=1, le=1000)
    correct_option: str = Field(min_length=1, max_length=8)
    marks: float | None = None


class AnswerKeyIn(BaseModel):
    # Replaces the whole key for the test: a partial PATCH of a key is how you
    # end up grading against a half-updated one.
    entries: list[AnswerKeyEntry]


class CandidateIn(BaseModel):
    """The editable candidate block. All optional: OCR may have found nothing."""
    roll_no: str | None = Field(default=None, max_length=60)
    student_name: str | None = Field(default=None, max_length=160)
    class_std: str | None = Field(default=None, max_length=60)
    section: str | None = Field(default=None, max_length=30)
    registration_no: str | None = Field(default=None, max_length=60)


class AnswerOverride(BaseModel):
    question_no: int = Field(ge=1, le=1000)
    # None clears the answer back to unattempted.
    marked_option: str | None = Field(default=None, max_length=8)
