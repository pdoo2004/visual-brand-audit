# 3.1 — Research OpenCV/Pillow/scikit-learn approaches for brightness, color, contrast, and framing

**Jira:** SCRUM-116  
**Owner:** Sanish  
**Estimate:** 6 hours  
**Function:** CV Research

### Purpose

This task reviews practical methods for extracting measurable image features using OpenCV, Pillow, NumPy, and scikit-learn. The review is aligned with the six locked MVP criteria:

1. Q1 — Exposure and brightness  
2. Q2 — Contrast  
3. Q3 — Color palette fit  
4. Q4 — Framing and subject position  
5. Q5 — Sharpness and subject emphasis  
6. B1 — Tone and approachability  

The first five criteria can be supported by computer-vision measurements. B1 is context-dependent and will require a structured vision-language-model judgment. The purpose of this task is to identify candidate methods; implementation, testing, and threshold calibration will follow later.

### Q1. Exposure and brightness

Brightness is commonly represented using image intensity or luminance statistics. Datta et al. included average pixel intensity as a feature for photographic-aesthetic analysis, while Ke et al. used average brightness as part of a photo-quality assessment system [1, 2]. However, Ke et al. noted that the correct exposure may be different for the subject and the background, meaning that whole-image brightness alone is not sufficient. OpenCV can convert an RGB image to grayscale using a weighted intensity transformation. Pillow’s `ImageStat` can calculate statistics for an entire image or a masked region [5, 6].

**Candidate features:**

- Mean and median grayscale intensity.
- Proportion of pixels near black.
- Proportion of pixels near white.
- Mean intensity within the subject region, if available.
- Difference between subject and background brightness.

**Selected configuration baseline:** Mean luminance, near-black pixel fraction, and near-white pixel fraction, using the provisional bounds in `brand_standards.json`. Median intensity and subject/background brightness remain exploratory additions. The analyzer must use one documented intensity conversion consistently; OpenCV grayscale intensity and other luma conventions should not be treated as interchangeable.

**Limitation:** A dark or bright image is not automatically poor. The final interpretation must depend on the project rubric and the visual context.

### Q2. Contrast

Ke et al. measured contrast using the width containing the middle 98% of the image’s gray-level histogram rather than relying only on minimum and maximum intensity [2]. This reduces the effect of isolated extreme pixels.

For a simpler implementation, NumPy or Pillow can calculate the standard deviation of grayscale intensity. A percentile range, such as \(P_{95}-P_{5}\), is another robust measure of tonal spread.

**Candidate features:**

- Grayscale standard deviation.
- Difference between the 95th and 5th intensity percentiles.
- Width of the middle 98% histogram mass.
- Regional or subject/background contrast.

**Selected configuration baseline:** Luminance standard deviation, `p5_p95_range` (P95 minus P5), and near-black/near-white fractions. Apply the placeholder bounds and clipping cutoffs in the configuration. The middle-98% histogram width remains an alternative explored in the literature. Clipping measurements must be computed when contrast is selected even if exposure is not selected.

**Limitation:** Global contrast does not necessarily indicate whether the subject separates from the background. Higher contrast should not automatically receive a higher score.

Automatic histogram equalization should not be performed before extracting the feature because it changes the image’s intensity distribution and therefore changes the contrast being measured.

### Q3. Color palette fit

Color analysis in photographic-quality research has included color histograms, average saturation, average hue, and hue-count features. Ke et al. used color distributions and hue count to describe palette complexity and simplicity [2]. Datta et al. also examined color and saturation-related features [1].

OpenCV supports HSV and CIE Lab conversions. HSV is useful for analyzing saturation and value, while Lab is a candidate space for comparing colors and extracting representative palettes [5].

Scikit-learn’s K-means color-quantization example represents image pixels as points in a three-dimensional color space. The resulting cluster centers form a reduced color palette, and the number of pixels assigned to each cluster provides the proportion of each representative color [7].

**Candidate features:**

- Mean and median HSV saturation.
- Saturation distribution.
- Hue histogram or hue count.
- Dominant colors from K-means.
- Proportion of pixels represented by each dominant color.
- Distance between dominant colors and a configured brand palette.

**Selected configuration baseline:** Use K-means clustering in CIELAB with D65 white point to extract five representative colors and their pixel proportions. The current configuration proposes a random seed of 42 and Euclidean Delta E 76 distance. For each representative color, find the nearest configured palette color; calculate `palette_distance` as the proportion-weighted mean of those nearest distances. Lower values indicate closer palette fit. The current palette is an unconfirmed placeholder, and the acceptance threshold is unset. HSV saturation and hue statistics remain supplementary research features. Sampling, initialization settings, and color encoding must be fixed during implementation for reproducibility. Use consistently scaled Lab values for distance calculations.

