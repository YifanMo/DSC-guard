#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from eth_utils import event_abi_to_log_topic
from web3 import Web3
from web3._utils.events import get_event_data

from common import (
    PipelineError,
    ensure_dir,
    get_case,
    http_json,
    load_env,
    read_json,
    read_jsonl,
    repo_path,
    resolve_template,
    rpc_call,
    write_json,
    write_jsonl,
)
from materialize_feed_binding_case import _hex_to_int, _norm_addr
from verify_trace import Verifier


DEFAULT_OUTPUT_DIR = repo_path("artifacts", "eval_dataset", "materialized_unknown_negative")
DEFAULT_RESULTS_DIR = repo_path("results")
ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
_CACHE_LOCK = threading.Lock()


@dataclass
class RequestBudget:
    max_rpc: int
    max_source: int
    max_debug_trace: int = 0
    rpc_used: int = 0
    source_used: int = 0
    debug_trace_used: int = 0
    lock: Any = field(default_factory=threading.Lock, repr=False)

    def use_rpc(self) -> None:
        with self.lock:
            if self.rpc_used + 1 > self.max_rpc:
                raise PipelineError(f"RPC request budget exceeded: {self.rpc_used + 1}>{self.max_rpc}")
            self.rpc_used += 1

    def use_source(self) -> None:
        with self.lock:
            if self.source_used + 1 > self.max_source:
                raise PipelineError(f"Explorer/source request budget exceeded: {self.source_used + 1}>{self.max_source}")
            self.source_used += 1

    def use_debug_trace(self) -> None:
        with self.lock:
            if self.debug_trace_used + 1 > self.max_debug_trace:
                raise PipelineError(
                    f"Debug trace request budget exceeded: {self.debug_trace_used + 1}>{self.max_debug_trace}"
                )
            self.debug_trace_used += 1


def _rpc(rpc_url: str, method: str, params: List[Any], budget: RequestBudget, attempts: int = 3) -> Any:
    last_error: Optional[Exception] = None
    for attempt in range(attempts):
        budget.use_rpc()
        try:
            return rpc_call(rpc_url, method, params, timeout=60)
        except Exception as exc:  # pragma: no cover - provider failures vary.
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1)
    raise PipelineError(f"Read-only RPC request failed for {method}: {last_error}") from last_error


def _safe_file_id(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    text = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value)[:80].strip("_")
    return f"{text}_{digest}" if text else digest


