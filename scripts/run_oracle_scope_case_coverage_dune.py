#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from common import ensure_dir, load_env, repo_path
from run_broad_dune_queries import _execute_sql, _fetch_all_rows, _poll_execution


OUTPUT_DIR = repo_path("artifacts", "broad_search", "case_coverage", "oracle_scope_case_coverage")
SQL_PATH = OUTPUT_DIR / "query.sql"


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_report(rows: List[Dict[str, Any]], manifest: Dict[str, Any]) -> None:
    missing = [row for row in rows if not row.get("oracle_scope_covered")]
    lines = [
        "# Oracle Scope Case Coverage Dune Run",
        "",
        f"- Execution id: `{manifest.get('execution_id', '')}`",
        f"- State: `{manifest.get('status', {}).get('state', '')}`",
        f"- Credits: `{manifest.get('status', {}).get('execution_cost_credits', '')}`",
        f"- Cases covered: `{len(rows) - len(missing)}/{len(rows)}`",
        "",
        "| case | chain | expected scope | covered | oracle logs | oracle topic0s | matched classes | matched rules |",
        "|---|---|---|---|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            f"`{row.get('case_id', '')}` | "
            f"`{row.get('chain', '')}` | "
            f"`{row.get('expected_scope_class', '')}` | "
            f"`{row.get('oracle_scope_covered', False)}` | "
            f"{row.get('oracle_scope_log_count', 0)} | "
            f"{row.get('oracle_scope_unique_topic0_count', 0)} | "
            f"{row.get('matched_scope_classes', '') or ''} | "
            f"{row.get('matched_rules', '') or ''} |"
        )
    if missing:
        lines.extend(["", "## Missing Cases", ""])
        for row in missing:
            lines.append(
                f"- `{row.get('case_id')}`: unmatched topic0s `{row.get('unmatched_topic0s', '')}`"
            )
    ensure_dir(OUTPUT_DIR)
    (OUTPUT_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    if not SQL_PATH.exists():
        raise SystemExit(f"Missing SQL file: {SQL_PATH}")
    sql = SQL_PATH.read_text(encoding="utf-8")
    env = load_env()
    api_key = env.get("DUNE_MCP_KEY") or env.get("DUNE_API_KEY")
    if not api_key:
        raise SystemExit("Missing DUNE_MCP_KEY or DUNE_API_KEY")

    manifest: Dict[str, Any] = {
        "query_sql": str(SQL_PATH),
        "scope": "oracle_activity_log_scope case coverage validation",
        "performance": args.performance,
    }
    ensure_dir(OUTPUT_DIR)
    if args.dry_run:
        manifest["dry_run"] = True
        _write_json(OUTPUT_DIR / "manifest.json", manifest)
        print(f"dry_run_sql={SQL_PATH}")
        return

    execution = _execute_sql(sql, api_key, args.performance)
    execution_id = execution.get("execution_id")
    manifest["execution_id"] = execution_id
    manifest["submit_payload"] = {key: value for key, value in execution.items() if key != "result"}
    _write_json(OUTPUT_DIR / "manifest.json", manifest)
    print(f"execution_id={execution_id}")

    status = _poll_execution(
        execution_id,
        api_key,
        poll_interval=args.poll_interval,
        timeout_seconds=args.timeout_seconds,
        max_execution_credits=args.max_execution_credits,
    )
    manifest["status"] = status
    _write_json(OUTPUT_DIR / "manifest.json", manifest)
    print(f"state={status.get('state')} credits={status.get('execution_cost_credits')}")
    if status.get("state") != "QUERY_STATE_COMPLETED":
        raise SystemExit(json.dumps(status, indent=2, sort_keys=True))

    rows, result_payload = _fetch_all_rows(execution_id, api_key, page_size=args.page_size)
    _write_json(OUTPUT_DIR / "result_raw_payload.json", result_payload)
    _write_json(OUTPUT_DIR / "result.json", {"rows": rows})
    _write_report(rows, manifest)

    missing = [row for row in rows if not row.get("oracle_scope_covered")]
    print(f"rows={len(rows)} covered={len(rows) - len(missing)}/{len(rows)}")
    print(f"result={OUTPUT_DIR / 'result.json'}")
    print(f"report={OUTPUT_DIR / 'report.md'}")
    if missing:
        raise SystemExit(f"Missing oracle scope coverage for: {', '.join(row.get('case_id', '') for row in missing)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the oracle scope case-coverage Dune SQL.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--performance", default="medium")
    parser.add_argument("--poll-interval", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--max-execution-credits", type=float, default=5.0)
    parser.add_argument("--page-size", type=int, default=1000)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
