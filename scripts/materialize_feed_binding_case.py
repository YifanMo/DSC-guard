#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from common import (
    PipelineError,
    ensure_dir,
    get_case,
    http_json,
    load_env,
    repo_path,
    resolve_template,
    rpc_call,
    write_json,
    write_jsonl,
)


SUPPORTED_CASES = {"ploutos"}
EVIDENCE_QUALITY = "real_tx_with_inferred_decode"
FLOW_EVIDENCE_QUALITY = "real_tx_with_receipt_flow_decode"
ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
CHAINLINK_DESCRIPTION_SELECTOR = "0x7284e416"
CHAINLINK_DECIMALS_SELECTOR = "0x313ce567"
BOUNDARY_TXS = {
    "ploutos": [
        {
            "role": "repair",
            "event_type": "ORACLE_FEED_REPAIRED",
            "hash": "0xee3d7556528d3ceb00681a3c7ed7be3751c83923675bc3774c77f9f4e60d20f0",
            "note": "Oracle feed was changed after the exploit transaction.",
            "feed_after": "0x3e7d1eab13ad0104d2750b8863b489d65364e32d",
        },
    ],
}
FEED_PROBES = {
    "ploutos": {
        "forbidden_feed": "0xf4030086522a5beea4988f8ca5b36dbc97bee88c",
        "repair_feed": "0x3e7d1eab13ad0104d2750b8863b489d65364e32d",
    },
}
TOKEN_METADATA = {
    "ethereum": {
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": {"symbol": "USDC", "decimals": 6},
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": {"symbol": "WETH", "decimals": 18},
        "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": {"symbol": "WBTC", "decimals": 8},
        "0x64aa3364f17a4d01c6f1751fd97c2bd3d7e7f1d5": {"symbol": "OHM", "decimals": 9},
    },
    "base": {
        "0x2ae3f1ec7f1f5012cfeab0185bfc7aa3cf0dec22": {"symbol": "cbETH", "decimals": 18},
        "0x4200000000000000000000000000000000000006": {"symbol": "WETH", "decimals": 18},
        "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": {"symbol": "USDC", "decimals": 6},
        "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca": {"symbol": "USDbC", "decimals": 6},
    },
}


def _hex_to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, int):
        return value
    return int(str(value), 16)


def _norm_addr(value: str) -> str:
    value = (value or "").lower()
    if not value.startswith("0x"):
        value = f"0x{value}"
    body = value[2:]
    return "0x" + body.rjust(40, "0")[-40:]


def _selector(input_data: str) -> str:
    data = input_data or "0x"
    return data[:10] if len(data) >= 10 else data


def _decode_abi_string(value: str) -> str:
    if not value or value == "0x":
        return ""
    data = bytes.fromhex(value[2:])
    if len(data) >= 64:
        length = int.from_bytes(data[32:64], "big")
        return data[64 : 64 + length].decode("utf-8", errors="replace")
    return data.rstrip(b"\x00").decode("utf-8", errors="replace")


def _topic_address(topic: str) -> str:
    topic = topic or "0x"
    return _norm_addr(topic[-40:])


def _hex_data_to_int(value: str) -> int:
    value = value or "0x0"
    return int(value, 16)


