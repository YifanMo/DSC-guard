# Oracle-Consumption Failure Evidence Dataset

## Dataset Scope

This dataset targets **price-oracle consumption failures in EVM lending protocols**.

We define this class as incidents where a lending protocol consumes price-oracle data with incorrect identity, transformation, or freshness semantics when computing collateral value, borrow capacity, or liquidation eligibility. The oracle data source may be external and even correctly reported; the failure lies in how the protocol binds, transforms, or validates the price before using it in lending-state transitions.

Chinese wording:

> 本数据集关注 EVM 借贷协议中的价格预言机消费失效：外部价格源可能本身正常，但协议在将价格用于抵押品估值、借款额度计算或清算判断时，因绑定、组合或时效性处理错误而产生错误状态转移。

This scope is narrower than general DeFi oracle risk and broader than Chainlink feed-log monitoring. It captures a recurring software-engineering failure class: integration-level oracle-consumption defects in lending protocols.

## Three Failure Classes

| Failure class | Software semantic mismatch | Required evidence | MVP cases |
|---|---|---|---|
| Feed-binding failure | Identity mismatch | protocol oracle setter or mapping update, followed by supply/borrow | Ploutos Money |
| Price-composition failure | Arithmetic / transformation mismatch | governance or oracle-wrapper config, expected/actual formula, followed by liquidation/borrow | Moonwell cbETH |
| Freshness-handling failure | Temporal validity mismatch | stale-oracle marker or last feed update, followed by supply/borrow | Venus LUNA, Blizz LUNA |

### Feed-Binding Failure

The protocol binds an asset to the wrong price source. The feed itself can report normal prices, so Chainlink `AnswerUpdated` logs are not enough.

Examples:

- Ploutos: `USDC -> BTC/USD`
- Rho: `ETH/address(0) -> WBTC/USD`

### Price-Composition Failure

The protocol uses a price source from the right semantic family but applies an incorrect valuation formula.

Example:

- Moonwell cbETH: `cbETH/USD` should be `cbETH/ETH * ETH/USD`, but the protocol consumed only `cbETH/ETH`.

### Freshness-Handling Failure

The protocol continues to consume an oracle value after it becomes stale, paused, or economically invalid.

Examples:

- Venus LUNA: LUNA remained accepted as collateral after the feed stopped near `$0.107`.
- Blizz LUNA: Avalanche LUNA collateral continued to be accepted after the feed stopped near the lower-bound value.

## Boundary

Included:

- EVM lending and borrowing protocols.
- Price oracle data used for collateral valuation, borrow capacity, or liquidation.
- Failures observable through transaction receipts, protocol events, oracle events, decoded logs, and local historical CSV artifacts.
- Chainlink-compatible feeds, oracle wrappers, governance-set oracle configs, and lending market events.

Excluded:

- General DEX oracle price manipulation.
- Flash-loan manipulation of AMM spot or TWAP prices.
- Randomness or event-resolution oracles.
- Cross-chain bridge oracle failures.
- Pure governance attacks unrelated to oracle valuation.
- Non-EVM incidents.
- Unknown-incident discovery through full-chain scanning.

Boundary statement for paper writing:

> We do not aim to cover all oracle attacks. Instead, we study a bounded but recurring class of integration-level failures where lending protocols consume price-oracle data with incorrect identity, transformation, or freshness semantics.

## Cost-Controlled Collection Policy

The dataset is intentionally bounded to control paid API usage.

- Default to local artifacts and historical CSV files.
- Reuse materialized Dune locator outputs instead of rerunning broad queries.
- Use RPC only for known transaction receipts or missing-field validation.
- Avoid full-chain scans and open-ended `eth_getLogs` windows.
- Keep full candidate lists in JSONL artifacts; reports only need representative previews.
- Never write `.env` API keys into logs, reports, or cached artifacts.

Per-case collection policy is encoded in `artifacts/dataset_manifest.json`.

## Broad Search Extension

The five MVP incidents form a seed set for a larger index-level candidate dataset. The broad-search extension derives one rule family from each failure class, renders Dune SQL templates, assigns evidence-closure tiers to remote candidates, and materializes only `A_replayable` plus logically eligible `B_high_confidence_incomplete` evidence slices locally. It does not use top-k, weighted scores, or largest-amount cutoffs as dataset selection rules.

- Rule manifest: `artifacts/broad_search/rules.json`
- SQL templates: `artifacts/broad_search/sql/`
- Imported candidate rows: `artifacts/broad_search/candidates_full.jsonl`
- Materialization queue: `artifacts/broad_search/materialization_queue.jsonl`
- Coverage report: `results/broad_search_coverage.md`
- Strategy note: `results/broad_search_strategy.md`
- Dataset scope note: `results/broad_dataset_scope.md`

This extension is deliberately local-first by default: generating SQL does not execute Dune queries, ingestion only reads exported CSV/JSON rows, and materialization is dry-run unless bounded historical receipt downloads are explicitly enabled.

## Paper-Safe Terminology

Recommended:

- `oracle-consumption failure`
- `feed-binding failure`
- `price-composition failure`
- `freshness-handling failure`
- `identity / transformation / freshness semantics`
- `log-driven semantic replay`

Avoid as the dataset title:

- `Chainlink Risk Dataset`
- `DeFi Oracle Risk Dataset`
- `Oracle Attack Dataset`

These names are either too narrow, too broad, or too security-incident focused for a software-engineering submission.

## External Positioning

OWASP Smart Contract Security treats price-oracle trust violations as including manipulation, staleness, and misconfiguration. This dataset focuses on a narrower software-engineering subclass: protocol-side price-oracle consumption failures in lending protocols.

Chainlink Data Feeds are commonly used for lending, collateral, liquidation, and insolvency protection. This matches the state transitions replayed by the dataset, but the dataset is not limited to Chainlink feed logs alone.

References:

- OWASP SC03 Price Oracle Manipulation: https://scs.owasp.org/sctop10/SC03-PriceOracleManipulation/
- Chainlink Data Feeds: https://chain.link/data-feeds
