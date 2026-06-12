# Ploutos Money USDC oracle misconfiguration

- Case: `ploutos`
- Chain: `ethereum`
- Input records: `4`
- Alerts: `3`

## Key Transactions

- config: `0xcfedf63b37a6cd45b21bc94e3de5412fee0765e7dad6b7c8561a01cebd193ab6`
- exploit: `0xa17dc37e1b65c65d20042212fb834974f7faaa961442e3fc05393778705f8474`

## Alerts

- `USDC_FEED_MUST_BE_USDC_USD` (feed_mismatch, critical) at block `24538896`, tx `0xcfedf63b37a6cd45b21bc94e3de5412fee0765e7dad6b7c8561a01cebd193ab6`
  - asset=USDC, expected_feed=USDC/USD, actual_feed=BTC/USD
- `COLLATERAL_ENABLING_SUPPLY` (collateral_enabling_supply_under_bad_oracle, high) at block `24538897`, tx `0xa17dc37e1b65c65d20042212fb834974f7faaa961442e3fc05393778705f8474`
  - supplier=0x3885869b0f4526806b468a0c64a89bb860a18cee, asset=USDC, amount=unknown, reasons=['bad_oracle:first_risky_collateral_supply', 'bad_oracle:latest_topup_before_impact'], evidence_rule=first risky collateral supply or latest top-up before same-actor impact
- `BORROW_AFTER_ORACLE_VIOLATION` (attacker_localization, critical) at block `24538897`, tx `0xa17dc37e1b65c65d20042212fb834974f7faaa961442e3fc05393778705f8474`
  - borrower=0x3885869b0f4526806b468a0c64a89bb860a18cee, collateral_asset=USDC, borrow_asset=unknown, borrow_amount=unknown, reasons=['feed_mismatch']

## Attacker Candidates

- `0x3885869b0f4526806b468a0c64a89bb860a18cee` roles=['borrower'] txs=`0xa17dc37e1b65c65d20042212fb834974f7faaa961442e3fc05393778705f8474`
  - borrowed unknown unknown against USDC
