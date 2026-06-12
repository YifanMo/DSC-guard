#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from common import PipelineError, ensure_dir, load_env, repo_path, write_json
from render_broad_search_queries import (
    DEFAULT_CHAINS,
    feed_binding_preflight_count_sql,
    feed_binding_sql,
    freshness_preflight_count_sql,
    freshness_sql,
    parse_chains,
    price_composition_preflight_count_sql,
    price_composition_sql,
)


DUNE_API_BASE = "https://api.dune.com/api/v1"
RULES = {
    "feed_binding_failure": feed_binding_sql,
    "price_composition_failure": price_composition_sql,
    "freshness_handling_failure": freshness_sql,
}
PREFLIGHT_RULES = {
    "feed_binding_failure": feed_binding_preflight_count_sql,
    "price_composition_failure": price_composition_preflight_count_sql,
    "freshness_handling_failure": freshness_preflight_count_sql,
}
STAGE_BUDGETS = {
    "calibration": {"max_execution_credits": 5.0, "max_total_credits": 50.0},
    "pilot": {"max_execution_credits": 10.0, "max_total_credits": 150.0},
    "full": {"max_execution_credits": 20.0, "max_total_credits": 1200.0},
}
TERMINAL_STATES = {
    "QUERY_STATE_COMPLETED",
    "QUERY_STATE_FAILED",
    "QUERY_STATE_CANCELLED",
    "QUERY_STATE_EXPIRED",
}


@dataclass(frozen=True)
class DuneShard:
    shard_id: str
    failure_class: str
    chain: str
    start: str
    end: str


def _date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _year_windows(start: str, end: str) -> List[tuple[str, str]]:
    start_date = _date(start)
    end_date = _date(end)
    if end_date < start_date:
        raise PipelineError(f"End date {end} is earlier than start date {start}")
    windows: List[tuple[str, str]] = []
    current = start_date
    while current <= end_date:
        year_end = date(current.year, 12, 31)
        window_end = min(year_end, end_date)
        windows.append((current.isoformat(), window_end.isoformat()))
        current = window_end + timedelta(days=1)
    return windows


def _month_windows(start: str, end: str) -> List[tuple[str, str]]:
    start_date = _date(start)
    end_date = _date(end)
    if end_date < start_date:
        raise PipelineError(f"End date {end} is earlier than start date {start}")
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


def build_shards(
    start: str,
    end: str,
    chains: Iterable[str],
    split_by: str = "year,chain,rule",
    rules: Optional[Iterable[str]] = None,
) -> List[DuneShard]:
    split_parts = {part.strip() for part in split_by.split(",") if part.strip()}
    if split_parts not in ({"year", "chain", "rule"}, {"month", "chain", "rule"}):
        raise PipelineError("Only --split-by year,chain,rule or month,chain,rule is supported for Broad Search Dataset v1")
    parsed_chains = parse_chains(chains)
    selected_rules = [rule for rule in (rules or RULES.keys()) if rule]
    unknown_rules = sorted(set(selected_rules) - set(RULES))
    if unknown_rules:
        raise PipelineError(f"Unknown broad-search rule(s): {', '.join(unknown_rules)}")
    windows = _month_windows(start, end) if "month" in split_parts else _year_windows(start, end)
    shards: List[DuneShard] = []
    for rule in selected_rules:
        for window_start, window_end in windows:
            time_key = window_start[:7] if "month" in split_parts else window_start[:4]
            for chain in parsed_chains:
                shard_id = f"{time_key}_{chain}_{rule}".replace("-", "_")
                shards.append(
                    DuneShard(
                        shard_id=shard_id,
                        failure_class=rule,
                        chain=chain,
                        start=window_start,
                        end=window_end,
                    )
                )
    return shards


