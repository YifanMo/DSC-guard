# Ethereum Dune Credit Estimate

This is a read-only Dune index-level estimate for the Ethereum-only Broad Search coverage runner.

## SQL Output

- Dry-run SQL directory: `artifacts/broad_search/case_coverage_ethereum_txonly_estimate/dune_shards/`
- Ethereum shards rendered: `22`
- Active Ethereum cases: `2`
  - `blueberry_faulty_oracle`
  - `ploutos`
- Ethereum canonical attack txs: `2`

## Observed Paid Runs

| shard | query type | status | credits | result |
|---|---|---:|---:|---|
| `raw_2022_ethereum` | raw count | completed | `2.677794118` | `408,543,268` tx; `758,814,854` logs; `33,564,110` unique contracts |
| `case_hit_2024_ethereum` | tx-only case hit | completed | `0.750735295` | Blueberry attack tx found in Dune transactions |
| `case_hit_2024_ethereum` | old detailed case hit | completed | `18.080147059` | Obsolete: joined logs/traces/transfers |
| `case_hit_2024_ethereum` | exact-date detailed case hit | cancelled | `144.0025` | Obsolete: still too expensive |

## Estimate

- Raw Ethereum yearly coverage counts: about `13-25` credits for 2022-2026.
  - Baseline: `2.68` credits for 2022 multiplied by five yearly shards is `13.4`.
  - Use `25` as a safer upper estimate because later years may have more indexed rows.
- Transaction-only case-hit validation: about `1.5-3` credits for the two Ethereum case-year shards.
  - Baseline: `0.75` credits for one attack-tx year shard.
- Current detailed case-hit SQL must not be used for full runs.
  - It makes the query join logs/traces/transfers and can jump above `100` credits even for one known attack tx.
- Rule-suspicious yearly counts are not yet cost-estimated.
  - Treat them as high/unknown until each rule has its own bounded smoke run.
  - Do not run all Ethereum rule-count shards without an explicit budget guard.

## Recommended Ethereum First Run

Use transaction-only case-hit plus raw yearly counts first:

```bash
python scripts/run_case_coverage_broad_search.py \
  --chains ethereum \
  --query-types raw_count,case_hit \
  --execute-dune \
  --resume \
  --performance medium \
  --max-execution-credits 10 \
  --max-total-credits 40 \
  --output-dir artifacts/broad_search/case_coverage_ethereum_txonly_estimate
```

This should be enough for the first paper claim:

> Ethereum alone contains hundreds of millions of yearly transactions and logs in the Broad Search scope, and the known Ethereum seed attack transactions are present in the remote Dune index-level coverage layer.

## Safety Boundary

- No receipt download.
- No RPC fallback.
- No chain writes, write-method calls, private keys, attack simulation, or future-target prediction.
