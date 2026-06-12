# Moonwell cbETH Full Trace Materialization

## Safety scope

- Scope: read-only historical reconstruction for the Moonwell cbETH / MIP-X43 oracle-consumption incident.
- Default offline mode uses local Dune decoded artifacts only.
- Optional RPC fill is limited to receipt, transaction, and block reads for already-known historical tx hashes.
- No transaction construction, private keys, write calls, simulations, or open-ended `eth_getLogs` scans are used.

## Evidence quality

- Status markers: `dune_decoded_event`, `receipt_flow_decoded`, `rpc_receipt_backed`.
- Raw receipt-backed tx count: `16`.
- Decoded ERC20 transfer flow count: `145`.
- Borrow amounts come from Dune decoded Moonwell event aggregates; per-tx amounts remain `unknown` when the local aggregate does not provide them.

## Trigger closure

- MIP-X43 execution tx: `0xd26baf29dcba7bf66db4be17b46a49bb4dacca41ace968c98c8a5b09a03ae812`.
- Temporal governor: `0x84eaf5e855514685927b75876e0c9798895c249a`.
- Oracle target: `0xec942be8a8114bfd0396a5052c36027f2ca6a9d0`.
- Selector: `0x0c607acf` / `setFeed(string,address)`.
- Formula mismatch: expected `cbETH/ETH * ETH/USD`, actual `cbETH/ETH`.

## Impact closure

- Liquidation records: `109`.
- Borrower candidates: `3`.
- Borrow txs materialized: `14`.
- Total decoded cbETH borrowed: `465.81700159946678042`.

## Full Dune event rescan

- Full decoded event rows: `124`.
- Unique impact txs: `123`.
- cbETH-collateral liquidation events: `109`.
- Dune-observed affected borrowers: `81` vs public affected borrowers `181`.
- Public seized cbETH benchmark: `1096.317`; public bad debt benchmark USD `1780000`.
- Residual gap: the public affected-borrower count is larger than the Dune liquidation/borrow event closure; keep this gap explicit instead of treating the 124 decoded rows as the complete public impact set.

## Raw receipt closure

- Raw evidence artifact mode: `rpc`.
- Raw tx snapshots saved: `16`.
- Snapshot stores receipt, transaction, and block payloads only; API keys and RPC URLs are not written.

## Artifacts

- Trace: `artifacts/log_trace/moonwell_cbeth.jsonl`
- Materialized evidence: `artifacts/moonwell_cbeth_locator/moonwell_evidence.json`
- Raw evidence: `artifacts/moonwell_cbeth_locator/raw_evidence.json`
- Detection report: `results/moonwell_cbeth_detection.md`
