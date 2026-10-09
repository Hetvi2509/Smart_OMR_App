"""Read one submission's candidate details, as a standalone process.

    python -m app.ocr_job <submission_id>

Run out-of-process on purpose: paddle holds the GIL through inference, so doing
this inside the API server froze every other request for the duration of the
read. A subprocess cannot block the server's event loop.

Writes the result straight to Postgres and exits; the API only waits for it.
"""
from __future__ import annotations

import json
import logging
import sys

import cv2
import numpy as np

from . import blobs, db, ocr

logger = logging.getLogger("omr.ocr_job")


def run(submission_id: int) -> int:
    row = db.one("SELECT image_path FROM submissions WHERE id=%s", (submission_id,))
    if row is None:
        logger.error("submission %s not found", submission_id)
        return 1

    path = row.get("image_path")
    data = blobs.load(path)
    if data is None:
        # The sheet was deleted between the scan and this pass (or, on the db
        # backend, the blob row is gone).
        db.execute("UPDATE ocr_results SET status='failed' WHERE submission_id=%s",
                   (submission_id,))
        logger.error("image for submission %s is gone", submission_id)
        return 1

    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        db.execute("UPDATE ocr_results SET status='failed' WHERE submission_id=%s",
                   (submission_id,))
        logger.error("could not decode image for submission %s", submission_id)
        return 1

    candidate = ocr.extract_candidate(image)

    # CASE WHEN edited_at IS NULL: the operator may have typed the details in
    # while this pass was running, and a human entry always wins over the
    # machine's. The *_raw columns still record what OCR saw.
    db.execute(
        "UPDATE ocr_results SET"
        " roll_no = CASE WHEN edited_at IS NULL THEN %s ELSE roll_no END,"
        " student_name = CASE WHEN edited_at IS NULL THEN %s ELSE student_name END,"
        " class_std = CASE WHEN edited_at IS NULL THEN %s ELSE class_std END,"
        " section = CASE WHEN edited_at IS NULL THEN %s ELSE section END,"
        " registration_no = CASE WHEN edited_at IS NULL THEN %s"
        "   ELSE registration_no END,"
        " roll_no_raw=%s, student_name_raw=%s, class_std_raw=%s,"
        " section_raw=%s, registration_no_raw=%s,"
        " confidence=%s, raw_lines=%s, engine=%s, status=%s"
        " WHERE submission_id=%s",
        (candidate["roll_no"], candidate["student_name"],
         candidate["class_std"], candidate["section"],
         candidate["registration_no"],
         candidate["roll_no"], candidate["student_name"],
         candidate["class_std"], candidate["section"],
         candidate["registration_no"],
         candidate["confidence"], json.dumps(candidate["raw_lines"]),
         candidate["engine"],
         "done" if candidate["engine"] else "failed",
         submission_id))

    found = {k: candidate[k] for k in
             ("roll_no", "student_name", "class_std", "section",
              "registration_no") if candidate[k]}
    logger.info("submission %s: %s", submission_id, found or "no fields read")
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        return run(int(sys.argv[1]))
    except ValueError:
        print(f"not a submission id: {sys.argv[1]!r}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
