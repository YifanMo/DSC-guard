#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from common import ensure_dir, read_json, repo_path, write_json, write_jsonl


def _read_trace(case_id: str) -> List[Dict[str, Any]]:
    path = repo_path("artifacts", "log_trace", f"{case_id}.jsonl")
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _iso_time(timestamp: Any) -> str:
    if timestamp in (None, ""):
        return "1970-01-01T00:00:00Z"
    return datetime.fromtimestamp(int(timestamp), timezone.utc).isoformat().replace("+00:00", "Z")


def _numeric(value: Any) -> float:
    if value in (None, "", "unknown"):
        return 0.0
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return 0.0


def _actor_count(trace: List[Dict[str, Any]]) -> int:
    actors = set()
    for record in trace:
        decoded = record.get("decoded") or {}
        for key in ("borrower", "supplier", "account", "attacker", "liquidator", "actor"):
            value = decoded.get(key)
            if value:
                actors.add(str(value).lower())
    return len(actors)


def _impact_usd(trace: List[Dict[str, Any]]) -> float:
    total = 0.0
    for record in trace:
        if record.get("event_type") != "BORROW":
            continue
        decoded = record.get("decoded") or {}
        total += _numeric(decoded.get("borrow_amount_usd"))
    return total


def _seed_candidate(case_item: Dict[str, Any], index: int) -> Dict[str, Any]:
    case_id = case_item["case"]
    trace = _read_trace(case_id)
    trigger_event = case_item.get("trigger_event")
    impact_events = set(case_item.get("impact_events") or [])
    trigger = next((record for record in trace if record.get("event_type") == trigger_event), trace[0] if trace else {})
    impact_records = [record for record in trace if record.get("event_type") in impact_events]
    impact_txs = sorted({record.get("tx_hash", "") for record in impact_records if record.get("tx_hash")})
    trigger_timestamp = int(trigger.get("block_timestamp") or 0)
    ordered_impacts = sorted(
        impact_records,
        key=lambda item: (item.get("block_number") or 0, item.get("transaction_index") or 0, item.get("log_index") or 0),
    )
    first_impact = next(
        (record for record in ordered_impacts if int(record.get("block_timestamp") or 0) >= trigger_timestamp),
        ordered_impacts[0] if ordered_impacts else {},
    )
    first_impact_timestamp = int(first_impact.get("block_timestamp") or 0)
    trigger_block = int(trigger.get("block_number") or 0)
    first_impact_block = int(first_impact.get("block_number") or 0)
    trigger_to_impact = max(0, first_impact_timestamp - trigger_timestamp) if first_impact_timestamp else 0
    evidence_tier = "A_replayable" if trigger and impact_records else "B_high_confidence_incomplete"
    source_quality = {
        "feed_binding_failure": "receipt_flow_decoded",
        "price_semantics_mismatch": "forum_canonical_tx_list",
        "price_composition_failure": "dune_decoded_event_plus_receipt",
        "freshness_handling_failure": "dune_or_local_decoded_event",
    }.get(case_item.get("failure_class"), "local_materialized_evidence")
    if case_id == "blueberry_faulty_oracle":
        source_quality = "postmortem_canonical_tx"

    return {
        "candidate_id": f"seed-{index:03d}-{case_id}",
        "dataset_layer": "seed_evaluation",
        "already_materialized": True,
        "case": case_id,
        "chain": case_item.get("chain", ""),
        "protocol": case_item.get("name", ""),
        "failure_class": case_item.get("failure_class", ""),
        "trigger_tx": trigger.get("tx_hash", ""),
        "trigger_block": trigger_block,
        "trigger_time": _iso_time(trigger.get("block_timestamp")),
        "trigger_year": datetime.fromtimestamp(trigger_timestamp or 0, timezone.utc).year,
        "affected_asset": (
            (trigger.get("decoded") or {}).get("asset")
            or (case_item.get("stale_oracle") or {}).get("asset")
            or case_item.get("semantic_dimension", "")
        ),
        "evidence_tier": evidence_tier,
        "closure_reason": "MVP seed case already has local replay trace and evidence artifacts.",
        "has_trigger": bool(trigger),
        "has_oracle_anomaly": bool(case_item.get("violated_constraints")),
        "has_lending_impact": bool(impact_records),
        "has_actor": _actor_count(trace) > 0,
        "has_temporal_order": bool(
            trigger
            and impact_records
            and (
                (first_impact_timestamp and first_impact_timestamp >= trigger_timestamp)
                or (first_impact_block and first_impact_block >= trigger_block)
            )
        ),
        "has_replayable_constraint": bool(trace),
        "trigger_to_impact_seconds": trigger_to_impact,
        "impact_tx_count": len(impact_txs),
        "impact_usd_known": _impact_usd(trace),
        "impact_txs": impact_txs,
        "source_quality": source_quality,
        "source_quality_rank": 0,
        "remote_query_id": "",
        "materialization_action": "none_seed_already_materialized",
        "estimated_trigger_receipts": 0,
        "estimated_impact_receipts": 0,
        "estimated_abi_requests": 0,
        "estimated_total_rpc_requests": 0,
    }


def build_seed_candidates() -> List[Dict[str, Any]]:
    manifest = read_json(repo_path("artifacts", "dataset_manifest.json"))
    return [_seed_candidate(case_item, index) for index, case_item in enumerate(manifest.get("cases", []), start=1)]


def render_seed_candidates() -> Dict[str, Path]:
    candidates = build_seed_candidates()
    summary = {
        "dataset_layer": "seed_evaluation",
        "seed_evaluation_count": len(candidates),
        "already_materialized_count": sum(1 for row in candidates if row.get("already_materialized")),
        "materialization_queue_count": 0,
        "estimated_queue_rpc_requests": 0,
        "cases": [row["case"] for row in candidates],
        "by_failure_class": {},
    }
    for row in candidates:
        failure_class = row["failure_class"]
        summary["by_failure_class"][failure_class] = summary["by_failure_class"].get(failure_class, 0) + 1
    outputs = {
        "candidates": repo_path("artifacts", "broad_search", "seed_candidates.jsonl"),
        "summary": repo_path("artifacts", "broad_search", "seed_candidate_summary.json"),
        "report": repo_path("results", "broad_seed_candidates.md"),
    }
    write_jsonl(outputs["candidates"], candidates)
    write_json(outputs["summary"], summary)
    ensure_dir(outputs["report"].parent)
    lines = [
        "# Broad Search Seed Candidates",
        "",
        "These MVP cases are fixed seed/evaluation rows. They are already materialized locally and do not enter the broad-search download queue.",
        "",
        f"- Seed evaluation count: `{summary['seed_evaluation_count']}`",
        f"- Already materialized: `{summary['already_materialized_count']}`",
        f"- Additional RPC requests: `{summary['estimated_queue_rpc_requests']}`",
        "",
        "| candidate_id | case | chain | failure_class | evidence_tier | impact_tx_count |",
        "|---|---|---|---|---|---:|",
    ]
    for row in candidates:
        lines.append(
            f"| {row['candidate_id']} | {row['case']} | {row['chain']} | {row['failure_class']} | {row['evidence_tier']} | {row['impact_tx_count']} |"
        )
    outputs["report"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Render seed/evaluation candidates from local MVP evidence.")
    parser.parse_args()
    outputs = render_seed_candidates()
    print("Wrote broad-search seed candidates:")
    for key, path in outputs.items():
        print(f"- {key}: {path}")


if __name__ == "__main__":
    main()
