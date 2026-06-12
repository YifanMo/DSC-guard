# Moonwell wrsETH oracle malfunction

- Case: `moonwell_wrseth`
- Chain: `base`
- Input records: `13`
- Alerts: `13`

## Key Transactions

- first_attack: `0x229caeb87e0b6c31afad950150d2ba05a8d7fe823c9e5c05af63b4150b8f6cc6`
- attacker_contract: `0x42ecd332d47c91cbc83b39bd7f53cebe5e9734bb`
- attacker_eoa: `0x6997a8c804642ae2de16d7b8ff09565a5d5658ff`

## Alerts

- `WRSETH_ETH_SOURCE_MUST_NOT_OUTLIER` (price_source_outlier, critical) at block `0`, tx ``
  - asset=wrsETH, feed=0xd7221b10fbbc1e1ba95fd0b4d031c15f7f365296, quote_asset=ETH, reported_rate=1649934.60732, block_timestamp=1762235095, reason=wrsETH/ETH source reported an abnormal outlier value
- `BORROW_AFTER_ORACLE_VIOLATION` (attacker_localization, critical) at block `0`, tx `0x229caeb87e0b6c31afad950150d2ba05a8d7fe823c9e5c05af63b4150b8f6cc6`
  - borrower=0x42ecd332d47c91cbc83b39bd7f53cebe5e9734bb, collateral_asset=wrsETH, borrow_asset=cbXRP, borrow_amount=1206000, reasons=['price_source_outlier']
- `BORROW_AFTER_ORACLE_VIOLATION` (attacker_localization, critical) at block `0`, tx `0xecb1c96e15889dc11d2928f6e63e34abcb8b1114bd69f15a794fa4df07f647aa`
  - borrower=0x42ecd332d47c91cbc83b39bd7f53cebe5e9734bb, collateral_asset=wrsETH, borrow_asset=EURC, borrow_amount=80000, reasons=['price_source_outlier']
- `BORROW_AFTER_ORACLE_VIOLATION` (attacker_localization, critical) at block `0`, tx `0x7855a861bb27ba93aac37ec60e2de3381c46f82070dc4d300aca70ee05cc69ec`
  - borrower=0x42ecd332d47c91cbc83b39bd7f53cebe5e9734bb, collateral_asset=wrsETH, borrow_asset=EURC, borrow_amount=73300, reasons=['price_source_outlier']
- `BORROW_AFTER_ORACLE_VIOLATION` (attacker_localization, critical) at block `0`, tx `0xc5daf8bfea0b7f6c5da8e4b08e19df2be58094a366aa2387e9b9443fb0e0c0d4`
  - borrower=0x42ecd332d47c91cbc83b39bd7f53cebe5e9734bb, collateral_asset=wrsETH, borrow_asset=USDC, borrow_amount=80000, reasons=['price_source_outlier']
- `BORROW_AFTER_ORACLE_VIOLATION` (attacker_localization, critical) at block `0`, tx `0xa5f60967fc6ad8c0f5b82f1a12970371333c16d8dddee5cd3a4f8a95561769fd`
  - borrower=0x42ecd332d47c91cbc83b39bd7f53cebe5e9734bb, collateral_asset=wrsETH, borrow_asset=AERO, borrow_amount=101000, reasons=['price_source_outlier']
- `BORROW_AFTER_ORACLE_VIOLATION` (attacker_localization, critical) at block `0`, tx `0x815715adbf5032d1b968d5fda6c3589d2f4d3ab0b7a12c42f7f6a3cddbf99ff9`
  - borrower=0x42ecd332d47c91cbc83b39bd7f53cebe5e9734bb, collateral_asset=wrsETH, borrow_asset=AERO, borrow_amount=101000, reasons=['price_source_outlier']
- `BORROW_AFTER_ORACLE_VIOLATION` (attacker_localization, critical) at block `0`, tx `0x190a491c0ef095d5447d6d813dc8e2ec11a5710e189771c24527393a2beb05ac`
  - borrower=0x42ecd332d47c91cbc83b39bd7f53cebe5e9734bb, collateral_asset=wrsETH, borrow_asset=wstETH, borrow_amount=21, reasons=['price_source_outlier']
- `BORROW_AFTER_ORACLE_VIOLATION` (attacker_localization, critical) at block `0`, tx `0xff3075de35647efed753a918d20a92d9113e14a86a6dc98064b94249d14a54c1`
  - borrower=0x42ecd332d47c91cbc83b39bd7f53cebe5e9734bb, collateral_asset=wrsETH, borrow_asset=wstETH, borrow_amount=20.5, reasons=['price_source_outlier']
- `BORROW_AFTER_ORACLE_VIOLATION` (attacker_localization, critical) at block `0`, tx `0x76911abc581204db6063763b024de0bf7bb1bbb62f61dc81be3bac4bc9e474b2`
  - borrower=0x42ecd332d47c91cbc83b39bd7f53cebe5e9734bb, collateral_asset=wrsETH, borrow_asset=wstETH, borrow_amount=20.5, reasons=['price_source_outlier']
- `BORROW_AFTER_ORACLE_VIOLATION` (attacker_localization, critical) at block `0`, tx `0x5cd5b182e8be9e13360970d851f2479376f9de30f9f07dda617e6deba5e72ca4`
  - borrower=0x42ecd332d47c91cbc83b39bd7f53cebe5e9734bb, collateral_asset=wrsETH, borrow_asset=wstETH, borrow_amount=20, reasons=['price_source_outlier']
