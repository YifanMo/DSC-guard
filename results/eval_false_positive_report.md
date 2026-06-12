# Benign False Positive Report

Replay has not been executed by this builder. It prepares the labelled evaluation inputs and separates verified benign rows from unknown negatives.

- Positive recall denominator: `6`
- False-positive denominator: `30`
- Expected benign replay result: `violation=false`, no attacker localization, no violated K-style constraint.

Run the local verifier/materializer over `artifacts/eval_dataset/*.jsonl` before reporting final FP metrics.