For cluster proportions p_i, cluster colors c_i, and palette colors b_j:

$$D = \sum_i p_i \min_j d(c_i, b_j)$$

This is a continuous palette-distance measure; the configured approach does not use a brand-color pixel-coverage pass/fail rule.

**Limitations:** K-means depends on the selected number of clusters, initialization, and sampled pixels. A large background may dominate the palette. Color similarity alone does not establish color harmony or brand alignment.

### Q4. Framing and subject position

Framing cannot be evaluated reliably from image dimensions alone. Luo and Tang first extracted a subject region and then calculated features using the subject/background division [3]. Luo, Wang, and Tang also investigated content-based photo-quality assessment, motivating consideration of image content alongside global measurements [4].

OpenCV provides saliency APIs, including spectral-residual and fine-grained static saliency methods, which can be explored as an initial estimate of visually prominent regions [8].

**Candidate features:**

- Normalized subject-center coordinates.
- Subject area relative to total image area.
- Distance from the subject to each image border.
- Distance from the subject center to the image center.
- Distance from the subject center to rule-of-thirds intersections.
- Amount of available space around the subject.

**Selected configuration baseline:** Obtain a subject region and report `subject_bbox` in normalized x, y, width, height coordinates, `center_offset`, `thirds_offset`, and `edge_margin_min`. The localization method and geometric thresholds are not finalized. Saliency is an exploratory localization option, and occupancy is supplementary evidence. Missing or unreliable subject localization should produce `unavailable_needs_review`, not an automatic framing failure.

**Limitation:** Saliency does not necessarily identify the intended subject. Multiple subjects, textured backgrounds, and landscape photographs may produce ambiguous results. Centered composition and rule-of-thirds composition should initially be reported as measurements rather than treated as universal requirements.

### Q5. Sharpness and subject emphasis

Sharpness is commonly estimated from the amount of high-frequency image information. Focus-measure research groups methods into gradient-based, Laplacian-based, wavelet-based, statistical, and frequency-domain families [9]. Gradient and Laplacian methods are practical for an OpenCV prototype, but their results can be sensitive to image noise, texture, contrast, and the size of the evaluation region.

Ke et al. also used blur and frequency-related features in photo-quality assessment [2]. Luo and Tang’s subject-focused approach supports comparing the subject region with the background rather than evaluating the entire image only [3].

**Candidate features:**

- Variance of the Laplacian.
- Gradient magnitude or gradient-energy statistics.
- High-frequency energy.
- Subject sharpness compared with background sharpness.
- Optional blur estimation using frequency-domain features.

**Selected configuration baseline:** Use variance of the Laplacian to obtain `subject_sharpness` and `background_sharpness`, then calculate `sharpness_ratio`. Gradient energy and frequency-domain features remain alternatives for experimentation. Framing and sharpness share a subject-region dependency. Handle missing regions and a zero background-sharpness denominator explicitly during implementation; do not produce an infinite ratio. Thresholds remain unset. Sharpness ratio alone does not establish visual dominance or message clarity. Intentional motion is not an automatic failure and should be reviewed in context.

**Limitation:** A textured region may appear sharp even when it is blurred, while a smooth subject may produce a low sharpness value despite being in focus. Measurements also depend on resolution and processing. Establish a consistent analysis resolution and document it before calibrating thresholds; this is an implementation decision, not a requirement to alter the existing preprocessing behavior.

### B1. Tone and approachability

Tone and approachability are not reliably determined from brightness, color, contrast, or framing measurements alone. Those measurements can provide supporting evidence, but the judgment depends on content, context, people, and the intended brand personality.

**Candidate approach:**

- Provide the image and the configured placeholder target tone, “approachable, competent,” to a vision-language model.
- Require a structured label from the configured allowed labels: `approachable` or `competent`. A low fit score must remain possible for images that do not fit the target tone.
- Request an integer fit score of 1–5. The scoring engine maps it to 0–100 using `(fit_score - 1) / 4 * 100`, identified in the configuration as `linear_1_5_to_0_100`.
- Require one sentence identifying visible evidence.
- On model failure or invalid output, mark B1 as `unavailable_needs_review` and continue returning available CV results. Retry behavior belongs to the model client; the current configuration includes a provisional `max_retries` setting.
- If uncertain responses should trigger review, define an explicit validation/review rule first; this is not currently specified by the rubric.

