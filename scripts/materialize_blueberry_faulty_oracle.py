#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from datetime import datetime, timezone
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


CASE_ID = "blueberry_faulty_oracle"
ATTACK_TX = "0xf0464b01d962f714eee9d4392b2494524d0e10ce3eb3723873afd1346b8b06e4"
ATTACKER_EOA = "0xc0ffeebabe5d496b2dde509f9fa189c25cf29671"
ATTACKER_CONTRACT = "0x3aa228a80f50763045bdfc45012da124bd0a6809"
SOURCE_URL = "https://medium.com/%40blueberryprotocol/2-22-24-exploit-post-mortem-6f6be7c1dcc3"
SECONDARY_SOURCE_URL = "https://learnblockchain.cn/article/7507"
BORROWING_ENABLED_TIME = "2024-02-22T08:36:00Z"
ATTACK_TIME = "2024-02-23T02:22:11Z"
FLASHLOAN_ASSET = "WETH"
FLASHLOAN_AMOUNT = "1"
REPORTED_PROCEEDS_ETH = "457"
REPORTED_RETURNED_ETH = "366.5"
REPORTED_PROTOCOL_RETAINED_ETH = "91.3"
EVIDENCE_QUALITY_OFFLINE = "blueberry_postmortem_canonical_seed"
EVIDENCE_QUALITY_RPC = "blueberry_postmortem_seed_plus_rpc_receipt"
TX_ROLE = "FLASHLOAN+SUPPLY_WETH+BORROW_UNDERPRICED_ASSETS+SWAP_TO_ETH"

