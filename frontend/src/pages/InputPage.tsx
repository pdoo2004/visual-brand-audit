import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { errorMessage, submitUpload, submitUrl } from "../api";
import FileDropzone from "../components/FileDropzone";
import { Button, Card, Checkbox } from "../components/ui";
import { METHOD_GROUPS, RUBRICS } from "../config/criteria";
import { checkFiles, mergeFiles, validateForm, type FileProblem, type FormErrors } from "../lib/validation";

export default function InputPage() {
  const navigate = useNavigate();
  const [rubricId, setRubricId] = useState(RUBRICS[0].rubricId);
  const rubric = RUBRICS.find((r) => r.rubricId === rubricId) ?? RUBRICS[0];

  const [files, setFiles] = useState<File[]>([]);
  const [inputMode, setInputMode] = useState<"upload" | "url">("upload");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [maxPages, setMaxPages] = useState(3);
  const [urlError, setUrlError] = useState<string | null>(null);
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
    setUrlError(null);
    setErrors({});

    const criterionIds = rubric.criteria.filter((c) => selected.has(c.criterionId)).map((c) => c.criterionId);

    if (criterionIds.length === 0) {
      setErrors({ criteria: "Select at least one criterion." });
      return;
    }

    if (inputMode === "upload") {
      const found = validateForm(files, criterionIds);
      setErrors(found);
      if (found.files || found.criteria) return;
    } else {
      try {
        const parsed = new URL(websiteUrl.trim());
        if (!["http:", "https:"].includes(parsed.protocol) || !parsed.hostname) {
          throw new Error("Invalid URL");
        }
      } catch {
        setUrlError("Enter a valid HTTP or HTTPS webpage URL.");
        return;
      }
    }

    setSubmitting(true);
    try {
      const job = inputMode === "url"
        ? await submitUrl({
            url: websiteUrl.trim(),
            rubricId: rubric.rubricId,
            criterionIds,
            maxPages,
          })
        : await submitUpload({ files, rubricId: rubric.rubricId, criterionIds });
      navigate(`/jobs/${job.job_id}`);
    } catch (err) {
      setSubmitError(errorMessage(err));
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto max-w-4xl p-6">
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <Card className="flex flex-col gap-4">
          <h2 className="text-lg font-semibold">1. Add photographs</h2>
          <fieldset className="flex flex-wrap gap-4" disabled={submitting}>
            <legend className="sr-only">Choose image source</legend>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="inputMode"
                value="upload"
                checked={inputMode === "upload"}
                onChange={() => { setInputMode("upload"); setSubmitError(null); setUrlError(null); }}
              />
              Upload images
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="inputMode"
                value="url"
                checked={inputMode === "url"}
                onChange={() => { setInputMode("url"); setSubmitError(null); setErrors({}); }}
              />
              Webpage URL
            </label>
          </fieldset>

          {inputMode === "upload" ? (
            <>
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
            </>
          ) : (
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-1">
                <label htmlFor="website-url" className="text-sm font-medium">Website URL</label>
                <input
                  id="website-url"
                  type="url"
                  placeholder="https://example.com/gallery"
                  value={websiteUrl}
                  disabled={submitting}
                  onChange={(e) => { setWebsiteUrl(e.target.value); setUrlError(null); }}
                  aria-invalid={Boolean(urlError)}
                  aria-describedby={urlError ? "url-error" : undefined}
                  className="rounded-control border border-line bg-surface px-3 py-2"
                />
                {urlError && <p id="url-error" role="alert" className="text-sm text-status-fail">{urlError}</p>}
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="max-pages" className="text-sm font-medium">Maximum pages to crawl</label>
                <select
                  id="max-pages"
                  value={maxPages}
                  disabled={submitting}
                  onChange={(e) => setMaxPages(Number(e.target.value))}
                  className="rounded-control border border-line bg-surface px-3 py-2"
                >
                  <option value={1}>1 page</option>
                  <option value={3}>3 pages</option>
                  <option value={5}>5 pages</option>
                  <option value={10}>10 pages</option>
                </select>
              </div>
              <p className="text-sm text-text-muted">
                BrandLens will discover photographs from this webpage and analyze unique supported images.
              </p>
            </div>
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
            <p role="alert" className="text-sm text-status-fail">{errors.criteria}</p>
          )}
          <div className="flex items-center gap-2 text-sm">
            <label htmlFor="rubric" className="font-medium text-text-muted">Rubric</label>
            <select
              id="rubric"
              value={rubricId}
              disabled={submitting}
              onChange={(e) => changeRubric(e.target.value)}
              className="rounded-control border border-line bg-surface px-3 py-2"
            >
              {RUBRICS.map((r) => (
                <option key={r.rubricId} value={r.rubricId}>{r.name}</option>
              ))}
            </select>
          </div>
        </Card>

        <div className="flex flex-col items-end gap-2">
          {submitError && <p role="alert" className="text-sm text-status-fail">{submitError}</p>}
          <Button type="submit" disabled={submitting}>
            {submitting ? "Submitting…" : "Analyze"}
          </Button>
        </div>
      </form>
    </main>
  );
}