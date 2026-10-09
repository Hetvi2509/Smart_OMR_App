"""Accuracy and robustness checks for the reader.

The single most important property is that the lattice lands on the printed
bubbles, because every number downstream depends on it and a lattice that is
off by one row produces confidently *wrong* answers rather than an obvious
error.  These tests therefore assert on the fit itself as well as on the
answers read from it, and exercise the distortions a phone capture actually
introduces.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from omr_mcq import SheetUnreadable, layout, read_sheet
from omr_mcq.reader import load_image, normalise

HERE = Path(__file__).parent
ROOT = HERE.parent
SAMPLE = ROOT / "samples" / "neet_marked_sheet.jpg"
CROPPED = ROOT / "samples" / "neet_cropped_reject.jpg"

pytestmark = pytest.mark.skipif(not SAMPLE.exists(),
                                reason="sample capture not present")


def truth() -> dict:
    data = json.loads((HERE / "ground_truth.json").read_text())
    return data["eval_0f9157047bb5_original.jpg"]["answers"]


def expected_answers() -> dict:
    """Ground truth as option labels, keyed by question number."""
    return {int(q): ("ABCD"[v - 1] if v else None) for q, v in truth().items()}


def image() -> np.ndarray:
    return normalise(load_image(SAMPLE))


def accuracy(result) -> float:
    want = expected_answers()
    hits = sum(1 for q, option in want.items() if result.answers[q] == option)
    return hits / len(want)


# --- Core accuracy ----------------------------------------------------------

def test_reads_every_answer_on_the_real_capture():
    """The whole point: the answers must match what a human reads off the sheet."""
    result = read_sheet(SAMPLE, layout.NEET)
    assert accuracy(result) == 1.0
    assert result.answered == 39


def test_lattice_matches_the_printed_grid():
    result = read_sheet(SAMPLE, layout.NEET)
    grid = result.grid
    assert grid["blocks"] == 4
    assert grid["rows"] == 50
    # Measured on this capture at the 1600px working width.
    assert 28 <= grid["row_pitch"] <= 32
    assert 32 <= grid["col_pitch"] <= 38
    assert 10 <= grid["radius"] <= 16
    assert grid["fit_score"] >= 0.9


def test_nothing_is_confidently_wrong():
    """A wrong answer reported as confident is the worst failure mode.

    Anything the reader cannot resolve must surface for review, never as a
    silently wrong CONFIDENT read.
    """
    result = read_sheet(SAMPLE, layout.NEET)
    want = expected_answers()
    by_q = {question.q: question for question in result.questions}
    for q, option in want.items():
        if result.answers[q] != option:
            assert by_q[q].needs_review, f"Q{q} wrong but not flagged"


# --- Robustness -------------------------------------------------------------

def _rotate(img: np.ndarray, degrees: float) -> np.ndarray:
    h, w = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), degrees, 1.0)
    return cv2.warpAffine(img, matrix, (w, h), borderValue=(235, 235, 235))


@pytest.mark.parametrize("degrees", [-2.5, -0.7, 0.8, 2.5])
def test_survives_rotation(degrees: float):
    """Phone captures are never perfectly square to the page."""
    result = read_sheet(_rotate(image(), degrees), layout.NEET)
    assert result.grid["rows"] == 50
    assert accuracy(result) == 1.0


@pytest.mark.parametrize("ksize", [3, 5])
def test_survives_blur(ksize: int):
    """Soft focus must not move the lattice or lose a row."""
    result = read_sheet(cv2.GaussianBlur(image(), (ksize, ksize), 0), layout.NEET)
    assert result.grid["rows"] == 50
    assert accuracy(result) == 1.0


@pytest.mark.parametrize("gain", [0.75, 1.25])
def test_survives_exposure(gain: float):
    """Under- and over-exposure must not change the reading.

    This is the payoff from estimating paper level locally and deciding
    relatively: a global multiplier scales marks and paper together, so the
    per-question comparison is unaffected.
    """
    scaled = np.clip(image().astype(np.float32) * gain, 0, 255).astype(np.uint8)
    assert accuracy(read_sheet(scaled, layout.NEET)) == 1.0


def test_survives_uneven_illumination():
    """One side lit, the other shadowed -- the classic failure of any single
    global threshold."""
    img = image().astype(np.float32)
    ramp = np.linspace(0.65, 1.15, img.shape[1], dtype=np.float32)[None, :, None]
    lit = np.clip(img * ramp, 0, 255).astype(np.uint8)
    assert accuracy(read_sheet(lit, layout.NEET)) == 1.0


def test_survives_noise():
    rng = np.random.default_rng(0)
    img = image().astype(np.int16)
    noisy = np.clip(img + rng.normal(0, 8, img.shape).astype(np.int16),
                    0, 255).astype(np.uint8)
    assert accuracy(read_sheet(noisy, layout.NEET)) == 1.0


# --- Refusing rather than guessing ------------------------------------------

@pytest.mark.skipif(not CROPPED.exists(), reason="cropped sample not present")
def test_refuses_a_sheet_with_columns_out_of_frame():
    """A capture missing part of the grid must be refused, not guessed.

    Returning a partial read that looks complete is the most damaging thing
    this package could do: it yields confident marks for questions nobody
    actually checked.
    """
    with pytest.raises(SheetUnreadable) as exc:
        read_sheet(CROPPED, layout.NEET)
    # Any of the localisation guards may fire first depending on how the
    # frame is cropped; what matters is that it refuses with a usable hint.
    assert exc.value.reason in ("grid_not_found", "incomplete_grid",
                                "grid_touches_frame", "row_count_mismatch",
                                "irregular_block_spacing")
    assert exc.value.hint


def test_refuses_an_image_with_no_sheet_in_it():
    noise = np.random.default_rng(1).integers(0, 255, (900, 700, 3), dtype=np.uint8)
    with pytest.raises(SheetUnreadable):
        read_sheet(noise, layout.NEET)


def test_refuses_an_unreadable_file():
    with pytest.raises(SheetUnreadable):
        read_sheet(HERE / "ground_truth.json", layout.NEET)


# --- Scoring integration ----------------------------------------------------

def test_scores_against_an_answer_key():
    key = {q: option for q, option in expected_answers().items() if option}
    result = read_sheet(SAMPLE, layout.NEET, answer_key=key)
    assert result.score.correct == 39
    assert result.score.wrong == 0
    assert result.total == result.score.max_score


def test_reads_without_an_answer_key():
    """Reading a new form before any key exists must work."""
    result = read_sheet(SAMPLE, layout.NEET)
    assert result.score is None
    assert result.total is None
    assert result.answered == 39


def test_result_serialises_to_json():
    key = {q: option for q, option in expected_answers().items() if option}
    payload = read_sheet(SAMPLE, layout.NEET, answer_key=key).as_dict()
    json.dumps(payload)  # must not raise
    assert payload["layout"] == "NEET"
    assert len(payload["questions"]) == 200


# --- Second real capture ----------------------------------------------------

SAMPLE_B = ROOT / "samples" / "neet_marked_sheet_b.jpg"


@pytest.mark.skipif(not SAMPLE_B.exists(), reason="second capture not present")
def test_reads_a_second_real_capture_of_the_same_sheet():
    """Guards against an accuracy claim resting on one file's JPEG encoding.

    Same physical sheet, independently re-encoded, so the pixels differ while
    the answers do not.
    """
    result = read_sheet(SAMPLE_B, layout.NEET)
    assert result.grid["rows"] == 50
    assert result.grid["blocks"] == 4
    assert accuracy(result) == 1.0
    assert result.answered == 39


@pytest.mark.skipif(not SAMPLE_B.exists(), reason="second capture not present")
def test_low_resolution_capture_is_refused_rather_than_misread():
    """Below roughly 1000 px of sheet width a bubble is too small to read.

    Measured on this sheet: accuracy holds to 1000 px, slips at 900 px, and
    the signal is gone below that.  A reader that accepts such a frame returns
    confidently wrong marks -- the earlier pipeline scored 12/50 on a 720 px
    capture while reporting success -- so the fit is refused instead.
    """
    img = load_image(SAMPLE_B)
    h, w = img.shape[:2]
    tiny = cv2.resize(img, (720, int(h * 720 / w)), interpolation=cv2.INTER_AREA)
    with pytest.raises(SheetUnreadable):
        read_sheet(tiny, layout.NEET)
