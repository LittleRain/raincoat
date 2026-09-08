# Scoring model

Normalize each signal to 0–1, then calculate `score = 100 × Σ(weight_i × signal_i)`. Normalize edited weights to sum to 1. Completeness is a gate or penalty: candidates below `completeness_threshold` should not enter 精选版 and must be flagged in HTML. Cap duration's contribution so pauses are not mistaken for long rallies.

- 精选版: highest scores and high completeness confidence.
- 标准版: balanced score and target duration.
- 完整版: more qualifying rallies, excluding invalid or severely truncated clips.

Reasons must be traceable to signals; do not claim exact shuttle speed unless it was actually measured.
