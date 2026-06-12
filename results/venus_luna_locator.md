# Venus LUNA Materialized Trace

## Safety scope

- Scope: read-only historical incident detection and forensic reporting.
- Data source priority: local CSV first; RPC only fills missing historical metadata.
- It does not submit transactions, call protocol write methods, handle private keys, or generate exploit execution steps.

## Findings

- Stale oracle marker: tx `0xa73bcdba45d34dde372a3284ef4749004a76b2e04be345c602c99d60f4048d4f`, block `17737661`, answer `$0.10736482`.
- Candidate accounts: `12`.
- Evidence counts: `122` vLUNA deposit tx, `95` vBUSD borrow tx.
- Total LUNA deposit: `241225445.631822`.
- Total BUSD borrowed: `$11686144.73999`.
- Top two BUSD borrowed: `$11411700` vs public narrative `$11411700`.
- RPC fallback requests: `0`.

## Top Candidates

- `0x8d655aaaa0ec224b17972df385e25325b9103332` deposited `153302956.306563` LUNA and borrowed `$8867000` BUSD
  - first deposit tx: `0xa9a0682280af5be4e6d58ad7cc24018719aaaf3ed04f3a1d2316361ab11735ec`
  - first borrow tx: `0xb81cabf803237f12e145434f68b7e541e0829da17fbf55e347e782e7c6b10a63`
- `0x1f6d66ba924ebf554883cf84d482394013ed294b` deposited `77406225.725322` LUNA and borrowed `$2544700` BUSD
  - first deposit tx: `0x382484444a46b2898902f6556e91ad2d6f89adb984746276de8c9858db8b7f9d`
  - first borrow tx: `0x9c077d3c492fd07d713aa4f2488e1d6c94407b955039a7e8a19b5bc788a6118f`
- `0x3b7f525dc67cca55251abb5d04c81a83a6005269` deposited `7164378.94279` LUNA and borrowed `$159350` BUSD
  - first deposit tx: `0xb012400c94380a94bbe482be5b28f4ea84b615736cd398449a5a6035ddd0bf44`
  - first borrow tx: `0x7f56b112ff81183986d68bd6d40cb09bfeb1b394507782f574ec38f6c50fe1c0`
- `0x5e6a2f64ff885f095a279ca7deb938ec43c54c4e` deposited `2507596.237243` LUNA and borrowed `$58935.099815` BUSD
  - first deposit tx: `0x26deaac18f1fba41982591e2c534064d7fee3fac6a5c69c72930ed7abb30e6bf`
  - first borrow tx: `0x5705df104877041a9618afe04bfb964876cb1e070ff9417ec50b20102640979d`
- `0x20481433fa76ccf0766ae566fb8582a6c5261c80` deposited `815535.23813` LUNA and borrowed `$44040` BUSD
  - first deposit tx: `0xa2f81e0ce3fe738abe85fcb6ee5898b714eefb75acfbceb2eff5d66e2b062de5`
  - first borrow tx: `0xec4353ece5b4f04983d3b5e3fdd4e6686b5c07019ddfc4d3ac8a991a4f5fc37d`
