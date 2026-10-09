"""Smart OMR Evaluator API.

The only component that holds the Neon credentials.  The mobile app reaches
Postgres exclusively through these endpoints.
"""
from __future__ import annotations

import json
import logging

from fastapi import (
    Depends, FastAPI, File, HTTPException, Query, Response, UploadFile, status,
)
from fastapi.middleware.cors import CORSMiddleware

from . import auth, blobs, config, db, ocr, pipeline, report
from .models import (
    AnswerKeyIn, AnswerOverride, CandidateIn, SignIn, SignUp, TestIn,
)
from .omr_engine import SheetUnreadable, layout_info

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("omr.api")

app = FastAPI(title="Smart OMR Evaluator API", version="1.0.0")

# The app is served to Expo Go from a LAN address that changes per network, so
# the origin cannot be enumerated.  Safe here because every protected route
# requires a bearer token -- there is no cookie for a browser to send along.
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

CurrentUser = Depends(auth.current_user)


@app.on_event("startup")
def _startup() -> None:
    config.validate()
    config.ensure_dirs()
    db.init_schema()
    logger.info("Schema ready. OCR %s.",
                "enabled" if config.ENABLE_OCR else "disabled")


@app.get("/health")
def health() -> dict:
    """Liveness plus the two facts the app's Settings screen shows."""
    try:
        db.one("SELECT 1 AS ok")
        database = "connected"
    except Exception as exc:                          # noqa: BLE001
        logger.warning("health: database unreachable: %s", exc)
        database = "unreachable"
    return {"status": "ok" if database == "connected" else "degraded",
            "database": database,
            "ocr_enabled": config.ENABLE_OCR,
            "ocr_available": ocr.available(),
            "storage_backend": config.STORAGE_BACKEND,
            "version": app.version}


@app.get("/layouts")
def layouts() -> dict:
    return {"layouts": layout_info()}


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------

def _public_user(row: dict) -> dict:
    return {"id": row["id"], "email": row["email"],
            "full_name": row["full_name"], "role": row["role"],
            "institution_id": row.get("institution_id"),
            "institution_name": row.get("institution_name")}


@app.post("/auth/signup", status_code=status.HTTP_201_CREATED)
def signup(body: SignUp) -> dict:
    if len(body.password.encode("utf-8")) > auth.MAX_PASSWORD_BYTES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Password is too long; use 72 bytes or fewer.")
    email = body.email.strip().lower()
    if db.one("SELECT 1 FROM users WHERE lower(email)=%s", (email,)):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "An account with that email already exists.")

    with db.conn() as c:
        institution_id = None
        if body.institution_name and body.institution_name.strip():
            institution_id = c.execute(
                "INSERT INTO institutions (name) VALUES (%s) RETURNING id",
                (body.institution_name.strip(),)).fetchone()["id"]
        user = c.execute(
            "INSERT INTO users (email, password_hash, full_name, institution_id,"
            " role) VALUES (%s,%s,%s,%s,'admin')"
            " RETURNING id, email, full_name, role, institution_id",
            (email, auth.hash_password(body.password), body.full_name.strip(),
             institution_id)).fetchone()
        db.audit(c, user["id"], "auth.signup", "user", user["id"])

    user["institution_name"] = (body.institution_name or "").strip() or None
    return {"token": auth.make_token(user["id"]), "user": _public_user(user)}


