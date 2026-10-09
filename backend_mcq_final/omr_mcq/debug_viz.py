"""Debug overlays for the structure-driven reader.

Kept out of :mod:`annotate` because that module draws *grading* feedback on a
canonical-frame sheet, whereas these overlays draw *localisation* evidence in
the photo's own frame.  Being able to see where the lattice landed is the
difference between "the answers are wrong" and "row 36 sits in the section
gap", which is precisely the failure that motivated this module's existence.
"""
from __future__ import annotations

import cv2
import numpy as np

from . import marks
from .marks import Decision

RED = (40, 40, 220)
GREEN = (60, 180, 60)
AMBER = (0, 165, 255)
BLUE = (220, 140, 40)
GREY = (150, 150, 150)

STATUS_COLOUR = {
    marks.CONFIDENT: GREEN,
    marks.BLANK: GREY,
    marks.MULTIPLE_MARK: RED,
    marks.LOW_CONFIDENCE: AMBER,
    marks.INVALID: RED,
}


def draw_grid(image: np.ndarray, fit, decisions: list[Decision] | None = None,
              label_rows: bool = True) -> np.ndarray:
    """Render the fitted lattice, and each cell's verdict when available.

    Every ROI the reader actually sampled is drawn, so a mis-fit shows up
    directly as circles sitting off the printed bubbles rather than having to
    be inferred from wrong answers.
    """
    from .grid import deskew

    out = image.copy() if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    # Draw in the same (deskewed) frame the lattice was fitted in, or the
    # overlay would appear offset from the bubbles it actually sampled.
    out = deskew(out, fit.skew)
    x, y, w, h = fit.box
    cv2.rectangle(out, (x, y), (x + w, y + h), BLUE, 2)

    r = int(round(fit.radius))
    n_rows = len(fit.rows)
    for b_idx, block in enumerate(fit.blocks):
        for r_idx, cy in enumerate(fit.rows):
            d = None
            if decisions is not None:
                flat = b_idx * n_rows + r_idx
                if flat < len(decisions):
                    d = decisions[flat]
            for o_idx, cx in enumerate(block):
                colour = GREY
                thickness = 1
                if d is not None:
                    colour = STATUS_COLOUR.get(d.status, GREY)
                    if d.choice == o_idx:
                        thickness = 2
                    elif d.status in (marks.CONFIDENT, marks.BLANK):
                        colour = GREY
                cv2.circle(out, (int(round(cx)), int(round(cy))), r, colour, thickness)
        if label_rows:
            for r_idx, cy in enumerate(fit.rows):
                cv2.putText(out, str(b_idx * n_rows + r_idx + 1),
                            (int(block[0]) - 58, int(cy) + 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, BLUE, 1, cv2.LINE_AA)
    return out


def draw_profiles(gray: np.ndarray, fit) -> np.ndarray:
    """Side-by-side row and column ink profiles with the fitted lattice marked.

    Makes a pitch or phase error visible as a comb that walks off its peaks,
    which no amount of staring at the answers themselves would reveal.
    """
    from . import grid as grid_mod

    ink = grid_mod._ink_map(gray)
    x, y, w, h = fit.box
    panel = np.full((h, 320, 3), 255, dtype=np.uint8)

    cols = [c for b in fit.blocks for c in b]
    lo, hi = int(min(cols)) - 12, int(max(cols)) + 12
    prof = grid_mod._smooth_profile(ink[y:y + h, max(0, lo):hi], axis=1)
    if prof.max() > 0:
        scaled = (prof / prof.max() * 300).astype(int)
        for i, v in enumerate(scaled[:h]):
            cv2.line(panel, (0, i), (int(v), i), (90, 90, 90), 1)
    for cy in fit.rows:
        yy = int(round(cy)) - y
        if 0 <= yy < h:
            cv2.line(panel, (0, yy), (318, yy), RED, 1)
    return panel


def draw_report(image: np.ndarray, fit, decisions: list[Decision] | None = None,
                labels: list[str] | None = None) -> np.ndarray:
    """Single-image diagnostic covering every stage of the read.

    Panels, left to right: the deskewed input with the detected grid box and
    anchors; the fitted ROIs coloured by verdict; and a legend carrying the
    lattice parameters, the verdict tally, and the questions needing review.

    One image rather than several because the failure modes are *relational*
    -- a lattice that is right in isolation can still be one row out relative
    to the print -- and those only show up when the evidence is side by side.
    """
    from .grid import deskew

    base = image.copy() if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    base = deskew(base, fit.skew)
    h, w = base.shape[:2]

    stage1 = base.copy()
    x, y, bw, bh = fit.box
    cv2.rectangle(stage1, (x, y), (x + bw, y + bh), BLUE, 3)
    for cx in (c for b in fit.blocks for c in b):
        cv2.line(stage1, (int(cx), y), (int(cx), y + bh), (200, 200, 0), 1)
    for cy in fit.rows:
        cv2.line(stage1, (x, int(cy)), (x + bw, int(cy)), (0, 200, 200), 1)
    _banner(stage1, "1. registration: grid box + row/column anchors")

    stage2 = draw_grid(base, fit, decisions, label_rows=False)
    _banner(stage2, "2. ROIs, coloured by verdict")

    panel = np.full((h, max(360, w // 3), 3), 250, dtype=np.uint8)
    lines = [
        "3. summary",
        "",
        f"blocks     {len(fit.blocks)}",
        f"rows       {len(fit.rows)}",
        f"row pitch  {fit.row_pitch:.2f} px",
        f"col pitch  {fit.col_pitch:.2f} px",
        f"radius     {fit.radius:.2f} px",
        f"skew       {fit.skew:+.2f} deg",
        f"lattice    {fit.score:.2f}",
        "",
    ]
    if decisions:
        tally: dict[str, int] = {}
        for d in decisions:
            tally[d.status] = tally.get(d.status, 0) + 1
        lines.extend(f"{k:<15}{v}" for k, v in sorted(tally.items()))
        review = [i + 1 for i, d in enumerate(decisions) if d.needs_review]
        lines += ["", f"needs review: {len(review)}"]
        lines += ["  " + ", ".join(str(q) for q in review[i:i + 6])
                  for i in range(0, min(len(review), 36), 6)]
        lines += ["", "legend:", "  green  CONFIDENT", "  amber  LOW_CONFIDENCE",
                  "  red    MULTIPLE_MARK / INVALID", "  grey   BLANK"]
    for i, text in enumerate(lines):
        cv2.putText(panel, text, (14, 40 + i * 26), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (40, 40, 40), 1, cv2.LINE_AA)

    return np.hstack([stage1, stage2, panel])


def _banner(img: np.ndarray, text: str) -> None:
    cv2.rectangle(img, (0, 0), (img.shape[1], 46), (255, 255, 255), -1)
    cv2.putText(img, text, (14, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                (20, 20, 20), 2, cv2.LINE_AA)


# Grading colours for the review image.  Deliberately the same vocabulary a
# teacher already reads on a hand-marked paper: green right, red wrong, amber
# "look at this".
MARK_CORRECT = (60, 170, 60)
MARK_WRONG = (40, 40, 225)
MARK_EXPECTED = (150, 200, 60)
MARK_REVIEW = (0, 170, 255)


def draw_review(image: np.ndarray, fit, decisions: list[Decision],
                scored: list[dict] | None = None) -> np.ndarray:
    """The annotated sheet a teacher sees next to the score.

    Different from :func:`draw_grid`, which exists to debug *localisation* and
    therefore rings all ~800 ROIs including the blanks.  That is the right
    picture when the question is "did the lattice land correctly", and the
    wrong one here: a teacher checking a result needs the handful of bubbles
    that carry a decision to stand out, and a grid of grey rings over every
    unmarked bubble hides exactly those.

    So this draws only what was decided:

    * a thick ring on the bubble the student marked, green when it matches the
      key and red when it does not
    * a thin ring on the correct option whenever the student got it wrong, so
      the right answer is visible without cross-referencing the key
    * an amber ring on anything flagged for review, with the question number
      called out, since those are the ones where the printed score is not yet
      final

    *scored* is the per-question list from ``score.score_answers``; without it
    the marks are still ringed but nothing is judged right or wrong, which is
    the correct behaviour when no answer key exists.
    """
    from .grid import deskew

    out = image.copy() if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    out = deskew(out, fit.skew)

    by_q = {rec["q"]: rec for rec in (scored or [])}
    # Ring width scales with bubble size so the overlay reads the same on a
    # phone photo and on a 200 dpi scan.
    r = max(6, int(round(fit.radius)))
    thick = max(2, int(round(fit.radius * 0.22)))
    n_rows = len(fit.rows)

    for b_idx, block in enumerate(fit.blocks):
        for r_idx, cy in enumerate(fit.rows):
            flat = b_idx * n_rows + r_idx
            if flat >= len(decisions):
                continue
            d = decisions[flat]
            rec = by_q.get(flat + 1)
            status = (rec or {}).get("status")
            centre = (int(round(cy)))

            if d.choice is not None:
                cx = block[d.choice]
                if status == "correct":
                    colour = MARK_CORRECT
                elif status == "wrong":
                    colour = MARK_WRONG
                elif d.needs_review:
                    colour = MARK_REVIEW
                else:
                    colour = MARK_CORRECT if status is None else MARK_REVIEW
                cv2.circle(out, (int(round(cx)), centre), r + 3, colour,
                           thick, cv2.LINE_AA)

            # Show the expected answer only where the student actually
            # attempted the question and got it wrong.  Marking it on every
            # unattempted question too would ring all four blank subject
            # blocks on a partly-completed sheet -- 150 rings on the sample
            # capture -- burying the handful of real mistakes the teacher
            # opened the image to look at.
            expected = (rec or {}).get("correct")
            if expected and status == "wrong":
                labels = _block_labels(len(block))
                if expected in labels:
                    ex = block[labels.index(expected)]
                    # Dashed-looking double ring so it reads as "this is the
                    # answer" rather than "this is what was marked".
                    cv2.circle(out, (int(round(ex)), centre), r + 8,
                               MARK_EXPECTED, max(2, thick - 1), cv2.LINE_AA)

            if d.needs_review:
                cv2.putText(out, str(flat + 1),
                            (int(block[0]) - r - 46, centre + 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.52, MARK_REVIEW, 2,
                            cv2.LINE_AA)

    _draw_legend(out, decisions, bool(scored))
    return out


def _block_labels(n: int) -> list[str]:
    return [chr(ord("A") + i) for i in range(n)]


def _draw_legend(img: np.ndarray, decisions: list[Decision], scored: bool) -> None:
    """Key to the ring colours, drawn on the sheet itself.

    On the image rather than in the app's UI so the annotated file still
    explains itself when it is shared, printed, or attached to a dispute --
    which is most of what these images get used for.
    """
    review = sum(1 for d in decisions if d.needs_review)
    rows = ([("marked correct", MARK_CORRECT), ("marked wrong", MARK_WRONG),
             ("correct answer", MARK_EXPECTED)] if scored
            else [("mark detected", MARK_CORRECT)])
    rows.append((f"needs review ({review})", MARK_REVIEW))

    pad, line_h = 16, 34
    w = 330
    h = pad * 2 + line_h * len(rows)
    x0, y0 = 12, 12
    panel = img[y0:y0 + h, x0:x0 + w]
    if panel.size:
        img[y0:y0 + h, x0:x0 + w] = cv2.addWeighted(
            panel, 0.25, np.full_like(panel, 255), 0.75, 0)
    cv2.rectangle(img, (x0, y0), (x0 + w, y0 + h), (120, 120, 120), 1)
    for i, (label, colour) in enumerate(rows):
        cy = y0 + pad + line_h * i + 12
        cv2.circle(img, (x0 + pad + 12, cy), 11, colour, 3, cv2.LINE_AA)
        cv2.putText(img, label, (x0 + pad + 34, cy + 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.58, (30, 30, 30), 1, cv2.LINE_AA)
