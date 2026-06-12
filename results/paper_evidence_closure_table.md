# Evidence Closure Table

| case | has_trigger | has_oracle_anomaly | has_lending_impact | has_actor | has_temporal_order | has_replayable_constraint | raw_receipt_present | transfer_flow_count | pre_attack_log_count | pre_attack_topic_log_count | pre_attack_topic_coverage | has_pre_attack_topics | evidence_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ploutos | True | True | True | True | True | True | True | 6 | 1 | 1 | 1/1 | True | real_tx_with_receipt_flow_decode |
| moonwell_cbeth | True | True | True | True | True | True | True | 145 | 71 | 71 | 71/71 | True | real_materialized |
| moonwell_wrseth | True | True | True | True | True | True | False | 0 | 3 | 3 | 3/3 | True | real_materialized |
| blueberry_faulty_oracle | True | True | True | True | True | True | False | 0 | 56 | 56 | 56/56 | True | real_materialized |
| venus_luna | True | True | True | True | True | True | False | 0 | 3 | 3 | 3/3 | True | real_materialized |
| blizz_luna | True | True | True | True | True | True | False | 0 | 3 | 3 | 3/3 | True | real_materialized |
