#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import build_benign_eval_dataset as benign
from common import (
    PipelineError,
    ensure_dir,
    get_case,
    http_json,
    load_env,
    read_json,
    repo_path,
    resolve_template,
    rpc_call,
    write_json,
    write_jsonl,
)
from materialize_benign_eval_samples import materialize_samples
from materialize_feed_binding_case import _hex_to_int, _norm_addr


DEFAULT_OUTPUT_DIR = repo_path("artifacts", "eval_dataset", "no_dune_10k")
DEFAULT_RESULTS_DIR = repo_path("results")
DEFAULT_START = "2022-01-01"
DEFAULT_END = "2026-05-12"
DEFAULT_TARGET_TOTAL = 10_000
DEFAULT_SMALL_POOL_THRESHOLD = 1_000
CASE_ORDER = [
    "ploutos",
    "blueberry_faulty_oracle",
    "moonwell_wrseth",
    "moonwell_cbeth",
    "venus_luna",
    "blizz_luna",
]
LARGE_CASE_ALLOCATION_ORDER = ["moonwell_cbeth", "venus_luna", "blizz_luna"]
DEFICIT_FILL_ORDER = ["blizz_luna", "venus_luna", "moonwell_cbeth"]
DEFAULT_POOL_ESTIMATES = {
    "ploutos": 62,
    "blueberry_faulty_oracle": 38,
    "moonwell_wrseth": 677,
    "moonwell_cbeth": 1_687_292,
    "venus_luna": 5_376,
    "blizz_luna": 9_250,
}


class RequestBudget:
    def __init__(self, max_explorer: int, max_rpc: int = 0) -> None:
        self.max_explorer = max_explorer
        self.max_rpc = max_rpc
        self.explorer_used = 0
        self.rpc_used = 0

    def use_explorer(self) -> None:
        if self.explorer_used + 1 > self.max_explorer:
            raise PipelineError(f"Explorer request budget exceeded: {self.explorer_used + 1}>{self.max_explorer}")
        self.explorer_used += 1

    def use_rpc(self) -> None:
        if self.rpc_used + 1 > self.max_rpc:
            raise PipelineError(f"Candidate RPC request budget exceeded: {self.rpc_used + 1}>{self.max_rpc}")
        self.rpc_used += 1


class ExplorerClient:
    def __init__(self, case_id: str, env: Dict[str, str], budget: RequestBudget, cache_dir: Optional[Path] = None) -> None:
        self.case_id = case_id
        self.case = get_case(case_id)
        self.env = env
        self.budget = budget
        self.cache_dir = cache_dir
        self.api = self.case.get("explorer_api", "")
        self.chain_id = self.case.get("chain_id")
        self.key = env.get(self.case.get("api_key_env", ""), "")
        self.rpc_url = resolve_template(self.case.get("rpc_url_template", ""), env)
        if not self.api or not self.key:
            raise PipelineError(f"Missing explorer API/key for {case_id}")

    def call(self, params: Dict[str, Any], attempts: int = 3) -> Any:
        base_params = dict(params)
        base_params["apikey"] = self.key
        if "/v2/" in self.api:
            base_params["chainid"] = self.chain_id
        endpoints = [(self.api, dict(base_params))]
        if "/v2/" not in self.api:
            v2_params = dict(base_params)
            v2_params["chainid"] = self.chain_id
            endpoints.append(("https://api.etherscan.io/v2/api", v2_params))
        cache_path = None
        if self.cache_dir is not None:
            safe_params = {key: value for key, value in base_params.items() if key != "apikey"}
            payload = json.dumps(safe_params, sort_keys=True, separators=(",", ":"))
            key = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            cache_path = self.cache_dir / self.case_id / str(base_params.get("module", "unknown")) / str(base_params.get("action", "unknown")) / f"{key}.json"
            if cache_path.exists():
                return read_json(cache_path)
        last_error = ""
        for endpoint, endpoint_params in endpoints:
            for attempt in range(attempts):
                self.budget.use_explorer()
                try:
                    payload = http_json(endpoint, endpoint_params, timeout=90)
                except Exception as exc:  # pragma: no cover - provider failures vary.
                    last_error = str(exc)
                    if attempt + 1 < attempts:
                        time.sleep(1)
                    continue
                result = payload.get("result") if isinstance(payload, dict) else None
                if isinstance(result, str) and "deprecated v1 endpoint" in result.lower():
                    last_error = "deprecated_v1_endpoint"
                    break
                if cache_path is not None:
                    write_json(cache_path, payload)
                return payload
        raise PipelineError(f"Explorer request failed for {self.case_id}: {last_error}")

    def rpc(self, method: str, params: List[Any], timeout: int = 90, attempts: int = 3) -> Any:
        cache_path = None
        if self.cache_dir is not None:
            payload = json.dumps({"method": method, "params": params}, sort_keys=True, separators=(",", ":"))
            key = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            cache_path = self.cache_dir / self.case_id / "rpc" / method / f"{key}.json"
            if cache_path.exists():
                cached = read_json(cache_path)
                return cached.get("result") if isinstance(cached, dict) else None
        last_error: Optional[Exception] = None
        for attempt in range(attempts):
            self.budget.use_rpc()
            try:
                result = rpc_call(self.rpc_url, method, params, timeout=timeout)
                break
            except Exception as exc:  # pragma: no cover - provider/network failures vary.
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(1)
        else:
            raise PipelineError(f"RPC request failed for {self.case_id} {method}: {last_error}") from last_error
        if cache_path is not None:
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
        return result

    def _rpc_block_timestamp(self, block_number: int) -> int:
        block = self.rpc("eth_getBlockByNumber", [hex(int(block_number)), False])
        return _hex_value(block.get("timestamp", "0x0")) if isinstance(block, dict) else 0

    def _rpc_block_by_time(self, timestamp: int, closest: str) -> int:
        latest_hex = self.rpc("eth_blockNumber", [])
        latest = _hex_value(latest_hex)
        low, high = 0, latest
        best_before = 0
        best_after = latest
        while low <= high:
            mid = (low + high) // 2
            ts = self._rpc_block_timestamp(mid)
            if ts <= timestamp:
                best_before = mid
                low = mid + 1
            else:
                best_after = mid
                high = mid - 1
        return best_before if closest == "before" else best_after

    def block_by_time(self, timestamp: int, closest: str) -> int:
        try:
            payload = self.call(
                {
                    "module": "block",
                    "action": "getblocknobytime",
                    "timestamp": int(timestamp),
                    "closest": closest,
                }
            )
            result = payload.get("result") if isinstance(payload, dict) else None
            if result not in (None, "", "0"):
                return int(str(result), 0)
        except Exception:
            pass
        return self._rpc_block_by_time(timestamp, closest)

    def rpc_logs(self, *, from_block: int, to_block: int, topic0: str, address: str = "") -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "fromBlock": hex(int(from_block)),
            "toBlock": hex(int(to_block)),
            "topics": [topic0],
        }
        if address:
            params["address"] = address
        result = self.rpc("eth_getLogs", [params], timeout=120)
        return result if isinstance(result, list) else []

    def logs(
        self,
        *,
        from_block: int,
        to_block: int,
        topic0: str,
        address: str = "",
        page: int = 1,
        offset: int = 1000,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "module": "logs",
            "action": "getLogs",
            "fromBlock": str(int(from_block)),
            "toBlock": str(int(to_block)),
            "topic0": topic0,
            "page": str(int(page)),
            "offset": str(int(offset)),
        }
        if address:
            params["address"] = address
        try:
            payload = self.call(params)
        except PipelineError:
            return self.rpc_logs(from_block=from_block, to_block=to_block, topic0=topic0, address=address)
        result = payload.get("result") if isinstance(payload, dict) else None
        if isinstance(result, list):
            return result
        if isinstance(result, str):
            lowered = result.lower()
            if "no records" in lowered:
                return []
            if "not supported" in lowered or "upgrade your api plan" in lowered:
                return self.rpc_logs(from_block=from_block, to_block=to_block, topic0=topic0, address=address)
        message = payload.get("message") if isinstance(payload, dict) else ""
        if isinstance(result, str) and result:
            raise PipelineError(f"Explorer getLogs returned non-list result for {self.case_id}: {result}")
        if message and str(message).lower() not in {"ok", "no records found"}:
            raise PipelineError(f"Explorer getLogs failed for {self.case_id}: {message}")
        return []


