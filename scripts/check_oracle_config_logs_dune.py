#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from common import ensure_dir, load_env, repo_path
from run_broad_dune_queries import _execute_sql, _fetch_all_rows, _poll_execution


OUTPUT_DIR = repo_path("artifacts", "broad_search", "case_coverage", "oracle_config_log_dune_check")


TARGETS = [
    {
        "case_key": "case_a",
        "case_id": "moonwell_wrseth",
        "chain": "base",
        "address": "0xd7221b10fbbc1e1ba95fd0b4d031c15f7f365296",
        "addr_key": "addr_1",
        "role": "wrseth_eth_feed",
        "start_block": 37522875,
        "end_block": 37722874,
        "start_date": "2025-10-20",
        "end_date": "2025-11-04",
    },
    {
        "case_key": "case_a",
        "case_id": "moonwell_wrseth",
        "chain": "base",
        "address": "0x71041dddad3595f9ced3dccfbe3d1f4b0a16bb70",
        "addr_key": "addr_2",
        "role": "eth_usd_feed",
        "start_block": 37522875,
        "end_block": 37722874,
        "start_date": "2025-10-20",
        "end_date": "2025-11-04",
    },
    {
        "case_key": "case_a",
        "case_id": "moonwell_wrseth",
        "chain": "base",
        "address": "0x79c613b4f07080963c3b0ca58eb2745dd4c744a5",
        "addr_key": "addr_3",
        "role": "oracle_adapter_from_trace",
        "start_block": 37522875,
        "end_block": 37722874,
        "start_date": "2025-10-20",
        "end_date": "2025-11-04",
    },
    {
        "case_key": "case_a",
        "case_id": "moonwell_wrseth",
        "chain": "base",
        "address": "0xec942be8a8114bfd0396a5052c36027f2ca6a9d0",
        "addr_key": "addr_4",
        "role": "moonwell_oracle_wrapper_from_trace",
        "start_block": 37522875,
        "end_block": 37722874,
        "start_date": "2025-10-20",
        "end_date": "2025-11-04",
    },
    {
        "case_key": "case_a",
        "case_id": "moonwell_wrseth",
        "chain": "base",
        "address": "0xfbb21d0380bee3312b33c4353c8936a0f13ef26c",
        "addr_key": "addr_5",
        "role": "moonwell_comptroller",
        "start_block": 37522875,
        "end_block": 37722874,
        "start_date": "2025-10-20",
        "end_date": "2025-11-04",
    },
    {
        "case_key": "case_b",
        "case_id": "blueberry_faulty_oracle",
        "chain": "ethereum",
        "address": "0xffadb0bba4379dfabfb20ca6823f6ec439429ec2",
        "addr_key": "addr_1",
        "role": "blueberry_controller",
        "start_block": 19187289,
        "end_block": 19287288,
        "start_date": "2024-02-08",
        "end_date": "2024-02-23",
    },
    {
        "case_key": "case_b",
        "case_id": "blueberry_faulty_oracle",
        "chain": "ethereum",
        "address": "0xdfe469ace05c3d0d4461439e6cf5d0f46f33ec56",
        "addr_key": "addr_2",
        "role": "price_oracle_proxy_path",
        "start_block": 19187289,
        "end_block": 19287288,
        "start_date": "2024-02-08",
        "end_date": "2024-02-23",
    },
    {
        "case_key": "case_b",
        "case_id": "blueberry_faulty_oracle",
        "chain": "ethereum",
        "address": "0x770d3e22703210c09a573c2043081d97286f415e",
        "addr_key": "addr_3",
        "role": "oracle_impl_path",
        "start_block": 19187289,
        "end_block": 19287288,
        "start_date": "2024-02-08",
        "end_date": "2024-02-23",
    },
    {
        "case_key": "case_b",
        "case_id": "blueberry_faulty_oracle",
        "chain": "ethereum",
        "address": "0xc5cea3f9c92291335076d4c2ec6ae72e45fb8937",
        "addr_key": "addr_4",
        "role": "core_oracle_path",
        "start_block": 19187289,
        "end_block": 19287288,
        "start_date": "2024-02-08",
        "end_date": "2024-02-23",
    },
    {
        "case_key": "case_b",
        "case_id": "blueberry_faulty_oracle",
        "chain": "ethereum",
        "address": "0x5818562baac907b859e27813e8c0962d416dab59",
        "addr_key": "addr_5",
        "role": "core_oracle_impl_path",
        "start_block": 19187289,
        "end_block": 19287288,
        "start_date": "2024-02-08",
        "end_date": "2024-02-23",
    },
    {
        "case_key": "case_b",
        "case_id": "blueberry_faulty_oracle",
        "chain": "ethereum",
        "address": "0x9a72298ae3886221820b1c878d12d872087d3a23",
        "addr_key": "addr_6",
        "role": "feed_proxy_from_trace_1",
        "start_block": 19187289,
        "end_block": 19287288,
        "start_date": "2024-02-08",
        "end_date": "2024-02-23",
    },
    {
        "case_key": "case_b",
        "case_id": "blueberry_faulty_oracle",
        "chain": "ethereum",
        "address": "0x5f4ec3df9cbd43714fe2740f5e3616155c5b8419",
        "addr_key": "addr_7",
        "role": "feed_proxy_from_trace_2",
        "start_block": 19187289,
        "end_block": 19287288,
        "start_date": "2024-02-08",
        "end_date": "2024-02-23",
    },
    {
        "case_key": "case_b",
        "case_id": "blueberry_faulty_oracle",
        "chain": "ethereum",
        "address": "0x8fffffd4afb6115b954bd326cbe7b4ba576818f6",
        "addr_key": "addr_8",
        "role": "feed_proxy_from_trace_3",
        "start_block": 19187289,
        "end_block": 19287288,
        "start_date": "2024-02-08",
        "end_date": "2024-02-23",
    },
]


