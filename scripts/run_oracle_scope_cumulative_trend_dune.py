#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from common import ensure_dir, load_env, repo_path
from run_broad_dune_queries import _execute_sql, _execution_status, _fetch_all_rows, _poll_execution


OUTPUT_DIR = repo_path("artifacts", "broad_search", "oracle_scope_cumulative_trend")
SQL_PATH = OUTPUT_DIR / "query.sql"


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _parse_month(value: Any) -> datetime:
    text = str(value)
    if " " in text:
        text = text.split(" ", 1)[0]
    return datetime.strptime(text[:10], "%Y-%m-%d")


def _as_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    return int(float(value))


def _render_charts(rows: List[Dict[str, Any]]) -> List[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # type: ignore

    ensure_dir(OUTPUT_DIR)
    paths: List[Path] = []

    all_rows = sorted(
        [row for row in rows if row.get("chain") == "all_active_case_chains"],
        key=lambda row: _parse_month(row.get("month")),
    )
    if all_rows:
        months = [_parse_month(row.get("month")) for row in all_rows]

        fig, ax = plt.subplots(figsize=(13, 6))
        ax.plot(months, [_as_int(row.get("cumulative_oracle_log_count")) for row in all_rows], color="#2563eb", linewidth=2.4)
        ax.set_title("Cumulative Oracle-Scope Logs")
        ax.set_xlabel("Month")
        ax.set_ylabel("Cumulative log count")
        ax.grid(True, axis="y", alpha=0.25)
        fig.autofmt_xdate(rotation=35)
        fig.tight_layout()
        path = OUTPUT_DIR / "cumulative_oracle_scope_logs.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        paths.append(path)

        fig, ax = plt.subplots(figsize=(13, 6))
        ax.plot(months, [_as_int(row.get("cumulative_unique_contract_count")) for row in all_rows], color="#dc2626", linewidth=2.4)
        ax.set_title("Cumulative Unique Oracle-Scope Contracts")
        ax.set_xlabel("Month")
        ax.set_ylabel("Cumulative unique chain-contract count")
        ax.grid(True, axis="y", alpha=0.25)
        fig.autofmt_xdate(rotation=35)
        fig.tight_layout()
        path = OUTPUT_DIR / "cumulative_oracle_scope_contracts.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        paths.append(path)

    chain_rows = [row for row in rows if row.get("chain") != "all_active_case_chains"]
    chains = sorted({str(row.get("chain")) for row in chain_rows})
    if chain_rows and chains:
        fig, axes = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
        for chain in chains:
            series = sorted(
                [row for row in chain_rows if row.get("chain") == chain],
                key=lambda row: _parse_month(row.get("month")),
            )
            months = [_parse_month(row.get("month")) for row in series]
            axes[0].plot(months, [_as_int(row.get("cumulative_oracle_log_count")) for row in series], linewidth=1.9, label=chain)
            axes[1].plot(months, [_as_int(row.get("cumulative_unique_contract_count")) for row in series], linewidth=1.9, label=chain)
        axes[0].set_title("Cumulative Oracle-Scope Logs By Chain")
        axes[0].set_ylabel("Cumulative logs")
        axes[1].set_title("Cumulative Unique Oracle-Scope Contracts By Chain")
        axes[1].set_ylabel("Cumulative unique contracts")
        axes[1].set_xlabel("Month")
        axes[0].grid(True, axis="y", alpha=0.25)
        axes[1].grid(True, axis="y", alpha=0.25)
        axes[0].legend(ncol=4, fontsize=9)
        fig.autofmt_xdate(rotation=35)
        fig.tight_layout()
        path = OUTPUT_DIR / "cumulative_oracle_scope_by_chain.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        paths.append(path)

    return paths


def _write_report(rows: List[Dict[str, Any]], chart_paths: Iterable[Path], manifest: Dict[str, Any]) -> None:
    all_rows = sorted(
        [row for row in rows if row.get("chain") == "all_active_case_chains"],
        key=lambda row: _parse_month(row.get("month")),
    )
    latest = all_rows[-1] if all_rows else {}
    first = all_rows[0] if all_rows else {}
    lines = [
        "# Oracle Scope Cumulative Trend",
        "",
        f"- Execution id: `{manifest.get('execution_id', '')}`",
        f"- State: `{manifest.get('status', {}).get('state', '')}`",
        f"- Credits: `{manifest.get('status', {}).get('execution_cost_credits', '')}`",
        "- Chains: `ethereum`, `base`, `bnb`, `avalanche_c`",
        "- Scope: S1-S4 oracle-specific topic0 matches from `oracle_activity_log_scope`.",
        "- Contract identity: chain-scoped `(blockchain, contract_address)` first-seen count.",
        "",
    ]
    for path in chart_paths:
        lines.append(f"![{path.stem}]({path})")
        lines.append("")
    if all_rows:
        lines.extend(
            [
                "## Summary",
                "",
                f"- First month: `{str(first.get('month'))[:10]}`, cumulative logs `{first.get('cumulative_oracle_log_count')}`, cumulative unique contracts `{first.get('cumulative_unique_contract_count')}`",
                f"- Latest month: `{str(latest.get('month'))[:10]}`, cumulative logs `{latest.get('cumulative_oracle_log_count')}`, cumulative unique contracts `{latest.get('cumulative_unique_contract_count')}`",
                "",
                "## All-Chain Cumulative Series",
                "",
                "| month | monthly logs | new contracts | cumulative logs | cumulative unique contracts |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for row in all_rows:
            lines.append(
                "| "
                f"{str(row.get('month'))[:10]} | "
                f"{row.get('monthly_oracle_log_count')} | "
                f"{row.get('monthly_new_contract_count')} | "
                f"{row.get('cumulative_oracle_log_count')} | "
                f"{row.get('cumulative_unique_contract_count')} |"
            )
    (OUTPUT_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _materialize(execution_id: str, api_key: str, manifest: Dict[str, Any], page_size: int) -> None:
    status = _execution_status(execution_id, api_key)
    manifest["status"] = status
    _write_json(OUTPUT_DIR / "manifest.json", manifest)
    print(f"state={status.get('state')} credits={status.get('execution_cost_credits')}")
    if status.get("state") != "QUERY_STATE_COMPLETED":
        raise SystemExit(json.dumps(status, indent=2, sort_keys=True))

    rows, result_payload = _fetch_all_rows(execution_id, api_key, page_size=page_size)
    _write_json(OUTPUT_DIR / "result_raw_payload.json", result_payload)
    _write_json(OUTPUT_DIR / "result.json", {"rows": rows})
    _write_csv(OUTPUT_DIR / "result.csv", rows)
    charts = _render_charts(rows)
    _write_report(rows, charts, manifest)
    print(f"rows={len(rows)}")
    print(f"result={OUTPUT_DIR / 'result.json'}")
    print(f"csv={OUTPUT_DIR / 'result.csv'}")
    for path in charts:
        print(f"chart={path}")
    print(f"report={OUTPUT_DIR / 'report.md'}")


def run(args: argparse.Namespace) -> None:
    if not SQL_PATH.exists():
        raise SystemExit(f"Missing SQL file: {SQL_PATH}")
    env = load_env()
    api_key = env.get("DUNE_MCP_KEY") or env.get("DUNE_API_KEY")
    if not api_key:
        raise SystemExit("Missing DUNE_MCP_KEY or DUNE_API_KEY")

    ensure_dir(OUTPUT_DIR)
    manifest: Dict[str, Any] = {
        "query_sql": str(SQL_PATH),
        "scope": "oracle_activity_log_scope cumulative trend",
        "performance": args.performance,
    }
    if args.dry_run:
        manifest["dry_run"] = True
        _write_json(OUTPUT_DIR / "manifest.json", manifest)
        print(f"dry_run_sql={SQL_PATH}")
        return
    if args.fetch_execution_id:
        manifest["execution_id"] = args.fetch_execution_id
        manifest["fetch_existing_execution"] = True
        print(f"execution_id={args.fetch_execution_id}")
        _materialize(args.fetch_execution_id, api_key, manifest, args.page_size)
        return

    sql = SQL_PATH.read_text(encoding="utf-8")
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
    if status.get("state") != "QUERY_STATE_COMPLETED":
        print(f"state={status.get('state')} credits={status.get('execution_cost_credits')}")
        raise SystemExit(json.dumps(status, indent=2, sort_keys=True))
    _materialize(execution_id, api_key, manifest, args.page_size)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Dune cumulative trend for oracle_activity_log_scope.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--performance", default="medium")
    parser.add_argument("--poll-interval", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--max-execution-credits", type=float, default=160.0)
    parser.add_argument("--page-size", type=int, default=5000)
    parser.add_argument("--fetch-execution-id", default="", help="Fetch an existing completed Dune execution instead of submitting SQL.")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
