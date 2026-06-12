#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

from common import PipelineError, ensure_dir, read_json, read_jsonl, repo_path, write_json, write_jsonl


ALLOWED_TIERS = {"A_replayable", "B_high_confidence_incomplete"}


def _txs(value: Any) -> List[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    text = str(value)
    separator = ";" if ";" in text else ","
    return [item.strip().lower() for item in text.split(separator) if item.strip()]


def _row_txs(row: Dict[str, Any]) -> Set[str]:
    txs = set(_txs(row.get("impact_txs")))
    trigger = str(row.get("trigger_tx", "") or "").strip().lower()
    if trigger:
        txs.add(trigger)
    return txs


def _load_blizz_mvp_txs() -> Set[str]:
    txs: Set[str] = set()
    candidate_path = repo_path("artifacts", "blizz_luna_locator", "dune_candidates_full.jsonl")
    if candidate_path.exists():
        for row in read_jsonl(candidate_path):
            for field in (
                "luna_deposit_txs",
                "borrow_txs",
                "first_luna_deposit_tx",
                "first_borrow_tx",
            ):
                txs.update(_txs(row.get(field)))
    trace_path = repo_path("artifacts", "log_trace", "blizz_luna.jsonl")
    if trace_path.exists():
        for row in read_jsonl(trace_path):
            txs.update(_txs(row.get("tx_hash")))
            decoded = row.get("decoded") or {}
            if isinstance(decoded, dict):
                txs.update(_txs(decoded.get("all_deposit_txs")))
                txs.update(_txs(decoded.get("all_borrow_txs")))
    return {tx for tx in txs if tx}


def _mvp_txs(case_id: str) -> Set[str]:
    if case_id == "blizz_luna":
        txs = _load_blizz_mvp_txs()
    else:
        trace_path = repo_path("artifacts", "log_trace", f"{case_id}.jsonl")
        txs = set()
        if trace_path.exists():
            for row in read_jsonl(trace_path):
                txs.update(_txs(row.get("tx_hash")))
    if not txs:
        raise PipelineError(f"No local MVP tx evidence found for {case_id}")
    return txs


def _mvp_case_ids(mvp_case: str) -> List[str]:
    if mvp_case != "all":
        return [mvp_case]
    manifest = read_json(repo_path("artifacts", "dataset_manifest.json"))
    return [str(case["case"]) for case in manifest.get("cases", [])]


def _eligible_queue_rows(queue_rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        row
        for row in queue_rows
        if row.get("evidence_tier") in ALLOWED_TIERS
        and not row.get("already_materialized")
        and row.get("dataset_layer") != "seed_evaluation"
    ]


def _sort_for_minimal_mvp_download(row: Dict[str, Any], mvp_txs: Set[str]) -> tuple[int, float, int, str]:
    overlap = len(_row_txs(row) & mvp_txs)
    return (
        -overlap,
        -float(row.get("impact_usd_known") or 0),
        int(row.get("gate_sequence") or 10**9),
        str(row.get("candidate_id", "")),
    )


def _receipt_bundles(row: Dict[str, Any]) -> int:
    return int(row.get("estimated_total_rpc_requests") or 0)


def _rpc_requests(row: Dict[str, Any]) -> int:
    return _receipt_bundles(row) * 3


def _abi_requests(row: Dict[str, Any]) -> int:
    return int(row.get("estimated_abi_requests") or 0)


def build_preflight(
    *,
    candidates_path: Path,
    queue_path: Path,
    mvp_case: str,
    output_queue: Path,
    output_json: Path,
    output_report: Path,
    target_local_bundles: int | None = None,
    must_cover_mvp: bool = False,
    max_download_candidates: int | None = None,
) -> Dict[str, Any]:
    candidates = read_jsonl(candidates_path)
    queue_rows = read_jsonl(queue_path)
    eligible = _eligible_queue_rows(queue_rows)
    mvp_cases = _mvp_case_ids(mvp_case)
    mvp_txs_by_case = {case_id: _mvp_txs(case_id) for case_id in mvp_cases}
    all_mvp_txs = {tx for txs in mvp_txs_by_case.values() for tx in txs}
    selected = sorted(eligible, key=lambda row: _sort_for_minimal_mvp_download(row, all_mvp_txs))
    case_summaries: List[Dict[str, Any]] = []
    for case_id in mvp_cases:
        mvp_txs = mvp_txs_by_case[case_id]
        overlap_rows = [row for row in eligible if _row_txs(row) & mvp_txs]
        selected_for_case = [row for row in selected if _row_txs(row) & mvp_txs]
        selected_overlap_txs_for_case = sorted(
            {tx for row in selected_for_case for tx in (_row_txs(row) & mvp_txs)}
        )
        case_summaries.append(
            {
                "case": case_id,
                "seed_already_materialized": True,
                "mvp_known_tx_count": len(mvp_txs),
                "remote_overlap_candidate_count": len(overlap_rows),
                "selected_remote_candidate_count": len(selected_for_case),
                "selected_receipt_log_bundles": sum(_receipt_bundles(row) for row in selected_for_case),
                "selected_estimated_rpc_requests": sum(_rpc_requests(row) for row in selected_for_case),
                "selected_mvp_overlap_tx_count": len(selected_overlap_txs_for_case),
                "covered_by_seed_or_selected": True,
            }
        )
    selected_overlap_txs = sorted({tx for row in selected for tx in (_row_txs(row) & all_mvp_txs)})
    overlap_candidate_ids = {
        str(row.get("candidate_id", ""))
        for row in eligible
        if _row_txs(row) & all_mvp_txs
    }
    candidate_tx_refs = sum(1 + len(_txs(row.get("impact_txs"))) for row in candidates)
    candidate_unique_txs = sorted({tx for row in candidates for tx in _row_txs(row)})
    eligible_bundle_count = sum(_receipt_bundles(row) for row in eligible)
    selected_bundle_count = sum(_receipt_bundles(row) for row in selected)
    target_exceeded = target_local_bundles is not None and selected_bundle_count > target_local_bundles
    summary = {
        "scope": "read-only broad-search download-scope preflight",
        "contains_api_keys": False,
        "no_receipts_downloaded": True,
        "mvp_case": mvp_case,
        "mvp_cases": mvp_cases,
        "seed_evaluation_case_count": len(mvp_cases),
        "seed_already_materialized_case_count": len(case_summaries),
        "mvp_known_tx_count": len(all_mvp_txs),
        "remote_candidate_count": len(candidates),
        "remote_candidate_tx_reference_count": candidate_tx_refs,
        "remote_unique_candidate_tx_count": len(candidate_unique_txs),
        "eligible_queue_candidate_count": len(eligible),
        "eligible_queue_receipt_log_bundles": eligible_bundle_count,
        "eligible_queue_estimated_rpc_requests": sum(_rpc_requests(row) for row in eligible),
        "eligible_queue_estimated_abi_requests": sum(_abi_requests(row) for row in eligible),
        "mvp_overlap_candidate_count": len(overlap_candidate_ids),
        "selected_download_policy": "all_gate_eligible_candidates_no_topk",
        "deprecated_max_download_candidates_ignored": max_download_candidates,
        "target_local_bundles": target_local_bundles,
        "target_local_bundles_exceeded": target_exceeded,
        "requires_stricter_rules": target_exceeded,
        "selected_download_candidate_count": len(selected),
        "selected_download_receipt_log_bundles": selected_bundle_count,
        "selected_download_estimated_rpc_requests": sum(_rpc_requests(row) for row in selected),
        "selected_download_estimated_abi_requests": sum(_abi_requests(row) for row in selected),
        "selected_mvp_overlap_tx_count": len(selected_overlap_txs),
        "mvp_covered_by_selected": all(item["covered_by_seed_or_selected"] for item in case_summaries),
        "must_cover_mvp": must_cover_mvp,
        "must_cover_mvp_satisfied": (not must_cover_mvp) or all(item["covered_by_seed_or_selected"] for item in case_summaries),
        "remote_mvp_overlap_case_count": sum(1 for item in case_summaries if item["remote_overlap_candidate_count"] > 0),
        "case_summaries": case_summaries,
        "selected_candidate_ids": [row.get("candidate_id", "") for row in selected],
        "selected_trigger_txs": [row.get("trigger_tx", "") for row in selected],
        "selected_mvp_overlap_txs": selected_overlap_txs,
        "outputs": {
            "selected_queue": str(output_queue),
            "json": str(output_json),
            "report": str(output_report),
        },
        "safety": {
            "historical_index_rows_only": True,
            "no_open_ended_getlogs": True,
            "no_write_calls": True,
            "no_private_keys": True,
            "no_attack_simulation": True,
        },
    }
    write_jsonl(output_queue, selected)
    write_json(output_json, summary)
    ensure_dir(output_report.parent)
    output_report.write_text(_markdown(summary), encoding="utf-8")
    return summary


def _markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# Broad Download-Scope Preflight",
        "",
        "This preflight uses existing remote broad-search index rows and local seed evidence. It does not download receipts or execute chain calls.",
        "",
        f"- MVP case required in selected subset: `{summary['mvp_case']}`",
        f"- MVP covered by selected subset: `{summary['mvp_covered_by_selected']}`",
        f"- Seed/evaluation cases: `{summary.get('seed_evaluation_case_count', 1)}`",
        f"- Seed cases already materialized: `{summary.get('seed_already_materialized_case_count', 1)}`",
        f"- Remote candidate rows: `{summary['remote_candidate_count']}`",
        f"- Remote candidate tx/log references: `{summary['remote_candidate_tx_reference_count']}`",
        f"- Remote unique candidate tx references: `{summary['remote_unique_candidate_tx_count']}`",
        f"- Queue candidates eligible for local download: `{summary['eligible_queue_candidate_count']}`",
        f"- Eligible queue receipt/log bundles: `{summary['eligible_queue_receipt_log_bundles']}`",
        f"- Eligible queue estimated RPC requests: `{summary['eligible_queue_estimated_rpc_requests']}`",
        f"- Selected download candidates: `{summary['selected_download_candidate_count']}`",
        f"- Selected receipt/log bundles: `{summary['selected_download_receipt_log_bundles']}`",
        f"- Selected estimated RPC requests: `{summary['selected_download_estimated_rpc_requests']}`",
        f"- Selected estimated ABI requests: `{summary['selected_download_estimated_abi_requests']}`",
        f"- Target local bundles: `{summary.get('target_local_bundles')}`",
        f"- Target exceeded: `{summary.get('target_local_bundles_exceeded')}`",
        f"- Requires stricter rules: `{summary.get('requires_stricter_rules')}`",
        f"- MVP-overlap candidates in eligible queue: `{summary['mvp_overlap_candidate_count']}`",
        f"- MVP-overlap txs in selected subset: `{summary['selected_mvp_overlap_tx_count']}`",
        "",
        "## MVP Case Coverage",
        "",
        "| case | seed_materialized | remote_overlap_candidates | selected_remote_candidates | selected_bundles | selected_rpc |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in summary.get("case_summaries", []):
        lines.append(
            "| {case} | {seed} | {overlap} | {selected} | {bundles} | {rpc} |".format(
                case=item["case"],
                seed=item["seed_already_materialized"],
                overlap=item["remote_overlap_candidate_count"],
                selected=item["selected_remote_candidate_count"],
                bundles=item["selected_receipt_log_bundles"],
                rpc=item["selected_estimated_rpc_requests"],
            )
        )
    lines.extend(
        [
            "",
        "## Selected Candidates",
        "",
        "Selection is gate-only: every A/B candidate satisfying fixed evidence-closure predicates is included. If the count is too high, the next experiment should tighten the semantic gates instead of truncating this table.",
        "",
        "| candidate_id | trigger_tx |",
        "|---|---|",
        ]
    )
    for candidate_id, trigger_tx in zip(summary["selected_candidate_ids"], summary["selected_trigger_txs"]):
        lines.append(f"| `{candidate_id}` | `{trigger_tx}` |")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- Read-only historical index rows only.",
            "- No receipt download in this preflight.",
            "- No write calls, private keys, transaction simulation, or future target prediction.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preflight broad-search download scope and select a minimal MVP-covering local queue."
    )
    parser.add_argument("--candidates", default=str(repo_path("artifacts", "broad_search", "candidates_full.jsonl")))
    parser.add_argument("--queue", default=str(repo_path("artifacts", "broad_search", "materialization_queue.jsonl")))
    parser.add_argument("--mvp-case", default="blizz_luna")
    parser.add_argument(
        "--max-download-candidates",
        type=int,
        default=None,
        help="Deprecated compatibility flag; ignored because selection is gate-only.",
    )
    parser.add_argument("--target-local-bundles", type=int, default=None)
    parser.add_argument("--must-cover-mvp", action="store_true")
    parser.add_argument(
        "--output-queue",
        default=str(repo_path("artifacts", "broad_search", "materialization_queue_blizz_minimal.jsonl")),
    )
    parser.add_argument(
        "--output-json",
        default=str(repo_path("artifacts", "broad_search", "download_scope_preflight.json")),
    )
    parser.add_argument(
        "--output-report",
        default=str(repo_path("results", "broad_download_scope_preflight.md")),
    )
    args = parser.parse_args()
    try:
        summary = build_preflight(
            candidates_path=Path(args.candidates),
            queue_path=Path(args.queue),
            mvp_case=args.mvp_case,
            output_queue=Path(args.output_queue),
            output_json=Path(args.output_json),
            output_report=Path(args.output_report),
            target_local_bundles=args.target_local_bundles,
            must_cover_mvp=args.must_cover_mvp,
            max_download_candidates=args.max_download_candidates,
        )
    except PipelineError as exc:
        raise SystemExit(str(exc)) from exc
    print("Broad-search download-scope preflight:")
    print(f"- remote candidate rows: {summary['remote_candidate_count']}")
    print(f"- remote candidate tx/log references: {summary['remote_candidate_tx_reference_count']}")
    print(f"- eligible queue receipt/log bundles: {summary['eligible_queue_receipt_log_bundles']}")
    print(f"- selected receipt/log bundles: {summary['selected_download_receipt_log_bundles']}")
    print(f"- MVP covered by selected subset: {summary['mvp_covered_by_selected']}")


if __name__ == "__main__":
    main()
