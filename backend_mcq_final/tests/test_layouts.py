"""Layout generalisation.

The reader's central claim is that it measures geometry from the sheet rather
than from a coordinate file, so one code path reads several different forms.
These tests hold that claim to the blank master forms: each must fit with
exactly the block and row counts its layout declares.

They also guard the other half of the claim -- that a *blank* form reads as
blank.  A fit that is one row out typically lands on a block header and reads
its text as a mark, which is how a silent off-by-one shows up in practice.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from omr_mcq import layout, read_sheet

BLANKS = Path(__file__).parent.parent / "samples" / "blanks"

CASES = [
    ("neet_blank.png", layout.NEET),
    ("jee_blank.png", layout.JEE),
    ("gujcet_blank.png", layout.GUJCET),
    ("hsc_blank.png", layout.HSC),
]

pytestmark = pytest.mark.skipif(not BLANKS.is_dir(),
                                reason="blank master renders not present")


@pytest.mark.parametrize("filename,sheet_layout",
                         CASES, ids=[c[1].name for c in CASES])
def test_blank_master_fits_its_declared_layout(filename: str, sheet_layout):
    path = BLANKS / filename
    if not path.exists():
        pytest.skip(f"{filename} not present")
    result = read_sheet(path, sheet_layout)
    assert result.grid["blocks"] == sheet_layout.blocks
    assert result.grid["rows"] == sheet_layout.rows_per_block


@pytest.mark.parametrize("filename,sheet_layout",
                         CASES, ids=[c[1].name for c in CASES])
def test_blank_master_reads_as_blank(filename: str, sheet_layout):
    """No bubble on an unmarked form may read as filled.

    A single false positive here means the lattice has drifted onto printed
    furniture -- a block header or a section banner -- and every question after
    it is renumbered.
    """
    path = BLANKS / filename
    if not path.exists():
        pytest.skip(f"{filename} not present")
    result = read_sheet(path, sheet_layout)
    marked = [q.q for q in result.questions if q.marked]
    assert marked == [], f"{sheet_layout.name}: {len(marked)} false positives"


def test_row_pitch_is_uniform_across_the_grid():
    """An even pitch is the signature of a correctly-placed lattice."""
    import numpy as np

    path = BLANKS / "gujcet_blank.png"
    if not path.exists():
        pytest.skip("gujcet blank not present")
    result = read_sheet(path, layout.GUJCET)
    gaps = np.diff(result._fit.rows)
    assert gaps.std() < result.grid["row_pitch"] * 0.1


# --- Layout validation ------------------------------------------------------

def test_subject_names_must_match_the_block_count():
    with pytest.raises(ValueError):
        layout.Layout(name="bad", blocks=3, rows_per_block=10,
                      subjects=("only", "two"))


def test_questions_are_numbered_block_by_block():
    assert layout.NEET.subject_of(1) == "Physics"
    assert layout.NEET.subject_of(50) == "Physics"
    assert layout.NEET.subject_of(51) == "Chemistry"
    assert layout.NEET.subject_of(200) == "Zoology"


def test_layouts_are_looked_up_case_insensitively():
    assert layout.get("NEET") is layout.NEET
    assert layout.get(" neet ") is layout.NEET
    with pytest.raises(KeyError):
        layout.get("no-such-sheet")


# --- Refusing the wrong layout ----------------------------------------------

def test_wrong_layout_is_refused_not_misread():
    """A sheet read against the wrong layout must raise, never return answers.

    This is the silent-misread case: an HSC form fits 10 rows of the 50 a NEET
    layout expects, and before the row-count guard the reader returned those
    10 rows as questions 1-10 of a 200-question paper.  Every answer after the
    first missing row is then attributed to the wrong question while the call
    reports success.
    """
    from omr_mcq import SheetUnreadable, read_sheet

    path = BLANKS / "hsc_blank.png"
    if not path.exists():
        pytest.skip("hsc blank not present")
    with pytest.raises(SheetUnreadable) as exc:
        read_sheet(path, layout.NEET)
    assert exc.value.reason in ("row_count_mismatch", "incomplete_grid")


@pytest.mark.parametrize("filename,sheet_layout",
                         CASES, ids=[c[1].name for c in CASES])
def test_layout_is_detected_automatically(filename: str, sheet_layout):
    """Each blank master must be identified as exactly its own layout.

    The guards are only useful if they are selective enough to tell the four
    forms apart; if several layouts accepted the same sheet, auto-detection
    would be a coin flip.
    """
    from omr_mcq import detect_layout

    path = BLANKS / filename
    if not path.exists():
        pytest.skip(f"{filename} not present")
    detected, _result = detect_layout(path)
    assert detected.name == sheet_layout.name


def test_detection_refuses_rather_than_guessing():
    """An image no layout fits must raise, not return a best guess.

    Grading against the wrong layout renumbers every answer, so a guess here
    is worse than no answer at all.
    """
    import numpy as np

    from omr_mcq import SheetUnreadable, detect_layout

    noise = np.random.default_rng(2).integers(0, 255, (1400, 1000, 3), dtype=np.uint8)
    with pytest.raises(SheetUnreadable):
        detect_layout(noise)


# --- Guards against reading the wrong sheet ---------------------------------
# Each of these was a real misdetection found by sweeping 31 captures: the
# reader returned a confident answer set for the wrong layout, which renumbers
# every question. All four now refuse instead.

def _media(name: str):
    path = BLANKS.parent.parent.parent / "backend" / "media" / f"{name}_original.jpg"
    if not path.exists():
        pytest.skip(f"{name} not in backend/media")
    return path


@pytest.mark.parametrize("name,expected", [
    ("analyze_1ab7d65839b9", "NEET"),
    ("eval_0f9157047bb5", "NEET"),
    ("analyze_32c765b82f6e", "HSC"),
    ("analyze_c45cf5603495", "GUJCET"),
])
def test_real_captures_detect_their_own_layout(name: str, expected: str):
    from omr_mcq import detect_layout

    detected, _result = detect_layout(_media(name))
    assert detected.name == expected


@pytest.mark.parametrize("name,reason", [
    # Zoology column cropped at the frame edge; fitted the 3-block GUJCET
    # layout and read three subjects as the whole paper.
    ("eval_4fd5d84896d9", "grid_touches_frame"),
    # Photographed small in frame, so one block was missed between two others;
    # strides of 261 and 128 px against a uniform printed stride.
    ("eval_279b0c34c83d", "irregular_block_spacing"),
    # Lower rows out of frame: 38 rows found where NEET declares 50.
    ("analyze_0641bc268b7e", "row_count_mismatch"),
])
def test_cropped_captures_are_refused_with_a_specific_reason(name: str, reason: str):
    """Each guard must fire for its own cause, so the hint is actionable."""
    from omr_mcq import SheetUnreadable, layout as layout_mod, read_sheet

    with pytest.raises(SheetUnreadable) as exc:
        read_sheet(_media(name), layout_mod.NEET)
    assert exc.value.reason == reason


@pytest.mark.parametrize("name", [
    "eval_4fd5d84896d9", "eval_279b0c34c83d", "analyze_0641bc268b7e",
])
def test_no_layout_accepts_a_cropped_capture(name: str):
    """Refusing under one layout is not enough; none may accept it."""
    from omr_mcq import SheetUnreadable, detect_layout

    with pytest.raises(SheetUnreadable):
        detect_layout(_media(name))
