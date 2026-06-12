# RQ2 Ablation Study

This ablation evaluates whether DSC-Guard's log-semantics binding is necessary for replayable oracle-consumption detection.

- Positive cases: `6`
- Positive impact txs: `285`
- Known actors: `55`
- Strict benign rows: `9637`

| Variant | Replayable case recall | Impact tx recall | Pre-attack tx evidence | Actor recall | Strict attack FP | Benign warning rate |
|---|---:|---:|---:|---:|---:|---:|
| `full_dsc_guard` | `6/6` (100.00%) | `285/285` (100.00%) | `4/6` (66.67%) | `55/55` (100.00%) | `0/9637` (0.00%) | `14/10000` (0.14%) |
| `without_log_semantics_abi_only` | `0/6` (0.00%) | `0/285` (0.00%) | `0/6` (0.00%) | `0/55` (0.00%) | `0/9637` (0.00%) | `9641/10000` (96.41%) |
| `topic_only_raw_filter` | `0/6` (0.00%) | `0/285` (0.00%) | `0/6` (0.00%) | `0/55` (0.00%) | `0/9637` (0.00%) | `10000/10000` (100.00%) |
| `oracle_boundary_without_lending_binding` | `0/6` (0.00%) | `0/285` (0.00%) | `4/6` (66.67%) | `0/55` (0.00%) | `0/9637` (0.00%) | `10000/10000` (100.00%) |
| `impact_only_without_oracle_boundary` | `0/6` (0.00%) | `0/285` (0.00%) | `0/6` (0.00%) | `0/55` (0.00%) | `0/9637` (0.00%) | `0/10000` (0.00%) |

## Variant Meaning

- `full_dsc_guard`: Full log-semantics binding plus evidence closure and K-style replay constraints.
- `without_log_semantics_abi_only`: ABI/event-shape information only; semantic bindings for asset/feed/actor/collateral are removed.
- `topic_only_raw_filter`: Topic/contract/transaction visibility only; no ABI parameters and no semantic roles.
- `oracle_boundary_without_lending_binding`: Oracle boundary semantics are kept, but downstream lending semantics are removed.
- `impact_only_without_oracle_boundary`: Borrow/liquidation impact logs are kept, but oracle boundary and anomaly semantics are removed.

## Per-Case Replayable Detection

| Variant | Ploutos | Moonwell cbETH | Moonwell wrsETH | Blueberry | Venus LUNA | Blizz LUNA |
|---|---:|---:|---:|---:|---:|---:|
| `full_dsc_guard` | yes | yes | yes | yes | yes | yes |
| `without_log_semantics_abi_only` | no | no | no | no | no | no |
| `topic_only_raw_filter` | no | no | no | no | no | no |
| `oracle_boundary_without_lending_binding` | no | no | no | no | no | no |
| `impact_only_without_oracle_boundary` | no | no | no | no | no | no |

## Notes

- attack_alert_case_recall counts any verifier alert; replayable_case_recall requires an attacker-localization alert on an impact transaction.
- Strict attack FP counts confirmed replayable attack alerts over strict benign rows.
- Benign warning rate counts non-replayable warning/review volume over all materialized benign rows.
- Topic-only and ABI-only are intentionally read-only observation baselines; they cannot replay oracle-consumption constraints without semantic bindings.
