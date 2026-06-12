# RQ3 Early Evidence Lead Time

- Cases: `6`
- Pre-attack observed with tx evidence: `4`
- Semantic-marker-only cases: `2`

| Case | Status | Lead seconds | Dangerous event | Dangerous tx | First impact tx |
|---|---|---:|---|---|---|
| `ploutos` | `pre_attack_observed` | 12 | `ORACLE_FEED_SET` | `0xcfedf63b37a6cd45b21bc94e3de5412fee0765e7dad6b7c8561a01cebd193ab6` | `0xa17dc37e1b65c65d20042212fb834974f7faaa961442e3fc05393778705f8474` |
| `moonwell_cbeth` | `pre_attack_observed` | 2 | `ORACLE_FORMULA_SET` | `0xd26baf29dcba7bf66db4be17b46a49bb4dacca41ace968c98c8a5b09a03ae812` | `0xc400576de059e8c21c13249bd4cf28b8e8f4be9052772208b65dfa10cd15a7ce` |
| `moonwell_wrseth` | `semantic_marker_only` | 1 | `ORACLE_PRICE_MALFUNCTION` | `` | `0x229caeb87e0b6c31afad950150d2ba05a8d7fe823c9e5c05af63b4150b8f6cc6` |
| `blueberry_faulty_oracle` | `semantic_marker_only` | 63971 | `ORACLE_IMPLEMENTATION_MISMATCH` | `` | `0xf0464b01d962f714eee9d4392b2494524d0e10ce3eb3723873afd1346b8b06e4` |
| `venus_luna` | `pre_attack_observed` | 471 | `STALE_ORACLE_START` | `0xa73bcdba45d34dde372a3284ef4749004a76b2e04be345c602c99d60f4048d4f` | `0xf5004eb392b1e9403cb5d5e40d11981352d6afe9214d0896cc55fb111e0ff41f` |
| `blizz_luna` | `pre_attack_observed` | 44525 | `STALE_ORACLE_START` | `0x6b5f6f5b620489aa6616c7e0b4fdd9df712ef47fbd9ba9acf9dedb8cd2207473` | `0x567d89dce96868de08559dbdb1bbe24f0bae47fa421b9dc140496a0f6808cb51` |

- semantic_marker_only means the case trace has a validated semantic marker but no canonical pre-impact tx hash.
- Lead time is measured from first dangerous oracle/config/stale evidence to first borrow/liquidation impact.
