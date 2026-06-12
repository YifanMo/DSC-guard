#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from common import (
    PipelineError,
    ensure_dir,
    get_case,
    load_env,
    repo_path,
    resolve_template,
    rpc_call,
    write_json,
    write_jsonl,
)
from materialize_feed_binding_case import _hex_to_int, _norm_addr, transfer_flow_summary


CASE_ID = "moonwell_wrseth"
ATTACKER_CONTRACT = "0x42ecd332d47c91cbc83b39bd7f53cebe5e9734bb"
ATTACKER_EOA = "0x6997a8c804642ae2de16d7b8ff09565a5d5658ff"
ETH_USD_ORACLE = "0x71041dddad3595f9ced3dccfbe3d1f4b0a16bb70"
WRSETH_ETH_ORACLE = "0xd7221b10fbbc1e1ba95fd0b4d031c15f7f365296"
MALFUNCTION_TIME = "2025-11-04T05:44:55Z"
MALFUNCTION_RATE = "1649934.60732"
PUBLIC_BAD_DEBT_USD = "3700000"
FORUM_URL = "https://forum.moonwell.fi/t/wrseth-oracle-malfunction-11-4-25/2017"
EVIDENCE_QUALITY_OFFLINE = "moonwell_forum_canonical_seed"
EVIDENCE_QUALITY_RPC = "moonwell_forum_seed_plus_rpc_receipt"

ATTACK_TXS = [
    ("0x229caeb87e0b6c31afad950150d2ba05a8d7fe823c9e5c05af63b4150b8f6cc6", "cbXRP", "1206000"),
    ("0xecb1c96e15889dc11d2928f6e63e34abcb8b1114bd69f15a794fa4df07f647aa", "EURC", "80000"),
    ("0x7855a861bb27ba93aac37ec60e2de3381c46f82070dc4d300aca70ee05cc69ec", "EURC", "73300"),
    ("0xc5daf8bfea0b7f6c5da8e4b08e19df2be58094a366aa2387e9b9443fb0e0c0d4", "USDC", "80000"),
    ("0xa5f60967fc6ad8c0f5b82f1a12970371333c16d8dddee5cd3a4f8a95561769fd", "AERO", "101000"),
    ("0x815715adbf5032d1b968d5fda6c3589d2f4d3ab0b7a12c42f7f6a3cddbf99ff9", "AERO", "101000"),
    ("0x190a491c0ef095d5447d6d813dc8e2ec11a5710e189771c24527393a2beb05ac", "wstETH", "21"),
    ("0xff3075de35647efed753a918d20a92d9113e14a86a6dc98064b94249d14a54c1", "wstETH", "20.5"),
    ("0x76911abc581204db6063763b024de0bf7bb1bbb62f61dc81be3bac4bc9e474b2", "wstETH", "20.5"),
    ("0x5cd5b182e8be9e13360970d851f2479376f9de30f9f07dda617e6deba5e72ca4", "wstETH", "20"),
    ("0xd74224baa38bb6872769d43469aea69f45683281ca475c658338f2c08e5f412d", "cbETH", "24"),
    ("0x26abab9dd1119f13ba4899cea1d5875e3c5286427732a4eb7143aa44485cf6e0", "cbETH", "24"),
]


@dataclass
class RequestBudget:
    max_rpc: int
    rpc_used: int = 0

    def use_rpc(self) -> None:
        if self.rpc_used + 1 > self.max_rpc:
            raise PipelineError(f"RPC request budget exceeded: {self.rpc_used + 1}>{self.max_rpc}")
        self.rpc_used += 1


def _parse_time(value: str) -> datetime:
    clean = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(clean).astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _unix(value: str) -> int:
    return int(_parse_time(value).timestamp())


