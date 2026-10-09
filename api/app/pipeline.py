"""The scan pipeline: image in, stored evaluation out.

    image bytes
      -> omr_mcq.read_sheet            (existing engine, backend_mcq_final)
      -> PaddleOCR header              (candidate identity)
      -> answer key fetched from Neon  (by test_id, never passed by the client)
      -> omr_mcq.apply_scheme          (existing marking rules)
      -> rows in Neon
"""
from __future__ import annotations

import json
import logging
import queue
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from . import blobs, config, db
from .omr_engine import (
    MarkingScheme, SheetUnreadable, annotate, apply_scheme, get_layout,
    read_sheet,
)

logger = logging.getLogger(__name__)

# Order matters: a higher grade is checked first.
_GRADES = ((90, "A+"), (80, "A"), (70, "B+"), (60, "B"),
           (50, "C"), (40, "D"), (33, "E"))


def grade_for(percentage: float) -> str:
    for floor, label in _GRADES:
        if percentage >= floor:
            return label
    return "F"


def scheme_from_test(test: dict) -> MarkingScheme:
    return MarkingScheme(
        correct=float(test["marks_correct"]),
        wrong=float(test["marks_wrong"]),
        blank=float(test["marks_blank"]),
        ambiguous_policy=test["ambiguous_policy"],
        floor_at_zero=bool(test["floor_at_zero"]),
    )


def fetch_answer_key(test_id: int) -> dict[int, str]:
    """The stored key for *test_id*, as the engine wants it.

    Read from Neon on every scan and never accepted from the client: the key is
    the thing being graded against, so a caller must not be able to supply it.
    """
    rows = db.query(
        "SELECT question_no, correct_option FROM answer_keys"
        " WHERE test_id = %s ORDER BY question_no", (test_id,))
    return {int(r["question_no"]): r["correct_option"] for r in rows}


def save_upload(data: bytes, submission_id: int, filename: str) -> str:
    config.ensure_dirs()
    suffix = Path(filename or "").suffix.lower()
    if suffix not in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
        suffix = ".jpg"
    name = f"sub_{submission_id}{suffix}"
    return blobs.save(data, config.UPLOAD_DIR, name)


def decode(data: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise SheetUnreadable("decode_failed",
                              "That file is not a readable image.")
    return img


# OCR runs in a separate *process*, not a thread.
#
# Paddle's inference holds Python's GIL for long stretches, so an in-process
# worker froze the whole server: a plain GET /health took 13s while a sheet was
# being read. A subprocess cannot block this process's event loop at all, and
# the OS schedules it against the request path rather than inside it.
#
# One job at a time, queued: concurrent passes do not finish sooner on a
# saturated CPU and only lengthen the queue.
_ocr_queue: "queue.Queue[int]" = queue.Queue(maxsize=256)
_worker: threading.Thread | None = None
_worker_lock = threading.Lock()


def queue_candidate_ocr(submission_id: int) -> None:
    """Hand a stored submission to the background OCR worker.

    Only the id is queued: the sheet is already on disk, so the worker reads it
    from there rather than carrying a decoded array between processes.
    """
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_ocr_pump, name="candidate-ocr",
                                       daemon=True)
            _worker.start()
    try:
        _ocr_queue.put_nowait(submission_id)
    except queue.Full:
        # A full queue means a long backlog. Marking it failed is honest: the
        # UI shows the fields as needing entry rather than waiting forever.
        logger.warning("OCR queue full; skipping submission %s", submission_id)
        db.execute("UPDATE ocr_results SET status='failed' WHERE submission_id=%s",
                   (submission_id,))


def _ocr_pump() -> None:
    """Feed queued submissions to the OCR subprocess, one at a time.

    This thread only waits on a subprocess, so it holds no GIL while the work
    runs.
    """
    while True:
        submission_id = _ocr_queue.get()
        try:
            _run_ocr_subprocess(submission_id)
        except Exception:                             # noqa: BLE001
            logger.exception("candidate OCR failed for submission %s",
                             submission_id)
            try:
                db.execute("UPDATE ocr_results SET status='failed'"
                           " WHERE submission_id=%s", (submission_id,))
            except Exception:                         # noqa: BLE001
                logger.exception("could not mark OCR failed for %s", submission_id)
        finally:
            _ocr_queue.task_done()


# Generous: a first run downloads model weights before it can read anything.
OCR_TIMEOUT_SECONDS = 600


