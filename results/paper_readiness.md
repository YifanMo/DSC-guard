# Paper Readiness Snapshot

## Evidence Status

- `real_materialized`: 5 case(s)
- `real_tx_with_receipt_flow_decode`: 1 case(s)

## Current Claim Boundary

- The dataset supports a bounded study of price-oracle consumption failures in EVM lending protocols.
- The implementation should be described as Slither-derived semantic IR plus K-style replay semantics for oracle-consumption constraints.
- Fixture traces are retained for pipeline tests only and should not be described as paper evidence.

## Case Summary

- `ploutos` (feed_binding_failure): real_tx_with_receipt_flow_decode, 1 attacker candidate(s), 1 attack tx(s), 1 pre-attack log(s), receipt_flow_estimated: largest known-token flow 187.366746326704993556 WETH.
- `moonwell_cbeth` (price_composition_failure): real_materialized, 14 attacker candidate(s), 123 attack tx(s), 71 pre-attack log(s), cbeth_borrowed=465.81700159946678042.
- `moonwell_wrseth` (price_semantics_mismatch): real_materialized, 2 attacker candidate(s), 12 attack tx(s), 3 pre-attack log(s), public_bad_debt_usd=3700000; canonical_attack_txs=12.
- `blueberry_faulty_oracle` (price_semantics_mismatch): real_materialized, 2 attacker candidate(s), 1 attack tx(s), 56 pre-attack log(s), reported_proceeds_eth=457; canonical_attack_txs=1.
- `venus_luna` (freshness_handling_failure): real_materialized, 12 attacker candidate(s), 217 attack tx(s), 3 pre-attack log(s), total_borrowed_busd=11686144.73999; top_two=11411700.
- `blizz_luna` (freshness_handling_failure): real_materialized, 24 attacker candidate(s), 108 attack tx(s), 3 pre-attack log(s), known_borrowed_usd=6305417.642606887; public_loss_usd=8280000; coverage=76.15238698800589.
