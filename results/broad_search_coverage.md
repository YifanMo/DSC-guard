# Broad Search Coverage

This report summarizes remote index-level broad-search candidates imported from Dune-style exports. It does not imply that all raw logs or receipts were downloaded locally.

- Candidate count: `5`
- Seed evaluation count: `6`
- Remote candidate count: `5`
- Materialization queue count: `3`
- Estimated queue receipt bundles: `8`
- Estimated queue RPC requests: `24`
- Estimated queue ABI requests: `7`

## By Chain / Year / Class / Tier

| chain | year | failure_class | evidence_tier | candidate_count |
|---|---:|---|---|---:|
| avalanche | 2022 | freshness_handling_failure | A_replayable | 1 |
| base | 2024 | price_composition_failure | B_high_confidence_incomplete | 1 |
| bsc | 2022 | freshness_handling_failure | C_remote_anomaly_only | 1 |
| ethereum | 2024 | feed_binding_failure | A_replayable | 1 |
| scroll | 2024 | feed_binding_failure | B_high_confidence_incomplete | 1 |

## By Failure Class / Tier

| failure_class | evidence_tier | candidate_count |
|---|---|---:|
| feed_binding_failure | A_replayable | 1 |
| feed_binding_failure | B_high_confidence_incomplete | 1 |
| freshness_handling_failure | A_replayable | 1 |
| freshness_handling_failure | C_remote_anomaly_only | 1 |
| price_composition_failure | B_high_confidence_incomplete | 1 |

## By Source Quality

| source_quality | candidate_count |
|---|---:|
| decoded_protocol_event | 3 |
| oracle_feed_only | 1 |
| raw_transfer_heuristic | 1 |