def _run_ocr_subprocess(submission_id: int) -> None:
    """Run `python -m app.ocr_job <id>` and wait for it."""
    proc = subprocess.run(
        [sys.executable, "-m", "app.ocr_job", str(submission_id)],
        cwd=str(config.ROOT),
        capture_output=True,
        text=True,
        timeout=OCR_TIMEOUT_SECONDS,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"ocr_job exited {proc.returncode}: {proc.stderr.strip()[-400:]}")


def _write_annotated(result, submission_id: int) -> str | None:
    """Render and store the engine's review overlay for one sheet.

    Never fatal: the overlay is a review aid, so a failure here must not throw
    away a sheet that was read and scored correctly. The result screen simply
    shows the original photo instead.
    """
    try:
        config.ensure_dirs()
        # JPEG, not PNG: the overlay of a 1600px sheet is ~6 MB as PNG and
        # ~400 KB as JPEG, and it is going to a phone over WiFi. Encoded to
        # bytes in memory (not written via cv2.imwrite) so the same code path
        # works whether storage ends up on disk or in Postgres.
        ok, buf = cv2.imencode(".jpg", annotate(result),
                               [cv2.IMWRITE_JPEG_QUALITY, 88])
        if not ok:
            return None
        return blobs.save(buf.tobytes(), config.ANNOTATED_DIR,
                          f"sub_{submission_id}.jpg", content_type="image/jpeg")
    except Exception:                                 # noqa: BLE001
        logger.exception("could not render the review overlay for %s",
                         submission_id)
        return None


def _reader_status(verdict: str) -> str:
    """Map an engine verdict onto the status string apply_scheme expects."""
    if verdict == "MULTIPLE_MARK":
        return "multiple"
    if verdict == "INVALID":
        return "invalid"
    if verdict == "BLANK":
        return "blank"
    return "ok"


