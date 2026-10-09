# Advanced OMR Evaluation System — Problem Statement & Solution Guide

> **Status:** Design specification (for review) · **Date:** 2026‑07‑04
> This document is the single source of truth for *what* we are building and *how*. It combines the **problem statement**, the **solution architecture**, and a **step‑by‑step build guide**.

---

## 1. Problem Statement

We want a mobile application that lets a teacher / proctor:

1. **Create a test**
   - Select an **exam type** — **NEET**, **JEE**, or **Custom**.
   - **Enter the answer key** by tapping the correct option (A/B/C/D) for each question in an on‑screen grid.
   - Configure the **marking scheme** (marks for correct / negative for wrong / zero for blank).

2. **Evaluate answer sheets (OMR)**
   - Point the **phone camera** at a filled OMR sheet and scan it.
   - The system automatically reads which options the student marked, identifies **correct vs incorrect** answers, and computes the **total marks**.
   - The student's **Name** and **Roll Number** are **extracted at the moment of evaluation** (roll number from the sheet, name resolved from a roster).
   - A **report** is generated containing the **photo of the OMR sheet**, the evaluation score, subject‑wise and question‑wise breakdown, and the student's name & roll number.

### Hard requirements (what makes this "Advanced")

- **Any phone.** Must not depend on a specific device's camera or compute.
- **Any orientation.** The sheet may be photographed **straight, tilted, skewed, rotated, or upside‑down ("flipped")**. The system must dewarp and grade correctly regardless.
- **Dynamic capture.** The user just takes a photo; the system figures out the geometry itself.
- **Minimal time.** Grading a sheet must complete in roughly **≤ 1 second** of processing so a proctor can grade a stack quickly.

### Non‑goals (MVP scope limits)

- We grade **our own printed template** (which carries alignment markers), not arbitrary third‑party sheets.
- **JEE numeric/integer‑type** questions are not gradable on a 4‑option bubble sheet — MCQ‑only for the MVP.
- Handwriting recognition of the student's **name** is out of scope; the name comes from a **roster** keyed by the bubbled roll number.

---

## 2. Users & Core Flows

| Actor | Flow |
|---|---|
| Teacher | Create test → enter answer key → (optionally) upload student roster → grade sheets → view/share reports |
| Proctor | Open a saved test → scan each student sheet → instant result → move to next |

**Flow A — Create Test**
`Pick exam type → preset fills question count/sections/marking → tap answer key grid → save`

**Flow B — Evaluate**
`Open test → camera + align guide → capture → upload → grade → result overlay → report`

---

## 3. Requirements

### Functional
- FR1 Create/save tests with exam type, answer key, and marking scheme.
- FR2 Import a student roster (roll number → name).
- FR3 Capture an OMR photo with on‑screen alignment guidance.
- FR4 Detect the sheet and correct perspective from **any** orientation/tilt/flip.
- FR5 Read all answer bubbles and the roll‑number bubble grid.
- FR6 Score against the answer key using the marking scheme (with subject subtotals).
- FR7 Resolve the student name from the roster via roll number.
- FR8 Produce an annotated image (correct = green, wrong = red, show correct option).
- FR9 Generate a report (PDF) with the sheet photo + all scores + identity.
- FR10 Keep a history of evaluations per test.

### Non‑functional
- NFR1 **Speed:** ≤ ~1 s server‑side grading per sheet; instant perceived result.
- NFR2 **Robustness:** tolerant of lighting, shadow, mild glare, rotation, upside‑down.
- NFR3 **Portability:** works across Android/iOS phones and camera qualities.
- NFR4 **Reliability:** never silently misgrade — on a bad capture, return a **retake hint**.
- NFR5 **Offline‑ready (future):** architecture allows moving grading on‑device later.

---

## 4. Architecture

**Chosen stack (locked with the client):**

- **Frontend:** **React Native** app (capture, test creation, results, reports).
- **Sheet:** **Custom OMR template with four ArUco corner markers** + a `template.json` describing bubble geometry.
- **Identity:** **Bubbled roll number** read from the sheet → **name from roster**.
- **Grading engine:** **Python FastAPI + OpenCV** backend (recommended because RN has no mature on‑device OpenCV/ArUco path; Python+OpenCV is the proven OMR stack). On‑device grading is a documented future option.

