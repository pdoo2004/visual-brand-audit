import type { JobResults } from "../../api";
import { Card, SourceTag } from "../ui";
import { criterionName, formatScore } from "../../lib/results";
import { batchStats } from "../../lib/summary";

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <Card className="flex flex-col gap-1">
      <dt className="text-sm text-text-muted">{label}</dt>
      <dd className="text-3xl font-semibold tabular-nums">{value}</dd>
      {note && <dd className="text-xs text-text-muted">{note}</dd>}
    </Card>
  );
}

/** A horizontal bar. `percent` is 0-100; the bar is decorative, the numbers beside it carry the meaning. */
function Bar({ percent }: { percent: number }) {
  return (
    <div aria-hidden="true" className="h-2 w-full rounded-full bg-surface-muted">
      <div className="h-2 rounded-full bg-brand-500" style={{ width: `${Math.max(0, Math.min(100, percent))}%` }} />
    </div>
  );
}

/** Batch summary: counts, average score, score distribution, and average per criterion. */
export default function SummaryPanel({ results }: { results: JobResults }) {
  const stats = batchStats(results);
  const maxBucket = Math.max(1, ...stats.distribution.map((b) => b.count));

  return (
    <section aria-label="Batch summary" className="mt-6 flex flex-col gap-4">
      <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Images analyzed" value={`${stats.scored} of ${stats.total}`} />
        <Stat
          label="Average score"
          value={stats.average === null ? "–" : formatScore(stats.average)}
          note={stats.average === null ? "Not available yet" : "out of 100"}
        />
        <Stat label="Below standard" value={String(stats.flagged)} note="Flagged by the rubric" />
        <Stat label="Skipped or failed" value={String(stats.skipped)} note="No score" />
      </dl>

      {!stats.hasRealScores ? (
        <p className="text-sm text-text-muted">
          Score statistics will appear here once images have criterion scores.
        </p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <h2 className="text-lg font-semibold">Score distribution</h2>
            <ul className="mt-3 flex flex-col gap-2">
              {stats.distribution.map((b) => (
                <li key={b.bucket} className="flex items-center gap-3 text-sm">
                  <span className="w-16 shrink-0 text-text-muted tabular-nums">{b.bucket.replace("-", "–")}</span>
                  <Bar percent={(b.count / maxBucket) * 100} />
                  <span className="w-6 shrink-0 text-right tabular-nums">{b.count}</span>
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <h2 className="text-lg font-semibold">Average by criterion</h2>
            {stats.criteria.length === 0 ? (
              <p className="mt-3 text-sm text-text-muted">No criterion scores yet.</p>
            ) : (
              <ul className="mt-3 flex flex-col gap-3">
                {stats.criteria.map((c) => (
                  <li key={c.criterionId} className="flex flex-col gap-1 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-2">
                        {criterionName(c.criterionId)}
                        <SourceTag source={c.source === "cv" ? "measured" : "ai"} />
                      </span>
                      <span className="tabular-nums">
                        {formatScore(c.average)}
                        <span className="text-text-muted"> / 100 · {c.count} {c.count === 1 ? "image" : "images"}</span>
                      </span>
                    </div>
                    <Bar percent={c.average} />
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </section>
  );
}