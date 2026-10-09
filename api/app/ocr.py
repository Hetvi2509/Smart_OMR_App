"""Candidate-identity extraction with PaddleOCR.

The OMR engine deliberately reads only the answer table ("Roll numbers are not
read" -- backend_mcq_final/README.md), so candidate identity comes from here.

Two rules shape this module:

* **The model loads lazily and only once.**  Importing paddle costs seconds and
  the first call downloads weights; doing that at boot would make the service
  look hung on startup.
* **OCR failure is never fatal.**  A sheet that scored correctly must still be
  saved when the header could not be read.  Every failure path returns empty
  fields plus a note, and the operator types the details in -- which the UI
  already supports, because every field is editable before the report.
"""
from __future__ import annotations

import logging
import os
import re
import threading

import numpy as np

from . import config

logger = logging.getLogger(__name__)

_engine = None
_engine_lock = threading.Lock()
_load_failed: str | None = None

# Label -> field.  Matched against the OCR text with the separators and casing
# stripped, so "Roll No.", "ROLL NO :" and "rollno" all land on the same field.
_LABELS: list[tuple[str, tuple[str, ...]]] = [
    ("roll_no", ("rollno", "rollnumber", "roll")),
    ("registration_no", ("registrationno", "registration", "regno",
                         "enrollmentno", "enrollment")),
    ("student_name", ("studentname", "candidatename", "name")),
    ("class_std", ("class", "standard", "std", "grade")),
    ("section", ("section", "sec", "div", "division")),
]

_ALL_ALIASES = {alias for _, aliases in _LABELS for alias in aliases}


