"""Read an OMR sheet: the one function most callers need.

    from omr_mcq import read_sheet, layout
    result = read_sheet("sheet.jpg", layout.NEET, answer_key={1: "C", ...})
    print(result.total, result.needs_review)

Everything below is a thin shell over :mod:`grid` (where the bubbles are) and
:mod:`marks` (whether each is filled).  Its job is to turn their output into
question numbers and marks, and to refuse rather than guess when the sheet
cannot be read.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from . import grid as grid_mod
from . import marks as marks_mod
from .layout import Layout
from .marking import MarkingScheme, ScoreSheet, apply_scheme

logger = logging.getLogger(__name__)

# Working width the reader normalises to.  Large enough that a ~30 px row
# pitch survives (the lattice needs several pixels per bubble), small enough
# that a 12 MP phone photo does not cost seconds.  Measured end-to-end at
# ~0.5-0.9 s per sheet at this width.
WORKING_WIDTH = 1600


class SheetUnreadable(Exception):
    """The sheet could not be read confidently.

    Raised instead of returning a partial result, because a half-read sheet
    that looks complete is the single most damaging thing this package could
    produce: it yields confident marks for questions nobody actually checked.
    """

    def __init__(self, reason: str, hint: str):
        super().__init__(hint)
        self.reason = reason
        self.hint = hint


@dataclass
class QuestionRead:
    """One question as the reader saw it, before any marking is applied."""

    q: int
    subject: str
    marked: str | None
    verdict: str                 # CONFIDENT | LOW_CONFIDENCE | BLANK | ...
    confidence: float
    needs_review: bool
    scores: list[float] = field(default_factory=list)


@dataclass
class SheetResult:
    """Everything one sheet produced."""

    layout: Layout
    questions: list[QuestionRead]
    grid: dict
    score: ScoreSheet | None = None

    @property
    def answered(self) -> int:
        return sum(1 for q in self.questions if q.marked is not None)

    @property
    def needs_review(self) -> list[int]:
        return [q.q for q in self.questions if q.needs_review]

    @property
    def answers(self) -> dict[int, str | None]:
        return {q.q: q.marked for q in self.questions}

    @property
    def total(self) -> float | None:
        return self.score.total if self.score else None

    def as_dict(self) -> dict:
        out = {
            "layout": self.layout.name,
            "grid": self.grid,
            "answered": self.answered,
            "needs_review": self.needs_review,
            "questions": [
                {"q": q.q, "subject": q.subject, "marked": q.marked,
                 "verdict": q.verdict, "confidence": round(q.confidence, 3),
                 "needs_review": q.needs_review}
                for q in self.questions
            ],
        }
        if self.score:
            out["score"] = self.score.as_dict()
            by_q = {o.q: o for o in self.score.outcomes}
            for record in out["questions"]:
                outcome = by_q.get(record["q"])
                if outcome:
                    record["expected"] = outcome.expected
                    record["status"] = outcome.status
                    record["marks"] = outcome.marks
        return out


def load_image(source: str | Path | bytes | np.ndarray) -> np.ndarray:
    """Accept a path, raw bytes, or an array, and return a BGR image."""
    if isinstance(source, np.ndarray):
        img = source
    elif isinstance(source, (bytes, bytearray)):
        img = cv2.imdecode(np.frombuffer(source, np.uint8), cv2.IMREAD_COLOR)
    else:
        img = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if img is None:
        raise SheetUnreadable("decode_failed",
                              "Could not read that image file.")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return img


def normalise(img: np.ndarray, width: int = WORKING_WIDTH) -> np.ndarray:
    """Scale to the working width.  Smaller images are left alone.

    Upscaling a small photo adds no detail, and the lattice fit would then be
    reported at a precision the pixels do not support.
    """
    h, w = img.shape[:2]
    if w <= width:
        return img
    return cv2.resize(img, (width, int(round(h * width / w))),
                      interpolation=cv2.INTER_AREA)


def read_sheet(source, sheet_layout: Layout,
               answer_key: dict | None = None,
               scheme: MarkingScheme | None = None) -> SheetResult:
    """Read one OMR sheet.

    Parameters
    ----------
    source:
        Image path, raw bytes, or a BGR array.
    sheet_layout:
        How the questions are counted; see :mod:`omr_mcq.layout`.
    answer_key:
        ``{question_number: option_label}``.  Optional -- without it the marks
        are still read and reported, just not scored, which is what you want
        when checking a new form before any key exists.
    scheme:
        Marking rules.  Defaults to the +4/-1 pattern with a double mark
        counted as wrong.

    Raises
    ------
    SheetUnreadable
        When the answer grid cannot be located, or when fewer blocks are found
        than the layout declares -- which would silently drop whole subjects.
    """
    img = normalise(load_image(source))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    fit = grid_mod.fit_grid(gray,
                            options_per_question=len(sheet_layout.options),
                            rows_per_block=sheet_layout.rows_per_block,
                            n_blocks=sheet_layout.blocks)
    if fit is None or not fit.ok:
        raise SheetUnreadable(
            "grid_not_found",
            "Could not lock onto the answer grid. Make sure the whole sheet, "
            "including every answer column, is in frame, flat and evenly lit.")

    # The answer table must not run off the edge of the photo.  A grid box
    # flush against the frame means columns were cropped away, and what
    # survives can still fit some *other* layout convincingly -- measured, a
    # NEET capture with its Zoology column cut off fitted the 3-block GUJCET
    # layout and read three subjects as if that were the whole paper.  The
    # block count cannot catch this, because the missing column never reaches
    # the fitter at all.
    box_x, box_y, box_w, box_h = fit.box
    img_h, img_w = gray.shape[:2]
    margin = max(2.0, fit.radius * 0.5)
    if (box_x < margin or box_y < margin
            or img_w - (box_x + box_w) < margin
            or img_h - (box_y + box_h) < margin):
        raise SheetUnreadable(
            "grid_touches_frame",
            "The answer grid runs to the edge of the photo, so part of it is "
            "cropped. Step back and include the whole sheet in frame.")

    # Block-to-block spacing must be regular.  A printed form repeats its
    # subject blocks at one stride, so a stride that is roughly double its
    # neighbour means a block sat between them and was missed -- the columns
    # on either side are real, which is why the block *count* alone cannot
    # catch it.  Measured: a NEET sheet photographed small in frame yielded
    # strides of 261 and 128 px and was read as a 3-block GUJCET paper, while
    # genuine forms run 228/230/232 and 246/280.
    if len(fit.blocks) > 2:
        strides = np.diff([block[0] for block in fit.blocks])
        if strides.min() > 0 and strides.max() / strides.min() > 1.5:
            raise SheetUnreadable(
                "irregular_block_spacing",
                "The answer columns are not evenly spaced, so at least one "
                "column was missed. Photograph the sheet larger in the frame, "
                "square on and evenly lit.")

    if len(fit.blocks) < sheet_layout.blocks:
        raise SheetUnreadable(
            "incomplete_grid",
            f"Found {len(fit.blocks)} of {sheet_layout.blocks} answer columns. "
            "Part of the sheet is outside the frame or obscured.")

    # The row count must match the layout too, not just the block count.
    #
    # Without this the reader happily returns a 38-row fit for a 50-row
    # layout: the questions it did find are read correctly, but they are
    # numbered from the top of whatever it found, so every answer after the
    # first missing row is attributed to the wrong question.  That is the
    # silent-misread failure this package exists to avoid, and it is also how
    # a sheet of the *wrong layout* presents -- an HSC form read as NEET fits
    # 10 rows of 50 and reports success.
    #
    # Checked here rather than inside the fitter because only the caller knows
    # which layout was intended; the fitter is told the expected count and
    # does its best, which is the right division of labour.
    if len(fit.rows) != sheet_layout.rows_per_block:
        raise SheetUnreadable(
            "row_count_mismatch",
            f"Found {len(fit.rows)} question rows where the "
            f"{sheet_layout.name} layout expects "
            f"{sheet_layout.rows_per_block}. Either part of the grid is out "
            "of frame, or this is a different sheet layout.")

    decisions = marks_mod.read_grid(img, fit)
    labels = sheet_layout.options

    questions: list[QuestionRead] = []
    for idx, decision in enumerate(decisions[:sheet_layout.total_questions]):
        number = idx + 1
        marked = (labels[decision.choice]
                  if decision.choice is not None and decision.choice < len(labels)
                  else None)
        questions.append(QuestionRead(
            q=number,
            subject=sheet_layout.subject_of(number),
            marked=marked,
            verdict=decision.status,
            confidence=float(decision.confidence),
            needs_review=decision.needs_review,
            scores=[float(s) for s in decision.scores],
        ))

    result = SheetResult(
        layout=sheet_layout,
        questions=questions,
        grid={
            "blocks": len(fit.blocks),
            "rows": len(fit.rows),
            "row_pitch": round(fit.row_pitch, 2),
            "col_pitch": round(fit.col_pitch, 2),
            "radius": round(fit.radius, 2),
            "skew_deg": round(fit.skew, 2),
            "fit_score": round(fit.score, 3),
        },
    )

    if answer_key:
        per_q = [{"q": q.q, "subject": q.subject, "marked": q.marked,
                  "status": _reader_status(q.verdict),
                  "needs_review": q.needs_review}
                 for q in questions]
        result.score = apply_scheme(per_q, answer_key,
                                    scheme or MarkingScheme())

    # Kept for callers that want a debug overlay without re-fitting the grid.
    result._fit = fit              # type: ignore[attr-defined]
    result._decisions = decisions  # type: ignore[attr-defined]
    result._image = img            # type: ignore[attr-defined]
    return result


def detect_layout(source, candidates=None):
    """Return the first built-in layout that reads *source* cleanly.

    Useful when a batch mixes exam types, or when you are handed a photo and
    do not know which form it is.  A layout only "reads cleanly" when the
    fitted block *and* row counts match what it declares, and that check is
    strict enough to tell the forms apart: measured across 31 real captures,
    every sheet matched exactly one of the four built-in layouts, and the
    eight that matched none were genuinely unreadable (cropped mid-grid,
    photographed sideways, or columns out of frame).

    Returns ``(layout, result)``, or raises :class:`SheetUnreadable` when no
    candidate fits -- never a best guess, because grading against the wrong
    layout renumbers every answer.
    """
    from .layout import LAYOUTS

    options = list(candidates if candidates is not None else LAYOUTS.values())

    # Rank candidates by a fit taken with *no* counts imposed, so the sheet's
    # own geometry picks the layout rather than the order of the list.
    #
    # Trying each in turn and taking the first that is accepted is not enough:
    # the fitter honours whatever row count it is given, so GUJCET (3 blocks,
    # 40 rows) and JEE (3 blocks, 25 rows) both accept each other's sheets and
    # whichever is tried first wins.  An unconstrained fit recovers the true
    # shape -- measured on the blank masters it returns exactly 3x40, 3x25,
    # 4x49 and 5x10 -- which separates them cleanly.
    try:
        img = normalise(load_image(source))
        probe = grid_mod.fit_grid(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY),
                                  options_per_question=4)
    except SheetUnreadable:
        probe = None

    if probe is not None and probe.ok:
        # A layout with *fewer* blocks than the sheet actually has must never
        # be accepted, however well its row count happens to match.  A NEET
        # capture with its lower rows cut off probes as 4 blocks x 38 rows;
        # the NEET layout then rightly refuses on the row count, and without
        # this filter the 3-block GUJCET layout accepts it instead -- reading
        # three of the four subjects and renumbering every question.  Dropping
        # a whole subject column is never a better answer than refusing.
        options = [c for c in options if c.blocks >= len(probe.blocks)]

        def distance(candidate: Layout) -> tuple[int, int]:
            return (abs(len(probe.blocks) - candidate.blocks),
                    abs(len(probe.rows) - candidate.rows_per_block))

        options.sort(key=distance)

    last: SheetUnreadable | None = None
    for candidate in options:
        try:
            return candidate, read_sheet(source, candidate)
        except SheetUnreadable as exc:
            last = exc
    raise SheetUnreadable(
        "no_matching_layout",
        "No known sheet layout fits this image. "
        + (last.hint if last else ""))


def _reader_status(verdict: str) -> str:
    """Map a verdict onto the vocabulary :mod:`marking` expects.

    LOW_CONFIDENCE and INVALID fold onto "multiple" rather than onto a guess:
    all three mean "a human should look at this", and the marking layer
    already treats that as held-for-review rather than as a wrong answer.
    """
    if verdict == marks_mod.BLANK:
        return "none"
    if verdict == marks_mod.CONFIDENT:
        return "ok"
    return "multiple"


def annotate(result: SheetResult) -> np.ndarray:
    """Render the review overlay for a result from :func:`read_sheet`.

    Rings the bubble the student marked, green when it matches the key and red
    when it does not, with the correct option shown on the ones that were
    missed and an amber ring on anything held for review.
    """
    from . import debug_viz

    fit = getattr(result, "_fit", None)
    decisions = getattr(result, "_decisions", None)
    img = getattr(result, "_image", None)
    if fit is None or decisions is None or img is None:
        raise ValueError("result did not come from read_sheet()")

    scored = None
    if result.score:
        scored = [{"q": o.q, "subject": o.subject, "marked": o.marked,
                   "correct": o.expected, "status": o.status, "marks": o.marks}
                  for o in result.score.outcomes]
    return debug_viz.draw_review(img, fit, decisions, scored)


def diagnose(result: SheetResult) -> np.ndarray:
    """Render the three-panel localisation diagnostic.

    Use this when the question is "did the lattice land correctly", rather
    than "what did the student answer".
    """
    from . import debug_viz

    fit = getattr(result, "_fit", None)
    decisions = getattr(result, "_decisions", None)
    img = getattr(result, "_image", None)
    if fit is None or decisions is None or img is None:
        raise ValueError("result did not come from read_sheet()")
    return debug_viz.draw_report(img, fit, decisions)
