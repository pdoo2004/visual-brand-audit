"""Scoring engine: rubric rules and weights applied to CV and model results."""

from brandlens.scoring.engine import CriterionScore, ImageScore, score_image
from brandlens.scoring.explanations import (
    attach_explanations,
    explain_criterion,
    explained_results,
    summarize_image,
)

__all__ = [
    "CriterionScore",
    "ImageScore",
    "attach_explanations",
    "explain_criterion",
    "explained_results",
    "score_image",
    "summarize_image",
]