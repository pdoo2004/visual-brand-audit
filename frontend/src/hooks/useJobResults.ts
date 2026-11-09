import { useCallback, useEffect, useState } from "react";
import { ApiError, errorMessage, getJobResults, type JobResults } from "../api";

export interface ResultsFailure {
  message: string;
  code: string;
  /** True for network/server trouble, where trying again may help. */
  retryable: boolean;
}

export interface JobResultsState {
  results: JobResults | null;
  failure: ResultsFailure | null;
  retry: () => void;
}

/**
 * Loads GET /jobs/{id}/results once. Results do not change after a job finishes, so there is
 * no polling. A 409 (job still running) comes back as failure.code === "JOB_NOT_FINISHED".
 * Remount via a `key` when jobId changes.
 */
export function useJobResults(jobId: string): JobResultsState {
  const [results, setResults] = useState<JobResults | null>(null);
  const [failure, setFailure] = useState<ResultsFailure | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    getJobResults(jobId, { signal: controller.signal })
      .then(setResults)
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setFailure({
          message: errorMessage(err),
          code: err instanceof ApiError ? err.code : "UNKNOWN_ERROR",
          retryable: err instanceof ApiError && (err.status === 0 || err.status >= 500),
        });
      });
    return () => controller.abort();
  }, [jobId, attempt]);

  const retry = useCallback(() => {
    setFailure(null);
    setAttempt((n) => n + 1);
  }, []);

  return { results, failure, retry };
}