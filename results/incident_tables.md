# Oracle Misconfiguration Incident Tables

## Scope

- Times are UTC.
- `attack_txs` separates core exploit transactions from lifecycle transactions.
- `boundary_logs` contains config, stale, cap, repair, and recovery boundary records; those are not counted as attack transactions.

## Case Summary

| case | actors | attack txs/events | boundary logs | pre-attack logs | pre-attack logs with topics | natural window / note |
|---|---:|---:|---:|---:|---:|---|
| `venus_luna` | 12 | 217 | 3 | 3 | 3 | 2022-05-12T11:38:44Z |
| `blizz_luna` | 24 | 108 | 3 | 3 | 3 | 2022-05-12T11:39:06Z |
| `moonwell_cbeth` | 14 | 123 | 2 | 71 | 71 | 2026-02-15T19:42:05Z |
| `moonwell_wrseth` | 2 | 12 | 4 | 3 | 3 | 2025-11-04T05:44:55Z |
| `blueberry_faulty_oracle` | 2 | 1 | 5 | 56 | 56 | 2024-02-22T08:36:00Z |
| `ploutos` | 1 | 1 | 2 | 1 | 1 | 2026-02-26T05:09:11Z |

## Artifacts

- Per-case tables: `artifacts/incident_tables/<case>/{attackers,attack_txs,boundary_logs}.jsonl`
- Per-case pre-attack logs: `artifacts/incident_tables/<case>/pre_attack_logs.jsonl`
- Per-case summaries: `artifacts/incident_tables/<case>/summary.json`
- Moonwell full Dune event cache: `artifacts/moonwell_cbeth_locator/dune_full_events.jsonl`