TOPIC_NAMES = {
    "0x6f1951b2aad10f3fc81b86d91105b413a5b3f847a34bbc5ce1904201b14438f6": "NewBorrowCap(address,uint256)",
    "0x3ab23ab0d51cccc0c3085aec51f99228625aa1a922b3a8ca89a26b0f2027a1a5": "MarketEntered(address,address)",
    "0x0559884fd3a460db3073b7fc896cc77986f16e378210ded43186175bf646fc5f": "AnswerUpdated(int256,uint256,uint256)",
}


def render_sql() -> str:
    values = []
    for target in TARGETS:
        values.append(
            "("
            f"'{target['case_key']}', "
            f"'{target['chain']}', "
            f"0x{target['address'][2:]}, "
            f"'{target['addr_key']}', "
            f"{target['start_block']}, "
            f"{target['end_block']}, "
            f"DATE '{target['start_date']}', "
            f"DATE '{target['end_date']}'"
            ")"
        )
    return f"""-- Read-only Dune check: pre-attack logs emitted by known oracle/controller paths.
-- Dune receives anonymized case/address keys and bounded historical windows only.
WITH targets(case_key, chain, address, addr_key, start_block, end_block, start_date, end_date) AS (
  VALUES
    {",\n    ".join(values)}
),
matched_logs AS (
  SELECT
    t.case_key,
    t.chain,
    t.addr_key,
    l.topic0,
    l.tx_hash,
    l.block_number,
    l.block_time,
    l.index AS log_index
  FROM targets t
  LEFT JOIN evms.logs l
    ON l.blockchain = t.chain
   AND l.contract_address = t.address
   AND l.block_number BETWEEN t.start_block AND t.end_block
   AND l.block_date BETWEEN t.start_date AND t.end_date
)
SELECT
  case_key,
  chain,
  addr_key,
  topic0,
  COUNT(tx_hash) AS log_count,
  approx_distinct(tx_hash) AS tx_count,
  MIN(block_number) AS first_block,
  MIN(block_time) AS first_time,
  max_by(tx_hash, block_number) AS latest_tx_hash,
  MAX(block_number) AS latest_block,
  MAX(block_time) AS latest_time,
  max_by(log_index, block_number) AS latest_log_index
FROM matched_logs
GROUP BY 1, 2, 3, 4
ORDER BY case_key, addr_key, log_count DESC, topic0
"""


