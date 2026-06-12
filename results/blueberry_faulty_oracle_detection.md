# Blueberry Protocol faulty oracle deployment

- Case: `blueberry_faulty_oracle`
- Chain: `ethereum`
- Input records: `2`
- Alerts: `2`

## Key Transactions

- canonical_attack: `0xf0464b01d962f714eee9d4392b2494524d0e10ce3eb3723873afd1346b8b06e4`
- attacker_eoa: `0xC0ffeEBABE5D496B2DDE509f9fa189C25cF29671`
- attacker_contract: `0x3AA228a80F50763045BDfc45012dA124Bd0a6809`

## Alerts

- `BLUEBERRY_MONEY_MARKET_MUST_USE_NORMALIZED_ORACLE_SEMANTICS` (decimal_semantics_mismatch, critical) at block `0`, tx ``
  - asset=WETH, expected_oracle=PriceOracleProxy, actual_oracle=CoreOracle, expected_semantics=Money Market should consume normalized collateral and borrow-asset USD prices through the proxy., actual_semantics=Money Market consumed CoreOracle 18-decimal scaled prices directly, underpricing OHM/USDC/WBTC borrow assets versus WETH collateral., block_timestamp=1708590960, reason=faulty oracle implementation/decimal semantics deployment
- `BORROW_AFTER_ORACLE_VIOLATION` (attacker_localization, critical) at block `0`, tx `0xf0464b01d962f714eee9d4392b2494524d0e10ce3eb3723873afd1346b8b06e4`
  - borrower=0x3aa228a80f50763045bdfc45012da124bd0a6809, collateral_asset=WETH, borrow_asset=OHM+USDC+WBTC, borrow_amount=8616.071267266 OHM; 913262.603416 USDC; 6.866901 WBTC, reasons=['decimal_semantics_mismatch']

## Attacker Candidates

- `0x3aa228a80f50763045bdfc45012da124bd0a6809` roles=['borrower'] txs=`0xf0464b01d962f714eee9d4392b2494524d0e10ce3eb3723873afd1346b8b06e4`
  - borrowed 8616.071267266 OHM; 913262.603416 USDC; 6.866901 WBTC OHM+USDC+WBTC against WETH
- `0xc0ffeebabe5d496b2dde509f9fa189c25cf29671` roles=['actor'] txs=`0xf0464b01d962f714eee9d4392b2494524d0e10ce3eb3723873afd1346b8b06e4`
  - borrowed 8616.071267266 OHM; 913262.603416 USDC; 6.866901 WBTC OHM+USDC+WBTC against WETH
