# Broad Dataset Table

| dataset_layer | seed_set_size | remote_candidate_count | local_materialization_queue_count | validated_local_case_count | materialization_rate | estimated_rpc_requests | estimated_abi_requests | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| index_level_candidate_dataset | 6 | 5 | 3 | 6 | 60.00% | 24 | 7 | Seed cases are already materialized; remote candidates are compact index rows and only the queue is eligible for local receipt materialization. |
| feed_binding_failure |  | 2 | 1 |  | 50.00% |  |  | Per-class remote candidate coverage and local materialization eligibility. |
| freshness_handling_failure |  | 2 | 1 |  | 50.00% |  |  | Per-class remote candidate coverage and local materialization eligibility. |
| price_composition_failure |  | 1 | 1 |  | 100.00% |  |  | Per-class remote candidate coverage and local materialization eligibility. |
