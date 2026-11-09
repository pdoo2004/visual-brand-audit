import type { ImageResult } from "../api";

/**
 * Where an image's picture comes from. The backend has no image-serving endpoint yet, so this
 * returns null and the UI shows a placeholder tile. When the endpoint exists, change only this
 * function, e.g. `return \`/api/v1/images/${image.image_id}/file\`;`
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function imageUrl(_image: ImageResult): string | null {
  return null;
}