@app.post("/auth/login")
def login(body: SignIn) -> dict:
    row = db.one(
        "SELECT u.id, u.email, u.full_name, u.role, u.institution_id,"
        " u.password_hash, i.name AS institution_name FROM users u"
        " LEFT JOIN institutions i ON i.id = u.institution_id"
        " WHERE lower(u.email)=%s", (body.email.strip().lower(),))
    # One message for both unknown-email and wrong-password, so the response
    # cannot be used to enumerate which addresses have accounts.
    if row is None or not auth.verify_password(body.password, row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Incorrect email or password.")
    db.execute("UPDATE users SET last_login_at=now() WHERE id=%s", (row["id"],))
    return {"token": auth.make_token(row["id"]), "user": _public_user(row)}


@app.get("/auth/me")
def me(user: dict = CurrentUser) -> dict:
    return {"user": _public_user(user)}


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

def _owned_test(test_id: int, user: dict) -> dict:
    """Fetch a test the caller owns, or 404.

    404 rather than 403 for someone else's test: confirming a row exists is
    itself a leak.
    """
    row = db.one(
        "SELECT t.*, i.name AS institution_name,"
        " (SELECT count(*) FROM answer_keys k WHERE k.test_id=t.id) AS key_count,"
        " (SELECT count(*) FROM submissions s WHERE s.test_id=t.id) AS submission_count"
        " FROM tests t LEFT JOIN institutions i ON i.id=t.institution_id"
        " WHERE t.id=%s AND t.user_id=%s", (test_id, user["id"]))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Test not found.")
    return row


@app.get("/tests")
def list_tests(user: dict = CurrentUser, q: str | None = None,
               limit: int = Query(100, ge=1, le=500)) -> dict:
    sql = ("SELECT t.*,"
           " (SELECT count(*) FROM answer_keys k WHERE k.test_id=t.id) AS key_count,"
           " (SELECT count(*) FROM submissions s WHERE s.test_id=t.id) AS submission_count"
           " FROM tests t WHERE t.user_id=%s")
    params: list = [user["id"]]
    if q:
        sql += " AND (t.name ILIKE %s OR coalesce(t.subject,'') ILIKE %s)"
        params += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY t.created_at DESC LIMIT %s"
    params.append(limit)
    return {"tests": db.query(sql, tuple(params))}


@app.post("/tests", status_code=status.HTTP_201_CREATED)
def create_test(body: TestIn, user: dict = CurrentUser) -> dict:
    with db.conn() as c:
        row = c.execute(
            "INSERT INTO tests (user_id, institution_id, name, subject,"
            " exam_date, layout, total_questions, options, marks_correct,"
            " marks_wrong, marks_blank, ambiguous_policy, floor_at_zero)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (user["id"], user.get("institution_id"), body.name.strip(),
             body.subject, body.exam_date, body.layout, body.total_questions,
             body.options, body.marks_correct, body.marks_wrong,
             body.marks_blank, body.ambiguous_policy, body.floor_at_zero)
        ).fetchone()
        db.audit(c, user["id"], "test.created", "test", row["id"],
                 {"name": row["name"], "layout": row["layout"]})
    row["key_count"] = 0
    row["submission_count"] = 0
    return {"test": row}


@app.get("/tests/{test_id}")
def get_test(test_id: int, user: dict = CurrentUser) -> dict:
    return {"test": _owned_test(test_id, user)}


@app.put("/tests/{test_id}")
def update_test(test_id: int, body: TestIn, user: dict = CurrentUser) -> dict:
    _owned_test(test_id, user)
    with db.conn() as c:
        row = c.execute(
            "UPDATE tests SET name=%s, subject=%s, exam_date=%s, layout=%s,"
            " total_questions=%s, options=%s, marks_correct=%s, marks_wrong=%s,"
            " marks_blank=%s, ambiguous_policy=%s, floor_at_zero=%s,"
            " updated_at=now() WHERE id=%s AND user_id=%s RETURNING *",
            (body.name.strip(), body.subject, body.exam_date, body.layout,
             body.total_questions, body.options, body.marks_correct,
             body.marks_wrong, body.marks_blank, body.ambiguous_policy,
             body.floor_at_zero, test_id, user["id"])).fetchone()
        db.audit(c, user["id"], "test.updated", "test", test_id)
    return {"test": row}


@app.delete("/tests/{test_id}")
def delete_test(test_id: int, user: dict = CurrentUser) -> dict:
    _owned_test(test_id, user)
    with db.conn() as c:
        # Answer key, submissions, results and reports go with it via ON
        # DELETE CASCADE; the audit row stays.
        c.execute("DELETE FROM tests WHERE id=%s AND user_id=%s",
                  (test_id, user["id"]))
        db.audit(c, user["id"], "test.deleted", "test", test_id)
    return {"deleted": True}


