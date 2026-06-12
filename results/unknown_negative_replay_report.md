# Unknown-Negative Benign Replay

This run materialized the `unknown_negative` hard-benign candidates with read-only historical receipts, bytecode, source metadata, and minimal replay traces.

- Input samples: `0`
- Materialized samples: `10000`
- Replay alerts: `14`
- Strict benign after replay: `9637`
- Needs review or alert after replay: `363`
- RPC requests: `0/60000`
- Explorer/source requests: `0/12000`
- Debug trace requests: `0/2000`
- Cumulative RPC cache files: `38275`
- Cumulative source/ABI cache files: `5508`
- Cumulative debug trace cache files: `312`

## By Case

| case | samples | replay alerts |
|---|---:|---:|
| blizz_luna | 1623 | 0 |
| blueberry_faulty_oracle | 34 | 0 |
| moonwell_cbeth | 2896 | 0 |
| moonwell_wrseth | 636 | 0 |
| ploutos | 60 | 14 |
| venus_luna | 4751 | 0 |

## Verification Status

| status | rows |
|---|---:|
| materialized_no_replayable_constraint_violation | 9591 |
| needs_review_case_asset_other_feed | 14 |
| unknown_after_materialization | 349 |
| verified_no_case_feed_mismatch | 46 |

Rows marked `materialized_no_replayable_constraint_violation` or `verified_no_case_feed_mismatch` can be counted as replay-checked benign for the current DSC-Guard constraints. Rows marked `unknown_after_materialization` remain review candidates and should not enter the strict false-positive denominator.
