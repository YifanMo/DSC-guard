#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from common import (
    PipelineError,
    ensure_dir,
    load_cases,
    load_env,
    read_jsonl,
    repo_path,
    resolve_template,
    rpc_call,
    write_json,
)


ALLOWED_TIERS = {"A_replayable", "B_high_confidence_incomplete"}
FALLBACK_RPC_TEMPLATES = {
    "ethereum": "https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_KEY}",
    "bnb": "https://bnb-mainnet.g.alchemy.com/v2/{ALCHEMY_KEY}",
    "bsc": "https://bnb-mainnet.g.alchemy.com/v2/{ALCHEMY_KEY}",
    "base": "https://base-mainnet.g.alchemy.com/v2/{ALCHEMY_KEY}",
    "arbitrum": "https://arb-mainnet.g.alchemy.com/v2/{ALCHEMY_KEY}",
    "optimism": "https://opt-mainnet.g.alchemy.com/v2/{ALCHEMY_KEY}",
    "polygon": "https://polygon-mainnet.g.alchemy.com/v2/{ALCHEMY_KEY}",
    "avalanche": "https://avax-mainnet.g.alchemy.com/v2/{ALCHEMY_KEY}",
    "avalanche_c": "https://avax-mainnet.g.alchemy.com/v2/{ALCHEMY_KEY}",
    "scroll": "https://scroll-mainnet.g.alchemy.com/v2/{ALCHEMY_KEY}",
}