```
[ React Native app ]                          [ Python FastAPI + OpenCV backend ]
  Create Test  ─────── POST /tests ──────────►  Tests / AnswerKey / MarkScheme  (DB)
  Upload Roster ────── POST /students ───────►  Students roster (roll → name)     (DB)
  Camera capture
    + align guide + JPEG compress
              ───────  POST /evaluate ────────►  CV PIPELINE:
                                                   ArUco detect → homography (dewarp)
                                                   → template register
                                                   → bubble fill read (answers + roll)
                                                   → score vs key → roll→name
                                                   → annotate image
   Result overlay ◄── JSON + annotated image ──  {roll,name,per_question,score,...}
   Report / PDF   ◄──  GET /reports/{id}.pdf ──  ReportLab PDF (photo + scores)
```

**Why a backend and not on‑device (for MVP):** a compressed ~1080p JPEG (~200–400 KB) round‑trips in well under a second; Python/OpenCV gives us robust, testable ArUco + homography + bubble reading immediately, versus a fragile native‑module CV path in React Native.

---

## 5. OMR Template Design (the printed sheet)

The sheet is engineered so a photo from any angle can be perfectly rectified.

- **Four ArUco corner markers**, each with a **unique ID** (e.g. TL=0, TR=1, BR=2, BL=3).
  - Because each corner is uniquely identified, detecting them tells us **which way is up** → **rotation and upside‑down ("flip") are resolved automatically**, and a perspective transform flattens tilt/skew.
- **Header band:** test title; optional QR code encoding the `test_id`.
- **Roll‑number grid:** *N* columns (e.g. 10 digits). Each column is a vertical **0–9** bubble strip; the student darkens one bubble per column.
- **Answer grid:** grouped into **subject sections** (e.g. NEET: Physics / Chemistry / Botany / Zoology), each question having **4 option bubbles (A–D)**.

**`template.json`** stores every bubble's coordinate **in the canonical (dewarped) frame**, so after rectification we know exactly where to sample each bubble. (Concept mirrors the open‑source `Udayraj123/OMRChecker` template approach.)

```jsonc
// template.json (illustrative)
{
  "page": { "width": 2100, "height": 2970 },          // canonical px (A4 @ ~250dpi)
  "markers": { "type": "aruco", "dict": "4x4_50",
               "ids": { "TL": 0, "TR": 1, "BR": 2, "BL": 3 } },
  "roll": { "origin": [200, 500], "cols": 10, "rows": 10,
            "dx": 60, "dy": 60, "bubble_r": 18 },
  "sections": [
    { "name": "Physics", "questions": 45, "options": 4,
      "origin": [200, 1200], "q_dy": 55, "opt_dx": 70, "bubble_r": 16 }
    // ... Chemistry, Botany, Zoology
  ]
}
```

---

## 6. Computer‑Vision Pipeline (the core)

Implemented in `backend/app/cv/`. Orchestrated by `pipeline.py`, fully instrumented for timing.

1. **Preprocess** — decode → downscale to a working width → grayscale → denoise → adaptive threshold.
2. **Marker detection** (`detect.py`) — `cv2.aruco.detectMarkers`; require all **4** corner IDs. If fewer are found → return a **retake hint** (blur / glare / partial / cropped) instead of guessing.
3. **Dewarp** (`dewarp.py`) — compute a homography from the four marker centers to the canonical template rectangle with `cv2.getPerspectiveTransform` + `cv2.warpPerspective`. Output: a **flat, upright, fixed‑size** sheet regardless of the input tilt/rotation/flip.
4. **Template registration** — load `template.json`; every bubble ROI is now at a known location.
5. **Bubble reading** (`bubbles.py`) — for each question, measure the **fill ratio** of each option ROI and pick the marked option using **relative** thresholding *within that question* (robust to uneven lighting/shadow). Flag `none` / `multiple` / `ambiguous`.
6. **Roll‑number reading** (`roll.py`) — same fill logic down each roll column → assemble the roll string.
7. **Scoring** (`score.py`) — compare to the answer key using the marking scheme (+correct / −wrong / 0 blank); compute **per‑subject** subtotals and total.
8. **Identity** — roll → name from roster. If no roster / no match → return roll only and let the app accept a manual name.
9. **Annotation** (`annotate.py`) — draw **green** on correct, **red** on wrong, and highlight the **correct** option for wrong answers; save the annotated image.
10. **Response** — JSON:
    ```json
    {
      "roll": "1234567890", "name": "Asha K",
      "per_question": [{"q":1,"marked":"B","correct":"C","status":"wrong"}],
      "correct": 150, "incorrect": 20, "unattempted": 10,
      "subject_scores": {"Physics": 168, "Chemistry": 150},
      "total": 580, "max": 720,
      "annotated_url": "/media/eval_00123_annotated.jpg",
      "timing_ms": 640
    }
    ```

