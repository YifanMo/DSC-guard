#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from common import PipelineError, ensure_dir, load_env, repo_path, write_json
from ingest_broad_search_results import ingest
from preflight_broad_download_scope import build_preflight
from render_broad_search_queries import parse_chains, render_queries
from run_broad_dune_queries import (
    _execute_sql,
    _fetch_all_rows,
    _poll_execution,
    build_shards,
    run_shards,
)


DEFAULT_START = "2022-01-01"
DEFAULT_END = "2026-05-12"
DEFAULT_CHAINS = "ethereum,scroll,base,bnb,avalanche"
DEFAULT_RULES = "feed_binding_failure,price_composition_failure,freshness_handling_failure"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _date_key(value: str) -> str:
    return value.replace("-", "")


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _year_windows(start: str, end: str) -> List[tuple[str, str]]:
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    windows: List[tuple[str, str]] = []
    current = start_date
    while current <= end_date:
        window_end = min(date(current.year, 12, 31), end_date)
        windows.append((current.isoformat(), window_end.isoformat()))
        current = window_end + timedelta(days=1)
    return windows


def _month_windows(start: str, end: str) -> List[tuple[str, str]]:
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    windows: List[tuple[str, str]] = []
    current = start_date
    while current <= end_date:
        if current.month == 12:
            month_end = date(current.year, 12, 31)
        else:
            month_end = date(current.year, current.month + 1, 1) - timedelta(days=1)
        window_end = min(month_end, end_date)
        windows.append((current.isoformat(), window_end.isoformat()))
        current = window_end + timedelta(days=1)
    return windows


