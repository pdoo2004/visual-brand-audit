import { z } from "zod";

export const jobStateSchema = z.enum([
  "queued",
  "preprocessing",
  "analyzing",
  "scoring",
  "completed",
  "completed_with_errors",
  "failed",
]);
export type JobState = z.infer<typeof jobStateSchema>;

/** True once a job will not change state again, so polling can stop. */
export function isTerminalJobState(state: JobState): boolean {
  return state === "completed" || state === "completed_with_errors" || state === "failed";
}

export const imageStatusSchema = z.enum(["scored", "partial", "failed", "filtered_out"]);
export type ImageStatus = z.infer<typeof imageStatusSchema>;

export const verdictSchema = z.enum(["agree", "disagree"]);
export type Verdict = z.infer<typeof verdictSchema>;

const criterionSourceSchema = z.enum(["cv", "vlm"]);
const availabilitySchema = z.enum(["ok", "unavailable_needs_review"]);
const rejectReasonSchema = z.enum([
  "unsupported_format",
  "too_many_pixels",
  "animated",
  "too_small",
  "extreme_aspect_ratio",
  "unprocessable",
]);

export const API_ERROR_CODES = [
  "VALIDATION_ERROR",
  "UNSUPPORTED_FILE_TYPE",
  "FILE_TOO_LARGE",
  "NOT_FOUND",
  "JOB_NOT_FINISHED",
  "NOT_IMPLEMENTED",
  "INTERNAL_ERROR",
] as const;
export type ApiErrorCode = (typeof API_ERROR_CODES)[number];

// ---- Errors -----------------------------------------------------------------------

/** The body of an error: { code, message, details }. */
export const errorBodySchema = z.object({
  code: z.string(),
  message: z.string(),
  details: z.array(z.unknown()).default([]),
});
export type ErrorBody = z.infer<typeof errorBodySchema>;

// ---- Rubrics (GET /api/v1/rubrics) --------------------------------------------------

export const criterionInfoSchema = z.object({
  criterion_id: z.string(),
  name: z.string(),
  definition: z.string(),
  evaluation_evidence: z.string(),
  method: criterionSourceSchema,
  weight: z.number().nullable(),
});
export type CriterionInfo = z.infer<typeof criterionInfoSchema>;

export const rubricInfoSchema = z.object({
  rubric_id: z.string(),
  name: z.string(),
  criteria: z.array(criterionInfoSchema),
});
export type RubricInfo = z.infer<typeof rubricInfoSchema>;

export const rubricListSchema = z.object({ rubrics: z.array(rubricInfoSchema) });
export type RubricList = z.infer<typeof rubricListSchema>;

// ---- Jobs (POST /analyses/uploads, GET /jobs/{id}) ---------------------------------------

export const jobAcceptedSchema = z.object({
  job_id: z.guid(),
  status: z.literal("queued"),
  input_type: z.enum(["upload", "url"]),
  created_at: z.string(),
  status_url: z.string(),
});
export type JobAccepted = z.infer<typeof jobAcceptedSchema>;

export const jobProgressSchema = z.object({
  images_total: z.number().int().nonnegative(),
  images_done: z.number().int().nonnegative(),
  images_failed: z.number().int().nonnegative(),
});
export type JobProgress = z.infer<typeof jobProgressSchema>;

export const jobStatusSchema = z.object({
  job_id: z.guid(),
  status: jobStateSchema,
  progress: jobProgressSchema,
  created_at: z.string(),
  updated_at: z.string(),
  error: errorBodySchema.nullish(), // present only when status is "failed"
});
export type JobStatus = z.infer<typeof jobStatusSchema>;

// ---- Feedback (POST /images/{id}/feedback) ------------------------------------------------

/** Request body. Mirrors the backend: comment up to 1000 chars, criterion_id null = whole image. */
export const feedbackSubmissionSchema = z.object({
  verdict: verdictSchema,
  comment: z.string().trim().max(1000).nullish(),
  criterion_id: z.string().nullish(),
});
export type FeedbackSubmission = z.infer<typeof feedbackSubmissionSchema>;

export const feedbackRecordSchema = z.object({
  feedback_id: z.guid(),
  image_id: z.guid(),
  criterion_id: z.string().nullable(),
  verdict: verdictSchema,
  comment: z.string().nullable(),
  created_at: z.string(),
});
export type FeedbackRecord = z.infer<typeof feedbackRecordSchema>;

// ---- Results (GET /jobs/{id}/results) ---------------------------------------------------

export const criterionResultSchema = z.object({
  criterion_id: z.string(),
  score: z.number().nullable(), // null when the criterion could not be evaluated
  weight: z.number(),
  source: criterionSourceSchema,
  label: z.string().nullish(), // tone label for the VLM criterion
  explanation: z.string().nullish(),
  evidence: z.array(z.string()).default([]),
  availability: availabilitySchema,
});
export type CriterionResult = z.infer<typeof criterionResultSchema>;

export const imageResultSchema = z.object({
  image_id: z.guid(),
  source: z.string(), // "upload:name.jpg" or an image URL
  status: imageStatusSchema,
  reject_reason: rejectReasonSchema.nullish(),
  overall_score: z.number().nullable(),
  flagged: z.boolean().default(false),
  measurements: z.record(z.string(), z.unknown()).nullish(), // provisional keys
  criteria: z.array(criterionResultSchema).default([]),
  feedback: feedbackRecordSchema.nullish(),
});
export type ImageResult = z.infer<typeof imageResultSchema>;

export const resultsSummarySchema = z.object({
  images_scored: z.number().int().nonnegative(),
  mean_overall: z.number().nullable(),
  score_distribution: z.array(z.object({ bucket: z.string(), count: z.number().int().nonnegative() })).default([]),
  flagged_count: z.number().int().nonnegative(),
});
export type ResultsSummary = z.infer<typeof resultsSummarySchema>;

export const jobResultsSchema = z.object({
  job_id: z.guid(),
  rubric_id: z.string(),
  summary: resultsSummarySchema,
  images: z.array(imageResultSchema),
});
export type JobResults = z.infer<typeof jobResultsSchema>;