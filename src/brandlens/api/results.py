"""Assemble the dashboard payload (JobResults) from stored rows (SCRUM-159 / task 7.7a)."""

from __future__ import annotations

import itertools
import json
import sqlite3
from datetime import datetime
from uuid import UUID

from brandlens.api import db as database
from brandlens.api.schemas import (
    CriterionResult,
    FeedbackRecord,
    ImageResult,
    ImageStatus,
    JobResults,
    ResultsSummary,
    ScoreBucket,
)

# Five equal-width buckets; a score of exactly 100 counts in the last one.
_BUCKET_EDGES = (0, 20, 40, 60, 80, 100)


def _distribution(scores: list[float]) -> list[ScoreBucket]:
    counts = [0] * (len(_BUCKET_EDGES) - 1)
    for s in scores:
        counts[min(int(s // 20), len(counts) - 1)] += 1
    return [
        ScoreBucket(bucket=f"{lo}-{hi}", count=n)
        for (lo, hi), n in zip(itertools.pairwise(_BUCKET_EDGES), counts, strict=True)
    ]


def _criterion(row: sqlite3.Row) -> CriterionResult:
    return CriterionResult(
        criterion_id=row["criterion_id"],
        score=row["score"],
        weight=row["weight"],
        source=row["source"],
        label=row["label"],
        explanation=row["explanation"],
        evidence=json.loads(row["evidence_json"]) if row["evidence_json"] else [],
        availability=row["availability"],
    )


def _feedback(row: sqlite3.Row | None) -> FeedbackRecord | None:
    if row is None:
        return None
    return FeedbackRecord(
        feedback_id=UUID(row["feedback_id"]),
        image_id=UUID(row["image_id"]),
        criterion_id=row["criterion_id"],
        verdict=row["verdict"],
        comment=row["comment"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def build_job_results(conn: sqlite3.Connection, job_id: str) -> JobResults | None:
    """Return the stored results for a job, or None if the job does not exist.

    Reads four small queries for the whole job (job, images, criteria, feedback),
    never one query per image. The summary is derived from the image rows each
    time, as the database design requires, so it cannot drift from them.
    """
    job = database.get_job(conn, job_id)
    if job is None:
        return None

    criteria_by_image = database.get_job_criterion_scores(conn, job_id)
    feedback_by_image = database.get_job_latest_feedback(conn, job_id)

    images: list[ImageResult] = []
    for row in database.get_job_images(conn, job_id):
        # An image that never reached a final state (e.g. the job failed first)
        # is reported as failed rather than leaving the UI with a blank status.
        status = ImageStatus(row["status"]) if row["status"] else ImageStatus.FAILED
        images.append(
            ImageResult(
                image_id=UUID(row["image_id"]),
                source=row["source"],
                status=status,
                reject_reason=row["reject_reason"],
                overall_score=row["overall_score"],
                flagged=bool(row["flagged"]),
                measurements=(
                    json.loads(row["measurements_json"]) if row["measurements_json"] else None
                ),
                criteria=[_criterion(c) for c in criteria_by_image.get(row["image_id"], [])],
                feedback=_feedback(feedback_by_image.get(row["image_id"])),
            )
        )

    scores = [i.overall_score for i in images if i.overall_score is not None]
    summary = ResultsSummary(
        images_scored=len(scores),
        mean_overall=round(sum(scores) / len(scores), 1) if scores else None,
        score_distribution=_distribution(scores),
        flagged_count=sum(1 for i in images if i.flagged),
    )
    return JobResults(
        job_id=UUID(job_id), rubric_id=job["rubric_id"], summary=summary, images=images
    )
