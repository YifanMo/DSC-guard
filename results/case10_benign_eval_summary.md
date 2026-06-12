# Per-Case Benign Sample Run

This run generated a deterministic 10-row benign candidate slice for each active case from historical Dune log indexes.

- Dune execution id: `01KSM15PZ9BSXGN1JP1M1M1JSQ, 01KSM16HBBH6B2W03KYEAXJ9PK, 01KSM17BJQXN4J9KR4VQ4ZKX50, 01KSM18V9K71TSHW62D2RXCXZ2, 01KSM19NM2BFSDW7EM7ACZGAVY, 01KSM1C6Q9HP7Z901HEGB1ACZR`
- Dune state: `QUERY_STATE_COMPLETED`
- Dune credits: `84.849352944`
- Total rows: `60`

| case | rows |
|---|---:|
| blizz_luna | 10 |
| blueberry_faulty_oracle | 10 |
| moonwell_cbeth | 10 |
| moonwell_wrseth | 10 |
| ploutos | 10 |
| venus_luna | 10 |

## Label Counts

| label | rows |
|---|---:|
| benign_verified | 30 |
| unknown_negative | 30 |

Only `benign_verified` rows should enter the false-positive denominator immediately. `unknown_negative` rows are hard-benign candidates and require local replay/materialization before being counted as confirmed benign.