# --------------------------------------------------------------------------
# Answer keys
# --------------------------------------------------------------------------

@app.get("/tests/{test_id}/answer-key")
def get_answer_key(test_id: int, user: dict = CurrentUser) -> dict:
    test = _owned_test(test_id, user)
    rows = db.query(
        "SELECT question_no, correct_option, marks FROM answer_keys"
        " WHERE test_id=%s ORDER BY question_no", (test_id,))
    return {"test_id": test_id, "total_questions": test["total_questions"],
            "entries": rows, "count": len(rows)}


@app.put("/tests/{test_id}/answer-key")
def put_answer_key(test_id: int, body: AnswerKeyIn,
                   user: dict = CurrentUser) -> dict:
    """Replace the test's answer key.

    Validated against the test's own option labels and question count, because
    a key with an option the sheet does not have can never match and would
    silently mark every student wrong.
    """
    test = _owned_test(test_id, user)
    allowed = {o.strip().upper() for o in str(test["options"]).split(",") if o.strip()}
    total = int(test["total_questions"])

    seen: set[int] = set()
    cleaned: list[tuple[int, str, float | None]] = []
    for e in body.entries:
        opt = e.correct_option.strip().upper()
        if e.question_no > total:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Question {e.question_no} is beyond this test's "
                f"{total} questions.")
        if allowed and opt not in allowed:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Question {e.question_no}: '{e.correct_option}' is not one of "
                f"{', '.join(sorted(allowed))}.")
        if e.question_no in seen:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Question {e.question_no} appears twice in the answer key.")
        seen.add(e.question_no)
        cleaned.append((e.question_no, opt, e.marks))

    with db.conn() as c:
        c.execute("DELETE FROM answer_keys WHERE test_id=%s", (test_id,))
        if cleaned:
            with c.cursor() as cur:
                cur.executemany(
                    "INSERT INTO answer_keys (test_id, question_no,"
                    " correct_option, marks) VALUES (%s,%s,%s,%s)",
                    [(test_id, q, o, m) for q, o, m in cleaned])
        # A test with a key is ready to scan against; without one it is a draft.
        c.execute("UPDATE tests SET status=%s, updated_at=now() WHERE id=%s",
                  ("ready" if cleaned else "draft", test_id))
        db.audit(c, user["id"], "answer_key.replaced", "test", test_id,
                 {"entries": len(cleaned)})
    return {"test_id": test_id, "count": len(cleaned)}


# --------------------------------------------------------------------------
# Scan
# --------------------------------------------------------------------------

@app.post("/tests/{test_id}/scan")
async def scan(test_id: int, file: UploadFile = File(...),
               user: dict = CurrentUser) -> dict:
    """Upload one OMR sheet and get the stored, evaluated result back.

    The answer key is read from Neon inside the pipeline using *test_id*; the
    client cannot influence what the sheet is graded against.
    """
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "The uploaded file was empty.")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Image is larger than {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")

    # The test lookup (with its answer-key count folded in via a subquery, so
    # it costs no extra round-trip) decides whether a submission row should
    # exist at all -- a rejected scan must not leave an orphan 'processing'
    # row, so this stays its own query, ahead of the insert.
    test = _owned_test(test_id, user)
    if not test["key_count"]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This test has no answer key yet. Add the answer key before scanning.")

    submission_id = db.execute(
        "INSERT INTO submissions (test_id, user_id, status)"
        " VALUES (%s,%s,'processing') RETURNING id",
        (test_id, user["id"]))["id"]

    try:
        image = pipeline.decode(data)
        path = pipeline.save_upload(data, submission_id, file.filename or "")
        result = pipeline.process(submission_id, test, image, user["id"],
                                  image_path=path)
        # Candidate OCR is handed to a worker thread rather than to
        # BackgroundTasks: the latter runs before the connection is released,
        # so a second scan queues behind the first one's ~30s of OCR. The
        # client polls GET /results/{id} for the details.
        if config.ENABLE_OCR:
            pipeline.queue_candidate_ocr(submission_id)
    except SheetUnreadable as exc:
        # The engine refused the sheet. That is a real, reportable outcome, so
        # the submission is kept as a failed row with the engine's own hint.
        db.execute(
            "UPDATE submissions SET status='failed', error_reason=%s,"
            " error_hint=%s, processed_at=now() WHERE id=%s",
            (exc.reason, exc.hint, submission_id))
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {
            "message": exc.hint, "reason": exc.reason,
            "submission_id": submission_id,
        })
    except Exception as exc:                          # noqa: BLE001
        logger.exception("scan failed for submission %s", submission_id)
        db.execute(
            "UPDATE submissions SET status='failed', error_reason='server_error',"
            " error_hint=%s, processed_at=now() WHERE id=%s",
            (str(exc)[:400], submission_id))
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            "Could not process that sheet. Please try again.")

    result["test"] = {"id": test["id"], "name": test["name"],
                      "subject": test["subject"]}
    return result


