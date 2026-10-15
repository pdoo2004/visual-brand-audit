"""Task 3.4: integrate geometry filtering and image standardization."""

from collections.abc import Mapping

from PIL import Image

from .photo_filter import FilterSettings, filter_photo
from .standardization import StandardizationSettings, standardize_image


def _resolve_settings(filter_settings, standardization_settings):
    """Create defaults and reject invalid configuration before processing."""
    if filter_settings is None:
        filter_settings = FilterSettings()
    if standardization_settings is None:
        standardization_settings = StandardizationSettings()
    if not isinstance(filter_settings, FilterSettings):
        raise TypeError("filter_settings must be a FilterSettings object.")
    if not isinstance(standardization_settings, StandardizationSettings):
        raise TypeError("standardization_settings must be a StandardizationSettings object.")
    return filter_settings, standardization_settings


def preprocess_image(
    image: Image.Image,
    filter_settings: FilterSettings | None = None,
    standardization_settings: StandardizationSettings | None = None,
) -> Image.Image | None:
    """Filter an image, then standardize it if accepted.

    Args:
        image: Loaded Pillow image. The input is not modified or closed.
        filter_settings: Geometry thresholds; None uses defaults.
        standardization_settings: Output settings; None uses defaults.

    Returns:
        Image.Image | None: A new standardized image, or None if excluded.
        The caller owns the returned image and may close it when finished.

    Raises:
        TypeError: If input or settings have incorrect types.
        ValueError: If image validation or standardization fails.
        OSError: If image decoding or processing fails.

    Notes:
        Filtering uses original dimensions, before resizing. Passing geometry
        rules does not confirm photographic content. Loading and saving are
        caller responsibilities. Exceptions from the component functions
        propagate to the caller.
    """
    filter_settings, standardization_settings = _resolve_settings(filter_settings, standardization_settings)
    
    if not isinstance(image, Image.Image):
        raise TypeError("image must be a Pillow image.")
    if min(image.size) <= 0:
        raise ValueError("Image dimensions must be positive.")
    if getattr(image, "n_frames", 1) > 1:
        raise ValueError("Animated or multi-frame images are not supported.")

    filtered = filter_photo(image, filter_settings)
    if filtered is None:
        return None
    return standardize_image(filtered, standardization_settings)


def preprocess_batch(
    images: Mapping[str, Image.Image],
    filter_settings: FilterSettings | None = None,
    standardization_settings: StandardizationSettings | None = None,
) -> dict:
    """Process a batch while preserving input identifiers.

    Args:
        images: Mapping of unique, nonempty string IDs to loaded images.
        filter_settings: Geometry thresholds; None uses defaults.
        standardization_settings: Output settings; None uses defaults.

    Returns:
        dict: Three mappings: accepted (ID to new Pillow image), excluded
        (ID to reason), and errors (ID to error text). Every input ID occurs
        in exactly one mapping on normal completion. Empty input returns
        three empty mappings. Accepted images are owned by the caller.
        This dictionary contains image objects and is not JSON serializable.

    Raises:
        TypeError: If the batch container, IDs, or configuration are invalid.
        ValueError: If an ID is empty or whitespace-only.

    Notes:
        Expected per-image TypeError, ValueError, and OSError exceptions are
        recorded and processing continues. Unexpected programming errors and
        interrupts propagate. Already-created outputs are closed if the batch
        aborts. Inputs remain owned by the caller. Invalid batch configuration
        is rejected before any images are processed.
    """
    filter_settings, standardization_settings = _resolve_settings(
        filter_settings, standardization_settings
    )
    if not isinstance(images, Mapping):
        raise TypeError("images must be a mapping of IDs to Pillow images.")
    for image_id in images:
        if not isinstance(image_id, str):
            raise TypeError("Image IDs must be strings.")
        if not image_id.strip():
            raise ValueError("Image IDs must not be empty.")

    result = {"accepted": {}, "excluded": {}, "errors": {}}
    try:
        for image_id, image in images.items():
            try:
                processed = preprocess_image(
                    image, filter_settings, standardization_settings
                )
            except (TypeError, ValueError, OSError) as error:
                result["errors"][image_id] = f"{type(error).__name__}: {error}"
                continue
            if processed is None:
                result["excluded"][image_id] = "Rejected by geometry filter."
            else:
                result["accepted"][image_id] = processed
    except BaseException:
        # Cleanup only; never suppress interrupts or unexpected failures.
        for processed in result["accepted"].values():
            processed.close()
        raise
    return result
