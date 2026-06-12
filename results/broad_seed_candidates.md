# Broad Search Seed Candidates

These MVP cases are fixed seed/evaluation rows. They are already materialized locally and do not enter the broad-search download queue.

- Seed evaluation count: `6`
- Already materialized: `6`
- Additional RPC requests: `0`

| candidate_id | case | chain | failure_class | evidence_tier | impact_tx_count |
|---|---|---|---|---|---:|
| seed-001-ploutos | ploutos | ethereum | feed_binding_failure | A_replayable | 1 |
| seed-002-moonwell_cbeth | moonwell_cbeth | base | price_composition_failure | A_replayable | 123 |
| seed-003-moonwell_wrseth | moonwell_wrseth | base | price_semantics_mismatch | A_replayable | 12 |
| seed-004-blueberry_faulty_oracle | blueberry_faulty_oracle | ethereum | price_semantics_mismatch | A_replayable | 1 |
| seed-005-venus_luna | venus_luna | bsc | freshness_handling_failure | A_replayable | 217 |
| seed-006-blizz_luna | blizz_luna | avalanche | freshness_handling_failure | A_replayable | 108 |
