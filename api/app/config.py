"""Settings, read from the environment only.

The Neon credentials live here and nowhere else.  The mobile app never sees
them: it talks to this service, which talks to Postgres.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Minimal .env reader so `uvicorn app.main:app` works with no shell setup.

    Real environment variables win, so a deployment that sets them properly is
    unaffected by a stale .env left in the tree.
    """
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "")
JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
# Long-lived: a teacher scanning a stack of sheets should not be logged out
# mid-batch.  Revocation is by password change, which bumps the token version.
JWT_TTL_SECONDS = 60 * 60 * 24 * 30
ENABLE_OCR = os.environ.get("ENABLE_OCR", "1") not in ("0", "false", "False", "")

# Uploaded sheets, overlays and generated PDFs.
#
# STORAGE_BACKEND=disk (default): files live under STORAGE_DIR and the
# database stores a filesystem path. Right for local dev and for any host
# with a persistent disk.
#
# STORAGE_BACKEND=db: file bytes go into Postgres itself (see app/blobs.py).
# Required on a host with no persistent disk -- Render's free tier wipes
# local files on every restart/redeploy, so a stored path would point at
# nothing after the first one. Set this when deploying there.
STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "disk").strip().lower()

STORAGE = Path(os.environ.get("STORAGE_DIR", ROOT / "storage"))
UPLOAD_DIR = STORAGE / "uploads"
REPORT_DIR = STORAGE / "reports"
# The engine's review overlay: the scanned sheet with every detected bubble
# ringed. Written during the scan, served to the result screen.
ANNOTATED_DIR = STORAGE / "annotated"

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def ensure_dirs() -> None:
    if STORAGE_BACKEND == "db":
        return
    for d in (UPLOAD_DIR, REPORT_DIR, ANNOTATED_DIR):
        d.mkdir(parents=True, exist_ok=True)


def validate() -> None:
    """Fail at boot, not on the first request, when secrets are missing."""
    missing = [n for n, v in (("DATABASE_URL", DATABASE_URL),
                              ("JWT_SECRET", JWT_SECRET)) if not v]
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            f"Copy api/.env.example to api/.env and fill them in.")
