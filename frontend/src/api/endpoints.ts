import { buildUploadFormData, type UploadSubmission } from "../lib/analysisRequest";
import { request } from "./client";
import { ApiError } from "./errors";
import {
    feedbackListSchema,
    feedbackRecordSchema,
    feedbackSubmissionSchema,
    jobAcceptedSchema,
    jobResultsSchema,
    jobStatusSchema,
    rubricListSchema,
    type FeedbackRecord,
    type FeedbackSubmission,
    type JobAccepted,
    type JobResults,
    type JobStatus,
    type RubricList,
} from "./schemas";

/** Optional second argument of every call, so a screen can cancel it. */
export interface CallOptions {
    signal?: AbortSignal;
}

/** GET /rubrics: rubrics and criteria for Screen 1. */
export function getRubrics(options: CallOptions = {}): Promise<RubricList> {
    return request("/rubrics", rubricListSchema, options);
}

/** POST /analyses/uploads: submit photos for analysis. Resolves with the new job. */
export function submitUpload(submission: UploadSubmission, options: CallOptions = {}): Promise<JobAccepted> {
    return request("/analyses/uploads", jobAcceptedSchema, {
        method: "POST",
        formData: buildUploadFormData(submission),
        ...options,
    });
}

/** Body fields for the existing webpage URL submission endpoint. */
export interface UrlSubmission {
    url: string;
    rubricId: string;
    criterionIds: string[];
    maxPages: number;
}

/** POST /analyses/urls: discover and analyze images from a webpage. */
export function submitUrl(submission: UrlSubmission, options: CallOptions = {}): Promise<JobAccepted> {
    return request("/analyses/urls", jobAcceptedSchema, {
        method: "POST",
        json: {
            url: submission.url,
            rubric_id: submission.rubricId,
            criterion_ids: submission.criterionIds,
            max_pages: submission.maxPages,
        },
        ...options,
    });
}

/** GET /jobs/{id}: status and progress, for Screen 2 polling. */
export function getJobStatus(jobId: string, options: CallOptions = {}): Promise<JobStatus> {
    return request(`/jobs/${encodeURIComponent(jobId)}`, jobStatusSchema, options);
}

/** GET /jobs/{id}/results: dashboard data. Rejects with code JOB_NOT_FINISHED (409) while running. */
export function getJobResults(jobId: string, options: CallOptions = {}): Promise<JobResults> {
    return request(`/jobs/${encodeURIComponent(jobId)}/results`, jobResultsSchema, options);
}

/** POST /images/{id}/feedback: Agree or Disagree on the AI's reasoning. */
export function submitFeedback(
    imageId: string,
    feedback: FeedbackSubmission,
    options: CallOptions = {},
): Promise<FeedbackRecord> {
    // Check the request body before sending, so a bad value fails here with a clear message.
    const checked = feedbackSubmissionSchema.safeParse(feedback);
    if (!checked.success) {
        return Promise.reject(
            new ApiError(0, "VALIDATION_ERROR", checked.error.issues[0]?.message ?? "Invalid feedback.", checked.error.issues),
        );
    }
    return request(`/images/${encodeURIComponent(imageId)}/feedback`, feedbackRecordSchema, {
        method: "POST",
        json: checked.data,
        ...options,
    });
}



/** GET /images/{id}/feedback: every Agree/Disagree saved for an image, newest first. */
export function getImageFeedback(imageId: string, options: CallOptions = {}): Promise<FeedbackRecord[]> {
    return request(`/images/${encodeURIComponent(imageId)}/feedback`, feedbackListSchema, options);
}