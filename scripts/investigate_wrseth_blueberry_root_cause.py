#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from eth_utils import keccak

from common import PipelineError, ensure_dir, get_case, load_env, repo_path, resolve_template, rpc_call, write_json
from materialize_feed_binding_case import _norm_addr
from materialize_pre_attack_logs import (
    BLUEBERRY_ATTACK_TX,
    BLUEBERRY_BORROWING_ENABLED_TIME,
    MOONWELL_WRSETH_FIRST_ATTACK_TX,
    MOONWELL_WRSETH_ORACLES,
)


def _topic(signature: str) -> str:
    return "0x" + keccak(text=signature).hex()


def _selector(signature: str) -> str:
    return "0x" + keccak(text=signature)[:4].hex()


OUTPUT_DIR = repo_path("artifacts", "root_cause_queries")
REPORT_PATH = repo_path("results", "wrseth_blueberry_root_cause_queries.md")

MOONWELL_TARGET_TIME = "2025-11-04T05:44:55Z"
MOONWELL_EXTRA_ADDRESSES = {
    "oracle_adapter_from_trace": "0x79c613b4f07080963c3b0ca58eb2745dd4c744a5",
    "moonwell_oracle_wrapper_from_trace": "0xec942be8a8114bfd0396a5052c36027f2ca6a9d0",
    "moonwell_comptroller": "0xfbb21d0380bee3312b33c4353c8936a0f13ef26c",
}

BLUEBERRY_TARGETS = {
    "blueberry_controller": "0xffadb0bba4379dfabfb20ca6823f6ec439429ec2",
    "price_oracle_proxy_path": "0xdfe469ace05c3d0d4461439e6cf5d0f46f33ec56",
    "oracle_impl_path": "0x770d3e22703210c09a573c2043081d97286f415e",
    "core_oracle_path": "0xc5cea3f9c92291335076d4c2ec6ae72e45fb8937",
    "core_oracle_impl_path": "0x5818562baac907b859e27813e8c0962d416dab59",
    "feed_proxy_from_trace_1": "0x9a72298ae3886221820b1c878d12d872087d3a23",
    "feed_proxy_from_trace_2": "0x5f4ec3df9cbd43714fe2740f5e3616155c5b8419",
    "feed_proxy_from_trace_3": "0x8fffffd4afb6115b954bd326cbe7b4ba576818f6",
}
BLUEBERRY_CANDIDATE_TXS = [
    "0xebc5b8def4a740070abdea92597dafa415df71c8160baad53bf8304546ba5fd4",
    "0xec22b433071377b9190eb66d9689418c7c0eec9a3b471932440049f01c3eb4c1",
    "0x28e522e8e0a68cd36f567d76ec6c93fcb04a1a7847f30a355262161a70a93b84",
    "0x60f89a4846cdfe257423cdd8ce0090d013ae68481d71adc6594ac5cdaccf1312",
    "0xddfa180adc51772e78fd2925b6a2b1acca4147b74bea1e3fc334f42c647e879f",
    "0xf3839f44184a01b120c24df84e0bfa3b7913b041909a6cd05005df9612490381",
    "0xadf75e4538de805e0ac8b7b1c22d3e1c1b87d6c13cd6e64021cc9b06ace951b9",
]
COMMON_GETTERS = [
    "aggregator()",
    "oracle()",
    "priceOracle()",
    "getOracle()",
    "implementation()",
    "admin()",
    "owner()",
    "pendingOwner()",
    "decimals()",
    "description()",
    "version()",
    "typeAndVersion()",
    "latestRoundData()",
]
EIP1967_SLOTS = {
    "implementation": hex(int.from_bytes(keccak(text="eip1967.proxy.implementation"), "big") - 1),
    "admin": hex(int.from_bytes(keccak(text="eip1967.proxy.admin"), "big") - 1),
    "beacon": hex(int.from_bytes(keccak(text="eip1967.proxy.beacon"), "big") - 1),
}
KNOWN_EVENT_TOPICS = {
    _topic("AnswerUpdated(int256,uint256,uint256)"): "AnswerUpdated(int256,uint256,uint256)",
    _topic("NewRound(uint256,address,uint256)"): "NewRound(uint256,address,uint256)",
    _topic("NewTransmission(uint32,int192,address,int192[],bytes,bytes32)"): "NewTransmission(uint32,int192,address,int192[],bytes,bytes32)",
    _topic("NewBorrowCap(address,uint256)"): "NewBorrowCap(address,uint256)",
    _topic("NewPriceOracle(address,address)"): "NewPriceOracle(address,address)",
    _topic("NewOracle(address,address)"): "NewOracle(address,address)",
    _topic("SetRoute(address,address)"): "SetRoute(address,address)",
    _topic("SetTokenPriceFeed(address,address)"): "SetTokenPriceFeed(address,address)",
    _topic("SetTimeGap(address,uint256)"): "SetTimeGap(address,uint256)",
    _topic("SetTokenRemapping(address,address)"): "SetTokenRemapping(address,address)",
    _topic("CreditLimitChanged(address,address,uint256)"): "CreditLimitChanged(address,address,uint256)",
    _topic("ActionPaused(address,string,bool)"): "ActionPaused(address,string,bool)",
    _topic("MarketListed(address)"): "MarketListed(address)",
    _topic("OwnershipTransferred(address,address)"): "OwnershipTransferred(address,address)",
    _topic("Upgraded(address)"): "Upgraded(address)",
    _topic("AdminChanged(address,address)"): "AdminChanged(address,address)",
}

