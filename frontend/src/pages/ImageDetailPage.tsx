import { Link, Navigate, useParams } from "react-router-dom";
import CriterionRow from "../components/results/CriterionRow";
import ImageThumb from "../components/results/ImageThumb";
import { Button, Card, StatusBadge } from "../components/ui";
import { useJobResults } from "../hooks/useJobResults";
import { displayName, formatScore, imageStatus, isScored, skippedReason } from "../lib/results";

export default function ImageDetailPage() {
  const { jobId, imageId } = useParams();
  if (!jobId || !imageId) return <Navigate to="/" replace />;
  return <DetailView key={`${jobId}/${imageId}`} jobId={jobId} imageId={imageId} />;
}

function DetailView({ jobId, imageId }: { jobId: string; imageId: string }) {
  const { results, failure, retry } = useJobResults(jobId);
  const image = results?.images.find((i) => i.image_id === imageId);
  const back = (
    <Link to={`/jobs/${jobId}/results`} className="text-sm underline">
      ← Back to results
    </Link>
  );

  return (
    <main className="mx-auto max-w-3xl p-6">
      {back}

      {!results && !failure && <p className="mt-6 text-sm text-text-muted">Loading…</p>}

      {failure && (
        <Card className="mt-6 flex flex-col items-start gap-3">
          <p role="alert" className="text-sm text-status-fail">
            {failure.message}
          </p>
          {failure.retryable && (
            <Button variant="secondary" onClick={retry}>
              Try again
            </Button>
          )}
        </Card>
      )}

      {results && !image && (
        <p role="alert" className="mt-6 text-sm text-status-fail">
          That image is not part of this analysis.
        </p>
      )}

      {image && (
        <>
          <h1 className="mt-4 text-2xl font-semibold">{displayName(image.source)}</h1>
          <div className="mt-4 flex flex-col gap-4 sm:flex-row">
            <ImageThumb image={image} className="h-56 w-full shrink-0 rounded-card sm:w-72" />
            <div className="flex flex-col items-start gap-2">
              {isScored(image) ? (
                <>
                  <p className="text-4xl font-semibold tabular-nums">
                    {formatScore(image.overall_score)}
                    <span className="text-base font-normal text-text-muted"> / 100</span>
                  </p>
                  {imageStatus(image) && <StatusBadge status={imageStatus(image)!} />}
                  <p className="text-sm text-text-muted">Weighted average of the criteria below.</p>
                </>
              ) : (
                <p className="text-sm text-text-muted">{skippedReason(image)}</p>
              )}
            </div>
          </div>

          {isScored(image) && (
            <Card className="mt-6">
              <h2 className="text-lg font-semibold">Criteria</h2>
              {image.criteria.length === 0 ? (
                <p className="mt-2 text-sm text-text-muted">No criterion scores were recorded for this image.</p>
              ) : (
                <ul className="mt-2 divide-y divide-line">
                  {image.criteria.map((c) => (
                    <CriterionRow key={c.criterion_id} criterion={c} />
                  ))}
                </ul>
              )}
            </Card>
          )}
        </>
      )}
    </main>
  );
}