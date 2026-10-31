"""SQLite database access layer.

Implements the schema from docs/architecture/database-schema.md using the
built-in sqlite3 module. Every public function expects an open Connection
(obtained via get_conn) so callers control transaction boundaries.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
    submission_url: str | None = None,
    max_pages: int | None = None,
) -> None:
    """Insert a queued job. URL jobs must supply `submission_url` (enforced by a table CHECK)."""
    ts = _now()
    conn.execute(
        "INSERT INTO jobs (job_id, rubric_id, input_type, submission_url, max_pages,"
        " status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)",
        (job_id, rubric_id, input_type, submission_url, max_pages, ts, ts),
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


# ---------------------------------------------------------------------------
# Result persistence (SCRUM-158 / task 7.7)
# ---------------------------------------------------------------------------

_CRITERION_COLUMNS = (
    "criterion_id", "score", "weight", "source", "label",
    "explanation", "evidence_json", "availability",
)


def _criterion_row(job_id: str, image_id: str, criterion: Mapping[str, Any], ts: str) -> tuple:
    """Flatten one criterion mapping into the column order of `criterion_scores`."""
    evidence = list(criterion.get("evidence") or [])
    return (
        image_id,
        criterion["criterion_id"],
        job_id,
        criterion.get("score"),
        criterion["weight"],
        criterion["source"],
        criterion.get("label"),
        criterion.get("explanation"),
        json.dumps(evidence),
        criterion["availability"],
        ts,
        ts,
    )


def save_image_result(
    conn: sqlite3.Connection,
    image_id: str,
    *,
    status: str,
    criteria: Sequence[Mapping[str, Any]] = (),
    measurements: Mapping[str, Any] | None = None,
    overall_score: float | None = None,
    flagged: bool | int | None = None,
    width: int | None = None,
    height: int | None = None,
    processed_path: str | None = None,
    reject_reason: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    """Store one image's final outcome: the image row plus its criterion rows.

    Runs inside the caller's transaction, so the image header and its criterion
    rows are written together or not at all. Calling it again for the same image
    replaces the earlier criterion rows (safe to retry). Each criterion mapping
    needs ``criterion_id``, ``weight``, ``source`` and ``availability``; ``score``,
    ``label``, ``explanation`` and ``evidence`` are optional. Raises ``LookupError``
    if the image does not exist.
    """
    row = conn.execute("SELECT job_id FROM images WHERE image_id = ?", (image_id,)).fetchone()
    if row is None:
        raise LookupError(f"image {image_id!r} not found")
    job_id = row["job_id"]
    ts = _now()

    conn.execute(
        """UPDATE images
           SET status = ?, width = ?, height = ?, processed_path = ?,
               reject_reason = ?, measurements_json = ?, overall_score = ?,
               flagged = ?, error_code = ?, error_message = ?, updated_at = ?
           WHERE image_id = ?""",
        (
            status, width, height, processed_path, reject_reason,
            json.dumps(measurements) if measurements is not None else None,
            overall_score,
            None if flagged is None else int(bool(flagged)),
            error_code, error_message, ts, image_id,
        ),
    )
    conn.execute("DELETE FROM criterion_scores WHERE image_id = ?", (image_id,))
    conn.executemany(
        "INSERT INTO criterion_scores (image_id, criterion_id, job_id, score, weight, source,"
        " label, explanation, evidence_json, availability, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [_criterion_row(job_id, image_id, c, ts) for c in criteria],
    )


def get_job(conn: sqlite3.Connection, job_id: str) -> sqlite3.Row | None:
    """Return the job row (rubric, status, timestamps, error) or None if unknown."""
    return conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()


def get_job_images(conn: sqlite3.Connection, job_id: str) -> list[sqlite3.Row]:
    """All image rows for a job, in upload order."""
    return conn.execute(
        "SELECT * FROM images WHERE job_id = ? ORDER BY ordinal", (job_id,)
    ).fetchall()


def get_job_criterion_scores(
    conn: sqlite3.Connection, job_id: str
) -> dict[str, list[sqlite3.Row]]:
    """Criterion rows for a whole job, grouped by image_id.

    One query for the job (not one per image), ordered by the position the
    criteria were selected in, so the results UI shows them in a stable order.
    """
    rows = conn.execute(
        """SELECT cs.*
           FROM criterion_scores AS cs
           JOIN job_criteria AS jc
             ON jc.job_id = cs.job_id AND jc.criterion_id = cs.criterion_id
           WHERE cs.job_id = ?
           ORDER BY cs.image_id, jc.position""",
        (job_id,),
    ).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = {}
    for r in rows:
        grouped.setdefault(r["image_id"], []).append(r)
    return grouped


def get_job_latest_feedback(
    conn: sqlite3.Connection, job_id: str
) -> dict[str, sqlite3.Row]:
    """Latest whole-image feedback row for each image in a job, keyed by image_id.

    Uses the ordering from database-schema.md (`created_at DESC, feedback_id DESC`).
    Criterion-specific feedback is left out on purpose: it must not show up as a
    verdict on the whole image.
    """
    rows = conn.execute(
        """SELECT f.*
           FROM feedback AS f
           JOIN images AS i ON i.image_id = f.image_id
           WHERE i.job_id = ? AND f.criterion_id IS NULL
           ORDER BY f.created_at DESC, f.feedback_id DESC""",
        (job_id,),
    ).fetchall()
    latest: dict[str, sqlite3.Row] = {}
    for r in rows:
        latest.setdefault(r["image_id"], r)  # first row seen is the newest
    return latest
