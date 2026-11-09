import type { CriterionResult, ImageResult } from "../api";
import { DEFAULT_RUBRIC } from "../config/criteria";

export type ResultStatus = "pass" | "review" | "fail";

/** Demo thresholds (match flag_threshold 60 in config/brand_standards.json; uncalibrated). */
export const PASS_AT = 70;
export const REVIEW_AT = 60;

/** "upload:team-photo.jpg" -> "team-photo.jpg"; URLs keep their last path segment. */
export function displayName(source: string): string {
  const stripped = source.startsWith("upload:") ? source.slice("upload:".length) : source;
  const last = stripped.split("/").filter(Boolean).pop();
  return last ?? stripped;
}

/** Human name for a criterion id; falls back to a tidied id for criteria we don't know. */
export function criterionName(id: string): string {
  const known = DEFAULT_RUBRIC.criteria.find((c) => c.criterionId === id);
  if (known) return known.name;
  const words = id.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function criterionStatus(c: CriterionResult): ResultStatus {
  if (c.availability !== "ok" || c.score === null) return "review";
  if (c.score >= PASS_AT) return "pass";
  if (c.score >= REVIEW_AT) return "review";
  return "fail";
}

/** Overall status for an image, or null when it was never scored (filtered out). */
export function imageStatus(image: ImageResult): ResultStatus | null {
  if (image.status === "filtered_out") return null;
    if (image.status === "failed") return "fail";
  if (image.criteria.length === 0) return null; // nothing to judge yet
  if (image.flagged) return "fail";
  if (image.status === "partial" || image.criteria.some((c) => c.availability !== "ok")) return "review";
  return "pass";
}

export function isScored(image: ImageResult): boolean {
  return image.status === "scored" || image.status === "partial";
}
/** Scored with real criterion results. The backend worker currently stubs scoring (score 0, no criteria). */
export function hasScores(image: ImageResult): boolean {
  return isScored(image) && image.criteria.length > 0;
}
export function formatScore(score: number | null): string {
  return score === null ? "–" : String(Math.round(score));
}

const REJECT_TEXT: Record<string, string> = {
  unsupported_format: "Unsupported file format",
  too_many_pixels: "Image is too large to process",
  animated: "Animated images are not supported",
  too_small: "Image is too small to analyze",
  extreme_aspect_ratio: "Aspect ratio is too extreme",
  unprocessable: "File could not be read as an image",
};

/** One line explaining why an image has no score. */
export function skippedReason(image: ImageResult): string {
  if (image.status === "filtered_out") {
    return (image.reject_reason && REJECT_TEXT[image.reject_reason]) || "Skipped before analysis";
  }
  return "Analysis failed for this image";
}