def _format_amount(raw: int, decimals: Optional[int]) -> str:
    if decimals is None:
        return str(raw)
    amount = Decimal(raw) / (Decimal(10) ** decimals)
    text = format(amount, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _iso_from_timestamp(value: int) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _feed_constraint(case: Dict[str, Any]) -> Dict[str, Any]:
    for constraint in case.get("constraints", []):
        if constraint.get("type") == "feed_mismatch":
            return constraint
    raise PipelineError(f"Case {case['id']} has no feed_mismatch constraint.")


def _fixture_like_address(value: str) -> bool:
    body = (value or "").lower().removeprefix("0x")
    return len(body) == 40 and len(set(body)) == 1


def _token_meta(chain: str, token_address: str) -> Dict[str, Any]:
    meta = TOKEN_METADATA.get(chain, {}).get(_norm_addr(token_address))
    if meta:
        return dict(meta)
    return {"symbol": "UNKNOWN", "decimals": None}


def decode_erc20_transfer(log: Dict[str, Any], chain: str) -> Optional[Dict[str, Any]]:
    topics = [str(topic).lower() for topic in (log.get("topics") or [])]
    if len(topics) < 3 or topics[0] != ERC20_TRANSFER_TOPIC:
        return None
    token_address = _norm_addr(log.get("address", ""))
    amount_raw = _hex_data_to_int(log.get("data") or "0x0")
    meta = _token_meta(chain, token_address)
    return {
        "token_address": token_address,
        "symbol": meta["symbol"],
        "decimals": meta["decimals"],
        "from": _topic_address(topics[1]),
        "to": _topic_address(topics[2]),
        "amount_raw": str(amount_raw),
        "amount": _format_amount(amount_raw, meta["decimals"]),
        "log_index": _hex_to_int(log.get("logIndex", "0x0")),
        "tx_hash": log.get("transactionHash"),
    }


def transfer_flow_summary(
    receipt: Dict[str, Any],
    chain: str,
    attacker: str,
    protocol: str,
) -> List[Dict[str, Any]]:
    attacker = _norm_addr(attacker)
    protocol = _norm_addr(protocol)
    flows: List[Dict[str, Any]] = []
    for log in receipt.get("logs", []):
        transfer = decode_erc20_transfer(log, chain)
        if not transfer:
            continue
        direction = "other"
        if transfer["from"] == attacker and transfer["to"] == protocol:
            direction = "attacker_to_protocol"
        elif transfer["from"] == protocol and transfer["to"] == attacker:
            direction = "protocol_to_attacker"
        elif transfer["from"] == attacker:
            direction = "attacker_outbound"
        elif transfer["to"] == attacker:
            direction = "attacker_inbound"
        elif transfer["from"] == protocol:
            direction = "protocol_outbound"
        elif transfer["to"] == protocol:
            direction = "protocol_inbound"
        item = dict(transfer)
        item["direction"] = direction
        flows.append(item)
    return sorted(flows, key=lambda item: item["log_index"])


@dataclass
class RequestBudget:
    max_rpc: int
    max_abi: int
    rpc_used: int = 0
    abi_used: int = 0

    def use_rpc(self, count: int = 1) -> None:
        if self.rpc_used + count > self.max_rpc:
            raise PipelineError(f"RPC request budget exceeded: {self.rpc_used + count}>{self.max_rpc}")
        self.rpc_used += count

    def use_abi(self, count: int = 1) -> None:
        if self.abi_used + count > self.max_abi:
            raise PipelineError(f"ABI request budget exceeded: {self.abi_used + count}>{self.max_abi}")
        self.abi_used += count


def _rpc(rpc_url: str, method: str, params: List[Any], budget: RequestBudget, attempts: int = 3) -> Any:
    last_error: Optional[Exception] = None
    for attempt in range(attempts):
        budget.use_rpc()
        try:
            return rpc_call(rpc_url, method, params)
        except Exception as exc:  # pragma: no cover - provider/network failures vary
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1)
    raise PipelineError(f"Read-only RPC request failed for {method}: {last_error}") from last_error


def _probe_chainlink_feed(rpc_url: str, address: str, budget: RequestBudget) -> Dict[str, Any]:
    if not address:
        return {"address": "", "description": "", "decimals": None, "available": False}
    try:
        description_raw = _rpc(
            rpc_url,
            "eth_call",
            [{"to": _norm_addr(address), "data": CHAINLINK_DESCRIPTION_SELECTOR}, "latest"],
            budget,
        )
        decimals_raw = _rpc(
            rpc_url,
            "eth_call",
            [{"to": _norm_addr(address), "data": CHAINLINK_DECIMALS_SELECTOR}, "latest"],
            budget,
        )
    except PipelineError as exc:
        return {"address": _norm_addr(address), "description": "", "decimals": None, "available": False, "error": str(exc)}
    return {
        "address": _norm_addr(address),
        "description": _decode_abi_string(description_raw),
        "decimals": int(decimals_raw, 16) if decimals_raw and decimals_raw != "0x" else None,
        "available": True,
    }


