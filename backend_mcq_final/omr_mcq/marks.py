"""Mark classification inside known bubble ROIs.

Separated from :mod:`grid` on purpose: *where* a bubble is and *whether it is
marked* are independent problems, and conflating them is what makes
circle-detection pipelines brittle.  Once :mod:`grid` has fixed the lattice,
nothing here needs to find a shape -- each ROI is simply scored for ink and
the scores are compared against each other.

Scoring
-------
``score_roi`` returns the fraction of the ROI's disc that reads as ink, where
"ink" is a per-pixel decision made against a *locally* estimated paper level
rather than a global threshold.  Local estimation is what makes the same
number mean the same thing on the shadowed and the lit half of one photo.

Colour is folded in via channel spread so a red or green pen mark counts even
though its luminance can sit close to white paper.

Decision
--------
Marks are decided by comparing the options of one question against each
other, never against a fixed page-wide cut.  Two thresholds are derived from
the sheet's own population of scores (Otsu on the full score histogram, which
is strongly bimodal on any real sheet), and the gap between the best and
second-best option decides confidence.  The outcome is one of:

``CONFIDENT``       one option clearly above the floor and ahead of the rest
``BLANK``           nothing above the floor
``MULTIPLE_MARK``   two or more options above the floor and close together
``LOW_CONFIDENCE``  the leader is marginal -- above the floor, but not clearly
``INVALID``         the question carried no sampleable ROI at all

The last two are reported, never guessed at.  For grading, a wrong confident
answer is far more damaging than a flagged one, so anything short of a clear
read is surfaced for review instead of being resolved silently.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# A pixel counts as ink when it is at least this far below the locally
# estimated paper level, on a 0..255 scale.  Set from the contrast between
# pencil/pen shading and paper on the sample captures; well below the ~90-point
# gap a solid mark produces, and well above JPEG/sensor noise (~5-10 points).
INK_DELTA = 90.0
# Channel spread above which a pixel is treated as coloured ink regardless of
# how bright it is, so red/green/orange marks are not lost to luminance.
COLOUR_DELTA = 45.0
# Fraction of the ROI disc that must read as ink before an option is even a
# candidate.  Deliberately low: it is only a floor to keep paper texture out,
# with the real decision made relatively, below.
MIN_FILL = 0.18
# Relative margin between best and runner-up, as a fraction of the best score.
# Below this the two are treated as indistinguishable -> "multiple".
AMBIGUOUS_RATIO = 0.55
# Absolute floor multiplier applied to the Otsu split of the sheet's own score
# histogram, so a faintly-marked sheet is still read while noise is not.
OTSU_RELAX = 0.75
# Need this many scores before the sheet-calibrated floor is trustworthy.
MIN_SAMPLES_FOR_OTSU = 40


# Reported verdict for one question.  These are the strings the API and the
# debug overlay use, chosen so that every non-CONFIDENT outcome is actionable
# by a human rather than silently resolved:
#
#   CONFIDENT       one option clearly ahead -- safe to grade automatically
#   LOW_CONFIDENCE  a mark is present but its lead is slim (faint, partly
#                   erased, or a scribble); graded, but flagged for review
#   BLANK           no option carries enough ink to count as a mark
#   MULTIPLE_MARK   two or more options are marked and cannot be separated
#   INVALID         the question could not be read at all (no ROI sampled)
CONFIDENT = "CONFIDENT"
LOW_CONFIDENCE = "LOW_CONFIDENCE"
BLANK = "BLANK"
MULTIPLE_MARK = "MULTIPLE_MARK"
INVALID = "INVALID"

REVIEW_STATUSES = (LOW_CONFIDENCE, MULTIPLE_MARK, INVALID)


@dataclass
class Decision:
    """One question's read."""

    choice: int | None          # index into the option list, None if unread
    status: str                 # one of the five verdicts above
    confidence: float           # 0..1
    scores: list[float]         # per-option fill fraction (raw, pre-pedestal)

    @property
    def needs_review(self) -> bool:
        return self.status in REVIEW_STATUSES


PAPER_KERNEL = 41


def _paper_level(gray: np.ndarray) -> np.ndarray:
    """Per-pixel estimate of blank-paper brightness.

    Grey-scale dilation (a local maximum) is used rather than a blur or a
    median.  Marks are always *darker* than the paper they sit on, so the
    brightest pixel in a neighbourhood a bit larger than one bubble is, by
    construction, unmarked paper.  A median is not safe here: inside a
    solidly-filled bubble most of the window is ink, so the median follows the
    mark down and the mark then measures as barely darker than its own
    surroundings.  Measured on the sample capture that collapse is exactly what
    happened -- a filled bubble read 94 against a 52 centre where dilation
    correctly reported 174, which is why filled and blank bubbles scored
    almost identically before this change.
    """
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (PAPER_KERNEL, PAPER_KERNEL))
    return cv2.dilate(gray, k)


