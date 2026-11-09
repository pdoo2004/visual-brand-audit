import { useCallback, useEffect, useState } from "react";
import { errorMessage, getImageFeedback, submitFeedback, type FeedbackRecord, type Verdict } from "../api";

/** Feedback target: a criterion id, or null for the image as a whole. */
export type FeedbackTarget = string | null;

const keyOf = (target: FeedbackTarget) => target ?? "__image__";

export interface ImageFeedbackState {
  /** False until the saved feedback has been fetched (or the fetch failed). */
  ready: boolean;
  /** True when earlier feedback could not be loaded; sending new feedback still works. */
  loadFailed: boolean;
  /** Latest saved feedback for a target, if any. */
  latest: (target: FeedbackTarget) => FeedbackRecord | undefined;
  isSaving: (target: FeedbackTarget) => boolean;
  errorFor: (target: FeedbackTarget) => string | null;
  /** Save a verdict (and optional comment). Resolves when the request finishes. */
  save: (target: FeedbackTarget, verdict: Verdict, comment: string | null) => Promise<void>;
}

/**
 * Saved Agree/Disagree feedback for one image. The backend keeps every submission as history
 * (newest first), so "latest for a target" is the first record that matches it.
 * Remount via a `key` when imageId changes.
 */
export function useImageFeedback(imageId: string): ImageFeedbackState {
  const [records, setRecords] = useState<FeedbackRecord[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string | null>>({});

  useEffect(() => {
    const controller = new AbortController();
    getImageFeedback(imageId, { signal: controller.signal })
      .then(setRecords)
      .catch(() => {
        if (controller.signal.aborted) return;
        setLoadFailed(true);
        setRecords([]);
      });
    return () => controller.abort();
  }, [imageId]);

  const latest = useCallback(
    (target: FeedbackTarget) => records?.find((r) => (r.criterion_id ?? null) === target),
    [records],
  );

  const save = useCallback(
    async (target: FeedbackTarget, verdict: Verdict, comment: string | null) => {
      const key = keyOf(target);
      setSaving((s) => ({ ...s, [key]: true }));
      setErrors((e) => ({ ...e, [key]: null }));
      try {
        const record = await submitFeedback(imageId, { verdict, comment, criterion_id: target });
        setRecords((prev) => [record, ...(prev ?? [])]);
      } catch (err) {
        setErrors((e) => ({ ...e, [key]: errorMessage(err) }));
      } finally {
        setSaving((s) => ({ ...s, [key]: false }));
      }
    },
    [imageId],
  );

  return {
    ready: records !== null,
    loadFailed,
    latest,
    isSaving: (target) => saving[keyOf(target)] ?? false,
    errorFor: (target) => errors[keyOf(target)] ?? null,
    save,
  };
}