def _fetch_abi(case: Dict[str, Any], address: str, env: Dict[str, str], budget: RequestBudget) -> Dict[str, Any]:
    if not address or address == "0x0000000000000000000000000000000000000000":
        return {"available": False, "reason": "empty_address"}
    api = case.get("explorer_api")
    key_name = case.get("api_key_env")
    if not api or not key_name or not env.get(key_name):
        return {"available": False, "reason": "explorer_api_or_key_missing"}

    budget.use_abi()
    params: Dict[str, Any] = {
        "module": "contract",
        "action": "getabi",
        "address": address,
        "apikey": env[key_name],
    }
    if "/v2/" in api:
        params["chainid"] = case["chain_id"]
    try:
        payload = http_json(api, params)
    except Exception as exc:  # pragma: no cover - network errors vary by provider
        return {"available": False, "reason": f"abi_request_failed:{exc}"}

    result = payload.get("result") if isinstance(payload, dict) else None
    if not result or result in ("Contract source code not verified", "Max rate limit reached"):
        return {"available": False, "reason": str(result or "empty_abi_result")}
    try:
        abi = json.loads(result)
    except json.JSONDecodeError:
        return {"available": False, "reason": "abi_json_decode_failed"}

    function_names = sorted(
        {
            item.get("name", "")
            for item in abi
            if isinstance(item, dict) and item.get("type") == "function" and item.get("name")
        }
    )
    relevant = [
        name
        for name in function_names
        if any(keyword in name.lower() for keyword in ("oracle", "feed", "source", "borrow", "mint", "supply"))
    ]
    return {
        "available": True,
        "function_count": len(function_names),
        "relevant_functions": relevant[:20],
    }


def _tx_summary(tx: Dict[str, Any], receipt: Dict[str, Any], block: Dict[str, Any], abi: Dict[str, Any]) -> Dict[str, Any]:
    timestamp = _hex_to_int(block.get("timestamp"))
    return {
        "hash": tx.get("hash") or receipt.get("transactionHash"),
        "from": _norm_addr(tx.get("from", "")),
        "to": _norm_addr(tx.get("to", "")) if tx.get("to") else "",
        "block_number": _hex_to_int(receipt.get("blockNumber")),
        "block_timestamp": timestamp,
        "block_time": _iso_from_timestamp(timestamp) if timestamp else "",
        "transaction_index": _hex_to_int(receipt.get("transactionIndex")),
        "status": _hex_to_int(receipt.get("status", "0x0")),
        "input_selector": _selector(tx.get("input", "")),
        "log_count": len(receipt.get("logs", [])),
        "raw_log_addresses": sorted({_norm_addr(log.get("address", "")) for log in receipt.get("logs", []) if log.get("address")}),
        "abi": abi,
    }


def _raw_evidence_snapshot(
    case: Dict[str, Any],
    receipts: Dict[str, Dict[str, Any]],
    txs: Dict[str, Dict[str, Any]],
    blocks: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "case": case["id"],
        "chain": case["chain"],
        "scope": "raw read-only RPC evidence for configured known transactions",
        "contains_api_keys": False,
        "rpc_methods": ["eth_getTransactionReceipt", "eth_getTransactionByHash", "eth_getBlockByNumber"],
        "transactions": {
            role: {
                "transaction": txs[role],
                "receipt": receipts[role],
                "block": blocks[receipts[role]["blockNumber"]],
            }
            for role in txs
        },
    }


