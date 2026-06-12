# Toolchain Hardening Snapshot

This run hardens the local DSC-Guard artifact path from fixture-only output to a real verified-source Slither/K check.

## Installed Tools

- Slither: `0.10.4`
- default solc: `0.8.35+commit.47b9dedd.Darwin.appleclang`
- K Framework: `v7.1.282`
- Java: `OpenJDK 26.0.1`

K commands require Homebrew OpenJDK on this machine. Project scripts set `JAVA_HOME=/opt/homebrew/opt/openjdk` and prepend the Java bin directory before running `kompile`.

## Source Collection

All six active cases now have `source_targets` in `config/cases.json`. `scripts/source_collect.py` fetched verified source snapshots and ABI metadata into `cache/sources/{case}` and `cache/abi/{case}`.

| Case | Configured source targets | Collected source files | Slither-mined targets |
|---|---:|---:|---:|
| `ploutos` | 2 | 7 | 7 |
| `moonwell_cbeth` | 3 | 47 | 39 |
| `moonwell_wrseth` | 4 | 27 | 27 |
| `blueberry_faulty_oracle` | 5 | 64 | 61 |
| `venus_luna` | 3 | 56 | 46 |
| `blizz_luna` | 5 | 41 | 33 |

## Case Status

| Case | Slither backend | Event semantics | K module | K compiled |
|---|---|---:|---|---|
| `ploutos` | `slither` | 3 | `artifacts/k/ploutos.k` | yes |
| `moonwell_cbeth` | `slither` | 107 | `artifacts/k/moonwell_cbeth.k` | yes |
| `moonwell_wrseth` | `slither` | 77 | `artifacts/k/moonwell_wrseth.k` | yes |
| `blueberry_faulty_oracle` | `slither` | 168 | `artifacts/k/blueberry_faulty_oracle.k` | yes |
| `venus_luna` | `slither` | 227 | `artifacts/k/venus_luna.k` | yes |
| `blizz_luna` | `slither` | 218 | `artifacts/k/blizz_luna.k` | yes |

The compiled K definitions are stored under `artifacts/k/*-kompiled/`. The machine-readable manifest is `artifacts/k/k_compile_manifest.json`.

## Boundary

This is now a real-source toolchain check: Slither IR was generated with `scripts/slither_mine.py --require-slither` from verified sources collected for each case, and each generated K module was compiled with `scripts/k_generate.py --kompile`.

The extraction is not complete for every fetched Solidity file. Several explorer source bundles still produce import/remapping or nonstandard source-format warnings, and skipped files are recorded in `artifacts/slither_ir/{case}.json`. The claim supported by this artifact is therefore:

`verified-source Slither extraction succeeded for every active case and generated compilable K-style replay modules`, not `every fetched source file compiled without warning`.
