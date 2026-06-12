#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from common import (
    PipelineError,
    ensure_dir,
    get_case,
    load_env,
    read_json,
    read_jsonl,
    repo_path,
    resolve_template,
    rpc_call,
    write_json,
    write_jsonl,
)
from locate_blizz_luna import ANSWER_UPDATED_TOPIC, VENUS_HISTORY_DIR, VENUS_LUNA_FEED, _norm_addr


CASE_ORDER = [
    "ploutos",
    "moonwell_cbeth",
    "moonwell_wrseth",
    "blueberry_faulty_oracle",
    "venus_luna",
    "blizz_luna",
]

MOONWELL_CBETH_TRIGGER_TX = "0xd26baf29dcba7bf66db4be17b46a49bb4dacca41ace968c98c8a5b09a03ae812"
MOONWELL_WRSETH_FIRST_ATTACK_TX = "0x229caeb87e0b6c31afad950150d2ba05a8d7fe823c9e5c05af63b4150b8f6cc6"
MOONWELL_WRSETH_ORACLES = [
    "0xd7221b10fbbc1e1ba95fd0b4d031c15f7f365296",
    "0x71041dddad3595f9ced3dccfbe3d1f4b0a16bb70",
]
MOONWELL_WRSETH_MALFUNCTION_TIME = "2025-11-04T05:44:55Z"
BLUEBERRY_ATTACK_TX = "0xf0464b01d962f714eee9d4392b2494524d0e10ce3eb3723873afd1346b8b06e4"
BLUEBERRY_BORROWING_ENABLED_TIME = "2024-02-22T08:36:00Z"
BLUEBERRY_CONFIG_SCAN_START_TIME = "2024-02-22T08:15:00Z"
BLUEBERRY_SCAN_ADDRESSES = [
    "0xffadb0bba4379dfabfb20ca6823f6ec439429ec2",
    "0xdfe469ace05c3d0d4461439e6cf5d0f46f33ec56",
    "0x770d3e22703210c09a573c2043081d97286f415e",
    "0xc5cea3f9c92291335076d4c2ec6ae72e45fb8937",
    "0x5818562baac907b859e27813e8c0962d416dab59",
    "0x9a72298ae3886221820b1c878d12d872087d3a23",
    "0x5f4ec3df9cbd43714fe2740f5e3616155c5b8419",
    "0x8fffffd4afb6115b954bd326cbe7b4ba576818f6",
    "0xcb0d9ff5bdd34521c6f8cdbeaf15e1a76fa4dd5d",
    "0x327e45b3444cca9ce1559780cfd44181a175e83c",
    "0xd94b367b222f72434c70ad36b6a36944561fa5f4",
    "0x16d43cac32329ec286dc14431e0c0e805e6f5174",
    "0xc29c188e81a0dede959beeb1db181c121f19476d",
    "0xfb8ddd624e340204f32905692c3fd7da59335e81",
    "0xb5a7d8c7f85bb48fcf10ad5c3efb090a3fe40069",
    "0x045cb2ffea4c2cef4e9a754bd02bd6bb9e0df841",
    "0x643d448cea0d3616f0b32e3718f563b164e7edd2",
]
BLUEBERRY_OPERATIONAL_TOPICS = {
    # ERC-20 / Compound-style market activity logs. These can prove activity
    # before the attack, but they are not oracle/config/pause boundary logs.
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
    "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925",
    "0x4dec04e750ca11537cabcd8a9eab06494de08da3735bc8871cd41250e190bc04",
    "0x4c209b5fc8ad50758f13e2e1088ba56a560dff690a1c6fef26394f4c03821c4f",
    "0xe5b754fb1abb7f01b499791d0b820ae3b6af3424ac1c59768edb53f4ec31a929",
    "0x13ed6866d4e1ee6da46d93fd5c39f316dcb8e4999089e77a34724186f128fdd8",
    "0x1a2a22cb7b85ad2a3f8b8e17113e6a22dc0f7d0c3f8768516e79f6d7cd5b6fbb",
    "0x298637f684da9d3d7e4da85e347459b7524f659af40f09a7a1d3e2c4c8c4e8a5",
}


