"""Reproduce every accuracy number this package claims.

    python benchmark.py

Reports, for the real capture and for synthesised distortions of it:

  * ROI localisation precision and recall, measured against bubble positions
    found independently of the fitter under test
  * filled / empty classification accuracy
  * end-to-end answer accuracy against hand-read ground truth
  * processing time

and, for each blank master form, whether the declared layout is recovered.

Written as a script rather than a test because its output is a table a human
reads when deciding whether a change helped; the pass/fail thresholds live in
tests/ instead.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import cv2
import numpy as np

from omr_mcq import layout, read_sheet
from omr_mcq.grid import bubble_blobs, deskew
from omr_mcq.reader import SheetUnreadable, load_image, normalise

ROOT = Path(__file__).parent
SAMPLE = ROOT / "samples" / "neet_marked_sheet.jpg"
BLANKS = ROOT / "samples" / "blanks"
TRUTH = ROOT / "tests" / "ground_truth.json"


def expected_answers() -> dict:
    data = json.loads(TRUTH.read_text())["eval_0f9157047bb5_original.jpg"]["answers"]
    return {int(q): ("ABCD"[v - 1] if v else None) for q, v in data.items()}


def reference_bubbles(gray: np.ndarray, box) -> np.ndarray:
    """Bubble centres measured independently of the fitter under test.

    Precision and recall are meaningless if both sides of the comparison come
    from the code being measured.  This is a plain connected-component pass
    with a generous size filter: a weak detector on its own, since it misses
    merged and broken bubbles, but unbiased with respect to the lattice.
    """
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 31, 8)
    count, _labels, stats, centroids = cv2.connectedComponentsWithStats(binary, 8)
    if count <= 1:
        return np.empty((0, 2))
    widths = stats[1:, cv2.CC_STAT_WIDTH].astype(float)
    heights = stats[1:, cv2.CC_STAT_HEIGHT].astype(float)
    centres = centroids[1:]
    x, y, w, h = box
    keep = ((widths > 10) & (widths < 60) & (heights > 10) & (heights < 60)
            & (np.abs(widths - heights) < 8)
            & (centres[:, 0] >= x) & (centres[:, 0] <= x + w)
            & (centres[:, 1] >= y) & (centres[:, 1] <= y + h))
    return centres[keep]


def roi_precision_recall(fit, reference: np.ndarray) -> tuple[float, float]:
    """How well the fitted ROIs cover independently measured bubbles.

    A fitted ROI counts as matched when a reference bubble lies within half a
    radius of its centre, i.e. the ROI samples that bubble and not a neighbour.
    """
    if reference.size == 0 or not fit.blocks:
        return 0.0, 0.0
    predicted = np.array([[cx, cy] for b in fit.blocks for cy in fit.rows for cx in b])
    tolerance = max(3.0, fit.radius * 0.5)
    distance = np.linalg.norm(predicted[:, None, :] - reference[None, :, :], axis=2)
    return (float(np.mean(distance.min(axis=1) <= tolerance)),
            float(np.mean(distance.min(axis=0) <= tolerance)))


def classification_stats(result) -> dict:
    """Filled-vs-empty accuracy over every sampled ROI, not just the answers."""
    want = expected_answers()
    tp = tn = fp = fn = 0
    by_q = {q.q: q for q in result.questions}
    for question, option in want.items():
        read = by_q[question]
        for index, label in enumerate(result.layout.options):
            should_be_filled = (option == label)
            is_filled = (read.marked == label)
            if should_be_filled and is_filled:
                tp += 1
            elif should_be_filled:
                fn += 1
            elif is_filled:
                fp += 1
            else:
                tn += 1
    total = tp + tn + fp + fn or 1
    return {"accuracy": (tp + tn) / total, "tp": tp, "tn": tn, "fp": fp, "fn": fn}


def distortions(img: np.ndarray) -> dict:
    """The distortions a phone capture actually introduces."""
    h, w = img.shape[:2]
    rng = np.random.default_rng(0)

    def rotate(degrees):
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), degrees, 1.0)
        return cv2.warpAffine(img, matrix, (w, h), borderValue=(235, 235, 235))

    ramp = np.linspace(0.65, 1.15, w, dtype=np.float32)[None, :, None]
    return {
        "clean": img,
        "rotate -2.5": rotate(-2.5), "rotate -0.7": rotate(-0.7),
        "rotate +0.8": rotate(0.8), "rotate +2.5": rotate(2.5),
        "blur 3x3": cv2.GaussianBlur(img, (3, 3), 0),
        "blur 5x5": cv2.GaussianBlur(img, (5, 5), 0),
        "dark x0.75": np.clip(img.astype(np.float32) * 0.75, 0, 255).astype(np.uint8),
        "bright x1.25": np.clip(img.astype(np.float32) * 1.25, 0, 255).astype(np.uint8),
        "light ramp": np.clip(img.astype(np.float32) * ramp, 0, 255).astype(np.uint8),
        "noise sigma 8": np.clip(img.astype(np.int16)
                                 + rng.normal(0, 8, img.shape).astype(np.int16),
                                 0, 255).astype(np.uint8),
    }


def main() -> int:
    if not SAMPLE.exists():
        print(f"sample capture missing: {SAMPLE}")
        return 1

    want = expected_answers()
    img = normalise(load_image(SAMPLE))
    failures = 0

    start = time.time()
    result = read_sheet(img, layout.NEET,
                        answer_key={q: o for q, o in want.items() if o})
    elapsed = (time.time() - start) * 1000

    hits = sum(1 for q, option in want.items() if result.answers[q] == option)
    grid = result.grid
    gray = deskew(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), result._fit.skew)
    reference = reference_bubbles(gray, result._fit.box)
    precision, recall = roi_precision_recall(result._fit, reference)
    cls = classification_stats(result)

    print("=" * 72)
    print(f"ACCURACY  {SAMPLE.name}  ({len(want)} hand-read questions)")
    print("=" * 72)
    print(f"  answers        {hits}/{len(want)}  ({hits / len(want):.1%})")
    print(f"  classification {cls['accuracy']:.2%}  "
          f"tp={cls['tp']} tn={cls['tn']} fp={cls['fp']} fn={cls['fn']}")
    print(f"  ROI precision  {precision:.1%}   recall {recall:.1%}   "
          f"(vs {len(reference)} independently measured bubbles)")
    print(f"  lattice        {grid['blocks']} blocks x {grid['rows']} rows, "
          f"pitch {grid['row_pitch']}/{grid['col_pitch']}, r={grid['radius']}, "
          f"skew {grid['skew_deg']:+}deg, fit {grid['fit_score']}")
    print(f"  score          {result.total} / {result.score.max_score}   "
          f"{elapsed:.0f} ms")
    failures += hits != len(want)

    print()
    print("ROBUSTNESS  (same sheet, synthesised capture distortions)")
    print("-" * 72)
    print(f"{'condition':<16}{'rows':>6}{'ROI prec':>10}{'recall':>9}"
          f"{'answers':>10}{'ms':>8}")
    for name, variant in distortions(img).items():
        start = time.time()
        try:
            got = read_sheet(variant, layout.NEET)
        except SheetUnreadable as exc:
            print(f"{name:<16}{'-':>6}{'-':>10}{'-':>9}{exc.reason:>10}")
            failures += 1
            continue
        ms = (time.time() - start) * 1000
        correct = sum(1 for q, option in want.items() if got.answers[q] == option)
        vgray = deskew(cv2.cvtColor(variant, cv2.COLOR_BGR2GRAY), got._fit.skew)
        p, r = roi_precision_recall(got._fit, reference_bubbles(vgray, got._fit.box))
        flag = "" if correct == len(want) else "   <-- "
        failures += correct != len(want)
        print(f"{name:<16}{got.grid['rows']:>6}{p:>9.1%}{r:>9.1%}"
              f"{correct:>7}/{len(want)}{ms:>8.0f}{flag}")

    second = ROOT / "samples" / "neet_marked_sheet_b.jpg"
    if second.exists():
        print()
        print("SECOND REAL CAPTURE  (same sheet, independently re-encoded)")
        print("-" * 72)
        start = time.time()
        got = read_sheet(second, layout.NEET)
        ms = (time.time() - start) * 1000
        correct = sum(1 for q, option in want.items() if got.answers[q] == option)
        failures += correct != len(want)
        print(f"  {second.name}  rows {got.grid['rows']}  "
              f"answers {correct}/{len(want)}  {ms:.0f} ms")

    if BLANKS.is_dir():
        print()
        print("LAYOUT GENERALISATION  (blank master forms)")
        print("-" * 72)
        cases = [("neet_blank.png", layout.NEET), ("jee_blank.png", layout.JEE),
                 ("gujcet_blank.png", layout.GUJCET), ("hsc_blank.png", layout.HSC)]
        for filename, sheet_layout in cases:
            path = BLANKS / filename
            if not path.exists():
                continue
            start = time.time()
            try:
                got = read_sheet(path, sheet_layout)
            except SheetUnreadable as exc:
                print(f"  {sheet_layout.name:<8} FAILED: {exc.reason}")
                failures += 1
                continue
            ms = (time.time() - start) * 1000
            false_marks = sum(1 for q in got.questions if q.marked)
            ok = (got.grid["blocks"] == sheet_layout.blocks
                  and got.grid["rows"] == sheet_layout.rows_per_block
                  and false_marks == 0)
            failures += not ok
            print(f"  {sheet_layout.name:<8} blocks {got.grid['blocks']}/"
                  f"{sheet_layout.blocks}  rows {got.grid['rows']:>3}/"
                  f"{sheet_layout.rows_per_block}  false marks {false_marks}"
                  f"  {ms:>5.0f}ms  {'ok' if ok else '<-- MISMATCH'}")

    media = ROOT.parent / "backend" / "media"
    if media.is_dir():
        import hashlib

        from omr_mcq import detect_layout

        print()
        print("LAYOUT DETECTION  (every distinct full-resolution capture)")
        print("-" * 72)
        distinct = {}
        for path in sorted(media.glob("*_original.jpg")):
            img = cv2.imread(str(path))
            if img is None or img.shape[1] < 1000:
                continue
            digest = hashlib.md5(path.read_bytes()).hexdigest()[:10]
            distinct.setdefault(digest, path)
        tally, refusals = {}, {}
        for digest, path in sorted(distinct.items()):
            try:
                detected, got = detect_layout(path)
                tally.setdefault(detected.name, []).append(got.answered)
            except SheetUnreadable as exc:
                refusals[exc.reason] = refusals.get(exc.reason, 0) + 1
        for name, answered in sorted(tally.items()):
            print(f"  {name:<8} {len(answered):>2} sheets   "
                  f"answered {sorted(answered)}")
        print(f"  refused  {sum(refusals.values()):>2} sheets   {refusals}")
        print(f"  of {len(distinct)} distinct captures; none silently misread")

    print()
    print(f"failures: {failures}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
