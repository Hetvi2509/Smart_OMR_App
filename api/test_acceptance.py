"""The critical acceptance test, run against the real Neon database.

    signup -> login -> create test -> add answer key -> scan a real sheet
    -> OMR pipeline -> OCR -> key fetched from Neon -> evaluated
    -> edit candidate -> override an answer and re-score
    -> generate report -> read it back from History

Run:  venv/Scripts/python.exe -m pytest test_acceptance.py -q
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.main import app

SAMPLE = Path(__file__).resolve().parent.parent / "backend_mcq_final" / "samples"
SHEET = SAMPLE / "neet_marked_sheet.jpg"
KEY_JSON = SAMPLE / "neet_answer_key.json"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def account(client):
    """A throwaway account, removed afterwards so reruns stay clean."""
    email = f"acceptance_{uuid.uuid4().hex[:10]}@omr-example.com"
    r = client.post("/auth/signup", json={
        "email": email, "password": "Str0ngPass!2026",
        "full_name": "Acceptance Runner",
        "institution_name": "Acceptance Institute"})
    assert r.status_code == 201, r.text
    token = r.json()["token"]
    user_id = r.json()["user"]["id"]
    yield {"email": email, "token": token, "id": user_id,
           "headers": {"Authorization": f"Bearer {token}"}}
    db.execute("DELETE FROM users WHERE id=%s", (user_id,))


def answer_key_entries() -> list[dict]:
    """The sample key, converted from 1-4 to A-D."""
    raw = json.loads(KEY_JSON.read_text())
    return [{"question_no": int(q), "correct_option": "ABCD"[int(v) - 1]}
            for q, v in raw.items()]


def test_health_and_database(client):
    body = client.get("/health").json()
    assert body["database"] == "connected", body
    assert body["status"] == "ok"


def test_login_rejects_wrong_password(client, account):
    r = client.post("/auth/login", json={"email": account["email"],
                                         "password": "not-the-password"})
    assert r.status_code == 401


def test_login_works(client, account):
    r = client.post("/auth/login", json={"email": account["email"],
                                         "password": "Str0ngPass!2026"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["institution_name"] == "Acceptance Institute"


def test_protected_route_needs_token(client):
    assert client.get("/tests").status_code == 401


@pytest.fixture(scope="module")
def test_id(client, account):
    r = client.post("/tests", headers=account["headers"], json={
        "name": "NEET Mock Acceptance", "subject": "PCB",
        "layout": "neet", "total_questions": 200,
        "marks_correct": 4, "marks_wrong": -1})
    assert r.status_code == 201, r.text
    return r.json()["test"]["id"]


def test_scan_blocked_without_answer_key(client, account, test_id):
    """A test with no key must refuse to scan rather than grade against nothing."""
    with SHEET.open("rb") as fh:
        r = client.post(f"/tests/{test_id}/scan", headers=account["headers"],
                        files={"file": ("sheet.jpg", fh, "image/jpeg")})
    assert r.status_code == 409, r.text


def test_answer_key_rejects_bad_option(client, account, test_id):
    r = client.put(f"/tests/{test_id}/answer-key", headers=account["headers"],
                   json={"entries": [{"question_no": 1, "correct_option": "Z"}]})
    assert r.status_code == 422


def test_answer_key_rejects_out_of_range_question(client, account, test_id):
    r = client.put(f"/tests/{test_id}/answer-key", headers=account["headers"],
                   json={"entries": [{"question_no": 9999,
                                      "correct_option": "A"}]})
    assert r.status_code == 422


def test_add_answer_key(client, account, test_id):
    entries = answer_key_entries()
    r = client.put(f"/tests/{test_id}/answer-key", headers=account["headers"],
                   json={"entries": entries})
    assert r.status_code == 200, r.text
    assert r.json()["count"] == len(entries)
    # Stored against this test, and readable back.
    got = client.get(f"/tests/{test_id}/answer-key",
                     headers=account["headers"]).json()
    assert got["count"] == len(entries)


@pytest.fixture(scope="module")
def scan_result(client, account, test_id):
    with SHEET.open("rb") as fh:
        r = client.post(f"/tests/{test_id}/scan", headers=account["headers"],
                        files={"file": ("sheet.jpg", fh, "image/jpeg")})
    assert r.status_code == 200, r.text
    return r.json()


def test_scan_detected_and_scored(scan_result):
    """The engine's known-good numbers for this sheet, through the whole API."""
    assert scan_result["status"] == "completed"
    assert scan_result["layout"] == "NEET"
    assert scan_result["answered"] == 39
    score = scan_result["score"]
    # 39 marks read, all correct against the sample key: 39 * 4 = 156.
    assert score["correct"] == 39
    assert score["wrong"] == 0
    assert score["total"] == 156.0
    assert score["max"] == 800.0
    assert score["percentage"] == 19.5
    assert scan_result["key_questions"] == 200


