import type { ImageResult } from "../api";

/**
 * Preview URL for a result image. Served by GET /api/v1/images/{id}/file
 * (proxied to the API in vite.config.ts during local dev).
 */
export function imageUrl(image: ImageResult): string | null {
  return `/api/v1/images/${image.image_id}/file`;
}
