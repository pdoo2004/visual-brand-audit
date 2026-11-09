"""Turn structured criterion scores into reviewer-facing explanations (SCRUM-122/123).

Explanations must track the underlying score: they cite the same evidence and
reasons the engine already produced, without inventing measurements or tones.
"""

from __future__ import annotations

from brandlens.scoring.engine import CriterionScore, ImageScore

_OK = "ok"


def explain_criterion(row: CriterionScore) -> str:
    """Build one human-readable sentence (or short paragraph) for a criterion.

    Available criteria summarize pass/fail or the tone label with evidence.
    Unavailable criteria state that review is needed and keep the engine reason.
    """
    name = row.criterion_id.replace("_", " ")
    if row.availability != _OK:
        reason = row.reasons[0] if row.reasons else "inputs were incomplete."
        return f"{name}: needs review — {reason}"

    assert row.score is not None
    if row.source == "vlm":
        label = row.label or "no tone label"
        evidence = row.evidence[0] if row.evidence else "no visible evidence was cited"
        return (
            f"{name}: score {row.score:.0f}/100 "
            f"(label: {label}). Evidence: {evidence}."
        )

    if row.score >= 100:
        detail = row.evidence[0] if row.evidence else "all active thresholds held"
        return f"{name}: passed ({detail})."
    if row.score <= 0:
        detail = row.reasons[0] if row.reasons else "a threshold was missed"
        return f"{name}: failed — {detail}."
    detail = row.evidence[0] if row.evidence else (row.reasons[0] if row.reasons else "see measurements")
    return f"{name}: score {row.score:.0f}/100 ({detail})."


def summarize_image(score: ImageScore) -> str:
    """Derive an image-level summary from criterion rows (SCRUM-123).

    Mentions the overall score when available, flags incomplete/needs-review
    criteria by id, and notes when the image is flagged by the rubric threshold.
    """
    rows = score.criteria
    review_ids = [row.criterion_id for row in rows if row.availability != _OK]
    available = [row for row in rows if row.availability == _OK]

    if score.status == "failed" or not available:
        if review_ids:
            return (
                "No criteria could be scored. Needs review: "
                + ", ".join(review_ids)
                + "."
            )
        return "No criteria could be scored."

    overall = score.overall_score
    assert overall is not None
    parts = [f"Overall score {overall:.0f}/100 ({score.status})."]

    if review_ids:
        parts.append("Needs review: " + ", ".join(review_ids) + ".")
    else:
        parts.append("All selected criteria completed.")

    if score.flagged:
        parts.append("Flagged below the rubric threshold.")

    return " ".join(parts)


def attach_explanations(score: ImageScore) -> list[dict]:
    """Criterion mappings ready for API/DB persistence, each with ``explanation``."""
    return [
        {
            "criterion_id": row.criterion_id,
            "score": row.score,
            "weight": row.weight,
            "source": row.source,
            "label": row.label,
            "explanation": explain_criterion(row),
            "evidence": list(row.evidence),
            "availability": row.availability,
        }
        for row in score.criteria
    ]


def explained_results(
    score: ImageScore,
) -> tuple[list[dict], str]:
    """Return (criterion dicts with explanations, image summary text)."""
    return attach_explanations(score), summarize_image(score)
