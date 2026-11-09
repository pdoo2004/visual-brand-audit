import type { ReactNode } from "react";
import type { CriterionResult } from "../../api";
import { SourceTag, StatusBadge } from "../ui";
import { criterionName, criterionStatus, formatScore } from "../../lib/results";

/** `children` is an optional slot below the explanation, used for the feedback controls. */
export default function CriterionRow({ criterion, children }: { criterion: CriterionResult; children?: ReactNode }) {
  const unavailable = criterion.availability !== "ok";
  return (
    <li className="flex flex-col gap-2 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h3 className="font-medium">{criterionName(criterion.criterion_id)}</h3>
          <SourceTag source={criterion.source === "cv" ? "measured" : "ai"} />
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm tabular-nums">
            <span className="text-lg font-semibold">{formatScore(criterion.score)}</span>
            {criterion.score !== null && <span className="text-text-muted"> / 100</span>}
          </span>
          <StatusBadge status={criterionStatus(criterion)} />
        </div>
      </div>

      {criterion.label && <p className="text-sm text-text-muted">Tone: {criterion.label}</p>}

      {unavailable ? (
        <p className="text-sm text-status-review">
          This criterion could not be evaluated automatically and needs a human review.
        </p>
      ) : (
        criterion.explanation && <p className="text-sm">{criterion.explanation}</p>
      )}

      {criterion.evidence.length > 0 && (
        <ul className="list-disc pl-5 text-sm text-text-muted">
          {criterion.evidence.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}

      {children}
    </li>
  );
}