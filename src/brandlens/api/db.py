"""SQLite database access layer.

Implements the schema from docs/architecture/database-schema.md using the
built-in sqlite3 module. Every public function expects an open Connection
(obtained via get_conn) so callers control transaction boundaries.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Generator

# Reference DDL from database-schema.md, adapted with IF NOT EXISTS guards.
_DDL = """\
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS jobs (
    job_id              TEXT PRIMARY KEY,
    rubric_id           TEXT NOT NULL,
    input_type          TEXT NOT NULL
                            CHECK (input_type IN ('upload', 'url')),
    submission_url      TEXT,
    max_pages           INTEGER
                            CHECK (max_pages IS NULL OR max_pages > 0),
    status              TEXT NOT NULL
                            CHECK (status IN (
                                'queued', 'crawling', 'preprocessing',
                                'analyzing', 'scoring',
                                'completed', 'completed_with_errors', 'failed'
                            )),
    error_code          TEXT,
    error_message       TEXT,
    error_details_json  TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    CHECK (input_type <> 'url' OR submission_url IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS job_criteria (
    job_id        TEXT    NOT NULL,
    criterion_id  TEXT    NOT NULL,
    position      INTEGER NOT NULL CHECK (position >= 0),
    PRIMARY KEY (job_id, criterion_id),
    UNIQUE (job_id, position),
    FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS images (
    image_id        TEXT PRIMARY KEY,
    job_id          TEXT NOT NULL,
    ordinal         INTEGER NOT NULL CHECK (ordinal >= 0),
    source          TEXT NOT NULL,
    raw_path        TEXT,
    processed_path  TEXT,
    status          TEXT
                        CHECK (
                            status IS NULL OR
                            status IN ('scored', 'partial', 'failed', 'filtered_out')
                        ),
    reject_reason   TEXT
                        CHECK (
                            reject_reason IS NULL OR reject_reason IN (
                                'unsupported_format', 'too_many_pixels', 'animated',
                                'too_small', 'extreme_aspect_ratio', 'unprocessable'
                            )
                        ),
    width           INTEGER CHECK (width IS NULL OR width > 0),
    height          INTEGER CHECK (height IS NULL OR height > 0),
    color_mode      TEXT,
    measurements_json TEXT,
    overall_score   REAL
                        CHECK (
                            overall_score IS NULL OR
                            (overall_score >= 0 AND overall_score <= 100)
                        ),
    flagged         INTEGER CHECK (flagged IS NULL OR flagged IN (0, 1)),
    error_code      TEXT,
    error_message   TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE (job_id, ordinal),
    UNIQUE (image_id, job_id),
    FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE,
    CHECK (status <> 'filtered_out' OR reject_reason IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS criterion_scores (
    image_id      TEXT NOT NULL,
    criterion_id  TEXT NOT NULL,
    job_id        TEXT NOT NULL,
    score         REAL CHECK (score IS NULL OR (score >= 0 AND score <= 100)),
    weight        REAL NOT NULL CHECK (weight >= 0 AND weight <= 1),
    source        TEXT NOT NULL CHECK (source IN ('cv', 'vlm')),
    label         TEXT,
    explanation   TEXT,
    evidence_json TEXT,
    availability  TEXT NOT NULL CHECK (availability IN ('ok', 'unavailable_needs_review')),
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (image_id, criterion_id),
    FOREIGN KEY (image_id, job_id)
        REFERENCES images(image_id, job_id) ON DELETE CASCADE,
    FOREIGN KEY (job_id, criterion_id)
        REFERENCES job_criteria(job_id, criterion_id) ON DELETE CASCADE,
    CHECK (
        (availability = 'ok' AND score IS NOT NULL) OR
        (availability = 'unavailable_needs_review' AND score IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS feedback (
    feedback_id   TEXT PRIMARY KEY,
    image_id      TEXT NOT NULL,
    criterion_id  TEXT,
    verdict       TEXT NOT NULL CHECK (verdict IN ('agree', 'disagree')),
    comment       TEXT CHECK (comment IS NULL OR length(comment) <= 1000),
    created_at    TEXT NOT NULL,
    FOREIGN KEY (image_id) REFERENCES images(image_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_updated
    ON jobs(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_images_job_status
    ON images(job_id, status);
CREATE INDEX IF NOT EXISTS idx_feedback_image_criterion_created
    ON feedback(image_id, criterion_id, created_at DESC);
"""


def _now() -> str:
    dt = datetime.now(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def init_db(db_path: Path) -> None:
    """Create all tables and indexes if they do not already exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_DDL)


@contextmanager
def get_conn(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Yield a connection with FK enforcement, WAL mode, and auto commit/rollback."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_job(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    rubric_id: str,
    input_type: str = "upload",
) -> None:
    ts = _now()
    conn.execute(
        "INSERT INTO jobs (job_id, rubric_id, input_type, status, created_at, updated_at)"
        " VALUES (?, ?, ?, 'queued', ?, ?)",
        (job_id, rubric_id, input_type, ts, ts),
    )


def insert_job_criteria(
    conn: sqlite3.Connection,
    job_id: str,
    criterion_ids: list[str],
) -> None:
    conn.executemany(
        "INSERT INTO job_criteria (job_id, criterion_id, position) VALUES (?, ?, ?)",
        [(job_id, cid, pos) for pos, cid in enumerate(criterion_ids)],
    )


def create_image(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    ordinal: int,
    source: str,
    raw_path: str | None = None,
) -> str:
    image_id = str(uuid.uuid4())
    ts = _now()
    conn.execute(
        "INSERT INTO images"
        " (image_id, job_id, ordinal, source, raw_path, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (image_id, job_id, ordinal, source, raw_path, ts, ts),
    )
    return image_id


def set_job_status(
    conn: sqlite3.Connection,
    job_id: str,
    status: str,
    *,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    conn.execute(
        "UPDATE jobs"
        " SET status = ?, error_code = ?, error_message = ?, updated_at = ?"
        " WHERE job_id = ?",
        (status, error_code, error_message, _now(), job_id),
    )


def set_image_done(
    conn: sqlite3.Connection,
    image_id: str,
    *,
    status: str,
    width: int | None = None,
    height: int | None = None,
    processed_path: str | None = None,
    reject_reason: str | None = None,
    overall_score: float | None = None,
    flagged: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    conn.execute(
        """UPDATE images
           SET status = ?, width = ?, height = ?, processed_path = ?,
               reject_reason = ?, overall_score = ?, flagged = ?,
               error_code = ?, error_message = ?, updated_at = ?
           WHERE image_id = ?""",
        (
            status, width, height, processed_path,
            reject_reason, overall_score, flagged,
            error_code, error_message, _now(), image_id,
        ),
    )


def query_job_progress(
    conn: sqlite3.Connection,
    job_id: str,
) -> sqlite3.Row | None:
    """Return the job row with aggregated image-count columns."""
    return conn.execute(
        """SELECT
               j.job_id,
               j.status,
               j.created_at,
               j.updated_at,
               j.error_code,
               j.error_message,
               COUNT(i.image_id)                                         AS images_total,
               SUM(CASE WHEN i.status IS NOT NULL THEN 1 ELSE 0 END)    AS images_done,
               SUM(CASE WHEN i.status = 'failed'  THEN 1 ELSE 0 END)    AS images_failed
           FROM jobs AS j
           LEFT JOIN images AS i ON i.job_id = j.job_id
           WHERE j.job_id = ?
           GROUP BY j.job_id""",
        (job_id,),
    ).fetchone()
