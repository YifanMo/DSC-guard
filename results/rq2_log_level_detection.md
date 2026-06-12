# RQ2 Log-Level Detection Metrics

This report adds collateral-enabling early evidence as a log-warning category. It does not add, remove, or relabel experiment data.

## Definitions

- Positive target logs: Target logs now include direct violation records plus collateral-enabling early evidence. A SUPPLY record is counted as early evidence only when a bad-oracle/stale state is already active and the same actor later produces a borrow/liquidation impact; remaining context logs stay in the all-semantic denominator as support-only records.
- Benign negative logs: Each materialized benign sample row is treated as one log-level negative candidate. Only verified strict benign rows enter the confirmed FP denominator; unknown and review rows are reported separately.
- Context-only logs, such as SUPPLY records used to build a causal replay trace, are now included in the all-semantic-log recall denominator. They are still reported separately because they are not direct violation targets.
- Collateral-enabling SUPPLY logs are counted as early evidence only when they are bound to an active bad-oracle state and a later same-actor borrow/liquidation impact.

## Summary

- All case semantic logs: `470`
- Incident warning alerts: `431`
- Incident-log warning recall: `91.70%`
- Incident-log warning recall Wilson 95% CI: `88.86% - 93.87%`
- Direct violation target logs: `291`
- Detected direct violation logs: `291`
- Direct-violation recall: `100.00%`
- Collateral-enabling early evidence logs: `140`
- Detected early evidence logs: `140`
- Context-only records included in all-log denominator: `179`
- Support-only context records not alerted: `39`
- Replay coverage over all semantic logs: `470/470` (`100.00%`)
- Target semantic logs: `431`
- Detected target semantic logs: `431`
- Target-log recall: `100.00%`
- Target-log recall Wilson 95% CI: `99.12% - 100.00%`
- Canonical target logs: `429`
- Canonical target-log recall: `100.00%`
- Semantic-marker target records: `2`
- Materialized benign log rows: `10000`
- Strict benign log rows: `9637`
- Confirmed strict FP log rows: `0`
- Unknown log rows excluded: `349`
- Review/alert log rows excluded: `14`
- Strict log precision: `100.00%`
- Strict precision Wilson 95% CI: `99.12% - 100.00%`
- Conservative precision floor with review rows counted as FP: `96.85%`

## Per-Case Positive Logs

| Case | Class | All logs | Warning alerts | Direct violation | Early evidence | Support-only | Warning recall | Direct recall |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `ploutos` | `feed_binding` | 4 | 3 | 2 | 1 | 1 | `75.00%` | `100.00%` |
| `moonwell_cbeth` | `price_semantics` | 124 | 124 | 124 | 0 | 0 | `100.00%` | `100.00%` |
| `moonwell_wrseth` | `price_semantics` | 13 | 13 | 13 | 0 | 0 | `100.00%` | `100.00%` |
| `blueberry_faulty_oracle` | `price_semantics` | 2 | 2 | 2 | 0 | 0 | `100.00%` | `100.00%` |
| `venus_luna` | `freshness` | 218 | 201 | 96 | 105 | 17 | `92.20%` | `100.00%` |
| `blizz_luna` | `freshness` | 109 | 88 | 54 | 34 | 21 | `80.73%` | `100.00%` |

## Target Event Types

| Event type | Target logs | Detected |
|---|---:|---:|
| `BORROW` | 176 | 176 |
| `LIQUIDATE` | 109 | 109 |
| `ORACLE_FEED_SET` | 1 | 1 |
| `ORACLE_FORMULA_SET` | 1 | 1 |
| `ORACLE_IMPLEMENTATION_MISMATCH` | 1 | 1 |
| `ORACLE_PRICE_MALFUNCTION` | 1 | 1 |
| `STALE_ORACLE_START` | 2 | 2 |
| `SUPPLY` | 140 | 140 |

## Interpretation

The incident-log warning recall includes direct violation alerts and collateral-enabling SUPPLY alerts. A SUPPLY record is not treated as suspicious by topic alone; it must be connected to an already active bad-oracle state and a later same-actor borrow or liquidation impact. Remaining support-only context records stay in the denominator and prevent the metric from becoming trivially perfect.

The strict precision remains high because no verified benign log row produced a confirmed replayable violation. To avoid overclaiming, the table also reports a conservative precision floor that treats all review/alert benign rows as if they were false positives.