def deanonymize(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    lookup = {(item["case_key"], item["addr_key"]): item for item in TARGETS}
    enriched = []
    for row in rows:
        target = lookup.get((row.get("case_key"), row.get("addr_key")), {})
        topic = str(row.get("topic0") or "")
        enriched.append(
            {
                **row,
                "case_id": target.get("case_id", ""),
                "address": target.get("address", ""),
                "role": target.get("role", ""),
                "topic_name": TOPIC_NAMES.get(topic.lower(), ""),
            }
        )
    return enriched


def write_report(rows: List[Dict[str, Any]], manifest: Dict[str, Any]) -> None:
    lines = [
        "# Dune Oracle Config Log Check",
        "",
        f"- Execution id: `{manifest.get('execution_id', '')}`",
        f"- State: `{manifest.get('status', {}).get('state', '')}`",
        f"- Credits: `{manifest.get('status', {}).get('execution_cost_credits', '')}`",
        "",
        "| case | role | topic0 | topic name | logs | txs | first block | latest block | sample/latest tx |",
        "|---|---|---|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        if int(row.get("log_count") or 0) == 0:
            continue
        lines.append(
            "| "
            f"`{row.get('case_id', '')}` | "
            f"`{row.get('role', '')}` | "
            f"`{row.get('topic0', '')}` | "
            f"{row.get('topic_name', '') or 'undecoded'} | "
            f"{row.get('log_count', 0)} | "
            f"{row.get('tx_count', 0)} | "
            f"{row.get('first_block', '')} | "
            f"{row.get('latest_block', '')} | "
            f"`{row.get('latest_tx_hash', '')}` |"
        )
    (OUTPUT_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    ensure_dir(OUTPUT_DIR)
    sql = render_sql()
    (OUTPUT_DIR / "query.sql").write_text(sql, encoding="utf-8")
    local_mapping = [
        {key: item[key] for key in ("case_key", "case_id", "addr_key", "role", "address", "chain", "start_block", "end_block")}
        for item in TARGETS
    ]
    (OUTPUT_DIR / "local_mapping.json").write_text(json.dumps(local_mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.dry_run:
        print(f"Wrote dry-run SQL: {OUTPUT_DIR / 'query.sql'}")
        return
    api_key = load_env().get("DUNE_MCP_KEY") or load_env().get("DUNE_API_KEY")
    if not api_key:
        raise SystemExit("Missing DUNE_MCP_KEY or DUNE_API_KEY")
    execution = _execute_sql(sql, api_key, args.performance)
    execution_id = execution.get("execution_id")
    manifest: Dict[str, Any] = {
        "execution_id": execution_id,
        "performance": args.performance,
        "query_sql": str(OUTPUT_DIR / "query.sql"),
        "scope": "read-only compact pre-attack topic0 aggregation for two approved cases",
        "submit_payload": {key: value for key, value in execution.items() if key != "result"},
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"execution_id={execution_id}")
    status = _poll_execution(
        execution_id,
        api_key,
        poll_interval=args.poll_interval,
        timeout_seconds=args.timeout_seconds,
        max_execution_credits=args.max_execution_credits,
    )
    manifest["status"] = status
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"state={status.get('state')} credits={status.get('execution_cost_credits')}")
    if status.get("state") != "QUERY_STATE_COMPLETED":
        raise SystemExit(json.dumps(status, indent=2, sort_keys=True))
    rows, _ = _fetch_all_rows(execution_id, api_key, page_size=args.page_size)
    enriched = deanonymize(rows)
    (OUTPUT_DIR / "result_raw.json").write_text(json.dumps({"rows": rows}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "result.json").write_text(json.dumps({"rows": enriched}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(enriched, manifest)
    print(f"rows={len(enriched)}")
    print(f"wrote={OUTPUT_DIR / 'result.json'}")
    print(f"report={OUTPUT_DIR / 'report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check pre-attack oracle/controller logs on Dune for two approved cases.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--performance", default="medium")
    parser.add_argument("--poll-interval", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--max-execution-credits", type=float, default=None)
    parser.add_argument("--page-size", type=int, default=1000)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
