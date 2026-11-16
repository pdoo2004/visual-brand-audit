# 3.9 throughput results

Results were obtained from these saved runs:

| Run | Median batch seconds | Images/second | Speedup |
| --- | ---: | ---: | ---: |
| [baseline_20261116T214849195871Z](baseline_20261116T214849195871Z/run.json) | 3.368673 | 2.968528 | 1.000x |
| [optimized_20261116T234404698970Z](optimized_20261116T234404698970Z/run.json) | 2.181725 | 4.583530 | 1.544x |

This comparison shows **54.4% higher measured throughput**. Both runs use the
same ten photographs and preprocessing/CV/scoring settings. One warm-up batch
is excluded; the baseline has eleven measured batches and the optimized run
has three. Timings vary between runs, so the improvement applies to this saved
comparison.

All seven [acceptance checks](optimized_20261116T234404698970Z/comparison_checks.csv)
passed: repeatable outputs, matching inputs/settings and environment, identical
standardized pixels, CV/scoring outputs within `rtol=atol=1e-9`, and improved
median throughput.

Color palette analysis avoids sorting the complete sampled colors when a small
prefix already proves sufficient diversity. Compiled squared-Euclidean distance
calculations reduce temporary arrays during full-image cluster assignment.
Sampling and K-means settings remain unchanged.

The [3.9 notebook](../../examples/3_9_throughput_benchmark.ipynb) shows the current
run against `BASELINE_JSON`. Set the optional `OLD_RUN_JSON` to a saved `run.json`
to add a third `old_run` row without processing that run again. Speedup is relative
to the baseline. Historical compatibility checks appear separately; incompatible
old runs have no speedup value.

Saved run folders contain measurements and outputs in `run.json`, timing CSVs,
stage logs, and comparison checks. The benchmark covers loading, preprocessing,
brightness, contrast, color palette analysis, and scoring. VLM requests, subject
detection, framing/sharpness, persistent image writes, and database work are
outside its scope.