def _week_windows(start: str, end: str) -> List[tuple[str, str]]:
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    windows: List[tuple[str, str]] = []
    current = start_date
    while current <= end_date:
        window_end = min(current + timedelta(days=6), end_date)
        windows.append((current.isoformat(), window_end.isoformat()))
        current = window_end + timedelta(days=1)
    return windows


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _rule_list(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def story_scope_count_sql(start: str, end: str, chains: Iterable[str]) -> str:
    return f"""-- Story-scope count-only query.
-- Counts the remote historical log/transaction surface for the MVP chains.
-- This query emits compact counts only; it does not download receipts or logs.
WITH params AS (
  SELECT DATE '{start}' AS start_date, DATE '{end}' AS end_date
),
scope_chains AS (
  SELECT chain
  FROM (VALUES {', '.join(f"('{chain}')" for chain in parse_chains(chains))}) AS t(chain)
),
log_counts AS (
  SELECT
    l.blockchain AS chain,
    COUNT(*) AS raw_log_count,
    COUNT(DISTINCT l.tx_hash) AS tx_with_logs_count,
    COUNT(DISTINCT l.contract_address) AS log_contract_count
  FROM evms.logs l
  JOIN scope_chains c ON c.chain = l.blockchain
  WHERE l.block_date BETWEEN (SELECT start_date FROM params) AND (SELECT end_date FROM params)
  GROUP BY 1
),
transaction_counts AS (
  SELECT
    tx.blockchain AS chain,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT tx."to") AS touched_contract_count
  FROM evms.transactions tx
  JOIN scope_chains c ON c.chain = tx.blockchain
  WHERE tx.block_date BETWEEN (SELECT start_date FROM params) AND (SELECT end_date FROM params)
  GROUP BY 1
)
SELECT
  c.chain,
  DATE '{start}' AS start_date,
  DATE '{end}' AS end_date,
  COALESCE(l.raw_log_count, 0) AS raw_log_count,
  COALESCE(l.tx_with_logs_count, 0) AS tx_with_logs_count,
  COALESCE(l.log_contract_count, 0) AS log_contract_count,
  COALESCE(t.transaction_count, 0) AS transaction_count,
  COALESCE(t.touched_contract_count, 0) AS touched_contract_count
FROM scope_chains c
LEFT JOIN log_counts l ON l.chain = c.chain
LEFT JOIN transaction_counts t ON t.chain = c.chain
ORDER BY c.chain;
"""


def _write_rows(path: Path, rows: List[Dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps({"rows": rows}, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def execute_scope_counts(
    sql: str,
    *,
    output_dir: Path,
    performance: str,
    poll_interval: int,
    timeout_seconds: int,
    no_credit_limit: bool,
    max_execution_credits: Optional[float],
    page_size: int,
) -> Dict[str, Any]:
    env = load_env()
    api_key = env.get("DUNE_MCP_KEY") or env.get("DUNE_API_KEY")
    if not api_key:
        raise PipelineError("Missing DUNE_MCP_KEY or DUNE_API_KEY in .env/environment")
    ensure_dir(output_dir)
    manifest_path = output_dir / "scope_counts_manifest.json"
    started = time.time()
    execution = _execute_sql(sql, api_key, performance)
    execution_id = execution.get("execution_id")
    if not execution_id:
        raise PipelineError(f"Dune scope count query did not return execution_id: {execution}")
    manifest: Dict[str, Any] = {
        "dataset": "story_scope_remote_counts",
        "status": "submitted",
        "execution_id": execution_id,
        "performance": performance,
        "submitted_at": _utc_now(),
        "contains_api_keys": False,
        "credit_guard": "disabled_by_user" if no_credit_limit else "enabled",
    }
    write_json(manifest_path, manifest)
    status = _poll_execution(
        execution_id,
        api_key,
        poll_interval=poll_interval,
        timeout_seconds=timeout_seconds,
        max_execution_credits=None if no_credit_limit else max_execution_credits,
    )
    manifest.update(
        {
            "state": status.get("state"),
            "execution_cost_credits": status.get("execution_cost_credits"),
            "duration_seconds": round(time.time() - started, 3),
            "status_payload": {key: value for key, value in status.items() if key != "result"},
        }
    )
    if status.get("state") != "QUERY_STATE_COMPLETED":
        manifest["status"] = "cancelled" if status.get("state") == "QUERY_STATE_CANCELLED" else "failed"
        write_json(manifest_path, manifest)
        return manifest
    rows, payload = _fetch_all_rows(execution_id, api_key, page_size=page_size)
    _write_rows(output_dir / "story_scope_counts.json", rows)
    manifest.update(
        {
            "status": "completed",
            "row_count": len(rows),
            "metadata": (payload.get("result") or {}).get("metadata") or {},
        }
    )
    write_json(manifest_path, manifest)
    return manifest


def execute_scope_count_shards(
    *,
    start: str,
    end: str,
    chains: List[str],
    output_dir: Path,
    performance: str,
    poll_interval: int,
    timeout_seconds: int,
    no_credit_limit: bool,
    max_execution_credits: Optional[float],
    page_size: int,
    split_by: str = "year",
) -> Dict[str, Any]:
    ensure_dir(output_dir)
    rows: List[Dict[str, Any]] = []
    shard_manifests: List[Dict[str, Any]] = []
    stop_reason = ""
    if split_by == "week":
        windows = _week_windows(start, end)
    elif split_by == "month":
        windows = _month_windows(start, end)
    else:
        windows = _year_windows(start, end)
    for chain in parse_chains(chains):
        if stop_reason:
            break
        for window_start, window_end in windows:
            if stop_reason:
                break
            if split_by == "week":
                time_key = f"{window_start}_{window_end}".replace("-", "_")
            elif split_by == "month":
                time_key = window_start[:7].replace("-", "_")
            else:
                time_key = window_start[:4]
            shard_dir = output_dir / f"{time_key}_{chain}"
            sql = story_scope_count_sql(window_start, window_end, [chain])
            ensure_dir(shard_dir)
            (shard_dir / "query.sql").write_text(sql, encoding="utf-8")
            manifest = execute_scope_counts(
                sql,
                output_dir=shard_dir,
                performance=performance,
                poll_interval=poll_interval,
                timeout_seconds=timeout_seconds,
                no_credit_limit=no_credit_limit,
                max_execution_credits=max_execution_credits,
                page_size=page_size,
            )
            manifest["shard_id"] = f"{time_key}_{chain}_scope_counts"
            manifest["chain"] = chain
            manifest["start"] = window_start
            manifest["end"] = window_end
            shard_manifests.append(manifest)
            shard_rows_payload = _read_json(shard_dir / "story_scope_counts.json")
            rows.extend(shard_rows_payload.get("rows", []) if isinstance(shard_rows_payload, dict) else [])
            if manifest.get("status") != "completed":
                stop_reason = f"scope_count_shard_{manifest.get('status', 'not_completed')}"
    _write_rows(output_dir / "story_scope_counts.json", rows)
    summary = {
        "dataset": "story_scope_remote_counts_sharded",
        "status": "completed" if all(item.get("status") == "completed" for item in shard_manifests) else "partial",
        "shard_count": len(shard_manifests),
        "completed_count": sum(1 for item in shard_manifests if item.get("status") == "completed"),
        "cancelled_count": sum(1 for item in shard_manifests if item.get("status") == "cancelled"),
        "failed_count": sum(1 for item in shard_manifests if item.get("status") == "failed"),
        "row_count": len(rows),
        "execution_cost_credits": sum(float(item.get("execution_cost_credits") or 0) for item in shard_manifests),
        "contains_api_keys": False,
        "credit_guard": "disabled_by_user" if no_credit_limit else "enabled",
        "split_by": split_by,
        "shards": shard_manifests,
        "stop_reason": stop_reason,
    }
    write_json(output_dir / "scope_counts_manifest.json", summary)
    return summary


def _recommendations(download_summary: Dict[str, Any], target_local_bundles: int) -> List[str]:
    selected_bundles = int(download_summary.get("selected_download_receipt_log_bundles") or 0)
    if selected_bundles <= target_local_bundles:
        return ["Current evidence gates fit the target local bundle budget; do not truncate candidates."]
    return [
        "Do not apply top-k. Tighten evidence gates and rerun count-only preflight.",
        "Promote A_replayable-only materialization for the oversized class.",
        "Require decoded protocol event evidence instead of raw transfer heuristic for oversized B-tier candidates.",
        "Require same-protocol supply->borrow or liquidation closure with a first causal impact transaction.",
        "For freshness candidates, require the latest prior stale/lower-bound oracle episode before impact.",
    ]


def _write_markdown_reports(
    *,
    output_dir: Path,
    manifest: Dict[str, Any],
    download_summary: Dict[str, Any],
    target_local_bundles: int,
) -> None:
    counts = _read_json(output_dir / "scope_counts" / "story_scope_counts.json")
    count_rows = counts.get("rows", []) if isinstance(counts, dict) else []
    count_lines = [
        "# Story Scope Counts",
        "",
        "This report is count-only remote coverage. It does not download full logs or receipts.",
        "",
        f"- Chains: `{', '.join(manifest['chains'])}`",
        f"- Time range: `{manifest['start']}` to `{manifest['end']}`",
        f"- Dune execution: `{manifest.get('scope_counts', {}).get('status', 'not_run')}`",
        "",
        "| chain | raw_log_count | tx_with_logs_count | transaction_count |",
        "|---|---:|---:|---:|",
    ]
    for row in count_rows:
        count_lines.append(
            f"| {row.get('chain', '')} | {row.get('raw_log_count', 0)} | {row.get('tx_with_logs_count', 0)} | {row.get('transaction_count', 0)} |"
        )
    if not count_rows:
        count_lines.append("| not_run | 0 | 0 | 0 |")
    (repo_path("results", "story_scope_counts.md")).write_text("\n".join(count_lines) + "\n", encoding="utf-8")

    recommendations = _recommendations(download_summary, target_local_bundles)
    plan_lines = [
        "# Story Scope Download Plan",
        "",
        "Local download scope is controlled by evidence-closure gates, not top-k ranking or weighted scores.",
        "",
        f"- Target local bundles: `{target_local_bundles}`",
        f"- Gate-selected candidates: `{download_summary.get('selected_download_candidate_count', 0)}`",
        f"- Gate-selected receipt/log bundles: `{download_summary.get('selected_download_receipt_log_bundles', 0)}`",
        f"- Estimated RPC requests: `{download_summary.get('selected_download_estimated_rpc_requests', 0)}`",
        f"- Requires stricter rules: `{download_summary.get('requires_stricter_rules', False)}`",
        f"- MVP covered by seed or selected candidates: `{download_summary.get('mvp_covered_by_selected', False)}`",
        "",
        "## Rule Adjustment Recommendations",
        "",
    ]
    plan_lines.extend(f"- {item}" for item in recommendations)
    plan_lines.extend(
        [
            "",
            "## Safety Boundary",
            "",
            "- Read-only historical Dune index and known receipt planning only.",
            "- No chain writes, private keys, write-method calls, attack simulation, or future target prediction.",
            "",
        ]
    )
    (repo_path("results", "story_scope_download_plan.md")).write_text("\n".join(plan_lines), encoding="utf-8")

    detection_lines = [
        "# Story Detection Summary",
        "",
        "The broad-search optimization dataset is combined with the already materialized MVP seed/evaluation set.",
        "",
        "- MVP seed cases remain the detection ground truth for the current paper artifact.",
        "- Broad candidates are downloaded only after evidence-closure gates pass.",
        "- Detection output should be refreshed with `python scripts/reproduce_mvp.py --mode verify` after any local materialization run.",
        "",
    ]
    (repo_path("results", "story_detection_summary.md")).write_text("\n".join(detection_lines), encoding="utf-8")


def run_auto_tune(
    *,
    start: str,
    end: str,
    chains: List[str],
    rules: List[str],
    output_dir: Path,
    execute_dune: bool,
    execute_candidates: bool,
    count_only: bool,
    no_credit_limit: bool,
    performance: str,
    split_by: str,
    scope_split_by: str,
    resume: bool,
    target_local_bundles: int,
    candidate_export_dir: Optional[Path],
    page_size: int,
    poll_interval: int,
    timeout_seconds: int,
    max_execution_credits: Optional[float],
    max_total_credits: Optional[float],
) -> Dict[str, Any]:
    ensure_dir(output_dir)
    sql_dir = output_dir / "sql"
    ensure_dir(sql_dir)
    scope_sql = story_scope_count_sql(start, end, chains)
    (sql_dir / "00_story_scope_counts.sql").write_text(scope_sql, encoding="utf-8")
    for name, sql in render_queries(start, end, chains).items():
        (sql_dir / name).write_text(sql, encoding="utf-8")

    manifest: Dict[str, Any] = {
        "experiment": "broad_search_auto_tune",
        "scope": "remote count/index search plus gate-only local evidence planning",
        "start": start,
        "end": end,
        "chains": parse_chains(chains),
        "rules": rules,
        "target_local_bundles": target_local_bundles,
        "execute_dune": execute_dune,
        "execute_candidates": execute_candidates,
        "count_only": count_only,
        "no_credit_limit": no_credit_limit,
        "contains_api_keys": False,
        "safety": {
            "historical_read_only": True,
            "no_write_calls": True,
            "no_private_keys": True,
            "no_attack_simulation": True,
            "no_future_target_prediction": True,
            "no_topk_dataset_truncation": True,
        },
        "created_at": _utc_now(),
    }

    if execute_dune:
        scope_result = execute_scope_count_shards(
            start=start,
            end=end,
            chains=parse_chains(chains),
            output_dir=output_dir / "scope_counts",
            performance=performance,
            poll_interval=poll_interval,
            timeout_seconds=timeout_seconds,
            no_credit_limit=no_credit_limit,
            max_execution_credits=max_execution_credits,
            page_size=page_size,
            split_by=scope_split_by,
        )
        manifest["scope_counts"] = scope_result
        if count_only:
            manifest["preflight_counts"] = {"status": "skipped_count_only"}
        elif scope_result.get("status") == "completed":
            shards = build_shards(start, end, parse_chains(chains), split_by, rules)
            preflight = run_shards(
                shards,
                output_dir=output_dir / "preflight_counts",
                performance=performance,
                resume=resume,
                dry_run=False,
                page_size=page_size,
                poll_interval=poll_interval,
                timeout_seconds=timeout_seconds,
                max_execution_credits=max_execution_credits,
                max_total_credits=max_total_credits,
                no_credit_limit=no_credit_limit,
                preflight_counts=True,
                stop_on_cancel=True,
            )
            manifest["preflight_counts"] = preflight
        else:
            manifest["preflight_counts"] = {
                "status": "skipped_after_scope_count",
                "reason": scope_result.get("stop_reason") or "scope_count_not_completed",
            }
    else:
        shards = build_shards(start, end, parse_chains(chains), split_by, rules)
        preflight = run_shards(
            shards,
            output_dir=output_dir / "preflight_counts",
            performance=performance,
            resume=False,
            dry_run=True,
            page_size=page_size,
            poll_interval=poll_interval,
            timeout_seconds=timeout_seconds,
            max_execution_credits=max_execution_credits,
            max_total_credits=max_total_credits,
            no_credit_limit=no_credit_limit,
            preflight_counts=True,
            stop_on_cancel=True,
        )
        manifest["preflight_counts"] = preflight
        manifest["scope_counts"] = {"status": "dry_run", "sql_path": str(sql_dir / "00_story_scope_counts.sql")}

    index_dir = output_dir / "local_index"
    candidate_run_dir = output_dir / "candidate_run"
    preflight_status = (manifest.get("preflight_counts") or {}).get("status")
    if execute_candidates and preflight_status not in {"skipped_after_scope_count", "skipped_count_only"}:
        candidate_run = run_shards(
            build_shards(start, end, parse_chains(chains), split_by, rules),
            output_dir=candidate_run_dir,
            performance=performance,
            resume=resume,
            dry_run=False,
            page_size=page_size,
            poll_interval=poll_interval,
            timeout_seconds=timeout_seconds,
            max_execution_credits=max_execution_credits,
            max_total_credits=max_total_credits,
            no_credit_limit=no_credit_limit,
            preflight_counts=False,
            stop_on_cancel=True,
        )
        manifest["candidate_run"] = candidate_run
        candidate_export_dir = candidate_run_dir
    elif execute_candidates:
        manifest["candidate_run"] = {
            "status": "skipped_after_preflight",
            "reason": (manifest.get("preflight_counts") or {}).get("reason", "preflight_not_completed"),
        }
    else:
        manifest["candidate_run"] = {"status": "not_run"}

    if candidate_export_dir is not None:
        outputs = ingest(candidate_export_dir, output_dir=index_dir, allow_empty=True)
        manifest["candidate_ingest"] = {key: str(value) for key, value in outputs.items()}
        candidates_path = outputs["candidates"]
        queue_path = outputs["queue"]
    else:
        candidates_path = repo_path("artifacts", "broad_search", "candidates_full.jsonl")
        queue_path = repo_path("artifacts", "broad_search", "materialization_queue.jsonl")
        manifest["candidate_ingest"] = {"status": "using_existing_artifacts", "candidates": str(candidates_path), "queue": str(queue_path)}

    download_summary = build_preflight(
        candidates_path=candidates_path,
        queue_path=queue_path,
        mvp_case="all",
        output_queue=output_dir / "materialization_queue_gate_all.jsonl",
        output_json=output_dir / "download_scope_preflight.json",
        output_report=output_dir / "download_scope_preflight.md",
        target_local_bundles=target_local_bundles,
        must_cover_mvp=True,
    )
    manifest["download_scope_preflight"] = download_summary
    write_json(output_dir / "auto_tune_manifest.json", manifest)
    write_json(repo_path("artifacts", "broad_search", "story_scope_counts.json"), {"manifest": manifest})
    _write_markdown_reports(
        output_dir=output_dir,
        manifest=manifest,
        download_summary=download_summary,
        target_local_bundles=target_local_bundles,
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-tune broad-search rules with count-only Dune preflight and gate-only local planning.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--chains", default=DEFAULT_CHAINS)
    parser.add_argument("--rules", default=DEFAULT_RULES)
    parser.add_argument("--output-dir", default=str(repo_path("artifacts", "broad_search", "auto_tune_story_scope")))
    parser.add_argument("--execute-dune", action="store_true")
    parser.add_argument("--execute-candidates", action="store_true", help="After preflight, execute broad candidate shards and ingest their compact rows.")
    parser.add_argument("--count-only", action="store_true", help="Run remote scope counts only and skip rule preflight/candidate execution.")
    parser.add_argument("--no-credit-limit", action="store_true")
    parser.add_argument("--performance", choices=["small", "medium", "large"], default="medium")
    parser.add_argument("--split-by", default="month,chain,rule")
    parser.add_argument("--scope-split-by", choices=["year", "month", "week"], default="year")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--target-local-bundles", type=int, default=3000)
    parser.add_argument("--candidate-export-dir", default="")
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--poll-interval", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--max-execution-credits", type=float, default=None)
    parser.add_argument("--max-total-credits", type=float, default=None)
    args = parser.parse_args()
    try:
        result = run_auto_tune(
            start=args.start,
            end=args.end,
            chains=parse_chains(args.chains),
            rules=_rule_list(args.rules),
            output_dir=Path(args.output_dir),
            execute_dune=args.execute_dune,
            execute_candidates=args.execute_candidates,
            count_only=args.count_only,
            no_credit_limit=args.no_credit_limit,
            performance=args.performance,
            split_by=args.split_by,
            scope_split_by=args.scope_split_by,
            resume=args.resume,
            target_local_bundles=args.target_local_bundles,
            candidate_export_dir=Path(args.candidate_export_dir) if args.candidate_export_dir else None,
            page_size=args.page_size,
            poll_interval=args.poll_interval,
            timeout_seconds=args.timeout_seconds,
            max_execution_credits=args.max_execution_credits,
            max_total_credits=args.max_total_credits,
        )
    except PipelineError as exc:
        raise SystemExit(str(exc)) from exc
    print("Broad-search auto-tune summary:")
    print(f"- execute dune: {result['execute_dune']}")
    print(f"- execute candidates: {result['execute_candidates']}")
    print(f"- count only: {result['count_only']}")
    print(f"- chains: {', '.join(result['chains'])}")
    print(f"- rules: {', '.join(result['rules'])}")
    print(f"- target local bundles: {result['target_local_bundles']}")
    print(f"- output: {Path(args.output_dir)}")


if __name__ == "__main__":
    main()
