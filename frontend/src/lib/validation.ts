export const ALLOWED_MIME_TYPES = ["image/jpeg", "image/png", "image/webp"] as const;
export const ACCEPT_ATTRIBUTE = ALLOWED_MIME_TYPES.join(",");
export const MAX_FILE_BYTES = 10 * 1024 * 1024; // contract: proposed 10 MB per file

export interface FileProblem {
  fileName: string;
  message: string;
}

export interface FileSplit {
  accepted: File[];
  rejected: FileProblem[];
}

function formatMb(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Splits picked files into ones the API will accept and ones it would reject. */
export function checkFiles(files: File[]): FileSplit {
  const accepted: File[] = [];
  const rejected: FileProblem[] = [];
  for (const file of files) {
    if (!(ALLOWED_MIME_TYPES as readonly string[]).includes(file.type)) {
      rejected.push({ fileName: file.name, message: "Unsupported type. Use JPEG, PNG, or WebP." });
    } else if (file.size > MAX_FILE_BYTES) {
      rejected.push({
        fileName: file.name,
        message: `Too large (${formatMb(file.size)}). Limit is ${formatMb(MAX_FILE_BYTES)}.`,
      });
    } else if (file.size === 0) {
      rejected.push({ fileName: file.name, message: "File is empty." });
    } else {
      accepted.push(file);
    }
  }
  return { accepted, rejected };
}

/** Adds new files to the current list, skipping exact duplicates (same name, size, mtime). */
export function mergeFiles(current: File[], incoming: File[]): File[] {
  const key = (f: File) => `${f.name}|${f.size}|${f.lastModified}`;
  const seen = new Set(current.map(key));
  return [...current, ...incoming.filter((f) => !seen.has(key(f)))];
}

export interface FormErrors {
  files?: string;
  criteria?: string;
}

export function validateForm(files: File[], criterionIds: string[]): FormErrors {
  const errors: FormErrors = {};
  if (files.length === 0) errors.files = "Add at least one photograph.";
  if (criterionIds.length === 0) errors.criteria = "Select at least one criterion.";
  return errors;
}