def build_stage_shards(stage: str, *, start: str, end: str, chains: Iterable[str], split_by: str, rules: Iterable[str]) -> List[DuneShard]:
    selected_rules = [rule for rule in rules if rule]
    if stage == "calibration":
        return [
            DuneShard("calibration_scroll_2024_07_feed_binding_failure", "feed_binding_failure", "scroll", "2024-07-01", "2024-07-31"),
            DuneShard("calibration_ethereum_2024_01_feed_binding_failure", "feed_binding_failure", "ethereum", "2024-01-01", "2024-01-31"),
            DuneShard("calibration_base_2024_01_price_composition_failure", "price_composition_failure", "base", "2024-01-01", "2024-01-31"),
            DuneShard("calibration_base_2025_01_price_composition_failure", "price_composition_failure", "base", "2025-01-01", "2025-01-31"),
            DuneShard("calibration_bnb_2022_05_freshness_handling_failure", "freshness_handling_failure", "bnb", "2022-05-01", "2022-05-31"),
            DuneShard("calibration_avalanche_c_2022_05_freshness_handling_failure", "freshness_handling_failure", "avalanche_c", "2022-05-01", "2022-05-31"),
        ]
    if stage == "pilot":
        shards: List[DuneShard] = []
        pilot_chains = parse_chains(["ethereum", "scroll", "base", "bnb", "avalanche_c"])
        for rule in selected_rules:
            for year in ("2022", "2024"):
                for chain in pilot_chains:
                    shards.append(DuneShard(f"pilot_{year}_{chain}_{rule}", rule, chain, f"{year}-01-01", f"{year}-12-31"))
        return shards
    if stage == "full":
        return build_shards(start, end, chains, split_by, selected_rules)
    raise PipelineError(f"Unknown broad-search stage: {stage}")


def render_shard_sql(shard: DuneShard, *, preflight_counts: bool = False) -> str:
    if preflight_counts:
        if shard.failure_class not in PREFLIGHT_RULES:
            raise PipelineError(f"Preflight counts are not implemented for {shard.failure_class}")
        return PREFLIGHT_RULES[shard.failure_class](shard.start, shard.end, [shard.chain])
    return RULES[shard.failure_class](shard.start, shard.end, [shard.chain])


