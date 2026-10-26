import { Link, Navigate, useParams } from "react-router-dom";
import { Button, Card, ProgressBar } from "../components/ui";
import { useJobStatus } from "../hooks/useJobStatus";
import { headline, progressPercent, stageStatuses, STAGES, stateLabel, type StageStatus } from "../lib/jobStages";

const stageStyles: Record<StageStatus, { label: string; classes: string; marker: string }> = {
  done: { label: "Done", classes: "text-status-pass", marker: "✓" },
  active: { label: "In progress", classes: "text-brand-600", marker: "●" },
  waiting: { label: "Waiting", classes: "text-text-muted", marker: "○" },
};

export default function ProgressPage() {
  const { jobId } = useParams();
  if (!jobId) return <Navigate to="/" replace />;
  // `key` remounts the view for a different job, so polling state never leaks between jobs.
  return <JobProgressView key={jobId} jobId={jobId} />;
}

function JobProgressView({ jobId }: { jobId: string }) {
  const { status, failure, reconnecting, retry } = useJobStatus(jobId);

  const state = status?.status;
  const finished = state === "completed" || state === "completed_with_errors";
  const jobFailed = state === "failed";
  const stages = state ? stageStatuses(state) : null;

  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="text-2xl font-semibold">Analyzing photographs</h1>
      <p className="mt-1 text-sm text-text-muted">
        Job {jobId.slice(0, 8)}
        {status && status.progress.images_total > 0 && ` · ${status.progress.images_total} images queued`}
      </p>

      <Card className="mt-6 flex flex-col gap-4">
        {!status && !failure && <p className="text-sm text-text-muted">Checking job status…</p>}

        {status && (
          <>
            <div className="flex items-baseline justify-between gap-4">
              <p aria-live="polite" className="font-medium">
                {headline(status.status, status.progress)}
              </p>
              <span className="text-sm text-text-muted">{stateLabel(status.status)}</span>
            </div>

            <ProgressBar value={progressPercent(status.progress)} />

            {status.progress.images_failed > 0 && (
              <p className="text-sm text-status-review">
                {status.progress.images_failed} {status.progress.images_failed === 1 ? "image" : "images"} could not be
                analyzed.
              </p>
            )}

            {stages && !jobFailed && (
              <ul className="flex flex-col divide-y divide-line text-sm">
                {STAGES.map((stage, index) => {
                  const style = stageStyles[stages[index]];
                  return (
                    <li key={stage.state} className="flex items-center justify-between gap-4 py-2">
                      <span className="flex items-center gap-2">
                        <span aria-hidden="true" className={style.classes}>
                          {style.marker}
                        </span>
                        {stage.label}
                      </span>
                      <span className={style.classes}>{style.label}</span>
                    </li>
                  );
                })}
              </ul>
            )}

            {jobFailed && (
              <p role="alert" className="text-sm text-status-fail">
                {status.error?.message ?? "The analysis could not be completed."}
              </p>
            )}
          </>
        )}

        {reconnecting && !failure && (
          <p role="status" className="text-sm text-status-review">
            Connection problem. Retrying…
          </p>
        )}

        {failure && (
          <div role="alert" className="flex flex-col items-start gap-3 text-sm text-status-fail">
            <p>{failure.message}</p>
            {failure.retryable ? (
              <Button variant="secondary" onClick={retry}>
                Try again
              </Button>
            ) : (
              <Link to="/" className="font-medium underline">
                Start a new analysis
              </Link>
            )}
          </div>
        )}
      </Card>

      <div className="mt-4 flex items-center justify-between gap-4 text-sm text-text-muted">
        <span>
          {finished || jobFailed
            ? ""
            : "You can leave this page open. The job keeps running in the background."}
        </span>
        <span className="flex items-center gap-4">
          <Link to="/" className="underline">
            New analysis
          </Link>
          {finished && (
            <Link
              to={`/jobs/${jobId}/results`}
              className="rounded-control bg-ink px-4 py-2 text-sm font-medium text-surface hover:bg-ink/90"
            >
              View results
            </Link>
          )}
        </span>
      </div>
    </main>
  );
}