/**
 * Selectable criteria for Screen 1.
 * */
export type CriterionMethod = "cv" | "vlm";

export interface CriterionOption {
  criterionId: string;
  name: string;
  method: CriterionMethod;
}

export interface RubricOption {
  rubricId: string;
  name: string;
  criteria: CriterionOption[];
}

export const DEFAULT_RUBRIC: RubricOption = {
  rubricId: "default-v1-draft",
  name: "Default photography standards",
  criteria: [
    { criterionId: "exposure_brightness", name: "Exposure and brightness", method: "cv" },
    { criterionId: "contrast", name: "Contrast", method: "cv" },
    { criterionId: "color_palette_fit", name: "Color palette fit", method: "cv" },
    { criterionId: "framing_subject_position", name: "Framing and subject position", method: "cv" },
    { criterionId: "sharpness_subject_emphasis", name: "Sharpness and subject emphasis", method: "cv" },
    { criterionId: "tone_approachability", name: "Tone and approachability", method: "vlm" },
  ],
};

export const RUBRICS: RubricOption[] = [DEFAULT_RUBRIC];

export const METHOD_GROUPS: { method: CriterionMethod; heading: string }[] = [
  { method: "cv", heading: "Measured attributes" },
  { method: "vlm", heading: "Tone and message" },
];