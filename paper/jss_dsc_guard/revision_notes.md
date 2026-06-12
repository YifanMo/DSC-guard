# Revision notes from rejected version

This draft intentionally changes the rejected paper's framing.

- Scope is narrowed from general DON attack detection to EVM lending price-oracle consumption failures.
- The single LUNA-only evaluation is replaced with six cases: Ploutos, Moonwell cbETH, Moonwell wrsETH, Blueberry, Venus LUNA, and Blizz LUNA.
- Standard metrics are added: case recall, impact-transaction recall, log-level warning recall, strict false-positive denominator, conservative precision floor, early-evidence lead time, actor localization, and ablation.
- The paper explicitly discusses multi-contract evidence closure instead of claiming isolated single-contract state machines.
- The logs-only blind spot is stated as a limitation: unlogged state transitions can desynchronize the replay state.
- Related work now includes VeriOracle, DeFiRanger, Slither, KEVM/K, and log-analysis work.
- The claim is conservative: Slither-derived semantic IR plus K-style replay semantics, not a complete EVM semantics or universal oracle attack detector.
