#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from common import (
    PipelineError,
    ensure_dir,
    get_case,
    load_env,
    read_jsonl,
    repo_path,
    resolve_template,
    rpc_call,
    write_json,
    write_jsonl,
)
from materialize_feed_binding_case import (
    _hex_to_int,
    _norm_addr,
    transfer_flow_summary,
)


CASE_ID = "moonwell_cbeth"
DUNE_EVIDENCE_QUALITY = "dune_decoded_event"
RPC_EVIDENCE_QUALITY = "rpc_receipt_backed"
FLOW_EVIDENCE_QUALITY = "receipt_flow_decoded"
MCBETH_BORROW_SOURCE = "dune:moonwell_base.mcbeth_evt_borrow"
LIQUIDATION_SOURCE = "dune:moonwell_base.*_evt_liquidateborrow"
ORACLE_SOURCE = "dune:moonwell_base.temporalgovernor_evt_executedtransaction"


@dataclass
class RequestBudget:
    max_rpc: int
    rpc_used: int = 0

    def use_rpc(self) -> None:
        if self.rpc_used + 1 > self.max_rpc:
            raise PipelineError(f"RPC request budget exceeded: {self.rpc_used + 1}>{self.max_rpc}")
        self.rpc_used += 1


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


def _parse_time(value: str) -> datetime:
    clean = (value or "").strip()
    if not clean:
        return datetime.fromtimestamp(0, timezone.utc)
    if clean.endswith(" UTC"):
        clean = clean[:-4].strip() + "+00:00"
    elif clean.endswith("Z"):
        clean = clean[:-1] + "+00:00"
    elif "+" not in clean and clean.count(":") >= 2:
        clean += "+00:00"
    return datetime.fromisoformat(clean).astimezone(timezone.utc)


def _unix(value: str) -> int:
    return int(_parse_time(value).timestamp())


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _fixture_like_address(value: str) -> bool:
    body = (value or "").lower().removeprefix("0x")
    return len(body) == 40 and len(set(body)) == 1


def _formula_constraint(case: Dict[str, Any]) -> Dict[str, Any]:
    for constraint in case.get("constraints", []):
        if constraint.get("type") == "formula_mismatch":
            return constraint
    raise PipelineError(f"Case {case['id']} has no formula_mismatch constraint.")


