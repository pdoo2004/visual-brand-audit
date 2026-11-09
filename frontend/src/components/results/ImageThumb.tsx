import type { ImageResult } from "../../api";
import { imageUrl } from "../../config/images";
import { displayName } from "../../lib/results";

/** The picture, or a labelled placeholder while the backend cannot serve images. */
export default function ImageThumb({ image, className = "" }: { image: ImageResult; className?: string }) {
  const url = imageUrl(image);
  const name = displayName(image.source);
  if (url) {
    return <img src={url} alt={name} className={`object-cover ${className}`} />;
  }
  return (
    <div
      role="img"
      aria-label={`${name} (preview not available)`}
      className={`flex items-center justify-center border border-line bg-surface-muted p-2 text-center text-xs text-text-muted ${className}`}
    >
      Preview not available
    </div>
  );
}