def process(submission_id: int, test: dict, image: np.ndarray,
            user_id: int, image_path: str | None = None) -> dict:
    """Read, score and store one sheet.  Returns the API result payload.

    Raises SheetUnreadable when the engine refuses the sheet; the caller marks
    the submission failed and reports the engine's own reason and hint.
    """
    started = time.time()
    layout = get_layout(test["layout"])
    scheme = scheme_from_test(test)

    # The key fetch (~1s, Neon round-trip) and the bubble read (~0.6s, pure
    # CPU) touch nothing in common, so they run concurrently on a thread
    # instead of back to back.
    with ThreadPoolExecutor(max_workers=2) as pool:
        key_future = pool.submit(fetch_answer_key, test["id"])
        # The engine raises rather than returning a partial read; re-raising
        # here (outside the pool) keeps SheetUnreadable visible to the caller.
        try:
            result = read_sheet(image, layout)
        finally:
            answer_key = key_future.result()
    score = apply_scheme(
        [{"q": q.q, "subject": q.subject, "marked": q.marked,
          "status": _reader_status(q.verdict), "needs_review": q.needs_review}
         for q in result.questions],
        answer_key, scheme)

    # The review overlay: the sheet with every bubble the algorithm detected
    # ringed, green where it matches the key and red where it does not. This
    # is what lets a teacher check the machine's reading against the paper
    # instead of taking the total on trust.
    #
    # annotate() colours from result.score, which read_sheet only populates
    # when it is handed the key itself; the key is fetched separately here, so
    # the score is attached before rendering.
    result.score = score
    annotated_path = _write_annotated(result, submission_id)

    elapsed_ms = int((time.time() - started) * 1000)

    max_marks = float(score.max_score)
    percentage = (round(float(score.total) / max_marks * 100, 2)
                  if max_marks else 0.0)

    # One transaction, pipelined: Neon's cross-region round-trip is ~1s, and
    # this save used to make ~7 of them sequentially (~7s) for work that is
    # otherwise done in under 2s. Pipeline mode queues every statement and
    # sends them together, so the whole save costs about one round-trip
    # instead of one per statement. The only true dependency is evaluation_id,
    # which the evaluation_items batch needs -- so the queue is split there:
    # everything independent goes in the first batch (including the
    # evaluation upsert), one sync reads back its id, then the dependent
    # batch goes in a second pipeline block.
    with db.conn() as c:
        with c.pipeline():
            c.execute(
                "UPDATE submissions SET status='completed', image_path=%s,"
                " annotated_path=%s, layout_used=%s, answered_count=%s,"
                " review_questions=%s, processing_ms=%s, processed_at=now(),"
                " error_reason=NULL, error_hint=NULL WHERE id=%s",
                (image_path, annotated_path, layout.name, result.answered,
                 result.needs_review, elapsed_ms, submission_id))

            c.execute("DELETE FROM detected_answers WHERE submission_id=%s",
                      (submission_id,))
            with c.cursor() as cur:
                cur.executemany(
                    "INSERT INTO detected_answers (submission_id, question_no,"
                    " subject, marked_option, verdict, confidence, needs_review)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    [(submission_id, q.q, q.subject, q.marked, q.verdict,
                      round(float(q.confidence), 3), q.needs_review)
                     for q in result.questions])

            # The candidate row is created empty and filled by the background
            # OCR pass; see app/ocr_job.py. ON CONFLICT DO NOTHING so a
            # re-scan of the same submission cannot wipe details a human
            # already corrected.
            c.execute(
                "INSERT INTO ocr_results (submission_id, status)"
                " VALUES (%s, %s) ON CONFLICT (submission_id) DO NOTHING",
                (submission_id, "pending" if config.ENABLE_OCR else "skipped"))

            eval_cur = c.execute(
                "INSERT INTO evaluations (submission_id, test_id, correct_count,"
                " wrong_count, unattempted_count, invalid_count, unscored_count,"
                " total_marks, max_marks, percentage, grade, subject_scores,"
                " scheme_used)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                " ON CONFLICT (submission_id) DO UPDATE SET"
                " correct_count=EXCLUDED.correct_count,"
                " wrong_count=EXCLUDED.wrong_count,"
                " unattempted_count=EXCLUDED.unattempted_count,"
                " invalid_count=EXCLUDED.invalid_count,"
                " unscored_count=EXCLUDED.unscored_count,"
                " total_marks=EXCLUDED.total_marks, max_marks=EXCLUDED.max_marks,"
                " percentage=EXCLUDED.percentage, grade=EXCLUDED.grade,"
                " subject_scores=EXCLUDED.subject_scores,"
                " scheme_used=EXCLUDED.scheme_used, evaluated_at=now()"
                " RETURNING id",
                (submission_id, test["id"], score.correct, score.wrong,
                 score.unattempted, score.invalid, score.unscored,
                 float(score.total), max_marks, percentage,
                 grade_for(percentage), json.dumps(score.subject_scores),
                 json.dumps(vars(scheme))))

            # Reading this result inside the pipeline forces a sync here --
            # the one round-trip evaluation_items cannot avoid, since it
            # genuinely depends on the id just generated.
            evaluation_id = eval_cur.fetchone()["id"]

        with c.pipeline():
            c.execute("DELETE FROM evaluation_items WHERE evaluation_id=%s",
                      (evaluation_id,))
            with c.cursor() as cur:
                cur.executemany(
                    "INSERT INTO evaluation_items (evaluation_id, question_no,"
                    " subject, marked_option, expected_option, status, marks,"
                    " needs_review, note) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    [(evaluation_id, o.q, o.subject, o.marked, o.expected,
                      o.status, float(o.marks), o.needs_review, o.note)
                     for o in score.outcomes])

            db.audit(c, user_id, "scan.completed", "submission", submission_id,
                     {"test_id": test["id"], "total": float(score.total),
                      "percentage": percentage, "answered": result.answered,
                      "ms": elapsed_ms})

    return {
        "submission_id": submission_id,
        "evaluation_id": evaluation_id,
        "status": "completed",
        "layout": layout.name,
        "answered": result.answered,
        "processing_ms": elapsed_ms,
        "review_questions": result.needs_review,
        "key_questions": len(answer_key),
        # Empty at this point by design: OCR runs after the response so the
        # caller is not held for ~30s of CPU-bound text recognition. The app
        # polls the result and the fields appear when the pass finishes.
        "candidate": {k: None for k in
                      ("roll_no", "student_name", "class_std", "section",
                       "registration_no")},
        "ocr": {"status": "pending" if config.ENABLE_OCR else "skipped",
                "confidence": None, "engine": None, "note": None},
        "score": {
            "correct": score.correct, "wrong": score.wrong,
            "unattempted": score.unattempted, "invalid": score.invalid,
            "unscored": score.unscored, "attempted": score.attempted,
            "total": float(score.total), "max": max_marks,
            "percentage": percentage, "grade": grade_for(percentage),
            "subject_scores": score.subject_scores,
        },
    }
