# Benign Candidate Count-Only Summary

This is a Dune aggregate count-only run for the current case-aware benign sampling logic. It does not download full logs or receipts.

| case | sample source | candidate log rows | tx count | status |
|---|---|---:|---:|---|
| ploutos | case_topic | 62 | 62 | exact_count_only_dune_completed |
| moonwell_cbeth | case_topic | 1,687,292 | 1,689,802 | exact_count_only_dune_completed |
| moonwell_wrseth | same_oracle | 677 | 677 | exact_count_only_dune_completed |
| blueberry_faulty_oracle | case_topic | 38 | 34 | exact_count_only_dune_completed |
| venus_luna | same_oracle_estimated_from_hash_bucket | 5,376 | 5,376 | estimated_due_bnb_dune_shard_pending_cancelled |
| blizz_luna | same_oracle | 18,500 | 18,120 | exact_count_only_dune_completed |

Total estimated candidate log rows under sample-source logic: `1,711,945`.

Broad fallback counts can be much larger for freshness cases; see `summary_final.json`.
