"""Candidate-extraction tests.

The rule these all defend: **a wrong candidate field is worse than an empty
one.** An empty roll number is visible on the result screen and gets typed in;
a confident wrong one silently files a student's marks under someone else.

Skipped as a group when PaddleOCR is not installed, so the suite still runs on
a machine without it.

Run:  venv/Scripts/python.exe -m pytest test_ocr.py -q
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app import ocr

SAMPLES = Path(__file__).resolve().parent.parent / "backend_mcq_final" / "samples"
FIELDS = ("roll_no", "student_name", "class_std", "section", "registration_no")

pytestmark = pytest.mark.skipif(
    not ocr.available() or ocr._load() is None,
    reason="PaddleOCR is not installed on this machine",
)


def header(*rows: str, width: int = 1400, pad: int = 120) -> np.ndarray:
    """A synthetic sheet header. `pad` keeps text off the edge, which the
    detector otherwise clips."""
    img = np.full((120 + 100 * len(rows), width, 3), 255, np.uint8)
    for i, text in enumerate(rows):
        cv2.putText(img, text, (pad, 100 + i * 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
    return img


def two_column(pairs: list[tuple[str, str]], width: int = 1400) -> np.ndarray:
    """A boxed header: label on the left, value in its own column."""
    img = np.full((120 + 100 * len(pairs), width, 3), 255, np.uint8)
    for i, (label, value) in enumerate(pairs):
        y = 100 + i * 100
        cv2.putText(img, label, (120, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
        cv2.putText(img, value, (640, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
    return img


@pytest.mark.parametrize("sheet", ["neet_marked_sheet.jpg", "neet_marked_sheet_b.jpg"])
def test_blank_header_invents_nothing(sheet):
    """The real captures have an empty candidate block.

    Their headers do contain text -- the institute name, "NEET", the band rule
    "SECTION - A" and the subject headings -- all of which has been mistaken
    for candidate data before. Every field must come back empty.
    """
    img = cv2.imread(str(SAMPLES / sheet))
    assert img is not None, f"missing sample {sheet}"
    result = ocr.extract_candidate(img)
    found = {k: result[k] for k in FIELDS if result[k]}
    assert not found, f"invented candidate data from a blank header: {found}"


def test_section_band_rule_is_not_a_section():
    """"SECTION - A" is printed on every sheet by the form itself."""
    assert ocr._split_label("SECTION - A") is None
    assert ocr._split_label("SECTION-A") is None
    # A genuine filled field still reads.
    assert ocr._split_label("Section: B") == ("section", "B")


def test_labelled_fields_are_extracted():
    result = ocr.extract_candidate(header(
        "ROLL NO : 240571",
        "STUDENT NAME : RAHUL VERMA",
        "CLASS : 12",
        "SECTION : B",
        "REG NO : REG2026881",
    ), header_fraction=1.0)
    assert result["roll_no"] == "240571"
    assert result["student_name"] == "RAHUL VERMA"
    assert result["class_std"] == "12"
    assert result["section"] == "B"
    assert result["registration_no"] == "REG2026881"


def test_value_beside_label_is_extracted():
    """A boxed form writes the value in a column beside the label."""
    result = ocr.extract_candidate(two_column([
        ("ROLL NO", "771024"),
        ("STUDENT NAME", "ANITA DESAI"),
        ("CLASS", "11"),
    ]), header_fraction=1.0)
    assert result["roll_no"] == "771024"
    assert result["student_name"] == "ANITA DESAI"
    assert result["class_std"] == "11"


def test_value_below_a_label_is_not_taken():
    """Text on a different printed line is not this label's value.

    This is the exact shape of the bug: reading in detector order made the
    answer grid's "PHYSICS" heading the student's name.
    """
    img = np.full((420, 1400, 3), 255, np.uint8)
    cv2.putText(img, "STUDENT NAME", (120, 100),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
    # Far below, as a grid heading would be.
    cv2.putText(img, "PHYSICS", (640, 320),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
    result = ocr.extract_candidate(img, header_fraction=1.0)
    assert result["student_name"] is None, result["student_name"]


def test_neighbouring_label_is_not_a_value():
    """Two labels side by side: neither supplies the other's value."""
    result = ocr.extract_candidate(
        two_column([("ROLL NO", "CLASS")]), header_fraction=1.0)
    assert result["roll_no"] is None


def test_ocr_failure_is_not_fatal(monkeypatch):
    """A broken engine must still return a usable, empty result."""
    monkeypatch.setattr(ocr, "_lines", lambda img: [])
    result = ocr.extract_candidate(header("ROLL NO : 1"), header_fraction=1.0)
    assert all(result[f] is None for f in FIELDS)
    assert result["note"]


def test_disabled_ocr_returns_empty(monkeypatch):
    monkeypatch.setattr(ocr.config, "ENABLE_OCR", False)
    result = ocr.extract_candidate(header("ROLL NO : 1"), header_fraction=1.0)
    assert all(result[f] is None for f in FIELDS)
    assert "disabled" in (result["note"] or "").lower()
