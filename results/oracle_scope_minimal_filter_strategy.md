# Oracle-Scope Minimal Filter Strategy

This strategy turns the broad oracle activity surface into a small local validation dataset without using top-k, weighted scores, or amount-ranked truncation.

## Layers

- Layer 1 counts `oracle_activity_log_scope` logs on Dune. This is the broad research surface, not the suspicious-candidate count.
- Layer 2 keeps only candidates with an oracle boundary followed by lending impact under R1/R2/R3 evidence-closure rules.
- Layer 3 schedules only the minimal causal replay bundle for A/B tier candidates.

## Case Coverage

- R1 covers Ploutos through feed-binding config plus downstream lending/flow impact.
- R2 covers Moonwell cbETH, Moonwell wrsETH, and Blueberry through oracle config, abnormal oracle update, or oracle-path wiring plus borrow/liquidation impact.
- R3 covers Venus and Blizz through lower-bound/stale Chainlink update plus same-account lending impact closure.

## Safety Boundary

- Dune SQL generation and optional Dune execution are read-only historical analysis.
- The default script does not execute Dune, RPC, chain writes, simulations, or private-key operations.

Rendered SQL artifacts: `/var/folders/gl/7_7qr96n1y9709c_l9wjxmbr0000gn/T/tmpx_oz51jm`