def test_scan_stored_every_question(scan_result):
    n = db.one("SELECT count(*) AS n FROM detected_answers WHERE submission_id=%s",
               (scan_result["submission_id"],))["n"]
    assert n == 200


def test_unreadable_sheet_is_reported_not_crashed(client, account, test_id):
    """The engine's refusal must surface as a 422 with its reason."""
    bad = SAMPLE / "neet_cropped_reject.jpg"
    with bad.open("rb") as fh:
        r = client.post(f"/tests/{test_id}/scan", headers=account["headers"],
                        files={"file": ("bad.jpg", fh, "image/jpeg")})
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["reason"], detail
    # The failed attempt is still recorded, with the engine's hint.
    row = db.one("SELECT status, error_reason FROM submissions WHERE id=%s",
                 (detail["submission_id"],))
    assert row["status"] == "failed"


def test_non_image_upload_is_rejected(client, account, test_id):
    r = client.post(f"/tests/{test_id}/scan", headers=account["headers"],
                    files={"file": ("notes.txt", b"this is not an image",
                                    "text/plain")})
    assert r.status_code == 422


def test_annotated_overlay_is_stored_and_served(client, account, scan_result):
    """The engine's review overlay is rendered during the scan and served back.

    This is what lets a teacher check the machine's reading against the paper,
    so a result without it is only half a result.
    """
    sid = scan_result["submission_id"]
    row = db.one("SELECT annotated_path FROM submissions WHERE id=%s", (sid,))
    assert row["annotated_path"], "no overlay recorded for the submission"

    r = client.get(f"/results/{sid}/annotated", headers=account["headers"])
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "image/jpeg"
    # JPEG magic number: the bytes really are an image, not an error page.
    assert r.content[:2] == bytes([0xFF, 0xD8]), "response is not a JPEG"
    assert len(r.content) > 10_000, "overlay is suspiciously small"


def test_annotated_overlay_is_private(client, account, scan_result):
    """Another user cannot read someone else's sheet overlay."""
    import uuid as _uuid
    other = client.post("/auth/signup", json={
        "email": f"ovl_{_uuid.uuid4().hex[:8]}@omr-example.com",
        "password": "An0therPass!99", "full_name": "Other Viewer"}).json()
    headers = {"Authorization": f"Bearer {other['token']}"}
    try:
        r = client.get(f"/results/{scan_result['submission_id']}/annotated",
                       headers=headers)
        assert r.status_code == 404
    finally:
        db.execute("DELETE FROM users WHERE id=%s", (other["user"]["id"],))


def test_edit_candidate_details(client, account, scan_result):
    """OCR output is editable before the report, and the raw read is kept."""
    sid = scan_result["submission_id"]
    r = client.put(f"/results/{sid}/candidate", headers=account["headers"],
                   json={"roll_no": "R-2026-0042",
                         "student_name": "Priya Sharma",
                         "class_std": "12", "section": "B",
                         "registration_no": "REG99881"})
    assert r.status_code == 200, r.text
    cand = r.json()["candidate"]
    assert cand["student_name"] == "Priya Sharma"
    assert cand["edited_at"] is not None


def test_override_answer_rescores(client, account, scan_result):
    """A manual answer fix re-runs the same marking code and moves the total."""
    sid = scan_result["submission_id"]
    key = {e["question_no"]: e["correct_option"] for e in answer_key_entries()}
    # Question 200 was blank on this sheet; answering it correctly adds 4.
    r = client.post(f"/results/{sid}/answers", headers=account["headers"],
                    json=[{"question_no": 200,
                           "marked_option": key[200]}])
    assert r.status_code == 200, r.text
    ev = r.json()["evaluation"]
    assert float(ev["total_marks"]) == 160.0
    assert ev["correct_count"] == 40


def test_override_rejects_invalid_option(client, account, scan_result):
    r = client.post(f"/results/{scan_result['submission_id']}/answers",
                    headers=account["headers"],
                    json=[{"question_no": 5, "marked_option": "X"}])
    assert r.status_code == 422