@dataclass
class RequestBudget:
    max_rpc: int
    rpc_used: int = 0

    def use(self) -> None:
        if self.rpc_used + 1 > self.max_rpc:
            raise PipelineError(f"RPC request budget exceeded: {self.rpc_used + 1}>{self.max_rpc}")
        self.rpc_used += 1


class Rpc:
    def __init__(self, case_id: str, max_rpc_requests: int):
        self.case_id = case_id
        self.url = resolve_template(get_case(case_id)["rpc_url_template"], load_env())
        self.budget = RequestBudget(max_rpc_requests)
        self.block_cache: Dict[int, Dict[str, Any]] = {}

    def call(self, method: str, params: List[Any], *, optional: bool = False) -> Any:
        self.budget.use()
        try:
            return rpc_call(self.url, method, params, timeout=90)
        except Exception as exc:
            if optional:
                return {"error": str(exc)}
            raise

    def tx(self, tx_hash: str) -> Dict[str, Any]:
        return self.call("eth_getTransactionByHash", [tx_hash]) or {}

    def receipt(self, tx_hash: str) -> Dict[str, Any]:
        return self.call("eth_getTransactionReceipt", [tx_hash]) or {}

    def block(self, block_number: int) -> Dict[str, Any]:
        if block_number not in self.block_cache:
            self.block_cache[block_number] = self.call("eth_getBlockByNumber", [hex(block_number), False]) or {}
        return self.block_cache[block_number]

    def eth_call(self, to: str, data: str, block: int | str = "latest", *, optional: bool = True) -> Any:
        block_tag = hex(block) if isinstance(block, int) else block
        return self.call("eth_call", [{"to": _norm_addr(to), "data": data}, block_tag], optional=optional)

    def storage_at(self, address: str, slot: str, block: int | str = "latest") -> Any:
        block_tag = hex(block) if isinstance(block, int) else block
        return self.call("eth_getStorageAt", [_norm_addr(address), slot, block_tag], optional=True)

    def logs(self, address: str, from_block: int, to_block: int, *, step: int = 5000) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        current = from_block
        while current <= to_block:
            end = min(current + step - 1, to_block)
            result = self.call(
                "eth_getLogs",
                [{"address": _norm_addr(address), "fromBlock": hex(current), "toBlock": hex(end)}],
                optional=True,
            )
            if isinstance(result, dict) and result.get("error"):
                rows.append({"error": result["error"], "fromBlock": current, "toBlock": end})
            else:
                rows.extend(result or [])
            current = end + 1
        return rows

    def block_by_timestamp(self, target_timestamp: int) -> int:
        latest = _hex_to_int(self.call("eth_blockNumber", []))
        low, high = 0, latest
        while low < high:
            mid = (low + high) // 2
            if _hex_to_int(self.block(mid).get("timestamp")) < target_timestamp:
                low = mid + 1
            else:
                high = mid
        return low


def _hex_to_int(value: Any) -> int:
    if value in (None, "", "0x"):
        return 0
    if isinstance(value, int):
        return value
    text = str(value)
    return int(text, 16) if text.startswith("0x") else int(text)


