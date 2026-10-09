"""Sheet layout: the little the reader needs to know about a form.

The reader measures geometry from the sheet itself, so a layout carries no
coordinates -- no bubble centres, no pitches, no margins, and no corner
markers.  It says only how the questions are *counted*: how many option
bubbles per question, how many question rows per subject block, how many
blocks, and what the options are called.

That is the whole contract, and it is why the same code reads the NEET, JEE,
GUJCET and HSC forms without a per-sheet calibration step.  A new form is four
numbers, not a coordinate file.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Layout:
    """How a sheet's questions are arranged.

    Parameters
    ----------
    name:
        Human label, used in reports and debug output.
    blocks:
        Number of column blocks across the answer grid.  On these forms one
        block is one subject.
    rows_per_block:
        Question rows within a block.
    options:
        Option labels in printed order.  Their *count* drives the geometry;
        the labels themselves only matter for reporting, so a sheet printed
        with 1/2/3/4 can still be reported as A/B/C/D if the answer key uses
        letters.
    subjects:
        Optional per-block subject names, for per-subject subtotals.  When
        omitted the blocks are reported as "Block 1", "Block 2", and so on.
    """

    name: str
    blocks: int
    rows_per_block: int
    options: tuple[str, ...] = ("A", "B", "C", "D")
    subjects: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        if self.blocks < 1:
            raise ValueError("blocks must be at least 1")
        if self.rows_per_block < 1:
            raise ValueError("rows_per_block must be at least 1")
        if len(self.options) < 2:
            raise ValueError("a question needs at least two options")
        if self.subjects and len(self.subjects) != self.blocks:
            raise ValueError(
                f"{self.name}: {len(self.subjects)} subject names for "
                f"{self.blocks} blocks")

    @property
    def total_questions(self) -> int:
        return self.blocks * self.rows_per_block

    def subject_of(self, question: int) -> str:
        """Subject for a 1-based question number.

        Questions are numbered block by block -- 1-50 in the first block,
        51-100 in the second -- which is how these forms print them and how
        the lattice enumerates them, so the two line up without a mapping.
        """
        index = (question - 1) // self.rows_per_block
        if self.subjects and 0 <= index < len(self.subjects):
            return self.subjects[index]
        return f"Block {index + 1}"


# Layouts measured from the institute's own blank master forms.  Verified by
# tests/test_layouts.py, which fits each one and checks the recovered block and
# row counts against these numbers.
NEET = Layout(
    name="NEET",
    blocks=4,
    rows_per_block=50,
    subjects=("Physics", "Chemistry", "Botany", "Zoology"),
)

JEE = Layout(
    name="JEE",
    blocks=3,
    rows_per_block=25,
    subjects=("Physics", "Chemistry", "Maths"),
)

GUJCET = Layout(
    name="GUJCET",
    blocks=3,
    rows_per_block=40,
    subjects=("Physics", "Chemistry", "Maths/Biology"),
)

HSC = Layout(
    name="HSC",
    blocks=5,
    rows_per_block=10,
)

LAYOUTS: dict[str, Layout] = {
    "neet": NEET,
    "jee": JEE,
    "gujcet": GUJCET,
    "hsc": HSC,
}


def get(name: str) -> Layout:
    """Look up a built-in layout by name, case-insensitively."""
    try:
        return LAYOUTS[name.strip().lower()]
    except KeyError:
        known = ", ".join(sorted(LAYOUTS))
        raise KeyError(f"unknown layout {name!r}; known layouts: {known}") from None
