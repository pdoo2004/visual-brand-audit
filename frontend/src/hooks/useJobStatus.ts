import { useCallback, useEffect, useState } from "react";
import { ApiError, errorMessage, getJobStatus, isTerminalJobState, type JobStatus } from "../api";

/** How often to ask the backend for progress while a job is running. */
export const POLL_INTERVAL_MS = 2000;
/** After this many failed requests in a row, stop retrying and ask the user. */
const MAX_CONSECUTIVE_FAILURES = 5;

export interface PollFailure {
  message: string;
  code: string;
  /** True when trying again could help (network or server trouble); false for e.g. NOT_FOUND. */
  retryable: boolean;
}

export interface JobStatusState {
  /** Latest status received, or null before the first response. */
  status: JobStatus | null;
  /** Set when polling has stopped because of an error the user needs to see. */
  failure: PollFailure | null;
  /** True while requests are failing but the hook is still retrying on its own. */
  reconnecting: boolean;
  /** Restart polling after a retryable failure. */
  retry: () => void;
}

/** Network trouble and server errors may pass; 4xx errors (not found, bad request) will not. */
function isTransient(err: unknown): boolean {
  return err instanceof ApiError && (err.status === 0 || err.status >= 500);
}

/**
 * Polls GET /jobs/{id} until the job reaches a final state.
 *
 * - One request at a time: the next poll is scheduled only after the previous one finishes.
 * - Stops on completed, completed_with_errors, or failed, and when the page is left.
 * - Retries network and server errors with a growing delay before giving up.
 *
 * The caller should remount this hook (via a `key`) when `jobId` changes, so state resets.
 */
export function useJobStatus(jobId: string, intervalMs: number = POLL_INTERVAL_MS): JobStatusState {
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [failure, setFailure] = useState<PollFailure | null>(null);
  const [reconnecting, setReconnecting] = useState(false);
  const [attempt, setAttempt] = useState(0); // bumping this restarts the effect (see `retry`)

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;

    async function poll() {
      try {
        const next = await getJobStatus(jobId, { signal: controller.signal });
        failures = 0;
        setReconnecting(false);
        setStatus(next);
        if (!isTerminalJobState(next.status)) timer = setTimeout(poll, intervalMs);
      } catch (err) {
        if (controller.signal.aborted) return; // the page was left; nothing to report
        failures += 1;
        if (isTransient(err) && failures < MAX_CONSECUTIVE_FAILURES) {
          setReconnecting(true);
          timer = setTimeout(poll, intervalMs * Math.min(failures + 1, 3));
          return;
        }
        setReconnecting(false);
        setFailure({
          message: errorMessage(err),
          code: err instanceof ApiError ? err.code : "UNKNOWN_ERROR",
          retryable: isTransient(err),
        });
      }
    }

    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [jobId, intervalMs, attempt]);

  const retry = useCallback(() => {
    setFailure(null);
    setAttempt((n) => n + 1);
  }, []);

  return { status, failure, reconnecting, retry };
}