def _api_request(
    method: str,
    path: str,
    api_key: str,
    *,
    body: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 120,
) -> Dict[str, Any]:
    url = f"{DUNE_API_BASE}{path}"
    if params:
        clean_params = {key: value for key, value in params.items() if value is not None}
        if clean_params:
            url += "?" + urllib.parse.urlencode(clean_params)
    data = None
    headers = {
        "X-Dune-Api-Key": api_key,
        "Content-Type": "application/json",
        "User-Agent": "dsc-guard-mvp/0.1",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        raise PipelineError(f"Dune API {method} {path} failed with HTTP {exc.code}: {payload}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PipelineError(f"Dune API {method} {path} network error: {exc}") from exc


def _execute_sql(sql: str, api_key: str, performance: str) -> Dict[str, Any]:
    return _api_request("POST", "/sql/execute", api_key, body={"sql": sql, "performance": performance})


def _execution_status(execution_id: str, api_key: str) -> Dict[str, Any]:
    return _api_request("GET", f"/execution/{execution_id}/status", api_key)


def _execution_results(execution_id: str, api_key: str, *, limit: int, offset: int) -> Dict[str, Any]:
    return _api_request(
        "GET",
        f"/execution/{execution_id}/results",
        api_key,
        params={"limit": limit, "offset": offset},
    )


def _cancel_execution(execution_id: str, api_key: str) -> Dict[str, Any]:
    return _api_request("POST", f"/execution/{execution_id}/cancel", api_key)


def _poll_execution(
    execution_id: str,
    api_key: str,
    *,
    poll_interval: int,
    timeout_seconds: int,
    max_execution_credits: Optional[float] = None,
) -> Dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_status: Dict[str, Any] = {}
    last_error = ""
    while time.time() <= deadline:
        try:
            last_status = _execution_status(execution_id, api_key)
        except PipelineError as exc:
            last_error = str(exc)
            time.sleep(poll_interval)
            continue
        state = last_status.get("state", "")
        cost = last_status.get("execution_cost_credits")
        if max_execution_credits is not None and cost is not None and float(cost) > max_execution_credits:
            cancel_payload = _cancel_execution(execution_id, api_key)
            last_status["state"] = "QUERY_STATE_CANCELLED"
            last_status["is_execution_finished"] = True
            last_status["cancel_reason"] = "max_execution_credits_exceeded"
            last_status["cancel_payload"] = cancel_payload
            return last_status
        if last_status.get("is_execution_finished") or state in TERMINAL_STATES:
            return last_status
        time.sleep(poll_interval)
    timeout_status = last_status or {"execution_id": execution_id}
    timeout_status["state"] = timeout_status.get("state") or "TIMEOUT"
    timeout_status["is_execution_finished"] = False
    if last_error:
        timeout_status["last_poll_error"] = last_error
    return timeout_status


def _fetch_all_rows(execution_id: str, api_key: str, *, page_size: int) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0
    final_payload: Dict[str, Any] = {}
    while True:
        payload = _execution_results(execution_id, api_key, limit=page_size, offset=offset)
        final_payload = payload
        page_rows = ((payload.get("result") or {}).get("rows") or [])
        rows.extend(page_rows)
        next_offset = payload.get("next_offset")
        if next_offset is None:
            break
        offset = int(next_offset)
    return rows, final_payload


def _write_rows_json(path: Path, rows: List[Dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps({"rows": rows}, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_rows_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    import csv

    ensure_dir(path.parent)
    headers = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _completed_manifest(manifest_path: Path, result_json: Path) -> bool:
    if not manifest_path.exists() or not result_json.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return manifest.get("status") == "completed" and bool(manifest.get("execution_id"))


def _resumable_execution_id(manifest_path: Path, result_json: Path) -> Optional[str]:
    if not manifest_path.exists() or result_json.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    execution_id = manifest.get("execution_id")
    state = manifest.get("state")
    if execution_id and state in {"QUERY_STATE_SUBMITTED", "QUERY_STATE_PENDING", "QUERY_STATE_EXECUTING", "TIMEOUT"}:
        return str(execution_id)
    return None


def _terminal_noncompleted_manifest(manifest_path: Path) -> Optional[Dict[str, Any]]:
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if manifest.get("status") in {"failed", "cancelled"}:
        return manifest
    return None


def _shard_paths(output_dir: Path, shard: DuneShard) -> Dict[str, Path]:
    shard_dir = output_dir / shard.shard_id
    return {
        "dir": shard_dir,
        "sql": shard_dir / "query.sql",
        "manifest": shard_dir / "manifest.json",
        "json": shard_dir / "result.json",
        "csv": shard_dir / "result.csv",
    }


def run_shards(
    shards: List[DuneShard],
    *,
    output_dir: Path,
    performance: str,
    resume: bool,
    dry_run: bool,
    page_size: int,
    poll_interval: int,
    timeout_seconds: int,
    max_shards: Optional[int] = None,
    max_execution_credits: Optional[float] = None,
    max_total_credits: Optional[float] = None,
    no_credit_limit: bool = False,
    rerun_failed: bool = False,
    preflight_counts: bool = False,
    stop_on_cancel: bool = False,
) -> Dict[str, Any]:
    env = load_env()
    api_key = env.get("DUNE_MCP_KEY") or env.get("DUNE_API_KEY")
    selected = shards[:max_shards] if max_shards is not None else shards
    ensure_dir(output_dir)
    run_manifest: Dict[str, Any] = {
        "dataset": "broad_search_preflight_counts" if preflight_counts else "broad_search_dataset_v1",
        "preflight_counts": preflight_counts,
        "dry_run": dry_run,
        "performance": performance,
        "output_dir": str(output_dir),
        "shard_count": len(selected),
        "max_execution_credits": max_execution_credits,
        "max_total_credits": max_total_credits,
        "credit_guard": "disabled_by_user" if no_credit_limit else "enabled",
        "stop_on_cancel": stop_on_cancel,
        "shards": [],
        "contains_api_keys": False,
    }
    combined_rows: List[Dict[str, Any]] = []
    total_credits_seen = 0.0
    stop_reason = ""
    for shard in selected:
        shard_started = time.time()
        paths = _shard_paths(output_dir, shard)
        ensure_dir(paths["dir"])
        shard_manifest: Dict[str, Any] = {
            "shard_id": shard.shard_id,
            "failure_class": shard.failure_class,
            "chain": shard.chain,
            "start": shard.start,
            "end": shard.end,
            "performance": performance,
            "sql_path": str(paths["sql"]),
            "result_json": str(paths["json"]),
            "result_csv": str(paths["csv"]),
            "contains_api_keys": False,
            "preflight_counts": preflight_counts,
        }
        if stop_reason:
            shard_manifest.update(
                {
                    "status": "skipped_stop_on_cancel",
                    "skip_reason": stop_reason,
                    "duration_seconds": round(time.time() - shard_started, 3),
                }
            )
            write_json(paths["manifest"], shard_manifest)
            run_manifest["shards"].append(shard_manifest)
            continue
        sql = render_shard_sql(shard, preflight_counts=preflight_counts)
        paths["sql"].write_text(sql, encoding="utf-8")
        if not no_credit_limit and max_total_credits is not None and total_credits_seen >= max_total_credits:
            shard_manifest.update(
                {
                    "status": "skipped_budget",
                    "skip_reason": "max_total_credits_reached",
                    "duration_seconds": round(time.time() - shard_started, 3),
                }
            )
            write_json(paths["manifest"], shard_manifest)
            run_manifest["shards"].append(shard_manifest)
            continue
        if resume and _completed_manifest(paths["manifest"], paths["json"]):
            existing = json.loads(paths["manifest"].read_text(encoding="utf-8"))
            try:
                existing_rows = json.loads(paths["json"].read_text(encoding="utf-8")).get("rows", [])
                combined_rows.extend(existing_rows)
            except json.JSONDecodeError:
                pass
            existing["resume_skipped"] = True
            total_credits_seen += float(existing.get("execution_cost_credits") or 0)
            run_manifest["shards"].append(existing)
            continue
        terminal = _terminal_noncompleted_manifest(paths["manifest"]) if resume and not rerun_failed else None
        if terminal:
            terminal["resume_skipped"] = True
            total_credits_seen += float(terminal.get("execution_cost_credits") or 0)
            run_manifest["shards"].append(terminal)
            continue
        if dry_run:
            shard_manifest.update({"status": "dry_run", "row_count": 0, "duration_seconds": round(time.time() - shard_started, 3)})
            write_json(paths["manifest"], shard_manifest)
            run_manifest["shards"].append(shard_manifest)
            continue
        if not api_key:
            raise PipelineError("Missing DUNE_MCP_KEY or DUNE_API_KEY in .env/environment")
        execution_id = _resumable_execution_id(paths["manifest"], paths["json"]) if resume else None
        if not execution_id:
            execution = _execute_sql(sql, api_key or "", performance)
            execution_id = execution.get("execution_id")
            if not execution_id:
                shard_manifest.update({"status": "failed", "error": execution})
                write_json(paths["manifest"], shard_manifest)
                run_manifest["shards"].append(shard_manifest)
                if stop_on_cancel:
                    stop_reason = "previous_shard_failed"
                continue
            shard_manifest.update(
                {
                    "status": "submitted",
                    "state": "QUERY_STATE_SUBMITTED",
                    "execution_id": execution_id,
                    "execution_submit_payload": {k: v for k, v in execution.items() if k != "result"},
                    "submitted_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                }
            )
            write_json(paths["manifest"], shard_manifest)
        else:
            shard_manifest["resumed_execution"] = True
            shard_manifest.update(
                {
                    "status": "resumed",
                    "execution_id": execution_id,
                    "resumed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                }
            )
            write_json(paths["manifest"], shard_manifest)
        status = _poll_execution(
            execution_id,
            api_key or "",
            poll_interval=poll_interval,
            timeout_seconds=timeout_seconds,
            max_execution_credits=None if no_credit_limit else max_execution_credits,
        )
        shard_manifest.update(
            {
                "execution_id": execution_id,
                "state": status.get("state"),
                "execution_cost_credits": status.get("execution_cost_credits"),
                "duration_seconds": round(time.time() - shard_started, 3),
                "status_payload": {k: v for k, v in status.items() if k != "result"},
            }
        )
        total_credits_seen += float(status.get("execution_cost_credits") or 0)
        if not status.get("is_execution_finished") and status.get("state") not in TERMINAL_STATES:
            shard_manifest["status"] = "running"
            write_json(paths["manifest"], shard_manifest)
            run_manifest["shards"].append(shard_manifest)
            continue
        if status.get("state") != "QUERY_STATE_COMPLETED":
            shard_manifest["status"] = "cancelled" if status.get("state") == "QUERY_STATE_CANCELLED" else "failed"
            shard_manifest["error"] = status.get("error") or status
            write_json(paths["manifest"], shard_manifest)
            run_manifest["shards"].append(shard_manifest)
            if stop_on_cancel:
                stop_reason = f"previous_shard_{shard_manifest['status']}"
            continue
        rows, final_payload = _fetch_all_rows(execution_id, api_key or "", page_size=page_size)
        _write_rows_json(paths["json"], rows)
        _write_rows_csv(paths["csv"], rows)
        combined_rows.extend(rows)
        metadata = (final_payload.get("result") or {}).get("metadata") or {}
        shard_manifest.update(
            {
                "status": "completed",
                "row_count": len(rows),
                "metadata": metadata,
                "expires_at": final_payload.get("expires_at") or status.get("expires_at"),
            }
        )
        write_json(paths["manifest"], shard_manifest)
        run_manifest["shards"].append(shard_manifest)
    run_manifest["completed_count"] = sum(1 for item in run_manifest["shards"] if item.get("status") == "completed")
    run_manifest["failed_count"] = sum(1 for item in run_manifest["shards"] if item.get("status") == "failed")
    run_manifest["cancelled_count"] = sum(1 for item in run_manifest["shards"] if item.get("status") == "cancelled")
    run_manifest["skipped_budget_count"] = sum(1 for item in run_manifest["shards"] if item.get("status") == "skipped_budget")
    run_manifest["skipped_stop_on_cancel_count"] = sum(
        1 for item in run_manifest["shards"] if item.get("status") == "skipped_stop_on_cancel"
    )
    run_manifest["running_count"] = sum(1 for item in run_manifest["shards"] if item.get("status") == "running")
    run_manifest["dry_run_count"] = sum(1 for item in run_manifest["shards"] if item.get("status") == "dry_run")
    run_manifest["observed_execution_credits"] = total_credits_seen
    if combined_rows:
        _write_rows_json(output_dir / "combined_results.json", combined_rows)
        _write_rows_csv(output_dir / "combined_results.csv", combined_rows)
    run_manifest["combined_row_count"] = len(combined_rows)
    write_json(output_dir / "run_manifest.json", run_manifest)
    write_experiment_log(run_manifest)
    return run_manifest


def write_experiment_log(run_manifest: Dict[str, Any]) -> None:
    output = repo_path("results", "broad_search_experiment_log.md")
    ensure_dir(output.parent)
    lines = [
        "# Broad Search Experiment Log",
        "",
        f"- Output dir: `{run_manifest.get('output_dir', '')}`",
        f"- Dry run: `{run_manifest.get('dry_run')}`",
        f"- Shards: `{run_manifest.get('shard_count')}`",
        f"- Completed: `{run_manifest.get('completed_count')}`",
        f"- Running: `{run_manifest.get('running_count')}`",
        f"- Failed: `{run_manifest.get('failed_count')}`",
        f"- Cancelled: `{run_manifest.get('cancelled_count')}`",
        f"- Skipped by budget: `{run_manifest.get('skipped_budget_count')}`",
        f"- Skipped by stop-on-cancel: `{run_manifest.get('skipped_stop_on_cancel_count', 0)}`",
        f"- Observed Dune credits: `{run_manifest.get('observed_execution_credits')}`",
        "",
        "| shard_id | class | chain | start | end | status | state | credits | rows | duration_s | reason |",
        "|---|---|---|---|---|---|---|---:|---:|---:|---|",
    ]
    for shard in run_manifest.get("shards", []):
        error = shard.get("error") or shard.get("status_payload") or {}
        reason = shard.get("skip_reason") or error.get("cancel_reason") or (error.get("message") if isinstance(error, dict) else "")
        lines.append(
            "| {shard_id} | {failure_class} | {chain} | {start} | {end} | {status} | {state} | {credits} | {rows} | {duration} | {reason} |".format(
                shard_id=shard.get("shard_id", ""),
                failure_class=shard.get("failure_class", ""),
                chain=shard.get("chain", ""),
                start=shard.get("start", ""),
                end=shard.get("end", ""),
                status=shard.get("status", ""),
                state=shard.get("state", ""),
                credits=shard.get("execution_cost_credits", ""),
                rows=shard.get("row_count", ""),
                duration=shard.get("duration_seconds", ""),
                reason=str(reason).replace("|", "/"),
            )
        )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute Broad Search Dataset v1 Dune SQL shards and export results.")
    parser.add_argument("--stage", choices=["calibration", "pilot", "full"], default=None)
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default="2026-05-12")
    parser.add_argument("--chains", default=DEFAULT_CHAINS)
    parser.add_argument("--split-by", default="year,chain,rule")
    parser.add_argument("--rules", default=",".join(RULES), help="Comma-separated failure classes to run.")
    parser.add_argument("--performance", choices=["small", "medium", "large"], default="small")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Render shard SQL and manifests without calling Dune.")
    parser.add_argument("--output-dir", default=str(repo_path("artifacts", "broad_search", "dune_exports", "full_mvp_chains_2022_20260512")))
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--poll-interval", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--max-shards", type=int, default=None, help="Optional safety cap for smoke runs.")
    parser.add_argument("--max-execution-credits", type=float, default=None, help="Cancel a shard if Dune reports credits above this value.")
    parser.add_argument("--max-total-credits", type=float, default=None, help="Stop scheduling new shards once observed credits reach this value.")
    parser.add_argument(
        "--no-credit-limit",
        action="store_true",
        help="Disable Dune credit guards for this run. RPC/local materialization budgets are not affected.",
    )
    parser.add_argument("--rerun-failed", action="store_true", help="With --resume, rerun failed/cancelled shard manifests.")
    parser.add_argument("--cancel-execution", default="", help="Cancel a running Dune execution id and exit.")
    parser.add_argument("--preflight-counts", action="store_true", help="Run compact count-only preflight SQL for supported rules.")
    parser.add_argument("--stop-on-cancel", action="store_true", help="Stop scheduling later shards after any shard is cancelled or failed.")
    args = parser.parse_args()
    try:
        if args.cancel_execution:
            env = load_env()
            api_key = env.get("DUNE_MCP_KEY") or env.get("DUNE_API_KEY")
            if not api_key:
                raise PipelineError("Missing DUNE_MCP_KEY or DUNE_API_KEY in .env/environment")
            result = _cancel_execution(args.cancel_execution, api_key)
            print("Cancelled Dune execution:")
            print(json.dumps(result, indent=2, sort_keys=True))
            return
        rules = [rule.strip() for rule in args.rules.split(",") if rule.strip()]
        if args.preflight_counts:
            unsupported = sorted(set(rules) - set(PREFLIGHT_RULES))
            if unsupported:
                raise PipelineError(f"Preflight counts are not implemented for: {', '.join(unsupported)}")
        if args.stage:
            shards = build_stage_shards(args.stage, start=args.start, end=args.end, chains=parse_chains(args.chains), split_by=args.split_by, rules=rules)
            stage_budget = STAGE_BUDGETS[args.stage]
            max_execution_credits = args.max_execution_credits
            max_total_credits = args.max_total_credits
            if not args.dry_run:
                if args.no_credit_limit:
                    max_execution_credits = None
                    max_total_credits = None
                else:
                    max_execution_credits = max_execution_credits if max_execution_credits is not None else stage_budget["max_execution_credits"]
                    max_total_credits = max_total_credits if max_total_credits is not None else stage_budget["max_total_credits"]
        else:
            shards = build_shards(args.start, args.end, parse_chains(args.chains), args.split_by, rules)
            max_execution_credits = args.max_execution_credits
            max_total_credits = args.max_total_credits
        result = run_shards(
            shards,
            output_dir=Path(args.output_dir),
            performance=args.performance,
            resume=args.resume,
            dry_run=args.dry_run,
            page_size=args.page_size,
            poll_interval=args.poll_interval,
            timeout_seconds=args.timeout_seconds,
            max_shards=args.max_shards,
            max_execution_credits=max_execution_credits,
            max_total_credits=max_total_credits,
            no_credit_limit=args.no_credit_limit,
            rerun_failed=args.rerun_failed,
            preflight_counts=args.preflight_counts,
            stop_on_cancel=args.stop_on_cancel,
        )
    except PipelineError as exc:
        raise SystemExit(str(exc)) from exc
    print("Broad-search Dune shard run summary:")
    print(f"- dry run: {result['dry_run']}")
    print(f"- shards: {result['shard_count']}")
    print(f"- completed: {result['completed_count']}")
    print(f"- running: {result['running_count']}")
    print(f"- failed: {result['failed_count']}")
    print(f"- cancelled: {result['cancelled_count']}")
    print(f"- skipped by stop-on-cancel: {result.get('skipped_stop_on_cancel_count', 0)}")
    print(f"- output: {result['output_dir']}")
    print(f"- observed credits: {result['observed_execution_credits']}")


if __name__ == "__main__":
    main()
