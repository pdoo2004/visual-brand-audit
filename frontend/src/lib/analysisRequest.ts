export interface UploadSubmission {
  files: File[];
  rubricId: string;
  criterionIds: string[];
}

/**
 * Builds the multipart body for POST /api/v1/analyses/uploads.
 */
export function buildUploadFormData({ files, rubricId, criterionIds }: UploadSubmission): FormData {
  const body = new FormData();
  for (const file of files) body.append("files", file, file.name);
  body.append("rubric_id", rubricId);
  for (const id of new Set(criterionIds)) body.append("criterion_ids", id);
  return body;
}