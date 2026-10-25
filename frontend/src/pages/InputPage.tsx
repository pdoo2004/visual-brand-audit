import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { submitUpload } from "../api/submitUpload";
import FileDropzone from "../components/FileDropzone";
import { Button, Card, Checkbox } from "../components/ui";
import { METHOD_GROUPS, RUBRICS } from "../config/criteria";
import { checkFiles, mergeFiles, validateForm, type FileProblem, type FormErrors } from "../lib/validation";

export default function InputPage() {
  const navigate = useNavigate();
  const [rubricId, setRubricId] = useState(RUBRICS[0].rubricId);
  const rubric = RUBRICS.find((r) => r.rubricId === rubricId) ?? RUBRICS[0];

  const [files, setFiles] = useState<File[]>([]);
  const [rejected, setRejected] = useState<FileProblem[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [errors, setErrors] = useState<FormErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  function addFiles(incoming: File[]) {
    const { accepted, rejected: bad } = checkFiles(incoming);
    setRejected(bad);
    if (accepted.length > 0) {
      setFiles((current) => mergeFiles(current, accepted));
      setErrors((e) => ({ ...e, files: undefined }));
    }
  }

  function toggleCriterion(id: string, on: boolean) {
    setSelected((current) => {
      const next = new Set(current);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
    setErrors((e) => ({ ...e, criteria: undefined }));
  }

  function changeRubric(id: string) {
    setRubricId(id);
    setSelected(new Set()); // criteria belong to one rubric
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitError(null);

    const criterionIds = rubric.criteria.filter((c) => selected.has(c.criterionId)).map((c) => c.criterionId);
    const found = validateForm(files, criterionIds);
    setErrors(found);
    if (found.files || found.criteria) return;

    setSubmitting(true);
    try {
      const job = await submitUpload({ files, rubricId: rubric.rubricId, criterionIds });
      navigate(`/jobs/${job.job_id}`);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Something went wrong. Try again.");
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto max-w-4xl p-6">
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <Card className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold">1. Add photographs</h2>
          <FileDropzone
            files={files}
            onAdd={addFiles}
            onRemove={(i) => setFiles((f) => f.filter((_, idx) => idx !== i))}
            error={errors.files}
            disabled={submitting}
          />
          {rejected.length > 0 && (
            <ul role="alert" className="flex flex-col gap-1 text-sm text-status-fail">
              {rejected.map((p, i) => (
                <li key={`${p.fileName}-${i}`}>
                  <span className="font-medium">{p.fileName}:</span> {p.message}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="flex flex-col gap-4">
          <h2 className="text-lg font-semibold">2. Select brand standards</h2>
          <div className="grid gap-6 sm:grid-cols-2">
            {METHOD_GROUPS.map(({ method, heading }) => {
              const group = rubric.criteria.filter((c) => c.method === method);
              if (group.length === 0) return null;
              return (
                <fieldset key={method} className="flex flex-col gap-2">
                  <legend className="mb-1 text-sm font-medium text-text-muted">{heading}</legend>
                  {group.map((c) => (
                    <Checkbox
                      key={c.criterionId}
                      label={c.name}
                      checked={selected.has(c.criterionId)}
                      disabled={submitting}
                      onChange={(e) => toggleCriterion(c.criterionId, e.target.checked)}
                    />
                  ))}
                </fieldset>
              );
            })}
          </div>
          {errors.criteria && (
            <p role="alert" className="text-sm text-status-fail">
              {errors.criteria}
            </p>
          )}
          <div className="flex items-center gap-2 text-sm">
            <label htmlFor="rubric" className="font-medium text-text-muted">
              Rubric
            </label>
            <select
              id="rubric"
              value={rubricId}
              disabled={submitting}
              onChange={(e) => changeRubric(e.target.value)}
              className="rounded-control border border-line bg-surface px-3 py-2"
            >
              {RUBRICS.map((r) => (
                <option key={r.rubricId} value={r.rubricId}>
                  {r.name}
                </option>
              ))}
            </select>
          </div>
        </Card>

        <div className="flex flex-col items-end gap-2">
          {submitError && (
            <p role="alert" className="text-sm text-status-fail">
              {submitError}
            </p>
          )}
          <Button type="submit" disabled={submitting}>
            {submitting ? "Submitting…" : "Analyze"}
          </Button>
        </div>
      </form>
    </main>
  );
}