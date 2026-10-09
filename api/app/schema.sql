-- Neon PostgreSQL schema.  Applied idempotently at boot by db.init_schema().

CREATE TABLE IF NOT EXISTS institutions (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    code        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    id              BIGSERIAL PRIMARY KEY,
    institution_id  BIGINT REFERENCES institutions(id) ON DELETE SET NULL,
    email           TEXT NOT NULL,
    password_hash   TEXT NOT NULL,
    full_name       TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'teacher',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at   TIMESTAMPTZ
);
-- Case-insensitive uniqueness: Teacher@x.com and teacher@x.com are one person.
CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_key ON users (lower(email));

CREATE TABLE IF NOT EXISTS tests (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    institution_id  BIGINT REFERENCES institutions(id) ON DELETE SET NULL,
    name            TEXT NOT NULL,
    subject         TEXT,
    exam_date       DATE,
    layout          TEXT NOT NULL DEFAULT 'neet',
    total_questions INTEGER NOT NULL,
    options         TEXT NOT NULL DEFAULT 'A,B,C,D',
    -- Marking rules, stored as the shape omr_mcq.MarkingScheme.from_dict reads.
    marks_correct   NUMERIC(6,2) NOT NULL DEFAULT 4,
    marks_wrong     NUMERIC(6,2) NOT NULL DEFAULT -1,
    marks_blank     NUMERIC(6,2) NOT NULL DEFAULT 0,
    ambiguous_policy TEXT NOT NULL DEFAULT 'wrong',
    floor_at_zero   BOOLEAN NOT NULL DEFAULT TRUE,
    status          TEXT NOT NULL DEFAULT 'draft',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS tests_user_idx ON tests (user_id, created_at DESC);

-- The answer key is bound to its test by this FK plus the UNIQUE below:
-- one row per (test, question), so a key can never silently hold two answers
-- for one question, and deleting a test takes its key with it.
CREATE TABLE IF NOT EXISTS answer_keys (
    id          BIGSERIAL PRIMARY KEY,
    test_id     BIGINT NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    question_no INTEGER NOT NULL CHECK (question_no >= 1),
    correct_option TEXT NOT NULL,
    marks       NUMERIC(6,2),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (test_id, question_no)
);

CREATE TABLE IF NOT EXISTS submissions (
    id            BIGSERIAL PRIMARY KEY,
    test_id       BIGINT NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    image_path    TEXT,
    status        TEXT NOT NULL DEFAULT 'pending',
    error_reason  TEXT,
    error_hint    TEXT,
    layout_used   TEXT,
    answered_count INTEGER,
    review_questions INTEGER[] NOT NULL DEFAULT '{}',
    processing_ms INTEGER,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS submissions_user_idx ON submissions (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS submissions_test_idx ON submissions (test_id, created_at DESC);

-- Candidate identity.  `*_raw` is what PaddleOCR saw; the plain column is the
-- value in force after any human edit.  Keeping both means an edit is always
-- auditable against the machine's original reading.
CREATE TABLE IF NOT EXISTS ocr_results (
    id             BIGSERIAL PRIMARY KEY,
    submission_id  BIGINT NOT NULL UNIQUE REFERENCES submissions(id) ON DELETE CASCADE,
    roll_no        TEXT,
    student_name   TEXT,
    class_std      TEXT,
    section        TEXT,
    registration_no TEXT,
    roll_no_raw    TEXT,
    student_name_raw TEXT,
    class_std_raw  TEXT,
    section_raw    TEXT,
    registration_no_raw TEXT,
    confidence     NUMERIC(5,3),
    raw_lines      JSONB NOT NULL DEFAULT '[]',
    engine         TEXT,
    -- pending while the background OCR pass runs, then done | failed | skipped.
    status         TEXT NOT NULL DEFAULT 'pending',
    edited_by      BIGINT REFERENCES users(id) ON DELETE SET NULL,
    edited_at      TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS detected_answers (
    id            BIGSERIAL PRIMARY KEY,
    submission_id BIGINT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    question_no   INTEGER NOT NULL,
    subject       TEXT,
    marked_option TEXT,
    verdict       TEXT NOT NULL,
    confidence    NUMERIC(6,3),
    needs_review  BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (submission_id, question_no)
);

CREATE TABLE IF NOT EXISTS evaluations (
    id            BIGSERIAL PRIMARY KEY,
    submission_id BIGINT NOT NULL UNIQUE REFERENCES submissions(id) ON DELETE CASCADE,
    test_id       BIGINT NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    correct_count INTEGER NOT NULL DEFAULT 0,
    wrong_count   INTEGER NOT NULL DEFAULT 0,
    unattempted_count INTEGER NOT NULL DEFAULT 0,
    invalid_count INTEGER NOT NULL DEFAULT 0,
    unscored_count INTEGER NOT NULL DEFAULT 0,
    total_marks   NUMERIC(8,2) NOT NULL DEFAULT 0,
    max_marks     NUMERIC(8,2) NOT NULL DEFAULT 0,
    percentage    NUMERIC(6,2) NOT NULL DEFAULT 0,
    grade         TEXT,
    subject_scores JSONB NOT NULL DEFAULT '{}',
    -- Snapshot of the scheme used, so a later change to the test's marking
    -- rules cannot retroactively alter what this result says it scored.
    scheme_used   JSONB NOT NULL DEFAULT '{}',
    evaluated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS evaluations_test_idx ON evaluations (test_id);

-- Per-question outcome, the detail behind the totals above.
CREATE TABLE IF NOT EXISTS evaluation_items (
    id            BIGSERIAL PRIMARY KEY,
    evaluation_id BIGINT NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    question_no   INTEGER NOT NULL,
    subject       TEXT,
    marked_option TEXT,
    expected_option TEXT,
    status        TEXT NOT NULL,
    marks         NUMERIC(6,2) NOT NULL DEFAULT 0,
    needs_review  BOOLEAN NOT NULL DEFAULT FALSE,
    note          TEXT,
    UNIQUE (evaluation_id, question_no)
);

CREATE TABLE IF NOT EXISTS reports (
    id            BIGSERIAL PRIMARY KEY,
    submission_id BIGINT REFERENCES submissions(id) ON DELETE CASCADE,
    test_id       BIGINT REFERENCES tests(id) ON DELETE CASCADE,
    user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL DEFAULT 'student',
    file_path     TEXT,
    file_size     INTEGER,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS reports_user_idx ON reports (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT REFERENCES users(id) ON DELETE SET NULL,
    action      TEXT NOT NULL,
    entity      TEXT,
    entity_id   BIGINT,
    detail      JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS audit_user_idx ON audit_log (user_id, created_at DESC);

-- Additive migrations, safe to re-run: the CREATE TABLEs above are
-- IF NOT EXISTS, so a column added after a database was first created needs
-- its own statement here.
ALTER TABLE ocr_results ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS annotated_path TEXT;

-- File bytes, used when STORAGE_BACKEND=db (see app/blobs.py). Not used on
-- the disk backend, but always created: switching backends later needs
-- nothing more than restarting with a different STORAGE_BACKEND value.
CREATE TABLE IF NOT EXISTS file_blobs (
    id           TEXT PRIMARY KEY,
    filename     TEXT NOT NULL,
    content_type TEXT NOT NULL,
    data         BYTEA NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