This criterion should remain separate from the OpenCV/Pillow/scikit-learn feature extractor. The CV pipeline can provide measurable evidence, while the vision-language model evaluates the contextual brand criterion.

### Research scope and selected baseline

The candidate features above describe the research scope. The current `brand_standards.json` selects a smaller baseline; additional features remain exploratory unless incorporated into a later rubric version. Method selection is provisional and does not imply that the analyzer or scoring logic has been implemented.

| MVP criterion | Selected configuration baseline | Main library or tool |
|---|---|---|
| Q1 Exposure and brightness | Mean luminance and near-black/near-white fractions | OpenCV, NumPy, Pillow |
| Q2 Contrast | Luminance standard deviation, P95–P5 range, and clipping fractions | NumPy, Pillow, OpenCV |
| Q3 Color palette fit | Lab K-means, cluster proportions, and weighted nearest-palette distance | OpenCV, scikit-learn, NumPy |
| Q4 Framing and subject position | Subject bounding box, center/thirds offsets, and minimum edge margin | OpenCV, NumPy |
| Q5 Sharpness and subject emphasis | Subject/background Laplacian variance and sharpness ratio; emphasis limitations require review | OpenCV, NumPy |
| B1 Tone and approachability | Configured target tone, allowed label, integer 1–5 fit score, and visible evidence | Vision-language model |

### Relationship to Subtask 1.3

Subtask 3.1 identifies candidate methods and motivates the proposed baseline. Subtask 1.3 records the criterion definitions, expected evidence, evaluator methods, parameters, and required outputs in the configuration. The palette, tone words, and numerical bounds remain provisional. Weights, the overall flag threshold, and several criterion thresholds remain unset; `scoring_ready` is false. The schema intentionally leaves `params` flexible, so additional parameter and scoring-readiness validation is required in implementation.

Human-readable explanations are generated for each photograph by the evaluation/scoring pipeline. For CV criteria, explanations should be grounded in measurements and decision rules; for B1, the model must cite visible evidence. These per-image explanations are not fixed review text stored in `brand_standards.json`. Reviewer Agree/Disagree feedback is a separate downstream function.

### Conclusion

The literature supports using interpretable image features as a practical baseline for Q1–Q5. Brightness, contrast, color distribution, subject position, and sharpness have all been used in computational photography or photo-quality research. The research also shows that whole-image features are insufficient for some judgments, particularly exposure, framing, and subject emphasis. Subject-region analysis should therefore be added when a reliable subject location is available.

For this project, the next step is to test the recommended baseline methods on representative photographs and compare the outputs with human judgments. The extracted measurements should remain separate from pass/fail scoring so that thresholds can be revised after mentor and team review.

### References

1. Datta, R., Joshi, D., Li, J., & Wang, J. Z. (2006). *Studying aesthetics in photographic images using a computational approach*. ECCV, 288–301. https://doi.org/10.1007/11744078_23

2. Ke, Y., Tang, X., & Jing, F. (2006). *The design of high-level features for photo quality assessment*. CVPR, 419–426. https://mmlab.ie.cuhk.edu.hk/pdf/keTJ_CVPR06.pdf

3. Luo, Y., & Tang, X. (2008). *Photo and video quality evaluation: Focusing on the subject*. ECCV. https://mmlab.ie.cuhk.edu.hk/2008/ECCV2008LuoTang.pdf

4. Luo, W., Wang, X., & Tang, X. (2011). *Content-based photo quality assessment*. ICCV. https://mmlab.ie.cuhk.edu.hk/project_photo_quality.html

5. OpenCV. *Color conversions*. https://docs.opencv.org/4.x/de/d25/imgproc_color_conversions.html

6. Pillow. *ImageStat module*. https://pillow.readthedocs.io/en/stable/reference/ImageStat.html

7. Scikit-learn. *Color quantization using K-means*. https://scikit-learn.org/1.5/auto_examples/cluster/plot_color_quantization.html

8. OpenCV. *Saliency API*. https://docs.opencv.org/4.x/d8/d65/group__saliency.html

9. Pertuz, S., Puig, D., & Garcia, M. A. (2013). *Analysis of focus measure operators for shape-from-focus*. Pattern Recognition, 46(5), 1415–1432. https://doi.org/10.1016/j.patcog.2012.11.011