def _load_candidates(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise PipelineError(f"Missing Moonwell candidate artifact: {path}")
    return read_jsonl(path)


def _load_findings(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise PipelineError(f"Missing Moonwell Dune findings artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate_tx_hashes(candidate: Dict[str, Any]) -> List[str]:
    hashes = candidate.get("tx_hashes")
    if isinstance(hashes, list) and hashes:
        return [str(tx_hash) for tx_hash in hashes]
    representative = candidate.get("representative_tx")
    return [str(representative)] if representative else []


def _all_materialized_txs(findings: Dict[str, Any], candidates: List[Dict[str, Any]]) -> List[Tuple[str, str, Dict[str, Any]]]:
    txs: List[Tuple[str, str, Dict[str, Any]]] = []
    trigger_tx = ((findings.get("oracle_trigger") or {}).get("tx_hash") or "").lower()
    if trigger_tx:
        txs.append(("oracle_trigger", trigger_tx, findings.get("oracle_trigger") or {}))
    for candidate in candidates:
        role = str(candidate.get("candidate_type") or candidate.get("role") or "candidate")
        for tx_hash in _candidate_tx_hashes(candidate):
            txs.append((role, tx_hash.lower(), candidate))
    dedup: Dict[str, Tuple[str, str, Dict[str, Any]]] = {}
    for role, tx_hash, source in txs:
        if tx_hash:
            dedup.setdefault(tx_hash, (role, tx_hash, source))
    return list(dedup.values())


def _tx_summary(receipt: Dict[str, Any], tx: Dict[str, Any], block: Dict[str, Any]) -> Dict[str, Any]:
    timestamp = _hex_to_int(block.get("timestamp"))
    return {
        "hash": (tx.get("hash") or receipt.get("transactionHash") or "").lower(),
        "from": _norm_addr(tx.get("from", "")) if tx.get("from") else "",
        "to": _norm_addr(tx.get("to", "")) if tx.get("to") else "",
        "block_number": _hex_to_int(receipt.get("blockNumber")),
        "block_timestamp": timestamp,
        "block_time": datetime.fromtimestamp(timestamp, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z") if timestamp else "",
        "transaction_index": _hex_to_int(receipt.get("transactionIndex")),
        "status": _hex_to_int(receipt.get("status", "0x0")),
        "log_count": len(receipt.get("logs") or []),
        "raw_log_addresses": sorted(
            {_norm_addr(log.get("address", "")) for log in receipt.get("logs", []) if log.get("address")}
        ),
    }


def _collect_rpc_evidence(
    case: Dict[str, Any],
    findings: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    max_rpc_requests: int,
) -> Dict[str, Any]:
    env = load_env()
    rpc_url = resolve_template(case["rpc_url_template"], env)
    budget = RequestBudget(max_rpc=max_rpc_requests)
    raw_transactions: Dict[str, Dict[str, Any]] = {}
    tx_summaries: Dict[str, Dict[str, Any]] = {}

    for role, tx_hash, source in _all_materialized_txs(findings, candidates):
        receipt = _rpc(rpc_url, "eth_getTransactionReceipt", [tx_hash], budget)
        if not receipt:
            raise PipelineError(f"No receipt returned for Moonwell tx {tx_hash}")
        tx = _rpc(rpc_url, "eth_getTransactionByHash", [tx_hash], budget)
        if not tx:
            raise PipelineError(f"No transaction returned for Moonwell tx {tx_hash}")
        block_number = receipt.get("blockNumber")
        block = _rpc(rpc_url, "eth_getBlockByNumber", [block_number, False], budget)
        if not block:
            raise PipelineError(f"No block returned for Moonwell tx {tx_hash} block {block_number}")
        raw_transactions[tx_hash] = {
            "role": role,
            "source_candidate": {
                key: source.get(key)
                for key in ("candidate_type", "address", "representative_tx", "event_type", "block_number", "block_time")
                if isinstance(source, dict) and key in source
            },
            "transaction": tx,
            "receipt": receipt,
            "block": block,
        }
        tx_summaries[tx_hash] = _tx_summary(receipt, tx, block)

    return {
        "raw_evidence": _raw_evidence_snapshot("rpc", raw_transactions),
        "tx_summaries": tx_summaries,
        "request_budget": {"rpc_used": budget.rpc_used, "rpc_max": budget.max_rpc},
    }


def _raw_evidence_snapshot(mode: str, transactions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "case": CASE_ID,
        "chain": "base",
        "mode": mode,
        "scope": "raw read-only Base RPC evidence for Moonwell MIP-X43 trigger and candidate transactions",
        "contains_api_keys": False,
        "contains_rpc_url": False,
        "rpc_methods": ["eth_getTransactionReceipt", "eth_getTransactionByHash", "eth_getBlockByNumber"],
        "transactions": transactions,
    }


def _rpc_evidence_from_raw(raw_evidence: Dict[str, Any]) -> Dict[str, Any]:
    tx_summaries: Dict[str, Dict[str, Any]] = {}
    for tx_hash, item in (raw_evidence.get("transactions") or {}).items():
        receipt = item.get("receipt") or {}
        tx = item.get("transaction") or {}
        block = item.get("block") or {}
        if receipt and tx and block:
            tx_summaries[(tx_hash or tx.get("hash") or receipt.get("transactionHash") or "").lower()] = _tx_summary(receipt, tx, block)
    return {
        "raw_evidence": raw_evidence,
        "tx_summaries": tx_summaries,
        "request_budget": {
            "rpc_used": len(tx_summaries) * 3,
            "rpc_max": len(tx_summaries) * 3,
            "source": "existing_raw_evidence",
        },
    }


def _rpc_summary(tx_hash: str, rpc_evidence: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return (rpc_evidence.get("tx_summaries") or {}).get((tx_hash or "").lower())


def _flow_for_tx(tx_hash: str, address: str, protocol: str, raw_evidence: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_tx = ((raw_evidence.get("transactions") or {}).get((tx_hash or "").lower()) or {})
    receipt = raw_tx.get("receipt") or {}
    if not receipt:
        return []
    return transfer_flow_summary(receipt, "base", address, protocol)


def _quality_for_tx(tx_hash: str, flow: List[Dict[str, Any]], rpc_evidence: Dict[str, Any]) -> str:
    if flow:
        return FLOW_EVIDENCE_QUALITY
    if _rpc_summary(tx_hash, rpc_evidence):
        return RPC_EVIDENCE_QUALITY
    return DUNE_EVIDENCE_QUALITY


def _record_position(
    tx_hash: str,
    candidate: Dict[str, Any],
    sequence: int,
    rpc_evidence: Dict[str, Any],
) -> Dict[str, Any]:
    rpc = _rpc_summary(tx_hash, rpc_evidence)
    if rpc:
        return {
            "block_number": rpc["block_number"],
            "block_timestamp": rpc["block_timestamp"],
            "transaction_index": rpc["transaction_index"],
            "raw_log_addresses": rpc["raw_log_addresses"],
            "canonical_order_verified": True,
        }
    return {
        "block_number": int(candidate.get("block_number") or 0),
        "block_timestamp": _unix(candidate.get("block_time", "")),
        "transaction_index": sequence,
        "raw_log_addresses": [],
        "canonical_order_verified": False,
    }


def build_trace_records(
    case: Dict[str, Any],
    findings: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    rpc_evidence: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    rpc_evidence = rpc_evidence or {"tx_summaries": {}, "raw_evidence": _raw_evidence_snapshot("offline", {})}
    raw_evidence = rpc_evidence.get("raw_evidence") or {}
    constraint = _formula_constraint(case)
    trigger = findings.get("oracle_trigger") or {}
    contracts = findings.get("identified_contracts") or {}
    mcbeth_market = contracts.get("mcbeth_market", "")

    trigger_tx = trigger.get("tx_hash") or (case.get("known_txs") or {}).get("mip_x43_execute", "")
    trigger_rpc = _rpc_summary(trigger_tx, rpc_evidence)
    trigger_block_number = trigger_rpc["block_number"] if trigger_rpc else int(trigger.get("block_number") or 0)
    trigger_block_timestamp = trigger_rpc["block_timestamp"] if trigger_rpc else _unix(trigger.get("block_time", ""))
    trigger_tx_index = trigger_rpc["transaction_index"] if trigger_rpc else 0
    trigger_flow = _flow_for_tx(trigger_tx, trigger.get("governor", contracts.get("temporal_governor", "")), contracts.get("chainlink_oracle", ""), raw_evidence)
    trigger_quality = _quality_for_tx(trigger_tx, trigger_flow, rpc_evidence)

    records: List[Dict[str, Any]] = [
        {
            "case": CASE_ID,
            "event_type": "ORACLE_FORMULA_SET",
            "block_number": trigger_block_number,
            "block_timestamp": trigger_block_timestamp,
            "tx_hash": trigger_tx,
            "transaction_index": trigger_tx_index,
            "log_index": 0,
            "address": contracts.get("chainlink_oracle", ""),
            "decoded": {
                "asset": constraint.get("asset", "cbETH"),
                "expected_formula": constraint.get("expected_formula", trigger.get("expected_formula", "")),
                "actual_formula": trigger.get("actual_formula") or constraint.get("forbidden_formula", "cbETH/ETH"),
                "actor": trigger.get("actor", ""),
                "governor": contracts.get("temporal_governor", ""),
                "target": contracts.get("chainlink_oracle", ""),
                "selector": trigger.get("selector", ""),
                "selector_name": "setFeed(string,address)",
                "source": ORACLE_SOURCE,
                "evidence_quality": trigger_quality,
                "canonical_order_verified": bool(trigger_rpc),
                "raw_log_addresses": trigger_rpc.get("raw_log_addresses", []) if trigger_rpc else [],
                "transfer_flow_summary": trigger_flow,
            },
        }
    ]

    for candidate_index, candidate in enumerate(candidates, start=1):
        address = _norm_addr(candidate.get("address", ""))
        if _fixture_like_address(address):
            raise PipelineError(f"Refusing fixture-like Moonwell candidate address: {address}")
        if candidate.get("candidate_type") == "liquidator":
            tx_hash = candidate.get("representative_tx", "")
            flow = _flow_for_tx(tx_hash, address, mcbeth_market, raw_evidence)
            quality = _quality_for_tx(tx_hash, flow, rpc_evidence)
            pos = _record_position(tx_hash, candidate, candidate_index, rpc_evidence)
            records.append(
                {
                    "case": CASE_ID,
                    "event_type": "LIQUIDATE",
                    "block_number": pos["block_number"],
                    "block_timestamp": pos["block_timestamp"],
                    "tx_hash": tx_hash,
                    "transaction_index": pos["transaction_index"],
                    "log_index": candidate_index,
                    "address": LIQUIDATION_SOURCE if not pos["canonical_order_verified"] else mcbeth_market,
                    "decoded": {
                        "liquidator": address,
                        "borrower": _norm_addr(candidate.get("borrower", "")),
                        "collateral_asset": "cbETH",
                        "repay_market": candidate.get("repay_market", ""),
                        "repay_amount_raw": str(candidate.get("repay_amount_raw", "")),
                        "seized_mtoken_raw": str(candidate.get("seized_mtoken_raw", "")),
                        "seized_amount": f"{candidate.get('seized_mtoken_raw', '')} mcbETH-raw",
                        "source": LIQUIDATION_SOURCE,
                        "evidence_quality": quality,
                        "canonical_order_verified": pos["canonical_order_verified"],
                        "raw_log_addresses": pos["raw_log_addresses"],
                        "transfer_flow_summary": flow,
                    },
                }
            )
            continue

        if candidate.get("candidate_type") != "borrower":
            continue
        tx_hashes = _candidate_tx_hashes(candidate)
        representative_tx = str(candidate.get("representative_tx", ""))
        for tx_index, tx_hash in enumerate(tx_hashes, start=1):
            flow = _flow_for_tx(tx_hash, address, mcbeth_market, raw_evidence)
            quality = _quality_for_tx(tx_hash, flow, rpc_evidence)
            pos = _record_position(tx_hash, candidate, tx_index, rpc_evidence)
            local_amount = str(candidate.get("borrowed_cbeth", "")) if tx_hash == representative_tx or len(tx_hashes) == 1 else "unknown"
            amount_scope = "borrower_aggregate" if local_amount != "unknown" and len(tx_hashes) > 1 else "single_tx" if len(tx_hashes) == 1 else "not_available_in_local_candidate_artifact"
            records.append(
                {
                    "case": CASE_ID,
                    "event_type": "BORROW",
                    "block_number": pos["block_number"],
                    "block_timestamp": pos["block_timestamp"],
                    "tx_hash": tx_hash,
                    "transaction_index": pos["transaction_index"],
                    "log_index": tx_index,
                    "address": mcbeth_market,
                    "decoded": {
                        "borrower": address,
                        "collateral_asset": "non-cbETH collateral",
                        "borrow_asset": "cbETH",
                        "borrow_amount": local_amount,
                        "borrow_amount_scope": amount_scope,
                        "aggregate_borrowed_cbeth": str(candidate.get("borrowed_cbeth", "")),
                        "aggregate_tx_count": int(candidate.get("tx_count") or len(tx_hashes)),
                        "all_borrow_txs": tx_hashes,
                        "source": MCBETH_BORROW_SOURCE,
                        "evidence_quality": quality,
                        "canonical_order_verified": pos["canonical_order_verified"],
                        "raw_log_addresses": pos["raw_log_addresses"],
                        "transfer_flow_summary": flow,
                    },
                }
            )

    return sorted(
        records,
        key=lambda item: (
            int(item.get("block_number") or 0),
            int(item.get("transaction_index") or 0),
            int(item.get("log_index") or 0),
        ),
    )


def summarize(
    findings: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    records: List[Dict[str, Any]],
    rpc_evidence: Dict[str, Any],
) -> Dict[str, Any]:
    borrowers = [item for item in candidates if item.get("candidate_type") == "borrower"]
    liquidations = [item for item in candidates if item.get("candidate_type") == "liquidator"]
    dune_summary = findings.get("summary", {})
    total = dune_summary.get("total_borrowed_cbeth")
    if total in (None, ""):
        total = format(
            sum(Decimal(str(item.get("borrowed_cbeth", "0") or "0")) for item in borrowers),
            "f",
        ).rstrip("0").rstrip(".")
    borrow_txs = {tx for item in borrowers for tx in _candidate_tx_hashes(item)}
    transfer_flow_count = sum(len((record.get("decoded") or {}).get("transfer_flow_summary") or []) for record in records)
    return {
        "liquidation_count": len(liquidations),
        "borrower_count": len(borrowers),
        "borrow_tx_count": len(borrow_txs),
        "total_borrowed_cbeth": str(total),
        "raw_receipt_tx_count": len((rpc_evidence.get("raw_evidence") or {}).get("transactions") or {}),
        "transfer_flow_count": transfer_flow_count,
        "trace_records": len(records),
        "dune_summary": dune_summary,
    }


def build_materialized_evidence(
    case: Dict[str, Any],
    findings: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    records: List[Dict[str, Any]],
    rpc_evidence: Dict[str, Any],
    request_budget: Dict[str, Any],
) -> Dict[str, Any]:
    qualities = sorted(
        {
            str((record.get("decoded") or {}).get("evidence_quality"))
            for record in records
            if (record.get("decoded") or {}).get("evidence_quality")
        }
    )
    return {
        "case": CASE_ID,
        "case_name": case["name"],
        "chain": case["chain"],
        "scope": "read-only historical Moonwell cbETH oracle-consumption evidence materialization",
        "safety": {
            "no_write_calls": True,
            "no_private_keys": True,
            "no_open_ended_getlogs": True,
            "rpc_methods": ["eth_getTransactionReceipt", "eth_getTransactionByHash", "eth_getBlockByNumber"],
        },
        "evidence_quality": qualities,
        "request_budget": request_budget,
        "oracle_trigger": findings.get("oracle_trigger", {}),
        "identified_contracts": findings.get("identified_contracts", {}),
        "summary": summarize(findings, candidates, records, rpc_evidence),
        "candidates": candidates,
        "artifacts": {
            "candidates_jsonl": "artifacts/moonwell_cbeth_locator/moonwell_candidates_full.jsonl",
            "dune_findings": "artifacts/moonwell_cbeth_locator/dune_findings.json",
            "raw_evidence": "artifacts/moonwell_cbeth_locator/raw_evidence.json",
            "replay_trace": "artifacts/log_trace/moonwell_cbeth.jsonl",
            "locator_report": "results/moonwell_cbeth_locator.md",
        },
    }


def render_report(materialized: Dict[str, Any], raw_evidence: Dict[str, Any]) -> str:
    trigger = materialized.get("oracle_trigger") or {}
    contracts = materialized.get("identified_contracts") or {}
    summary = materialized.get("summary") or {}
    dune_summary = summary.get("dune_summary") or {}
    raw_txs = raw_evidence.get("transactions") or {}
    flow_count = int(summary.get("transfer_flow_count") or 0)
    quality = ", ".join(f"`{item}`" for item in materialized.get("evidence_quality") or [])
    return "\n".join(
        [
            "# Moonwell cbETH Full Trace Materialization",
            "",
            "## Safety scope",
            "",
            "- Scope: read-only historical reconstruction for the Moonwell cbETH / MIP-X43 oracle-consumption incident.",
            "- Default offline mode uses local Dune decoded artifacts only.",
            "- Optional RPC fill is limited to receipt, transaction, and block reads for already-known historical tx hashes.",
            "- No transaction construction, private keys, write calls, simulations, or open-ended `eth_getLogs` scans are used.",
            "",
            "## Evidence quality",
            "",
            f"- Status markers: {quality}.",
            f"- Raw receipt-backed tx count: `{summary.get('raw_receipt_tx_count')}`.",
            f"- Decoded ERC20 transfer flow count: `{flow_count}`.",
            "- Borrow amounts come from Dune decoded Moonwell event aggregates; per-tx amounts remain `unknown` when the local aggregate does not provide them.",
            "",
            "## Trigger closure",
            "",
            f"- MIP-X43 execution tx: `{trigger.get('tx_hash', '')}`.",
            f"- Temporal governor: `{contracts.get('temporal_governor', '')}`.",
            f"- Oracle target: `{contracts.get('chainlink_oracle', '')}`.",
            f"- Selector: `{trigger.get('selector', '')}` / `setFeed(string,address)`.",
            f"- Formula mismatch: expected `{trigger.get('expected_formula', 'cbETH/ETH * ETH/USD')}`, actual `{trigger.get('actual_formula', 'cbETH/ETH')}`.",
            "",
            "## Impact closure",
            "",
            f"- Liquidation records: `{summary.get('liquidation_count')}`.",
            f"- Borrower candidates: `{summary.get('borrower_count')}`.",
            f"- Borrow txs materialized: `{summary.get('borrow_tx_count')}`.",
            f"- Total decoded cbETH borrowed: `{summary.get('total_borrowed_cbeth')}`.",
            "",
            "## Full Dune event rescan",
            "",
            f"- Full decoded event rows: `{dune_summary.get('full_event_count', 'not_available')}`.",
            f"- Unique impact txs: `{dune_summary.get('full_unique_tx_count', 'not_available')}`.",
            f"- cbETH-collateral liquidation events: `{dune_summary.get('full_liquidation_event_count', 'not_available')}`.",
            f"- Dune-observed affected borrowers: `{dune_summary.get('full_affected_borrower_count', 'not_available')}` vs public affected borrowers `{dune_summary.get('public_affected_borrowers', 'not_available')}`.",
            f"- Public seized cbETH benchmark: `{dune_summary.get('public_seized_cbeth', 'not_available')}`; public bad debt benchmark USD `{dune_summary.get('public_bad_debt_usd', 'not_available')}`.",
            "- Residual gap: the public affected-borrower count is larger than the Dune liquidation/borrow event closure; keep this gap explicit instead of treating the 124 decoded rows as the complete public impact set.",
            "",
            "## Raw receipt closure",
            "",
            f"- Raw evidence artifact mode: `{raw_evidence.get('mode')}`.",
            f"- Raw tx snapshots saved: `{len(raw_txs)}`.",
            "- Snapshot stores receipt, transaction, and block payloads only; API keys and RPC URLs are not written.",
            "",
            "## Artifacts",
            "",
            "- Trace: `artifacts/log_trace/moonwell_cbeth.jsonl`",
            "- Materialized evidence: `artifacts/moonwell_cbeth_locator/moonwell_evidence.json`",
            "- Raw evidence: `artifacts/moonwell_cbeth_locator/raw_evidence.json`",
            "- Detection report: `results/moonwell_cbeth_detection.md`",
            "",
        ]
    )


def materialize(
    *,
    offline: bool = False,
    allow_rpc_fill: bool = False,
    max_rpc_requests: int = 80,
) -> Dict[str, Path]:
    case = get_case(CASE_ID)
    candidates_path = repo_path("artifacts", "moonwell_cbeth_locator", "moonwell_candidates_full.jsonl")
    findings_path = repo_path("artifacts", "moonwell_cbeth_locator", "dune_findings.json")
    evidence_path = repo_path("artifacts", "moonwell_cbeth_locator", "moonwell_evidence.json")
    raw_path = repo_path("artifacts", "moonwell_cbeth_locator", "raw_evidence.json")
    trace_path = repo_path("artifacts", "log_trace", "moonwell_cbeth.jsonl")
    report_path = repo_path("results", "moonwell_cbeth_locator.md")

    candidates = _load_candidates(candidates_path)
    findings = _load_findings(findings_path)

    if allow_rpc_fill and not offline:
        rpc_evidence = _collect_rpc_evidence(case, findings, candidates, max_rpc_requests)
        raw_evidence = rpc_evidence["raw_evidence"]
        request_budget = rpc_evidence["request_budget"]
    else:
        if raw_path.exists():
            raw_evidence = json.loads(raw_path.read_text(encoding="utf-8"))
            rpc_evidence = _rpc_evidence_from_raw(raw_evidence)
            request_budget = rpc_evidence["request_budget"]
        else:
            raw_evidence = _raw_evidence_snapshot("offline", {})
            rpc_evidence = {"raw_evidence": raw_evidence, "tx_summaries": {}}
            request_budget = {"rpc_used": 0, "rpc_max": max_rpc_requests}

    records = build_trace_records(case, findings, candidates, rpc_evidence)
    materialized = build_materialized_evidence(case, findings, candidates, records, rpc_evidence, request_budget)

    write_jsonl(trace_path, records)
    write_json(evidence_path, _json_safe(materialized))
    write_json(raw_path, _json_safe(raw_evidence))
    ensure_dir(report_path.parent)
    report_path.write_text(render_report(_json_safe(materialized), _json_safe(raw_evidence)), encoding="utf-8")
    return {"trace": trace_path, "evidence": evidence_path, "raw_evidence": raw_path, "report": report_path}


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize full Moonwell cbETH historical evidence trace.")
    parser.add_argument("--offline", action="store_true", help="Use local Dune artifacts only; do not call RPC.")
    parser.add_argument("--allow-rpc-fill", action="store_true", help="Allow bounded read-only Base RPC fill for known tx hashes.")
    parser.add_argument("--max-rpc-requests", type=int, default=80)
    args = parser.parse_args()

    try:
        outputs = materialize(
            offline=args.offline,
            allow_rpc_fill=args.allow_rpc_fill,
            max_rpc_requests=args.max_rpc_requests,
        )
    except PipelineError as exc:
        raise SystemExit(str(exc)) from exc

    print("Wrote Moonwell materialized artifacts:")
    for key, path in outputs.items():
        print(f"- {key}: {path}")


if __name__ == "__main__":
    main()
