"""CV implementations available to brand configuration.

To add an implementation: import its class and add it to CV_REGISTRY below.
Settings, defaults, output units, descriptions, and input requirements belong
inside each criterion. This file contains no copies of those specifications.
"""

from .brightness_criterion import BrightnessCriterion
from .color_palette_criterion import ColorPaletteCriterion
from .contrast_criterion import ContrastCriterion
from .registry_support import CVRegistry
from .subject_framing_criterion import SubjectFramingCriterion
from .subject_sharpness_criterion import SubjectSharpnessCriterion

CV_REGISTRY = CVRegistry(
    (
        BrightnessCriterion,
        ContrastCriterion,
        ColorPaletteCriterion,
        SubjectFramingCriterion,
        SubjectSharpnessCriterion,
    )
)

get_cv_registration = CV_REGISTRY.get_registration
get_cv_catalog = CV_REGISTRY.get_catalog
