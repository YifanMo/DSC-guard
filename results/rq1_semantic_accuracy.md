# RQ1 Semantic Extraction Accuracy

- Cases: `6`
- Automatic IR cases: `6`
- Manual-seed-supported cases: `0`
- Automatic semantic-label F1: `0.457`

| Case | Backend | Inclusion | Precision | Recall | F1 |
|---|---|---|---:|---:|---:|
| `ploutos` | `slither` | `automatic_ir_available` | 1.000 | 0.111 | 0.200 |
| `moonwell_cbeth` | `slither` | `automatic_ir_available` | 1.000 | 0.333 | 0.500 |
| `moonwell_wrseth` | `slither` | `automatic_ir_available` | 0.500 | 0.125 | 0.200 |
| `blueberry_faulty_oracle` | `slither` | `automatic_ir_available` | 0.800 | 0.500 | 0.615 |
| `venus_luna` | `slither` | `automatic_ir_available` | 1.000 | 0.556 | 0.714 |
| `blizz_luna` | `slither` | `automatic_ir_available` | 1.000 | 0.222 | 0.364 |

All active cases have Slither-backed semantic IR in the current artifact set.