def _rpc(rpc_url: str, method: str, params: List[Any], budget: RequestBudget, attempts: int = 3) -> Any:
    last_error: Optional[Exception] = None
    for attempt in range(attempts):
        budget.use_rpc()
        try:
            return rpc_call(rpc_url, method, params, timeout=60)
        except Exception as exc:  # pragma: no cover - provider failures vary
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1)
    raise PipelineError(f"Read-only RPC request failed for {method}: {last_error}") from last_error


def _tx_summary(receipt: Dict[str, Any], tx: Dict[str, Any], block: Dict[str, Any]) -> Dict[str, Any]:
    timestamp = _hex_to_int(block.get("timestamp"))
    return {
        "hash": (tx.get("hash") or receipt.get("transactionHash") or "").lower(),
        "from": _norm_addr(tx.get("from", "")) if tx.get("from") else "",
        "to": _norm_addr(tx.get("to", "")) if tx.get("to") else "",
        "block_number": _hex_to_int(receipt.get("blockNumber")),
        "block_timestamp": timestamp,
        "block_time": _iso(datetime.fromtimestamp(timestamp, timezone.utc)) if timestamp else "",
        "transaction_index": _hex_to_int(receipt.get("transactionIndex")),
        "status": _hex_to_int(receipt.get("status", "0x0")),
        "log_count": len(receipt.get("logs") or []),
    }


def _collect_rpc_evidence(max_rpc_requests: int) -> Dict[str, Any]:
    case = get_case(CASE_ID)
    rpc_url = resolve_template(case["rpc_url_template"], load_env())
    budget = RequestBudget(max_rpc=max_rpc_requests)
    raw_transactions: Dict[str, Dict[str, Any]] = {}
    summaries: Dict[str, Dict[str, Any]] = {}
    for tx_hash, _, _ in ATTACK_TXS:
        receipt = _rpc(rpc_url, "eth_getTransactionReceipt", [tx_hash], budget)
        if not receipt:
            raise PipelineError(f"No receipt returned for Moonwell wrsETH tx {tx_hash}")
        tx = _rpc(rpc_url, "eth_getTransactionByHash", [tx_hash], budget)
        if not tx:
            raise PipelineError(f"No transaction returned for Moonwell wrsETH tx {tx_hash}")
        block = _rpc(rpc_url, "eth_getBlockByNumber", [receipt.get("blockNumber"), False], budget)
        if not block:
            raise PipelineError(f"No block returned for Moonwell wrsETH tx {tx_hash}")
        raw_transactions[tx_hash] = {"transaction": tx, "receipt": receipt, "block": block}
        summaries[tx_hash] = _tx_summary(receipt, tx, block)
    return {
        "tx_summaries": summaries,
        "raw_evidence": {
            "case": CASE_ID,
            "chain": "base",
            "mode": "rpc",
            "scope": "raw read-only Base RPC evidence for Moonwell wrsETH attack transactions",
            "contains_api_keys": False,
            "contains_rpc_url": False,
            "rpc_methods": ["eth_getTransactionReceipt", "eth_getTransactionByHash", "eth_getBlockByNumber"],
            "transactions": raw_transactions,
        },
        "request_budget": {"rpc_used": budget.rpc_used, "rpc_max": budget.max_rpc},
    }


def _default_position(index: int) -> Dict[str, Any]:
    start = _parse_time(MALFUNCTION_TIME)
    event_time = start + timedelta(seconds=index)
    return {
        "block_number": 0,
        "block_timestamp": int(event_time.timestamp()),
        "block_time": _iso(event_time),
        "transaction_index": index,
        "receipt_status": None,
        "evidence_quality": EVIDENCE_QUALITY_OFFLINE,
    }


def _position(tx_hash: str, index: int, rpc_evidence: Dict[str, Any]) -> Dict[str, Any]:
    summary = (rpc_evidence.get("tx_summaries") or {}).get(tx_hash)
    if not summary:
        return _default_position(index)
    return {
        "block_number": summary["block_number"],
        "block_timestamp": summary["block_timestamp"],
        "block_time": summary["block_time"],
        "transaction_index": summary["transaction_index"],
        "receipt_status": summary["status"],
        "evidence_quality": EVIDENCE_QUALITY_RPC,
    }


