# Blizz LUNA Attack Locator

## Safety scope

- Scope: read-only historical incident detection and forensic reporting.
- The locator queries archived public chain data and writes evidence artifacts only.
- It does not submit transactions, deploy contracts, call protocol write methods, handle private keys, or generate exploit execution steps.

## Venus-derived signal

- LUNA/USD feed: `0xec72d46011d67a6ac4fa7d3f476fa2049dc807ee`
- Last Venus update: block `17737661`, tx `0xa73bcdba45d34dde372a3284ef4749004a76b2e04be345c602c99d60f4048d4f`, answer `$0.10736482`
- Reference window: `2022-05-12T11:38:44Z` to `2022-05-13T12:00:00Z`
- Top reference borrow total: `$11411700` BUSD

Top Venus reference accounts:
- `0x8d655aaaa0ec224b17972df385e25325b9103332` deposited `153302956.306563` LUNA, borrowed `$8867000` BUSD
  - deposit tx: `0xa9a0682280af5be4e6d58ad7cc24018719aaaf3ed04f3a1d2316361ab11735ec`
  - first borrow tx: `0xb81cabf803237f12e145434f68b7e541e0829da17fbf55e347e782e7c6b10a63`
  - largest borrow tx: `0x9725e3ab82543ebd29d3967a39a6cc10cfbd5f4ea5887eeec0105c3ee2e1896a`
- `0x1f6d66ba924ebf554883cf84d482394013ed294b` deposited `77406225.725322` LUNA, borrowed `$2544700` BUSD
  - deposit tx: `0x382484444a46b2898902f6556e91ad2d6f89adb984746276de8c9858db8b7f9d`
  - first borrow tx: `0x9c077d3c492fd07d713aa4f2488e1d6c94407b955039a7e8a19b5bc788a6118f`
  - largest borrow tx: `0xd0e0d9eaa193009d23e8af419d88e4363845a2858f7d640b568ae70ab09c6ef5`

## Data-source status

- `ALCHEMY_KEY`: `present`
- `ETHERSCAN_KEY`: `present`
- `DUNE_MCP_KEY`: `present`

## Dune coarse-screen queries

- `/Users/moyifan/Desktop/desktop/oracle_misconfigure/artifacts/blizz_luna_locator/sql/01_discover_luna_tokens.sql`
- `/Users/moyifan/Desktop/desktop/oracle_misconfigure/artifacts/blizz_luna_locator/sql/02_discover_blizz_addresses.sql`
- `/Users/moyifan/Desktop/desktop/oracle_misconfigure/artifacts/blizz_luna_locator/sql/03_find_blizz_luna_candidates.sql`
- `/Users/moyifan/Desktop/desktop/oracle_misconfigure/artifacts/blizz_luna_locator/sql/04_find_luna_oracle_updates.sql`
- `/Users/moyifan/Desktop/desktop/oracle_misconfigure/artifacts/blizz_luna_locator/sql/05_discover_full_blizz_markets.sql`

## Dune-confirmed historical findings

- LUNA token: `0x120ad3e5a7c796349e591f1570d9f7980f4ea9cb` (Axelar Wrapped LUNA, decimals `6`)
- Blizz bLUNA market: `0xbd1f70fc3bff70a37441c9d8b51c0d9220483c5a`
- LUNA/USD stale marker: feed `0x2e7e21f479167c1206420c956f3e8e392da580f5`, tx `0x6b5f6f5b620489aa6616c7e0b4fdd9df712ef47fbd9ba9acf9dedb8cd2207473`, block `14596360`, answer `$0.10736482`

## Full-market coverage

- Blizz lending markets: `24` total, `1` bLUNA, `23` borrow markets.
- Full candidate accounts: `24`.
- Full evidence counts: `55` LUNA deposit tx, `53` borrow tx.
- Known borrowed USD: `$6305417.642607` vs public Blizz loss `$8280000`; coverage `76.15%`, gap `$1974582.357393`.
- SlowMist comparison point: `$8300000`.
- Missing USD price borrow events: `11`; raw token amounts remain in full artifacts.
- Full candidates JSONL: `artifacts/blizz_luna_locator/dune_candidates_full.jsonl`.
- Top historical candidate accounts from Dune preview:
  - `0x42623912bf3910a30d13a9887cdd19d74d1870d5` deposited `7914327198` LUNA and borrowed about `$4460422.266643567` across `WETH.e, WBTC.e, AAVE.e, LINK.e`
    - borrow tx: `0x31424b26402e8f0d609ea339599f4e071fbc8269ac13910e4731367708a2d337`
    - borrow tx: `0x3e5e20303b58e62f641915776d3355638788835d4aabcfe7d14937d61a875043`
    - borrow tx: `0x45d107bec13a386377c86c8f672e6b483b879693d77eb4197b79b1afcc44632e`
    - borrow tx: `0x29d22ae1b27b502bf0f1c1531a69422d863b2bb3bd531c466bd2ee7e13cc082d`
  - `0x4b6cfd17afbfca3db464843232ec294bb5abe249` deposited `652599998.5` LUNA and borrowed about `$381189.2416666666` across `DAI.e`
    - borrow tx: `0xcdbd16b3c4297709a34f1a1b47644d111b4a395a6b6756e56c45a6484191f6d3`
  - `0xe84c01208c4868d5615fccf0b98f8c90f460d2b6` deposited `1886865805.5` LUNA and borrowed about `$276206.12416666665` across `WETH.e, MIM, USDT.e`
    - borrow tx: `0x81d2f763a170f8074f9a7aa9353fdeac91c7359eca66025b3675866df1af5156`
    - borrow tx: `0x47efb7872b1a140fbcfaf282e5903583428ae2dabcd574d11c86a611d34a63a1`
    - borrow tx: `0x0a888cd11faff6f9688c960aa7943da68c8ee181de39aff7b820371423e9e20c`
    - borrow tx: `0x0abe759396559311722037ea17ad51b200830b5e3dfaf6ae973018e6cfdcbf36`

## Blizz candidate status

- Alchemy verification was not executed. Provide `--luna-token`, `--luna-feed`, one or more `--blizz-address`, and `--execute-alchemy` after Dune resolves the Blizz address set.
- No synthetic Blizz transaction hashes were written by this locator. Existing fixture traces remain only for pipeline tests.
