# Moonwell wrsETH and Blueberry Log Evidence

## Scope

This note summarizes read-only historical log evidence for two price-semantics cases that do not have a clear event-log-backed oracle configuration trigger in the current dataset:

- Moonwell wrsETH oracle malfunction on Base.
- Blueberry faulty oracle deployment on Ethereum.

The analysis uses bounded `eth_getLogs` queries over known oracle/controller addresses and receipt logs already materialized for the first attack transactions.

## Pre-Attack Oracle-Related Logs

### Dune Check

- Dune execution id: `01KS9XN5QNYHVG3NGAPABG8GBG`.
- State: `QUERY_STATE_COMPLETED`.
- Credits: `6.454264706`.
- Query artifact: `artifacts/broad_search/case_coverage/oracle_config_log_dune_check/query.sql`.
- Result artifact: `artifacts/broad_search/case_coverage/oracle_config_log_dune_check/result.json`.

| case | window | checked addresses | result |
|---|---:|---:|---|
| Moonwell wrsETH | 200,000 blocks before first attack block `37722875` | wrsETH feed, ETH/USD feed, oracle adapter, Moonwell oracle wrapper, comptroller | Feed/wrapper/adapter addresses emitted no logs. Comptroller emitted normal market/account logs, but no direct oracle config log. |
| Blueberry | 100,000 blocks before first attack block `19287289` | controller, price oracle proxy path, core oracle path, feed proxies | Controller and oracle proxy/core oracle path emitted logs. These show configuration/activity around lending and oracle contracts, but the dataset still needs ABI/source-backed interpretation before treating them as the root trigger. |

### Moonwell wrsETH Dune Topics

| address role | topic0 | decoded / interpretation | logs | txs | latest block | latest tx |
|---|---|---|---:|---:|---:|---|
| wrsETH/ETH feed | N/A | no logs in checked window | 0 | 0 | N/A | N/A |
| ETH/USD feed | N/A | no logs in checked window | 0 | 0 | N/A | N/A |
| oracle adapter from trace | N/A | no logs in checked window | 0 | 0 | N/A | N/A |
| Moonwell oracle wrapper from trace | N/A | no logs in checked window | 0 | 0 | N/A | N/A |
| Moonwell comptroller | `0x3ab23ab0d51cccc0c3085aec51f99228625aa1a922b3a8ca89a26b0f2027a1a5` | `MarketEntered(address,address)` | 435 | 420 | 37722803 | `0x9a513472d908ff1e9ee696fb1663df964a04c1b1503fd0813b9a8f59af942675` |
| Moonwell comptroller | `0xe699a64c18b07ac5b7301aa273f36a2287239eb9501d81950672794afba29a0d` | undecoded comptroller event | 63 | 63 | 37721589 | `0xe1acdb0f56568ec7f6302fc8aa0824a4803a75a69983ef3c552f72d3e2addccf` |

### Blueberry Pre-Attack Topics

| address role | topic0 | decoded / interpretation | logs | txs | latest block | latest tx |
|---|---|---|---:|---:|---:|---|
| Blueberry controller | `0xd2430896b2083037d8bf873ee97e05de0442c7137b4c9413b9e928f7212869e9` | undecoded controller event | 14 | 14 | 19282025 | `0x60f89a4846cdfe257423cdd8ce0090d013ae68481d71adc6594ac5cdaccf1312` |
| Blueberry controller | `0x6f1951b2aad10f3fc81b86d91105b413a5b3f847a34bbc5ce1904201b14438f6` | `NewBorrowCap(address,uint256)` | 13 | 1 | 19282027 | `0x28e522e8e0a68cd36f567d76ec6c93fcb04a1a7847f30a355262161a70a93b84` |
| Blueberry controller | `0x71aec636243f9709bb0007ae15e9afb8150ab01716d75fd7573be5cc096e03b0` | undecoded controller event | 13 | 13 | 19282026 | `0xddfa180adc51772e78fd2925b6a2b1acca4147b74bea1e3fc334f42c647e879f` |
| Blueberry controller | `0xcf583bb0c569eb967f806b11601c4cb93c10310485c67add5f8362c2f212321f` | undecoded controller event | 1 | 1 | 19196915 | `0xf3839f44184a01b120c24df84e0bfa3b7913b041909a6cd05005df9612490381` |
| Blueberry controller | `0xd52b2b9b7e9ee655fcb95d2e5b9e0c9f69e7ef2b8e9d2d0ea78402d576d22e22` | undecoded controller event | 1 | 1 | 19223227 | `0xadf75e4538de805e0ac8b7b1c22d3e1c1b87d6c13cd6e64021cc9b06ace951b9` |
| Price oracle proxy path | `0xa8c96090e146ce1076efa81e5424d56e13d5c3854943f7926406c12d15d6dbe9` | oracle-proxy-path log, not decoded by current ABI lookup | 47 | 7 | 19281917 | `0xebc5b8def4a740070abdea92597dafa415df71c8160baad53bf8304546ba5fd4` |
| Core oracle path | `0xd1b3641b73e6c323671a85001b02db34d4e63a7fa6d264896138094dd6b8bfdf` | core-oracle-path log, not decoded by current ABI lookup | 16 | 3 | 19281917 | `0xebc5b8def4a740070abdea92597dafa415df71c8160baad53bf8304546ba5fd4` |
| Core oracle path | `0xdb99134445c07379338e9d1d3ca5cd958bd95af80ce8e9b6d73882f9b12002e4` | core-oracle-path log, not decoded by current ABI lookup | 12 | 1 | 19221808 | `0xec22b433071377b9190eb66d9689418c7c0eec9a3b471932440049f01c3eb4c1` |
| Core oracle path | `0xaef9ecb0b33da1a5a170fdeed3accb3e88c5257f51d6faa019cea841b864d049` | core-oracle-path log, not decoded by current ABI lookup | 5 | 3 | 19281917 | `0xebc5b8def4a740070abdea92597dafa415df71c8160baad53bf8304546ba5fd4` |
| feed proxies from attack trace | N/A | no logs in checked window | 0 | 0 | N/A | N/A |

