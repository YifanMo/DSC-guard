# Paid Broad Search Auto-Tuning Experiment

This experiment executed paid, read-only Dune queries for the broad-search `/goal` workflow. It did not download full logs locally, send transactions, call write methods, handle private keys, simulate attacks, or predict future targets.

## What Ran

| run | purpose | result | observed credits |
|---|---|---|---:|
| `auto_tune_story_scope_paid` | initial 5-chain scope count plus yearly R1 preflight | stopped after cost signals | `411.252059` |
| `auto_tune_story_scope_paid_v2` | sharded scope count by chain/year after first adjustment | partial success; stopped at Base 2025 yearly count | `178.746482` |
| `auto_tune_story_scope_paid_v3_base2025_monthly` | Base 2025 count-only rerun by month | Jan-Oct completed; Nov hit Dune resource cap | `86.607194` |
| `auto_tune_story_scope_paid_v4_base2025_weekly_tail` | Base Nov-Dec weekly retry | blocked by Dune account datapoint limit before execution | `0` |

## Dynamic Rule Adjustments

- The initial all-chain scope count was too coarse and was cancelled at `67.343676471` credits. The scope-count stage was changed to chain/year shards.
- The initial R1 yearly Ethereum preflight was too expensive and was cancelled at `343.908382353` credits. R1 was tightened to decoded-metadata-first binding changes, so broad raw calldata scanning is not used as the entry point.
- Auto-tune now defaults to month-level rule preflight and stops scheduling after a cancelled shard.
- Scope counts now support `year`, `month`, and `week` splitting. Base 2025 showed that high-activity years require month or week splits.
- Candidate materialization remains gate-only. No top-k, weighted score, or amount-based cutoff was introduced.

## Remote Coverage Observed

Completed paid count shards currently cover Ethereum 2022-2026, Scroll 2022-2026, Base 2022-2024, and Base 2025 Jan-Oct. Across completed rows:

| chain | completed count rows | raw logs | transactions |
|---|---:|---:|---:|
| Ethereum | `5` | `5,064,239,620` | `2,044,623,813` |
| Scroll | `5` | `1,066,061,580` | `137,605,163` |
| Base | `13` | `15,373,631,405` | `4,277,856,804` |
| Total completed count rows | `23` | `21,503,932,605` | `6,460,085,780` |

BNB, Avalanche, Base 2025 Nov-Dec, and Base 2026 were not reached because the experiment stopped on Dune cost/resource/account-limit signals.

## Current Local Download Scope

Using the existing Blizz broad recall export and gate-only queue:

- Remote candidate rows: `111`
- Materialization queue rows: `111`
- Receipt/log bundles: `333`
- Estimated RPC requests: `999`
- Estimated ABI requests: `222`
- Target local bundles: `3000`
- Stricter rules required for this current queue: `False`

The current local queue already includes Blizz broad recall candidates and remains below the `3000` bundle target without top-k truncation.

## Next Safe Step

Dune returned `HTTP 402` for the weekly tail retry, meaning the account-level datapoint limit must be increased before more paid queries can be submitted. Once the Dune account limit is raised, resume with count-only weekly shards for Base 2025 Nov-Dec, then continue BNB and Avalanche scope counts before running candidate shards.
