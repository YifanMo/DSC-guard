# Oracle Log Scope Definition

## Scope Name

`oracle_activity_log_scope`

## Definition

`oracle_activity_log_scope` is the set of receipt-backed smart-contract logs that record an oracle system's price reporting, price-source binding, price-composition configuration, governance-mediated oracle changes, or oracle proxy/deployment wiring.

The unit of analysis is a log row:

- `chain`
- `block_time`
- `tx_hash`
- `log_index`
- `contract_address`
- `topic0`
- `topics`
- `data`

This scope is intentionally broader than exploit transactions. It captures the oracle-control and oracle-reporting surface where misconfigurations become observable before downstream borrowing, liquidation, swap, or transfer activity.

## Inclusion Rules

### S1. Oracle Price Reporting Logs

Logs emitted by price feed or aggregator contracts when a new oracle answer, round, or transmission is recorded.

Examples:

- Chainlink OCR `NewTransmission`
- Chainlink `NewRound`
- Chainlink `AnswerUpdated`

This class captures stale-price and outlier-price incidents where the relevant boundary is the last or abnormal oracle answer before impact.

### S2. Feed Binding And Price Source Configuration Logs

Logs emitted when a protocol binds an asset, market, or token symbol to a price source.

Examples:

- asset-to-feed mapping updates
- `setFeed`-style wrapper configuration
- `SetTokenPriceFeed`
- `NewPriceOracle`

This class captures cases where the configured price source is the wrong feed or wrong oracle contract.

### S3. Price Composition And Route Configuration Logs

Logs emitted when an oracle wrapper, adapter, route, remapping, or conversion path is configured.

Examples:

- `SetRoute`
- `SetTimeGap`
- token remapping
- wrapper/adapter events that change how component prices are combined

This class captures cases where the source may be valid in isolation but the protocol composes, scales, or routes it incorrectly.

### S4. Governance-Executed Oracle Configuration Logs

Governance or timelock execution logs are included only when the executed target or decoded input changes oracle, feed, wrapper, adapter, or price-composition state.

Generic governance execution logs are not included by topic alone. They must be tied to an oracle target, oracle setter selector, or receipt logs from oracle contracts in the same transaction.

### S5. Oracle Proxy, Deployment, And Wiring Logs

Proxy/deployment/wiring logs are included only when the contract is on the oracle path.

Examples:

- oracle proxy initialization
- oracle proxy ownership/admin transfer
- implementation or admin wiring evidence
- deployment or constructor evidence for oracle path contracts

Generic `Initialized` or `OwnershipTransferred` logs are not included unless the contract is an oracle, oracle proxy, feed adapter, price router, or protocol price oracle.

## Exclusion Rules

The following logs are excluded from `oracle_activity_log_scope` even if they appear in incident transactions:

- ERC20 `Transfer`
- ERC20 `Approval`
- DEX `Swap`
- WETH `Deposit` / `Withdrawal`
- lending `Mint`, `Deposit`, `Borrow`, `RepayBorrow`, `LiquidateBorrow`
- market entry/collateral enablement
- protocol-specific accounting events
- flashloan logs

These logs belong to `impact_log_scope`, not `oracle_activity_log_scope`. They are useful for proving exploitation or loss, but they do not define the oracle research surface.

## Case Coverage

All active oracle-misconfiguration cases have pre-attack boundary evidence inside `oracle_activity_log_scope`.

| case | chain | scope class | boundary evidence |
|---|---|---|---|
| `venus_luna` | BNB | S1 oracle price reporting | LUNA/USD feed `NewTransmission`, `NewRound`, `AnswerUpdated` before stale collateral borrowing |
| `blizz_luna` | Avalanche | S1 oracle price reporting | LUNA/USD feed `NewTransmission`, `NewRound`, `AnswerUpdated` before stale collateral borrowing |
| `moonwell_wrseth` | Base | S1 oracle price reporting | wrsETH/ETH aggregator abnormal update at `2025-11-04T05:44:55Z` |
| `moonwell_cbeth` | Base | S2/S3/S4 oracle configuration | governance execution and oracle wrapper/feed-composition configuration logs |
| `blueberry_faulty_oracle` | Ethereum | S2/S3/S5 oracle path wiring | oracle proxy/core route configuration logs such as `SetRoute`, `SetTokenPriceFeed`, `SetTimeGap` |
| `ploutos` | Ethereum | S2 feed binding | USDC feed binding changed to the wrong price source |

## Paper Framing

The story is:

1. Oracle-dependent protocols expose a broad on-chain activity surface where prices are reported, feeds are bound, routes are configured, and oracle contracts are wired through governance and proxies.
2. This surface is large and increasingly common across chains, making oracle-log analysis a meaningful research target rather than a narrow exploit-specific artifact.
3. Every real incident in our active oracle-misconfiguration dataset has pre-attack boundary evidence inside this independently defined oracle activity surface.
4. DSC-Guard operates on this broad surface and applies semantic checks for feed identity, price composition, freshness, and oracle implementation/decimal semantics.
5. The tool then connects oracle-scope anomalies to downstream impact logs, demonstrating practical utility on real incidents.

## Recommended Metrics

For the broad-scope section of the paper, report at least:

- yearly `oracle_activity_log_scope` log count
- yearly unique oracle-related contracts
- yearly unique transactions emitting oracle-scope logs
- per-chain split
- normalized rate per million total smart-contract logs

The normalized rate is important because raw counts can increase simply because total chain activity increases.

## Relationship To Other Scopes

`oracle_activity_log_scope`:

- research object
- used to show oracle activity is broad and important
- contains pre-attack oracle boundary evidence for all active cases

`impact_log_scope`:

- downstream borrowing, liquidation, transfer, swap, and flashloan evidence
- used to prove exploitation and loss
- not used to define oracle activity

`case_coverage_scope`:

- union of oracle activity logs and selected impact logs
- used to show that broad oracle logs can be linked to concrete real-world incidents