## First Attack Transaction Log Pattern

### Moonwell wrsETH

- First attack tx: `0x229caeb87e0b6c31afad950150d2ba05a8d7fe823c9e5c05af63b4150b8f6cc6`
- Block: `37722875`
- Receipt logs: `31`
- Key log pattern:
  - `wrsETH` transfer/approval logs from `0xedfa23602d0ec14714057867a78d01e94176bea0`.
  - `mwrsETH` market token activity from `0xfc41b49d064ac646015b459c522820db9472f4b5`.
  - `mcbXRP` borrow-like event from `0xb4fb8fed5b3aaa8434f0b19b1b623d977e07e86d`.
  - `cbXRP` and `WETH` transfer/swap logs after borrow.

Representative topics:

| topic0 | interpretation |
|---|---|
| `0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef` | ERC20 `Transfer` |
| `0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925` | ERC20 `Approval` |
| `0x4dec04e750ca11537cabcd8a9eab06494de08da3735bc8871cd41250e190bc04` | Compound-style `Mint` / supply-like event |
| `0x13ed6866d4e1ee6da46f845c46d7e54120883d75c5ea9a2dacc1c4ca8984ab80` | Compound-style `Borrow` event |
| `0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67` | Uniswap V3 `Swap` |

Interpretation: the receipt log sequence shows collateral-side wrsETH activity followed by borrow-like market activity and swaps. The oracle failure itself is not emitted as a log; it is visible through the semantic condition that the borrow path consumed an abnormal wrsETH/ETH price source.

### Blueberry

- First attack tx: `0xf0464b01d962f714eee9d4392b2494524d0e10ce3eb3723873afd1346b8b06e4`
- Block: `19287289`
- Receipt logs: `44`
- Key log pattern:
  - WETH flashloan/collateral transfer into the attacker contract.
  - `bWETH` mint/supply-like logs.
  - `bOHM`, `bUSDC`, and `bWBTC` borrow-like logs.
  - OHM/USDC/WBTC transfers and Uniswap swaps into WETH/ETH.
  - Balancer flashloan-like log in the same receipt.

Representative topics:

| topic0 | interpretation |
|---|---|
| `0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef` | ERC20 `Transfer` |
| `0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925` | ERC20 `Approval` |
| `0x4dec04e750ca11537cabcd8a9eab06494de08da3735bc8871cd41250e190bc04` | Compound-style `Mint` / supply-like event |
| `0x13ed6866d4e1ee6da46f845c46d7e54120883d75c5ea9a2dacc1c4ca8984ab80` | Compound-style `Borrow` event |
| `0x3ab23ab0d51cccc0c3085aec51f99228625aa1a922b3a8ca89a26b0f2027a1a5` | `MarketEntered(address,address)` |
| `0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67` | Uniswap V3 `Swap` |
| `0x0d7d75e01ab95780d3cd1c8ec0dd6c2ce19e3a20427eec8bf53283b6fb8e95f0` | Balancer flashloan-like event |

Interpretation: the receipt logs provide a compact local evidence slice for the impact side: WETH supplied, multiple borrow markets used, borrowed assets transferred out, and swaps executed. The oracle-consumption failure is visible through the trace/semantic layer (`borrowAllowed -> getPrice(address) -> latestRoundData()`), not through a dedicated oracle config event.

## Paper Framing

For these two cases, the broad-search scope should not be described as "oracle event logs only." A more accurate statement is:

> Event logs establish the protocol impact closure, while trace-level oracle calls establish the oracle-consumption path when the protocol does not emit a dedicated oracle configuration event.