def _parse_time(value: Any) -> Optional[datetime]:
    parsed = benign._parse_time(value)
    return parsed.astimezone(timezone.utc) if parsed else None


def _timestamp(value: datetime) -> int:
    return int(value.astimezone(timezone.utc).timestamp())


def _valid_hash(value: Any, nbytes: int = 32) -> bool:
    text = str(value or "").lower()
    return len(text) == 2 + nbytes * 2 and text.startswith("0x") and all(ch in "0123456789abcdef" for ch in text[2:])


def _stable_int(*parts: Any) -> int:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return int(hashlib.sha256(payload).hexdigest(), 16)


def _stable_log_key(row: Dict[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("case_related_to") or ""),
            str(row.get("chain") or ""),
            str(row.get("tx_hash") or "").lower(),
            str(row.get("contract_address") or "").lower(),
            str(row.get("topic0") or "").lower(),
            str(row.get("log_index") or ""),
        ]
    )


def _signed_int256(value: str) -> int:
    raw = int(str(value or "0x0"), 16)
    if raw >= 2**255:
        raw -= 2**256
    return raw


def _answer_from_topic(topic: str, decimals: int) -> Optional[float]:
    if not str(topic or "").startswith("0x"):
        return None
    return abs(_signed_int256(topic)) / float(10**int(decimals))


def _read_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    return read_json(path)


def _read_count_rows() -> List[Dict[str, Any]]:
    paths = [
        repo_path("artifacts", "eval_dataset", "benign_count_only", "combined_count_rows.json"),
        repo_path("artifacts", "eval_dataset", "benign_count_only_strict_source", "combined_count_rows.json"),
    ]
    rows: List[Dict[str, Any]] = []
    seen: set[Tuple[Any, ...]] = set()
    for path in paths:
        payload = _read_json_if_exists(path)
        if not isinstance(payload, list):
            continue
        for row in payload:
            key = (
                row.get("case_related_to") or row.get("case"),
                row.get("benign_stratum"),
                row.get("chain"),
                row.get("year"),
                row.get("scope_class"),
                row.get("candidate_log_rows"),
                row.get("first_block_time"),
                row.get("last_block_time"),
            )
            if key in seen:
                continue
            seen.add(key)
            rows.append(dict(row))
    return rows


