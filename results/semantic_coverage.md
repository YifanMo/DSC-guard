# Semantic Coverage and Claim Boundary

## Claim Boundary

This MVP should be described as:

> Slither-derived semantic IR plus K-style replay semantics for oracle-consumption constraints.

It should not be described as a complete EVM semantics, a complete K Framework reproduction of Solidity execution, or a full-chain vulnerability discovery system.

## Covered Semantics

The current artifact covers the oracle-consumption behavior needed by the five MVP cases:

| Semantic area | Covered behavior | Cases |
|---|---|---|
| Feed binding | Asset-to-feed mapping updates and feed identity constraints | Ploutos, Rho |
| Price composition | Expected-vs-actual oracle formula constraints | Moonwell cbETH |
| Freshness handling | Explicit stale oracle markers and stale collateral consumption | Venus LUNA, Blizz LUNA |
| Lending impact | Supply, borrow, and liquidation events replayed in time order | All cases |
| Actor localization | Borrower/liquidator candidates from historical logs and decoded traces | All cases |
| Evidence closure | Trigger, oracle anomaly, lending impact, actor, temporal order, and replayable constraint | All cases |

## Artifact Boundary

The replay semantics are intentionally narrow. They model the log-level state needed to check business constraints:

- `<oracleMap>` for feed-binding state.
- `<staleAssets>` for stale oracle state.
- `<formulaViolations>` for price-composition state.
- attacker localization from borrow/liquidation records after the oracle violation.

The implementation does not claim:

- complete EVM bytecode semantics;
- complete Solidity semantics;
- full K Framework compatibility for arbitrary contracts;
- automatic discovery of unknown incidents by full-chain scanning;
- exploit simulation, transaction construction, or future target prediction.

## Evidence Sources

The dataset is built from historical, read-only evidence:

- verified local artifacts and decoded Dune event outputs;
- bounded RPC reads for known historical transactions;
- transaction receipts, transaction objects, block headers, and ERC20 transfer logs;
- local Venus CSVs for the Venus LUNA stale oracle case.

API keys are read from `.env` when explicit RPC fill is requested and are not written to reports or artifacts.

## Remaining Limitations

- Ploutos and Rho have receipt-backed transfer flow evidence, but protocol-specific borrow/supply amounts remain `unknown` where ABI-level decoding is incomplete.
- Blizz loss coverage uses known Dune USD prices and remains below public loss estimates because some transfer rows lack USD prices.
- Slither artifacts are useful for semantic framing, but the paper should avoid claiming full automatic extraction for every historical contract path unless those contracts are re-mined with Slither in the final artifact run.