# --------------------------------------------------------------------------
# Results / history
# --------------------------------------------------------------------------

def _owned_submission(submission_id: int, user: dict) -> dict:
    row = db.one("SELECT * FROM submissions WHERE id=%s AND user_id=%s",
                 (submission_id, user["id"]))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found.")
    return row


@app.get("/results")
def list_results(user: dict = CurrentUser,
                 q: str | None = None,
                 test_id: int | None = None,
                 status_filter: str | None = Query(None, alias="status"),
                 sort: str = Query("recent"),
                 limit: int = Query(50, ge=1, le=200),
                 offset: int = Query(0, ge=0)) -> dict:
    """History: one row per submission, newest first by default."""
    sql = [
        "SELECT s.id AS submission_id, s.status, s.created_at, s.processed_at,",
        " s.error_reason, s.error_hint, s.answered_count, s.processing_ms,",
        " s.layout_used, s.review_questions,",
        " t.id AS test_id, t.name AS test_name, t.subject,",
        " o.roll_no, o.student_name, o.class_std, o.section,",
        " o.registration_no,",
        " e.total_marks, e.max_marks, e.percentage, e.grade,",
        " e.correct_count, e.wrong_count, e.unattempted_count,",
        " e.invalid_count, e.evaluated_at",
        " FROM submissions s",
        " JOIN tests t ON t.id = s.test_id",
        " LEFT JOIN ocr_results o ON o.submission_id = s.id",
        " LEFT JOIN evaluations e ON e.submission_id = s.id",
        " WHERE s.user_id = %s",
    ]
    params: list = [user["id"]]
    if test_id:
        sql.append(" AND s.test_id = %s")
        params.append(test_id)
    if status_filter:
        sql.append(" AND s.status = %s")
        params.append(status_filter)
    if q:
        sql.append(" AND (coalesce(o.student_name,'') ILIKE %s"
                   " OR coalesce(o.roll_no,'') ILIKE %s"
                   " OR t.name ILIKE %s)")
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]

    order = {
        "recent": " ORDER BY s.created_at DESC",
        "oldest": " ORDER BY s.created_at ASC",
        "score_high": " ORDER BY e.percentage DESC NULLS LAST",
        "score_low": " ORDER BY e.percentage ASC NULLS LAST",
        "name": " ORDER BY o.student_name ASC NULLS LAST",
        "roll": " ORDER BY o.roll_no ASC NULLS LAST",
    }.get(sort, " ORDER BY s.created_at DESC")
    sql.append(order)
    sql.append(" LIMIT %s OFFSET %s")
    params += [limit, offset]

    # The page and its total are independent, so they share one round-trip
    # rather than costing ~1s each against Neon.
    with db.conn() as c:
        with c.pipeline():
            rows_cur = c.execute("".join(sql), tuple(params))
            total_cur = c.execute(
                "SELECT count(*) AS n FROM submissions WHERE user_id=%s",
                (user["id"],))
            rows = rows_cur.fetchall()
            total = total_cur.fetchone()["n"]
    return {"results": rows, "limit": limit, "offset": offset, "total": total}