BORROWED_ASSETS = [
    {"asset": "OHM", "amount": "8616.071267266"},
    {"asset": "USDC", "amount": "913262.603416"},
    {"asset": "WBTC", "amount": "6.866901"},
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
    receipt = _rpc(rpc_url, "eth_getTransactionReceipt", [ATTACK_TX], budget)
    if not receipt:
        raise PipelineError(f"No receipt returned for Blueberry tx {ATTACK_TX}")
    tx = _rpc(rpc_url, "eth_getTransactionByHash", [ATTACK_TX], budget)
    if not tx:
        raise PipelineError(f"No transaction returned for Blueberry tx {ATTACK_TX}")
    block = _rpc(rpc_url, "eth_getBlockByNumber", [receipt.get("blockNumber"), False], budget)
    if not block:
        raise PipelineError(f"No block returned for Blueberry tx {ATTACK_TX}")
    return {
        "tx_summaries": {ATTACK_TX: _tx_summary(receipt, tx, block)},
        "raw_evidence": {
            "case": CASE_ID,
            "chain": "ethereum",
            "mode": "rpc",
            "scope": "raw read-only Ethereum RPC evidence for the Blueberry canonical attack transaction",
            "contains_api_keys": False,
            "contains_rpc_url": False,
            "rpc_methods": ["eth_getTransactionReceipt", "eth_getTransactionByHash", "eth_getBlockByNumber"],
            "transactions": {ATTACK_TX: {"transaction": tx, "receipt": receipt, "block": block}},
        },
        "request_budget": {"rpc_used": budget.rpc_used, "rpc_max": budget.max_rpc},
    }


def _default_position() -> Dict[str, Any]:
    return {
        "block_number": 0,
        "block_timestamp": _unix(ATTACK_TIME),
        "block_time": ATTACK_TIME,
        "transaction_index": 0,
        "receipt_status": None,
        "evidence_quality": EVIDENCE_QUALITY_OFFLINE,
    }


def _position(rpc_evidence: Dict[str, Any]) -> Dict[str, Any]:
    summary = (rpc_evidence.get("tx_summaries") or {}).get(ATTACK_TX)
    if not summary:
        return _default_position()
    return {
        "block_number": summary["block_number"],
        "block_timestamp": summary["block_timestamp"],
        "block_time": summary["block_time"],
        "transaction_index": summary["transaction_index"],
        "receipt_status": summary["status"],
        "evidence_quality": EVIDENCE_QUALITY_RPC,
    }


def _flow_for_tx(rpc_evidence: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_tx = ((rpc_evidence.get("raw_evidence") or {}).get("transactions") or {}).get(ATTACK_TX) or {}
    receipt = raw_tx.get("receipt") or {}
    if not receipt:
        return []
    return transfer_flow_summary(receipt, "ethereum", ATTACKER_CONTRACT, ATTACKER_EOA)


def _borrow_amount_reported() -> str:
    return "; ".join(f"{item['amount']} {item['asset']}" for item in BORROWED_ASSETS)


def build_attack_rows(rpc_evidence: Dict[str, Any]) -> List[Dict[str, Any]]:
    pos = _position(rpc_evidence)
    return [
        {
            "case": CASE_ID,
            "tx_hash": ATTACK_TX,
            "attack_tier": "lifecycle",
            "tx_role": TX_ROLE,
            "actor": ATTACKER_EOA,
            "executor_contract": ATTACKER_CONTRACT,
            "flashloan_asset": FLASHLOAN_ASSET,
            "flashloan_amount": FLASHLOAN_AMOUNT,
            "borrow_assets": [item["asset"] for item in BORROWED_ASSETS],
            "borrow_amounts_reported": {item["asset"]: item["amount"] for item in BORROWED_ASSETS},
            "borrow_amount_reported": _borrow_amount_reported(),
            "proceeds_eth_reported": REPORTED_PROCEEDS_ETH,
            "block_number": pos["block_number"],
            "block_time": pos["block_time"],
            "transaction_index": pos["transaction_index"],
            "receipt_status": pos["receipt_status"],
            "evidence_source": pos["evidence_quality"],
            "source": SOURCE_URL,
        }
    ]


def build_boundary_logs(attack_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    attack = attack_rows[0] if attack_rows else {}
    return [
        {
            "case": CASE_ID,
            "boundary_type": "BORROWING_ENABLED_EARLY",
            "tx_hash": "",
            "block_number": None,
            "block_time": BORROWING_ENABLED_TIME,
            "actor": "",
            "target": "Blueberry Money Market",
            "receipt_status": None,
            "reason": "Post-mortem reports borrowers were allowed to borrow against collateral assets before the faulty oracle path was exploited.",
            "source": SOURCE_URL,
        },
        {
            "case": CASE_ID,
            "boundary_type": "FAULTY_ORACLE_DEPLOYMENT_ACTIVE",
            "tx_hash": "",
            "block_number": None,
            "block_time": BORROWING_ENABLED_TIME,
            "actor": "",
            "target": "PriceOracleProxy/CoreOracle path",
            "receipt_status": None,
            "reason": "Money Market consumed a faulty oracle implementation/decimal semantics path instead of the intended PriceOracleProxy semantics.",
            "source": SOURCE_URL,
        },
        {
            "case": CASE_ID,
            "boundary_type": "CORE_EXPLOIT_OR_RESCUE_TX",
            "tx_hash": attack.get("tx_hash", ""),
            "block_number": attack.get("block_number"),
            "block_time": attack.get("block_time", ""),
            "actor": attack.get("actor", ""),
            "target": attack.get("executor_contract", ""),
            "receipt_status": attack.get("receipt_status"),
            "reason": "Canonical transaction that flashloaned WETH, supplied it, borrowed OHM/USDC/WBTC, and swapped proceeds to ETH.",
            "source": SOURCE_URL,
        },
        {
            "case": CASE_ID,
            "boundary_type": "ORACLE_FIX_TX_NOT_CONFIRMED",
            "tx_hash": "",
            "block_number": None,
            "block_time": "",
            "actor": "",
            "target": "Blueberry oracle configuration",
            "receipt_status": None,
            "reason": "A receipt-backed oracle fix transaction is not yet identified in local artifacts.",
            "source": SOURCE_URL,
        },
        {
            "case": CASE_ID,
            "boundary_type": "PAUSE_TX_NOT_CONFIRMED",
            "tx_hash": "",
            "block_number": None,
            "block_time": "",
            "actor": "",
            "target": "Blueberry protocol controls",
            "receipt_status": None,
            "reason": "A receipt-backed pause/remediation transaction is not yet identified in local artifacts.",
            "source": SOURCE_URL,
        },
    ]


def build_trace_records(attack_rows: List[Dict[str, Any]], rpc_evidence: Dict[str, Any]) -> List[Dict[str, Any]]:
    flow = _flow_for_tx(rpc_evidence)
    attack = attack_rows[0]
    quality = EVIDENCE_QUALITY_RPC if attack.get("receipt_status") is not None else EVIDENCE_QUALITY_OFFLINE
    return [
        {
            "case": CASE_ID,
            "event_type": "ORACLE_IMPLEMENTATION_MISMATCH",
            "block_number": 0,
            "block_timestamp": _unix(BORROWING_ENABLED_TIME),
            "transaction_index": 0,
            "log_index": 0,
            "tx_hash": "",
            "address": "Blueberry Money Market",
            "decoded": {
                "asset": "WETH",
                "affected_borrow_assets": [item["asset"] for item in BORROWED_ASSETS],
                "expected_oracle": "PriceOracleProxy",
                "actual_oracle": "CoreOracle",
                "expected_semantics": "Money Market should consume normalized collateral and borrow-asset USD prices through the proxy.",
                "actual_semantics": "Money Market consumed CoreOracle 18-decimal scaled prices directly, underpricing OHM/USDC/WBTC borrow assets versus WETH collateral.",
                "actual_fault": "faulty oracle implementation/decimal semantics deployment",
                "source": SOURCE_URL,
                "evidence_quality": EVIDENCE_QUALITY_OFFLINE,
            },
        },
        {
            "case": CASE_ID,
            "event_type": "BORROW",
            "block_number": int(attack.get("block_number") or 0),
            "block_timestamp": int(_parse_time(attack["block_time"]).timestamp()) if attack.get("block_time") else 0,
            "transaction_index": int(attack.get("transaction_index") or 0),
            "log_index": 1,
            "tx_hash": attack["tx_hash"],
            "address": attack["executor_contract"],
            "decoded": {
                "borrower": attack["executor_contract"],
                "actor": attack["actor"],
                "collateral_asset": "WETH",
                "borrow_asset": "OHM+USDC+WBTC",
                "borrow_assets": attack["borrow_assets"],
                "borrow_amount": attack["borrow_amount_reported"],
                "borrow_amounts_reported": attack["borrow_amounts_reported"],
                "flashloan_asset": attack["flashloan_asset"],
                "flashloan_amount": attack["flashloan_amount"],
                "proceeds_eth_reported": attack["proceeds_eth_reported"],
                "tx_role": attack["tx_role"],
                "source": SOURCE_URL,
                "secondary_source": SECONDARY_SOURCE_URL,
                "evidence_quality": quality,
                "transfer_flow_summary": flow,
            },
        },
    ]


def build_findings(attack_rows: List[Dict[str, Any]], boundary_logs: List[Dict[str, Any]], rpc_evidence: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "case": CASE_ID,
        "name": "Blueberry Protocol faulty oracle deployment",
        "chain": "ethereum",
        "source": SOURCE_URL,
        "secondary_source": SECONDARY_SOURCE_URL,
        "scope": "read-only historical forensic materialization for the Blueberry faulty oracle deployment incident",
        "identified_contracts": {
            "attacker_eoa": ATTACKER_EOA,
            "attacker_contract": ATTACKER_CONTRACT,
        },
        "oracle_mismatch": {
            "asset": "WETH",
            "expected_oracle": "PriceOracleProxy",
            "actual_oracle": "CoreOracle",
            "semantic_dimension": "oracle_implementation_or_decimal_semantics_error",
            "time": BORROWING_ENABLED_TIME,
            "source": SOURCE_URL,
        },
        "attack_txs": attack_rows,
        "boundary_logs": boundary_logs,
        "summary": {
            "attacker_count": 2,
            "attack_tx_count": len(attack_rows),
            "borrowed_assets": BORROWED_ASSETS,
            "reported_proceeds_eth": REPORTED_PROCEEDS_ETH,
            "reported_returned_eth": REPORTED_RETURNED_ETH,
            "reported_protocol_retained_eth": REPORTED_PROTOCOL_RETAINED_ETH,
            "first_attack_time": attack_rows[0].get("block_time", "") if attack_rows else "",
            "last_attack_time": attack_rows[-1].get("block_time", "") if attack_rows else "",
            "canonical_source": SOURCE_URL,
        },
        "request_budget": rpc_evidence.get("request_budget", {"rpc_used": 0, "rpc_max": 0}),
        "full_artifacts": {
            "trace_jsonl": "artifacts/log_trace/blueberry_faulty_oracle.jsonl",
            "attack_txs_jsonl": "artifacts/blueberry_faulty_oracle_locator/attack_txs.jsonl",
            "raw_evidence_json": "artifacts/blueberry_faulty_oracle_locator/raw_evidence.json",
        },
    }


def render_report(findings: Dict[str, Any]) -> str:
    summary = findings["summary"]
    return "\n".join(
        [
            "# Blueberry Faulty Oracle Deployment",
            "",
            f"- Source: {SOURCE_URL}",
            f"- Borrowing enabled marker: `{BORROWING_ENABLED_TIME}`.",
            f"- Canonical attack tx: `{ATTACK_TX}`.",
            f"- Attackers under broad actor scope: `2`.",
            f"- Canonical attack txs: `{summary['attack_tx_count']}`.",
            f"- Reported proceeds: `{summary['reported_proceeds_eth']} ETH`.",
            "",
            "## Artifacts",
            "",
            "- Trace: `artifacts/log_trace/blueberry_faulty_oracle.jsonl`",
            "- Findings: `artifacts/blueberry_faulty_oracle_locator/blueberry_findings.json`",
            "- Raw evidence: `artifacts/blueberry_faulty_oracle_locator/raw_evidence.json`",
            "- Incident tables: `artifacts/incident_tables/blueberry_faulty_oracle/`",
            "",
        ]
    )


def materialize(*, allow_rpc_fill: bool, max_rpc_requests: int) -> Dict[str, Any]:
    rpc_evidence = (
        _collect_rpc_evidence(max_rpc_requests)
        if allow_rpc_fill
        else {
            "tx_summaries": {},
            "raw_evidence": {
                "case": CASE_ID,
                "chain": "ethereum",
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

    base = repo_path("artifacts", "blueberry_faulty_oracle_locator")
    ensure_dir(base)
    write_jsonl(base / "attack_txs.jsonl", attack_rows)
    write_json(base / "blueberry_findings.json", findings)
    write_json(base / "raw_evidence.json", rpc_evidence["raw_evidence"])
    write_jsonl(repo_path("artifacts", "log_trace", "blueberry_faulty_oracle.jsonl"), trace_records)
    report_path = repo_path("results", "blueberry_faulty_oracle_locator.md")
    ensure_dir(report_path.parent)
    report_path.write_text(render_report(findings), encoding="utf-8")
    return {"findings": findings, "trace_records": trace_records}


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize Blueberry faulty oracle deployment evidence.")
    parser.add_argument("--offline", action="store_true", help="Use canonical post-mortem tx list without RPC.")
    parser.add_argument("--allow-rpc-fill", action="store_true", help="Fetch transaction receipt/block for the canonical tx.")
    parser.add_argument("--max-rpc-requests", type=int, default=6)
    args = parser.parse_args()
    if args.offline and args.allow_rpc_fill:
        raise SystemExit("--offline and --allow-rpc-fill are mutually exclusive.")
    result = materialize(allow_rpc_fill=args.allow_rpc_fill and not args.offline, max_rpc_requests=args.max_rpc_requests)
    print("Wrote Blueberry materialized artifacts:")
    print(f"- {repo_path('artifacts', 'blueberry_faulty_oracle_locator', 'blueberry_findings.json')}")
    print(f"- {repo_path('artifacts', 'blueberry_faulty_oracle_locator', 'attack_txs.jsonl')}")
    print(f"- {repo_path('artifacts', 'log_trace', 'blueberry_faulty_oracle.jsonl')}")
    print(f"- trace_records={len(result['trace_records'])}")


if __name__ == "__main__":
    main()