### 6.1 Automatic capture (no manual corner‑matching)

Earlier versions of the Scan screen asked the user to manually fit the sheet into an on‑screen
corner box before taking a single photo — hard to do one‑handed, and the photo either worked or
didn't. This is replaced by a **live‑preview auto‑capture** loop, modeled on the UX of modern OS
document scanners but implemented server‑side against the existing CV cascade rather than a new
on‑device model:

- While framing the shot, the app POSTs a small, low‑quality preview frame (~640px wide) to a new
  **`POST /align-check`** endpoint roughly twice a second.
- `align-check` runs the *same* 3‑layer cascade as real grading (§6 Layer 1‑3: ORB → contour →
  ArUco) but stops immediately after alignment — no bubble/roll reading, scoring, or annotation —
  so it stays cheap enough to poll continuously (see `pipeline.check_alignment()`).
- It returns `{aligned, strategy, confidence, quad}`; the app draws a live quad overlay (amber
  while aligning, green once locked) and, once alignment holds for **2 consecutive checks**
  (~1.4s of "hold steady"), automatically fires the real full‑quality capture — the user never
  taps a shutter button or matches a corner box.
- Manual capture and gallery upload remain as an explicit fallback/override for difficult lighting
  or a user who prefers control.

**Why this design, and not something heavier:**

- **Native OS document scanners** — Apple's VisionKit (`VNDocumentCameraViewController`, used by
  Notes/Files) and Google's ML Kit Document Scanner API — are the gold‑standard reference for this
  UX: continuous on‑device edge detection with automatic capture the instant a document is framed.
  They were evaluated as a direct replacement (via `react-native-document-scanner-plugin`) but
  require ejecting the mobile app from Expo Go to a custom native build; the live‑preview‑via‑CV
  approach here ships the same user‑facing behavior (no corner matching, automatic shot) without
  that migration, and can be swapped in later as a drop‑in upgrade for true 30fps on‑device
  detection.
- **Classical contour/edge document‑boundary detection**, as used in early mobile scanning apps
  (CamScanner and similar), is exactly what the existing `ContourAligner` (Layer 2 fallback,
  `align.py`) already implements — largest‑quadrilateral‑contour extraction via Canny/adaptive
  threshold + `approxPolyDP`. Building the live‑preview check on top of it (plus the ORB layer)
  reuses this rather than re‑implementing document‑boundary detection.
- **ORB feature matching + RANSAC** (Layer 1, primary): Rublee et al., *"ORB: An Efficient
  Alternative to SIFT or SURF,"* ICCV 2011; Fischler & Bolles, *"Random Sample Consensus,"*
  Comm. ACM 1981 — the feature‑matching + robust‑homography‑fitting combination the whole cascade
  is built on. Its homography‑plausibility gate (`align._validate_homography`) checks that the
  input image's *center* lands near the canonical page and its corners spread around that center
  by a radius consistent with the image's own size under the fitted scale — decoupled from
  rotation, since a rotated image's corners sit the same distance from its own mapped center, just
  in a different direction. (A prior version bounded raw corner coordinates against a fixed margin
  around the canonical page, which wrongly rejected legitimate steep in‑plane rotations — e.g. a
  30° tilt with background canvas around the sheet — as bad matches, since a rotated axis‑aligned
  bounding box is inherently larger.)