def _sample_source_rows(case_id: str, count_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = [row for row in count_rows if str(row.get("case_related_to") or row.get("case") or "") == case_id]
    if case_id == "moonwell_wrseth":
        preferred = [row for row in rows if row.get("benign_stratum") == "case_topic"]
        if preferred:
            return preferred
    if case_id in {"venus_luna", "blizz_luna"}:
        preferred = [row for row in rows if row.get("benign_stratum") == "same_oracle"]
        if preferred:
            return preferred
    if case_id in {"ploutos", "moonwell_cbeth", "blueberry_faulty_oracle"}:
        preferred = [row for row in rows if row.get("benign_stratum") == "case_topic"]
        if preferred:
            return preferred
    return rows


def _pool_estimates(count_rows: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    estimates: Dict[str, int] = {}
    for case_id in CASE_ORDER:
        rows = _sample_source_rows(case_id, count_rows)
        total = sum(int(float(row.get("candidate_log_rows") or 0)) for row in rows)
        estimates[case_id] = total or DEFAULT_POOL_ESTIMATES[case_id]
    # The historical summary double-counted Blizz when strict-source rows were
    # merged with broad rows; force the exact source count when available.
    blizz_same = [
        int(float(row.get("candidate_log_rows") or 0))
        for row in count_rows
        if str(row.get("case_related_to") or row.get("case") or "") == "blizz_luna"
        and row.get("benign_stratum") == "same_oracle"
    ]
    if blizz_same:
        estimates["blizz_luna"] = max(blizz_same)
    wrseth_same = [
        int(float(row.get("candidate_log_rows") or 0))
        for row in count_rows
        if str(row.get("case_related_to") or row.get("case") or "") == "moonwell_wrseth"
        and row.get("benign_stratum") == "same_oracle"
    ]
    if wrseth_same:
        estimates["moonwell_wrseth"] = sum(wrseth_same)
    return estimates


def _allocation(estimates: Dict[str, int], target_total: int, small_threshold: int) -> Dict[str, int]:
    allocation: Dict[str, int] = {}
    large_cases: List[str] = []
    small_total = 0
    for case_id in CASE_ORDER:
        estimate = int(estimates.get(case_id, 0))
        if estimate < small_threshold:
            allocation[case_id] = estimate
            small_total += estimate
        else:
            allocation[case_id] = 0
            large_cases.append(case_id)
    remaining = max(0, int(target_total) - small_total)
    ordered_large = [case for case in LARGE_CASE_ALLOCATION_ORDER if case in large_cases] + [
        case for case in large_cases if case not in LARGE_CASE_ALLOCATION_ORDER
    ]
    if ordered_large:
        base, extra = divmod(remaining, len(ordered_large))
        for index, case_id in enumerate(ordered_large):
            allocation[case_id] = min(int(estimates[case_id]), base + (1 if index < extra else 0))
    return allocation


def _context_by_case(chains: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    return {ctx["case_id"]: ctx for ctx in benign._case_context_rows(chains)}


def _known_txs(ctx: Dict[str, Any]) -> set[str]:
    return {str(tx).lower() for tx in ctx.get("known_txs") or [] if _valid_hash(tx)}


def _time_bounds_for_stratum(case_id: str, row: Dict[str, Any], ctx: Dict[str, Any], start: str, end: str) -> Tuple[datetime, datetime]:
    first = _parse_time(row.get("first_block_time"))
    last = _parse_time(row.get("last_block_time"))
    if first and last:
        return first, last
    if case_id == "venus_luna":
        incident_start = ctx.get("incident_start")
        return _parse_time(start) or datetime(2022, 1, 1, tzinfo=timezone.utc), incident_start - timedelta(hours=24)
    if case_id == "blizz_luna":
        incident_start = ctx.get("incident_start")
        return _parse_time(start) or datetime(2022, 1, 1, tzinfo=timezone.utc), incident_start - timedelta(hours=24)
    return _parse_time(start) or datetime(2022, 1, 1, tzinfo=timezone.utc), _parse_time(end) or datetime(2026, 5, 12, tzinfo=timezone.utc)


def _topic_controls_for_case(case_id: str, ctx: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    if case_id == "ploutos":
        return [
            (topic0, "S2", "")
            for topic0, scope, _full_scope, _name, contextual in benign.ORACLE_TOPICS
            if scope == "S2" and not contextual
        ]
    if case_id == "moonwell_cbeth":
        return [
            ("0xbc7cd75a20ee27fd9adebab32041f755214dbc6bffa90cc0225b39da2e5c2d3b", "S4", ""),
        ]
    if case_id == "blueberry_faulty_oracle":
        return [
            ("0xa8c96090e146ce1076efa81e5424d56e13d5c3854943f7926406c12d15d6dbe9", "S3", ""),
            ("0xd1b3641b73e6c323671a85001b02db34d4e63a7fa6d264896138094dd6b8bfdf", "S3", ""),
            ("0xaef9ecb0b33da1a5a170fdeed3accb3e88c5257f51d6faa019cea841b864d049", "S2", ""),
        ]
    primary = str(ctx.get("primary_topic0") or "").lower()
    return [(primary, str(ctx.get("scope_class") or ""), "")] if primary else []


def _same_oracle_control(case_id: str, ctx: Dict[str, Any]) -> Optional[Tuple[str, float, float, int]]:
    bounds = ctx.get("normal_oracle_bounds")
    if bounds:
        return bounds
    if case_id == "moonwell_wrseth" and benign._valid_address(ctx.get("primary_contract")):
        return str(ctx["primary_contract"]).lower(), 0.5, 2.0, 18
    return None


def _case_strata(
    case_id: str,
    ctx: Dict[str, Any],
    count_rows: Sequence[Dict[str, Any]],
    start: str,
    end: str,
) -> List[Dict[str, Any]]:
    rows = _sample_source_rows(case_id, count_rows)
    if not rows:
        rows = [
            {
                "case_related_to": case_id,
                "benign_stratum": "same_oracle" if _same_oracle_control(case_id, ctx) else "case_topic",
                "candidate_log_rows": DEFAULT_POOL_ESTIMATES[case_id],
                "year": int(start[:4]),
                "scope_class": ctx.get("scope_class") or "",
            }
        ]
    strata: List[Dict[str, Any]] = []
    for row in rows:
        stratum = str(row.get("benign_stratum") or "")
        first, last = _time_bounds_for_stratum(case_id, row, ctx, start, end)
        if last < first:
            continue
        if stratum == "same_oracle":
            control = _same_oracle_control(case_id, ctx)
            if not control:
                continue
            feed, normal_min, normal_max, decimals = control
            strata.append(
                {
                    "benign_stratum": "same_oracle",
                    "label": "benign_verified",
                    "topic0": benign.ANSWER_UPDATED_TOPIC,
                    "scope_class": "S1",
                    "failure_class": ctx.get("failure_class") or "",
                    "address": feed,
                    "normal_min": normal_min,
                    "normal_max": normal_max,
                    "answer_decimals": decimals,
                    "first_time": first,
                    "last_time": last,
                    "estimated_rows": int(float(row.get("candidate_log_rows") or DEFAULT_POOL_ESTIMATES[case_id])),
                }
            )
        else:
            controls = _topic_controls_for_case(case_id, ctx)
            matching_controls = [item for item in controls if not row.get("scope_class") or item[1] == row.get("scope_class")]
            for topic0, scope_class, address in matching_controls or controls:
                strata.append(
                    {
                        "benign_stratum": "case_topic",
                        "label": "unknown_negative",
                        "topic0": topic0,
                        "scope_class": scope_class,
                        "failure_class": ctx.get("failure_class") or "",
                        "address": address,
                        "first_time": first,
                        "last_time": last,
                        "estimated_rows": max(1, int(float(row.get("candidate_log_rows") or DEFAULT_POOL_ESTIMATES[case_id]))),
                    }
                )
    return strata


def _incident_guard_blocks(client: ExplorerClient, ctx: Dict[str, Any], guard_hours: int) -> Tuple[int, int]:
    start = ctx["incident_start"] - timedelta(hours=guard_hours)
    end = ctx["incident_end"] + timedelta(hours=guard_hours)
    return client.block_by_time(_timestamp(start), "before"), client.block_by_time(_timestamp(end), "after")


def _block_range(client: ExplorerClient, first: datetime, last: datetime) -> Tuple[int, int]:
    return client.block_by_time(_timestamp(first), "after"), client.block_by_time(_timestamp(last), "before")


def _log_index(log: Dict[str, Any]) -> int:
    value = str(log.get("logIndex", "0x0") or "0x0")
    return _hex_to_int(value if value not in {"0x", ""} else "0x0")


def _hex_value(value: Any) -> int:
    text = str(value or "0x0")
    return _hex_to_int(text if text not in {"0x", ""} else "0x0")


def _row_from_log(
    case_id: str,
    chain: str,
    log: Dict[str, Any],
    stratum: Dict[str, Any],
) -> Dict[str, Any]:
    topics = [str(topic).lower() for topic in log.get("topics") or []]
    topic0 = topics[0] if topics else str(stratum.get("topic0") or "").lower()
    normalized_answer: Optional[float] = None
    label = str(stratum.get("label") or "unknown_negative")
    if stratum.get("benign_stratum") == "same_oracle" and len(topics) >= 2:
        normalized_answer = _answer_from_topic(topics[1], int(stratum.get("answer_decimals") or 8))
        if normalized_answer is None or not (float(stratum["normal_min"]) <= normalized_answer <= float(stratum["normal_max"])):
            label = "unknown_negative"
    block_time = _parse_time(log.get("timeStamp"))
    if not block_time and str(log.get("timeStamp") or "").startswith("0x"):
        block_time = datetime.fromtimestamp(_hex_to_int(log.get("timeStamp")), timezone.utc)
    year = block_time.year if block_time else int(stratum.get("first_time", datetime(1970, 1, 1, tzinfo=timezone.utc)).year)
    tx_hash = str(log.get("transactionHash") or "").lower()
    contract_address = _norm_addr(log.get("address") or "")
    return {
        "sample_id": f"benign-{stratum.get('benign_stratum')}-{case_id}-{tx_hash}-{_log_index(log)}",
        "label": label,
        "benign_stratum": stratum.get("benign_stratum"),
        "case_id": "",
        "case_related_to": case_id,
        "chain": chain,
        "display_chain": benign.display_chain(chain),
        "year": year,
        "failure_class": str(stratum.get("failure_class") or ""),
        "scope_class": stratum.get("scope_class") or "",
        "tx_hash": tx_hash,
        "contract_address": contract_address,
        "topic0": topic0,
        "expected_violation": False,
        "exclusion_reason": (
            "same oracle feed outside incident window with normal answer bounds"
            if stratum.get("benign_stratum") == "same_oracle" and label == "benign_verified"
            else "same case oracle-scope topic outside incident window; local replay required before FP denominator"
        ),
        "materialization_status": "explorer_candidate_pending_receipt_replay",
        "normalized_answer": normalized_answer,
        "block_number": _hex_value(log.get("blockNumber", "0x0")),
        "log_index": _log_index(log),
        "sampling_source": "etherscan_getLogs",
    }


def _dedupe(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        key = _stable_log_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _raw_log_key(log: Dict[str, Any]) -> str:
    topics = log.get("topics") or []
    topic0 = str(topics[0] if topics else log.get("topic0") or "").lower()
    return "|".join(
        [
            str(log.get("transactionHash") or "").lower(),
            _norm_addr(log.get("address") or ""),
            topic0,
            str(_log_index(log)),
        ]
    )


def _fetch_page_range(
    client: ExplorerClient,
    *,
    from_block: int,
    to_block: int,
    topic0: str,
    address: str,
    offset: int,
    max_pages: int,
) -> Tuple[List[Dict[str, Any]], bool]:
    rows: List[Dict[str, Any]] = []
    seen_keys: set[str] = set()
    complete = True
    for page in range(1, max_pages + 1):
        page_rows = client.logs(
            from_block=from_block,
            to_block=to_block,
            topic0=topic0,
            address=address,
            page=page,
            offset=offset,
        )
        rows.extend(page_rows)
        if len(page_rows) < offset:
            return rows, complete
    if rows and len(rows) >= offset * max_pages:
        complete = False
    return rows, complete


def _fetch_full_small_pool(
    client: ExplorerClient,
    stratum: Dict[str, Any],
    from_block: int,
    to_block: int,
    incident_guard: Tuple[int, int],
    offset: int,
    max_block_span: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    stack = [(from_block, to_block)]
    split_count = 0
    queries = 0
    while stack:
        lo, hi = stack.pop()
        if hi < lo:
            continue
        if max_block_span > 0 and hi - lo + 1 > max_block_span:
            mid = min(hi, lo + max_block_span - 1)
            stack.append((mid + 1, hi))
            stack.append((lo, mid))
            split_count += 1
            continue
        try:
            rows, complete = _fetch_page_range(
                client,
                from_block=lo,
                to_block=hi,
                topic0=stratum["topic0"],
                address=stratum.get("address") or "",
                offset=offset,
                max_pages=1,
            )
        except PipelineError:
            if hi > lo:
                mid = (lo + hi) // 2
                stack.append((mid + 1, hi))
                stack.append((lo, mid))
                split_count += 1
                continue
            raise
        queries += 1
        if not complete and hi > lo:
            mid = (lo + hi) // 2
            stack.append((mid + 1, hi))
            stack.append((lo, mid))
            split_count += 1
            continue
        result.extend(
            row
            for row in rows
            if not (incident_guard[0] <= _hex_value(row.get("blockNumber", "0x0")) <= incident_guard[1])
        )
    return result, {"strategy": "full_small_pool", "range_queries": queries, "split_count": split_count}


def _fetch_probe_resilient(
    client: ExplorerClient,
    stratum: Dict[str, Any],
    lo: int,
    hi: int,
    offset: int,
    max_pages: int,
    max_splits: int = 6,
) -> Tuple[List[Dict[str, Any]], int]:
    rows: List[Dict[str, Any]] = []
    split_count = 0
    stack: List[Tuple[int, int, int]] = [(lo, hi, 0)]
    while stack:
        start, end, depth = stack.pop()
        try:
            page_rows, _complete = _fetch_page_range(
                client,
                from_block=start,
                to_block=end,
                topic0=stratum["topic0"],
                address=stratum.get("address") or "",
                offset=offset,
                max_pages=max_pages,
            )
            rows.extend(page_rows)
        except PipelineError:
            if end > start and depth < max_splits:
                mid = (start + end) // 2
                stack.append((mid + 1, end, depth + 1))
                stack.append((start, mid, depth + 1))
                split_count += 1
                continue
            # A single-block or repeatedly failing probe is skipped. This is a
            # benign sampling pass, so losing one deterministic probe is safer
            # than relaxing the evidence rules or falling back to broad scans.
            continue
    return rows, split_count


def _cached_logs_for_stratum(
    client: ExplorerClient,
    stratum: Dict[str, Any],
    incident_guard: Tuple[int, int],
) -> List[Dict[str, Any]]:
    if client.cache_dir is None:
        return []
    roots = [
        client.cache_dir / client.case_id / "logs" / "getLogs",
        client.cache_dir / client.case_id / "rpc" / "eth_getLogs",
    ]
    wanted_topic = str(stratum.get("topic0") or "").lower()
    wanted_address = _norm_addr(stratum.get("address") or "")
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.glob("*.json")):
            try:
                payload = read_json(path)
            except Exception:
                continue
            result = payload.get("result") if isinstance(payload, dict) else None
            if not isinstance(result, list):
                continue
            for log in result:
                topics = [str(topic).lower() for topic in log.get("topics") or []]
                if wanted_topic and (not topics or topics[0] != wanted_topic):
                    continue
                if wanted_address and _norm_addr(log.get("address") or "") != wanted_address:
                    continue
                if incident_guard[0] <= _hex_value(log.get("blockNumber", "0x0")) <= incident_guard[1]:
                    continue
                key = _raw_log_key(log)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(log)
    return rows


def _probe_windows(from_block: int, to_block: int, probes: int, width: int, salt: str) -> List[Tuple[int, int]]:
    if to_block < from_block:
        return []
    span = to_block - from_block + 1
    probes = max(1, probes)
    width = max(1, min(width, span))
    windows: List[Tuple[int, int]] = []
    for index in range(probes):
        segment_start = from_block + (span * index) // probes
        segment_end = from_block + (span * (index + 1)) // probes - 1
        if segment_end < segment_start:
            segment_end = segment_start
        segment_span = segment_end - segment_start + 1
        local_width = min(width, segment_span)
        max_offset = max(0, segment_span - local_width)
        offset = _stable_int(salt, index) % (max_offset + 1)
        lo = segment_start + offset
        windows.append((lo, min(segment_end, lo + local_width - 1)))
    return windows


def _fetch_sampled_large_pool(
    client: ExplorerClient,
    stratum: Dict[str, Any],
    from_block: int,
    to_block: int,
    incident_guard: Tuple[int, int],
    target: int,
    offset: int,
    max_pages_per_probe: int,
    min_probe_blocks: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    cached_rows = _cached_logs_for_stratum(client, stratum, incident_guard)
    if len(cached_rows) >= target:
        return cached_rows, {
            "strategy": "local_cache_hash_sample",
            "cached_rows_available": len(cached_rows),
            "passes": [],
        }
    if len(cached_rows) >= min(1000, target):
        return cached_rows, {
            "strategy": "local_cache_partial_hash_sample",
            "cached_rows_available": len(cached_rows),
            "partial_cache_accept_threshold": min(1000, target),
            "passes": [],
        }
    rows: List[Dict[str, Any]] = list(cached_rows)
    seen_keys: set[str] = {_raw_log_key(row) for row in cached_rows}
    span = max(1, to_block - from_block + 1)
    probe_count = max(16, min(160, math.ceil(max(1, target) / 25)))
    base_width = max(min_probe_blocks, span // max(1, probe_count * 24))
    passes = []
    total_split_count = 0
    for pass_index, multiplier in enumerate([1, 2, 4, 8], start=1):
        rows_before_pass = len(rows)
        width = min(span, base_width * multiplier)
        windows = _probe_windows(from_block, to_block, probe_count, width, f"{client.case_id}:{stratum['topic0']}:{pass_index}")
        queries_before = client.budget.explorer_used
        for lo, hi in windows:
            if hi < incident_guard[0] or lo > incident_guard[1]:
                page_rows, split_count = _fetch_probe_resilient(
                    client,
                    stratum,
                    lo,
                    hi,
                    offset=offset,
                    max_pages=max_pages_per_probe,
                )
                total_split_count += split_count
                for row in page_rows:
                    if incident_guard[0] <= _hex_value(row.get("blockNumber", "0x0")) <= incident_guard[1]:
                        continue
                    key = _raw_log_key(row)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    rows.append(row)
            if len(rows) >= target * 2:
                break
        passes.append(
            {
                "pass": pass_index,
                "probe_count": len(windows),
                "probe_width_blocks": width,
                "explorer_requests": client.budget.explorer_used - queries_before,
                "collected_rows": len(rows),
            }
        )
        if len(rows) >= target:
            break
        if pass_index >= 2 and len(rows) == rows_before_pass:
            passes[-1]["stopped_reason"] = "no_new_unique_rows"
            break
    return rows, {"strategy": "stratified_probe_hash_sample", "range_split_count": total_split_count, "passes": passes}


def _select_stable(rows: Sequence[Dict[str, Any]], target: int, salt: str) -> List[Dict[str, Any]]:
    return sorted(
        _dedupe(rows),
        key=lambda row: (
            hashlib.sha256((salt + "|" + _stable_log_key(row)).encode("utf-8")).hexdigest(),
            str(row.get("tx_hash") or ""),
            int(row.get("log_index") or 0),
        ),
    )[:target]


def _fetch_case_candidates(
    case_id: str,
    ctx: Dict[str, Any],
    count_rows: Sequence[Dict[str, Any]],
    allocation: int,
    args: argparse.Namespace,
    env: Dict[str, str],
    budget: RequestBudget,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    client = ExplorerClient(case_id, env, budget, Path(args.output_dir) / "explorer_cache")
    strata = _case_strata(case_id, ctx, count_rows, args.start, args.end)
    total_estimate = sum(int(stratum.get("estimated_rows") or 0) for stratum in strata) or DEFAULT_POOL_ESTIMATES[case_id]
    incident_guard = _incident_guard_blocks(client, ctx, args.incident_guard_hours)
    known_txs = _known_txs(ctx)
    per_stratum_targets: List[int] = []
    remaining = allocation
    for index, stratum in enumerate(strata):
        if index + 1 == len(strata):
            per_stratum_targets.append(max(0, remaining))
        else:
            share = max(1, round(allocation * (int(stratum.get("estimated_rows") or 1) / total_estimate)))
            share = min(share, remaining)
            per_stratum_targets.append(share)
            remaining -= share

    case_rows: List[Dict[str, Any]] = []
    stratum_summaries: List[Dict[str, Any]] = []
    for stratum, target in zip(strata, per_stratum_targets):
        if target <= 0:
            continue
        from_block, to_block = _block_range(client, stratum["first_time"], stratum["last_time"])
        estimated = int(stratum.get("estimated_rows") or target)
        cached_logs = _cached_logs_for_stratum(client, stratum, incident_guard)
        if len(cached_logs) >= target:
            raw_logs = cached_logs
            fetch_summary = {
                "strategy": "local_cache_hash_sample",
                "cached_rows_available": len(cached_logs),
            }
        else:
            use_full_scan = estimated < args.small_pool_full_threshold
            if use_full_scan:
                raw_logs, fetch_summary = _fetch_full_small_pool(
                    client,
                    stratum,
                    from_block,
                    to_block,
                    incident_guard,
                    args.explorer_page_size,
                    args.max_full_scan_blocks,
                )
            else:
                raw_logs, fetch_summary = _fetch_sampled_large_pool(
                    client,
                    stratum,
                    from_block,
                    to_block,
                    incident_guard,
                    target,
                    args.explorer_page_size,
                    args.max_pages_per_probe,
                    args.min_probe_blocks,
                )
        rows = [
            _row_from_log(case_id, ctx["chain"], log, stratum)
            for log in raw_logs
            if _valid_hash(log.get("transactionHash")) and str(log.get("transactionHash")).lower() not in known_txs
        ]
        rows = _select_stable(rows, target, f"{case_id}:{stratum['topic0']}:{stratum.get('scope_class')}")
        case_rows.extend(rows)
        stratum_summaries.append(
            {
                "benign_stratum": stratum.get("benign_stratum"),
                "topic0": stratum.get("topic0"),
                "scope_class": stratum.get("scope_class"),
                "address": stratum.get("address", ""),
                "estimated_rows": estimated,
                "target": target,
                "fetched_candidate_logs": len(raw_logs),
                "selected_rows": len(rows),
                "from_block": from_block,
                "to_block": to_block,
                **fetch_summary,
            }
        )
    selected = _select_stable(case_rows, allocation, case_id)
    return selected, {
        "case": case_id,
        "allocation": allocation,
        "selected_rows": len(selected),
        "estimated_pool_rows": total_estimate,
        "incident_guard_blocks": {"from": incident_guard[0], "to": incident_guard[1]},
        "strata": stratum_summaries,
    }


def _top_up_allocations(shortfall: int, allocations: Dict[str, int], estimates: Dict[str, int]) -> Dict[str, int]:
    if shortfall <= 0:
        return allocations
    updated = dict(allocations)
    for case_id in DEFICIT_FILL_ORDER:
        room = max(0, int(estimates.get(case_id, 0)) - updated.get(case_id, 0))
        take = min(room, shortfall)
        updated[case_id] = updated.get(case_id, 0) + take
        shortfall -= take
        if shortfall <= 0:
            break
    return updated


def build_candidates(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output_dir)
    ensure_dir(output_dir)
    candidates_path = output_dir / "benign_candidates.jsonl"
    if args.resume and candidates_path.exists() and not args.rebuild_candidates:
        rows = [
            json.loads(line)
            for line in candidates_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return {
            "rows": rows,
            "summary": read_json(output_dir / "candidate_pools.json") if (output_dir / "candidate_pools.json").exists() else {},
            "resumed": True,
        }

    chains = benign._parse_csv(args.chains)
    contexts = _context_by_case(chains)
    count_rows = _read_count_rows()
    estimates = _pool_estimates(count_rows)
    allocations = _allocation(estimates, args.target_total, args.small_pool_full_threshold)
    env = load_env()
    budget = RequestBudget(max_explorer=args.max_explorer_requests, max_rpc=args.max_candidate_rpc_requests)
    all_rows: List[Dict[str, Any]] = []
    case_summaries: Dict[str, Any] = {}
    checkpoint_dir = output_dir / "candidate_checkpoints"

    if args.dry_run or not args.allow_explorer_fill:
        summary = {
            "dataset": "no_dune_10k_benign_candidates",
            "dry_run": True,
            "target_total": args.target_total,
            "small_pool_full_threshold": args.small_pool_full_threshold,
            "pool_estimates": estimates,
            "allocations": allocations,
            "selection_policy": "small pools are full; large pools use deterministic case/year/topic/block-window hash sampling; no Dune, rank truncation, scoring formula, amount-based ordering, nondeterministic sampling, or chain writes",
        }
        write_json(output_dir / "candidate_pools.json", summary)
        write_jsonl(candidates_path, [])
        return {"rows": [], "summary": summary, "resumed": False}

    for case_id in CASE_ORDER:
        if case_id not in contexts:
            continue
        allocation = int(allocations.get(case_id, 0))
        if allocation <= 0:
            continue
        checkpoint_path = checkpoint_dir / f"{case_id}.json"
        if args.resume and checkpoint_path.exists():
            checkpoint = read_json(checkpoint_path)
            rows = checkpoint.get("rows") if isinstance(checkpoint, dict) else []
            case_summary = checkpoint.get("summary") if isinstance(checkpoint, dict) else {}
            if isinstance(rows, list) and isinstance(case_summary, dict):
                if rows or not args.rebuild_candidates:
                    all_rows.extend(rows)
                    case_summaries[case_id] = case_summary
                    allocations[case_id] = max(int(allocations.get(case_id, 0)), len(rows))
                    continue
        rows, case_summary = _fetch_case_candidates(case_id, contexts[case_id], count_rows, allocation, args, env, budget)
        all_rows.extend(rows)
        case_summaries[case_id] = case_summary
        write_json(
            checkpoint_path,
            {
                "case": case_id,
                "rows": rows,
                "summary": case_summary,
                "contains_api_keys": False,
                "contains_rpc_url": False,
            },
        )

    all_rows = _select_stable(all_rows, args.target_total, "no_dune_10k_initial")
    if len(all_rows) < args.target_total:
        shortfall = args.target_total - len(all_rows)
        for case_id in DEFICIT_FILL_ORDER:
            if shortfall <= 0 or case_id not in contexts:
                break
            current_allocation = int(allocations.get(case_id, 0))
            current_selected = int(case_summaries.get(case_id, {}).get("selected_rows") or 0)
            # Do not ask an already underfilled pool for more rows; move the
            # deficit to a pool whose current allocation was satisfiable.
            if current_selected < current_allocation:
                continue
            room = max(0, int(estimates.get(case_id, 0)) - current_allocation)
            take = min(shortfall, room)
            if take <= 0:
                continue
            new_allocation = current_allocation + take
            rows, case_summary = _fetch_case_candidates(
                case_id,
                contexts[case_id],
                count_rows,
                new_allocation,
                args,
                env,
                budget,
            )
            all_rows = [row for row in all_rows if row.get("case_related_to") != case_id]
            all_rows.extend(rows)
            allocations[case_id] = new_allocation
            case_summaries[case_id] = case_summary
            checkpoint_path = checkpoint_dir / f"{case_id}.json"
            write_json(
                checkpoint_path,
                {
                    "case": case_id,
                    "rows": rows,
                    "summary": case_summary,
                    "contains_api_keys": False,
                    "contains_rpc_url": False,
                },
            )
            all_rows = _select_stable(all_rows, args.target_total, f"no_dune_10k_topup:{case_id}")
            shortfall = args.target_total - len(all_rows)
    write_jsonl(candidates_path, all_rows)
    by_case: Dict[str, int] = {}
    by_label: Dict[str, int] = {}
    for row in all_rows:
        by_case[row["case_related_to"]] = by_case.get(row["case_related_to"], 0) + 1
        by_label[row["label"]] = by_label.get(row["label"], 0) + 1
    summary = {
        "dataset": "no_dune_10k_benign_candidates",
        "dry_run": False,
        "target_total": args.target_total,
        "selected_candidate_count": len(all_rows),
        "small_pool_full_threshold": args.small_pool_full_threshold,
        "pool_estimates": estimates,
        "allocations": allocations,
        "selected_by_case": dict(sorted(by_case.items())),
        "selected_by_label": dict(sorted(by_label.items())),
        "case_summaries": case_summaries,
        "explorer_requests": {
            "used": budget.explorer_used,
            "max": budget.max_explorer,
        },
        "candidate_rpc_requests": {
            "used": budget.rpc_used,
            "max": budget.max_rpc,
        },
        "selection_policy": "small pools are full; large pools use deterministic case/year/topic/block-window hash sampling; no Dune, rank truncation, scoring formula, amount-based ordering, nondeterministic sampling, or chain writes",
        "safety_boundary": "read-only historical explorer/RPC evidence; no write methods, private keys, attack simulation, or future target prediction",
    }
    write_json(output_dir / "candidate_pools.json", summary)
    return {"rows": all_rows, "summary": summary, "resumed": False}


def _write_report(results_dir: Path, candidate_summary: Dict[str, Any], materialization_summary: Optional[Dict[str, Any]]) -> None:
    ensure_dir(results_dir)
    selected_by_case = candidate_summary.get("selected_by_case") or {}
    allocations = candidate_summary.get("allocations") or {}
    pool_estimates = candidate_summary.get("pool_estimates") or {}
    lines = [
        "# No-Dune 10k Benign Evaluation Dataset",
        "",
        "This dataset is built from case-aware historical oracle-scope logs using Explorer/Etherscan and RPC only. Dune count-only results are used only as prior pool-size estimates for allocation.",
        "",
        f"- Target samples: `{candidate_summary.get('target_total', 0)}`",
        f"- Selected candidates: `{candidate_summary.get('selected_candidate_count', 0)}`",
        f"- Explorer requests: `{(candidate_summary.get('explorer_requests') or {}).get('used', 0)}/{(candidate_summary.get('explorer_requests') or {}).get('max', 0)}`",
        f"- Candidate RPC fallback requests: `{(candidate_summary.get('candidate_rpc_requests') or {}).get('used', 0)}/{(candidate_summary.get('candidate_rpc_requests') or {}).get('max', 0)}`",
        "",
        "## Allocation",
        "",
        "| case | estimated pool | allocation | selected |",
        "|---|---:|---:|---:|",
    ]
    for case_id in CASE_ORDER:
        lines.append(
            f"| {case_id} | {int(pool_estimates.get(case_id, 0))} | {int(allocations.get(case_id, 0))} | {int(selected_by_case.get(case_id, 0))} |"
        )
    if materialization_summary:
        budget = materialization_summary.get("request_budget") or {}
        lines.extend(
            [
                "",
                "## Materialization",
                "",
                f"- Materialized samples: `{materialization_summary.get('materialized_sample_count', 0)}`",
                f"- Replay alerts: `{materialization_summary.get('replay_alert_count', 0)}`",
                f"- Strict benign after replay: `{materialization_summary.get('strict_benign_verified_after_replay', 0)}`",
                f"- RPC requests: `{budget.get('rpc_used', 0)}/{budget.get('rpc_max', 0)}`",
                f"- Source requests: `{budget.get('source_used', 0)}/{budget.get('source_max', 0)}`",
                f"- Debug trace requests: `{budget.get('debug_trace_used', 0)}/{budget.get('debug_trace_max', 0)}`",
            ]
        )
    lines.extend(
        [
            "",
            "Only `benign_verified` rows after replay enter the false-positive denominator. `unknown_negative` rows remain a review pool.",
        ]
    )
    (results_dir / "no_dune_10k_benign_eval_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _materialization_batch(rows: Sequence[Dict[str, Any]], materialization_dir: Path, batch_size: int) -> List[Dict[str, Any]]:
    if batch_size <= 0:
        return list(rows)
    checkpoint_dir = materialization_dir / "sample_checkpoints"
    done: set[str] = set()
    if checkpoint_dir.exists():
        for path in checkpoint_dir.glob("*.json"):
            try:
                payload = read_json(path)
            except Exception:
                continue
            sample_id = str(payload.get("sample_id") or "")
            if sample_id:
                done.add(sample_id)
    pending = [row for row in rows if str(row.get("sample_id") or "") not in done]
    return pending[:batch_size]


def run(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output_dir)
    results_dir = Path(args.results_dir)
    ensure_dir(output_dir)
    candidate_result = build_candidates(args)
    candidate_summary = candidate_result.get("summary") or {}
    materialization_summary: Optional[Dict[str, Any]] = None
    rows = candidate_result.get("rows") or []
    should_materialize = bool(args.allow_rpc_fill and rows and not args.dry_run)
    if should_materialize:
        materialization_dir = output_dir / "materialized"
        if args.resume and args.batch_size <= 0 and (materialization_dir / "materialization_summary.json").exists():
            materialization_summary = read_json(materialization_dir / "materialization_summary.json")
        else:
            batch_rows = _materialization_batch(rows, materialization_dir, args.batch_size)
            materialization_summary = materialize_samples(
                batch_rows,
                materialization_dir,
                results_dir,
                args.max_rpc_requests,
                args.max_source_requests if args.allow_explorer_fill else 0,
                args.max_debug_trace_requests,
                args.trace_mode,
                args.resume,
                args.workers,
                {str(row.get("sample_id") or "") for row in rows},
            )
    manifest = {
        "dataset": "no_dune_10k_benign_eval_dataset",
        "candidate_summary_path": str(output_dir / "candidate_pools.json"),
        "candidates_path": str(output_dir / "benign_candidates.jsonl"),
        "materialization_summary_path": str(output_dir / "materialized" / "materialization_summary.json") if materialization_summary else "",
        "dry_run": bool(args.dry_run),
        "allow_explorer_fill": bool(args.allow_explorer_fill),
        "allow_rpc_fill": bool(args.allow_rpc_fill),
        "trace_mode": args.trace_mode,
        "batch_size": args.batch_size,
        "workers": args.workers,
        "safety_boundary": "read-only historical explorer/RPC evidence; no chain writes, no write methods, no private keys, no attack simulation",
    }
    write_json(output_dir / "eval_manifest.json", manifest)
    _write_report(results_dir, candidate_summary, materialization_summary)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a 10k no-Dune case-aware benign evaluation dataset.")
    parser.add_argument("--chains", default="ethereum,bnb,base,avalanche_c")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--target-total", type=int, default=DEFAULT_TARGET_TOTAL)
    parser.add_argument("--small-pool-full-threshold", type=int, default=DEFAULT_SMALL_POOL_THRESHOLD)
    parser.add_argument("--same-oracle-full-scan-threshold", type=int, default=12_000)
    parser.add_argument("--incident-guard-hours", type=int, default=24)
    parser.add_argument("--allow-explorer-fill", action="store_true")
    parser.add_argument("--allow-rpc-fill", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--rebuild-candidates", action="store_true")
    parser.add_argument("--trace-mode", choices=["receipt", "debug", "two-layer"], default="two-layer")
    parser.add_argument("--explorer-page-size", type=int, default=1000)
    parser.add_argument("--max-pages-per-probe", type=int, default=2)
    parser.add_argument("--min-probe-blocks", type=int, default=2000)
    parser.add_argument("--max-full-scan-blocks", type=int, default=50_000)
    parser.add_argument("--max-explorer-requests", type=int, default=25_000)
    parser.add_argument("--max-candidate-rpc-requests", type=int, default=30_000)
    parser.add_argument("--max-rpc-requests", type=int, default=60_000)
    parser.add_argument("--max-source-requests", type=int, default=12_000)
    parser.add_argument("--max-debug-trace-requests", type=int, default=2_000)
    parser.add_argument("--batch-size", type=int, default=0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    args = parser.parse_args()
    try:
        manifest = run(args)
    except PipelineError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
