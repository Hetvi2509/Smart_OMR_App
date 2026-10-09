# How the reader works

Written for whoever has to change this code. It explains each step and, more
importantly, why the obvious alternative was rejected — every rejection below
is something that was measured failing on a real sheet, not a hunch.

## The idea in one paragraph

A printed OMR form has a rigid, repeating lattice of bubbles inside a ruled
table. That lattice is a far stronger signal than any individual bubble, so
the reader measures it from the whole page at once and then asks each cell
only how much ink sits inside it. No circle is ever detected.

## Why not detect circles

Hough-circle and per-bubble contour detection both answer "is there a circle
here", and both degrade exactly where an OMR reader has to be strongest:

- A **solidly shaded bubble stops being a circle.** It is a disc, and a
  circle detector tuned to find the printed outline will miss or mislocate it.
- A **blurred or broken outline stops being an edge**, so a soft-focus photo
  loses bubbles that are plainly visible to a human.
- Both are **per-bubble**, so each detection can fail independently. Losing one
  bubble out of 800 renumbers every question after it.

Fitting a lattice to the whole page inverts that. It is over-determined: two
or three numbers fitted against hundreds of bubbles, so individual missing,
merged or blurred bubbles cost nothing as long as most of their neighbours
survive. Losing a bubble is impossible, because bubbles are not what is being
found.

## Pipeline

### 1. Deskew

Residual in-plane rotation is measured from the printed table rules with a
Hough *line* transform and removed.

Everything downstream takes axis-aligned projections and column clusters,
which assume the rows are horizontal. They degrade quickly when they are not:
across a grid ~950px wide, half a degree of tilt smears a column sideways by
8px, a quarter of a row pitch. Measuring and removing the tilt once is far
cheaper than making every later stage rotation-invariant.

Note that the Hough transform appears here, and only here, finding straight
lines — which it is reliable at — rather than circles.

### 2. Find the answer table

Long-run morphology isolates the printed rules; the largest resulting box is
the answer table.

This is anchor-based registration where the sheet's own printed furniture is
the anchor, so nothing depends on corner markers. **Rejected alternative:** the
paper outline. It tells you nothing about where the content sits. An earlier
version of this system warped paper-corners onto a canonical rectangle, which
is geometrically valid and semantically meaningless; it scored 26% on this
sheet while looking like it had worked.

### 3. Find the bubbles as blobs

Connected components inside the table, filtered to small near-square shapes.

This is the primitive everything else is built on. Note what it is *not*: no
circle is fitted and no radius is searched. A blob only has to be roughly the
right size and squareness to vote, and the geometry comes from the lattice
fitted to the whole population.

**Rejected alternative:** projection-profile peaks. A profile collapses a whole
column into one number, so it cannot tell a bubble column from a column of
question-number glyphs, and faint columns on a blank master fall below any
threshold and fragment whole blocks. Measured: column localisation error of
12-72px with profiles, against 0.3-0.7px with blobs.

### 4. Fit the lattice

Blob centres cluster along x into option columns, grouped into per-subject
blocks, and along y into question rows. Both axes come from the same
measurement, so they are mutually consistent and sit on the bubbles' centres.

**Rejected alternative:** fitting the row phase by maximising ink under a comb.
That biases the lattice onto the top edge of the printed ring — measured as a
systematic 12px offset across all four layouts. Still inside the bubble, so
answers read, but it spends tolerance that rotation and perspective need.

Three filters keep printed furniture out of the row lattice:

- **Column alignment.** A real question row puts a bubble under every option
  column; a header's glyphs land between them. Measured: real rows score 17-19
  aligned blobs out of 16 columns, headers 0-6.
- **Off-lattice gaps.** A row whose gap to its neighbour is not close to a whole
  number of pitches is not on the grid. The GUJCET block header sat 1.80
  pitches above row 1 and passed the alignment test, because it spans the full
  width; this catches it.
- **Pitch consistency.** Clusters that disagree with the dominant pitch from
  both neighbours are dropped.

### 5. Reconcile the row count

The layout says how many rows to expect. The reader extends each section band
at whichever edge actually carries ink until the counts agree.

Two defects pull in opposite directions here, and they look identical as a
gap width:

- A **section banner** ("SECTION - B") opens about three pitches of space
  carrying no questions. Interpolating across it invents rows.
- A **heavily marked row** merges its bubbles into one or two large blobs and
  fails to cluster at all. Measured: the last row of each section yielded 3-4
  blobs against 16 columns, so both sections came up one row short.

Which *edge* loses the row varies with the distortion — the sharp capture
loses the last row of each section, the same image under 5x5 blur loses the
first instead — so the edge is chosen by probing for ink rather than assumed.

## Classification

### Paper level by dilation

Ink strength is measured against a locally estimated paper brightness, found
by greyscale dilation: marks are always darker than their paper, so the
brightest pixel in a neighbourhood larger than one bubble is, by construction,
unmarked paper.

**Rejected alternative:** a median blur. Inside a solidly filled bubble most of
the window is ink, so the median follows the mark down. Measured: a filled
bubble read 94 against a 52 centre where dilation correctly reported 174,
which made filled and blank bubbles score almost identically.

### Remove the printed label pedestal

Every bubble on these forms is printed with its option label inside it, so a
completely unmarked bubble still carries ink — measured at roughly 0.5 against
1.0 for a filled one. Subtracting the question's own median removes that
pedestal, and because it is per question it also cancels local shading.

### Decide relatively

The comparison that matters is between the options of one question, never
against a page-wide cut, which is what makes the reading robust to uneven
lighting. The "is anything marked at all" floor is calibrated per sheet by
Otsu's method on that sheet's own score histogram.

A question is `CONFIDENT` only when one option is clearly above the floor and
clearly ahead of the rest; everything else is reported rather than guessed.

## Refusing

Localisation can succeed on a *subset* of a sheet and look entirely healthy,
which is the failure mode that matters most: the questions found are read
correctly, but they are numbered from the top of whatever was found, so every
answer after the first missing row lands on the wrong question. Nothing in the
fit itself reveals this � the lattice is regular, the fit score is high.

So the reader checks the fit against what the layout declares, and against the
frame:

- **Row and block counts must match the layout.** A 10-row HSC form fits a
  50-row NEET layout happily, reporting 10 answered questions out of 200.
- **The grid must not touch the frame edge.** A NEET capture with its Zoology
  column cropped away fitted the 3-block GUJCET layout and read three subjects
  as if that were the whole paper. The block count cannot catch this, because
  the missing column never reaches the fitter.
- **Block strides must be regular.** A printed form repeats its subject blocks
  at one stride, so a stride roughly double its neighbour means a block sat
  between them and was missed. Measured: a sheet photographed small in frame
  gave strides of 261 and 128px where genuine forms run 228/230/232.
- **A candidate layout may not have fewer blocks than the sheet shows.**
  Dropping a whole subject column is never a better answer than refusing.

Across 31 real captures these take the silent-misread count to zero: 18 sheets
read under a correctly detected layout, 13 refused with a specific reason.

## Performance

About 0.5-0.9 s per sheet at the 1600px working width, dominated by the
connected-component pass and the ink map. Both are single full-image
operations, so cost scales with pixels rather than with question count — a
200-question sheet costs about the same as a 50-question one.
