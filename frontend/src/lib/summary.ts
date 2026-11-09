import type { ImageResult, JobResults } from "../api";
import { hasScores, isScored } from "./results";

export interface BatchStats {
  total: number;
  /** Images with a score (scored or partial), as reported by the backend. */
  scored: number;
  flagged: number;
  /** Filtered out before analysis, or failed during it. */
  skipped: number;
  /** Average overall score, or null when no image has real criterion results yet. */
  average: number | null;
  /** Count per score bucket, in the order the backend sends them (e.g. "0-20" ... "80-100"). */
  distribution: { bucket: string; count: number }[];
  criteria: CriterionAverage[];
  /** False while the backend only has stub scores (no criterion results). */
  hasRealScores: boolean;
}

export interface CriterionAverage {
  criterionId: string;
  source: "cv" | "vlm";
  /** Mean score across images where the criterion could be evaluated. */
  average: number;
  /** How many images that mean is based on. */
  count: number;
}

/** Average score of each criterion across all scored images; unavailable criteria are left out. */
export function criterionAverages(images: ImageResult[]): CriterionAverage[] {
  const totals = new Map<string, { source: "cv" | "vlm"; sum: number; count: number }>();
  for (const image of images) {
    if (!isScored(image)) continue;
    for (const c of image.criteria) {
      if (c.availability !== "ok" || c.score === null) continue;
      const entry = totals.get(c.criterion_id) ?? { source: c.source, sum: 0, count: 0 };
      entry.sum += c.score;
      entry.count += 1;
      totals.set(c.criterion_id, entry);
    }
  }
  return [...totals.entries()].map(([criterionId, t]) => ({
    criterionId,
    source: t.source,
    average: t.sum / t.count,
    count: t.count,
  }));
}

/** Everything the summary panel shows. Counts and the average come from the backend's summary. */
export function batchStats(results: JobResults): BatchStats {
  const { images, summary } = results;
  const hasRealScores = images.some(hasScores);
  return {
    total: images.length,
    scored: summary.images_scored,
    flagged: summary.flagged_count,
    skipped: images.filter((i) => i.status === "filtered_out" || i.status === "failed").length,
    average: hasRealScores ? summary.mean_overall : null,
    distribution: summary.score_distribution,
    criteria: criterionAverages(images),
    hasRealScores,
  };
}