def _iso(block: Dict[str, Any]) -> str:
    ts = _hex_to_int(block.get("timestamp"))
    return datetime.fromtimestamp(ts, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z") if ts else ""


def _unix(value: str) -> int:
    clean = value[:-1] + "+00:00" if value.endswith("Z") else value
    return int(datetime.fromisoformat(clean).astimezone(timezone.utc).timestamp())


def _decode_address_word(value: str) -> str:
    clean = (value or "0x").removeprefix("0x")
    if len(clean) < 64:
        return ""
    return _norm_addr("0x" + clean[-40:])


def _decode_uint(value: str) -> Optional[int]:
    clean = (value or "").removeprefix("0x")
    if len(clean) < 64:
        return None
    return int(clean[:64], 16)


def _decode_string(value: str) -> str:
    clean = (value or "").removeprefix("0x")
    if len(clean) < 128:
        return ""
    try:
        offset = int(clean[:64], 16) * 2
        length = int(clean[offset : offset + 64], 16)
        raw = clean[offset + 64 : offset + 64 + length * 2]
        return bytes.fromhex(raw).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _decode_latest_round_data(value: str) -> Dict[str, Any]:
    clean = (value or "").removeprefix("0x")
    if len(clean) < 64 * 5:
        return {}
    words = [clean[i : i + 64] for i in range(0, 64 * 5, 64)]
    answer_raw = int(words[1], 16)
    if answer_raw >= 2**255:
        answer_raw -= 2**256
    return {
        "round_id": int(words[0], 16),
        "answer_raw": answer_raw,
        "started_at": int(words[2], 16),
        "updated_at": int(words[3], 16),
        "answered_in_round": int(words[4], 16),
        "updated_at_iso": datetime.fromtimestamp(int(words[3], 16), timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z") if int(words[3], 16) else "",
    }


def _decode_call(signature: str, raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, str) or not raw.startswith("0x") or raw == "0x":
        return {"ok": False, "raw": raw}
    if signature in {"aggregator()", "oracle()", "priceOracle()", "getOracle()", "implementation()", "admin()", "owner()", "pendingOwner()"}:
        return {"ok": True, "address": _decode_address_word(raw), "raw": raw}
    if signature in {"decimals()", "version()"}:
        return {"ok": True, "value": _decode_uint(raw), "raw": raw}
    if signature in {"description()", "typeAndVersion()"}:
        return {"ok": True, "value": _decode_string(raw), "raw": raw}
    if signature == "latestRoundData()":
        return {"ok": True, **_decode_latest_round_data(raw), "raw": raw}
    return {"ok": True, "raw": raw}


def _safe_event_name(topic0: str, abi_events: Dict[str, str]) -> str:
    return abi_events.get((topic0 or "").lower()) or KNOWN_EVENT_TOPICS.get((topic0 or "").lower(), "")


def _http_json(url: str, params: Dict[str, Any]) -> Any:
    encoded = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    request = urllib.request.Request(f"{url}?{encoded}", headers={"User-Agent": "oracle-root-cause-query/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _etherscan(action: str, **params: Any) -> Any:
    env = load_env()
    api_key = env.get("ETHERSCAN_KEY")
    if not api_key:
        return {"error": "missing ETHERSCAN_KEY"}
    return _http_json(
        "https://api.etherscan.io/v2/api",
        {"chainid": "1", "module": "contract", "action": action, "apikey": api_key, **params},
    )


def _abi_for(address: str) -> List[Dict[str, Any]]:
    result = _etherscan("getabi", address=address)
    if isinstance(result, dict) and result.get("status") == "1":
        try:
            return json.loads(result.get("result", "[]"))
        except Exception:
            return []
    return []


def _source_for(address: str) -> Dict[str, Any]:
    result = _etherscan("getsourcecode", address=address)
    if isinstance(result, dict) and isinstance(result.get("result"), list) and result["result"]:
        item = dict(result["result"][0])
        item.pop("SourceCode", None)
        return item
    return {"error": result.get("result") if isinstance(result, dict) else str(result)}


def _creation_for(addresses: Iterable[str]) -> Any:
    env = load_env()
    api_key = env.get("ETHERSCAN_KEY")
    if not api_key:
        return {"error": "missing ETHERSCAN_KEY"}
    normalized = [_norm_addr(a) for a in addresses]
    rows = []
    for index in range(0, len(normalized), 5):
        result = _http_json(
            "https://api.etherscan.io/v2/api",
            {
                "chainid": "1",
                "module": "contract",
                "action": "getcontractcreation",
                "contractaddresses": ",".join(normalized[index : index + 5]),
                "apikey": api_key,
            },
        )
        if not isinstance(result, dict) or result.get("status") != "1":
            return result
        rows.extend(result.get("result") or [])
    return {"status": "1", "message": "OK", "result": rows}


def _abi_maps(abis: Dict[str, List[Dict[str, Any]]]) -> Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, str]]]:
    functions: Dict[str, Dict[str, str]] = {}
    events: Dict[str, Dict[str, str]] = {}
    for address, abi in abis.items():
        f_map: Dict[str, str] = {}
        e_map: Dict[str, str] = {}
        for item in abi:
            if item.get("type") == "function":
                sig = f"{item.get('name')}({','.join(inp.get('type','') for inp in item.get('inputs', []))})"
                f_map[_selector(sig)] = sig
            elif item.get("type") == "event":
                sig = f"{item.get('name')}({','.join(inp.get('type','') for inp in item.get('inputs', []))})"
                e_map[_topic(sig)] = sig
        functions[address.lower()] = f_map
        events[address.lower()] = e_map
    return functions, events


def _tx_summary(rpc: Rpc, tx_hash: str, fn_maps: Dict[str, Dict[str, str]], event_maps: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    tx = rpc.tx(tx_hash)
    receipt = rpc.receipt(tx_hash)
    block_number = _hex_to_int(receipt.get("blockNumber") or tx.get("blockNumber"))
    input_data = tx.get("input") or tx.get("data") or ""
    selector = input_data[:10] if input_data and input_data != "0x" else ""
    to_addr = _norm_addr(tx.get("to", "")) if tx.get("to") else ""
    event_counts: Dict[str, int] = {}
    touched_addresses = set()
    for log in receipt.get("logs") or []:
        address = _norm_addr(log.get("address", ""))
        touched_addresses.add(address)
        topics = log.get("topics") or []
        topic0 = (topics[0] if topics else "").lower()
        event_name = _safe_event_name(topic0, event_maps.get(address.lower(), {})) or topic0
        event_counts[event_name] = event_counts.get(event_name, 0) + 1
    return {
        "tx_hash": tx_hash,
        "block_number": block_number,
        "block_time": _iso(rpc.block(block_number)) if block_number else "",
        "from": _norm_addr(tx.get("from", "")) if tx.get("from") else "",
        "to": to_addr,
        "input_selector": selector,
        "decoded_function": fn_maps.get(to_addr.lower(), {}).get(selector, ""),
        "input_prefix": input_data[:138],
        "receipt_status": _hex_to_int(receipt.get("status")),
        "log_count": len(receipt.get("logs") or []),
        "event_counts": event_counts,
        "touched_target_addresses": sorted(address for address in touched_addresses if address in {_norm_addr(v) for v in BLUEBERRY_TARGETS.values()}),
    }


def investigate_moonwell(max_rpc: int, lookback_blocks: int) -> Dict[str, Any]:
    rpc = Rpc("moonwell_wrseth", max_rpc)
    attack_receipt = rpc.receipt(MOONWELL_WRSETH_FIRST_ATTACK_TX)
    attack_block = _hex_to_int(attack_receipt.get("blockNumber"))
    target_block = rpc.block_by_timestamp(_unix(MOONWELL_TARGET_TIME))
    addresses: Dict[str, str] = {
        "wrseth_eth_oracle": MOONWELL_WRSETH_ORACLES[0],
        "eth_usd_oracle": MOONWELL_WRSETH_ORACLES[1],
        **MOONWELL_EXTRA_ADDRESSES,
    }
    calls: Dict[str, Dict[str, Any]] = {}
    extra_scan_addresses = dict(addresses)
    for role, address in addresses.items():
        role_calls: Dict[str, Any] = {}
        for sig in COMMON_GETTERS:
            raw = rpc.eth_call(address, _selector(sig), block=max(target_block, attack_block - 1))
            role_calls[sig] = _decode_call(sig, raw)
            if sig == "aggregator()" and role_calls[sig].get("address"):
                extra_scan_addresses[f"{role}_aggregator"] = role_calls[sig]["address"]
        calls[role] = role_calls
    log_summary: Dict[str, Any] = {}
    from_block = max(0, target_block - lookback_blocks)
    to_block = attack_block - 1
    for role, address in sorted(extra_scan_addresses.items()):
        logs = rpc.logs(address, from_block, to_block, step=10000)
        topic_counts: Dict[str, int] = {}
        latest = None
        errors = []
        for log in logs:
            if "error" in log:
                errors.append(log)
                continue
            topics = log.get("topics") or []
            topic0 = (topics[0] if topics else "").lower()
            topic_counts[topic0] = topic_counts.get(topic0, 0) + 1
            latest = log if latest is None or _hex_to_int(log.get("blockNumber")) >= _hex_to_int(latest.get("blockNumber")) else latest
        log_summary[role] = {
            "address": address,
            "from_block": from_block,
            "to_block": to_block,
            "log_count": sum(topic_counts.values()),
            "topic_counts": topic_counts,
            "known_topic_names": {topic: KNOWN_EVENT_TOPICS.get(topic, "") for topic in topic_counts},
            "latest_tx": latest.get("transactionHash") if latest else "",
            "latest_block": _hex_to_int(latest.get("blockNumber")) if latest else None,
            "errors": errors[:3],
        }
    return {
        "case": "moonwell_wrseth",
        "target_time": MOONWELL_TARGET_TIME,
        "target_block": target_block,
        "first_attack_tx": MOONWELL_WRSETH_FIRST_ATTACK_TX,
        "first_attack_block": attack_block,
        "calls_at_or_before_attack": calls,
        "pre_attack_log_summary": log_summary,
        "rpc_used": rpc.budget.rpc_used,
    }


def investigate_blueberry(max_rpc: int, include_trace: bool) -> Dict[str, Any]:
    rpc = Rpc("blueberry_faulty_oracle", max_rpc)
    attack_receipt = rpc.receipt(BLUEBERRY_ATTACK_TX)
    attack_block = _hex_to_int(attack_receipt.get("blockNumber"))
    block_before_attack = max(0, attack_block - 1)
    addresses = {_norm_addr(v): role for role, v in BLUEBERRY_TARGETS.items()}
    creations = _creation_for(addresses.keys())
    abis = {address: _abi_for(address) for address in addresses}
    fn_maps, event_maps = _abi_maps(abis)
    sources = {address: _source_for(address) for address in addresses}
    getter_results: Dict[str, Dict[str, Any]] = {}
    proxy_slots: Dict[str, Dict[str, Any]] = {}
    for address, role in addresses.items():
        getter_results[role] = {}
        for sig in COMMON_GETTERS:
            raw = rpc.eth_call(address, _selector(sig), block=block_before_attack)
            decoded = _decode_call(sig, raw)
            if decoded.get("ok") or not isinstance(raw, dict):
                getter_results[role][sig] = decoded
        proxy_slots[role] = {
            name: {"raw": raw, "decoded_address": _decode_address_word(raw if isinstance(raw, str) else "")}
            for name, slot in EIP1967_SLOTS.items()
            for raw in [rpc.storage_at(address, slot, block=block_before_attack)]
        }
    tx_summaries = [_tx_summary(rpc, tx_hash, fn_maps, event_maps) for tx_hash in BLUEBERRY_CANDIDATE_TXS]
    traces: Dict[str, Any] = {}
    if include_trace:
        for tx_hash in BLUEBERRY_CANDIDATE_TXS[:3]:
            result = rpc.call(
                "debug_traceTransaction",
                [tx_hash, {"tracer": "prestateTracer", "tracerConfig": {"diffMode": True}}],
                optional=True,
            )
            if isinstance(result, dict) and "error" not in result:
                pre = result.get("pre") if isinstance(result.get("pre"), dict) else {}
                post = result.get("post") if isinstance(result.get("post"), dict) else {}
                touched = sorted(set(pre) | set(post))
                traces[tx_hash] = {
                    "supported": True,
                    "pre_address_count": len(pre),
                    "post_address_count": len(post),
                    "touched_address_count": len(touched),
                    "sample_touched_addresses": touched[:50],
                }
            else:
                traces[tx_hash] = {"supported": False, "error": result.get("error") if isinstance(result, dict) else str(result)}
    return {
        "case": "blueberry_faulty_oracle",
        "seed_time": BLUEBERRY_BORROWING_ENABLED_TIME,
        "first_attack_tx": BLUEBERRY_ATTACK_TX,
        "first_attack_block": attack_block,
        "target_addresses": BLUEBERRY_TARGETS,
        "contract_creation": creations,
        "source_metadata": sources,
        "verified_abi_functions": {addresses[address]: len([item for item in abi if item.get("type") == "function"]) for address, abi in abis.items()},
        "getter_results_before_attack": getter_results,
        "eip1967_slots_before_attack": proxy_slots,
        "candidate_config_tx_summaries": tx_summaries,
        "storage_diff_trace": traces,
        "rpc_used": rpc.budget.rpc_used,
    }


def render_report(moonwell: Dict[str, Any], blueberry: Dict[str, Any]) -> str:
    lines = [
        "# wrsETH / Blueberry Root Cause Query Results",
        "",
        "## Moonwell wrsETH",
        "",
        f"- Target malfunction time: `{moonwell['target_time']}`, target block `{moonwell['target_block']}`.",
        f"- First attack tx: `{moonwell['first_attack_tx']}`, block `{moonwell['first_attack_block']}`.",
        "- Historical calls and logs were queried on the wrsETH/ETH oracle, ETH/USD oracle, traced adapter/wrapper, comptroller, and any readable `aggregator()` targets.",
        "",
        "| role | address | latestRoundData updated_at | answer_raw | pre-attack logs | latest log tx |",
        "|---|---|---:|---:|---:|---|",
    ]
    calls = moonwell.get("calls_at_or_before_attack") or {}
    logs = moonwell.get("pre_attack_log_summary") or {}
    for role, summary in logs.items():
        latest_round = (calls.get(role) or {}).get("latestRoundData()") or {}
        lines.append(
            f"| `{role}` | `{summary.get('address','')}` | `{latest_round.get('updated_at_iso','')}` | "
            f"`{latest_round.get('answer_raw','')}` | {summary.get('log_count', 0)} | `{summary.get('latest_tx','')}` |"
        )
    lines.extend(
        [
            "",
            "## Blueberry",
            "",
            f"- First attack tx: `{blueberry['first_attack_tx']}`, block `{blueberry['first_attack_block']}`.",
            "- Queried contract creation/source metadata, common getters, EIP-1967 slots, candidate pre-attack config transactions, and optional storage diff trace.",
            "",
            "| tx | block time | to | selector | decoded function | target events |",
            "|---|---|---|---|---|---|",
        ]
    )
    for tx in blueberry.get("candidate_config_tx_summaries") or []:
        events = "; ".join(f"{k}:{v}" for k, v in sorted((tx.get("event_counts") or {}).items())[:4])
        lines.append(
            f"| `{tx.get('tx_hash')}` | `{tx.get('block_time')}` | `{tx.get('to')}` | "
            f"`{tx.get('input_selector')}` | `{tx.get('decoded_function')}` | {events} |"
        )
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "- JSON: `artifacts/root_cause_queries/wrseth_blueberry_root_cause.json`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Investigate wrsETH and Blueberry root-cause evidence beyond plain pre-attack logs.")
    parser.add_argument("--case", choices=["all", "moonwell_wrseth", "blueberry_faulty_oracle"], default="all")
    parser.add_argument("--max-rpc-requests", type=int, default=900)
    parser.add_argument("--moonwell-lookback-blocks", type=int, default=5000)
    parser.add_argument("--include-trace", action="store_true", help="Attempt debug_traceTransaction storage diff queries for selected Blueberry txs.")
    args = parser.parse_args()
    ensure_dir(OUTPUT_DIR)
    moonwell: Dict[str, Any] = {}
    blueberry: Dict[str, Any] = {}
    if args.case in {"all", "moonwell_wrseth"}:
        moonwell = investigate_moonwell(args.max_rpc_requests, args.moonwell_lookback_blocks)
    if args.case in {"all", "blueberry_faulty_oracle"}:
        blueberry = investigate_blueberry(args.max_rpc_requests, args.include_trace)
    result = {"moonwell_wrseth": moonwell, "blueberry_faulty_oracle": blueberry}
    write_json(OUTPUT_DIR / "wrseth_blueberry_root_cause.json", result)
    if moonwell and blueberry:
        ensure_dir(REPORT_PATH.parent)
        REPORT_PATH.write_text(render_report(moonwell, blueberry), encoding="utf-8")
    print(f"wrote={OUTPUT_DIR / 'wrseth_blueberry_root_cause.json'}")
    if moonwell:
        print(f"moonwell_rpc_used={moonwell.get('rpc_used')}")
    if blueberry:
        print(f"blueberry_rpc_used={blueberry.get('rpc_used')}")


if __name__ == "__main__":
    main()