@app.get("/results/{submission_id}")
def get_result(submission_id: int, user: dict = CurrentUser) -> dict:
    """Everything one submission produced: candidate, totals, every question."""
    submission = _owned_submission(submission_id, user)
    test = db.one("SELECT t.*, i.name AS institution_name FROM tests t"
                  " LEFT JOIN institutions i ON i.id=t.institution_id"
                  " WHERE t.id=%s", (submission["test_id"],))
    candidate = db.one("SELECT * FROM ocr_results WHERE submission_id=%s",
                       (submission_id,)) or {}
    evaluation = db.one("SELECT * FROM evaluations WHERE submission_id=%s",
                        (submission_id,))
    items = db.query(
        "SELECT question_no, subject, marked_option, expected_option, status,"
        " marks, needs_review, note FROM evaluation_items"
        " WHERE evaluation_id=%s ORDER BY question_no",
        (evaluation["id"],)) if evaluation else []
    detected = db.query(
        "SELECT question_no, subject, marked_option, verdict, confidence,"
        " needs_review FROM detected_answers WHERE submission_id=%s"
        " ORDER BY question_no", (submission_id,))
    reports = db.query(
        "SELECT id, kind, file_size, created_at FROM reports"
        " WHERE submission_id=%s ORDER BY created_at DESC", (submission_id,))

    # raw_lines is debug-grade OCR output; it stays in the DB but is not worth
    # shipping to a phone on every result open.
    candidate.pop("raw_lines", None)
    return {"submission": submission, "test": test, "candidate": candidate,
            "evaluation": evaluation, "items": items, "detected": detected,
            "reports": reports}


@app.put("/results/{submission_id}/candidate")
def edit_candidate(submission_id: int, body: CandidateIn,
                   user: dict = CurrentUser) -> dict:
    """Correct the OCR-extracted candidate details before reporting.

    The `*_raw` columns keep what PaddleOCR originally read, so an edit never
    destroys the machine's reading.
    """
    _owned_submission(submission_id, user)
    with db.conn() as c:
        row = c.execute(
            "INSERT INTO ocr_results (submission_id, roll_no, student_name,"
            " class_std, section, registration_no, edited_by, edited_at)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,now())"
            " ON CONFLICT (submission_id) DO UPDATE SET"
            " roll_no=EXCLUDED.roll_no, student_name=EXCLUDED.student_name,"
            " class_std=EXCLUDED.class_std, section=EXCLUDED.section,"
            " registration_no=EXCLUDED.registration_no,"
            " edited_by=EXCLUDED.edited_by, edited_at=now()"
            " RETURNING *",
            (submission_id, body.roll_no, body.student_name, body.class_std,
             body.section, body.registration_no, user["id"])).fetchone()
        db.audit(c, user["id"], "candidate.edited", "submission", submission_id,
                 body.model_dump())
    row.pop("raw_lines", None)
    return {"candidate": row}


@app.post("/results/{submission_id}/answers")
def override_answers(submission_id: int, body: list[AnswerOverride],
                     user: dict = CurrentUser) -> dict:
    """Correct one or more detected answers, then re-score from stored data.

    Re-reads the key and the scheme from Neon and re-runs the same marking
    code, so a manual fix produces a total computed exactly like an automatic
    one -- no second scoring path to drift.
    """
    submission = _owned_submission(submission_id, user)
    test = db.one("SELECT * FROM tests WHERE id=%s", (submission["test_id"],))
    allowed = {o.strip().upper() for o in str(test["options"]).split(",") if o.strip()}

    for ov in body:
        if ov.marked_option is not None:
            opt = ov.marked_option.strip().upper()
            if allowed and opt not in allowed:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    f"Question {ov.question_no}: '{ov.marked_option}' is not "
                    f"one of {', '.join(sorted(allowed))}.")

    with db.conn() as c:
        for ov in body:
            opt = ov.marked_option.strip().upper() if ov.marked_option else None
            # A human-entered answer is authoritative: mark it CONFIDENT and
            # clear the review flag, otherwise it would stay flagged forever.
            c.execute(
                "UPDATE detected_answers SET marked_option=%s,"
                " verdict=%s, needs_review=FALSE"
                " WHERE submission_id=%s AND question_no=%s",
                (opt, "MANUAL" if opt else "BLANK", submission_id,
                 ov.question_no))
        db.audit(c, user["id"], "answers.overridden", "submission",
                 submission_id, {"questions": [o.question_no for o in body]})

    return {"evaluation": _rescore(submission_id, test, user["id"])}


