import { Link, Navigate, useParams } from "react-router-dom";
import type { ImageResult } from "../api";
import ImageThumb from "../components/results/ImageThumb";
import { Button, Card, StatusBadge } from "../components/ui";
import { useJobResults } from "../hooks/useJobResults";
import { displayName, formatScore, imageStatus, isScored, skippedReason } from "../lib/results";

export default function DashboardPage() {
  const { jobId } = useParams();
  if (!jobId) return <Navigate to="/" replace />;
  return <ResultsView key={jobId} jobId={jobId} />;
}

function ResultsView({ jobId }: { jobId: string }) {
  const { results, failure, retry } = useJobResults(jobId);

  return (
    <main className="mx-auto max-w-5xl p-6">
      <h1 className="text-2xl font-semibold">Batch results</h1>
      <p className="mt-1 text-sm text-text-muted">Job {jobId.slice(0, 8)}</p>

      {!results && !failure && <p className="mt-6 text-sm text-text-muted">Loading results…</p>}

      {failure && (
        <Card className="mt-6 flex flex-col items-start gap-3">
          <p role="alert" className="text-sm text-status-fail">
            {failure.code === "JOB_NOT_FINISHED" ? "This analysis is still running." : failure.message}
          </p>
          {failure.code === "JOB_NOT_FINISHED" && (
            <Link to={`/jobs/${jobId}`} className="text-sm font-medium underline">
              View progress
            </Link>
          )}
          {failure.retryable && (
            <Button variant="secondary" onClick={retry}>
              Try again
            </Button>
          )}
        </Card>
      )}

      {results && (
        <>
          <p className="mt-4 text-sm">
            {results.summary.images_scored} of {results.images.length} images scored
            {results.summary.mean_overall !== null && <> · average {formatScore(results.summary.mean_overall)} / 100</>}
            {results.summary.flagged_count > 0 && <> · {results.summary.flagged_count} below standard</>}
          </p>

          {results.images.length === 0 ? (
            <p className="mt-6 text-sm text-text-muted">No images in this analysis.</p>
          ) : (
            <ul className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {results.images.map((image) => (
                <li key={image.image_id}>
                  <ImageCard jobId={jobId} image={image} />
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      <p className="mt-8 text-sm">
        <Link to="/" className="underline">
          New analysis
        </Link>
      </p>
    </main>
  );
}

function ImageCard({ jobId, image }: { jobId: string; image: ImageResult }) {
  const status = imageStatus(image);
  const scored = isScored(image);
  const body = (
    <Card className="flex h-full flex-col gap-3 p-0">
      <ImageThumb image={image} className="h-40 w-full rounded-t-card" />
      <div className="flex flex-col gap-2 p-4 pt-1">
        <p className="truncate font-medium" title={displayName(image.source)}>
          {displayName(image.source)}
        </p>
        {scored ? (
          <div className="flex items-center justify-between">
            <span className="text-2xl font-semibold tabular-nums">
              {formatScore(image.overall_score)}
              <span className="text-sm font-normal text-text-muted"> / 100</span>
            </span>
            {status && <StatusBadge status={status} />}
          </div>
        ) : (
          <p className="text-sm text-text-muted">{skippedReason(image)}</p>
        )}
        {scored && <p className="text-xs text-text-muted">{image.criteria.length} criteria evaluated</p>}
      </div>
    </Card>
  );
  if (!scored) return body;
  return (
    <Link to={`/jobs/${jobId}/results/${image.image_id}`} className="block h-full rounded-card focus-visible:outline-2">
      {body}
    </Link>
  );
}