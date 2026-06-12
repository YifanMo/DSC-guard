#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

from common import PipelineError, ensure_dir, load_env, repo_path, write_json, write_jsonl
from run_broad_dune_queries import _execute_sql, _fetch_all_rows, _poll_execution

import build_benign_eval_dataset as benign


DEFAULT_OUTPUT_DIR = repo_path("artifacts", "eval_dataset", "dune_case10_per_case")
ANSWER_UPDATED_TOPIC = benign.ANSWER_UPDATED_TOPIC


def _sql_string(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _sql_varbinary(value: str) -> str:
    text = str(value or "").lower()
    if not (text.startswith("0x") and all(ch in "0123456789abcdef" for ch in text[2:])):
        raise PipelineError(f"Invalid hex literal for Dune SQL: {value}")
    return text


def _dune_timestamp(value: Any) -> str:
    parsed = benign._parse_time(value)
    if not parsed:
        parsed = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _year_bounds_for_case(ctx: Dict[str, Any], global_start: str, global_end: str) -> tuple[str, str]:
    start_year = max(int(global_start[:4]), int(ctx["incident_start"].year))
    end_year = min(int(global_end[:4]), int(ctx["incident_end"].year))
    start = f"{start_year}-01-01"
    end = f"{end_year}-12-31"
    if end > global_end:
        end = global_end
    if start < global_start:
        start = global_start
    return start, end


def _known_txs_values(contexts: Sequence[Dict[str, Any]]) -> str:
    rows: List[str] = []
    for ctx in contexts:
        for tx_hash in ctx["known_txs"]:
            rows.append(f"({_sql_string(ctx['case_id'])}, {_sql_string(ctx['chain'])}, {_sql_varbinary(tx_hash)})")
    if not rows:
        return "('none', 'none', 0x0000000000000000000000000000000000000000000000000000000000000000)"
    return ",\n    ".join(rows)


def _exact_oracle_controls(contexts: Sequence[Dict[str, Any]]) -> str:
    rows: List[str] = []
    for ctx in contexts:
        case_id = ctx["case_id"]
        if case_id in {"venus_luna", "blizz_luna"} and ctx.get("normal_oracle_bounds"):
            feed, normal_min, normal_max, decimals = ctx["normal_oracle_bounds"]
            rows.append(
                "("
                + ", ".join(
                    [
                        _sql_string(case_id),
                        _sql_string(ctx["chain"]),
                        _sql_varbinary(feed),
                        str(float(normal_min)),
                        str(float(normal_max)),
                        str(int(decimals)),
                        f"TIMESTAMP {_sql_string(_dune_timestamp(ctx['incident_start']))}",
                        f"TIMESTAMP {_sql_string(_dune_timestamp(ctx['incident_end']))}",
                    ]
                )
                + ")"
            )
        elif case_id == "moonwell_wrseth" and benign._valid_address(ctx.get("primary_contract")):
            # The materialized incident receipt shows the malfunctioning OCR logs on
            # primary_contract. Normal wrsETH/ETH OCR answers are around 1e18.
            rows.append(
                "("
                + ", ".join(
                    [
                        _sql_string(case_id),
                        _sql_string(ctx["chain"]),
                        _sql_varbinary(ctx["primary_contract"]),
                        "0.5",
                        "2.0",
                        "18",
                        f"TIMESTAMP {_sql_string(_dune_timestamp(ctx['incident_start']))}",
                        f"TIMESTAMP {_sql_string(_dune_timestamp(ctx['incident_end']))}",
                    ]
                )
                + ")"
            )
    if not rows:
        return "('none', 'none', 0x0000000000000000000000000000000000000000, 0.0, 0.0, 8, TIMESTAMP '1970-01-01 00:00:00', TIMESTAMP '1970-01-02 00:00:00')"
    return ",\n    ".join(rows)


def _topics_by_scope(scope: str) -> List[tuple[str, str]]:
    rows: List[tuple[str, str]] = []
    for topic0, short_scope, _full_scope, _name, contextual in benign.ORACLE_TOPICS:
        if contextual:
            continue
        if short_scope == scope:
            rows.append((topic0, short_scope))
    return rows


def _topic_controls(contexts: Sequence[Dict[str, Any]], start: str, end: str) -> str:
    rows: List[str] = []
    for ctx in contexts:
        case_id = ctx["case_id"]
        case_start, case_end = _year_bounds_for_case(ctx, start, end)
        topic_rows: List[tuple[str, str]] = []
        if case_id == "ploutos":
            topic_rows = _topics_by_scope("S2")
        elif case_id == "moonwell_cbeth":
            topic_rows = [
                ("0xbc7cd75a20ee27fd9adebab32041f755214dbc6bffa90cc0225b39da2e5c2d3b", "S4"),
                ("0xd6b3a81dd8b7dc419d8d0f20797397ea2eaba914386b89898aa638438803a1ec", "S4"),
                ("0xd9e7d1778ca05570ced72c9aeb12a41fcc76f7f57ea25853dea228f8836d0022", "S2"),
            ]
        elif case_id == "blueberry_faulty_oracle":
            topic_rows = [
                ("0xa8c96090e146ce1076efa81e5424d56e13d5c3854943f7926406c12d15d6dbe9", "S3"),
                ("0xd1b3641b73e6c323671a85001b02db34d4e63a7fa6d264896138094dd6b8bfdf", "S3"),
                ("0xaef9ecb0b33da1a5a170fdeed3accb3e88c5257f51d6faa019cea841b864d049", "S2"),
            ]
        elif case_id == "moonwell_wrseth":
            topic_rows = [(ANSWER_UPDATED_TOPIC, "S1")]
        else:
            topic_rows = [(ctx["primary_topic0"], ctx["scope_class"])] if ctx.get("primary_topic0") else []
        for topic0, scope_class in topic_rows:
            rows.append(
                "("
                + ", ".join(
                    [
                        _sql_string(case_id),
                        _sql_string(ctx["chain"]),
                        _sql_varbinary(topic0),
                        _sql_string(scope_class),
                        f"DATE {_sql_string(case_start)}",
                        f"DATE {_sql_string(case_end)}",
                        f"TIMESTAMP {_sql_string(_dune_timestamp(ctx['incident_start']))}",
                        f"TIMESTAMP {_sql_string(_dune_timestamp(ctx['incident_end']))}",
                    ]
                )
                + ")"
            )
    if not rows:
        return "('none', 'none', 0x0000000000000000000000000000000000000000000000000000000000000000, 'S0', DATE '1970-01-01', DATE '1970-01-02', TIMESTAMP '1970-01-01 00:00:00', TIMESTAMP '1970-01-02 00:00:00')"
    return ",\n    ".join(rows)


def render_sql(contexts: Sequence[Dict[str, Any]], *, start: str, end: str, target_per_case: int, guard_hours: int) -> str:
    return f"""-- Per-case benign evaluation candidates.
-- The quota is deterministic per case and does not use risk scoring, amount ranking, nondeterministic sampling, or tx-specific case filters.
WITH
known_case_txs(case_id, chain, tx_hash) AS (
  VALUES
    {_known_txs_values(contexts)}
),
exact_oracle_controls(case_related_to, chain, feed_address, normal_min, normal_max, answer_decimals, incident_start, incident_end) AS (
  VALUES
    {_exact_oracle_controls(contexts)}
),
topic_controls(case_related_to, chain, topic0, scope_class, start_date, end_date, incident_start, incident_end) AS (
  VALUES
    {_topic_controls(contexts, start, end)}
),
exact_oracle_pool AS (
  SELECT DISTINCT
    1 AS source_priority,
    'same_oracle' AS benign_stratum,
    'benign_verified' AS label,
    o.case_related_to,
    l.blockchain AS chain,
    year(l.block_time) AS year,
    'S1' AS scope_class,
    l.block_time,
    l.tx_hash,
    l.contract_address,
    l.topic0,
    abs(CAST(bytearray_to_int256(l.topic1) AS double) / pow(10, o.answer_decimals)) AS normalized_answer,
    'same oracle feed outside incident window with normal answer bounds' AS exclusion_reason
  FROM evms.logs l
  JOIN exact_oracle_controls o
    ON o.chain = l.blockchain
   AND o.feed_address = l.contract_address
  LEFT JOIN known_case_txs kt
    ON kt.chain = l.blockchain
   AND kt.tx_hash = l.tx_hash
  WHERE l.block_date BETWEEN DATE {_sql_string(start)} AND DATE {_sql_string(end)}
    AND l.topic0 = {_sql_varbinary(ANSWER_UPDATED_TOPIC)}
    AND kt.tx_hash IS NULL
    AND NOT (
      l.block_time BETWEEN o.incident_start - INTERVAL '{guard_hours}' HOUR
                       AND o.incident_end + INTERVAL '{guard_hours}' HOUR
    )
    AND abs(CAST(bytearray_to_int256(l.topic1) AS double) / pow(10, o.answer_decimals))
        BETWEEN o.normal_min AND o.normal_max
),
topic_fallback_pool AS (
  SELECT DISTINCT
    2 AS source_priority,
    'case_topic' AS benign_stratum,
    'unknown_negative' AS label,
    c.case_related_to,
    l.blockchain AS chain,
    year(l.block_time) AS year,
    c.scope_class,
    l.block_time,
    l.tx_hash,
    l.contract_address,
    l.topic0,
    CAST(NULL AS double) AS normalized_answer,
    'same case-year oracle-scope topic outside incident window; local replay required before FP denominator' AS exclusion_reason
  FROM evms.logs l
  JOIN topic_controls c
    ON c.chain = l.blockchain
   AND c.topic0 = l.topic0
   AND l.block_date BETWEEN c.start_date AND c.end_date
  LEFT JOIN known_case_txs kt
    ON kt.chain = l.blockchain
   AND kt.tx_hash = l.tx_hash
  WHERE kt.tx_hash IS NULL
    AND NOT (
      l.block_time BETWEEN c.incident_start - INTERVAL '{guard_hours}' HOUR
                       AND c.incident_end + INTERVAL '{guard_hours}' HOUR
    )
),
ranked AS (
  SELECT
    *,
    row_number() OVER (
      PARTITION BY case_related_to
      ORDER BY source_priority, lower(CAST(tx_hash AS varchar)), lower(CAST(contract_address AS varchar)), lower(CAST(topic0 AS varchar))
    ) AS deterministic_case_sample_index
  FROM (
    SELECT * FROM exact_oracle_pool
    UNION ALL
    SELECT * FROM topic_fallback_pool
  )
)
SELECT
  'benign-' || benign_stratum || '-' || case_related_to || '-' || CAST(tx_hash AS varchar) AS sample_id,
  label,
  benign_stratum,
  chain,
  year,
  scope_class,
  CAST(tx_hash AS varchar) AS tx_hash,
  CAST(contract_address AS varchar) AS contract_address,
  CAST(topic0 AS varchar) AS topic0,
  case_related_to,
  false AS expected_violation,
  exclusion_reason,
  'remote_candidate_pending_receipt_replay' AS materialization_status,
  normalized_answer,
  deterministic_case_sample_index
FROM ranked
WHERE deterministic_case_sample_index <= {int(target_per_case)}
ORDER BY case_related_to, deterministic_case_sample_index;
"""


def write_summary(rows: Sequence[Dict[str, Any]], output_dir: Path, status: Dict[str, Any]) -> None:
    by_case: Dict[str, int] = {}
    by_label: Dict[str, int] = {}
    by_stratum: Dict[str, int] = {}
    examples: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        case_id = str(row.get("case_related_to") or "")
        by_case[case_id] = by_case.get(case_id, 0) + 1
        by_label[str(row.get("label") or "")] = by_label.get(str(row.get("label") or ""), 0) + 1
        by_stratum[str(row.get("benign_stratum") or "")] = by_stratum.get(str(row.get("benign_stratum") or ""), 0) + 1
        examples.setdefault(case_id, []).append(
            {
                "tx_hash": row.get("tx_hash"),
                "chain": row.get("chain"),
                "topic0": row.get("topic0"),
                "label": row.get("label"),
                "benign_stratum": row.get("benign_stratum"),
                "normalized_answer": row.get("normalized_answer"),
            }
        )
    summary = {
        "dataset": "per_case_10_benign_eval_candidates",
        "row_count": len(rows),
        "by_case": dict(sorted(by_case.items())),
        "by_label": dict(sorted(by_label.items())),
        "by_stratum": dict(sorted(by_stratum.items())),
        "dune_execution_id": status.get("execution_id"),
        "dune_execution_ids": status.get("execution_ids", []),
        "dune_state": status.get("state"),
        "dune_execution_cost_credits": status.get("execution_cost_credits"),
        "policy": "deterministic per-case quota over historical oracle-scope logs; no scoring, amount ranking, nondeterministic sampling, chain writes, private keys, or attack simulation",
        "examples": {case: values[:3] for case, values in sorted(examples.items())},
    }
    write_json(output_dir / "case10_summary.json", summary)

    lines = [
        "# Per-Case Benign Sample Run",
        "",
        "This run generated a deterministic 10-row benign candidate slice for each active case from historical Dune log indexes.",
        "",
        f"- Dune execution id: `{status.get('execution_id', '') or ', '.join(status.get('execution_ids', []))}`",
        f"- Dune state: `{status.get('state', '')}`",
        f"- Dune credits: `{status.get('execution_cost_credits', '')}`",
        f"- Total rows: `{len(rows)}`",
        "",
        "| case | rows |",
        "|---|---:|",
    ]
    for case_id, count in sorted(by_case.items()):
        lines.append(f"| {case_id} | {count} |")
    lines.extend(
        [
            "",
            "## Label Counts",
            "",
            "| label | rows |",
            "|---|---:|",
        ]
    )
    for label, count in sorted(by_label.items()):
        lines.append(f"| {label} | {count} |")
    lines.extend(
        [
            "",
            "Only `benign_verified` rows should enter the false-positive denominator immediately. `unknown_negative` rows are hard-benign candidates and require local replay/materialization before being counted as confirmed benign.",
        ]
    )
    repo_path("results", "case10_benign_eval_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> Dict[str, Any]:
    chains = benign._parse_csv(args.chains)
    contexts = benign._case_context_rows(chains)
    output_dir = Path(args.output_dir)
    ensure_dir(output_dir)
    sql = render_sql(
        contexts,
        start=args.start,
        end=args.end,
        target_per_case=args.target_per_case,
        guard_hours=args.incident_guard_hours,
    )
    (output_dir / "query.sql").write_text(sql, encoding="utf-8")
    if args.dry_run:
        manifest = {
            "dataset": "per_case_10_benign_eval_candidates",
            "dry_run": True,
            "query_path": str(output_dir / "query.sql"),
            "target_per_case": args.target_per_case,
        }
        write_json(output_dir / "run_manifest.json", manifest)
        return manifest

    env = load_env()
    api_keys = [
        ("DUNE_CLI_KEY", env.get("DUNE_CLI_KEY")),
        ("DUNE_MCP_KEY", env.get("DUNE_MCP_KEY")),
    ]
    api_keys = [(name, value) for name, value in api_keys if value]
    if not api_keys:
        raise PipelineError("Missing DUNE_CLI_KEY or DUNE_MCP_KEY in .env/environment")

    if args.split_by_case:
        all_rows: List[Dict[str, Any]] = []
        shard_manifests: List[Dict[str, Any]] = []
        for ctx in contexts:
            case_id = ctx["case_id"]
            shard_dir = output_dir / "shards" / case_id
            ensure_dir(shard_dir)
            shard_sql = render_sql(
                [ctx],
                start=args.start,
                end=args.end,
                target_per_case=args.target_per_case,
                guard_hours=args.incident_guard_hours,
            )
            (shard_dir / "query.sql").write_text(shard_sql, encoding="utf-8")
            execution = None
            api_key = ""
            api_key_name = ""
            submit_errors: List[Dict[str, str]] = []
            for candidate_name, candidate_key in api_keys:
                try:
                    execution = _execute_sql(shard_sql, candidate_key or "", args.performance)
                    api_key = candidate_key or ""
                    api_key_name = candidate_name
                    break
                except PipelineError as exc:
                    submit_errors.append({"key": candidate_name, "error": str(exc)})
                    continue
            if execution is None:
                write_json(shard_dir / "submit_errors.json", submit_errors)
                raise PipelineError(f"Dune SQL execution failed for {case_id}; see {shard_dir / 'submit_errors.json'}")
            execution_id = execution.get("execution_id")
            if not execution_id:
                raise PipelineError(f"Dune SQL execution did not return execution_id for {case_id}: {execution}")
            shard_manifest = {
                "case_id": case_id,
                "execution_id": execution_id,
                "api_key_env": api_key_name,
                "performance": args.performance,
                "query_path": str(shard_dir / "query.sql"),
                "submitted_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "contains_api_keys": False,
            }
            write_json(shard_dir / "run_manifest.json", shard_manifest)
            status = _poll_execution(
                execution_id,
                api_key,
                poll_interval=args.poll_interval,
                timeout_seconds=args.timeout_seconds,
                max_execution_credits=None,
            )
            status["execution_id"] = execution_id
            write_json(shard_dir / "status.json", status)
            if status.get("state") != "QUERY_STATE_COMPLETED":
                raise PipelineError(f"Dune query for {case_id} did not complete: {status.get('state')} {status.get('error') or ''}")
            rows, result_page = _fetch_all_rows(execution_id, api_key, page_size=args.page_size)
            write_json(shard_dir / "result_rows.json", rows)
            write_jsonl(shard_dir / "result_rows.jsonl", rows)
            write_json(shard_dir / "result_page.json", result_page)
            shard_manifest.update(
                {
                    "state": status.get("state"),
                    "execution_cost_credits": status.get("execution_cost_credits"),
                    "row_count": len(rows),
                    "api_key_env": api_key_name,
                }
            )
            write_json(shard_dir / "run_manifest.json", shard_manifest)
            shard_manifests.append(shard_manifest)
            all_rows.extend(rows)
        combined_status = {
            "execution_id": "",
            "execution_ids": [str(item.get("execution_id") or "") for item in shard_manifests],
            "state": "QUERY_STATE_COMPLETED",
            "execution_cost_credits": sum(float(item.get("execution_cost_credits") or 0) for item in shard_manifests),
        }
        write_json(output_dir / "result_rows.json", all_rows)
        write_jsonl(output_dir / "result_rows.jsonl", all_rows)
        write_summary(all_rows, output_dir, combined_status)
        manifest = {
            "dataset": "per_case_10_benign_eval_candidates",
            "dry_run": False,
            "split_by_case": True,
            "state": "QUERY_STATE_COMPLETED",
            "execution_cost_credits": combined_status["execution_cost_credits"],
            "row_count": len(all_rows),
            "shards": shard_manifests,
            "contains_api_keys": False,
        }
        write_json(output_dir / "run_manifest.json", manifest)
        return manifest

    execution: Dict[str, Any] | None = None
    api_key = ""
    api_key_name = ""
    submit_errors: List[Dict[str, str]] = []
    for candidate_name, candidate_key in api_keys:
        try:
            execution = _execute_sql(sql, candidate_key or "", args.performance)
            api_key = candidate_key or ""
            api_key_name = candidate_name
            break
        except PipelineError as exc:
            submit_errors.append({"key": candidate_name, "error": str(exc)})
            continue
    if execution is None:
        write_json(output_dir / "submit_errors.json", submit_errors)
        raise PipelineError("Dune SQL execution failed for DUNE_CLI_KEY and DUNE_MCP_KEY; see submit_errors.json")
    execution_id = execution.get("execution_id")
    if not execution_id:
        raise PipelineError(f"Dune SQL execution did not return execution_id: {execution}")
    submitted_manifest = {
        "dataset": "per_case_10_benign_eval_candidates",
        "dry_run": False,
        "execution_id": execution_id,
        "api_key_env": api_key_name,
        "performance": args.performance,
        "query_path": str(output_dir / "query.sql"),
        "submitted_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "contains_api_keys": False,
    }
    write_json(output_dir / "run_manifest.json", submitted_manifest)

    status = _poll_execution(
        execution_id,
        api_key,
        poll_interval=args.poll_interval,
        timeout_seconds=args.timeout_seconds,
        max_execution_credits=None,
    )
    status["execution_id"] = execution_id
    write_json(output_dir / "status.json", status)
    if status.get("state") != "QUERY_STATE_COMPLETED":
        raise PipelineError(f"Dune query did not complete: {status.get('state')} {status.get('error') or ''}")
    rows, result_page = _fetch_all_rows(execution_id, api_key, page_size=args.page_size)
    write_json(output_dir / "result_rows.json", rows)
    write_jsonl(output_dir / "result_rows.jsonl", rows)
    write_json(output_dir / "result_page.json", result_page)
    write_summary(rows, output_dir, status)
    submitted_manifest.update(
        {
            "state": status.get("state"),
            "execution_cost_credits": status.get("execution_cost_credits"),
            "row_count": len(rows),
            "api_key_env": api_key_name,
        }
    )
    write_json(output_dir / "run_manifest.json", submitted_manifest)
    return submitted_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Dune query that produces 10 benign candidates per active case.")
    parser.add_argument("--chains", default="ethereum,bnb,base,avalanche_c")
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default="2026-05-12")
    parser.add_argument("--target-per-case", type=int, default=10)
    parser.add_argument("--incident-guard-hours", type=int, default=24)
    parser.add_argument("--performance", choices=["small", "medium", "large"], default="medium")
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--poll-interval", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--split-by-case", action="store_true", help="Execute one smaller Dune query per active case.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    try:
        manifest = run(args)
        print(json.dumps(manifest, indent=2, sort_keys=True))
    except PipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