def _rescore(submission_id: int, test: dict, user_id: int) -> dict:
    """Re-apply the test's marking scheme to the stored detected answers."""
    from .omr_engine import apply_scheme

    detected = db.query(
        "SELECT question_no, subject, marked_option, verdict, needs_review"
        " FROM detected_answers WHERE submission_id=%s ORDER BY question_no",
        (submission_id,))
    answer_key = pipeline.fetch_answer_key(test["id"])
    scheme = pipeline.scheme_from_test(test)

    score = apply_scheme(
        [{"q": d["question_no"], "subject": d["subject"],
          "marked": d["marked_option"],
          "status": pipeline._reader_status(d["verdict"]),
          "needs_review": d["needs_review"]} for d in detected],
        answer_key, scheme)

    max_marks = float(score.max_score)
    percentage = (round(float(score.total) / max_marks * 100, 2)
                  if max_marks else 0.0)

    with db.conn() as c:
        row = c.execute(
            "UPDATE evaluations SET correct_count=%s, wrong_count=%s,"
            " unattempted_count=%s, invalid_count=%s, unscored_count=%s,"
            " total_marks=%s, max_marks=%s, percentage=%s, grade=%s,"
            " subject_scores=%s, evaluated_at=now()"
            " WHERE submission_id=%s RETURNING *",
            (score.correct, score.wrong, score.unattempted, score.invalid,
             score.unscored, float(score.total), max_marks, percentage,
             pipeline.grade_for(percentage), json.dumps(score.subject_scores),
             submission_id)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "This submission has no evaluation to update.")
        # Batched into one round-trip: these three statements are all
        # independent of each other once evaluation_id is known.
        with c.pipeline():
            c.execute("DELETE FROM evaluation_items WHERE evaluation_id=%s",
                      (row["id"],))
            with c.cursor() as cur:
                cur.executemany(
                    "INSERT INTO evaluation_items (evaluation_id, question_no,"
                    " subject, marked_option, expected_option, status, marks,"
                    " needs_review, note) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    [(row["id"], o.q, o.subject, o.marked, o.expected, o.status,
                      float(o.marks), o.needs_review, o.note)
                     for o in score.outcomes])
            c.execute(
                "UPDATE submissions SET review_questions=%s WHERE id=%s",
                ([d["question_no"] for d in detected if d["needs_review"]],
                 submission_id))
            db.audit(c, user_id, "result.rescored", "submission", submission_id,
                     {"total": float(score.total), "percentage": percentage})
    return row


@app.delete("/results/{submission_id}")
def delete_result(submission_id: int, user: dict = CurrentUser) -> dict:
    submission = _owned_submission(submission_id, user)
    # Reports CASCADE-delete with the submission, but that only drops the
    # row -- its file_path blob is not referenced from anywhere once the row
    # is gone, so it has to be collected before the row that names it is.
    report_paths = [r["file_path"] for r in db.query(
        "SELECT file_path FROM reports WHERE submission_id=%s", (submission_id,))
        if r["file_path"]]

    with db.conn() as c:
        c.execute("DELETE FROM submissions WHERE id=%s AND user_id=%s",
                  (submission_id, user["id"]))
        db.audit(c, user["id"], "result.deleted", "submission", submission_id)
    # Best-effort: a leftover file is harmless, a 500 on delete is not.
    for key in ("image_path", "annotated_path"):
        blobs.delete(submission.get(key))
    for path in report_paths:
        blobs.delete(path)
    return {"deleted": True}


