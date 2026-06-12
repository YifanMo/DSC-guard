# Story Scope Download Plan

Local download scope is controlled by evidence-closure gates, not top-k ranking or weighted scores.

- Target local bundles: `3000`
- Gate-selected candidates: `3`
- Gate-selected receipt/log bundles: `8`
- Estimated RPC requests: `24`
- Requires stricter rules: `False`
- MVP covered by seed or selected candidates: `True`

## Rule Adjustment Recommendations

- Current evidence gates fit the target local bundle budget; do not truncate candidates.

## Safety Boundary

- Read-only historical Dune index and known receipt planning only.
- No chain writes, private keys, write-method calls, attack simulation, or future target prediction.
