"""File storage for scanned sheets, overlays and PDF reports.

Two backends behind one interface, switched by STORAGE_BACKEND:

  "disk" (default, used for local dev): files live under config.STORAGE and
  the database stores a filesystem path. Fast, simple, and what the app has
  always done -- but a path is only meaningful on the machine that wrote it.

  "db": file bytes are written straight to Postgres (Neon) instead. This is
  for a host with no persistent disk -- Render's free tier wipes local files
  on every restart and redeploy, so a stored path would dangle. Neon is
  already the app's database and already free, so no third storage service
  needs an account. Sheets run a few hundred KB each; that is a fine fit for
  a BYTEA column and a poor fit for a service meant for terabytes.

Callers never touch a path or a row directly: `save()` returns an opaque
token to store in the existing *_path / file_path columns, and `load()` /
`serve()` take that token back. Which backend is active is invisible past
this module, so the rest of the app did not need to change shape -- only
pipeline.py, main.py and report.py's few read/write call sites did.
"""
from __future__ import annotations

import json
import mimetypes
import uuid
from pathlib import Path

from . import config, db

BACKEND = config.STORAGE_BACKEND  # "disk" | "db"

# A disk path never starts with this; a db-backend token always does. Lets
# load()/serve() tell the two apart even if BACKEND changes between the
# write and the read (e.g. mid-migration), so an old disk path still resolves.
_DB_PREFIX = "db:"


def save(data: bytes, directory: Path, filename: str, *, content_type: str | None = None) -> str:
    """Store *data* and return the token to persist in the database.

    *directory* and *filename* are used verbatim on the disk backend (callers
    already pick names like "sub_123.jpg"); on the db backend they are kept
    only as metadata, since the blob's identity is the token itself.
    """
    if BACKEND == "db":
        blob_id = uuid.uuid4().hex
        ctype = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        db.execute(
            "INSERT INTO file_blobs (id, filename, content_type, data)"
            " VALUES (%s,%s,%s,%s)",
            (blob_id, filename, ctype, data))
        return f"{_DB_PREFIX}{blob_id}"

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_bytes(data)
    return str(path)


def load(token: str | None) -> bytes | None:
    """The file's bytes, or None when *token* is empty or the file is gone."""
    if not token:
        return None
    if token.startswith(_DB_PREFIX):
        row = db.one("SELECT data FROM file_blobs WHERE id=%s",
                     (token[len(_DB_PREFIX):],))
        return bytes(row["data"]) if row else None
    path = Path(token)
    return path.read_bytes() if path.exists() else None


def exists(token: str | None) -> bool:
    if not token:
        return False
    if token.startswith(_DB_PREFIX):
        return db.one("SELECT 1 FROM file_blobs WHERE id=%s",
                      (token[len(_DB_PREFIX):],)) is not None
    return Path(token).exists()


def content_type(token: str | None, default: str = "application/octet-stream") -> str:
    if token and token.startswith(_DB_PREFIX):
        row = db.one("SELECT content_type FROM file_blobs WHERE id=%s",
                     (token[len(_DB_PREFIX):],))
        if row:
            return row["content_type"]
    return default


def delete(token: str | None) -> None:
    """Best-effort: a file that is already gone is not an error."""
    if not token:
        return
    if token.startswith(_DB_PREFIX):
        db.execute("DELETE FROM file_blobs WHERE id=%s", (token[len(_DB_PREFIX):],))
        return
    Path(token).unlink(missing_ok=True)


def local_path_for_cv2(token: str) -> tuple[str, "_TempCleanup | None"]:
    """A real filesystem path OpenCV / ReportLab can open, for *token*.

    Several call sites (`cv2.imread`, `ImageReader` for the PDF) take a path,
    not bytes. On the disk backend the token already is one. On the db
    backend the bytes are spooled to a temp file and handed back along with
    a cleanup handle the caller closes when done -- the temp file is deleted
    then, not left for the OS to reap.
    """
    if not token.startswith(_DB_PREFIX):
        return token, None

    import tempfile
    data = load(token)
    if data is None:
        raise FileNotFoundError(token)
    suffix = Path(_blob_filename(token) or "").suffix or ".bin"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(data)
    tmp.close()
    return tmp.name, _TempCleanup(tmp.name)


def _blob_filename(token: str) -> str | None:
    row = db.one("SELECT filename FROM file_blobs WHERE id=%s",
                 (token[len(_DB_PREFIX):],))
    return row["filename"] if row else None


class _TempCleanup:
    """Deletes its temp file once, on close() -- used as a context manager."""

    def __init__(self, path: str):
        self.path = path

    def close(self) -> None:
        Path(self.path).unlink(missing_ok=True)

    def __enter__(self) -> "_TempCleanup":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