@app.get("/results/{submission_id}/sheet")
def result_sheet(submission_id: int, user: dict = CurrentUser) -> Response:
    """The original scanned image, for the review screen."""
    submission = _owned_submission(submission_id, user)
    data = blobs.load(submission.get("image_path"))
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "The scanned image is no longer on the server.")
    ctype = blobs.content_type(submission.get("image_path"), "image/jpeg")
    return Response(content=data, media_type=ctype)


@app.get("/results/{submission_id}/annotated")
def result_annotated(submission_id: int, user: dict = CurrentUser) -> Response:
    """The sheet with every detected bubble ringed by the engine.

    Green where the marked option matches the answer key, red where it does
    not, with the expected option drawn on the ones that were missed. This is
    the image a teacher checks the machine's reading against.
    """
    submission = _owned_submission(submission_id, user)
    data = blobs.load(submission.get("annotated_path"))
    if data is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No review overlay was stored for this sheet.")
    return Response(content=data, media_type="image/jpeg")


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------

@app.post("/results/{submission_id}/report", status_code=status.HTTP_201_CREATED)
def create_report(submission_id: int, user: dict = CurrentUser) -> dict:
    """Generate the student result PDF and record its metadata."""
    submission = _owned_submission(submission_id, user)
    evaluation = db.one("SELECT * FROM evaluations WHERE submission_id=%s",
                        (submission_id,))
    if evaluation is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This sheet has no result yet, so there is nothing to report.")

    test = db.one("SELECT t.*, i.name AS institution_name FROM tests t"
                  " LEFT JOIN institutions i ON i.id=t.institution_id"
                  " WHERE t.id=%s", (submission["test_id"],))
    candidate = db.one("SELECT * FROM ocr_results WHERE submission_id=%s",
                       (submission_id,)) or {}
    items = db.query(
        "SELECT question_no, subject, marked_option, expected_option, status,"
        " marks FROM evaluation_items WHERE evaluation_id=%s"
        " ORDER BY question_no", (evaluation["id"],))

    pdf_bytes = report.build_student_report(test, submission, candidate,
                                            evaluation, items)
    token = blobs.save(pdf_bytes, config.REPORT_DIR,
                       f"report_sub_{submission_id}.pdf",
                       content_type="application/pdf")
    size = len(pdf_bytes)

    with db.conn() as c:
        row = c.execute(
            "INSERT INTO reports (submission_id, test_id, user_id, kind,"
            " file_path, file_size) VALUES (%s,%s,%s,'student',%s,%s)"
            " RETURNING id, kind, file_size, created_at",
            (submission_id, test["id"], user["id"], token, size)).fetchone()
        db.audit(c, user["id"], "report.generated", "submission",
                 submission_id, {"report_id": row["id"], "bytes": size})
    return {"report": row}


@app.get("/reports")
def list_reports(user: dict = CurrentUser,
                 limit: int = Query(50, ge=1, le=200)) -> dict:
    rows = db.query(
        "SELECT r.id, r.kind, r.file_size, r.created_at, r.submission_id,"
        " t.name AS test_name, o.student_name, o.roll_no"
        " FROM reports r"
        " LEFT JOIN tests t ON t.id = r.test_id"
        " LEFT JOIN ocr_results o ON o.submission_id = r.submission_id"
        " WHERE r.user_id=%s ORDER BY r.created_at DESC LIMIT %s",
        (user["id"], limit))
    return {"reports": rows}


@app.get("/reports/{report_id}/download")
def download_report(report_id: int, user: dict = CurrentUser) -> Response:
    row = db.one("SELECT * FROM reports WHERE id=%s AND user_id=%s",
                 (report_id, user["id"]))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found.")
    data = blobs.load(row.get("file_path"))
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "The report file is no longer on the server. "
                            "Generate it again.")
    filename = f"report_{report_id}.pdf"
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------

