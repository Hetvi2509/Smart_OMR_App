# Smart OMR Evaluator

Mobile app + CV backend that lets a teacher create a test, and lets a proctor point a phone camera
at a filled OMR sheet — in any orientation, tilt, or upside-down — and get an instant, scored,
annotated result with the student's name and roll number.

Full design/spec: [`docs/OMR_Advanced_System_Spec.md`](docs/OMR_Advanced_System_Spec.md).

## What's here

```
backend/     FastAPI + OpenCV grading service (ArUco detect -> dewarp -> bubble read -> score -> PDF)
mobile/      React Native (Expo) app: create test, roster, scan, results, reports, history
docs/        Design spec
```

## Quick start

**1. Backend** (see `backend/README.md` for detail)

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify it: `pytest tests/test_pipeline.py -v` runs the CV pipeline against synthetically photographed
sheets in every orientation (straight/tilted/rotated/upside-down/low-light/blurry/cropped) — no
printer or camera needed.

**2. Mobile app**

```bash
cd mobile
npm install
npx expo start
```

Open in Expo Go on your phone (same Wi-Fi as your backend) or a simulator. On first launch, tap
**Server** on the Home screen and confirm/edit the backend URL — it defaults to a guess based on the
Metro dev server's host, but you may need to enter your machine's LAN IP explicitly (e.g.
`http://192.168.1.23:8000`) for a physical device to reach it.

## How it works

1. **Create a test** — pick NEET / JEE / Custom, tap in the answer key, set the marking scheme.
   Saving builds a `template.json`-equivalent layout (ArUco marker positions + every bubble's
   canonical coordinate) and stores it with the test, so grading is self-consistent even for
   custom question counts.
2. **Scan** — just hold the phone up to the sheet. The app polls a lightweight `/align-check`
   endpoint a couple of times a second against small preview frames, draws a live quad overlay
   (amber while aligning, green once locked), and automatically fires the real capture once the
   sheet holds steady for ~1.4s — no manual corner-matching or shutter tap required. (Manual
   capture and gallery upload remain available as a fallback.) The full-quality photo is then
   resized/compressed client-side and POSTed to `/evaluate`.
3. **Grade** (`backend/app/cv/pipeline.py`) — detect the 4 uniquely-ID'd ArUco corner markers (this
   is what makes rotation, tilt, and upside-down photos all work: the IDs tell you which corner is
   which, regardless of how the sheet was photographed) → homography dewarp to a flat canonical
   frame → read every bubble's fill ratio (relative, per-question, so uneven lighting doesn't
   matter) → read the roll number the same way → score against the answer key → resolve the
   student's name from the roster → annotate the sheet (green = correct, red = wrong) → respond in
   well under a second.
4. **Result / Report** — the app shows the annotated sheet, totals, and subject-wise breakdown, and
   can generate/share a PDF report.

If the pipeline can't grade a photo with confidence (missing markers, blur, severe under/over
exposure) it never guesses — it returns a `retake` response with a specific hint, and the app
surfaces that on the Scan screen.

## Scope (MVP)

- Grades the project's own printed template (ArUco corner markers required) — not arbitrary
  third-party sheets.
- MCQ only (JEE numeric-answer questions aren't gradable on a 4-option bubble sheet).
- Student name comes from an uploaded roster keyed by roll number, not handwriting OCR.
- Grading runs server-side; on-device grading is a documented future option.