def _flow_for_tx(tx_hash: str, rpc_evidence: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_tx = ((rpc_evidence.get("raw_evidence") or {}).get("transactions") or {}).get(tx_hash) or {}
    receipt = raw_tx.get("receipt") or {}
    if not receipt:
        return []
    return transfer_flow_summary(receipt, "base", ATTACKER_CONTRACT, "moonwell_wrseth")


def build_attack_rows(rpc_evidence: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, (tx_hash, asset, amount) in enumerate(ATTACK_TXS, start=1):
        pos = _position(tx_hash, index, rpc_evidence)
        rows.append(
            {
                "case": CASE_ID,
                "tx_hash": tx_hash,
                "attack_tier": "lifecycle",
                "tx_role": "BORROW_AGAINST_OVERVALUED_WRSETH+SWAP_TO_WETH",
                "actor": ATTACKER_EOA,
                "executor_contract": ATTACKER_CONTRACT,
                "borrow_asset": asset,
                "borrow_amount_reported": amount,
                "block_number": pos["block_number"],
                "block_time": pos["block_time"],
                "transaction_index": pos["transaction_index"],
                "receipt_status": pos["receipt_status"],
                "evidence_source": pos["evidence_quality"],
                "source": FORUM_URL,
            }
        )
    return rows


def build_boundary_logs(attack_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ordered = sorted(attack_rows, key=lambda item: (item.get("block_time") or "", item.get("transaction_index") or 0))
    first_attack = ordered[0] if ordered else {}
    last_attack = ordered[-1] if ordered else {}
    return [
        {
            "case": CASE_ID,
            "boundary_type": "ORACLE_PRICE_MALFUNCTION_START",
            "tx_hash": "",
            "block_number": None,
            "block_time": MALFUNCTION_TIME,
            "actor": "",
            "target": WRSETH_ETH_ORACLE,
            "receipt_status": None,
            "reason": f"wrsETH/ETH feed reported 1 wrsETH = {MALFUNCTION_RATE} ETH.",
            "source": FORUM_URL,
        },
        {
            "case": CASE_ID,
            "boundary_type": "FIRST_CONFIRMED_ATTACK_TX",
            "tx_hash": first_attack.get("tx_hash", ""),
            "block_number": first_attack.get("block_number"),
            "block_time": first_attack.get("block_time", ""),
            "actor": first_attack.get("actor", ""),
            "target": first_attack.get("executor_contract", ""),
            "receipt_status": first_attack.get("receipt_status"),
            "reason": "First canonical forum-listed attack transaction.",
        },
        {
            "case": CASE_ID,
            "boundary_type": "LAST_CONFIRMED_ATTACK_TX",
            "tx_hash": last_attack.get("tx_hash", ""),
            "block_number": last_attack.get("block_number"),
            "block_time": last_attack.get("block_time", ""),
            "actor": last_attack.get("actor", ""),
            "target": last_attack.get("executor_contract", ""),
            "receipt_status": last_attack.get("receipt_status"),
            "reason": "Last canonical forum-listed attack transaction.",
        },
        {
            "case": CASE_ID,
            "boundary_type": "CAP_PAUSE_REMEDIATION_TX_NOT_CONFIRMED",
            "tx_hash": "",
            "block_number": None,
            "block_time": "",
            "actor": "",
            "target": "",
            "receipt_status": None,
            "reason": "Forum reports rapid cap changes and governance proposals, but local receipt-backed remediation txs are not yet identified.",
            "source": FORUM_URL,
        },
    ]


def build_trace_records(attack_rows: List[Dict[str, Any]], rpc_evidence: Dict[str, Any]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = [
        {
            "case": CASE_ID,
            "event_type": "ORACLE_PRICE_MALFUNCTION",
            "block_number": 0,
            "block_timestamp": _unix(MALFUNCTION_TIME),
            "transaction_index": 0,
            "log_index": 0,
            "tx_hash": "",
            "address": WRSETH_ETH_ORACLE,
            "decoded": {
                "asset": "wrsETH",
                "quote_asset": "ETH",
                "feed": WRSETH_ETH_ORACLE,
                "eth_usd_feed": ETH_USD_ORACLE,
                "reported_rate": MALFUNCTION_RATE,
                "expected_formula": "wrsETH/ETH * ETH/USD",
                "actual_fault": "wrsETH/ETH source reported an abnormal outlier value",
                "source": FORUM_URL,
                "evidence_quality": EVIDENCE_QUALITY_OFFLINE,
            },
        }
    ]
    for index, row in enumerate(attack_rows, start=1):
        flow = _flow_for_tx(row["tx_hash"], rpc_evidence)
        quality = EVIDENCE_QUALITY_RPC if row.get("receipt_status") is not None else EVIDENCE_QUALITY_OFFLINE
        records.append(
            {
                "case": CASE_ID,
                "event_type": "BORROW",
                "block_number": int(row.get("block_number") or 0),
                "block_timestamp": int(_parse_time(row["block_time"]).timestamp()) if row.get("block_time") else 0,
                "transaction_index": int(row.get("transaction_index") or index),
                "log_index": index,
                "tx_hash": row["tx_hash"],
                "address": row["executor_contract"],
                "decoded": {
                    "borrower": row["executor_contract"],
                    "actor": row["actor"],
                    "collateral_asset": "wrsETH",
                    "borrow_asset": row["borrow_asset"],
                    "borrow_amount": row["borrow_amount_reported"],
                    "borrow_amount_reported": row["borrow_amount_reported"],
                    "tx_role": row["tx_role"],
                    "source": FORUM_URL,
                    "evidence_quality": quality,
                    "transfer_flow_summary": flow,
                },
            }
        )
    return records


def build_findings(attack_rows: List[Dict[str, Any]], boundary_logs: List[Dict[str, Any]], rpc_evidence: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "case": CASE_ID,
        "name": "Moonwell wrsETH oracle malfunction",
        "chain": "base",
        "source": FORUM_URL,
        "scope": "read-only historical forensic materialization for the Moonwell wrsETH oracle malfunction",
        "identified_contracts": {
            "attacker_contract": ATTACKER_CONTRACT,
            "attacker_eoa": ATTACKER_EOA,
            "eth_usd_oracle": ETH_USD_ORACLE,
            "wrseth_eth_oracle": WRSETH_ETH_ORACLE,
        },
        "oracle_malfunction": {
            "asset": "wrsETH",
            "quote_asset": "ETH",
            "feed": WRSETH_ETH_ORACLE,
            "time": MALFUNCTION_TIME,
            "reported_rate": MALFUNCTION_RATE,
            "source": FORUM_URL,
        },
        "attack_txs": attack_rows,
        "boundary_logs": boundary_logs,
        "summary": {
            "attacker_count": 2,
            "attack_tx_count": len(attack_rows),
            "public_bad_debt_usd": PUBLIC_BAD_DEBT_USD,
            "borrowed_assets": sorted({row["borrow_asset"] for row in attack_rows}),
            "first_attack_time": boundary_logs[1]["block_time"],
            "last_attack_time": boundary_logs[2]["block_time"],
            "canonical_source": FORUM_URL,
        },
        "request_budget": rpc_evidence.get("request_budget", {"rpc_used": 0, "rpc_max": 0}),
        "full_artifacts": {
            "trace_jsonl": "artifacts/log_trace/moonwell_wrseth.jsonl",
            "attack_txs_jsonl": "artifacts/moonwell_wrseth_locator/attack_txs.jsonl",
            "raw_evidence_json": "artifacts/moonwell_wrseth_locator/raw_evidence.json",
        },
    }


def render_report(findings: Dict[str, Any]) -> str:
    summary = findings["summary"]
    oracle = findings["oracle_malfunction"]
    lines = [
        "# Moonwell wrsETH Oracle Malfunction",
        "",
        f"- Source: {FORUM_URL}",
        f"- Malfunction start: `{oracle['time']}`.",
        f"- Reported wrsETH/ETH rate: `{oracle['reported_rate']}`.",
        f"- Attackers: `2`.",
        f"- Canonical attack txs: `{summary['attack_tx_count']}`.",
        f"- Public bad debt reference: `${summary['public_bad_debt_usd']}`.",
        "",
        "## Artifacts",
        "",
        "- Trace: `artifacts/log_trace/moonwell_wrseth.jsonl`",
        "- Findings: `artifacts/moonwell_wrseth_locator/wrseth_findings.json`",
        "- Raw evidence: `artifacts/moonwell_wrseth_locator/raw_evidence.json`",
        "- Incident tables: `artifacts/incident_tables/moonwell_wrseth/`",
        "",
    ]
    return "\n".join(lines)


def materialize(*, allow_rpc_fill: bool, max_rpc_requests: int) -> Dict[str, Any]:
    rpc_evidence = (
        _collect_rpc_evidence(max_rpc_requests)
        if allow_rpc_fill
        else {
            "tx_summaries": {},
            "raw_evidence": {
                "case": CASE_ID,
                "chain": "base",
                "mode": "offline",
                "transactions": {},
                "contains_api_keys": False,
                "contains_rpc_url": False,
            },
            "request_budget": {"rpc_used": 0, "rpc_max": 0},
        }
    )
    attack_rows = build_attack_rows(rpc_evidence)
    boundary_logs = build_boundary_logs(attack_rows)
    trace_records = build_trace_records(attack_rows, rpc_evidence)
    findings = build_findings(attack_rows, boundary_logs, rpc_evidence)

    base = repo_path("artifacts", "moonwell_wrseth_locator")
    ensure_dir(base)
    write_jsonl(base / "attack_txs.jsonl", attack_rows)
    write_json(base / "wrseth_findings.json", findings)
    write_json(base / "raw_evidence.json", rpc_evidence["raw_evidence"])
    write_jsonl(repo_path("artifacts", "log_trace", "moonwell_wrseth.jsonl"), trace_records)
    report_path = repo_path("results", "moonwell_wrseth_locator.md")
    ensure_dir(report_path.parent)
    report_path.write_text(render_report(findings), encoding="utf-8")
    return {"findings": findings, "trace_records": trace_records}


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize Moonwell wrsETH oracle malfunction evidence.")
    parser.add_argument("--offline", action="store_true", help="Use canonical forum tx list without RPC.")
    parser.add_argument("--allow-rpc-fill", action="store_true", help="Fetch transaction receipts/blocks for canonical txs.")
    parser.add_argument("--max-rpc-requests", type=int, default=40)
    args = parser.parse_args()
    if args.offline and args.allow_rpc_fill:
        raise SystemExit("--offline and --allow-rpc-fill are mutually exclusive.")
    result = materialize(allow_rpc_fill=args.allow_rpc_fill and not args.offline, max_rpc_requests=args.max_rpc_requests)
    print("Wrote Moonwell wrsETH materialized artifacts:")
    print(f"- {repo_path('artifacts', 'moonwell_wrseth_locator', 'wrseth_findings.json')}")
    print(f"- {repo_path('artifacts', 'moonwell_wrseth_locator', 'attack_txs.jsonl')}")
    print(f"- {repo_path('artifacts', 'log_trace', 'moonwell_wrseth.jsonl')}")
    print(f"- trace_records={len(result['trace_records'])}")


if __name__ == "__main__":
    main()
