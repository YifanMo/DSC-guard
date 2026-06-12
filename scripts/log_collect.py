#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Any, Dict, List

from common import (
    PipelineError,
    get_case,
    load_env,
    print_status,
    repo_path,
    resolve_template,
    rpc_call,
    write_jsonl,
)


def fixture_trace_path(case_id: str) -> Path:
    return repo_path("fixtures", "log_trace", f"{case_id}.jsonl")


def output_trace_path(case_id: str) -> Path:
    return repo_path("artifacts", "log_trace", f"{case_id}.jsonl")


def copy_fixture(case_id: str, output: Path | None = None) -> Path:
    source = fixture_trace_path(case_id)
    if not source.exists():
        raise PipelineError(f"Missing fixture trace for {case_id}: {source}")
    target = output or output_trace_path(case_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return target


def _receipt_to_records(case_id: str, role: str, receipt: Dict[str, Any]) -> List[Dict[str, Any]]:
    records = []
    tx_hash = receipt.get("transactionHash", "")
    block_number = int(receipt.get("blockNumber", "0x0"), 16)
    transaction_index = int(receipt.get("transactionIndex", "0x0"), 16)
    for log in receipt.get("logs", []):
        records.append(
            {
                "case": case_id,
                "event_type": "RAW_LOG",
                "role": role,
                "block_number": block_number,
                "tx_hash": tx_hash,
                "transaction_index": transaction_index,
                "log_index": int(log.get("logIndex", "0x0"), 16),
                "address": log.get("address"),
                "topics": log.get("topics", []),
                "data": log.get("data"),
                "decoded": {},
            }
        )
    return records


def collect_online(case_id: str, output: Path | None = None) -> Path:
    case = get_case(case_id)
    env = load_env()
    template = case.get("rpc_url_template")
    if not template:
        raise PipelineError(f"No rpc_url_template configured for case {case_id}.")
    rpc_url = resolve_template(template, env)
    known_txs = case.get("known_txs") or {}
    if not known_txs:
        raise PipelineError(
            f"No known_txs configured for {case_id}. Use --fixture or add seed transactions to config/cases.json."
        )
    records: List[Dict[str, Any]] = []
    for role, tx_hash in known_txs.items():
        print_status(f"Fetching receipt for {case_id}:{role}:{tx_hash}")
        receipt = rpc_call(rpc_url, "eth_getTransactionReceipt", [tx_hash])
        if not receipt:
            raise PipelineError(f"No receipt returned for {tx_hash}")
        records.extend(_receipt_to_records(case_id, role, receipt))
    target = output or output_trace_path(case_id)
    write_jsonl(target, sorted(records, key=lambda item: (item["block_number"], item["transaction_index"], item["log_index"])))
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect and normalize logs for a case.")
    parser.add_argument("--case", required=True)
    parser.add_argument("--from-block", type=int, default=None)
    parser.add_argument("--to-block", type=int, default=None)
    parser.add_argument("--fixture", action="store_true", help="Use deterministic fixture trace.")
    parser.add_argument("--output", default="", help="Optional output JSONL path for test isolation.")
    args = parser.parse_args()
    try:
        output_path = Path(args.output) if args.output else None
        if args.fixture:
            output = copy_fixture(args.case, output_path)
        else:
            output = collect_online(args.case, output_path)
    except PipelineError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Wrote log trace: {output}")


if __name__ == "__main__":
    main()
