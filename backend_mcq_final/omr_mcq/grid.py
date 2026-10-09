"""Structure-driven bubble localisation.

Why this module exists
----------------------
A coordinate-driven reader -- one that warps the photo onto a canonical page
and reads fill at hard-coded centres -- only works when the printed sheet and
the canonical render are the same document.  For a pre-printed institute form
they are not, and nothing downstream can recover from that: every bubble is
sampled in the wrong place while the pipeline reports success.

So this module stops asking where a template *says* the bubbles are and
measures where they actually are, using the one thing a pre-printed OMR form
reliably has: a rigid, repeating lattice inside a ruled table.

The lattice is also a far stronger signal than any individual bubble.  Fitting
a handful of numbers against hundreds of bubbles is heavily over-determined,
so a bubble that is merged by heavy shading, broken by a fold, or washed out
by blur costs nothing as long as its neighbours survive.  That is the opposite
of per-bubble detection, where each failure is independent and a single missed
bubble renumbers every question after it.

Method (classical, deterministic, no training data)
---------------------------------------------------
1. **Deskew.**  Residual in-plane rotation is measured from the printed table
   rules and removed, so the axis-aligned steps below hold.
2. **Grid box.**  Long-line morphology isolates the printed rules; the largest
   resulting box is the answer table.  This is anchor-based registration in
   which the sheet's own printed furniture is the anchor, so nothing depends
   on corner markers being present or legible.
3. **Bubble blobs.**  Connected components inside that box, filtered to
   small near-square shapes, give the printed bubbles' centres directly.
   This is the primitive everything else is built on.  Note what it is *not*:
   no circle is fitted and no radius is searched.  A blob only has to be
   roughly the right size to vote, and the geometry comes from the lattice
   fitted to the whole population -- so heavily-shaded, merged or blurred
   bubbles that stop looking circular cost nothing.
4. **Lattice.**  Blob centres are clustered along x into option columns
   (grouped into per-subject blocks) and along y into question rows.  Row and
   column positions therefore come from the same measurement and sit on the
   bubbles' centres.
5. **Reconciliation.**  The template's known row count is used to recover rows
   that failed to cluster, extending each section band at whichever edge
   actually carries ink.  Section banners, which open a similar gap but carry
   no questions, are never interpolated across.
6. **Per-ROI classification.**  :mod:`marks` measures fill inside the
   resulting cells.  The lattice says where a bubble must be; the only
   question asked of the pixels is how much ink sits there.

This is the "geometric / grid-based localisation + pixel-density analysis"
family of OMR methods, which on pre-printed forms is more robust than
Hough-circle or per-bubble contour detection: those degrade exactly where OMR
needs to be strongest, since a heavily shaded bubble stops being a circle and
a blurred outline stops being an edge, whereas a lattice fitted to the whole
page cannot lose an individual bubble at all.

Validated (tests/benchmark_full.py) on the photographed NEET sheet at 100%
answer accuracy under eleven capture distortions -- rotation to 2.5 degrees,
3x3 and 5x5 blur, over- and under-exposure, a lateral illumination ramp and
sensor noise -- and on the NEET, JEE, GUJCET and HSC blank masters, whose row
counts and block counts it recovers exactly.

Everything here works in the photo's own pixel space; no warp onto a
canonical page is involved.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# --- Grid-box detection -----------------------------------------------------
# Fraction of the image's own dimension a morphological run must span to count
# as a printed table rule rather than incidental ink.  1/25 is deliberately
# permissive: the rules on a photographed sheet break up under blur and uneven
# lighting, and a shorter kernel still reconstructs enough of the box.
RULE_LEN_DIVISOR = 25
# The answer table has to be a real fraction of the page or we have locked onto
# some smaller printed box (the roll-number grid, a signature field).
MIN_GRID_AREA_RATIO = 0.08

# --- Lattice fitting --------------------------------------------------------
# Plausible answer-row pitch in working-space pixels.  At the pipeline's
# 1600 px working width an A4 sheet with 50 rows per block lands near 30 px;
# the band spans roughly half to double that so denser and sparser forms fit.
MIN_ROW_PITCH = 16
MAX_ROW_PITCH = 70
# Option bubbles sit much closer together than rows.
MIN_COL_PITCH = 14
MAX_COL_PITCH = 70
# Autocorrelation peak below this is not a credible periodic structure.
MIN_AUTOCORR_SCORE = 0.15
# Sub-pixel resolution of the comb phase search.
PHASE_STEP = 0.25
# A question's option columns must span at least this fraction of the
# block-to-block stride.  Answer blocks are printed close-packed, so a fitted
# block far narrower than its stride means the pitch collapsed onto a subset of
# the real columns.
MIN_BLOCK_FILL = 0.45
# Plausible printed-bubble diameter, in working-space pixels.  Measured across
# the four institute layouts at 200 dpi: 21 px (HSC) to 29 px (NEET/JEE).  The
# band is wide enough to cover other scan resolutions without admitting
# character glyphs at one end or whole table cells at the other.
MIN_BUBBLE_PX = 8
MAX_BUBBLE_PX = 60


def _ink_map(gray: np.ndarray) -> np.ndarray:
    """Binary ink image with the printed table rules removed.

    Adaptive (not global) thresholding because sheet photos routinely have one
    side brighter than the other; a single global cut either drops the shaded
    half's bubbles or floods the lit half.  The long-run subtraction matters
    because the table rules are the strongest periodic signal on the page and
    would otherwise dominate the projection profiles we are about to take.
    """
    th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY_INV, 31, 8)
    hor = cv2.morphologyEx(th, cv2.MORPH_OPEN,
                           cv2.getStructuringElement(cv2.MORPH_RECT, (60, 1)))
    ver = cv2.morphologyEx(th, cv2.MORPH_OPEN,
                           cv2.getStructuringElement(cv2.MORPH_RECT, (1, 60)))
    return cv2.subtract(th, cv2.bitwise_or(hor, ver))


# Skew beyond this (degrees) is a genuinely tilted capture the alignment stage
# should have handled; below it, a residual tilt is corrected here.
MAX_DESKEW_DEG = 12.0


def estimate_skew(gray: np.ndarray) -> float:
    """Residual in-plane rotation of the printed grid, in degrees.

    Everything downstream takes axis-aligned projection profiles, which assume
    the bubble rows are horizontal.  They degrade quickly when they are not: a
    row tilted by 2 degrees spreads its ink over ~30 px across the grid's
    width, which is a full row pitch, so the profile's peaks wash out and both
    the box-finding morphology and the pitch estimate fail.  Measuring and
    removing the tilt first is cheaper and far more robust than trying to make
    every later stage rotation-invariant.

    The angle comes from the printed table rules via the Hough transform --
    used here to find *straight lines*, which is what it is reliable at, rather
    than to find circles, which is the use this pipeline deliberately avoids.
    """
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)
    min_len = max(60, gray.shape[1] // 6)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 360, threshold=120,
                            minLineLength=min_len, maxLineGap=12)
    if lines is None:
        return 0.0
    angles = []
    for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):
        ang = np.degrees(np.arctan2(float(y2 - y1), float(x2 - x1)))
        # Fold vertical rules onto the horizontal axis so both contribute.
        if abs(ang) > 45:
            ang -= 90 * np.sign(ang)
        if abs(ang) <= MAX_DESKEW_DEG:
            angles.append(ang)
    if len(angles) < 5:
        return 0.0
    return float(np.median(angles))


def deskew(image: np.ndarray, angle: float) -> np.ndarray:
    """Rotate *image* by -angle about its centre, padding with paper white."""
    if abs(angle) < 0.05:
        return image
    h, w = image.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, 1.0)
    border = (255, 255, 255) if image.ndim == 3 else 255
    return cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=border)


def find_grid_box(gray: np.ndarray) -> tuple[int, int, int, int] | None:
    """Locate the answer table as (x, y, w, h), or None.

    Uses the printed rules rather than the paper edge: the paper edge tells us
    nothing about where the content sits (that is precisely how the old
    contour layer produced a valid-looking but meaningless warp), whereas the
    table is rigidly attached to the bubbles.
    """
    h_img, w_img = gray.shape[:2]
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY_INV, 41, 12)
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(10, w_img // RULE_LEN_DIVISOR), 1))
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(10, h_img // RULE_LEN_DIVISOR)))
    rules = cv2.bitwise_or(cv2.morphologyEx(bw, cv2.MORPH_OPEN, hk),
                           cv2.morphologyEx(bw, cv2.MORPH_OPEN, vk))
    rules = cv2.dilate(rules, np.ones((5, 5), np.uint8))

    contours, _ = cv2.findContours(rules, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    best = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(best)
    if w * h < h_img * w_img * MIN_GRID_AREA_RATIO:
        logger.debug("find_grid_box: largest ruled box too small (%dx%d)", w, h)
        return None
    return int(x), int(y), int(w), int(h)


def _smooth_profile(binary: np.ndarray, axis: int) -> np.ndarray:
    """1-D ink projection along *axis*, lightly smoothed.

    Smoothing is what lets a single blurred or broken bubble outline still
    contribute to its row's peak instead of splitting into two weak ones.
    """
    prof = (binary > 0).sum(axis=axis).astype(np.float32)
    if prof.size < 5:
        return prof
    k = (1, 5) if axis == 1 else (5, 1)
    shape = (-1, 1) if axis == 1 else (1, -1)
    return cv2.GaussianBlur(prof.reshape(shape), k, 0).ravel()


def estimate_pitch(profile: np.ndarray, lo: int, hi: int) -> tuple[float, float]:
    """Dominant period of *profile* within [lo, hi], via autocorrelation.

    Returns (pitch, score) where score is the normalised autocorrelation at the
    winning lag; 0.0 means no credible periodicity was found.  Reading the
    period off the autocorrelation rather than off inter-peak distances is the
    whole point -- every row on the page votes, so rows that are blank, merged
    by heavy shading, or blurred out cannot individually corrupt the estimate.
    """
    if profile.size <= hi * 2:
        return 0.0, 0.0
    centred = profile - profile.mean()
    denom = float((centred * centred).sum())
    if denom <= 0:
        return 0.0, 0.0
    ac = np.correlate(centred, centred, mode="full")[profile.size - 1:] / denom
    hi = min(hi, ac.size - 1)
    if hi <= lo:
        return 0.0, 0.0
    window = ac[lo:hi + 1]
    peak = float(window.max())
    if peak < MIN_AUTOCORR_SCORE:
        return 0.0, peak

    # Prefer the *fundamental* period over its harmonics.  A comb of rows
    # correlates strongly at the true pitch and at every integer multiple of
    # it, and when alternating rows differ slightly in ink (a numbered row
    # against an unnumbered one, or a shaded row against a blank one) the 2x
    # lag can score higher than the 1x lag.  Taking the raw argmax then locks
    # the lattice onto every second row -- measured on the blank NEET master it
    # returned 64 px for a grid whose real pitch is 32 px, which silently drops
    # half the questions.  So we take the smallest lag that is a local maximum
    # and within a small margin of the best, which is the fundamental.
    HARMONIC_TOLERANCE = 0.85
    lag = int(np.argmax(window)) + lo
    for i in range(1, window.size - 1):
        if window[i] < peak * HARMONIC_TOLERANCE:
            continue
        if window[i] >= window[i - 1] and window[i] >= window[i + 1]:
            lag = i + lo
            break
    score = float(ac[lag])

    # Parabolic interpolation around the integer peak for sub-pixel pitch --
    # a quarter-pixel pitch error compounds to several pixels of drift by the
    # 50th row, which is the difference between sampling a bubble and sampling
    # the gap above it.
    if 0 < lag < ac.size - 1:
        y0, y1, y2 = float(ac[lag - 1]), float(ac[lag]), float(ac[lag + 1])
        denom2 = y0 - 2 * y1 + y2
        if abs(denom2) > 1e-9:
            lag += float(np.clip(0.5 * (y0 - y2) / denom2, -0.5, 0.5))
    return float(lag), score


def fit_phase(profile: np.ndarray, pitch: float) -> float:
    """Offset in [0, pitch) placing a comb of period *pitch* on maximum ink.

    With the pitch already fixed this is a one-parameter fit against hundreds
    of samples, so it is heavily over-determined and correspondingly stable.
    """
    n = profile.size
    best_off, best_score = 0.0, -1.0
    for off in np.arange(0.0, pitch, PHASE_STEP):
        idx = np.arange(off, n, pitch).astype(int)
        idx = idx[idx < n]
        if idx.size == 0:
            continue
        score = float(profile[idx].mean())
        if score > best_score:
            best_off, best_score = float(off), score
    return best_off


def lattice(profile: np.ndarray, lo: int, hi: int,
            expected: int | None = None) -> tuple[list[float], float, float]:
    """Fit a regular 1-D lattice to *profile*.

    Returns (positions, pitch, score).  When *expected* is given the lattice is
    truncated or extended to exactly that many positions, which lets a caller
    that knows the form's question count (from the template) impose it rather
    than trusting however many peaks survived the photo.
    """
    pitch, score = estimate_pitch(profile, lo, hi)
    if pitch <= 0:
        return [], 0.0, score
    phase = fit_phase(profile, pitch)
    count = expected if expected else int((profile.size - phase) // pitch) + 1
    positions = [phase + i * pitch for i in range(max(0, count))]
    return [p for p in positions if -pitch < p < profile.size + pitch], float(pitch), score


def _split_runs(values: np.ndarray, gap: float) -> list[list[float]]:
    """Group sorted *values* into runs separated by more than *gap*."""
    runs: list[list[float]] = []
    for v in values:
        if runs and v - runs[-1][-1] <= gap:
            runs[-1].append(float(v))
        else:
            runs.append([float(v)])
    return runs


def bubble_blobs(gray: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    """Centres of blob-shaped ink inside *box*, as an (N, 3) array of x, y, d.

    Printed bubble outlines are the most distinctive thing on an OMR form: they
    are small, round, of near-identical size, and repeated hundreds of times.
    Connected components recover them directly and give sub-pixel centres in
    one pass, which is a far stronger primitive than peaks in a projection
    profile -- a profile integrates a whole column into one number and so
    cannot tell a bubble column from a column of question-number glyphs, while
    a blob carries its own size and aspect ratio.

    This is shape-based, but note what it is *not*: no circle is fitted and no
    radius is searched.  A blob only has to be small and roughly square to
    vote; the geometry comes from the lattice fitted to the whole population,
    so heavily-shaded, broken or blurred bubbles that stop looking circular
    cost nothing as long as most of their neighbours survive.
    """
    x, y, w, h = box
    th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY_INV, 31, 8)
    n, _lab, stats, centroids = cv2.connectedComponentsWithStats(th, 8)
    if n <= 1:
        return np.empty((0, 3), dtype=np.float64)

    bw = stats[1:, cv2.CC_STAT_WIDTH].astype(np.float64)
    bh = stats[1:, cv2.CC_STAT_HEIGHT].astype(np.float64)
    cen = centroids[1:]
    keep = (
        (bw >= MIN_BUBBLE_PX) & (bw <= MAX_BUBBLE_PX)
        & (bh >= MIN_BUBBLE_PX) & (bh <= MAX_BUBBLE_PX)
        & (np.abs(bw - bh) <= np.maximum(bw, bh) * 0.35)
        & (cen[:, 0] >= x) & (cen[:, 0] <= x + w)
        & (cen[:, 1] >= y) & (cen[:, 1] <= y + h)
    )
    if not keep.any():
        return np.empty((0, 3), dtype=np.float64)
    return np.column_stack([cen[keep, 0], cen[keep, 1],
                            (bw[keep] + bh[keep]) / 2.0])


def _cluster_1d(values: np.ndarray, tol: float, min_count: int) -> list[float]:
    """Mean of each run of *values* whose neighbours differ by at most *tol*.

    Runs shorter than *min_count* are dropped, which is what separates a real
    bubble column (tens of members, one per row) from a stray blob.
    """
    if values.size == 0:
        return []
    order = np.sort(values)
    out: list[float] = []
    run = [float(order[0])]
    for v in order[1:]:
        if v - run[-1] <= tol:
            run.append(float(v))
        else:
            if len(run) >= min_count:
                out.append(float(np.mean(run)))
            run = [float(v)]
    if len(run) >= min_count:
        out.append(float(np.mean(run)))
    return out


def find_option_columns(ink: np.ndarray | None, box: tuple[int, int, int, int],
                        options_per_question: int,
                        n_blocks: int | None = None,
                        gray: np.ndarray | None = None) -> list[list[float]]:
    """Locate the option-bubble columns, grouped into question blocks.

    Works from the bubble blobs themselves (see :func:`bubble_blobs`) rather
    than from a projection profile.  Blob centres cluster into columns
    directly, and the option columns are then picked out by the one property
    that distinguishes them from question-number columns: they come in evenly
    spaced groups of *options_per_question*, repeated once per subject block.

    *ink* is kept only so older callers that passed an ink map still work; the
    grayscale image is what this needs.  Pass ``gray``.
    """
    if gray is None:
        if ink is None:
            raise ValueError("find_option_columns needs gray (or legacy ink)")
        gray = ink
    x, y, w, h = box
    blobs = bubble_blobs(gray, box)
    if blobs.shape[0] < options_per_question * 2:
        return []

    diameter = float(np.median(blobs[:, 2]))
    # A column is a set of blobs sharing an x within a fraction of one bubble.
    cols = _cluster_1d(blobs[:, 0], tol=max(3.0, diameter * 0.35),
                       min_count=max(3, int(blobs.shape[0] * 0.01)))
    if len(cols) < options_per_question:
        return []

    arr = np.asarray(cols, dtype=np.float64)
    gaps = np.diff(arr)
    inner = gaps[(gaps >= MIN_COL_PITCH) & (gaps <= MAX_COL_PITCH)]
    if inner.size == 0:
        return []
    # The option pitch is the most repeated column gap on the sheet.
    hist_bin = max(2.0, diameter * 0.15)
    binned: dict[int, int] = {}
    for g in inner:
        binned[int(round(float(g) / hist_bin))] =             binned.get(int(round(float(g) / hist_bin)), 0) + 1
    opt_pitch = max(binned.items(), key=lambda kv: (kv[1], -kv[0]))[0] * hist_bin

    # Walk the columns, emitting a block wherever options_per_question of them
    # are consecutive at that pitch.
    blocks: list[list[float]] = []
    i = 0
    tol = max(2.0, opt_pitch * 0.25)
    while i + options_per_question <= len(arr):
        window = arr[i:i + options_per_question]
        if np.all(np.abs(np.diff(window) - opt_pitch) <= tol):
            blocks.append([float(v) for v in window])
            i += options_per_question
        else:
            i += 1

    if n_blocks and len(blocks) > n_blocks:
        # Too many candidates: keep the n_blocks that are most regularly
        # spaced, which is what a printed multi-subject grid looks like.
        starts = np.array([b[0] for b in blocks])
        best, best_err = None, None
        for k in range(len(blocks) - n_blocks + 1):
            sel = starts[k:k + n_blocks]
            if sel.size < 2:
                continue
            err = float(np.std(np.diff(sel))) if sel.size > 1 else 0.0
            if best_err is None or err < best_err:
                best, best_err = k, err
        if best is not None:
            blocks = blocks[best:best + n_blocks]
    return blocks


@dataclass
class GridFit:
    """Result of fitting the answer lattice to one photo."""

    box: tuple[int, int, int, int]
    blocks: list[list[float]]          # per block: option-column x centres
    rows: list[float]                  # row y centres (whole grid)
    row_pitch: float
    col_pitch: float
    radius: float
    score: float                       # 0..1 confidence in the lattice
    # Rotation (degrees) that was removed before fitting.  All coordinates in
    # this object live in the *deskewed* frame, so any image sampled with them
    # must be passed through ``deskew(img, skew)`` first -- ``read_grid`` does
    # this for callers.
    skew: float = 0.0
    debug: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.blocks) and len(self.rows) > 1 and self.score >= MIN_AUTOCORR_SCORE


def fit_grid(gray: np.ndarray, options_per_question: int = 4,
             rows_per_block: int | None = None,
             n_blocks: int | None = None) -> GridFit | None:
    """Fit the answer-bubble lattice directly to a photo of the sheet.

    Both axes are derived from one primitive -- the centres of blob-shaped ink
    inside the ruled answer table (see :func:`bubble_blobs`).  Columns and rows
    are then the clusters of those centres along x and y, which places the
    lattice on the bubbles' centres and keeps the two axes mutually consistent.

    *rows_per_block* and *n_blocks* let the caller impose the layout the
    template expects rather than accepting whatever the image happened to
    yield; both are optional.

    Coordinates in the returned fit are in the deskewed frame; use
    ``fit.skew`` (or ``marks.read_grid``, which handles it) when sampling.
    """
    skew = estimate_skew(gray)
    gray = deskew(gray, skew)
    box = find_grid_box(gray)
    if box is None:
        return None

    blobs = bubble_blobs(gray, box)
    if blobs.shape[0] < options_per_question * 2:
        logger.debug("fit_grid: only %d bubble blobs found", blobs.shape[0])
        return None
    diameter = max(2.0, float(np.median(blobs[:, 2])))

    blocks = find_option_columns(None, box, options_per_question, n_blocks, gray)
    if not blocks:
        logger.debug("fit_grid: no option-column blocks found")
        return None

    # Rows are clustered from the blobs that sit inside the answer columns, so
    # question-number glyphs and header text -- which are outside that x range
    # -- cannot contribute a spurious row.
    lo_x = min(c for b in blocks for c in b) - diameter
    hi_x = max(c for b in blocks for c in b) + diameter
    in_cols = blobs[(blobs[:, 0] >= lo_x) & (blobs[:, 0] <= hi_x)]
    # A genuine answer row carries one bubble per option in every block.
    # Requiring most of them excludes header and section-title strips, whose
    # glyphs cluster at a single y but span only part of the grid width --
    # measured on the blank NEET master, admitting one such strip put question
    # 1 on the "SECTION - A" banner and shifted all 50 answers by one row.
    # Deliberately permissive: a row only has to contribute a few blobs to
    # count.  Demanding most of a full row's bubbles loses rows where marks
    # have merged neighbouring bubbles into one blob -- measured on the
    # photographed NEET sheet, a 60% rule dropped two rows near the section
    # banner and shifted every answer after them.  Extra clusters picked up by
    # a low threshold (banner text, header strips) are removed further down by
    # the ink-coverage window selection, which is a much safer filter than
    # never detecting the row at all.
    per_row = 3
    rows = _cluster_1d(in_cols[:, 1], tol=max(3.0, diameter * 0.35),
                       min_count=per_row)
    if len(rows) < 2:
        logger.debug("fit_grid: too few row clusters (%d)", len(rows))
        return None
    rows = sorted(rows)

    # Keep only clusters that look like answer rows.  The test is how many of
    # a cluster's blobs sit on an actual option column: a printed question row
    # puts one bubble under every column, while a section banner or a header
    # strip contributes text that lands between them.  Measured on the
    # photographed NEET sheet, real rows score 17-19 aligned blobs out of 16
    # columns and the banner and header clusters score 0-6, so the two
    # populations are cleanly separable and no tuning is needed beyond
    # requiring roughly half the columns to be covered.
    col_centres = np.asarray([c for b in blocks for c in b], dtype=np.float64)
    need_on_cols = max(2, int(len(col_centres) * 0.5))
    aligned = []
    for r in rows:
        near = in_cols[np.abs(in_cols[:, 1] - r) <= diameter * 0.5]
        if near.size == 0:
            continue
        on = int(np.sum(np.min(np.abs(col_centres[None, :] - near[:, 0:1]), axis=1)
                        <= diameter * 0.35))
        if on >= need_on_cols:
            aligned.append(r)
    if len(aligned) >= 2:
        rows = aligned

    gaps = np.diff(rows)
    valid = (gaps >= MIN_ROW_PITCH) & (gaps <= MAX_ROW_PITCH)
    row_pitch = float(np.median(gaps[valid])) if valid.any() else float(np.median(gaps))
    # Confidence in the row structure: the fraction of consecutive gaps that
    # agree with the dominant pitch.  A cleanly printed grid scores near 1.0,
    # while a fit that has latched onto unrelated ink scores low and is
    # rejected by GridFit.ok.
    score = float(np.mean(np.abs(gaps - row_pitch) <= max(2.0, row_pitch * 0.25)))         if gaps.size else 0.0

    # Drop clusters that sit far off the dominant pitch from *both* of their
    # neighbours.  A header or instruction strip can pass the full-width test
    # above (its glyphs span the grid) yet sit a non-multiple of the pitch from
    # the real rows -- measured on the blank NEET master one such cluster sat
    # 101 px above row 1 against a 32 px pitch and displaced every question by
    # one.  Judging each cluster by its neighbours, rather than chaining from a
    # committed start, keeps the section break (a legitimate two-pitch gap)
    # from truncating the grid.
    if len(rows) > 3 and row_pitch > 0:
        def _on_pitch(delta: float) -> bool:
            step = abs(delta) / row_pitch
            k = round(step)
            return 1 <= k <= 2 and abs(step - k) <= 0.2

        kept = []
        for idx, r in enumerate(rows):
            prev_ok = idx > 0 and _on_pitch(r - rows[idx - 1])
            next_ok = idx + 1 < len(rows) and _on_pitch(rows[idx + 1] - r)
            if prev_ok or next_ok:
                kept.append(r)
        if len(kept) >= 2:
            rows = kept

    # Note on gaps: these forms interrupt the row lattice with section banners
    # ("SECTION - B"), which open a gap of about three row pitches containing
    # no question row at all.  Interpolating across such a gap invents rows and
    # shifts every later question, so no gap-filling is done here.  A row that
    # genuinely fails to cluster is instead recovered by the regularisation
    # below, which rebuilds each contiguous run from its own fitted pitch.

    # Drop an isolated row whose gap to the rest is not a whole number of
    # pitches.  A block header ("MATHS/BIOLOGY") spans the full grid width, so
    # it survives the column-alignment test above, but it does not sit on the
    # question lattice -- measured on the blank GUJCET master it sat 69.8 px
    # above row 1 against a 38.7 px pitch, which shifted all 40 rows by one and
    # read the header text itself as a marked bubble.
    #
    # Only the outermost rows are checked: an interior row that is off-pitch is
    # far more likely to be a real row the printer shifted slightly than a
    # stray, and dropping it would renumber everything after it.
    if row_pitch > 0 and len(rows) > 3:
        def _off_lattice(gap: float) -> bool:
            steps = gap / row_pitch
            # A real row sits one pitch from its neighbour.  Anything further
            # is either a section banner (a legitimate skip, left alone below)
            # or a stray; what is never legitimate is a gap that is not close
            # to a whole number of pitches at all.  The blank GUJCET header sat
            # at 1.80 pitches, so the tolerance has to be tighter than 0.2 to
            # catch it while still admitting a genuine 2-pitch section skip.
            return abs(steps - round(steps)) > 0.15 or round(steps) < 1

        while len(rows) > 3 and _off_lattice(rows[1] - rows[0]):
            rows = rows[1:]
        while len(rows) > 3 and _off_lattice(rows[-1] - rows[-2]):
            rows = rows[:-1]
        gaps = np.diff(rows)
        valid = (gaps >= MIN_ROW_PITCH) & (gaps <= MAX_ROW_PITCH)
        if valid.any():
            row_pitch = float(np.median(gaps[valid]))

    # Split the rows into section bands, then reconcile each band's row count
    # with the total the template expects.
    #
    # Two independent defects have to be handled here, and they pull opposite
    # ways.  Section banners ("SECTION - B") open a gap of roughly three
    # pitches carrying no questions, so nothing may be interpolated across
    # them.  Meanwhile a row whose bubbles are heavily marked merges into one
    # or two large blobs and fails to cluster at all -- measured on the
    # photographed NEET sheet the last row of each section yielded only 3-4
    # blobs against 16 columns, so both sections came up one row short and
    # every answer after them shifted by one.
    #
    # Rather than probe the image for those missing rows (which needs a
    # contrast threshold, and any fixed threshold fails under blur or
    # over-exposure), the shortfall is distributed using what is already known
    # for certain: the template's total row count, and the fact that each band
    # is internally evenly pitched.  Each band is extended at its trailing edge
    # -- where the merge happens, since the last row of a section abuts the
    # banner or the closing rule -- until the totals agree.
    if rows_per_block and len(rows) >= 2:
        # Split on any gap that is not close to a single pitch.  A wider gap
        # is either a section banner or a run of rows that failed to cluster,
        # and in both cases the rows either side belong to separately-anchored
        # runs: measuring a band's size across such a gap assumes the interior
        # is evenly filled, which is exactly what is in doubt.
        bands: list[list[float]] = [[rows[0]]]
        for prev, cur in zip(rows, rows[1:]):
            (bands.append([cur]) if cur - prev > row_pitch * 1.5
             else bands[-1].append(cur))

        sizes = [len(b) for b in bands]
        shortfall = rows_per_block - sum(sizes)
        # Only reconcile a small shortfall.  A large one means part of the grid
        # is genuinely absent from the image (a crop, a fold, a thumb over the
        # page), and inventing rows there would be a silent misread -- the fit
        # is left short so the caller can refuse it.
        # Distribute the shortfall, choosing for each added row whether it
        # belongs before a band or after it.  A row that fails to cluster is
        # one whose bubbles merged -- against a banner, a closing rule, or
        # simply through blur -- and that happens at either end: measured, the
        # sharp capture loses the last row of each section while the same image
        # under a 5x5 blur loses the *first* row instead.  Assuming one edge
        # shifts every answer by one whenever the other edge was the real
        # culprit, so the two candidates are compared on how much ink actually
        # sits there and the darker one wins.
        dark = (gray.astype(np.float32) <
                cv2.dilate(gray, cv2.getStructuringElement(
                    cv2.MORPH_ELLIPSE, (31, 31))).astype(np.float32) - 30.0)
        col_ix = np.clip(np.rint([c for b in blocks for c in b]).astype(int),
                         0, gray.shape[1] - 1)

        def _edge_ink(y: float) -> float:
            y0 = int(max(0, round(y - diameter * 0.35)))
            y1 = int(min(gray.shape[0], round(y + diameter * 0.35) + 1))
            if y1 <= y0:
                return -1.0
            strip = dark[y0:y1, :]
            return float(sum(1 for cx in col_ix
                             if strip[:, max(0, cx - 3):cx + 4].any()))

        leading = [0] * len(bands)
        if 0 < shortfall <= max(2, len(bands) * 2):
            for i in range(shortfall):
                bi = i % len(bands)
                band = bands[bi]
                step = ((band[-1] - band[0]) / (len(band) - 1)
                        if len(band) > 1 else row_pitch)
                before = _edge_ink(band[0] - step * (leading[bi] + 1))
                after = _edge_ink(band[0] + step * (sizes[bi] - leading[bi]))
                sizes[bi] += 1
                if before > after:
                    leading[bi] += 1

        if sum(sizes) == rows_per_block:
            rows = []
            for band, n, lead in zip(bands, sizes, leading):
                if n <= 1:
                    rows.extend(band[:1])
                    continue
                measured = ((band[-1] - band[0]) / (len(band) - 1)
                            if len(band) > 1 else row_pitch)
                # Resample from the band's own pitch so an extended band keeps
                # the printed spacing rather than stretching to fit.
                start = band[0] - measured * lead
                rows.extend(start + measured * k for k in range(n))

    if rows_per_block and len(rows) > rows_per_block:
        # More rows than the template expects.  Choose the window by how much
        # *bubble ink* it actually covers, not by how evenly spaced it is:
        # after gap-filling, several windows are equally regular, so regularity
        # can no longer discriminate and the choice silently slid off by one
        # row in testing.  Ink coverage cannot -- a window that includes a
        # phantom row at either end covers less than one that does not.
        counts = []
        half = max(2.0, diameter * 0.5)
        for r in rows:
            near = in_cols[np.abs(in_cols[:, 1] - r) <= half]
            counts.append(len(near))
        counts = np.asarray(counts, dtype=np.float64)
        best_start = int(np.argmax([counts[k:k + rows_per_block].sum()
                                    for k in range(len(rows) - rows_per_block + 1)]))
        rows = rows[best_start:best_start + rows_per_block]

    col_pitch = float(np.median([np.median(np.diff(b)) for b in blocks if len(b) > 1]))         if any(len(b) > 1 for b in blocks) else 0.0
    # Radius is measured from the blobs themselves rather than inferred from
    # the pitch, so a form whose bubbles are spaced loosely relative to their
    # size is sampled correctly.
    radius = max(3.0, diameter / 2.0)

    return GridFit(box=box, blocks=blocks, rows=rows, row_pitch=float(row_pitch),
                   col_pitch=col_pitch, radius=float(radius), score=float(score),
                   skew=float(skew),
                   debug={"n_blocks": len(blocks), "n_rows": len(rows)})