def _cache_key(method: str, params: Sequence[Any]) -> str:
    payload = json.dumps({"method": method, "params": list(params)}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _rpc_cached(
    rpc_url: str,
    method: str,
    params: List[Any],
    budget: RequestBudget,
    cache_dir: Path,
    memory_cache: Dict[Tuple[str, str], Any],
) -> Any:
    key = (method, _cache_key(method, params))
    with _CACHE_LOCK:
        if key in memory_cache:
            return memory_cache[key]
    cache_path = cache_dir / "rpc" / method / f"{key[1]}.json"
    if cache_path.exists():
        payload = read_json(cache_path)
        result = payload.get("result") if isinstance(payload, dict) else None
        with _CACHE_LOCK:
            memory_cache[key] = result
        return result
    result = _rpc(rpc_url, method, params, budget)
    with _CACHE_LOCK:
        if not cache_path.exists():
            write_json(
                cache_path,
                {
                    "method": method,
                    "params": params,
                    "result": result,
                    "contains_api_keys": False,
                    "contains_rpc_url": False,
                },
            )
        memory_cache[key] = result
    return result


def _load_samples(input_paths: Sequence[Path], labels: set[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str, str]] = set()
    for path in input_paths:
        if not path.exists():
            continue
        for row in read_jsonl(path):
            if row.get("label") not in labels:
                continue
            key = (
                str(row.get("case_related_to") or ""),
                str(row.get("tx_hash") or "").lower(),
                str(row.get("topic0") or "").lower(),
            )
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def _block_timestamp(block: Dict[str, Any]) -> int:
    return _hex_to_int(block.get("timestamp", "0x0"))


def _topic_address(topic: str) -> str:
    return _norm_addr((topic or "0x")[-40:])


def _event_signature_map(abi: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    mapping: Dict[str, Dict[str, Any]] = {}
    for item in abi:
        if not isinstance(item, dict) or item.get("type") != "event":
            continue
        try:
            mapping["0x" + event_abi_to_log_topic(item).hex()] = item
        except Exception:
            continue
    return mapping


def _safe_decode_log(event_abi: Dict[str, Any], log: Dict[str, Any]) -> Dict[str, Any]:
    try:
        decoded = get_event_data(Web3().codec, event_abi, log)
    except Exception as exc:
        return {"decode_error": str(exc), "event_name": event_abi.get("name", "")}
    args = {}
    for key, value in dict(decoded.get("args", {})).items():
        if isinstance(value, bytes):
            args[key] = "0x" + value.hex()
        else:
            args[key] = str(value)
    return {"event_name": event_abi.get("name", ""), "args": args}


def _summarize_call_trace(trace: Any) -> Dict[str, Any]:
    if not isinstance(trace, dict):
        return {"supported": False, "error": "trace_result_not_object"}
    touched: set[str] = set()
    call_types: Dict[str, int] = {}
    call_count = 0
    max_depth = 0

    def walk(node: Any, depth: int = 0) -> None:
        nonlocal call_count, max_depth
        if not isinstance(node, dict):
            return
        call_count += 1
        max_depth = max(max_depth, depth)
        call_type = str(node.get("type") or "").upper()
        if call_type:
            call_types[call_type] = call_types.get(call_type, 0) + 1
        for key in ("from", "to"):
            value = str(node.get(key) or "").lower()
            if value.startswith("0x") and len(value) == 42:
                touched.add(value)
        for child in node.get("calls") or []:
            walk(child, depth + 1)

    walk(trace, 0)
    return {
        "supported": True,
        "tracer": "callTracer",
        "call_count": call_count,
        "max_depth": max_depth,
        "call_types": dict(sorted(call_types.items())),
        "touched_address_count": len(touched),
        "sample_touched_addresses": sorted(touched)[:50],
    }


def _try_debug_trace(rpc_url: str, tx_hash: str, budget: RequestBudget, cache_dir: Optional[Path] = None) -> Dict[str, Any]:
    if budget.max_debug_trace <= 0:
        return {"attempted": False, "supported": False, "reason": "debug_trace_disabled"}
    cache_path = None
    if cache_dir is not None:
        cache_path = cache_dir / "debug_trace" / f"{tx_hash.lower()}.json"
        if cache_path.exists():
            return read_json(cache_path)
    try:
        budget.use_debug_trace()
    except PipelineError:
        return {"attempted": False, "supported": False, "reason": "debug_trace_budget_exhausted"}
    try:
        result = rpc_call(
            rpc_url,
            "debug_traceTransaction",
            [tx_hash, {"tracer": "callTracer", "timeout": "20s"}],
            timeout=90,
        )
    except Exception as exc:  # pragma: no cover - provider support varies by chain.
        summary = {"attempted": True, "supported": False, "error": str(exc)}
        if cache_path is not None:
            write_json(cache_path, summary)
        return summary
    summary = _summarize_call_trace(result)
    summary["attempted"] = True
    if cache_path is not None:
        with _CACHE_LOCK:
            write_json(cache_path, summary)
    return summary


def _fetch_source(case: Dict[str, Any], address: str, env: Dict[str, str], budget: RequestBudget) -> Dict[str, Any]:
    explorer_api = case.get("explorer_api")
    key_name = case.get("api_key_env")
    if not explorer_api or not key_name or not env.get(key_name):
        return {"available": False, "reason": "explorer_api_or_key_missing", "address": address}
    params = {
        "module": "contract",
        "action": "getsourcecode",
        "address": address,
        "apikey": env[key_name],
    }
    if "/v2/" in explorer_api:
        params["chainid"] = case.get("chain_id")
    endpoints = [(explorer_api, dict(params))]
    if "/v2/" not in explorer_api:
        v2_params = dict(params)
        v2_params["chainid"] = case.get("chain_id")
        endpoints.append(("https://api.etherscan.io/v2/api", v2_params))
    payload: Any = None
    errors: List[str] = []
    for endpoint, endpoint_params in endpoints:
        budget.use_source()
        try:
            payload = http_json(endpoint, endpoint_params, timeout=60)
        except Exception as exc:  # pragma: no cover - network/provider failures vary.
            errors.append(f"{endpoint}:{exc}")
            continue
        result = payload.get("result") if isinstance(payload, dict) else None
        if isinstance(result, str) and "deprecated v1 endpoint" in result.lower():
            errors.append(f"{endpoint}:deprecated_v1_endpoint")
            continue
        break
    if payload is None:
        return {"available": False, "reason": "source_request_failed:" + ";".join(errors), "address": address}
    result = payload.get("result") if isinstance(payload, dict) else None
    item = result[0] if isinstance(result, list) and result else {}
    source_code = item.get("SourceCode") if isinstance(item, dict) else ""
    abi_text = item.get("ABI") if isinstance(item, dict) else ""
    abi: List[Dict[str, Any]] = []
    if abi_text and abi_text != "Contract source code not verified":
        try:
            abi = json.loads(abi_text)
        except json.JSONDecodeError:
            abi = []
    return {
        "available": bool(source_code) and source_code != "Contract source code not verified",
        "address": address,
        "contract_name": item.get("ContractName", "") if isinstance(item, dict) else "",
        "compiler_version": item.get("CompilerVersion", "") if isinstance(item, dict) else "",
        "source_code": source_code if source_code and source_code != "Contract source code not verified" else "",
        "abi": abi,
        "abi_available": bool(abi),
        "reason": "" if source_code and source_code != "Contract source code not verified" else "source_not_verified_or_empty",
    }


def _load_source_cache(output_dir: Path, case_id: str, address: str) -> Optional[Dict[str, Any]]:
    source_path = output_dir / "sources" / case_id / f"{address}.json"
    abi_path = output_dir / "sources" / case_id / f"{address}_abi.json"
    if not source_path.exists() or not abi_path.exists():
        return None
    meta = read_json(source_path)
    abi = read_json(abi_path)
    if isinstance(meta, dict):
        meta["abi"] = abi if isinstance(abi, list) else []
        meta["abi_available"] = bool(meta["abi"])
        return meta
    return None


def _write_source_cache(output_dir: Path, case_id: str, address: str, source_meta: Dict[str, Any]) -> None:
    source_path = output_dir / "sources" / case_id / f"{address}.json"
    with _CACHE_LOCK:
        write_json(source_path, {key: value for key, value in source_meta.items() if key != "abi"})
        write_json(output_dir / "sources" / case_id / f"{address}_abi.json", source_meta.get("abi") or [])


def _checkpoint_path(output_dir: Path, sample_id: str) -> Path:
    return output_dir / "sample_checkpoints" / f"{_safe_file_id(sample_id)}.json"


def _load_checkpoints(
    output_dir: Path,
    allowed_sample_ids: Optional[set[str]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    materialized_rows: List[Dict[str, Any]] = []
    per_case_records: Dict[str, List[Dict[str, Any]]] = {}
    raw_snapshots: Dict[str, Any] = {}
    checkpoint_dir = output_dir / "sample_checkpoints"
    if not checkpoint_dir.exists():
        return materialized_rows, per_case_records, raw_snapshots
    seen_sample_ids: set[str] = set()
    for path in sorted(checkpoint_dir.glob("*.json")):
        payload = read_json(path)
        if not isinstance(payload, dict):
            continue
        sample_id = str(payload.get("sample_id") or path.stem)
        if allowed_sample_ids is not None and sample_id not in allowed_sample_ids:
            continue
        if sample_id in seen_sample_ids:
            continue
        seen_sample_ids.add(sample_id)
        materialized = payload.get("materialized_sample")
        record = payload.get("replay_record")
        raw = payload.get("raw_snapshot")
        if isinstance(materialized, dict):
            materialized_rows.append(materialized)
        if isinstance(record, dict):
            per_case_records.setdefault(str(record.get("case") or ""), []).append(record)
        if isinstance(raw, dict):
            raw_snapshots[sample_id] = raw
    return materialized_rows, per_case_records, raw_snapshots


def _matching_logs(receipt: Dict[str, Any], sample: Dict[str, Any]) -> List[Dict[str, Any]]:
    address = str(sample.get("contract_address") or "").lower()
    topic0 = str(sample.get("topic0") or "").lower()
    matches = []
    for log in receipt.get("logs") or []:
        topics = [str(topic).lower() for topic in log.get("topics") or []]
        if address and _norm_addr(log.get("address", "")) != _norm_addr(address):
            continue
        if topic0 and (not topics or topics[0] != topic0):
            continue
        matches.append(log)
    return matches


def _raw_log_summary(log: Dict[str, Any], event_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    topics = [str(topic).lower() for topic in log.get("topics") or []]
    topic0 = topics[0] if topics else ""
    event_abi = event_map.get(topic0)
    decoded = _safe_decode_log(event_abi, log) if event_abi else {"event_name": "", "args": {}}
    return {
        "address": _norm_addr(log.get("address", "")),
        "log_index": _hex_to_int(log.get("logIndex", "0x0")),
        "topic0": topic0,
        "topics": topics,
        "data": log.get("data", "0x"),
        "decoded_event": decoded,
    }


def _classify_sample(
    sample: Dict[str, Any],
    case: Dict[str, Any],
    receipt: Dict[str, Any],
    matching: List[Dict[str, Any]],
    event_map: Dict[str, Dict[str, Any]],
) -> Tuple[str, str, List[Dict[str, Any]]]:
    """Return (verification_status, replay_event_type, decoded_log_summaries)."""
    summaries = [_raw_log_summary(log, event_map) for log in matching]
    case_id = case["id"]
    if case_id == "ploutos":
        constraint = next((item for item in case.get("constraints", []) if item.get("type") == "feed_mismatch"), {})
        case_asset = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"  # Ethereum USDC.
        forbidden_feed = "0xf4030086522a5beea4988f8ca5b36dbc97bee88c"  # BTC/USD.
        for log in matching:
            topics = [str(topic).lower() for topic in log.get("topics") or []]
            if len(topics) >= 3:
                asset = _topic_address(topics[1])
                feed = _topic_address(topics[2])
                if asset == case_asset and feed == forbidden_feed:
                    return "violated_constraint", "ORACLE_FEED_SET", summaries
                if asset == case_asset and feed != "0x3e7d1eab13ad0104d2750b8863b489d65364e32d":
                    # This would violate the generic Ploutos USDC feed constraint if replayed.
                    return "needs_review_case_asset_other_feed", "ORACLE_FEED_SET", summaries
        return "verified_no_case_feed_mismatch", "BENIGN_ORACLE_SCOPE_LOG", summaries
    if case_id in {"moonwell_cbeth", "blueberry_faulty_oracle"}:
        if not matching:
            return "unknown_after_materialization", "BENIGN_ORACLE_SCOPE_LOG", summaries
        if all(summary["decoded_event"].get("event_name") for summary in summaries):
            return "materialized_no_replayable_constraint_violation", "BENIGN_ORACLE_SCOPE_LOG", summaries
        return "unknown_after_materialization", "BENIGN_ORACLE_SCOPE_LOG", summaries
    return "materialized_no_replayable_constraint_violation", "BENIGN_ORACLE_SCOPE_LOG", summaries


def _replay_record(
    sample: Dict[str, Any],
    case: Dict[str, Any],
    receipt: Dict[str, Any],
    tx: Dict[str, Any],
    block: Dict[str, Any],
    matching: List[Dict[str, Any]],
    verification_status: str,
    replay_event_type: str,
    log_summaries: List[Dict[str, Any]],
    source_meta: Dict[str, Any],
    bytecode: str,
    debug_trace_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    first_log = matching[0] if matching else {}
    log_index = _hex_to_int(first_log.get("logIndex", "0x0")) if first_log else 0
    decoded: Dict[str, Any] = {
        "sample_id": sample.get("sample_id"),
        "original_label": sample.get("label"),
        "case_related_to": sample.get("case_related_to"),
        "scope_class": sample.get("scope_class"),
        "topic0": sample.get("topic0"),
        "expected_violation": False,
        "verification_status": verification_status,
        "source_available": bool(source_meta.get("available")),
        "abi_available": bool(source_meta.get("abi_available")),
        "contract_name": source_meta.get("contract_name", ""),
        "bytecode_size": max(0, (len(bytecode or "0x") - 2) // 2),
        "matching_log_count": len(matching),
        "decoded_logs": log_summaries,
        "debug_trace": debug_trace_summary or {"attempted": False, "supported": False},
        "note": "Benign evaluation replay record; verifier should not raise oracle-consumption constraints unless a case-specific semantic violation is decoded.",
    }
    if replay_event_type == "ORACLE_FEED_SET":
        # Used only when a Ploutos-like candidate carries enough indexed data to
        # replay the feed binding constraint.
        log = matching[0] if matching else {}
        topics = [str(topic).lower() for topic in log.get("topics") or []]
        decoded.update(
            {
                "asset": "USDC",
                "expected_feed": "USDC/USD",
                "actual_feed": "BTC/USD" if len(topics) >= 3 and _topic_address(topics[2]) == "0xf4030086522a5beea4988f8ca5b36dbc97bee88c" else "unknown",
            }
        )
    return {
        "case": case["id"],
        "event_type": replay_event_type,
        "block_number": _hex_to_int(receipt.get("blockNumber", "0x0")),
        "block_timestamp": _block_timestamp(block),
        "tx_hash": (receipt.get("transactionHash") or tx.get("hash") or sample.get("tx_hash") or "").lower(),
        "transaction_index": _hex_to_int(receipt.get("transactionIndex", "0x0")),
        "log_index": log_index,
        "address": _norm_addr(sample.get("contract_address") or tx.get("to") or ""),
        "decoded": decoded,
    }


def materialize_samples(
    samples: Sequence[Dict[str, Any]],
    output_dir: Path,
    results_dir: Path,
    max_rpc_requests: int,
    max_source_requests: int,
    max_debug_trace_requests: int = 0,
    trace_mode: str = "receipt",
    resume: bool = False,
    workers: int = 1,
    allowed_sample_ids: Optional[set[str]] = None,
) -> Dict[str, Any]:
    ensure_dir(output_dir)
    ensure_dir(results_dir)
    env = load_env()
    budget = RequestBudget(
        max_rpc=max_rpc_requests,
        max_source=max_source_requests,
        max_debug_trace=max_debug_trace_requests if trace_mode in {"debug", "two-layer"} else 0,
    )
    cache: Dict[Tuple[str, str], Any] = {}
    source_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
    per_case_records: Dict[str, List[Dict[str, Any]]] = {}
    materialized_rows: List[Dict[str, Any]] = []
    raw_snapshots: Dict[str, Any] = {}
    if resume:
        materialized_rows, per_case_records, raw_snapshots = _load_checkpoints(output_dir, allowed_sample_ids)
    initial_checkpoint_count = len(materialized_rows)
    done_sample_ids = {str(row.get("sample_id") or "") for row in materialized_rows}
    cache_dir = output_dir / "request_cache"

    def process_sample(index: int, sample: Dict[str, Any]) -> Optional[Tuple[str, str, Dict[str, Any], Dict[str, Any], Dict[str, Any]]]:
        case_id = str(sample.get("case_related_to") or "")
        case = get_case(case_id)
        rpc_url = resolve_template(case["rpc_url_template"], env)
        tx_hash = str(sample.get("tx_hash") or "").lower()
        contract_address = _norm_addr(sample.get("contract_address") or "")
        sample_id = str(sample.get("sample_id") or f"unknown-{index:03d}")
        if resume and sample_id in done_sample_ids:
            return None
        if not tx_hash:
            return None

        receipt = _rpc_cached(rpc_url, "eth_getTransactionReceipt", [tx_hash], budget, cache_dir, cache)
        tx = _rpc_cached(rpc_url, "eth_getTransactionByHash", [tx_hash], budget, cache_dir, cache)
        block = _rpc_cached(rpc_url, "eth_getBlockByNumber", [receipt.get("blockNumber"), False], budget, cache_dir, cache)
        bytecode = _rpc_cached(rpc_url, "eth_getCode", [contract_address, receipt.get("blockNumber")], budget, cache_dir, cache)
        source_key = (case_id, contract_address)
        with _CACHE_LOCK:
            source_meta = source_cache.get(source_key)
        if source_meta is None:
            source_meta = _load_source_cache(output_dir, case_id, contract_address)
        if source_meta is None:
            source_meta = _fetch_source(case, contract_address, env, budget)
            _write_source_cache(output_dir, case_id, contract_address, source_meta)
        with _CACHE_LOCK:
            source_cache[source_key] = source_meta

        event_map = _event_signature_map(source_meta.get("abi") or [])
        matching = _matching_logs(receipt, sample)
        status, replay_event_type, log_summaries = _classify_sample(sample, case, receipt, matching, event_map)
        debug_trace_summary = {"attempted": False, "supported": False, "reason": "not_requested"}
        if trace_mode == "debug" or (trace_mode == "two-layer" and status == "unknown_after_materialization"):
            debug_trace_summary = _try_debug_trace(rpc_url, tx_hash, budget, cache_dir)
        record = _replay_record(
            sample,
            case,
            receipt,
            tx,
            block,
            matching,
            status,
            replay_event_type,
            log_summaries,
            source_meta,
            bytecode or "0x",
            debug_trace_summary,
        )

        raw_snapshot = {
            "case": case_id,
            "sample": sample,
            "transaction": tx,
            "receipt": receipt,
            "block": block,
            "bytecode_size": max(0, (len(bytecode or "0x") - 2) // 2),
            "source_available": bool(source_meta.get("available")),
            "abi_available": bool(source_meta.get("abi_available")),
            "matching_log_count": len(matching),
            "verification_status": status,
            "debug_trace": debug_trace_summary,
            "contains_api_keys": False,
            "contains_rpc_url": False,
        }
        materialized = dict(sample)
        materialized.update(
            {
                "materialization_status": "receipt_source_trace_replayed",
                "verification_status": status,
                "replay_event_type": replay_event_type,
                "source_available": bool(source_meta.get("available")),
                "abi_available": bool(source_meta.get("abi_available")),
                "bytecode_size": max(0, (len(bytecode or "0x") - 2) // 2),
                "matching_log_count": len(matching),
                "debug_trace_attempted": bool(debug_trace_summary.get("attempted")),
                "debug_trace_supported": bool(debug_trace_summary.get("supported")),
            }
        )
        checkpoint = {
            "sample_id": sample_id,
            "materialized_sample": materialized,
            "replay_record": record,
            "raw_snapshot": raw_snapshot,
            "contains_api_keys": False,
            "contains_rpc_url": False,
        }
        return sample_id, case_id, materialized, record, raw_snapshot | {"_checkpoint": checkpoint}

    pending = [
        (index, sample)
        for index, sample in enumerate(samples, start=1)
        if not (resume and str(sample.get("sample_id") or f"unknown-{index:03d}") in done_sample_ids)
    ]
    results: List[Tuple[str, str, Dict[str, Any], Dict[str, Any], Dict[str, Any]]] = []
    if workers > 1 and len(pending) > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(process_sample, index, sample) for index, sample in pending]
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    results.append(result)
    else:
        for index, sample in pending:
            result = process_sample(index, sample)
            if result is not None:
                results.append(result)

    for sample_id, case_id, materialized, record, raw_snapshot in results:
        raw_snapshot_clean = dict(raw_snapshot)
        checkpoint = raw_snapshot_clean.pop("_checkpoint")
        per_case_records.setdefault(case_id, []).append(record)
        raw_snapshots[str(sample_id)] = raw_snapshot_clean
        materialized_rows.append(materialized)
        done_sample_ids.add(sample_id)
        write_json(
            _checkpoint_path(output_dir, sample_id),
            checkpoint,
        )

    replay_results: Dict[str, Any] = {}
    for case_id, records in per_case_records.items():
        trace_path = output_dir / "traces" / f"{case_id}_unknown_negative_benign_trace.jsonl"
        write_jsonl(trace_path, sorted(records, key=lambda row: (row.get("block_number", 0), row.get("transaction_index", 0), row.get("log_index", 0))))
        case = get_case(case_id)
        result = Verifier(case, records).replay()
        replay_results[case_id] = result
        write_json(output_dir / "replay_results" / f"{case_id}.json", result)

    write_jsonl(output_dir / "materialized_samples.jsonl", materialized_rows)
    write_json(
        output_dir / "raw_evidence.json",
        {
            "dataset": "unknown_negative_benign_materialization",
            "scope": "read-only receipt/source/bytecode/minimal replay trace for benign evaluation candidates",
            "contains_api_keys": False,
            "contains_rpc_url": False,
            "rpc_methods": ["eth_getTransactionReceipt", "eth_getTransactionByHash", "eth_getBlockByNumber", "eth_getCode"],
            "explorer_methods": ["getsourcecode"],
            "debug_trace_methods": ["debug_traceTransaction"] if budget.max_debug_trace else [],
            "samples": raw_snapshots,
        },
    )

    by_case: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    for row in materialized_rows:
        by_case[str(row.get("case_related_to") or "")] = by_case.get(str(row.get("case_related_to") or ""), 0) + 1
        by_status[str(row.get("verification_status") or "")] = by_status.get(str(row.get("verification_status") or ""), 0) + 1
    alert_count = sum(len(result.get("alerts") or []) for result in replay_results.values())
    strict_benign_count = sum(
        1
        for row in materialized_rows
        if row.get("verification_status")
        in {"verified_no_case_feed_mismatch", "materialized_no_replayable_constraint_violation"}
    )
    summary = {
        "dataset": "unknown_negative_benign_materialization",
        "input_sample_count": len(samples),
        "materialized_sample_count": len(materialized_rows),
        "resumed_checkpoint_count": initial_checkpoint_count,
        "by_case": dict(sorted(by_case.items())),
        "by_verification_status": dict(sorted(by_status.items())),
        "replay_alert_count": alert_count,
        "replay_results": {case_id: {"alerts": len(result.get("alerts") or []), "input_records": result.get("input_records")} for case_id, result in replay_results.items()},
        "request_budget": {
            "rpc_used": budget.rpc_used,
            "rpc_max": budget.max_rpc,
            "source_used": budget.source_used,
            "source_max": budget.max_source,
            "debug_trace_used": budget.debug_trace_used,
            "debug_trace_max": budget.max_debug_trace,
        },
        "cumulative_cache_files": {
            "rpc": len(list((output_dir / "request_cache" / "rpc").rglob("*.json")))
            if (output_dir / "request_cache" / "rpc").exists()
            else 0,
            "source": len(list((output_dir / "sources").rglob("*.json"))) if (output_dir / "sources").exists() else 0,
            "debug_trace": len(list((output_dir / "request_cache" / "debug_trace").rglob("*.json")))
            if (output_dir / "request_cache" / "debug_trace").exists()
            else 0,
        },
        "strict_benign_verified_after_replay": sum(
            1
            for row in materialized_rows
            if row.get("verification_status")
            in {"verified_no_case_feed_mismatch", "materialized_no_replayable_constraint_violation"}
        ),
        "needs_review_or_alert_after_replay": len(materialized_rows) - strict_benign_count,
        "safety_boundary": "read-only historical RPC/explorer evidence; no chain writes, no write methods, no private keys, no attack simulation",
    }
    write_json(output_dir / "materialization_summary.json", summary)
    write_report(results_dir / "unknown_negative_replay_report.md", summary)
    return summary


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    lines = [
        "# Unknown-Negative Benign Replay",
        "",
        "This run materialized the `unknown_negative` hard-benign candidates with read-only historical receipts, bytecode, source metadata, and minimal replay traces.",
        "",
        f"- Input samples: `{summary['input_sample_count']}`",
        f"- Materialized samples: `{summary['materialized_sample_count']}`",
        f"- Replay alerts: `{summary['replay_alert_count']}`",
        f"- Strict benign after replay: `{summary['strict_benign_verified_after_replay']}`",
        f"- Needs review or alert after replay: `{summary.get('needs_review_or_alert_after_replay', 0)}`",
        f"- RPC requests: `{summary['request_budget']['rpc_used']}/{summary['request_budget']['rpc_max']}`",
        f"- Explorer/source requests: `{summary['request_budget']['source_used']}/{summary['request_budget']['source_max']}`",
        f"- Debug trace requests: `{summary['request_budget']['debug_trace_used']}/{summary['request_budget']['debug_trace_max']}`",
    ]
    cumulative = summary.get("cumulative_cache_files") or {}
    lines.extend(
        [
            f"- Cumulative RPC cache files: `{cumulative.get('rpc', 0)}`",
            f"- Cumulative source/ABI cache files: `{cumulative.get('source', 0)}`",
            f"- Cumulative debug trace cache files: `{cumulative.get('debug_trace', 0)}`",
            "",
            "## By Case",
            "",
            "| case | samples | replay alerts |",
            "|---|---:|---:|",
        ]
    )
    for case_id, count in summary.get("by_case", {}).items():
        alerts = (summary.get("replay_results", {}).get(case_id) or {}).get("alerts", 0)
        lines.append(f"| {case_id} | {count} | {alerts} |")
    lines.extend(["", "## Verification Status", "", "| status | rows |", "|---|---:|"])
    for status, count in summary.get("by_verification_status", {}).items():
        lines.append(f"| {status} | {count} |")
    lines.extend(
        [
            "",
            "Rows marked `materialized_no_replayable_constraint_violation` or `verified_no_case_feed_mismatch` can be counted as replay-checked benign for the current DSC-Guard constraints. Rows marked `unknown_after_materialization` remain review candidates and should not enter the strict false-positive denominator.",
        ]
    )
    ensure_dir(path.parent)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize unknown-negative benign samples and replay local constraints.")
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        help="JSONL input path. Defaults to artifacts/eval_dataset/benign_cross_protocol.jsonl and benign_same_protocol.jsonl.",
    )
    parser.add_argument("--labels", default="unknown_negative")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    parser.add_argument("--max-rpc-requests", type=int, default=250)
    parser.add_argument("--max-source-requests", type=int, default=80)
    parser.add_argument("--max-debug-trace-requests", type=int, default=0)
    parser.add_argument("--trace-mode", choices=["receipt", "debug", "two-layer"], default="receipt")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    paths = [Path(value) for value in args.input] if args.input else [
        repo_path("artifacts", "eval_dataset", "benign_cross_protocol.jsonl"),
        repo_path("artifacts", "eval_dataset", "benign_same_protocol.jsonl"),
    ]
    labels = {item.strip() for item in args.labels.split(",") if item.strip()}
    samples = _load_samples(paths, labels)
    if not samples:
        raise SystemExit("No matching samples found.")
    try:
        summary = materialize_samples(
            samples,
            Path(args.output_dir),
            Path(args.results_dir),
            args.max_rpc_requests,
            args.max_source_requests,
            args.max_debug_trace_requests,
            args.trace_mode,
            args.resume,
            args.workers,
            {str(row.get("sample_id") or "") for row in samples},
        )
    except PipelineError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