def _load_queue(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise PipelineError(f"Missing materialization queue: {path}")
    return read_jsonl(path)


def _eligible(row: Dict[str, Any]) -> bool:
    return row.get("evidence_tier") in ALLOWED_TIERS


def _estimate(row: Dict[str, Any]) -> Dict[str, Any]:
    receipt_bundles = int(row.get("estimated_total_rpc_requests") or 0)
    return {
        "candidate_id": row.get("candidate_id", ""),
        "chain": row.get("chain", ""),
        "failure_class": row.get("failure_class", ""),
        "evidence_tier": row.get("evidence_tier", ""),
        "trigger_tx": row.get("trigger_tx", ""),
        "estimated_trigger_receipts": int(row.get("estimated_trigger_receipts") or 1),
        "estimated_impact_receipts": int(row.get("estimated_impact_receipts") or 0),
        "estimated_abi_requests": int(row.get("estimated_abi_requests") or 0),
        "estimated_receipt_bundles": receipt_bundles,
        "estimated_total_rpc_requests": receipt_bundles * 3,
        "action": row.get("materialization_action", "download_minimal_causal_trace"),
    }


def _rpc_url_for_chain(chain: str) -> str:
    cases = load_cases()
    env = load_env()
    for case in cases.values():
        if case.get("chain") == chain and case.get("rpc_url_template"):
            return resolve_template(case["rpc_url_template"], env)
    template = FALLBACK_RPC_TEMPLATES.get(chain)
    if not template:
        raise PipelineError(f"No RPC template configured for broad-search chain: {chain}")
    return resolve_template(template, env)


def _receipt_bundle(rpc_url: str, tx_hash: str) -> Dict[str, Any]:
    receipt = rpc_call(rpc_url, "eth_getTransactionReceipt", [tx_hash], timeout=60)
    if not receipt:
        raise PipelineError(f"No receipt returned for broad-search tx {tx_hash}")
    tx = rpc_call(rpc_url, "eth_getTransactionByHash", [tx_hash], timeout=60)
    if not tx:
        raise PipelineError(f"No transaction returned for broad-search tx {tx_hash}")
    block = rpc_call(rpc_url, "eth_getBlockByNumber", [receipt["blockNumber"], False], timeout=60)
    if not block:
        raise PipelineError(f"No block returned for broad-search tx {tx_hash}")
    return {"receipt": receipt, "transaction": tx, "block": block}


def _materialize_candidate(row: Dict[str, Any], out_dir: Path, *, resume: bool = False) -> Dict[str, Any]:
    ensure_dir(out_dir)
    output = out_dir / f"{row.get('candidate_id', 'candidate')}.json"
    if resume and output.exists():
        return {"candidate_id": row.get("candidate_id", ""), "output": str(output), "status": "skipped_existing"}
    chain = row.get("chain", "")
    rpc_url = _rpc_url_for_chain(chain)
    tx_hashes = [row.get("trigger_tx", "")]
    tx_hashes.extend(row.get("impact_txs") or [])
    tx_hashes = [tx for tx in dict.fromkeys(tx_hashes) if tx]
    if not tx_hashes:
        raise PipelineError(f"Candidate has no tx hashes to materialize: {row.get('candidate_id')}")
    bundles = {tx_hash: _receipt_bundle(rpc_url, tx_hash) for tx_hash in tx_hashes}
    slice_data = {
        "candidate_id": row.get("candidate_id", ""),
        "scope": "read-only historical broad-search evidence slice",
        "contains_api_keys": False,
        "contains_rpc_url": False,
        "candidate": row,
        "rpc_methods": ["eth_getTransactionReceipt", "eth_getTransactionByHash", "eth_getBlockByNumber"],
        "transactions": bundles,
    }
    write_json(output, slice_data)
    return {"candidate_id": row.get("candidate_id", ""), "output": str(output), "status": "materialized", "tx_count": len(tx_hashes)}


def run_queue(
    queue_path: Path,
    *,
    dry_run: bool = True,
    allow_rpc_fill: bool = False,
    candidate_limit: Optional[int] = None,
    max_rpc_requests: Optional[int] = None,
    max_abi_requests: Optional[int] = None,
    resume: bool = False,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    queue = _load_queue(queue_path)
    eligible = [row for row in queue if _eligible(row)]
    skipped = [row for row in queue if not _eligible(row)]
    selected = eligible if candidate_limit is None else eligible[:candidate_limit]
    base_output_dir = output_dir or repo_path("artifacts", "broad_search")
    out_dir = base_output_dir / "evidence_slices"
    selected_for_download = [
        row for row in selected if not (resume and (out_dir / f"{row.get('candidate_id', 'candidate')}.json").exists())
    ]
    estimates = [_estimate(row) for row in selected_for_download]
    estimated_rpc_requests = sum(item["estimated_total_rpc_requests"] for item in estimates)
    estimated_abi_requests = sum(item["estimated_abi_requests"] for item in estimates)
    budget_exceeded = {
        "rpc": max_rpc_requests is not None and estimated_rpc_requests > max_rpc_requests,
        "abi": max_abi_requests is not None and estimated_abi_requests > max_abi_requests,
    }
    if allow_rpc_fill and not dry_run and any(budget_exceeded.values()):
        raise PipelineError(
            "Broad-search materialization budget exceeded: "
            f"estimated_rpc_requests={estimated_rpc_requests}, max_rpc_requests={max_rpc_requests}, "
            f"estimated_abi_requests={estimated_abi_requests}, max_abi_requests={max_abi_requests}"
        )
    result: Dict[str, Any] = {
        "mode": "dry_run" if dry_run or not allow_rpc_fill else "rpc_fill",
        "queue_path": str(queue_path),
        "queue_count": len(queue),
        "eligible_count": len(eligible),
        "skipped_count": len(skipped),
        "selected_count": len(selected),
        "candidate_limit": candidate_limit,
        "selection_policy": "all_gate_eligible_candidates" if candidate_limit is None else "operational_debug_limit_not_dataset_scope",
        "resume": resume,
        "already_materialized_count": len(selected) - len(selected_for_download),
        "selected_for_download_count": len(selected_for_download),
        "estimated_rpc_requests": estimated_rpc_requests,
        "estimated_abi_requests": estimated_abi_requests,
        "max_rpc_requests": max_rpc_requests,
        "max_abi_requests": max_abi_requests,
        "budget_exceeded": budget_exceeded,
        "selected": estimates,
        "skipped_candidate_ids": [row.get("candidate_id", "") for row in skipped],
        "safety": {
            "no_open_ended_getlogs": True,
            "no_write_calls": True,
            "no_private_keys": True,
            "historical_known_tx_receipts_only": True,
        },
    }
    if allow_rpc_fill and not dry_run:
        materialized = []
        errors = []
        for row in selected:
            try:
                materialized.append(_materialize_candidate(row, out_dir, resume=resume))
            except PipelineError as exc:
                errors.append({"candidate_id": row.get("candidate_id", ""), "error": str(exc)})
        result["materialized"] = materialized
        result["errors"] = errors
    output = base_output_dir / "materialization_dry_run.json"
    if allow_rpc_fill and not dry_run:
        output = base_output_dir / "materialization_run.json"
    write_json(output, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run or materialize broad-search local evidence queue.")
    parser.add_argument("--queue", default=str(repo_path("artifacts", "broad_search", "materialization_queue.jsonl")))
    parser.add_argument("--dry-run", action="store_true", default=True, help="Estimate request counts only; default behavior.")
    parser.add_argument("--allow-rpc-fill", action="store_true", help="Explicitly allow bounded read-only receipt/tx/block downloads.")
    parser.add_argument("--execute", action="store_true", help="Use with --allow-rpc-fill to perform downloads.")
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=None,
        help="Optional operational debug cap. Omit for the gate-only dataset queue.",
    )
    parser.add_argument("--max-rpc-requests", type=int, default=None)
    parser.add_argument("--max-abi-requests", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    try:
        result = run_queue(
            Path(args.queue),
            dry_run=not (args.allow_rpc_fill and args.execute),
            allow_rpc_fill=args.allow_rpc_fill,
            candidate_limit=args.candidate_limit,
            max_rpc_requests=args.max_rpc_requests,
            max_abi_requests=args.max_abi_requests,
            resume=args.resume,
        )
    except PipelineError as exc:
        raise SystemExit(str(exc)) from exc
    print("Broad-search materialization queue summary:")
    print(f"- mode: {result['mode']}")
    print(f"- eligible candidates: {result['eligible_count']}")
    print(f"- selected candidates: {result['selected_count']}")
    print(f"- candidates needing download: {result['selected_for_download_count']}")
    print(f"- estimated RPC requests: {result['estimated_rpc_requests']}")
    print(f"- estimated ABI requests: {result['estimated_abi_requests']}")


if __name__ == "__main__":
    main()
