# Benign Evaluation Dataset

This dataset is case-aware: positives come from the six active materialized cases, while benign candidates are sampled from the same oracle-scope surface without using rank truncation, scoring formulas, amount ranking, or nondeterministic random sampling.

## Current Counts

- Positive cases: `6`
- Benign candidates: `60`
- Benign verified rows: `30`
- Unknown negatives: `30`
- False-positive denominator: `30`

## Strata

- Same-oracle: `30`
- Same-protocol: `0`
- Cross-protocol oracle-scope: `30`

## Local Verification Policy

Only `benign_verified` rows enter the false-positive denominator. `unknown_negative` rows are a review/materialization queue and must be replayed locally before being treated as safe negatives.

## SQL

Rendered Dune SQL: `artifacts/eval_dataset/sql`
