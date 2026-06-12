#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, DefaultDict, Dict, Iterable, List, Optional, Tuple

from common import PipelineError, ensure_dir, repo_path, write_json, write_jsonl


REQUIRED_FIELDS = {
    "chain",
    "failure_class",
    "trigger_tx",
    "trigger_time",
    "evidence_tier",
    "has_trigger",
    "has_oracle_anomaly",
    "has_lending_impact",
    "has_actor",
    "has_temporal_order",
    "has_replayable_constraint",
    "impact_tx_count",
    "impact_usd_known",
    "source_quality_rank",
}
QUEUE_WINDOWS_SECONDS = {
    "feed_binding_failure": 24 * 3600,
    "price_composition_failure": 24 * 3600,
    "freshness_handling_failure": 24 * 3600,
}
REQUEST_CAPS = {
    "feed_binding_failure": {"trigger_receipts": 1, "impact_receipts": 1, "abi_requests": 2},
    "price_composition_failure": {"trigger_receipts": 1, "impact_receipts": 2, "abi_requests": 3},
    "freshness_handling_failure": {"trigger_receipts": 1, "impact_receipts": 2, "abi_requests": 2},
}
OPTIONAL_EVIDENCE_FIELDS = {
    "asset_identity_observed",
    "feed_identity_observed",
    "identity_mismatch_hint",
    "protocol_cluster_id",
    "feed_label",
    "feed_identity",
    "feed_identity_source",
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows_from_csv(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _rows_from_json(path: Path) -> List[Dict[str, Any]]:
    payload = _load_json(path)
    if isinstance(payload, list):
        return [dict(item) for item in payload]
    if isinstance(payload, dict):
        if isinstance(payload.get("rows"), list):
            return [dict(item) for item in payload["rows"]]
        if isinstance(payload.get("result"), list):
            return [dict(item) for item in payload["result"]]
    raise PipelineError(f"Unsupported JSON export shape: {path}")


def _rows_from_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_export_rows(input_dir: Path, *, allow_empty: bool = False) -> List[Dict[str, Any]]:
    if not input_dir.exists():
        raise PipelineError(f"Missing input directory: {input_dir}")
    rows: List[Dict[str, Any]] = []
    export_files_seen = 0
    for path in sorted(input_dir.rglob("*")):
        if path.name.startswith(".") or not path.is_file():
            continue
        try:
            if path.suffix.lower() == ".csv":
                loaded = _rows_from_csv(path)
            elif path.suffix.lower() == ".json":
                loaded = _rows_from_json(path)
            elif path.suffix.lower() == ".jsonl":
                loaded = _rows_from_jsonl(path)
            else:
                continue
        except PipelineError:
            continue
        export_files_seen += 1
        for index, row in enumerate(loaded, start=1):
            item = dict(row)
            item.setdefault("source_file", str(path.relative_to(input_dir)))
            item.setdefault("source_row", index)
            rows.append(item)
    if not rows and not allow_empty:
        raise PipelineError(f"No CSV/JSON/JSONL candidate exports found in {input_dir}")
    if not rows and allow_empty and export_files_seen == 0:
        raise PipelineError(f"No CSV/JSON/JSONL exports found in {input_dir}")
    return rows


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


def _int(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    return int(float(str(value)))


def _float(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    return float(str(value))


def _parse_time(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.fromtimestamp(0, timezone.utc)
    if text.endswith(" UTC"):
        text = text[:-4] + "+00:00"
    elif text.endswith("Z"):
        text = text[:-1] + "+00:00"
    elif "+" not in text and text.count(":") >= 2:
        text += "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def _tx_list(value: Any) -> List[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value)
    separator = ";" if ";" in text else ","
    return [item.strip() for item in text.split(separator) if item.strip()]


def normalize_candidate(row: Dict[str, Any], candidate_id: int) -> Dict[str, Any]:
    missing = sorted(field for field in REQUIRED_FIELDS if field not in row)
    if missing:
        raise PipelineError(f"Candidate row is missing required fields {missing}: {row}")
    trigger_time = _parse_time(row.get("trigger_time"))
    normalized = {
        "candidate_id": f"broad-{candidate_id:06d}",
        "dataset_layer": str(row.get("dataset_layer", "remote_candidate") or "remote_candidate").strip(),
        "already_materialized": _bool(row.get("already_materialized")),
        "chain": str(row.get("chain", "")).strip(),
        "protocol": str(row.get("protocol", "unknown_protocol") or "unknown_protocol").strip(),
        "failure_class": str(row.get("failure_class", "")).strip(),
        "trigger_tx": str(row.get("trigger_tx", "")).strip(),
        "trigger_block": _int(row.get("trigger_block")),
        "trigger_time": trigger_time.isoformat().replace("+00:00", "Z"),
        "trigger_year": trigger_time.year,
        "affected_asset": str(row.get("affected_asset", "") or "").strip(),
        "evidence_tier": str(row.get("evidence_tier", "")).strip(),
        "closure_reason": str(row.get("closure_reason", "") or "").strip(),
        "has_trigger": _bool(row.get("has_trigger")),
        "has_oracle_anomaly": _bool(row.get("has_oracle_anomaly")),
        "has_lending_impact": _bool(row.get("has_lending_impact")),
        "has_actor": _bool(row.get("has_actor")),
        "has_temporal_order": _bool(row.get("has_temporal_order")),
        "has_replayable_constraint": _bool(row.get("has_replayable_constraint")),
        "trigger_to_impact_seconds": _int(row.get("trigger_to_impact_seconds"), default=0),
        "impact_tx_count": _int(row.get("impact_tx_count")),
        "impact_usd_known": _float(row.get("impact_usd_known")),
        "source_quality": str(row.get("source_quality", "") or "").strip(),
        "source_quality_rank": _int(row.get("source_quality_rank"), default=99),
        "remote_query_id": str(row.get("remote_query_id", "") or "").strip(),
        "impact_txs": _tx_list(row.get("impact_txs")),
        "source_file": row.get("source_file", ""),
        "source_row": row.get("source_row", ""),
    }
    for field in OPTIONAL_EVIDENCE_FIELDS:
        if field in row:
            if field.endswith("_observed") or field == "identity_mismatch_hint":
                normalized[field] = _bool(row.get(field))
            else:
                normalized[field] = str(row.get(field, "") or "").strip()
    return normalized


def _candidate_key(candidate: Dict[str, Any]) -> Tuple[str, str, str, str]:
    return (
        candidate["chain"],
        candidate["failure_class"],
        candidate["trigger_tx"].lower(),
        candidate.get("affected_asset", "").lower(),
    )


def normalize_candidates(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    candidates: List[Dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        candidate = normalize_candidate(row, index)
        key = _candidate_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
    return sorted(
        candidates,
        key=lambda item: (
            item["chain"],
            item["failure_class"],
            item["trigger_year"],
            item["trigger_tx"],
        ),
    )


def eligible_for_queue(candidate: Dict[str, Any]) -> bool:
    if candidate.get("already_materialized") or candidate.get("dataset_layer") == "seed_evaluation":
        return False
    if candidate["evidence_tier"] == "A_replayable":
        return True
    if candidate["evidence_tier"] != "B_high_confidence_incomplete":
        return False
    window = QUEUE_WINDOWS_SECONDS.get(candidate["failure_class"], 24 * 3600)
    return (
        candidate["has_lending_impact"]
        and candidate["has_temporal_order"]
        and candidate["source_quality_rank"] <= 2
        and candidate["impact_tx_count"] > 0
        and 0 <= candidate["trigger_to_impact_seconds"] <= window
    )


def _queue_sort_key(candidate: Dict[str, Any]) -> Tuple[int, int, int, int, float, int, int]:
    tier_rank = {"A_replayable": 1, "B_high_confidence_incomplete": 2}.get(candidate["evidence_tier"], 9)
    return (
        tier_rank,
        -int(candidate["has_replayable_constraint"]),
        -int(candidate["has_actor"]),
        candidate["trigger_to_impact_seconds"] if candidate["trigger_to_impact_seconds"] >= 0 else 10**12,
        -candidate["impact_usd_known"],
        -candidate["impact_tx_count"],
        candidate["source_quality_rank"],
    )


def build_queue(candidates: List[Dict[str, Any]], max_per_class: Optional[int] = None) -> List[Dict[str, Any]]:
    grouped: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        if eligible_for_queue(candidate):
            grouped[candidate["failure_class"]].append(candidate)
    queue: List[Dict[str, Any]] = []
    for failure_class, items in grouped.items():
        for gate_sequence, candidate in enumerate(sorted(items, key=_queue_sort_key), start=1):
            caps = REQUEST_CAPS.get(failure_class, {"trigger_receipts": 1, "impact_receipts": 5, "abi_requests": 2})
            impact_receipts = min(candidate["impact_tx_count"], caps["impact_receipts"])
            queue.append(
                {
                    **candidate,
                    "gate_sequence": gate_sequence,
                    "materialization_action": "download_minimal_causal_trace",
                    "estimated_trigger_receipts": caps["trigger_receipts"],
                    "estimated_impact_receipts": impact_receipts,
                    "estimated_abi_requests": caps["abi_requests"],
                    "estimated_total_rpc_requests": caps["trigger_receipts"] + impact_receipts,
                }
            )
    return sorted(queue, key=lambda item: (item["failure_class"], item["gate_sequence"]))


def summarize(candidates: List[Dict[str, Any]], queue: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_chain_year_class_tier: DefaultDict[str, int] = defaultdict(int)
    by_class_tier: DefaultDict[str, int] = defaultdict(int)
    by_source_quality: DefaultDict[str, int] = defaultdict(int)
    impact_usd_by_class: DefaultDict[str, float] = defaultdict(float)
    queue_by_class: DefaultDict[str, int] = defaultdict(int)
    seed_summary_path = repo_path("artifacts", "broad_search", "seed_candidate_summary.json")
    seed_summary: Dict[str, Any] = {}
    if seed_summary_path.exists():
        try:
            seed_summary = _load_json(seed_summary_path)
        except json.JSONDecodeError:
            seed_summary = {}
    for candidate in candidates:
        key = "|".join(
            [
                candidate["chain"],
                str(candidate["trigger_year"]),
                candidate["failure_class"],
                candidate["evidence_tier"],
            ]
        )
        by_chain_year_class_tier[key] += 1
        by_class_tier[f"{candidate['failure_class']}|{candidate['evidence_tier']}"] += 1
        by_source_quality[candidate["source_quality"] or "unknown"] += 1
        impact_usd_by_class[candidate["failure_class"]] += candidate["impact_usd_known"]
    for candidate in queue:
        queue_by_class[candidate["failure_class"]] += 1
    return {
        "dataset_type": "index_level_candidate_dataset",
        "seed_evaluation_count": int(seed_summary.get("seed_evaluation_count") or 0),
        "remote_candidate_count": len(candidates),
        "candidate_count": len(candidates),
        "materialization_queue_count": len(queue),
        "local_materialization_policy": "gate-only: all A_replayable plus B_high_confidence_incomplete candidates satisfying fixed evidence-closure predicates; no top-k truncation",
        "by_chain_year_class_tier": dict(sorted(by_chain_year_class_tier.items())),
        "by_class_tier": dict(sorted(by_class_tier.items())),
        "by_source_quality": dict(sorted(by_source_quality.items())),
        "impact_usd_known_by_class": dict(sorted(impact_usd_by_class.items())),
        "queue_by_class": dict(sorted(queue_by_class.items())),
        "estimated_queue_receipt_bundles": sum(item["estimated_total_rpc_requests"] for item in queue),
        "estimated_queue_rpc_requests": sum(item["estimated_total_rpc_requests"] for item in queue) * 3,
        "estimated_queue_abi_requests": sum(item["estimated_abi_requests"] for item in queue),
    }


def _markdown_summary(summary: Dict[str, Any]) -> str:
    lines = [
        "# Broad Search Coverage",
        "",
        "This report summarizes remote index-level broad-search candidates imported from Dune-style exports. It does not imply that all raw logs or receipts were downloaded locally.",
        "",
        f"- Candidate count: `{summary['candidate_count']}`",
        f"- Seed evaluation count: `{summary.get('seed_evaluation_count', 0)}`",
        f"- Remote candidate count: `{summary.get('remote_candidate_count', summary['candidate_count'])}`",
        f"- Materialization queue count: `{summary['materialization_queue_count']}`",
        f"- Estimated queue receipt bundles: `{summary['estimated_queue_receipt_bundles']}`",
        f"- Estimated queue RPC requests: `{summary['estimated_queue_rpc_requests']}`",
        f"- Estimated queue ABI requests: `{summary['estimated_queue_abi_requests']}`",
        "",
        "## By Chain / Year / Class / Tier",
        "",
        "| chain | year | failure_class | evidence_tier | candidate_count |",
        "|---|---:|---|---|---:|",
    ]
    for key, count in summary["by_chain_year_class_tier"].items():
        chain, year, failure_class, tier = key.split("|")
        lines.append(f"| {chain} | {year} | {failure_class} | {tier} | {count} |")
    lines.extend(["", "## By Failure Class / Tier", "", "| failure_class | evidence_tier | candidate_count |", "|---|---|---:|"])
    for key, count in summary["by_class_tier"].items():
        failure_class, tier = key.split("|")
        lines.append(f"| {failure_class} | {tier} | {count} |")
    lines.extend(["", "## By Source Quality", "", "| source_quality | candidate_count |", "|---|---:|"])
    for source_quality, count in summary["by_source_quality"].items():
        lines.append(f"| {source_quality} | {count} |")
    lines.append("")
    return "\n".join(lines)


def ingest(input_dir: Path, max_per_class: Optional[int] = None, *, output_dir: Optional[Path] = None, allow_empty: bool = False) -> Dict[str, Path]:
    rows = load_export_rows(input_dir, allow_empty=allow_empty)
    candidates = normalize_candidates(rows)
    queue = build_queue(candidates, max_per_class=max_per_class)
    summary = summarize(candidates, queue)
    if output_dir is None:
        outputs = {
            "candidates": repo_path("artifacts", "broad_search", "candidates_full.jsonl"),
            "summary": repo_path("artifacts", "broad_search", "candidate_summary.json"),
            "queue": repo_path("artifacts", "broad_search", "materialization_queue.jsonl"),
            "coverage": repo_path("results", "broad_search_coverage.md"),
        }
    else:
        outputs = {
            "candidates": output_dir / "candidates_full.jsonl",
            "summary": output_dir / "candidate_summary.json",
            "queue": output_dir / "materialization_queue.jsonl",
            "coverage": output_dir / "broad_search_coverage.md",
        }
    write_jsonl(outputs["candidates"], candidates)
    write_json(outputs["summary"], summary)
    write_jsonl(outputs["queue"], queue)
    ensure_dir(outputs["coverage"].parent)
    outputs["coverage"].write_text(_markdown_summary(summary), encoding="utf-8")
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest broad-search candidate exports into local index and materialization queue artifacts.")
    parser.add_argument("--input-dir", required=True, help="Directory containing Dune-exported CSV/JSON/JSONL candidate files.")
    parser.add_argument(
        "--max-per-class",
        type=int,
        default=None,
        help="Deprecated compatibility flag; ignored because materialization queues are evidence-gate only.",
    )
    parser.add_argument("--allow-empty", action="store_true", help="Write empty candidate/queue artifacts when completed exports contain zero rows.")
    args = parser.parse_args()
    try:
        outputs = ingest(Path(args.input_dir), args.max_per_class, allow_empty=args.allow_empty)
    except PipelineError as exc:
        raise SystemExit(str(exc)) from exc
    print("Wrote broad-search candidate artifacts:")
    for key, path in outputs.items():
        print(f"- {key}: {path}")


if __name__ == "__main__":
    main()
