# wrsETH / Blueberry Root Cause Query Results

## Moonwell wrsETH

- Target malfunction time: `2025-11-04T05:44:55Z`, target block `37722874`.
- First attack tx: `0x229caeb87e0b6c31afad950150d2ba05a8d7fe823c9e5c05af63b4150b8f6cc6`, block `37722875`.
- Historical calls and logs were queried on the wrsETH/ETH oracle, ETH/USD oracle, traced adapter/wrapper, comptroller, and any readable `aggregator()` targets.

| role | address | latestRoundData updated_at | answer_raw | pre-attack logs | latest log tx |
|---|---|---:|---:|---:|---|
| `eth_usd_oracle` | `0x71041dddad3595f9ced3dccfbe3d1f4b0a16bb70` | `2025-11-04T05:43:55Z` | `352321000000` | 0 | `` |
| `eth_usd_oracle_aggregator` | `0x57d2d46fc7ff2a7142d479f2f59e1e3f95447077` | `` | `` | 123 | `0x8f97c467639ed2f58b715e96b45157a8b053ead659a3ea92c38b94cc0a485d57` |
| `moonwell_comptroller` | `0xfbb21d0380bee3312b33c4353c8936a0f13ef26c` | `` | `` | 10 | `0x9a513472d908ff1e9ee696fb1663df964a04c1b1503fd0813b9a8f59af942675` |
| `moonwell_oracle_wrapper_from_trace` | `0xec942be8a8114bfd0396a5052c36027f2ca6a9d0` | `` | `` | 0 | `` |
| `oracle_adapter_from_trace` | `0x79c613b4f07080963c3b0ca58eb2745dd4c744a5` | `2025-11-04T05:44:55Z` | `5813066107843462759938890135` | 0 | `` |
| `wrseth_eth_oracle` | `0xd7221b10fbbc1e1ba95fd0b4d031c15f7f365296` | `2025-11-04T05:44:55Z` | `1649934607316470707093500` | 0 | `` |
| `wrseth_eth_oracle_aggregator` | `0x4a61db12d0cb4293d799ecdd82e5994b5746f850` | `` | `` | 45 | `0x05098c93b19d707b54282e904756ad7975a73f5472355bd1c336a681b099dd36` |

## Blueberry

- First attack tx: `0xf0464b01d962f714eee9d4392b2494524d0e10ce3eb3723873afd1346b8b06e4`, block `19287289`.
- Queried contract creation/source metadata, common getters, EIP-1967 slots, candidate pre-attack config transactions, and optional storage diff trace.

| tx | block time | to | selector | decoded function | target events |
|---|---|---|---|---|---|
| `0xebc5b8def4a740070abdea92597dafa415df71c8160baad53bf8304546ba5fd4` | `2024-02-22T08:17:23Z` | `0x72d19f7c71a2bd5e61871b1d3df7a45ae5ec9582` | `0x6a761202` | `` | 0x442e715f626346e8c54381002da614f62bee8d27386535b2521ec8540898556e:1; OwnershipTransferred(address,address):1; SetRoute(address,address):14; SetTimeGap(address,uint256):1 |
| `0xec22b433071377b9190eb66d9689418c7c0eec9a3b471932440049f01c3eb4c1` | `2024-02-13T21:39:11Z` | `0x72d19f7c71a2bd5e61871b1d3df7a45ae5ec9582` | `0x6a761202` | `` | 0x442e715f626346e8c54381002da614f62bee8d27386535b2521ec8540898556e:1; SetRoute(address,address):12; SetTokenRemapping(address,address):12 |
| `0x28e522e8e0a68cd36f567d76ec6c93fcb04a1a7847f30a355262161a70a93b84` | `2024-02-22T08:39:35Z` | `0xffadb0bba4379dfabfb20ca6823f6ec439429ec2` | `0x607ef6c1` | `_setMarketBorrowCaps(address[],uint256[])` | NewBorrowCap(address,uint256):13 |
| `0x60f89a4846cdfe257423cdd8ce0090d013ae68481d71adc6594ac5cdaccf1312` | `2024-02-22T08:39:11Z` | `0xffadb0bba4379dfabfb20ca6823f6ec439429ec2` | `0xd84f6aeb` | `_setCreditLimit(address,address,uint256)` | CreditLimitChanged(address,address,uint256):1 |
| `0xddfa180adc51772e78fd2925b6a2b1acca4147b74bea1e3fc334f42c647e879f` | `2024-02-22T08:39:23Z` | `0xffadb0bba4379dfabfb20ca6823f6ec439429ec2` | `0x18c882a5` | `_setBorrowPaused(address,bool)` | ActionPaused(address,string,bool):1 |
| `0xf3839f44184a01b120c24df84e0bfa3b7913b041909a6cd05005df9612490381` | `2024-02-10T09:46:59Z` | `0xffadb0bba4379dfabfb20ca6823f6ec439429ec2` | `0x36bdd087` | `_supportMarket(address,uint8)` | MarketListed(address):1 |
| `0xadf75e4538de805e0ac8b7b1c22d3e1c1b87d6c13cd6e64021cc9b06ace951b9` | `2024-02-14T02:26:47Z` | `0xffadb0bba4379dfabfb20ca6823f6ec439429ec2` | `0x55ee1fe1` | `_setPriceOracle(address)` | NewPriceOracle(address,address):1 |

## Artifacts

- JSON: `artifacts/root_cause_queries/wrseth_blueberry_root_cause.json`
