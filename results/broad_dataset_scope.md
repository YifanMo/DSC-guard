# Broad Search Dataset v1 Scope

The broad-search dataset has two layers:

1. `index_level_candidate_dataset`: compact candidate rows exported from remote index systems such as Dune. These rows summarize historical oracle-consumption evidence without downloading raw receipts or full logs locally.
2. `seed_evaluation_dataset`: the 6 active seed cases that are already materialized locally and used to evaluate the rule families.
3. `local_semantic_validation_dataset`: local evidence slices materialized for new broad-search candidates that pass the `A_replayable` or logically eligible `B_high_confidence_incomplete` gates.

The scope remains historical EVM lending price-oracle consumption failures:

- feed-binding failures;
- price-composition failures;
- freshness-handling failures.

The broad layer is intended to support coverage claims over a wider candidate surface by chain, year, failure class, and evidence tier. It is not a full-chain raw log mirror.

Default chain scope is the validated seed-chain scope:

- Ethereum: Ploutos and Blueberry faulty oracle deployment.
- Base: Moonwell cbETH and Moonwell wrsETH.
- BNB Chain: Venus LUNA.
- Avalanche: Blizz LUNA.

This keeps the broad-search dataset cross-chain while avoiding the cost of default scans over chains that are not represented by the validated MVP evidence set. Additional EVM chains can still be passed explicitly with `--chains`.

## Cost Control

Remote index queries do the wide scan. Local downloads are bounded by the materialization queue. The queue is not capped by top-k, weighted scores, or largest-amount ordering:

- `A_replayable` candidates are eligible by default.
- `B_high_confidence_incomplete` candidates are eligible only when lending impact, temporal order, source quality, and impact transaction count are sufficient.
- `C_remote_anomaly_only` remains remote-only unless manually promoted after additional historical evidence appears.

If the gate-selected queue is too large, the experiment tightens semantic predicates and reruns count-only preflight instead of truncating accepted candidates.

Default per-candidate caps:

| failure_class | trigger receipts | impact receipts | ABI/source requests |
|---|---:|---:|---:|
| feed_binding_failure | 1 | 1 | 2 |
| price_composition_failure | 1 | 2 | 3 |
| freshness_handling_failure | 1 | 2 | 2 |

Seed/evaluation rows have `already_materialized=true` and do not enter the download queue.

`scripts/materialize_broad_queue.py` is dry-run by default. It reports estimated request counts and only performs bounded historical receipt downloads when `--allow-rpc-fill --execute` is explicitly provided.

`scripts/run_broad_dune_queries.py` executes the remote index layer by staged inventory-first shards. Use `--dry-run` for SQL/manifests only, and use `--resume` for paid runs so completed shards are not charged twice. The intended order is calibration, pilot, then full.

## Safety Boundary

This dataset construction is read-only historical forensics. It does not send transactions, call write methods, handle private keys, perform open-ended `eth_getLogs` scans from local RPC, simulate attacks, or predict future targets.