def collect_remote_materialized(case_id: str, max_rpc_requests: int, max_abi_requests: int) -> Dict[str, Any]:
    case = get_case(case_id)
    if case_id not in SUPPORTED_CASES:
        raise PipelineError("materialize_feed_binding_case.py supports only active feed-binding case ploutos.")
    known = case.get("known_txs") or {}
    if "config" not in known or "exploit" not in known:
        raise PipelineError(f"Case {case_id} must define known_txs.config and known_txs.exploit.")

    env = load_env()
    rpc_url = resolve_template(case["rpc_url_template"], env)
    budget = RequestBudget(max_rpc=max_rpc_requests, max_abi=max_abi_requests)

    receipts: Dict[str, Dict[str, Any]] = {}
    txs: Dict[str, Dict[str, Any]] = {}
    blocks: Dict[str, Dict[str, Any]] = {}
    abis: Dict[str, Dict[str, Any]] = {}

    tx_roles = [
        {"role": "config", "hash": known["config"]},
        {"role": "exploit", "hash": known["exploit"]},
        *BOUNDARY_TXS.get(case_id, []),
    ]
    for tx_role in tx_roles:
        role = tx_role["role"]
        tx_hash = tx_role["hash"]
        receipt = _rpc(rpc_url, "eth_getTransactionReceipt", [tx_hash], budget)
        if not receipt:
            raise PipelineError(f"No receipt returned for {case_id}:{role}:{tx_hash}")
        tx = _rpc(rpc_url, "eth_getTransactionByHash", [tx_hash], budget)
        if not tx:
            raise PipelineError(f"No transaction returned for {case_id}:{role}:{tx_hash}")
        block_number = receipt.get("blockNumber")
        if block_number not in blocks:
            block = _rpc(rpc_url, "eth_getBlockByNumber", [block_number, False], budget)
            if not block:
                raise PipelineError(f"No block returned for {case_id}:{role}:{block_number}")
            blocks[block_number] = block
        receipts[role] = receipt
        txs[role] = tx

    for address in sorted({tx.get("to", "") for tx in txs.values() if tx.get("to")}):
        abis[_norm_addr(address)] = _fetch_abi(case, _norm_addr(address), env, budget)

    exploit_attacker = _norm_addr(txs["exploit"].get("from", ""))
    exploit_protocol = _norm_addr(txs["exploit"].get("to", ""))
    flow_summary = transfer_flow_summary(receipts["exploit"], case["chain"], exploit_attacker, exploit_protocol)
    evidence_quality = FLOW_EVIDENCE_QUALITY if flow_summary else EVIDENCE_QUALITY

    transaction_summaries = {
        role: _tx_summary(txs[role], receipts[role], blocks[receipts[role]["blockNumber"]], abis.get(_norm_addr(txs[role].get("to", "")), {"available": False}))
        for role in txs
    }
    boundary_logs = []
    for tx_role in BOUNDARY_TXS.get(case_id, []):
        role = tx_role["role"]
        summary = transaction_summaries[role]
        boundary_logs.append(
            {
                "role": role,
                "event_type": tx_role["event_type"],
                "hash": summary["hash"],
                "from": summary["from"],
                "to": summary["to"],
                "block_number": summary["block_number"],
                "block_timestamp": summary["block_timestamp"],
                "block_time": summary["block_time"],
                "transaction_index": summary["transaction_index"],
                "status": summary["status"],
                "input_selector": summary["input_selector"],
                "log_count": summary["log_count"],
                "raw_log_addresses": summary["raw_log_addresses"],
                "feed_after": _norm_addr(tx_role.get("feed_after", "")) if tx_role.get("feed_after") else "",
                "note": tx_role.get("note", ""),
            }
        )

    feed_identity = {
        name: _probe_chainlink_feed(rpc_url, address, budget)
        for name, address in (FEED_PROBES.get(case_id) or {}).items()
    }

    materialized = {
        "case": case_id,
        "case_name": case["name"],
        "chain": case["chain"],
        "scope": "read-only known-transaction materialization for feed-binding oracle-consumption evidence with remediation boundary logs",
        "safety": {
            "rpc_methods": ["eth_getTransactionReceipt", "eth_getTransactionByHash", "eth_getBlockByNumber", "eth_call"],
            "no_write_calls": True,
            "no_private_keys": True,
            "no_open_ended_getlogs": True,
        },
        "evidence_quality": evidence_quality,
        "request_budget": {
            "rpc_used": budget.rpc_used,
            "rpc_max": budget.max_rpc,
            "abi_used": budget.abi_used,
            "abi_max": budget.max_abi,
        },
        "transactions": transaction_summaries,
        "boundary_logs": boundary_logs,
        "feed_identity_verification": feed_identity,
        "raw_evidence_artifact": f"artifacts/feed_binding_locator/{case_id}_raw_evidence.json",
        "transfer_flow_summary": flow_summary,
    }
    return {
        "materialized": materialized,
        "raw_evidence": _raw_evidence_snapshot(case, receipts, txs, blocks),
    }