@dataclass
class RequestBudget:
    max_rpc: int
    rpc_used: int = 0

    def use_rpc(self) -> None:
        if self.rpc_used + 1 > self.max_rpc:
            raise PipelineError(f"RPC request budget exceeded: {self.rpc_used + 1}>{self.max_rpc}")
        self.rpc_used += 1


class RpcReader:
    def __init__(self, case_id: str, max_rpc_requests: int):
        self.case_id = case_id
        self.rpc_url = resolve_template(get_case(case_id)["rpc_url_template"], load_env())
        self.budget = RequestBudget(max_rpc=max_rpc_requests)
        self.receipts: Dict[str, Dict[str, Any]] = {}
        self.transactions: Dict[str, Dict[str, Any]] = {}
        self.blocks: Dict[int, Dict[str, Any]] = {}

    def call(self, method: str, params: List[Any], attempts: int = 3) -> Any:
        last_error: Optional[Exception] = None
        for attempt in range(attempts):
            self.budget.use_rpc()
            try:
                return rpc_call(self.rpc_url, method, params, timeout=60)
            except Exception as exc:  # pragma: no cover - provider failures vary
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(1)
        raise PipelineError(f"Read-only RPC request failed for {self.case_id} {method}: {last_error}") from last_error

    def receipt(self, tx_hash: str) -> Dict[str, Any]:
        tx_hash = _norm_hash(tx_hash)
        if tx_hash not in self.receipts:
            receipt = self.call("eth_getTransactionReceipt", [tx_hash])
            if not receipt:
                raise PipelineError(f"No receipt returned for {self.case_id} tx {tx_hash}")
            self.receipts[tx_hash] = receipt
        return self.receipts[tx_hash]

    def transaction(self, tx_hash: str) -> Dict[str, Any]:
        tx_hash = _norm_hash(tx_hash)
        if tx_hash not in self.transactions:
            tx = self.call("eth_getTransactionByHash", [tx_hash])
            if not tx:
                raise PipelineError(f"No transaction returned for {self.case_id} tx {tx_hash}")
            self.transactions[tx_hash] = tx
        return self.transactions[tx_hash]

    def block(self, block_number: int) -> Dict[str, Any]:
        if block_number not in self.blocks:
            block = self.call("eth_getBlockByNumber", [hex(block_number), False])
            if not block:
                raise PipelineError(f"No block returned for {self.case_id} block {block_number}")
            self.blocks[block_number] = block
        return self.blocks[block_number]

    def bundle(self, tx_hash: str) -> Dict[str, Any]:
        receipt = self.receipt(tx_hash)
        block_number = _hex_to_int(receipt.get("blockNumber"))
        return {
            "receipt": receipt,
            "transaction": self.transaction(tx_hash),
            "block": self.block(block_number),
        }

    def block_by_timestamp(self, target_timestamp: int) -> int:
        latest = _hex_to_int(self.call("eth_blockNumber", []))
        low, high = 0, latest
        while low < high:
            mid = (low + high) // 2
            block = self.block(mid)
            if _hex_to_int(block.get("timestamp")) < target_timestamp:
                low = mid + 1
            else:
                high = mid
        return low

    def logs(
        self,
        *,
        addresses: Sequence[str],
        from_block: int,
        to_block: int,
        topics: Optional[List[Any]] = None,
        step: int = 1000,
    ) -> List[Dict[str, Any]]:
        found: List[Dict[str, Any]] = []
        current = from_block
        while current <= to_block:
            end = min(current + step - 1, to_block)
            params: Dict[str, Any] = {
                "fromBlock": hex(current),
                "toBlock": hex(end),
            }
            if addresses:
                params["address"] = [_norm_addr(address) for address in addresses]
            if topics:
                params["topics"] = topics
            found.extend(self.call("eth_getLogs", [params]) or [])
            current = end + 1
        return found


def _hex_to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, int):
        return value
    text = str(value)
    return int(text, 16) if text.startswith("0x") else int(text)


def _norm_hash(value: str) -> str:
    return (value or "").lower()


def _parse_time(value: str) -> datetime:
    clean = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(clean).astimezone(timezone.utc)


