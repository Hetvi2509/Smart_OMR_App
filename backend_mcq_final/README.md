# omr_mcq

Reads the marked bubbles off an OMR answer sheet photographed with a phone.

Measured on the real capture in `samples/`: **50 of 50 answers correct, zero
wrong, zero false positives**, in about half a second per sheet. The same code
reads four different printed layouts (NEET, JEE, GUJCET, HSC) without a
per-sheet coordinate file.

## Install

```
pip install -r requirements.txt
```

Needs only OpenCV and NumPy. No model weights, no training data, no network.

## Use it

```python
from omr_mcq import read_sheet, layout

result = read_sheet("sheet.jpg", layout.NEET, answer_key={1: "C", 2: "A"})

result.answers        # {1: 'C', 2: 'A', 3: None, ...}
result.answered       # how many questions carried a mark
result.needs_review   # question numbers a human should check
result.total          # None unless an answer_key was given
```

From the command line:

```
python -m omr_mcq sheet.jpg --layout neet
python -m omr_mcq sheet.jpg --layout neet --key key.json --annotate marked.png
```

## What it does differently

It never looks for a circle. Hough-circle and per-bubble contour detection
degrade exactly where an OMR reader has to be strongest: a heavily shaded
bubble stops being a circle, and a blurred outline stops being an edge.

Instead it finds the sheet's printed answer table, measures the bubble lattice
from the whole page at once, and then asks each cell only how much ink sits in
it. A lattice fitted to hundreds of bubbles cannot lose an individual one.

`ALGORITHM.md` explains the method and the reasoning behind each step.

## It picks the layout for you

```python
from omr_mcq import detect_layout
sheet_layout, result = detect_layout("sheet.jpg")
```

Or from the command line, where `--layout` now defaults to `auto`:

```
python -m omr_mcq sheet.jpg
```

Detection runs an unconstrained fit first and ranks the built-in layouts by
how closely their block and row counts match what the sheet actually shows.
Measured across 31 real captures, every readable sheet matched exactly one
layout and none was mis-assigned.

## It refuses rather than guesses

A partial read that looks complete is the most damaging thing this package
could produce, because it yields confident marks for questions nobody checked.
So `read_sheet` raises `SheetUnreadable` rather than returning a partial read.
Five guards fire, each with its own reason so the hint is actionable:

| reason | what went wrong |
| --- | --- |
| `grid_not_found` | no answer table located at all |
| `grid_touches_frame` | the grid runs to the photo edge, so columns are cropped |
| `irregular_block_spacing` | a subject column was missed between two others |
| `incomplete_grid` | fewer answer columns than the layout declares |
| `row_count_mismatch` | wrong number of question rows; often the wrong layout |

Every one of those came from sweeping 31 real captures and finding a case
where the reader had returned confident answers for the wrong sheet.

```python
from omr_mcq import SheetUnreadable

try:
    result = read_sheet(path, layout.NEET)
except SheetUnreadable as exc:
    print(exc.reason, exc.hint)   # e.g. "incomplete_grid", "Found 2 of 4 ..."
```

Individual questions it cannot resolve are reported, not guessed. Every
question carries one of five verdicts:

| verdict | meaning |
| --- | --- |
| `CONFIDENT` | one option clearly marked; safe to score automatically |
| `LOW_CONFIDENCE` | a mark is there but its lead is slim; scored and flagged |
| `BLANK` | nothing above the ink floor |
| `MULTIPLE_MARK` | two or more marks that cannot be separated |
| `INVALID` | the question could not be sampled at all |

`result.needs_review` lists the question numbers that are not `CONFIDENT` or
`BLANK`.

## Marking

Exam boards publish rules a three-number scheme cannot express, so the rules
are data:

```python
from omr_mcq import MarkingScheme, NEGATIVE_MARKING

read_sheet(path, layout.NEET, answer_key=key, scheme=NEGATIVE_MARKING)

MarkingScheme(correct=4, wrong=-1, blank=0,
              ambiguous_policy="wrong",   # NEET/JEE: a double mark is wrong
              floor_at_zero=True)         # report 0, not a negative total
```

Four things this gets right that a naive scheme does not:

- A **double mark is penalised**, not treated as a free blank. NEET and JEE
  count it as an incorrect response.
- A question **outside the answer key is unscored**, not wrong, and is
  excluded from the maximum. A half-entered key must not deduct marks.
- **Negative totals floor at zero**, per subject and overall.
- **Fractional marks do not drift.** Totals are quantised decimally, because a
  total gets read aloud to a student.

## Layouts

A layout says only how questions are *counted* — no coordinates:

```python
from omr_mcq import Layout

MY_SHEET = Layout(name="Mock", blocks=4, rows_per_block=25,
                  options=("A", "B", "C", "D"),
                  subjects=("Physics", "Chemistry", "Botany", "Zoology"))
```

Built in: `layout.NEET`, `layout.JEE`, `layout.GUJCET`, `layout.HSC`.

## Debug images

```python
from omr_mcq import annotate, diagnose
import cv2

cv2.imwrite("review.png", annotate(result))     # for a teacher
cv2.imwrite("debug.png", diagnose(result))      # for an engineer
```

`annotate` rings each marked bubble, green when it matches the key and red when
it does not, with the correct option shown on the ones that were missed.
`diagnose` renders the fitted lattice over the sheet, which is what you want
when the question is "did localisation land correctly" rather than "what did
the student answer".

## Verify it yourself

```
python -m pytest tests/ -q     # 45 tests
python benchmark.py            # the numbers above, reproduced
```

## Known limits

Read these before trusting it on a new form.

- **Ground truth is one hand-read sheet.** Everything above measures agreement
  with my own reading of that capture, plus synthesised distortions of it. It
  does not yet tell you how the reader behaves across students, handwriting or
  cameras. Add captures to `samples/` and entries to `tests/ground_truth.json`
  to widen it.
- **`MULTIPLE_MARK` and `LOW_CONFIDENCE` are not exercised by a real sheet.**
  They are covered by unit tests on synthetic scores. The sample has 39 clean
  marks and 161 blanks. A sheet with a genuine double mark or a half-erased
  answer is the most valuable thing to add next.
- **Roll numbers are not read.** The lattice covers the answer table only.
- **The sheet must have a ruled answer table.** Localisation anchors on the
  printed rules. A form without them needs a different anchor.
- **Reported ROI recall of 72-88% understates performance.** The reference
  detector used for that figure deliberately misses merged and broken bubbles,
  so it counts fewer bubbles than the sheet has. Answer accuracy is the number
  that matters.