- `BORROW_AFTER_ORACLE_VIOLATION` (attacker_localization, critical) at block `0`, tx `0xd74224baa38bb6872769d43469aea69f45683281ca475c658338f2c08e5f412d`
  - borrower=0x42ecd332d47c91cbc83b39bd7f53cebe5e9734bb, collateral_asset=wrsETH, borrow_asset=cbETH, borrow_amount=24, reasons=['price_source_outlier']
- `BORROW_AFTER_ORACLE_VIOLATION` (attacker_localization, critical) at block `0`, tx `0x26abab9dd1119f13ba4899cea1d5875e3c5286427732a4eb7143aa44485cf6e0`
  - borrower=0x42ecd332d47c91cbc83b39bd7f53cebe5e9734bb, collateral_asset=wrsETH, borrow_asset=cbETH, borrow_amount=24, reasons=['price_source_outlier']

## Attacker Candidates

- `0x42ecd332d47c91cbc83b39bd7f53cebe5e9734bb` roles=['borrower'] txs=`0x190a491c0ef095d5447d6d813dc8e2ec11a5710e189771c24527393a2beb05ac`, `0x229caeb87e0b6c31afad950150d2ba05a8d7fe823c9e5c05af63b4150b8f6cc6`, `0x26abab9dd1119f13ba4899cea1d5875e3c5286427732a4eb7143aa44485cf6e0`, `0x5cd5b182e8be9e13360970d851f2479376f9de30f9f07dda617e6deba5e72ca4`, `0x76911abc581204db6063763b024de0bf7bb1bbb62f61dc81be3bac4bc9e474b2`, `0x7855a861bb27ba93aac37ec60e2de3381c46f82070dc4d300aca70ee05cc69ec`, `0x815715adbf5032d1b968d5fda6c3589d2f4d3ab0b7a12c42f7f6a3cddbf99ff9`, `0xa5f60967fc6ad8c0f5b82f1a12970371333c16d8dddee5cd3a4f8a95561769fd`, `0xc5daf8bfea0b7f6c5da8e4b08e19df2be58094a366aa2387e9b9443fb0e0c0d4`, `0xd74224baa38bb6872769d43469aea69f45683281ca475c658338f2c08e5f412d`, `0xecb1c96e15889dc11d2928f6e63e34abcb8b1114bd69f15a794fa4df07f647aa`, `0xff3075de35647efed753a918d20a92d9113e14a86a6dc98064b94249d14a54c1`
  - borrowed 1206000 cbXRP against wrsETH
  - borrowed 80000 EURC against wrsETH
  - borrowed 73300 EURC against wrsETH
  - borrowed 80000 USDC against wrsETH
  - borrowed 101000 AERO against wrsETH
  - borrowed 101000 AERO against wrsETH
  - borrowed 21 wstETH against wrsETH
  - borrowed 20.5 wstETH against wrsETH
  - borrowed 20.5 wstETH against wrsETH
  - borrowed 20 wstETH against wrsETH
  - borrowed 24 cbETH against wrsETH
  - borrowed 24 cbETH against wrsETH
- `0x6997a8c804642ae2de16d7b8ff09565a5d5658ff` roles=['actor'] txs=`0x190a491c0ef095d5447d6d813dc8e2ec11a5710e189771c24527393a2beb05ac`, `0x229caeb87e0b6c31afad950150d2ba05a8d7fe823c9e5c05af63b4150b8f6cc6`, `0x26abab9dd1119f13ba4899cea1d5875e3c5286427732a4eb7143aa44485cf6e0`, `0x5cd5b182e8be9e13360970d851f2479376f9de30f9f07dda617e6deba5e72ca4`, `0x76911abc581204db6063763b024de0bf7bb1bbb62f61dc81be3bac4bc9e474b2`, `0x7855a861bb27ba93aac37ec60e2de3381c46f82070dc4d300aca70ee05cc69ec`, `0x815715adbf5032d1b968d5fda6c3589d2f4d3ab0b7a12c42f7f6a3cddbf99ff9`, `0xa5f60967fc6ad8c0f5b82f1a12970371333c16d8dddee5cd3a4f8a95561769fd`, `0xc5daf8bfea0b7f6c5da8e4b08e19df2be58094a366aa2387e9b9443fb0e0c0d4`, `0xd74224baa38bb6872769d43469aea69f45683281ca475c658338f2c08e5f412d`, `0xecb1c96e15889dc11d2928f6e63e34abcb8b1114bd69f15a794fa4df07f647aa`, `0xff3075de35647efed753a918d20a92d9113e14a86a6dc98064b94249d14a54c1`
  - borrowed 1206000 cbXRP against wrsETH
  - borrowed 80000 EURC against wrsETH
  - borrowed 73300 EURC against wrsETH
  - borrowed 80000 USDC against wrsETH
  - borrowed 101000 AERO against wrsETH
  - borrowed 101000 AERO against wrsETH
  - borrowed 21 wstETH against wrsETH
  - borrowed 20.5 wstETH against wrsETH
  - borrowed 20.5 wstETH against wrsETH
  - borrowed 20 wstETH against wrsETH
  - borrowed 24 cbETH against wrsETH
  - borrowed 24 cbETH against wrsETH
