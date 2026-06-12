# Blizz Broad Search Recall

This report records the read-only historical Broad Search calibration for recalling the Blizz LUNA freshness-handling incident without using Blizz transaction hashes, known attacker addresses, or protocol-specific search filters.

## R3 Rule

- Rule: `freshness_handling_failure`
- Query style: impact-led lower-bound stale closure
- Chain: `avalanche_c`
- Window: `2022-05-01` to `2022-05-31`
- Output directory: `artifacts/broad_search/single_chain/avalanche_2022_20260512/dune_r3_blizz_recall`
- Dune execution id: `01KRJPB04JQ24H73787BXDSYVB`
- Status: `completed`
- Credits: `16.117794118`
- Raw candidate rows: `115`
- Normalized remote candidates: `111`
- Evidence tier: all normalized candidates are `B_high_confidence_incomplete`
- Source quality: `impact_led_lower_bound_unresolved`

## Recall Evidence

The broad query recovered Blizz-like candidates through a generic lending-market pattern:

- Collateral asset: `LUNA`
- Protocol labels in the returned rows include `Blizz LUNA`, `Blizz WBTC`, `Blizz WETH`, and `Blizz LINK`.
- Candidate rows share the closure reason: lower-bound stale marker and same-account lending impact are present, while feed identity metadata remains incomplete.
- The broad rows overlap the locally materialized Blizz evidence: `52` broad rows share at least one supply or borrow transaction with `artifacts/blizz_luna_locator/dune_candidates_full.jsonl`.
- Matched broad rows cover about `$7.0419M` known borrowed USD, using Dune `amount_usd` where available.

Representative broad recall row:

- Trigger tx: `0x1bec6d78641099ceb20fb36ab32edaa089569cef8b507a7c79743cf4e5fd2ae5`
- Impact txs: `0x9aeee69ae27b420420808a6830ce9eefb13a46a8b35f5b7cb4c5b922e94402ee;0x3e5e20303b58e62f641915776d3355638788835d4aabcfe7d14937d61a875043`
- Known impact USD: `$4,460,422.266643567`
- Affected asset: `LUNA`
- Evidence tier: `B_high_confidence_incomplete`

## Local Download Plan

The ingested queue is stored at `artifacts/broad_search/materialization_queue.jsonl`.

- Queue candidates: `111`
- Max evidence bundle per candidate: `1` stale-marker receipt + `1` supply receipt + `1` borrow receipt
- Dry-run selected candidates: `111`
- Estimated receipt bundles: `333`
- Estimated RPC calls: `999`
- Estimated ABI requests: `222`

Seed/evaluation cases remain separate and are not re-downloaded.

## Limitations

The broad R3 recall intentionally keeps these rows in B tier, not A tier. The remote query proves a historical lower-bound marker plus same-account lending impact, but does not claim the feed identity is fully resolved from Dune labels. The local Blizz evidence and `verify_trace.py --case blizz_luna` provide the replayable semantic validation for the paper story.
