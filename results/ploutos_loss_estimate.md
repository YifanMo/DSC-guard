# Ploutos Money USDC oracle misconfiguration Loss / Impact Estimate

## Scope

- Input: local historical receipt evidence only.
- No RPC, Dune, explorer API, write call, private key, or transaction simulation is used.
- The estimate is evidence-scoped; it does not fabricate protocol amounts when protocol events are unavailable.

## Estimate

- Confidence: `receipt_flow_estimated`
- Estimation scope: `largest_known_token_flow_in_exploit_receipt_not_protocol_loss`
- Primary amount: `187.366746326704993556 WETH`
- Known USD estimate: `not_priced`
- Unknown/internal flow count: `2`
- Exploit tx: `0xa17dc37e1b65c65d20042212fb834974f7faaa961442e3fc05393778705f8474`
- Attacker candidate: `0x3885869b0f4526806b468a0c64a89bb860a18cee`

## Notes

- No standard Compound-style Borrow event was decoded in the exploit receipt.
- This is an observable receipt-flow impact estimate, not a protocol-level loss amount.
- Mint/burn, AMM swap, and unknown/internal token flows are not counted as protocol loss.

## Decoded Protocol Events

- No standard Compound-style Borrow event decoded.

## Observable Transfer Flow

- log `0` known_token_flow: 8.879192 USDC from `0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc` to `0x3e47945cca05439f99029a3d21e3166ce1a84fab`
- log `4` known_token_flow: 8.879192 USDC from `0x3e47945cca05439f99029a3d21e3166ce1a84fab` to `0x95bd113164b304dabf1fc940da2298dd45ca92fd`
- log `5` mint_or_burn: 8879192 UNKNOWN from `0x0000000000000000000000000000000000000000` to `0x3e47945cca05439f99029a3d21e3166ce1a84fab`
- log `9` mint_or_burn: 187366746326704993556 UNKNOWN from `0x0000000000000000000000000000000000000000` to `0x3e47945cca05439f99029a3d21e3166ce1a84fab`
- log `12` known_token_flow: 187.366746326704993556 WETH from `0xd060ebd4f56be8866376a3616b6e5aef87f945d2` to `0x3e47945cca05439f99029a3d21e3166ce1a84fab`
- log `14` known_token_flow: 0.004289216474598283 WETH from `0x3e47945cca05439f99029a3d21e3166ce1a84fab` to `0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc`