def _iso_from_timestamp(value: int) -> str:
    return datetime.fromtimestamp(value, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _block_time(block: Dict[str, Any]) -> str:
    timestamp = _hex_to_int(block.get("timestamp"))
    return _iso_from_timestamp(timestamp) if timestamp else ""


def _tx_position_from_receipt(receipt: Dict[str, Any]) -> Tuple[int, int]:
    return (_hex_to_int(receipt.get("blockNumber")), _hex_to_int(receipt.get("transactionIndex")))


def _log_position(log: Dict[str, Any]) -> Tuple[int, int, int]:
    return (
        _hex_to_int(log.get("blockNumber")),
        _hex_to_int(log.get("transactionIndex")),
        _hex_to_int(log.get("logIndex")),
    )


def _topics(log: Dict[str, Any]) -> List[str]:
    return [str(topic).lower() for topic in (log.get("topics") or [])]


def _pre_attack_path(case_id: str) -> Path:
    return repo_path("artifacts", "incident_tables", case_id, "pre_attack_logs.jsonl")


def _scan_path(case_id: str) -> Path:
    return repo_path("artifacts", "pre_attack_log_scans", f"{case_id}.json")


def _existing_rows(case_id: str) -> List[Dict[str, Any]]:
    path = _pre_attack_path(case_id)
    return read_jsonl(path) if path.exists() else []


def _existing_scan(case_id: str) -> Dict[str, Any]:
    return _load_json_if_exists(_scan_path(case_id))


def _write_case(case_id: str, rows: List[Dict[str, Any]], scan: Dict[str, Any]) -> None:
    rows = sorted(rows, key=lambda row: (int(row.get("block_number") or 0), int(row.get("transaction_index") or 0), int(row.get("log_index") or 0)))
    write_jsonl(_pre_attack_path(case_id), rows)
    write_json(_scan_path(case_id), scan)


def _row_from_log(
    *,
    case_id: str,
    boundary_type: str,
    log: Dict[str, Any],
    block_time: str,
    receipt_status: Optional[int],
    evidence_source: str,
    decoded_hint: str,
    is_primary_boundary_log: bool,
) -> Dict[str, Any]:
    topics = _topics(log)
    return {
        "case": case_id,
        "boundary_type": boundary_type,
        "tx_hash": _norm_hash(log.get("transactionHash") or ""),
        "block_number": _hex_to_int(log.get("blockNumber")),
        "block_time": block_time,
        "transaction_index": _hex_to_int(log.get("transactionIndex")),
        "log_index": _hex_to_int(log.get("logIndex")),
        "address": _norm_addr(log.get("address", "")),
        "topic0": topics[0] if topics else "",
        "topics": topics,
        "data": (log.get("data") or "").lower(),
        "receipt_status": receipt_status,
        "evidence_source": evidence_source,
        "decoded_hint": decoded_hint,
        "is_primary_boundary_log": bool(is_primary_boundary_log),
    }


def _rows_from_receipt_bundle(
    *,
    case_id: str,
    boundary_type: str,
    bundle: Dict[str, Any],
    evidence_source: str,
    decoded_hint_for_log: Callable[[Dict[str, Any]], str],
    primary_predicate: Callable[[Dict[str, Any]], bool],
) -> List[Dict[str, Any]]:
    receipt = bundle.get("receipt") or {}
    block = bundle.get("block") or {}
    status = _hex_to_int(receipt.get("status")) if receipt.get("status") is not None else None
    block_time = _block_time(block)
    rows = []
    for log in receipt.get("logs") or []:
        rows.append(
            _row_from_log(
                case_id=case_id,
                boundary_type=boundary_type,
                log=log,
                block_time=block_time,
                receipt_status=status,
                evidence_source=evidence_source,
                decoded_hint=decoded_hint_for_log(log),
                is_primary_boundary_log=primary_predicate(log),
            )
        )
    return rows


def _rows_from_rpc_tx(
    reader: RpcReader,
    *,
    case_id: str,
    tx_hash: str,
    boundary_type: str,
    evidence_source: str,
    decoded_hint_for_log: Callable[[Dict[str, Any]], str],
    primary_predicate: Callable[[Dict[str, Any]], bool],
) -> List[Dict[str, Any]]:
    return _rows_from_receipt_bundle(
        case_id=case_id,
        boundary_type=boundary_type,
        bundle=reader.bundle(tx_hash),
        evidence_source=evidence_source,
        decoded_hint_for_log=decoded_hint_for_log,
        primary_predicate=primary_predicate,
    )


def _load_json_if_exists(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return read_json(path)


def _raw_bundle(raw_evidence: Dict[str, Any], key_or_tx: str, role: Optional[str] = None) -> Dict[str, Any]:
    txs = raw_evidence.get("transactions") or {}
    if key_or_tx in txs:
        return txs[key_or_tx] or {}
    lowered = _norm_hash(key_or_tx)
    if lowered in txs:
        return txs[lowered] or {}
    if role:
        for item in txs.values():
            if isinstance(item, dict) and item.get("role") == role:
                return item
    return {}


def _materialize_ploutos() -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    raw = _load_json_if_exists(repo_path("artifacts", "feed_binding_locator", "ploutos_raw_evidence.json"))
    bundle = _raw_bundle(raw, "config")
    rows = _rows_from_receipt_bundle(
        case_id="ploutos",
        boundary_type="ORACLE_FEED_SET",
        bundle=bundle,
        evidence_source="existing_rpc_raw_evidence",
        decoded_hint_for_log=lambda log: "oracle feed mapping changed before exploit",
        primary_predicate=lambda log: True,
    ) if bundle else []
    return rows, {
        "case": "ploutos",
        "mode": "offline_existing_raw_evidence",
        "source": "artifacts/feed_binding_locator/ploutos_raw_evidence.json",
        "pre_attack_log_count": len(rows),
        "missing_pre_attack_receipt_reason": "" if rows else "missing ploutos config raw evidence",
    }


def _materialize_moonwell_cbeth() -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    raw = _load_json_if_exists(repo_path("artifacts", "moonwell_cbeth_locator", "raw_evidence.json"))
    bundle = _raw_bundle(raw, MOONWELL_CBETH_TRIGGER_TX, role="oracle_trigger")
    rows = _rows_from_receipt_bundle(
        case_id="moonwell_cbeth",
        boundary_type="ORACLE_FORMULA_SET",
        bundle=bundle,
        evidence_source="existing_rpc_raw_evidence",
        decoded_hint_for_log=lambda log: "MIP-X43 execution receipt log before cbETH borrow/liquidation impact",
        primary_predicate=lambda log: True,
    ) if bundle else []
    return rows, {
        "case": "moonwell_cbeth",
        "mode": "offline_existing_raw_evidence",
        "source": "artifacts/moonwell_cbeth_locator/raw_evidence.json",
        "pre_attack_log_count": len(rows),
        "missing_pre_attack_receipt_reason": "" if rows else "missing Moonwell cbETH trigger raw evidence",
    }


def _venus_csv_marker_row() -> Optional[Dict[str, Any]]:
    price_path = VENUS_HISTORY_DIR / "price.csv"
    if not price_path.exists():
        return None
    with price_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if _norm_hash(row.get("transaction_hash", "")) == get_case("venus_luna")["known_txs"]["stale_oracle_last_update"].lower():
                return row
    return None


def _row_from_local_csv_marker(case_id: str, boundary_type: str, row: Dict[str, Any], evidence_source: str, decoded_hint: str) -> Dict[str, Any]:
    topics = [str(row.get(key, "")).lower() for key in ("topic0", "topic1", "topic2", "topic3") if row.get(key)]
    block_time = str(row.get("block_timestamp", "")).replace(".000Z", "Z")
    return {
        "case": case_id,
        "boundary_type": boundary_type,
        "tx_hash": _norm_hash(row.get("transaction_hash", "")),
        "block_number": int(row.get("block_number") or 0),
        "block_time": block_time,
        "transaction_index": int(row.get("transaction_index") or 0),
        "log_index": int(row.get("log_index") or 0),
        "address": _norm_addr(row.get("address", "")),
        "topic0": topics[0] if topics else "",
        "topics": topics,
        "data": (row.get("data") or "").lower(),
        "receipt_status": 1,
        "evidence_source": evidence_source,
        "decoded_hint": decoded_hint,
        "is_primary_boundary_log": True,
    }


def _materialize_venus(*, allow_rpc_fill: bool, max_rpc_requests: int, preserve_existing: bool) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    tx_hash = get_case("venus_luna")["known_txs"]["stale_oracle_last_update"]
    if allow_rpc_fill:
        reader = RpcReader("venus_luna", max_rpc_requests)
        rows = _rows_from_rpc_tx(
            reader,
            case_id="venus_luna",
            tx_hash=tx_hash,
            boundary_type="STALE_ORACLE_START",
            evidence_source="rpc_receipt",
            decoded_hint_for_log=lambda log: "Chainlink AnswerUpdated stale marker" if _topics(log)[:1] == [ANSWER_UPDATED_TOPIC] and _norm_addr(log.get("address", "")) == VENUS_LUNA_FEED else "same receipt as stale marker transaction",
            primary_predicate=lambda log: _topics(log)[:1] == [ANSWER_UPDATED_TOPIC] and _norm_addr(log.get("address", "")) == VENUS_LUNA_FEED,
        )
        return rows, {
            "case": "venus_luna",
            "mode": "rpc",
            "tx_hash": tx_hash,
            "rpc_used": reader.budget.rpc_used,
            "pre_attack_log_count": len(rows),
            "missing_pre_attack_receipt_reason": "" if rows else "stale marker receipt contained no logs",
        }
    existing = _existing_rows("venus_luna") if preserve_existing else []
    existing_scan = _existing_scan("venus_luna") if preserve_existing else {}
    if existing_scan.get("mode") == "rpc" and "pre_attack_log_count" in existing_scan:
        return existing, existing_scan
    row = _venus_csv_marker_row()
    rows = [
        _row_from_local_csv_marker(
            "venus_luna",
            "STALE_ORACLE_START",
            row,
            "venus_local_history_csv_log",
            "local historical AnswerUpdated log row for stale marker; run --allow-rpc-fill for full receipt logs",
        )
    ] if row else []
    return rows, {
        "case": "venus_luna",
        "mode": "offline_local_history_csv",
        "source": str(VENUS_HISTORY_DIR / "price.csv"),
        "pre_attack_log_count": len(rows),
        "missing_pre_attack_receipt_reason": "" if rows else "missing Venus stale marker local CSV row",
    }


def _materialize_blizz(*, allow_rpc_fill: bool, max_rpc_requests: int, preserve_existing: bool) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    tx_hash = get_case("blizz_luna")["known_txs"]["stale_oracle_last_update"]
    if allow_rpc_fill:
        reader = RpcReader("blizz_luna", max_rpc_requests)
        feed = ((read_json(repo_path("artifacts", "blizz_luna_locator", "dune_findings.json")).get("identified_contracts") or {}).get("luna_usd_feed_candidate") or {}).get("address", "")
        rows = _rows_from_rpc_tx(
            reader,
            case_id="blizz_luna",
            tx_hash=tx_hash,
            boundary_type="STALE_ORACLE_START",
            evidence_source="rpc_receipt",
            decoded_hint_for_log=lambda log: "Chainlink AnswerUpdated stale marker" if _topics(log)[:1] == [ANSWER_UPDATED_TOPIC] and _norm_addr(log.get("address", "")) == _norm_addr(feed) else "same receipt as stale marker transaction",
            primary_predicate=lambda log: _topics(log)[:1] == [ANSWER_UPDATED_TOPIC] and _norm_addr(log.get("address", "")) == _norm_addr(feed),
        )
        return rows, {
            "case": "blizz_luna",
            "mode": "rpc",
            "tx_hash": tx_hash,
            "rpc_used": reader.budget.rpc_used,
            "pre_attack_log_count": len(rows),
            "missing_pre_attack_receipt_reason": "" if rows else "stale marker receipt contained no logs",
        }
    existing = _existing_rows("blizz_luna") if preserve_existing else []
    existing_scan = _existing_scan("blizz_luna") if preserve_existing else {}
    if existing_scan.get("mode") == "rpc" and "pre_attack_log_count" in existing_scan:
        return existing, existing_scan
    return existing, {
        "case": "blizz_luna",
        "mode": "offline_preserve_existing" if existing else "offline_missing_rpc_receipt",
        "tx_hash": tx_hash,
        "pre_attack_log_count": len(existing),
        "missing_pre_attack_receipt_reason": "" if existing else "Blizz stale marker receipt/log topics are not present in local artifacts; run materialize_pre_attack_logs.py --case blizz_luna --allow-rpc-fill",
    }


def _rows_from_scanned_logs(
    reader: RpcReader,
    *,
    case_id: str,
    boundary_type: str,
    logs: List[Dict[str, Any]],
    before_position: Tuple[int, int],
    evidence_source: str,
    decoded_hint: str,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    tx_status: Dict[str, Optional[int]] = {}
    block_times: Dict[int, str] = {}
    for log in logs:
        block_number, tx_index, _ = _log_position(log)
        if (block_number, tx_index) >= before_position:
            continue
        tx_hash = _norm_hash(log.get("transactionHash") or "")
        if tx_hash not in tx_status:
            receipt = reader.receipt(tx_hash)
            tx_status[tx_hash] = _hex_to_int(receipt.get("status")) if receipt.get("status") is not None else None
        if block_number not in block_times:
            block_times[block_number] = _block_time(reader.block(block_number))
        rows.append(
            _row_from_log(
                case_id=case_id,
                boundary_type=boundary_type,
                log=log,
                block_time=block_times[block_number],
                receipt_status=tx_status[tx_hash],
                evidence_source=evidence_source,
                decoded_hint=decoded_hint,
                is_primary_boundary_log=True,
            )
        )
    return rows


def _materialize_moonwell_wrseth(*, allow_rpc_fill: bool, max_rpc_requests: int, preserve_existing: bool) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not allow_rpc_fill:
        existing = _existing_rows("moonwell_wrseth") if preserve_existing else []
        existing_scan = _existing_scan("moonwell_wrseth") if preserve_existing else {}
        if existing_scan.get("mode") == "rpc_scan" and "pre_attack_log_count" in existing_scan:
            return existing, existing_scan
        return existing, {
            "case": "moonwell_wrseth",
            "mode": "offline_preserve_existing" if existing else "offline_no_receipt_backed_marker",
            "seed_time": "2025-11-04T05:44:55Z",
            "seed_addresses": MOONWELL_WRSETH_ORACLES,
            "pre_attack_log_count": len(existing),
            "missing_pre_attack_receipt_reason": "" if existing else "forum gives malfunction time and feed, but no receipt-backed malfunction tx is present in local artifacts",
        }
    reader = RpcReader("moonwell_wrseth", max_rpc_requests)
    first_receipt = reader.receipt(MOONWELL_WRSETH_FIRST_ATTACK_TX)
    attack_block, attack_tx_index = _tx_position_from_receipt(first_receipt)
    target_block = reader.block_by_timestamp(int(_parse_time(MOONWELL_WRSETH_MALFUNCTION_TIME).timestamp()))
    aggregator = ""
    raw_aggregator = reader.call("eth_call", [{"to": _norm_addr(MOONWELL_WRSETH_ORACLES[0]), "data": "0x245a7bfc"}, hex(max(target_block, attack_block - 1))])
    if isinstance(raw_aggregator, str) and raw_aggregator.startswith("0x") and len(raw_aggregator) >= 66:
        aggregator = _norm_addr("0x" + raw_aggregator[-40:])
    scan_addresses = list(MOONWELL_WRSETH_ORACLES)
    if aggregator:
        scan_addresses.append(aggregator)
    from_block = max(0, target_block - 20)
    logs = reader.logs(addresses=scan_addresses, from_block=from_block, to_block=attack_block - 1)
    qualifying = [
        log for log in logs
        if _norm_addr(log.get("address", "")) == aggregator
        and (_topics(log)[:1] or [""])[0]
        in {
            ANSWER_UPDATED_TOPIC,
            "0xf6a97944f31ea060dfde0566e4167c1a1082551e64b60ecb14d599a9d023d451",
            "0x0109fc6f55cf40689f02fbaad7af7fe7bbac8a3d2186600afc7d3e10cac60271",
        }
    ]
    latest_tx = ""
    if qualifying:
        latest = max(qualifying, key=lambda log: (_hex_to_int(log.get("blockNumber")), _hex_to_int(log.get("transactionIndex")), _hex_to_int(log.get("logIndex"))))
        latest_tx = _norm_hash(latest.get("transactionHash", ""))
    rows = []
    if latest_tx:
        rows = _rows_from_rpc_tx(
            reader,
            case_id="moonwell_wrseth",
            tx_hash=latest_tx,
            boundary_type="ORACLE_PRICE_MALFUNCTION_START",
            evidence_source="rpc_receipt_aggregator_log",
            decoded_hint_for_log=lambda log: "wrsETH/ETH aggregator update at malfunction time" if _norm_addr(log.get("address", "")) == aggregator else "same receipt as wrsETH/ETH aggregator update",
            primary_predicate=lambda log: _norm_addr(log.get("address", "")) == aggregator and (_topics(log)[:1] or [""])[0] == ANSWER_UPDATED_TOPIC,
        )
    return rows, {
        "case": "moonwell_wrseth",
        "mode": "rpc_scan",
        "seed_time": MOONWELL_WRSETH_MALFUNCTION_TIME,
        "seed_addresses": scan_addresses,
        "wrseth_eth_aggregator": aggregator,
        "from_block": from_block,
        "to_block": attack_block - 1,
        "first_attack_tx": MOONWELL_WRSETH_FIRST_ATTACK_TX,
        "malfunction_log_tx": latest_tx,
        "rpc_used": reader.budget.rpc_used,
        "scanned_log_count": len(logs),
        "pre_attack_log_count": len(rows),
        "missing_pre_attack_receipt_reason": "" if rows else "RPC scan found no wrsETH/ETH feed or aggregator logs before the first attack transaction in the local scan window",
    }


def _materialize_blueberry(*, allow_rpc_fill: bool, max_rpc_requests: int, preserve_existing: bool) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not allow_rpc_fill:
        existing = _existing_rows("blueberry_faulty_oracle") if preserve_existing else []
        existing_scan = _existing_scan("blueberry_faulty_oracle") if preserve_existing else {}
        if existing_scan.get("mode") == "rpc_scan" and "pre_attack_log_count" in existing_scan:
            return existing, existing_scan
        return existing, {
            "case": "blueberry_faulty_oracle",
            "mode": "offline_preserve_existing" if existing else "offline_no_receipt_backed_marker",
            "seed_time": BLUEBERRY_BORROWING_ENABLED_TIME,
            "seed_addresses": BLUEBERRY_SCAN_ADDRESSES,
            "pre_attack_log_count": len(existing),
            "missing_pre_attack_receipt_reason": "" if existing else "post-mortem gives borrowing-enabled/oracle-mismatch time, but no receipt-backed config tx is present in local artifacts",
        }
    reader = RpcReader("blueberry_faulty_oracle", max_rpc_requests)
    attack_receipt = reader.receipt(BLUEBERRY_ATTACK_TX)
    attack_block, attack_tx_index = _tx_position_from_receipt(attack_receipt)
    from_block = reader.block_by_timestamp(int(_parse_time(BLUEBERRY_CONFIG_SCAN_START_TIME).timestamp()))
    logs = reader.logs(addresses=sorted(set(BLUEBERRY_SCAN_ADDRESSES)), from_block=from_block, to_block=attack_block)
    config_logs = [log for log in logs if (_topics(log)[:1] or [""])[0] not in BLUEBERRY_OPERATIONAL_TOPICS]
    rows = _rows_from_scanned_logs(
        reader,
        case_id="blueberry_faulty_oracle",
        boundary_type="FAULTY_ORACLE_DEPLOYMENT_ACTIVE",
        logs=config_logs,
        before_position=(attack_block, attack_tx_index),
        evidence_source="rpc_log_scan",
        decoded_hint="Blueberry money-market/oracle/admin log before canonical attack transaction",
    )
    return rows, {
        "case": "blueberry_faulty_oracle",
        "mode": "rpc_scan",
        "seed_time": BLUEBERRY_BORROWING_ENABLED_TIME,
        "config_scan_start_time": BLUEBERRY_CONFIG_SCAN_START_TIME,
        "seed_addresses": BLUEBERRY_SCAN_ADDRESSES,
        "from_block": from_block,
        "to_block": attack_block,
        "first_attack_tx": BLUEBERRY_ATTACK_TX,
        "rpc_used": reader.budget.rpc_used,
        "scanned_log_count": len(logs),
        "candidate_config_log_count": len(config_logs),
        "pre_attack_log_count": len(rows),
        "missing_pre_attack_receipt_reason": "" if rows else "RPC scan found no Blueberry admin/config/pause/oracle logs before the canonical attack transaction after filtering normal market activity logs",
    }


def materialize_case(
    case_id: str,
    *,
    allow_rpc_fill: bool,
    max_rpc_requests: int,
    preserve_existing: bool = True,
) -> Dict[str, Any]:
    if case_id == "ploutos":
        rows, scan = _materialize_ploutos()
    elif case_id == "moonwell_cbeth":
        rows, scan = _materialize_moonwell_cbeth()
    elif case_id == "venus_luna":
        rows, scan = _materialize_venus(allow_rpc_fill=allow_rpc_fill, max_rpc_requests=max_rpc_requests, preserve_existing=preserve_existing)
    elif case_id == "blizz_luna":
        rows, scan = _materialize_blizz(allow_rpc_fill=allow_rpc_fill, max_rpc_requests=max_rpc_requests, preserve_existing=preserve_existing)
    elif case_id == "moonwell_wrseth":
        rows, scan = _materialize_moonwell_wrseth(allow_rpc_fill=allow_rpc_fill, max_rpc_requests=max_rpc_requests, preserve_existing=preserve_existing)
    elif case_id == "blueberry_faulty_oracle":
        rows, scan = _materialize_blueberry(allow_rpc_fill=allow_rpc_fill, max_rpc_requests=max_rpc_requests, preserve_existing=preserve_existing)
    else:
        raise PipelineError(f"Unsupported case for pre-attack logs: {case_id}")
    _write_case(case_id, rows, scan)
    return scan


def materialize_cases(
    case_ids: Iterable[str],
    *,
    allow_rpc_fill: bool,
    max_rpc_requests: int,
    preserve_existing: bool = True,
) -> Dict[str, Dict[str, Any]]:
    return {
        case_id: materialize_case(
            case_id,
            allow_rpc_fill=allow_rpc_fill,
            max_rpc_requests=max_rpc_requests,
            preserve_existing=preserve_existing,
        )
        for case_id in case_ids
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize pre-attack receipt/log topic evidence tables.")
    parser.add_argument("--case", choices=["all"] + CASE_ORDER, default="all")
    parser.add_argument("--offline", action="store_true", help="Do not perform RPC scans; preserve existing RPC rows where no offline raw evidence exists.")
    parser.add_argument("--allow-rpc-fill", action="store_true", help="Fetch known receipts or bounded log scans through configured RPC endpoints.")
    parser.add_argument("--max-rpc-requests", type=int, default=120)
    args = parser.parse_args()
    if args.offline and args.allow_rpc_fill:
        raise SystemExit("--offline and --allow-rpc-fill are mutually exclusive.")
    case_ids = CASE_ORDER if args.case == "all" else [args.case]
    scans = materialize_cases(
        case_ids,
        allow_rpc_fill=args.allow_rpc_fill and not args.offline,
        max_rpc_requests=args.max_rpc_requests,
        preserve_existing=True,
    )
    print("Wrote pre-attack log topic artifacts:")
    for case_id in case_ids:
        scan = scans[case_id]
        print(f"- {case_id}: rows={scan.get('pre_attack_log_count', 0)} path={_pre_attack_path(case_id)}")


if __name__ == "__main__":
    main()