- **Deep‑learning document rectification** — DocUNet (CVPR 2018), DewarpNet (ICCV 2019), DocTr
  (ACM MM 2021), and Fourier Document Restoration (CVPR 2022) represent the current state of the
  art for *dewarping curved/folded/crumpled* document photos via learned pixel‑displacement fields.
  They're deliberately **not** used here: an OMR sheet is a rigid flat sheet on a desk, so the only
  distortion is perspective (a projective transform fully recoverable in closed form), not page
  curl — reaching for a neural dewarping model would add substantial latency/model‑serving cost to
  solve a harder problem than the one that exists. This is noted explicitly so the choice reads as
  deliberate rather than an oversight if sheet handling ever changes (e.g. an unsupported "photo of
  a booklet page" mode).

### 6.2 Bubble‑reading accuracy

No OMR system — including flatbed‑scanner‑based ones — can honestly promise literal 100% accuracy:
a genuinely ambiguous mark (a half‑erased bubble, a stray pen dot, a bubble crossed out then
re‑marked) is ill‑posed for *any* reader, human included. What can be engineered is (a) minimizing
false reads on sheets a human would read unambiguously, and (b) never *silently* guessing on the
sheets a human would also find ambiguous — the retake/`"multiple"`/`"none"` machinery elsewhere in
this pipeline already reflects that philosophy. Two additions tighten (a) further:

- **Residual registration refinement** (`dewarp.refine_registration`) — the alignment cascade (§6)
  gets rotation/scale/perspective right, but real photos still leave a few pixels of consistent
  translational drift post‑warp (lens distortion, an imperfect corner fit, or the 3‑marker affine
  fallback having no perspective term). A single phase‑correlation pass (Foroosh, Zerubia & Berthod,
  *"Extension of Phase Correlation to Subpixel Registration,"* IEEE Trans. Image Processing 11(3),
  2002) against the pre‑rendered blank template corrects that drift for every bubble on the sheet
  at once — O(1) per sheet rather than re‑searching per bubble (NEET alone has ~820 bubbles). A
  low‑confidence or implausibly large correction is discarded rather than applied, matching this
  pipeline's fail‑safe pattern.
- **Per‑sheet adaptive fill threshold** (`bubbles.adaptive_abs_min_fill`) — the "is this bubble
  marked at all" floor was previously one fixed constant (0.30) for every photo. Otsu's method
  (Otsu, *"A Threshold Selection Method from Gray‑Level Histograms,"* IEEE Trans. SMC 9(1), 1979)
  is instead applied to *this sheet's own* population of bubble fill ratios each grading call —
  naturally bimodal (mostly‑blank bubbles vs. a few solidly‑marked ones), which is exactly the
  histogram shape Otsu is for — so a low‑contrast photo with faint pencil marks and a
  high‑contrast photo with heavy pen marks each get a floor calibrated to their own conditions,
  rather than one guess that's wrong for both. Clamped to `[0.18, 0.45]` so a degenerate histogram
  can't push it somewhere absurd, falling back to the fixed 0.30 constant when a sheet has too few
  bubbles to calibrate on.

**Explicitly not adopted (yet): a learned bubble classifier.** Recent OMR literature (e.g. survey
results reporting ~99%+ accuracy from a CNN/YOLO classifying each bubble crop as
filled/empty/crossed‑out, rather than rule‑based fill‑ratio thresholding) point at a real ceiling
above what classical fill‑ratio reading can reach — but that accuracy figure comes from training on
a labeled dataset of real scanned/photographed sheets. This project has no such dataset (only
synthetic renders), and shipping a "trained" classifier without real supervised data would be a
false accuracy claim, not an improvement. If real graded‑sheet photos become available (e.g. from
field use, with teacher‑corrected ground truth), a small CNN over bubble crops — as a corroborating
signal alongside the existing fill‑ratio reading, not a silent replacement — is the documented next
step.

### How each "hard requirement" is met
- **Orientation / flip / tilt** → unique‑ID ArUco corners + homography (unambiguous for any in‑plane rotation, perspective, and 180°/upside‑down). A true **mirror** (back of paper) is detected and **rejected with a hint** (bubbles not visible).
- **Lighting / shadow / glare** → adaptive threshold + per‑question relative fill comparison + a quality gate.
- **Any phone** → native camera + server CV, no device‑specific compute dependency.
- **Minimal time** → downscale, fast ArUco+warp+sampling (target < 1 s), lazy PDF generation, on‑device compression, and live capture guidance to reduce retakes.

---

## 7. Data Model & API

**Tables:** `Test`, `Question` (answer key), `Student` (roll, name), `Evaluation` (test_id, roll, score, image paths, timestamp), `Answer` (per‑question marked/correct/status).

**Endpoints:**
- `POST /tests` — create (exam_type, answer_key, marking_scheme, template_id); `GET /tests/{id}`.
- `POST /students` — bulk roster upload (roll → name), CSV or JSON.
- `POST /evaluate` — multipart (image + test_id) → grading JSON (§6).
- `POST /align-check` — multipart (image + test_id) → grading‑free alignment feedback for the live
  preview loop: `{aligned, strategy, confidence, quad, image_width, image_height, reason, hint}`
  (§6.1).
- `GET /reports/{id}` (JSON) and `GET /reports/{id}.pdf` (generated report).

---

## 8. Mobile App Screens

| Screen | Purpose |
|---|---|
| Home | List tests; start create/evaluate |
| CreateTest | Pick exam type; preset fills counts/sections/marking |
| EnterAnswerKey | Tap grid (A/B/C/D per question) |
| Roster | Import/enter roll → name list |
| Scan | Camera + alignment frame + live guidance + auto/one‑tap capture |
| Result | Overlay correct/incorrect on returned image; totals, subject‑wise, name/roll |
| Report | View / share / download PDF |
| History | Past evaluations per test |

---

## 9. Exam Presets & Marking

- **NEET:** 180 questions (Physics 45 / Chemistry 45 / Botany 45 / Zoology 45), 4 options, **+4 / −1 / 0**.
- **JEE Main:** MCQ sections, 4 options, **+4 / −1** (integer‑type questions out of MVP scope).
- **Custom:** user sets question count, options, and marking scheme.

---

## 10. Report Format (PDF)

Header (test name, date) · Student **name + roll** · **Total score / max** · **subject‑wise** table · **question‑wise** correct/incorrect table · the **annotated sheet photo**. Generated with ReportLab; viewable/shareable/downloadable from the app.

---

## 11. Technology Choices

- **Mobile:** React Native (Expo dev build); `react-native-vision-camera` or `expo-camera`; `expo-image-manipulator`; `react-navigation`; `axios` + `@tanstack/react-query`; `react-native-svg`; `zustand`.
- **Backend:** FastAPI + `uvicorn`; **`opencv-contrib-python`** (ArUco), `numpy`; `pydantic`; SQLAlchemy + SQLite (dev) / Postgres (prod); `reportlab`; `Pillow`; `python-multipart`.

---

## 12. Repository Layout

```
Smart_OMR_Evaluator/
  docs/OMR_Advanced_System_Spec.md      # this document
  backend/
    app/
      main.py
      api/        tests.py students.py evaluate.py reports.py
      cv/         detect.py dewarp.py bubbles.py roll.py score.py annotate.py pipeline.py
      models/     db.py schema.py
      templates/  neet.json jee.json custom.json  + printable sheets (PDF)
      report/     pdf.py
    tests/        sample images (straight/tilted/flipped/lowlight) + test_pipeline.py
    requirements.txt
  mobile/
    src/screens, src/components, src/api, src/navigation, src/store
  README.md
```

---

## 13. Build Milestones

- **M0 — Scaffold + this spec + template.** Repo skeleton, printable OMR sheet + `template.json` + generated ArUco markers.
- **M1 — CV core.** Pipeline proven on sample photos (straight/tilted/flipped/low‑light) via `tests/test_pipeline.py`.
- **M2 — API + DB.** Tests, roster, evaluate, reports; SQLite.
- **M3 — App:** create test + answer key + roster.
- **M4 — App:** scan → upload → result overlay.
- **M5 — Report/PDF + history + share/export.**
- **M6 — Hardening.** Orientation/flip/lighting test matrix, speed tuning, capture guidance; optional on‑device auto‑detect (stretch).

---

## 14. Verification Strategy

- **CV unit tests:** feed sample sheet photos in each orientation (straight / tilted / upside‑down / low‑light) → assert correct roll + expected score; assert a graceful **retake** response when markers are missing.
- **Backend:** run `uvicorn`; exercise `POST /tests`, `POST /students`, `POST /evaluate` with a sample image; verify JSON + annotated image + `/reports/{id}.pdf`.
- **End‑to‑end:** run the app in Expo, create a test, scan a printed sheet, confirm overlay + score + name/roll + shareable report; confirm per‑sheet grading time within target.

---

## 15. Assumptions & Limitations

- Students use **our printed template** (with markers); arbitrary sheets are out of scope.
- JEE numeric questions aren't gradable on a 4‑option bubble sheet (MCQ‑only MVP).
- Name accuracy depends on the roster; without one we surface the roll and allow manual name entry.
- MVP grades **server‑side**; offline on‑device grading is a future enhancement.
