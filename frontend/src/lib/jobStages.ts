import type { JobProgress, JobState } from "../api";

export type StageStatus = "done" | "active" | "waiting";

/**
 * The checklist on Screen 2. The API reports one job state at a time, so each stage is
 * tied to the state during which that work happens.
 */
export const STAGES: { state: JobState; label: string }[] = [
  { state: "preprocessing", label: "Preprocessing & filtering images" },
  { state: "analyzing", label: "Running computer-vision analysis" },
  { state: "scoring", label: "Scoring criteria (model inference)" },
  { state: "completed", label: "Aggregating scores and building dashboard" },
];

/** Where each state sits in the pipeline. Higher = further along. */
const ORDER: Record<JobState, number> = {
  queued: 0,
  preprocessing: 1,
  analyzing: 2,
  scoring: 3,
  completed: 5, // past every stage, so all show as done
  completed_with_errors: 5,
  failed: -1, // not on the happy path; the page shows an error instead of the checklist
};

/** Status of each stage for the current job state, in STAGES order. */
export function stageStatuses(state: JobState): StageStatus[] {
  const current = ORDER[state];
  return STAGES.map((_, index) => {
    const position = index + 1;
    if (current > position) return "done";
    if (current === position) return "active";
    return "waiting";
  });
}

/** 0-100, for the progress bar. */
export function progressPercent({ images_total, images_done }: JobProgress): number {
  if (images_total <= 0) return 0;
  return Math.min(100, Math.round((images_done / images_total) * 100));
}

/** Short label for the job state, shown beside the headline. */
export function stateLabel(state: JobState): string {
  switch (state) {
    case "queued":
      return "Queued";
    case "completed":
      return "Completed";
    case "completed_with_errors":
      return "Completed with errors";
    case "failed":
      return "Failed";
    default:
      return "Running";
  }
}

/** The headline sentence above the progress bar. */
export function headline(state: JobState, progress: JobProgress): string {
  const { images_total: total, images_done: done, images_failed: failed } = progress;
  switch (state) {
    case "queued":
      return "Waiting to start…";
    case "completed":
      return `Analyzed ${total} ${total === 1 ? "image" : "images"}`;
    case "completed_with_errors":
      return `Analyzed ${done - failed} of ${total} images`;
    case "failed":
      return "Analysis failed";
    default:
      return total > 0 ? `Processing ${done} of ${total} images` : "Processing images…";
  }
}