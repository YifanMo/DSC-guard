# Dataset Evidence Audit

This audit checks whether MVP evidence is backed by historical records or still contains fixture/synthetic values.

| Case | Status | Records | Alerts | Attackers | Attack txs | Flow logs | Pre-attack logs | Topic coverage | Placeholders | Loss / coverage |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `ploutos` | `real_tx_with_receipt_flow_decode` | 4 | 3 | 1 | 1 | 6 | 1 | 1/1 | 0 | receipt_flow_estimated: largest known-token flow 187.366746326704993556 WETH |
| `moonwell_cbeth` | `real_materialized` | 124 | 124 | 14 | 123 | 145 | 71 | 71/71 | 0 | cbeth_borrowed=465.81700159946678042 |
| `moonwell_wrseth` | `real_materialized` | 13 | 13 | 2 | 12 | 0 | 3 | 3/3 | 0 | public_bad_debt_usd=3700000; canonical_attack_txs=12 |
| `blueberry_faulty_oracle` | `real_materialized` | 2 | 2 | 2 | 1 | 0 | 56 | 56/56 | 0 | reported_proceeds_eth=457; canonical_attack_txs=1 |
| `venus_luna` | `real_materialized` | 218 | 201 | 12 | 217 | 0 | 3 | 3/3 | 0 | total_borrowed_busd=11686144.73999; top_two=11411700 |
| `blizz_luna` | `real_materialized` | 109 | 88 | 24 | 108 | 0 | 3 | 3/3 | 0 | known_borrowed_usd=6305417.642606887; public_loss_usd=8280000; coverage=76.15238698800589 |

## Limitations

- `ploutos`: some protocol-specific event fields are inferred from known transactions rather than fully ABI-decoded; loss is a receipt-flow impact estimate, not a fully protocol-decoded loss amount