def _ocr_threads() -> int:
    """How many cores the OCR pass may use: about half, and never all of them."""
    cores = os.cpu_count() or 2
    return max(1, min(4, cores // 2))


def available() -> bool:
    return config.ENABLE_OCR and _load_failed is None


def _load():
    """Import and construct the PaddleOCR engine, once, under a lock."""
    global _engine, _load_failed
    if _engine is not None or _load_failed is not None:
        return _engine
    with _engine_lock:
        if _engine is not None or _load_failed is not None:
            return _engine
        try:
            # paddlepaddle 3.x on Windows crashes inside its oneDNN kernel
            # ("ConvertPirAttribute2RuntimeAttribute not support") on the OCR
            # recognition graph.  These two flags must be set before paddle is
            # imported, and they are what makes inference work here at all.
            os.environ.setdefault("FLAGS_use_mkldnn", "0")
            os.environ.setdefault("FLAGS_enable_pir_api", "0")

            # Leave cores for the request path. Unthrottled, paddle takes every
            # core and starves the bubble reading that callers are waiting on:
            # a sheet that reads in 1.7s idle took 25s alongside an OCR pass.
            # OCR is background work, so it yields.
            os.environ.setdefault("OMP_NUM_THREADS", str(_ocr_threads()))

            from paddleocr import PaddleOCR
            logger.info("Loading PaddleOCR (first call downloads weights)...")
            # Angle classification off: sheet headers are horizontal, and it
            # roughly doubles load time for no gain here.
            kwargs = {"use_textline_orientation": False, "lang": "en"}
            try:
                _engine = PaddleOCR(enable_mkldnn=False,
                                    cpu_threads=_ocr_threads(), **kwargs)
            except TypeError:
                # Older/newer builds without that keyword; the FLAGS above
                # still apply.
                _engine = PaddleOCR(**kwargs)
            logger.info("PaddleOCR ready.")
        except Exception as exc:                      # noqa: BLE001
            # Covers the import, the weight download and the model init.  All
            # three mean the same thing to a caller: no OCR this run.
            _load_failed = f"{type(exc).__name__}: {exc}"
            logger.warning("PaddleOCR unavailable, continuing without it: %s",
                           _load_failed)
    return _engine


def _lines(image: np.ndarray) -> list[dict]:
    """Run the engine and flatten its output to [{text, confidence}].

    PaddleOCR's return shape differs between 2.x and 3.x, so both are handled;
    an unrecognised shape yields no lines rather than an exception.
    """
    engine = _load()
    if engine is None:
        return []
    try:
        raw = engine.predict(image) if hasattr(engine, "predict") \
            else engine.ocr(image)
    except Exception as exc:                          # noqa: BLE001
        logger.warning("OCR inference failed: %s", exc)
        return []

    out: list[dict] = []
    for page in (raw or []):
        # 3.x: a dict of parallel lists.
        if isinstance(page, dict):
            texts = page.get("rec_texts") or []
            scores = page.get("rec_scores") or []
            polys = page.get("rec_polys") or page.get("dt_polys") or []
            for i, text in enumerate(texts):
                score = scores[i] if i < len(scores) else 0.0
                out.append({"text": str(text), "confidence": float(score),
                            "box": _box(polys[i] if i < len(polys) else None)})
            continue
        # 2.x: [[box, (text, score)], ...]
        for entry in (page or []):
            try:
                text, score = entry[1][0], entry[1][1]
                out.append({"text": str(text), "confidence": float(score),
                            "box": _box(entry[0])})
            except (IndexError, TypeError, ValueError):
                continue
    return out


def _box(poly) -> list[float] | None:
    """Reduce a detection polygon to [x0, y0, x1, y1]."""
    if poly is None:
        return None
    try:
        pts = np.asarray(poly, dtype=float).reshape(-1, 2)
        return [float(pts[:, 0].min()), float(pts[:, 1].min()),
                float(pts[:, 0].max()), float(pts[:, 1].max())]
    except (ValueError, TypeError):
        return None


def _norm_label(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _split_label(text: str) -> tuple[str, str] | None:
    """Split "Roll No: 12345" into its field and value, if it is such a line."""
    for sep in (":", "-", "–"):
        if sep not in text:
            continue
        label, _, value = text.partition(sep)
        key = _norm_label(label)
        for field, aliases in _LABELS:
            if not (key in aliases or any(key.endswith(a) for a in aliases)):
                continue
            # "SECTION - A" is the answer grid's own band rule, printed on
            # every sheet, not a section the student wrote. A dash-joined
            # section is therefore never taken as a value; a real filled field
            # on these forms is written with a colon ("Section: B").
            if field == "section" and sep != ":":
                return None
            return field, value.strip()
    return None


def _value_beside(label: dict, lines: list[dict]) -> str | None:
    """The text written to the right of *label*, on the same printed line.

    Returns None when the label's value box is blank -- the common case on a
    sheet whose header was never filled in. An empty field the operator then
    types is far better than a confident wrong one taken from elsewhere on the
    page, because a wrong roll number attaches a result to the wrong student.
    """
    box = label.get("box")
    if not box:
        return None
    x0, y0, x1, y1 = box
    height = max(1.0, y1 - y0)
    centre = (y0 + y1) / 2

    best: tuple[float, str] | None = None
    for other in lines:
        if other is label:
            continue
        obox = other.get("box")
        if not obox:
            continue
        ox0, oy0, ox1, oy1 = obox
        # Same line: centres within half a line height of each other.
        if abs((oy0 + oy1) / 2 - centre) > height * 0.6:
            continue
        # To the right, and not so far that it belongs to another column.
        gap = ox0 - x1
        if gap < 0 or gap > height * 12:
            continue
        text = other["text"].strip()
        # Another label is a neighbouring field, not this one's value.
        if not text or _norm_label(text) in _ALL_ALIASES or _split_label(text):
            continue
        if best is None or gap < best[0]:
            best = (gap, text)
    return best[1] if best else None


def extract_candidate(image: np.ndarray, header_fraction: float = 0.3) -> dict:
    """Read candidate fields from the top *header_fraction* of the sheet.

    Cropping to the header keeps the answer grid's 200 bubbles out of the OCR
    input: they contribute nothing but noise and a lot of runtime.
    """
    result = {f: None for f, _ in _LABELS}
    result.update(raw_lines=[], confidence=None, engine=None, note=None)

    if not config.ENABLE_OCR:
        result["note"] = "OCR disabled on the server (ENABLE_OCR=0)."
        return result

    h = image.shape[0]
    crop = image[: max(1, int(h * header_fraction))]
    lines = _lines(crop)

    if not lines:
        result["note"] = (f"OCR unavailable: {_load_failed}" if _load_failed
                          else "No text found in the sheet header.")
        return result

    result["engine"] = "paddleocr"
    result["raw_lines"] = lines

    # Pass 1: "Label: value" on one line.
    for line in lines:
        hit = _split_label(line["text"])
        if hit and hit[1] and result.get(hit[0]) is None:
            result[hit[0]] = hit[1]

    # Pass 2: a bare label with its value written beside it, which is how a
    # boxed header prints ("STUDENT NAME | Rahul Verma").
    #
    # Position decides this, not reading order. Taking "the next line" instead
    # reads whatever the detector happened to emit next -- on a real sheet that
    # is a column heading from the answer grid below, which produced confident
    # nonsense like roll_no="CLASS". A value must sit on the label's own line
    # and to its right, or the field is left empty for a human to fill in.
    for line in lines:
        key = _norm_label(line["text"])
        for field, aliases in _LABELS:
            if result.get(field) is not None or key not in aliases:
                continue
            value = _value_beside(line, lines)
            if value:
                result[field] = value

    # Deliberately no "longest digit run" fallback for the roll number. The
    # header crop overlaps the top of the answer grid, whose printed question
    # numbers (151, 152, ...) are exactly such runs, so that guess attaches a
    # result to a student who does not exist. An empty roll number is visible
    # in the UI and gets typed in; a plausible wrong one does not.

    scores = [l["confidence"] for l in lines if l["confidence"]]
    result["confidence"] = round(sum(scores) / len(scores), 3) if scores else None
    if not any(result[f] for f, _ in _LABELS):
        result["note"] = "Header text was read but no candidate fields matched."
    return result
