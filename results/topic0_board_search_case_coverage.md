# Topic0 Board Search Case Coverage

SQL artifact:
`artifacts/broad_search/case_coverage/topic0_case_coverage.sql`

## What The Query Checks

The query seeds two receipt-backed transactions per active case:

- `pre_attack_boundary_tx`: first stored pre-attack boundary tx in `pre_attack_logs.jsonl`.
- `first_attack_tx`: first attack/lifecycle tx by on-chain order.

It joins those txs to `evms.logs`, groups receipt logs by `topic0`, maps each topic to a rule, and reports:

- `matched_topic0_count / unique_topic0_count`
- `semantic_topic0_count`
- `semantic_scope_covered`
- `matched_rules`
- `unmatched_topic0s`

`semantic_scope_covered=true` is the important case-coverage criterion. Support topics are kept so the SQL can also account for exact receipt topic coverage, but they are not treated as semantic incident boundaries.

## Coverage Interpretation

| case | pre-attack boundary rule coverage | first attack tx rule coverage | covered? |
|---|---|---|---|
| `venus_luna` | `R_PRE_CHAINLINK_ORACLE_UPDATE` | `R_IMPACT_BORROW`, `R_IMPACT_SUPPLY_OR_MINT` | yes |
| `blizz_luna` | `R_PRE_CHAINLINK_ORACLE_UPDATE` | `R_IMPACT_SUPPLY_OR_MINT`, `R_IMPACT_COLLATERAL_ENABLED` | yes |
| `moonwell_cbeth` | `R_PRE_PRICE_COMPOSITION_CONFIG`, `R_PRE_GOVERNANCE_EXECUTION` | `R_IMPACT_LIQUIDATION`, `R_IMPACT_LIQUIDATION_REPAY`, `R_IMPACT_SUPPLY_OR_MINT` | yes |
| `moonwell_wrseth` | `R_PRE_CHAINLINK_ORACLE_UPDATE` | `R_IMPACT_BORROW`, `R_IMPACT_MARKET_ENTERED`, `R_IMPACT_SUPPLY_OR_MINT` | yes |
| `blueberry_faulty_oracle` | `R_PRE_BLUEBERRY_ORACLE_PATH_CONFIG` | `R_IMPACT_BORROW`, `R_IMPACT_MARKET_ENTERED`, `R_IMPACT_SUPPLY_OR_MINT` | yes |
| `ploutos` | `R_PRE_FEED_BINDING_CONFIG` | `R_IMPACT_COLLATERAL_ENABLED` plus flow/support topics | yes, weaker on attack semantics |

## Notes

- Moonwell cbETH first attack tx is `0xa49a27498d82db8b093b2fcf969f2091f74dab437ee24ab2c43a182927335c84` by on-chain transaction index. The old representative tx `0xc400...a7ce` is in the same block but one transaction later.
- Ploutos is the weakest first-attack receipt from a pure lending-topic perspective: the receipt has strong fund-flow and collateral-enable topics, but no standard Compound `Borrow` topic in the first tx. It is still covered at the tx level because the pre-attack config topic is specific and the attack tx has lending/flow closure.
- The Chainlink topic rule covers Venus, Blizz, and Moonwell wrsETH because their first pre-attack boundary receipts all contain `NewTransmission`, `NewRound`, and `AnswerUpdated`.
- Blueberry coverage depends on oracle-path config topics (`SetRoute`, `SetTokenPriceFeed`, `SetTimeGap`), not only controller market-parameter topics.

## Validation Basis

- Pre-attack topic sets were read from local `pre_attack_logs.jsonl`.
- First attack receipt topic sets were checked via read-only RPC for the six active cases.
- The Dune SQL has not been executed in this note; it is written to be executed directly in Dune against `evms.logs`.
