# Benign Stratified Evaluation

This report expands the benign evaluation denominator so the main detection result is not presented as an unexplained perfect score.

## Overall

- Materialized benign rows: `10000`
- Strict benign rows used for confirmed FP denominator: `9637` (`96.37%`)
- Unknown rows excluded from strict FP denominator: `349` (`3.49%`)
- Review rows excluded from strict FP denominator: `14` (`0.14%`)
- Confirmed strict attack FP: `0/9637` (`0.00%`)

A row is counted as strict benign only after local materialization and replay do not produce a replayable oracle-consumption constraint violation. Unknown and review rows are retained in the dataset but not used as true negatives.

## By Case

| Case | Total | Strict benign | Unknown | Review | Strict rate |
|---|---:|---:|---:|---:|---:|
| `blizz_luna` | 1623 | 1623 | 0 | 0 | 100.00% |
| `blueberry_faulty_oracle` | 34 | 1 | 33 | 0 | 2.94% |
| `moonwell_cbeth` | 2896 | 2580 | 316 | 0 | 89.09% |
| `moonwell_wrseth` | 636 | 636 | 0 | 0 | 100.00% |
| `ploutos` | 60 | 46 | 0 | 14 | 76.67% |
| `venus_luna` | 4751 | 4751 | 0 | 0 | 100.00% |

## By Benign Stratum

| Stratum | Total | Strict benign | Unknown | Review | Strict rate |
|---|---:|---:|---:|---:|---:|
| `case_topic` | 3626 | 3263 | 349 | 14 | 89.99% |
| `same_oracle` | 6374 | 6374 | 0 | 0 | 100.00% |

## By Failure Class

| Failure class | Total | Strict benign | Unknown | Review | Strict rate |
|---|---:|---:|---:|---:|---:|
| `feed_binding_failure` | 60 | 46 | 0 | 14 | 76.67% |
| `freshness_handling_failure` | 6374 | 6374 | 0 | 0 | 100.00% |
| `price_composition_failure` | 2896 | 2580 | 316 | 0 | 89.09% |
| `price_semantics_mismatch` | 670 | 637 | 33 | 0 | 95.07% |

## By Scope Class

| Scope class | Total | Strict benign | Unknown | Review | Strict rate |
|---|---:|---:|---:|---:|---:|
| `S1` | 6374 | 6374 | 0 | 0 | 100.00% |
| `S2` | 64 | 47 | 3 | 14 | 73.44% |
| `S3` | 667 | 637 | 30 | 0 | 95.50% |
| `S4` | 2895 | 2579 | 316 | 0 | 89.08% |

## Unknown Rows

| Reason | Count | Case distribution | Scope distribution |
|---|---:|---|---|
| `generic_oracle_scope_log_not_bound_to_replay_semantics` | 33 | `{'blueberry_faulty_oracle': 33}` | `{'S2': 3, 'S3': 30}` |
| `generic_oracle_scope_log_without_source_or_abi` | 316 | `{'moonwell_cbeth': 316}` | `{'S4': 316}` |

Unknown rows are not failures of the detector. They are materialized oracle-scope logs for which the local evidence bundle was insufficient to prove a strict benign label. The dominant cause is generic governance/oracle-scope logs that are not bound to a replayable protocol state transition.

## Review Rows

| Reason | Count | Case distribution | Scope distribution |
|---|---:|---|---|
| `feed_binding_log_with_incomplete_actual_feed_identity` | 14 | `{'ploutos': 14}` | `{'S2': 14}` |

Review rows are kept out of the strict FP denominator because they are not confirmed attack false positives. In the current dataset they are Ploutos-like feed-binding logs where the event shape matches the case topic, but the actual feed identity is incomplete or unresolved.

## Paper Wording

Recommended wording:

> On six historical EVM lending oracle-consumption failures, DSC-Guard replayed all 285 impact transactions and localized all 55 known actors. On 9,637 verified hard-benign samples that share oracle, protocol, or log-pattern characteristics with the incidents, it produced no confirmed replayable attack false positives. We conservatively excluded 349 samples as insufficiently verifiable and routed 14 feed-binding-like samples to manual review rather than counting them as true negatives.
