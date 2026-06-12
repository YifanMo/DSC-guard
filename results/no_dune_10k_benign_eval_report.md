# No-Dune 10k Benign Evaluation Dataset

This dataset is built from case-aware historical oracle-scope logs using Explorer/Etherscan and RPC only. Dune count-only results are used only as prior pool-size estimates for allocation.

- Target samples: `10000`
- Selected candidates: `10000`
- Explorer requests: `0/25000`
- Candidate RPC fallback requests: `0/30000`

## Allocation

| case | estimated pool | allocation | selected |
|---|---:|---:|---:|
| ploutos | 62 | 62 | 60 |
| blueberry_faulty_oracle | 38 | 38 | 34 |
| moonwell_wrseth | 677 | 677 | 636 |
| moonwell_cbeth | 1687292 | 3075 | 2896 |
| venus_luna | 5376 | 5084 | 4751 |
| blizz_luna | 9250 | 3074 | 1623 |

## Materialization

- Materialized samples: `10000`
- Replay alerts: `14`
- Strict benign after replay: `9637`
- RPC requests: `0/60000`
- Source requests: `0/12000`
- Debug trace requests: `0/2000`

Only `benign_verified` rows after replay enter the false-positive denominator. `unknown_negative` rows remain a review pool.