def build_trace_records(case: Dict[str, Any], materialized: Dict[str, Any]) -> List[Dict[str, Any]]:
    constraint = _feed_constraint(case)
    config = materialized["transactions"]["config"]
    exploit = materialized["transactions"]["exploit"]
    flow_summary = materialized.get("transfer_flow_summary") or []
    attacker = exploit["from"]
    asset = constraint["asset"]
    expected_feed = constraint.get("expected_feed", "")
    actual_feed = constraint.get("forbidden_feed") or materialized.get("actual_feed") or "unknown"
    asset_alias = (constraint.get("asset_aliases") or [""])[0]

    if _fixture_like_address(attacker):
        raise PipelineError(f"Refusing to materialize fixture-like attacker address for {case['id']}: {attacker}")

    config_decoded = {
        "asset": asset,
        "expected_feed": expected_feed,
        "actual_feed": actual_feed,
        "actor": config["from"],
        "oracle_contract": config["to"],
        "selector": config["input_selector"],
        "abi": config["abi"],
        "evidence_quality": materialized["evidence_quality"],
        "decode_note": "feed identity is taken from the incident constraint and known config transaction; receipt and actor are historical",
        "raw_log_addresses": config["raw_log_addresses"],
    }
    if asset_alias:
        config_decoded["asset_alias"] = asset_alias

    supply_decoded = {
        "account": attacker,
        "asset": asset,
        "amount": "unknown",
        "tx_to": exploit["to"],
        "evidence_quality": materialized["evidence_quality"],
        "decode_note": "supply side is inferred from the known exploit transaction; amount is not fabricated",
        "raw_log_addresses": exploit["raw_log_addresses"],
        "transfer_flow_summary": flow_summary,
    }

    borrow_decoded = {
        "borrower": attacker,
        "collateral_asset": asset,
        "borrow_asset": "unknown",
        "borrow_amount": "unknown",
        "tx_to": exploit["to"],
        "evidence_quality": materialized["evidence_quality"],
        "decode_note": "borrower is the historical exploit transaction sender; asset amounts require protocol-specific ABI decoding",
        "raw_log_addresses": exploit["raw_log_addresses"],
        "transfer_flow_summary": flow_summary,
    }

    records = [
        {
            "case": case["id"],
            "event_type": "ORACLE_FEED_SET",
            "block_number": config["block_number"],
            "block_timestamp": config["block_timestamp"],
            "tx_hash": config["hash"],
            "transaction_index": config["transaction_index"],
            "log_index": 0,
            "address": config["to"],
            "decoded": config_decoded,
        },
        {
            "case": case["id"],
            "event_type": "SUPPLY",
            "block_number": exploit["block_number"],
            "block_timestamp": exploit["block_timestamp"],
            "tx_hash": exploit["hash"],
            "transaction_index": exploit["transaction_index"],
            "log_index": 0,
            "address": exploit["to"],
            "decoded": supply_decoded,
        },
        {
            "case": case["id"],
            "event_type": "BORROW",
            "block_number": exploit["block_number"],
            "block_timestamp": exploit["block_timestamp"],
            "tx_hash": exploit["hash"],
            "transaction_index": exploit["transaction_index"],
            "log_index": 1,
            "address": exploit["to"],
            "decoded": borrow_decoded,
        },
    ]
    for index, boundary in enumerate(materialized.get("boundary_logs") or [], start=1):
        records.append(
            {
                "case": case["id"],
                "event_type": boundary["event_type"],
                "block_number": boundary["block_number"],
                "block_timestamp": boundary["block_timestamp"],
                "tx_hash": boundary["hash"],
                "transaction_index": boundary["transaction_index"],
                "log_index": index,
                "address": boundary["to"],
                "decoded": {
                    "actor": boundary["from"],
                    "oracle_contract": boundary["to"],
                    "selector": boundary["input_selector"],
                    "status": boundary["status"],
                    "feed_after": boundary.get("feed_after", ""),
                    "note": boundary.get("note", ""),
                    "evidence_quality": materialized["evidence_quality"],
                    "raw_log_addresses": boundary.get("raw_log_addresses", []),
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


def render_report(case: Dict[str, Any], materialized: Dict[str, Any], trace_path: Path, evidence_path: Path, raw_path: Path) -> str:
    config = materialized["transactions"]["config"]
    exploit = materialized["transactions"]["exploit"]
    constraint = _feed_constraint(case)
    flow_summary = materialized.get("transfer_flow_summary") or []
    flow_lines = [
        f"- log `{item['log_index']}`: `{item['direction']}` {item['amount']} {item['symbol']} (`{item['token_address']}`), from `{item['from']}` to `{item['to']}`"
        for item in flow_summary
    ]
    if not flow_lines:
        flow_lines = ["- No ERC20 Transfer logs decoded from the exploit receipt."]
    boundary_lines = []
    for boundary in materialized.get("boundary_logs") or []:
        feed_after = boundary.get("feed_after")
        feed_suffix = f", feed_after `{feed_after}`" if feed_after else ""
        boundary_lines.append(
            f"- `{boundary['event_type']}` tx `{boundary['hash']}` at `{boundary['block_time']}`"
            f" by `{boundary['from']}`{feed_suffix}; status `{boundary['status']}`."
        )
    if not boundary_lines:
        boundary_lines = ["- No remediation boundary logs are configured for this case."]
    feed_lines = []
    for name, feed in (materialized.get("feed_identity_verification") or {}).items():
        feed_lines.append(
            f"- `{name}` `{feed.get('address', '')}`: `{feed.get('description', '')}`, decimals `{feed.get('decimals')}`."
        )
    if not feed_lines:
        feed_lines = ["- No Chainlink feed description probes were configured for this case."]
    return "\n".join(
        [
            f"# {case['name']} Feed-Binding Materialization",
            "",
            "## Safety scope",
            "",
            "- Scope: read-only historical known-transaction evidence materialization.",
            "- RPC calls are limited to receipt, transaction, and block reads for configured `known_txs`.",
            "- No transaction simulation, private key handling, write method, or open-ended `eth_getLogs` scan is used.",
            "",
            "## Evidence quality",
            "",
            f"- Status: `{materialized['evidence_quality']}`.",
            "- The trigger and actor fields come from historical transactions and receipts.",
            "- Asset/feed identity comes from the incident seed constraint; protocol-specific amounts remain `unknown` unless decoded later.",
            "- Token transfer flow is decoded directly from ERC20 `Transfer` logs in the historical exploit receipt.",
            "",
            "## Raw evidence closure",
            "",
            f"- Config receipt logs: `{config['log_count']}` from historical RPC.",
            f"- Exploit receipt logs: `{exploit['log_count']}` from historical RPC.",
            f"- Config tx sender/target/block: `{config['from']}` -> `{config['to']}` at block `{config['block_number']}`.",
            f"- Exploit tx sender/target/block: `{exploit['from']}` -> `{exploit['to']}` at block `{exploit['block_number']}`.",
            f"- Remediation boundary tx count: `{len(materialized.get('boundary_logs') or [])}`.",
            f"- Raw evidence snapshot: `{raw_path}`.",
            "- Snapshot contains receipt, transaction, and block payloads only; no API keys or RPC URLs are written.",
            "",
            "## Trigger",
            "",
            f"- Config tx: `{config['hash']}`",
            f"- Actor: `{config['from']}`",
            f"- Oracle/config contract: `{config['to']}`",
            f"- Block: `{config['block_number']}` at `{config['block_time']}`",
            f"- Constraint: `{constraint['asset']}` expected `{constraint.get('expected_feed')}`, observed incident feed `{constraint.get('forbidden_feed')}`",
            "",
            "## Feed identity verification",
            "",
            *feed_lines,
            "",
            "## Impact",
            "",
            f"- Exploit tx: `{exploit['hash']}`",
            f"- Attacker candidate: `{exploit['from']}`",
            f"- Protocol target: `{exploit['to']}`",
            f"- Block: `{exploit['block_number']}` at `{exploit['block_time']}`",
            f"- Raw log addresses observed: `{len(exploit['raw_log_addresses'])}`",
            "",
            "## Token transfer flow",
            "",
            *flow_lines,
            "",
            "## Remediation boundary",
            "",
            *boundary_lines,
            "",
            "## Artifacts",
            "",
            f"- Trace: `{trace_path}`",
            f"- Materialized evidence: `{evidence_path}`",
            f"- Raw evidence: `{raw_path}`",
            "",
        ]
    )


def materialize(
    case_id: str,
    allow_rpc_fill: bool = False,
    offline: bool = False,
    max_rpc_requests: int = 10,
    max_abi_requests: int = 20,
) -> Dict[str, Path]:
    case = get_case(case_id)
    if case_id not in SUPPORTED_CASES:
        raise PipelineError("Only active feed-binding case ploutos is a materializer target.")
    evidence_path = repo_path("artifacts", "feed_binding_locator", f"{case_id}_evidence.json")
    raw_evidence_path = repo_path("artifacts", "feed_binding_locator", f"{case_id}_raw_evidence.json")
    trace_path = repo_path("artifacts", "log_trace", f"{case_id}.jsonl")
    report_path = repo_path("results", f"{case_id}_locator.md")

    if offline:
        if not evidence_path.exists():
            raise PipelineError(f"Offline mode requires existing materialized evidence: {evidence_path}")
        materialized = json.loads(evidence_path.read_text(encoding="utf-8"))
    elif allow_rpc_fill:
        collected = collect_remote_materialized(case_id, max_rpc_requests, max_abi_requests)
        materialized = collected["materialized"]
        write_json(evidence_path, materialized)
        write_json(raw_evidence_path, collected["raw_evidence"])
    else:
        raise PipelineError("Remote materialization is explicit: pass --allow-rpc-fill, or --offline with existing evidence.")

    records = build_trace_records(case, materialized)
    write_jsonl(trace_path, records)
    ensure_dir(report_path.parent)
    report_path.write_text(render_report(case, materialized, trace_path, evidence_path, raw_evidence_path), encoding="utf-8")
    return {"trace": trace_path, "evidence": evidence_path, "raw_evidence": raw_evidence_path, "report": report_path}


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize Ploutos/Rho feed-binding evidence from known historical transactions.")
    parser.add_argument("--case", required=True, choices=sorted(SUPPORTED_CASES))
    parser.add_argument("--offline", action="store_true", help="Use existing feed-binding locator evidence; do not call RPC/API.")
    parser.add_argument("--allow-rpc-fill", action="store_true", help="Allow bounded read-only RPC/API calls for known transaction evidence.")
    parser.add_argument("--max-rpc-requests", type=int, default=10)
    parser.add_argument("--max-abi-requests", type=int, default=20)
    args = parser.parse_args()

    try:
        outputs = materialize(
            case_id=args.case,
            allow_rpc_fill=args.allow_rpc_fill,
            offline=args.offline,
            max_rpc_requests=args.max_rpc_requests,
            max_abi_requests=args.max_abi_requests,
        )
    except PipelineError as exc:
        raise SystemExit(str(exc)) from exc

    print("Wrote feed-binding materialized artifacts:")
    for key, path in outputs.items():
        print(f"- {key}: {path}")


if __name__ == "__main__":
    main()
