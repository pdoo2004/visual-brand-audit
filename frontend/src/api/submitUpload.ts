import { buildUploadFormData, type UploadSubmission } from "../lib/analysisRequest";

export interface JobAccepted {
  job_id: string;
  status: "queued";
  input_type: "upload" | "url";
  created_at: string;
  status_url: string;
}

export async function submitUpload(submission: UploadSubmission): Promise<JobAccepted> {
  let response: Response;
  try {
    response = await fetch("/api/v1/analyses/uploads", {
      method: "POST",
      body: buildUploadFormData(submission),
    });
  } catch {
    throw new Error("Could not reach the analysis service. Check that the API is running.");
  }

  if (response.ok) return (await response.json()) as JobAccepted;

  let message = `Request failed (${response.status}).`;
  try {
    const payload = await response.json();
    // Contract envelope: { error: { code, message } }. FastAPI's HTTPException wraps it in `detail`.
    const err = payload?.error ?? payload?.detail?.error ?? payload?.detail;
    if (typeof err?.message === "string") message = err.message;
  } catch {
    /* non-JSON error body: keep the generic message */
  }
  throw new Error(message);
}