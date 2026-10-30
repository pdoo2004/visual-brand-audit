"""CV implementations available to brand configuration.

To add an implementation: import its class and add it to _IMPLEMENTATIONS below.
Settings, defaults, output units, descriptions, and input requirements belong
inside each criterion. This file contains no copies of those specifications.
"""

from .brightness_criterion import BrightnessCriterion
from .color_palette_criterion import ColorPaletteCriterion
from .contrast_criterion import ContrastCriterion
from .subject_framing_criterion import SubjectFramingCriterion
from .subject_sharpness_criterion import SubjectSharpnessCriterion

_IMPLEMENTATIONS = (
    BrightnessCriterion,
    ContrastCriterion,
    ColorPaletteCriterion,
    SubjectFramingCriterion,
    SubjectSharpnessCriterion,
)

CV_REGISTRY = {cls.implementation_id: cls for cls in _IMPLEMENTATIONS}
if len(CV_REGISTRY) != len(_IMPLEMENTATIONS):
    raise ValueError("Duplicate CV implementation_id.")


def get_cv_catalog(*, include_defaults: bool = True) -> list[dict]:
    """Describe available implementations for configuration authors."""
    return [
        cls.describe(include_defaults=include_defaults) for cls in CV_REGISTRY.values()
    ]
