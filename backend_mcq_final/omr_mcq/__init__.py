"""omr_mcq -- structure-driven OMR bubble reading.

Locates answer bubbles by fitting a lattice to the sheet's own printed grid,
then classifies each region of interest by ink.  No circle detection, no
corner markers, and no per-sheet coordinate file: the geometry is measured
from the sheet, so one code path reads several different form layouts.

Quick start
-----------
    from omr_mcq import read_sheet, layout

    result = read_sheet("sheet.jpg", layout.NEET, answer_key={1: "C", 2: "A"})
    print(result.answers)        # {1: 'C', 2: 'A', ...}
    print(result.needs_review)   # question numbers a human should check
    print(result.total)          # None unless an answer_key was supplied

See ALGORITHM.md for how the lattice is fitted and why, and BENCHMARK.md for
the measured accuracy this package is built to hold.
"""
from __future__ import annotations

from . import layout
from .layout import Layout
from .marking import (
    AMBIGUOUS_POLICIES,
    NEGATIVE_MARKING,
    NO_NEGATIVE_MARKING,
    MarkingScheme,
    QuestionOutcome,
    ScoreSheet,
)
from .marks import (
    BLANK,
    CONFIDENT,
    INVALID,
    LOW_CONFIDENCE,
    MULTIPLE_MARK,
    REVIEW_STATUSES,
)
from .reader import (
    QuestionRead,
    SheetResult,
    SheetUnreadable,
    annotate,
    detect_layout,
    diagnose,
    read_sheet,
)

__version__ = "1.0.0"

__all__ = [
    "read_sheet", "detect_layout", "annotate", "diagnose",
    "SheetResult", "QuestionRead", "SheetUnreadable",
    "layout", "Layout",
    "MarkingScheme", "ScoreSheet", "QuestionOutcome",
    "NEGATIVE_MARKING", "NO_NEGATIVE_MARKING", "AMBIGUOUS_POLICIES",
    "CONFIDENT", "LOW_CONFIDENCE", "BLANK", "MULTIPLE_MARK", "INVALID",
    "REVIEW_STATUSES",
]
