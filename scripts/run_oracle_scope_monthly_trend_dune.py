#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from common import ensure_dir, load_env, repo_path
from run_broad_dune_queries import _execute_sql, _fetch_all_rows, _poll_execution


OUTPUT_DIR = repo_path("artifacts", "broad_search", "oracle_scope_monthly_trend")
SQL_PATH = OUTPUT_DIR / "query.sql"


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
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

    chart_paths: List[Path] = []
    ensure_dir(OUTPUT_DIR)

    all_rows = sorted(
        [row for row in rows if row.get("chain") == "all_active_case_chains"],
        key=lambda row: _parse_month(row.get("month")),
    )
    if all_rows:
        months = [_parse_month(row.get("month")) for row in all_rows]
        log_counts = [_as_int(row.get("oracle_log_count")) for row in all_rows]
        contract_counts = [_as_int(row.get("oracle_contract_count")) for row in all_rows]

        fig, ax1 = plt.subplots(figsize=(13, 6))
        ax1.plot(months, log_counts, color="#2563eb", linewidth=2.2, label="Oracle-scope logs")
        ax1.set_ylabel("Oracle-scope log count", color="#2563eb")
        ax1.tick_params(axis="y", labelcolor="#2563eb")
        ax1.grid(True, axis="y", alpha=0.25)

        ax2 = ax1.twinx()
        ax2.plot(months, contract_counts, color="#dc2626", linewidth=2.2, label="Unique contracts")
        ax2.set_ylabel("Unique contract count", color="#dc2626")
        ax2.tick_params(axis="y", labelcolor="#dc2626")

        fig.suptitle("Oracle Activity Log Scope Monthly Trend, All Active-Case Chains")
        ax1.set_xlabel("Month")
        fig.autofmt_xdate(rotation=35)
        lines = ax1.get_lines() + ax2.get_lines()
        ax1.legend(lines, [line.get_label() for line in lines], loc="upper left")
        fig.tight_layout()
        path = OUTPUT_DIR / "oracle_scope_monthly_trend_all_chains.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        chart_paths.append(path)

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
            axes[0].plot(months, [_as_int(row.get("oracle_log_count")) for row in series], linewidth=1.9, label=chain)
            axes[1].plot(months, [_as_int(row.get("oracle_contract_count")) for row in series], linewidth=1.9, label=chain)
        axes[0].set_ylabel("Oracle-scope logs")
        axes[1].set_ylabel("Unique contracts")
        axes[1].set_xlabel("Month")
        axes[0].grid(True, axis="y", alpha=0.25)
        axes[1].grid(True, axis="y", alpha=0.25)
        axes[0].legend(ncol=4, fontsize=9)
        fig.suptitle("Oracle Activity Log Scope Monthly Trend By Chain")
        fig.autofmt_xdate(rotation=35)
        fig.tight_layout()
        path = OUTPUT_DIR / "oracle_scope_monthly_trend_by_chain.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        chart_paths.append(path)

    return chart_paths


def _linear_slope(values: List[int]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    numerator = sum((idx - x_mean) * (value - y_mean) for idx, value in enumerate(values))
    denominator = sum((idx - x_mean) ** 2 for idx in range(n))
    return numerator / denominator if denominator else 0.0


def _write_report(rows: List[Dict[str, Any]], chart_paths: Iterable[Path], manifest: Dict[str, Any]) -> None:
    all_rows = sorted(
        [row for row in rows if row.get("chain") == "all_active_case_chains"],
        key=lambda row: _parse_month(row.get("month")),
    )
    log_values = [_as_int(row.get("oracle_log_count")) for row in all_rows]
    contract_values = [_as_int(row.get("oracle_contract_count")) for row in all_rows]
    first = all_rows[0] if all_rows else {}
    latest = all_rows[-1] if all_rows else {}
    peak = max(all_rows, key=lambda row: _as_int(row.get("oracle_log_count"))) if all_rows else {}

    lines = [
        "# Oracle Scope Monthly Trend",
        "",
        f"- Execution id: `{manifest.get('execution_id', '')}`",
        f"- State: `{manifest.get('status', {}).get('state', '')}`",
        f"- Credits: `{manifest.get('status', {}).get('execution_cost_credits', '')}`",
        f"- Rows: `{len(rows)}`",
        "- Chains: `ethereum`, `base`, `bnb`, `avalanche_c`",
        "- Scope: `oracle_activity_log_scope` S1-S4 oracle-specific topics. S5 proxy/wiring topics are excluded from the broad monthly trend because they are generic without oracle-path context.",
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
                f"- First month: `{str(first.get('month'))[:10]}`, logs `{first.get('oracle_log_count')}`, contracts `{first.get('oracle_contract_count')}`",
                f"- Latest month: `{str(latest.get('month'))[:10]}`, logs `{latest.get('oracle_log_count')}`, contracts `{latest.get('oracle_contract_count')}`",
                f"- Peak month by logs: `{str(peak.get('month'))[:10]}`, logs `{peak.get('oracle_log_count')}`, contracts `{peak.get('oracle_contract_count')}`",
                f"- Linear slope, logs per month: `{_linear_slope(log_values):.2f}`",
                f"- Linear slope, contracts per month: `{_linear_slope(contract_values):.2f}`",
                "",
                "## Monthly All-Chain Series",
                "",
                "| month | logs | txs | contracts | S1 price | S2 feed | S3 route | S4 gov | S5 contextual |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in all_rows:
            lines.append(
                "| "
                f"{str(row.get('month'))[:10]} | "
                f"{row.get('oracle_log_count')} | "
                f"{row.get('oracle_tx_count')} | "
                f"{row.get('oracle_contract_count')} | "
                f"{row.get('s1_price_reporting_log_count')} | "
                f"{row.get('s2_feed_binding_log_count')} | "
                f"{row.get('s3_route_config_log_count')} | "
                f"{row.get('s4_governance_config_log_count')} | "
                f"{row.get('s5_contextual_wiring_log_count')} |"
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

    ensure_dir(OUTPUT_DIR)
    manifest: Dict[str, Any] = {
        "query_sql": str(SQL_PATH),
        "scope": "oracle_activity_log_scope monthly trend",
        "performance": args.performance,
    }
    if args.dry_run:
        manifest["dry_run"] = True
        _write_json(OUTPUT_DIR / "manifest.json", manifest)
        print(f"dry_run_sql={SQL_PATH}")
        return

    if args.fetch_execution_id:
        from run_broad_dune_queries import _execution_status

        execution_id = args.fetch_execution_id
        manifest["execution_id"] = execution_id
        manifest["fetch_existing_execution"] = True
        status = _execution_status(execution_id, api_key)
        print(f"execution_id={execution_id}")
    else:
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
    _write_csv(OUTPUT_DIR / "result.csv", rows)
    chart_paths = _render_charts(rows)
    _write_report(rows, chart_paths, manifest)
    print(f"rows={len(rows)}")
    print(f"result={OUTPUT_DIR / 'result.json'}")
    print(f"csv={OUTPUT_DIR / 'result.csv'}")
    for path in chart_paths:
        print(f"chart={path}")
    print(f"report={OUTPUT_DIR / 'report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Dune monthly trend for oracle_activity_log_scope.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--performance", default="medium")
    parser.add_argument("--poll-interval", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--max-execution-credits", type=float, default=20.0)
    parser.add_argument("--page-size", type=int, default=5000)
    parser.add_argument("--fetch-execution-id", default="", help="Fetch an existing completed Dune execution instead of submitting SQL.")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
