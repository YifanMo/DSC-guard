# RQ2 Attack Detection Effectiveness

- Positive case recall: `6/6` (`100.00%`)
- Positive impact tx recall: `285/285` (`100.00%`)

| Case | Class | Impact tx | Detected tx | Alerts | Attackers |
|---|---|---:|---:|---:|---:|
| `ploutos` | `feed_binding` | 1 | 1 | 3 | 1 |
| `moonwell_cbeth` | `price_semantics` | 123 | 123 | 124 | 14 |
| `moonwell_wrseth` | `price_semantics` | 12 | 12 | 13 | 2 |
| `blueberry_faulty_oracle` | `price_semantics` | 1 | 1 | 2 | 2 |
| `venus_luna` | `freshness` | 95 | 95 | 201 | 12 |
| `blizz_luna` | `freshness` | 53 | 53 | 88 | 24 |

## Log-Level Metrics

- All case semantic logs: `470`
- Incident warning alerts: `431` (`91.70%` incident-log warning recall)
- Direct violation target logs: `291`
- Detected direct violation logs: `291` (`100.00%` recall)
- Collateral-enabling early evidence logs: `140`
- Target semantic logs: `431`
- Detected target semantic logs: `431` (`100.00%` recall)
- Canonical target logs: `429`
- Semantic-marker target records: `2`
- Context-only records included in all-log denominator: `179`
- Support-only context records not alerted: `39`
- Replay coverage over all semantic logs: `100.00%`
- Strict log precision: `100.00%`
- Conservative precision floor if review rows are counted as FP: `96.85%`
- Strict benign log rows: `9637`
- Unknown benign log rows excluded: `349`
- Review/alert benign log rows excluded: `14`

## Benign Set

- Materialized benign rows: `10000`
- Strict benign rows: `9637`
- Unknown rows excluded from FP denominator: `349`
- Review rows excluded from strict FP denominator: `14`
- Full DSC-Guard strict row FP rate: `0.00%`

## Baselines

| Baseline | Case recall | Tx recall | Description |
|---|---:|---:|---|
| `abi_only_parser` | `0.00%` | `0.00%` | Decodes event shape only and has no oracle-consumption constraints. |
| `tx_level_only_impact_visibility` | `100.00%` | `100.00%` | Sees downstream impact events but does not bind them to prior oracle semantics. |
| `full_dsc_guard` | `100.00%` | `100.00%` | Log semantics plus evidence closure and K-style oracle-consumption replay constraints. |
