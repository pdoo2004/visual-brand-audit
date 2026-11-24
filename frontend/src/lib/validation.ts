export const ALLOWED_MIME_TYPES = ["image/jpeg", "image/png", "image/webp"] as const;
export const ACCEPT_ATTRIBUTE = ALLOWED_MIME_TYPES.join(",");
export const MAX_FILE_BYTES = 10 * 1024 * 1024; // contract: proposed 10 MB per file
// Batch limits. These mirror the API defaults (BRANDLENS_MAX_FILES_PER_REQUEST and
// BRANDLENS_MAX_TOTAL_BYTES); the API enforces them regardless, this just warns earlier.
export const MAX_FILES = 20;
export const MAX_TOTAL_BYTES = 100 * 1024 * 1024;

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

/** Keeps files in order until the batch would pass the file-count or total-size limit. */
export function capFiles(files: File[]): FileSplit {
  const accepted: File[] = [];
  const rejected: FileProblem[] = [];
  let total = 0;
  for (const file of files) {
    if (accepted.length >= MAX_FILES) {
      rejected.push({
        fileName: file.name,
        message: `Not added. One analysis can include up to ${MAX_FILES} photos.`,
      });
    } else if (total + file.size > MAX_TOTAL_BYTES) {
      rejected.push({
        fileName: file.name,
        message: `Not added. One analysis can include up to ${formatMb(MAX_TOTAL_BYTES)} in total.`,
      });
    } else {
      accepted.push(file);
      total += file.size;
    }
  }
  return { accepted, rejected };
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