# Eval Replay False-Positive Denominator

- Positive cases: `6`
- Initial benign verified rows: `30`
- Unknown-negative rows materialized and replayed: `30`
- Replay alerts among unknown-negative rows: `0`
- Additional strict benign rows after replay: `11`
- Strict false-positive denominator total: `41`
- Remaining review-only unknown negatives: `19`

Rows that remain `unknown_after_materialization` are not counted in the strict denominator.