@app.get("/dashboard")
def dashboard(user: dict = CurrentUser) -> dict:
    """The numbers and recent activity the home screen shows.

    The three queries are independent, so they are pipelined into a single
    round-trip: run back to back against Neon they cost ~1s each, which is
    most of the time the home screen took to appear.
    """
    uid = user["id"]
    with db.conn() as c:
        with c.pipeline():
            stats_cur = c.execute(
                "SELECT"
                " (SELECT count(*) FROM tests WHERE user_id=%(u)s) AS tests,"
                " (SELECT count(*) FROM submissions WHERE user_id=%(u)s) AS scans,"
                " (SELECT count(*) FROM submissions WHERE user_id=%(u)s"
                "    AND status='completed') AS completed,"
                " (SELECT count(*) FROM submissions WHERE user_id=%(u)s"
                "    AND status='failed') AS failed,"
                " (SELECT count(*) FROM reports WHERE user_id=%(u)s) AS reports,"
                " (SELECT round(avg(e.percentage),2) FROM evaluations e"
                "    JOIN submissions s ON s.id=e.submission_id"
                "    WHERE s.user_id=%(u)s) AS avg_percentage,"
                " (SELECT count(*) FROM submissions WHERE user_id=%(u)s"
                "    AND created_at > now() - interval '7 days') AS scans_7d",
                {"u": uid})

            recent_cur = c.execute(
                "SELECT s.id AS submission_id, s.status, s.created_at,"
                " t.name AS test_name, o.student_name, o.roll_no,"
                " e.percentage, e.grade, e.total_marks, e.max_marks"
                " FROM submissions s JOIN tests t ON t.id=s.test_id"
                " LEFT JOIN ocr_results o ON o.submission_id=s.id"
                " LEFT JOIN evaluations e ON e.submission_id=s.id"
                " WHERE s.user_id=%s ORDER BY s.created_at DESC LIMIT 5",
                (uid,))

            # Per-test rollup, for the dashboard's "performance by test" list.
            by_test_cur = c.execute(
                "SELECT t.id, t.name, count(e.id) AS evaluated,"
                " round(avg(e.percentage),2) AS avg_percentage,"
                " max(e.percentage) AS best_percentage"
                " FROM tests t"
                " LEFT JOIN evaluations e ON e.test_id=t.id"
                " WHERE t.user_id=%s GROUP BY t.id, t.name"
                " ORDER BY max(e.evaluated_at) DESC NULLS LAST LIMIT 5",
                (uid,))

            stats = stats_cur.fetchone()
            recent = recent_cur.fetchall()
            by_test = by_test_cur.fetchall()

    return {"stats": stats, "recent": recent, "by_test": by_test,
            "user": _public_user(user)}


@app.get("/tests/{test_id}/results")
def test_results(test_id: int, user: dict = CurrentUser) -> dict:
    """Test-wise retrieval: every candidate's result for one test, ranked."""
    _owned_test(test_id, user)
    rows = db.query(
        "SELECT s.id AS submission_id, s.status, s.created_at,"
        " o.roll_no, o.student_name, o.class_std, o.section,"
        " e.total_marks, e.max_marks, e.percentage, e.grade,"
        " e.correct_count, e.wrong_count, e.unattempted_count"
        " FROM submissions s"
        " LEFT JOIN ocr_results o ON o.submission_id=s.id"
        " LEFT JOIN evaluations e ON e.submission_id=s.id"
        " WHERE s.test_id=%s AND s.user_id=%s"
        " ORDER BY e.percentage DESC NULLS LAST, s.created_at DESC",
        (test_id, user["id"]))
    summary = db.one(
        "SELECT count(e.id) AS evaluated, round(avg(e.percentage),2) AS avg_pct,"
        " max(e.percentage) AS max_pct, min(e.percentage) AS min_pct"
        " FROM evaluations e JOIN submissions s ON s.id=e.submission_id"
        " WHERE e.test_id=%s AND s.user_id=%s", (test_id, user["id"]))
    return {"results": rows, "summary": summary}


@app.get("/audit")
def audit_trail(user: dict = CurrentUser,
                limit: int = Query(100, ge=1, le=500)) -> dict:
    return {"events": db.query(
        "SELECT id, action, entity, entity_id, detail, created_at"
        " FROM audit_log WHERE user_id=%s ORDER BY created_at DESC LIMIT %s",
        (user["id"], limit))}
