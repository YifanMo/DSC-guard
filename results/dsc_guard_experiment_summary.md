# DSC-Guard Experiment Summary

This experiment uses local materialized artifacts only: six positive oracle-consumption failure cases and the no-Dune 10k benign sample set.

- RQ2 positive recall: `6/6` cases, `285/285` impact txs.
- RQ2 confirmed strict attack FP rate: `0.00%` over `9637` strict benign rows; `349` unknown rows and `14` review rows are excluded from the strict denominator.

Do not interpret the positive-set result as universal oracle-attack precision/recall. The supported claim is replayability over the curated target failure class plus no confirmed strict attack false positives over verified hard-benign samples.

Claim boundary: DSC-Guard here is evaluated as a log-semantics and K-style replay tool for EVM lending price-oracle consumption failures. It is not a complete EVM semantics, full DON attack detector, or production exploit predictor.
