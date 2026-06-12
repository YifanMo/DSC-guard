# Story Detection Summary

The broad-search optimization dataset is combined with the already materialized MVP seed/evaluation set.

- MVP seed cases remain the detection ground truth for the current paper artifact.
- Broad candidates are downloaded only after evidence-closure gates pass.
- Detection output should be refreshed with `python scripts/reproduce_mvp.py --mode verify` after any local materialization run.
