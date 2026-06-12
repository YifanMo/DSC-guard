# Ploutos Money USDC oracle misconfiguration Feed-Binding Materialization

## Safety scope

- Scope: read-only historical known-transaction evidence materialization.
- RPC calls are limited to receipt, transaction, and block reads for configured `known_txs`.
- No transaction simulation, private key handling, write method, or open-ended `eth_getLogs` scan is used.

## Evidence quality

- Status: `real_tx_with_receipt_flow_decode`.
- The trigger and actor fields come from historical transactions and receipts.
- Asset/feed identity comes from the incident seed constraint; protocol-specific amounts remain `unknown` unless decoded later.
- Token transfer flow is decoded directly from ERC20 `Transfer` logs in the historical exploit receipt.

## Raw evidence closure

- Config receipt logs: `1` from historical RPC.
- Exploit receipt logs: `18` from historical RPC.
- Config tx sender/target/block: `0xfb33205d32ca482a4d428c23181a9665d4ec02cc` -> `0x9dce7a180c34203fee8ce8ca62f244feeb67bd30` at block `24538896`.
- Exploit tx sender/target/block: `0x3885869b0f4526806b468a0c64a89bb860a18cee` -> `0x3e47945cca05439f99029a3d21e3166ce1a84fab` at block `24538897`.
- Remediation boundary tx count: `1`.
- Raw evidence snapshot: `/Users/moyifan/Desktop/desktop/oracle_misconfigure/artifacts/feed_binding_locator/ploutos_raw_evidence.json`.
- Snapshot contains receipt, transaction, and block payloads only; no API keys or RPC URLs are written.

## Trigger

- Config tx: `0xcfedf63b37a6cd45b21bc94e3de5412fee0765e7dad6b7c8561a01cebd193ab6`
- Actor: `0xfb33205d32ca482a4d428c23181a9665d4ec02cc`
- Oracle/config contract: `0x9dce7a180c34203fee8ce8ca62f244feeb67bd30`
- Block: `24538896` at `2026-02-26T05:07:47Z`
- Constraint: `USDC` expected `USDC/USD`, observed incident feed `BTC/USD`

## Feed identity verification

- `forbidden_feed` `0xf4030086522a5beea4988f8ca5b36dbc97bee88c`: `BTC / USD`, decimals `8`.
- `repair_feed` `0x3e7d1eab13ad0104d2750b8863b489d65364e32d`: `USDT / USD`, decimals `8`.

## Impact

- Exploit tx: `0xa17dc37e1b65c65d20042212fb834974f7faaa961442e3fc05393778705f8474`
- Attacker candidate: `0x3885869b0f4526806b468a0c64a89bb860a18cee`
- Protocol target: `0x3e47945cca05439f99029a3d21e3166ce1a84fab`
- Block: `24538897` at `2026-02-26T05:07:59Z`
- Raw log addresses observed: `6`

## Token transfer flow

- log `0`: `protocol_inbound` 8.879192 USDC (`0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48`), from `0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc` to `0x3e47945cca05439f99029a3d21e3166ce1a84fab`
- log `4`: `protocol_outbound` 8.879192 USDC (`0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48`), from `0x3e47945cca05439f99029a3d21e3166ce1a84fab` to `0x95bd113164b304dabf1fc940da2298dd45ca92fd`
- log `5`: `protocol_inbound` 8879192 UNKNOWN (`0x95bd113164b304dabf1fc940da2298dd45ca92fd`), from `0x0000000000000000000000000000000000000000` to `0x3e47945cca05439f99029a3d21e3166ce1a84fab`
- log `9`: `protocol_inbound` 187366746326704993556 UNKNOWN (`0x9517eb3669a4f51c30bfb86fcfdb6a3ea3571b92`), from `0x0000000000000000000000000000000000000000` to `0x3e47945cca05439f99029a3d21e3166ce1a84fab`
- log `12`: `protocol_inbound` 187.366746326704993556 WETH (`0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2`), from `0xd060ebd4f56be8866376a3616b6e5aef87f945d2` to `0x3e47945cca05439f99029a3d21e3166ce1a84fab`
- log `14`: `protocol_outbound` 0.004289216474598283 WETH (`0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2`), from `0x3e47945cca05439f99029a3d21e3166ce1a84fab` to `0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc`

## Remediation boundary

- `ORACLE_FEED_REPAIRED` tx `0xee3d7556528d3ceb00681a3c7ed7be3751c83923675bc3774c77f9f4e60d20f0` at `2026-02-26T05:09:11Z` by `0xfb33205d32ca482a4d428c23181a9665d4ec02cc`, feed_after `0x3e7d1eab13ad0104d2750b8863b489d65364e32d`; status `1`.

## Artifacts

- Trace: `/Users/moyifan/Desktop/desktop/oracle_misconfigure/artifacts/log_trace/ploutos.jsonl`
- Materialized evidence: `/Users/moyifan/Desktop/desktop/oracle_misconfigure/artifacts/feed_binding_locator/ploutos_evidence.json`
- Raw evidence: `/Users/moyifan/Desktop/desktop/oracle_misconfigure/artifacts/feed_binding_locator/ploutos_raw_evidence.json`
