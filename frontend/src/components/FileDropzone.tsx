import { useId, useState } from "react";
import { ACCEPT_ATTRIBUTE } from "../lib/validation";

interface FileDropzoneProps {
  files: File[];
  onAdd: (files: File[]) => void;
  onRemove: (index: number) => void;
  error?: string;
  disabled?: boolean;
}

export default function FileDropzone({ files, onAdd, onRemove, error, disabled }: FileDropzoneProps) {
  const inputId = useId();
  const [dragging, setDragging] = useState(false);

  function handleFiles(list: FileList | null) {
    if (list && list.length > 0) onAdd(Array.from(list));
  }

  return (
    <div className="flex flex-col gap-3">
      <label
        htmlFor={inputId}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (!disabled) handleFiles(e.dataTransfer.files);
        }}
        className={`flex min-h-40 flex-col items-center justify-center gap-1 rounded-card border-2 border-dashed px-4 py-8 text-center text-sm ${
          dragging ? "border-brand-500 bg-brand-50" : "border-line bg-surface-muted"
        } ${disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer"}`}
      >
        <span className="font-medium">Drop photos here</span>
        <span className="text-text-muted">or click to browse. JPEG, PNG, or WebP, up to 10 MB each.</span>
        <input
          id={inputId}
          type="file"
          multiple
          accept={ACCEPT_ATTRIBUTE}
          disabled={disabled}
          className="sr-only"
          onChange={(e) => {
            handleFiles(e.target.files);
            e.target.value = ""; // allow re-picking the same file after removing it
          }}
        />
      </label>

      {error && (
        <p role="alert" className="text-sm text-status-fail">
          {error}
        </p>
      )}

      {files.length > 0 && (
        <ul className="flex flex-col divide-y divide-line rounded-control border border-line bg-surface text-sm">
          {files.map((file, index) => (
            <li
              key={`${file.name}-${file.size}-${file.lastModified}`}
              className="flex items-center justify-between gap-3 px-3 py-2"
            >
              <span className="truncate">{file.name}</span>
              <span className="flex shrink-0 items-center gap-3">
                <span className="text-text-muted">{(file.size / 1024).toFixed(0)} KB</span>
                <button
                  type="button"
                  onClick={() => onRemove(index)}
                  disabled={disabled}
                  aria-label={`Remove ${file.name}`}
                  className="text-text-muted hover:text-ink disabled:opacity-50"
                >
                  Remove
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}