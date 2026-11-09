import { useState } from "react";
import type { FeedbackRecord, Verdict } from "../../api";

const MAX_COMMENT = 1000;

const verdictStyles: Record<Verdict, { label: string; selected: string }> = {
  agree: { label: "Agree", selected: "border-status-pass bg-status-pass-bg text-status-pass" },
  disagree: { label: "Disagree", selected: "border-status-fail bg-status-fail-bg text-status-fail" },
};
const VERDICTS: Verdict[] = ["agree", "disagree"];

interface Props {
  /** What the reviewer is judging, e.g. "Contrast" or "overall result". Used for accessible names. */
  subject: string;
  /** The latest saved feedback for this target, if any. */
  record: FeedbackRecord | undefined;
  saving: boolean;
  error: string | null;
  onSubmit: (verdict: Verdict, comment: string | null) => void;
}

/** Agree / Disagree with the AI's reasoning, plus an optional comment. */
export default function FeedbackControls({ subject, record, saving, error, onSubmit }: Props) {
  const [commentOpen, setCommentOpen] = useState(false);
  const [comment, setComment] = useState(record?.comment ?? "");
  const verdict = record?.verdict;
  const tooLong = comment.trim().length > MAX_COMMENT;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-text-muted">Do you agree with the AI's reasoning?</span>
        {VERDICTS.map((v) => {
          const selected = verdict === v;
          return (
            <button
              key={v}
              type="button"
              aria-pressed={selected}
              aria-label={`${verdictStyles[v].label} with the ${subject}`}
              disabled={saving}
              // Clicking the verdict that is already saved does nothing new; the comment box handles edits.
              onClick={() => !selected && onSubmit(v, comment.trim() || null)}
              className={`rounded-control border px-3 py-1 text-sm font-medium disabled:opacity-60 ${
                selected ? verdictStyles[v].selected : "border-line bg-surface text-ink hover:bg-surface-muted"
              }`}
            >
              {verdictStyles[v].label}
            </button>
          );
        })}
        {saving && (
          <span role="status" className="text-sm text-text-muted">
            Saving…
          </span>
        )}
        {!saving && verdict && !error && (
          <span role="status" className="text-sm text-text-muted">
            Saved
          </span>
        )}
      </div>

      {verdict && !commentOpen && (
        <button
          type="button"
          onClick={() => setCommentOpen(true)}
          className="self-start text-sm text-text-muted underline"
        >
          {record?.comment ? "Edit comment" : "Add a comment"}
        </button>
      )}

      {record?.comment && !commentOpen && <p className="text-sm">“{record.comment}”</p>}

      {verdict && commentOpen && (
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-text-muted">Comment (optional)</span>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={3}
              className="rounded-control border border-line bg-surface p-2"
            />
          </label>
          <div className="flex items-center gap-3">
            <button
              type="button"
              disabled={saving || tooLong}
              onClick={() => {
                onSubmit(verdict, comment.trim() || null);
                setCommentOpen(false);
              }}
              className="rounded-control bg-ink px-3 py-1 text-sm font-medium text-surface hover:bg-ink/90 disabled:opacity-60"
            >
              Save comment
            </button>
            <button type="button" onClick={() => setCommentOpen(false)} className="text-sm underline">
              Cancel
            </button>
            <span className={`ml-auto text-xs ${tooLong ? "text-status-fail" : "text-text-muted"}`}>
              {comment.trim().length} / {MAX_COMMENT}
            </span>
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className="text-sm text-status-fail">
          Could not save feedback: {error}
        </p>
      )}
    </div>
  );
}