def test_full_result_readback(client, account, scan_result):
    r = client.get(f"/results/{scan_result['submission_id']}",
                   headers=account["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["candidate"]["student_name"] == "Priya Sharma"
    assert len(body["items"]) == 200
    assert len(body["detected"]) == 200
    assert body["evaluation"]["grade"]


def test_generate_and_download_report(client, account, scan_result):
    sid = scan_result["submission_id"]
    r = client.post(f"/results/{sid}/report", headers=account["headers"])
    assert r.status_code == 201, r.text
    report_id = r.json()["report"]["id"]
    assert r.json()["report"]["file_size"] > 1000

    dl = client.get(f"/reports/{report_id}/download",
                    headers=account["headers"])
    assert dl.status_code == 200
    assert dl.content[:4] == b"%PDF"


def test_report_embeds_both_sheet_images(client, account, scan_result):
    """The PDF carries the overlay and the original scan.

    A printed result a student can dispute needs its evidence attached, so a
    report without the sheet images is incomplete.
    """
    sid = scan_result["submission_id"]
    r = client.post(f"/results/{sid}/report", headers=account["headers"])
    assert r.status_code == 201, r.text
    report_id = r.json()["report"]["id"]

    pdf = client.get(f"/reports/{report_id}/download",
                     headers=account["headers"]).content
    assert pdf[:4] == b"%PDF"
    # Two full-page photographs dominate the file; a text-only report is a
    # few tens of KB, so this size gap is the cheapest reliable signal.
    assert len(pdf) > 300_000, f"report looks image-less ({len(pdf)} bytes)"

    text = _pdf_text(pdf)
    assert "Answer Sheet" in text
    assert "As read by the scanner" in text
    assert "Original scan" in text


@pytest.mark.skipif(config.STORAGE_BACKEND != "db",
                    reason="blob accounting only applies to STORAGE_BACKEND=db")
def test_deleting_a_result_frees_its_blobs(client, account, test_id):
    """Deleting a submission must not leave its files behind in Postgres.

    Found by hand: the sheet and overlay were freed on delete, but a
    generated report's PDF was not, because `reports` rows CASCADE-delete
    with the submission and nothing collected the blob they pointed at
    first. On the disk backend that leak is an orphan file nobody notices;
    on the db backend it is a row in the user's own database that silently
    grows forever.
    """
    with SHEET.open("rb") as fh:
        r = client.post(f"/tests/{test_id}/scan", headers=account["headers"],
                        files={"file": ("sheet.jpg", fh, "image/jpeg")})
    assert r.status_code == 200, r.text
    sid = r.json()["submission_id"]

    rep = client.post(f"/results/{sid}/report", headers=account["headers"])
    assert rep.status_code == 201, rep.text

    before = db.one("SELECT count(*) AS n FROM file_blobs")["n"]
    assert before >= 3, "expected sheet + overlay + report blobs to exist"

    d = client.delete(f"/results/{sid}", headers=account["headers"])
    assert d.status_code == 200, d.text

    after = db.one("SELECT count(*) AS n FROM file_blobs")["n"]
    assert after == before - 3, (
        f"expected all 3 blobs (sheet, overlay, report) freed; "
        f"before={before} after={after}")


def _pdf_text(data: bytes) -> str:
    """All text in a PDF, or '' when no reader is installed."""
    try:
        import pypdfium2 as pdfium
    except ImportError:                               # pragma: no cover
        return ""
    import io
    doc = pdfium.PdfDocument(io.BytesIO(data))
    return chr(10).join(p.get_textpage().get_text_range() for p in doc)


def test_history_shows_the_result(client, account, scan_result):
    r = client.get("/results", headers=account["headers"],
                   params={"q": "Priya"})
    assert r.status_code == 200, r.text
    rows = r.json()["results"]
    ids = [row["submission_id"] for row in rows]
    assert scan_result["submission_id"] in ids
    row = next(x for x in rows if x["submission_id"] == scan_result["submission_id"])
    assert row["student_name"] == "Priya Sharma"
    assert float(row["total_marks"]) == 160.0


def test_history_sort_and_filter(client, account, test_id):
    r = client.get("/results", headers=account["headers"],
                   params={"test_id": test_id, "sort": "score_high",
                           "status": "completed"})
    assert r.status_code == 200
    assert all(x["status"] == "completed" for x in r.json()["results"])


def test_dashboard_counts(client, account):
    body = client.get("/dashboard", headers=account["headers"]).json()
    assert body["stats"]["tests"] >= 1
    assert body["stats"]["completed"] >= 1
    assert body["stats"]["reports"] >= 1
    assert len(body["recent"]) >= 1


def test_test_wise_results(client, account, test_id):
    body = client.get(f"/tests/{test_id}/results",
                      headers=account["headers"]).json()
    assert body["summary"]["evaluated"] >= 1
    assert any(r["student_name"] == "Priya Sharma" for r in body["results"])


def test_audit_trail_recorded(client, account):
    actions = {e["action"] for e in
               client.get("/audit", headers=account["headers"]).json()["events"]}
    assert {"auth.signup", "test.created", "answer_key.replaced",
            "scan.completed", "candidate.edited", "report.generated"} <= actions


def test_other_users_data_is_invisible(client, account, test_id):
    """Ownership is enforced, and a foreign id reads as 404, not 403."""
    other = client.post("/auth/signup", json={
        "email": f"other_{uuid.uuid4().hex[:8]}@omr-example.com",
        "password": "An0therPass!99", "full_name": "Other Teacher"}).json()
    headers = {"Authorization": f"Bearer {other['token']}"}
    try:
        assert client.get(f"/tests/{test_id}", headers=headers).status_code == 404
        assert client.get("/tests", headers=headers).json()["tests"] == []
    finally:
        db.execute("DELETE FROM users WHERE id=%s", (other["user"]["id"],))