def ink_mask(image: np.ndarray) -> np.ndarray:
    """Float 0..1 per-pixel ink strength for the whole (already-aligned) image.

    Computed once per sheet rather than per bubble: on a 200-question form that
    is ~800 ROIs, and doing the blur per ROI dominated runtime in the original
    implementation for no accuracy gain.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    paper = _paper_level(gray)
    darkness = np.clip((paper.astype(np.float32) - gray.astype(np.float32)) / INK_DELTA, 0.0, 1.0)
    if image.ndim == 3:
        bgr = image.astype(np.float32)
        spread = bgr.max(axis=2) - bgr.min(axis=2)
        colour = np.clip(spread / COLOUR_DELTA, 0.0, 1.0)
        return np.maximum(darkness, colour)
    return darkness


_DISC_CACHE: dict[int, np.ndarray] = {}


def _disc(radius: int) -> np.ndarray:
    m = _DISC_CACHE.get(radius)
    if m is None:
        yy, xx = np.ogrid[:2 * radius + 1, :2 * radius + 1]
        m = (xx - radius) ** 2 + (yy - radius) ** 2 <= radius ** 2
        _DISC_CACHE[radius] = m
    return m


def score_roi(ink: np.ndarray, cx: float, cy: float, r: float) -> float:
    """Fraction of the disc at (cx, cy) that reads as ink.

    The disc is shrunk slightly so the bubble's own printed outline sits
    outside it: the outline is present whether or not the student marked
    anything, so including it would add a constant offset to every option and
    compress the very difference the decision depends on.
    """
    rad = max(2, int(round(r * 0.72)))
    h, w = ink.shape[:2]
    icx, icy = int(round(cx)), int(round(cy))
    x0, x1 = max(0, icx - rad), min(w, icx + rad + 1)
    y0, y1 = max(0, icy - rad), min(h, icy + rad + 1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    mask = _disc(rad)[y0 - (icy - rad):y1 - (icy - rad), x0 - (icx - rad):x1 - (icx - rad)]
    if not mask.any():
        return 0.0
    return float(ink[y0:y1, x0:x1][mask].mean())


def relative_scores(scores: list[float]) -> list[float]:
    """Per-question scores with the question's own ink pedestal removed.

    Every bubble on these forms is printed with its option label inside it
    (1/2/3/4 rather than an empty ring), so a completely unmarked bubble still
    carries a fixed amount of ink -- measured at roughly 0.5 on the sample
    capture, against ~1.0 for a filled one.  That pedestal is common to all
    options of a question, so subtracting the question's own median (which is
    an unmarked option for any question answered normally, and stays robust
    even if two options are marked) leaves only what the student added.

    Doing this per question rather than per page also cancels local shading:
    a question sitting in a shadowed corner has its whole row of options
    darkened together, and the subtraction removes exactly that.
    """
    base = float(np.median(scores))
    return [max(0.0, s - base) for s in scores]


def calibrate_floor(all_scores: list[float]) -> float:
    """Sheet-specific "is this marked at all" floor.

    Otsu's split on the sheet's own score histogram adapts to this photo's
    contrast, which a fixed constant cannot: the same constant is either too
    strict for a faint pencil on a dim capture or too lenient for a crisp scan
    with heavy paper texture.  Relaxed slightly and clamped so a degenerate
    histogram (e.g. an entirely blank sheet, which is unimodal) cannot push the
    floor somewhere absurd.
    """
    if len(all_scores) < MIN_SAMPLES_FOR_OTSU:
        return MIN_FILL
    arr = (np.clip(np.asarray(all_scores, dtype=np.float32), 0, 1) * 255).astype(np.uint8)
    thresh, _ = cv2.threshold(arr.reshape(-1, 1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return float(np.clip((thresh / 255.0) * OTSU_RELAX, MIN_FILL, 0.60))


def decide(scores: list[float], floor: float) -> Decision:
    """Classify one question from its per-option scores.

    Relative, not absolute: the comparison that matters is between the options
    of *this* question, which cancels out any local lighting or paper
    difference that a page-wide threshold would be at the mercy of.
    """
    if not scores:
        return Decision(None, INVALID, 0.0, [])

    excess = relative_scores(scores)
    order = sorted(range(len(excess)), key=lambda i: excess[i], reverse=True)
    best, second = order[0], (order[1] if len(order) > 1 else None)
    top = excess[best]
    runner = excess[second] if second is not None else 0.0

    if top < floor:
        # Confidence here is confidence in *blankness*: the further the
        # strongest option sits below the floor, the surer we are.
        return Decision(None, BLANK, float(min(1.0, (floor - top) / max(floor, 1e-6))), scores)

    if runner >= floor and runner > top * AMBIGUOUS_RATIO:
        return Decision(None, MULTIPLE_MARK, float(1.0 - runner / max(top, 1e-6)), scores)

    # Separation between the leader and the runner-up, normalised by the
    # leader.  A solid single mark gives ~1.0; a hesitant or partly-erased one
    # gives a small margin and is flagged rather than trusted.
    margin = (top - runner) / max(top, 1e-6)
    if margin < 0.35:
        return Decision(best, LOW_CONFIDENCE, float(margin), scores)
    return Decision(best, CONFIDENT, float(min(1.0, margin)), scores)


def read_grid(image: np.ndarray, fit, questions_per_block: int | None = None
              ) -> list[Decision]:
    """Score and classify every cell of a fitted grid.

    Questions are emitted in the sheet's own reading order: all rows of block
    one, then all rows of block two, and so on, which is how these forms number
    them (1-50 Physics, 51-100 Chemistry, ...).
    """
    from .grid import deskew

    # The fit's coordinates are in the deskewed frame, so the image has to be
    # brought into that same frame before it is sampled.
    ink = ink_mask(deskew(image, fit.skew))
    rows = fit.rows if questions_per_block is None else fit.rows[:questions_per_block]

    raw: list[list[float]] = []
    for block in fit.blocks:
        for cy in rows:
            raw.append([score_roi(ink, cx, cy, fit.radius) for cx in block])

    # Calibrate on the pedestal-removed scores, since that is the scale the
    # decision actually works on.
    floor = calibrate_floor([s for opts in raw for s in relative_scores(opts)])
    return [decide(opts, floor) for opts in raw]
