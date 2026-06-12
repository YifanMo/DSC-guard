# Broad Search Case Coverage

This report is an index-level Dune coverage artifact. It counts remote historical rows and validates known attack transactions without downloading bulk receipts or logs locally.

## Run

- Dry run: `True`
- Execute Dune: `False`
- Output directory: `/var/folders/gl/7_7qr96n1y9709c_l9wjxmbr0000gn/T/tmpq7geb0y6`
- Shards: `3`
- Completed: `0`
- Failed: `0`
- Skipped after submit error: `0`
- Observed credits: `0.0`

## Case Manifest

- Active cases: `6`
- Canonical attack transactions: `462`
- Chains: `avalanche, base, bsc, ethereum`

| case | chain | broad class | attack txs |
|---|---|---|---:|
| `ploutos` | `ethereum` | `feed_binding_failure` | `1` |
| `moonwell_cbeth` | `base` | `price_composition_failure` | `123` |
| `moonwell_wrseth` | `base` | `price_composition_failure` | `12` |
| `blueberry_faulty_oracle` | `ethereum` | `price_composition_failure` | `1` |
| `venus_luna` | `bsc` | `freshness_handling_failure` | `217` |
| `blizz_luna` | `avalanche` | `freshness_handling_failure` | `108` |

## Yearly Raw Counts

_No Dune raw-count results are present yet. Run with `--execute-dune` to populate this section._

## Rule-Suspicious Counts

_No Dune rule-count results are present yet. Run with `--execute-dune` to populate this section._

## Case-Hit Validation

- All attack txs found in Dune raw tx layer: `False`
- All cases have representative rule match: `False`

| case | expected txs | found in Dune | rule matched | raw complete | representative rule match |
|---|---:|---:|---:|---|---|
| `blizz_luna` | 108 | 0 | 0 | `False` | `False` |
| `blueberry_faulty_oracle` | 1 | 0 | 0 | `False` | `False` |
| `moonwell_cbeth` | 123 | 0 | 0 | `False` | `False` |
| `moonwell_wrseth` | 12 | 0 | 0 | `False` | `False` |
| `ploutos` | 1 | 0 | 0 | `False` | `False` |
| `venus_luna` | 217 | 0 | 0 | `False` | `False` |

## Safety Boundary

- Read-only historical Dune index queries only.
- No RPC receipt download in this runner.
- No chain writes, write-method calls, private keys, attack simulation, or future-target prediction.
