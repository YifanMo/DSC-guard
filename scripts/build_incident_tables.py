#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

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
from materialize_venus_luna import (
    DEFAULT_VENUS_END,
    VENUS_LUNA_FEED,
    VENUS_VBUSD,
    VENUS_VLUNA,
    RpcFiller as VenusRpcFiller,
    _collect_borrows as _venus_collect_borrows,
    _collect_deposits as _venus_collect_deposits,
    _load_oracle_marker as _venus_load_oracle_marker,
    _parse_time as _venus_parse_time,
)
from materialize_pre_attack_logs import CASE_ORDER as PRE_ATTACK_CASE_ORDER, materialize_cases as materialize_pre_attack_cases


MOONWELL_FULL_EVENTS_EXECUTION_ID = "01KRBRE66A6Q52SWYMC1MZ3CNX"
MOONWELL_FULL_EVENTS_QUERY_ID = 7472449
MOONWELL_TRIGGER = {
    "event_type": "ORACLE_FORMULA_SET",
    "tx_hash": "0xd26baf29dcba7bf66db4be17b46a49bb4dacca41ace968c98c8a5b09a03ae812",
    "block_number": 42194663,
    "block_time": "2026-02-15T18:04:33Z",
    "actor": "0xaf3642bac06cda85340ecf18d40b8bf89958b69e",
    "target": "0xec942be8a8114bfd0396a5052c36027f2ca6a9d0",
    "reason": "MIP-X43 executed ChainlinkOracle setFeed(string,address) with cbETH/ETH instead of cbETH/ETH * ETH/USD.",
}
MOONWELL_PUBLIC_METRICS = {
    "public_seized_cbeth": "1096.317",
    "public_bad_debt_usd": "1780000",
    "public_affected_borrowers": 181,
}
BLIZZ_NATURAL_START = "2022-05-12T11:39:06Z"
BLIZZ_STALE_TX = "0x6b5f6f5b620489aa6616c7e0b4fdd9df712ef47fbd9ba9acf9dedb8cd2207473"
VENUS_DEFAULT_END = DEFAULT_VENUS_END


def _norm_hash(value: str) -> str:
    return (value or "").lower()


def _norm_addr(value: str) -> str:
    value = (value or "").lower()
    if not value:
        return ""
    if not value.startswith("0x"):
        value = f"0x{value}"
    return "0x" + value[2:].rjust(40, "0")[-40:]


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


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _iso_from_unix(value: int) -> str:
    return _iso(datetime.fromtimestamp(value, timezone.utc))


def _decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal(0)
    return Decimal(str(value))


def _decimal_text(value: Decimal, places: Optional[int] = None) -> str:
    if places is not None:
        value = value.quantize(Decimal(10) ** -places)
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _rows_to_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    write_jsonl(path, rows)


def _load_jsonl_if_exists(path: Path) -> List[Dict[str, Any]]:
    return read_jsonl(path) if path.exists() else []


def _local_event_time(event: Dict[str, Any]) -> str:
    timestamp = event.get("block_timestamp")
    return _iso_from_unix(int(timestamp)) if timestamp not in (None, "") else ""


def _local_event_sort_key(event: Dict[str, Any]) -> Tuple[int, int, int]:
    return (
        int(event.get("block_number") or 0),
        int(event.get("transaction_index") or 0),
        int(event.get("log_index") or 0),
    )


def _dune_key() -> str:
    env = load_env()
    key = env.get("DUNE_MCP_KEY") or env.get("DUNE_CLI_KEY")
    if not key:
        raise PipelineError("DUNE_MCP_KEY or DUNE_CLI_KEY is required to refresh Dune execution results.")
    return key


def fetch_dune_execution_rows(execution_id: str, limit: int = 32000) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    key = _dune_key()
    rows: List[Dict[str, Any]] = []
    offset = 0
    metadata: Dict[str, Any] = {}
    while True:
        query = urllib.parse.urlencode({"limit": limit, "offset": offset})
        url = f"https://api.dune.com/api/v1/execution/{execution_id}/results?{query}"
        request = urllib.request.Request(url, headers={"X-Dune-Api-Key": key})
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("state") not in {"QUERY_STATE_COMPLETED", "COMPLETED"}:
            raise PipelineError(f"Dune execution {execution_id} is not completed: {payload.get('state')}")
        result = payload.get("result") or {}
        metadata = result.get("metadata") or metadata
        page = result.get("rows") or []
        rows.extend(page)
        next_offset = payload.get("next_offset")
        if next_offset in (None, offset) or not page:
            break
        offset = int(next_offset)
    return rows, metadata


def _tx_status_path(case_id: str) -> Path:
    return repo_path("artifacts", "incident_tables", case_id, "receipt_status.json")


def _read_statuses(case_id: str) -> Dict[str, Dict[str, Any]]:
    path = _tx_status_path(case_id)
    return read_json(path) if path.exists() else {}


def refresh_receipt_status(case_id: str, tx_hashes: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    case = get_case(case_id)
    rpc_url = resolve_template(case["rpc_url_template"], load_env())
    statuses = _read_statuses(case_id)
    block_cache: Dict[str, Dict[str, Any]] = {}
    for tx_hash in sorted({_norm_hash(item) for item in tx_hashes if item}):
        if tx_hash in statuses:
            continue
        receipt = None
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                receipt = rpc_call(rpc_url, "eth_getTransactionReceipt", [tx_hash], timeout=60)
                break
            except Exception as exc:  # pragma: no cover - provider failures vary
                last_error = exc
                time.sleep(attempt + 1)
        if not receipt:
            statuses[tx_hash] = {"tx_hash": tx_hash, "receipt_found": False, "error": str(last_error or "empty_receipt")}
            continue
        block_number_hex = receipt.get("blockNumber")
        if block_number_hex not in block_cache:
            block_cache[block_number_hex] = rpc_call(rpc_url, "eth_getBlockByNumber", [block_number_hex, False], timeout=60)
        block = block_cache[block_number_hex]
        timestamp = int(block["timestamp"], 16)
        statuses[tx_hash] = {
            "tx_hash": tx_hash,
            "receipt_found": True,
            "status": int(receipt.get("status", "0x0"), 16),
            "block_number": int(block_number_hex, 16),
            "block_timestamp": timestamp,
            "block_time": _iso_from_unix(timestamp),
            "transaction_index": int(receipt.get("transactionIndex", "0x0"), 16),
            "log_count": len(receipt.get("logs") or []),
        }
    write_json(_tx_status_path(case_id), statuses)
    return statuses


def refresh_moonwell_full_events() -> List[Dict[str, Any]]:
    rows, metadata = fetch_dune_execution_rows(MOONWELL_FULL_EVENTS_EXECUTION_ID)
    base = repo_path("artifacts", "moonwell_cbeth_locator")
    _rows_to_jsonl(base / "dune_full_events.jsonl", rows)
    write_json(
        base / "dune_full_events_metadata.json",
        {
            "query_id": MOONWELL_FULL_EVENTS_QUERY_ID,
            "execution_id": MOONWELL_FULL_EVENTS_EXECUTION_ID,
            "row_count": len(rows),
            "metadata": metadata,
            "source": f"https://dune.com/queries/{MOONWELL_FULL_EVENTS_QUERY_ID}",
        },
    )
    return rows


def load_moonwell_full_events() -> List[Dict[str, Any]]:
    path = repo_path("artifacts", "moonwell_cbeth_locator", "dune_full_events.jsonl")
    if path.exists():
        return read_jsonl(path)
    return []


def rebuild_moonwell_candidates(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    liquidations = [row for row in rows if row.get("event_type") == "LIQUIDATE_CBETH_COLLATERAL"]
    borrows = [row for row in rows if row.get("event_type") == "BORROW_CBETH"]

    candidate_rows: List[Dict[str, Any]] = []
    for row in sorted(liquidations, key=lambda item: (_parse_time(item["evt_block_time"]), item.get("evt_tx_index") or 0, item.get("evt_index") or 0)):
        candidate_rows.append(
            {
                "case": "moonwell_cbeth",
                "candidate_type": "liquidator",
                "address": _norm_addr(row.get("actor", "")),
                "representative_tx": _norm_hash(row.get("evt_tx_hash", "")),
                "block_number": int(row.get("evt_block_number") or 0),
                "block_time": row.get("evt_block_time", ""),
                "role": "liquidator",
                "event_type": "LIQUIDATE_CBETH_COLLATERAL",
                "borrower": _norm_addr(row.get("borrower", "")),
                "repay_market": row.get("repay_market", ""),
                "repay_amount_raw": str(row.get("repay_raw", "")),
                "seized_mtoken_raw": str(row.get("seize_mtoken_raw", "")),
            }
        )

    grouped: Dict[str, Dict[str, Any]] = {}
    for row in sorted(borrows, key=lambda item: (_parse_time(item["evt_block_time"]), item.get("evt_tx_index") or 0, item.get("evt_index") or 0)):
        borrower = _norm_addr(row.get("borrower", ""))
        group = grouped.setdefault(
            borrower,
            {
                "case": "moonwell_cbeth",
                "candidate_type": "borrower",
                "address": borrower,
                "representative_tx": _norm_hash(row.get("evt_tx_hash", "")),
                "block_number": int(row.get("evt_block_number") or 0),
                "block_time": row.get("evt_block_time", ""),
                "role": "borrower",
                "event_type": "BORROW_CBETH",
                "borrowed_cbeth": Decimal(0),
                "event_count": 0,
                "tx_hashes": [],
            },
        )
        group["borrowed_cbeth"] += _decimal(row.get("borrow_cbeth"))
        group["event_count"] += 1
        tx_hash = _norm_hash(row.get("evt_tx_hash", ""))
        if tx_hash and tx_hash not in group["tx_hashes"]:
            group["tx_hashes"].append(tx_hash)

    for group in grouped.values():
        group["borrowed_cbeth"] = _decimal_text(group["borrowed_cbeth"])
        group["tx_count"] = len(group["tx_hashes"])
        candidate_rows.append(group)

    write_jsonl(repo_path("artifacts", "moonwell_cbeth_locator", "moonwell_candidates_full.jsonl"), candidate_rows)
    _update_moonwell_findings(rows, candidate_rows)


def _update_moonwell_findings(rows: List[Dict[str, Any]], candidates: List[Dict[str, Any]]) -> None:
    path = repo_path("artifacts", "moonwell_cbeth_locator", "dune_findings.json")
    findings = read_json(path)
    liquidations = [row for row in rows if row.get("event_type") == "LIQUIDATE_CBETH_COLLATERAL"]
    borrows = [row for row in rows if row.get("event_type") == "BORROW_CBETH"]
    liquidation_txs = {_norm_hash(row.get("evt_tx_hash", "")) for row in liquidations}
    borrow_txs = {_norm_hash(row.get("evt_tx_hash", "")) for row in borrows}
    affected_borrowers = {_norm_addr(row.get("borrower", "")) for row in rows}
    liquidators = {_norm_addr(row.get("actor", "")) for row in liquidations}
    total_borrowed = sum((_decimal(row.get("borrow_cbeth")) for row in borrows), Decimal(0))
    findings["summary"] = {
        **(findings.get("summary") or {}),
        "representative_previous_trace_tx_count": 16,
        "full_event_count": len(rows),
        "full_unique_tx_count": len(liquidation_txs | borrow_txs),
        "full_liquidation_event_count": len(liquidations),
        "full_liquidation_tx_count": len(liquidation_txs),
        "full_liquidator_count": len(liquidators),
        "full_affected_borrower_count": len(affected_borrowers),
        "mcbeth_borrow_event_count": len(borrows),
        "mcbeth_borrow_tx_count": len(borrow_txs),
        "mcbeth_borrower_count": len({row.get("borrower") for row in borrows}),
        "total_borrowed_cbeth": _decimal_text(total_borrowed),
        **MOONWELL_PUBLIC_METRICS,
    }
    findings["full_artifacts"] = {
        **(findings.get("full_artifacts") or {}),
        "events_jsonl": "artifacts/moonwell_cbeth_locator/dune_full_events.jsonl",
        "events_metadata_json": "artifacts/moonwell_cbeth_locator/dune_full_events_metadata.json",
        "candidates_jsonl": "artifacts/moonwell_cbeth_locator/moonwell_candidates_full.jsonl",
    }
    findings["completeness"] = {
        "status": "full_dune_event_rescan_materialized",
        "note": "Local candidates now include all Dune decoded cbETH-collateral liquidation events and all mcbETH borrow events from the incident query result.",
        "cap_boundary_status": "not_confirmed_in_local_rpc_scan",
    }
    write_json(path, findings)


def build_venus_tables(refresh_rpc_statuses: bool) -> Dict[str, Any]:
    case_id = "venus_luna"
    findings_path = repo_path("artifacts", "venus_luna_locator", "venus_findings.json")
    findings = read_json(findings_path)
    end_text = ((findings.get("window") or {}).get("end") or VENUS_DEFAULT_END).replace(".000Z", "Z")

    filler = VenusRpcFiller(offline=True, allow_rpc_fill=False, max_requests=0)
    oracle_row, oracle = _venus_load_oracle_marker(filler)
    start_time = _venus_parse_time(oracle["block_timestamp"])
    end_time = _venus_parse_time(end_text)
    deposits = _venus_collect_deposits(start_time, end_time, filler)
    borrows = _venus_collect_borrows(start_time, end_time, filler)

    candidate_rows = read_jsonl(repo_path("artifacts", "venus_luna_locator", "venus_candidates_full.jsonl"))
    candidate_accounts = {_norm_addr(row.get("address", "")) for row in candidate_rows}
    if not candidate_accounts:
        candidate_accounts = {account for account in borrows if account in deposits}

    tx_roles: Dict[str, Dict[str, Any]] = {}
    attacker_events: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for account in sorted(candidate_accounts):
        deposit_entry = deposits.get(account) or {}
        borrow_entry = borrows.get(account) or {}
        for event in deposit_entry.get("events") or []:
            tx_hash = _norm_hash(event.get("tx_hash", ""))
            detail = tx_roles.setdefault(
                tx_hash,
                {
                    "roles": set(),
                    "actors": set(),
                    "assets": set(),
                    "amounts": defaultdict(Decimal),
                    "events": [],
                },
            )
            detail["roles"].add("SUPPLY_LUNA")
            detail["actors"].add(account)
            detail["assets"].add("LUNA")
            detail["amounts"]["LUNA_SUPPLIED"] += _decimal(event.get("amount"))
            detail["events"].append(event)
            attacker_events[account].append(event)
        for event in borrow_entry.get("events") or []:
            tx_hash = _norm_hash(event.get("tx_hash", ""))
            detail = tx_roles.setdefault(
                tx_hash,
                {
                    "roles": set(),
                    "actors": set(),
                    "assets": set(),
                    "amounts": defaultdict(Decimal),
                    "events": [],
                },
            )
            detail["roles"].add("BORROW")
            detail["actors"].add(account)
            detail["assets"].add("BUSD")
            detail["amounts"]["BUSD_BORROWED"] += _decimal(event.get("amount"))
            detail["events"].append(event)
            attacker_events[account].append(event)

    statuses = refresh_receipt_status(case_id, tx_roles) if refresh_rpc_statuses else _read_statuses(case_id)
    attack_txs = []
    for tx_hash, detail in sorted(tx_roles.items(), key=lambda item: min((_local_event_sort_key(event) for event in item[1]["events"]), default=(0, 0, 0))):
        events = sorted(detail["events"], key=_local_event_sort_key)
        first_event = events[0] if events else {}
        status = statuses.get(tx_hash, {})
        attack_txs.append(
            {
                "case": case_id,
                "tx_hash": tx_hash,
                "attack_tier": "lifecycle",
                "tx_role": "+".join(sorted(detail["roles"])),
                "actor": ",".join(sorted(detail["actors"])),
                "asset": ",".join(sorted(detail["assets"])),
                "luna_supplied": _decimal_text(detail["amounts"].get("LUNA_SUPPLIED", Decimal(0))),
                "busd_borrowed": _decimal_text(detail["amounts"].get("BUSD_BORROWED", Decimal(0))),
                "block_number": status.get("block_number", first_event.get("block_number")),
                "block_time": status.get("block_time", _local_event_time(first_event)),
                "transaction_index": status.get("transaction_index", first_event.get("transaction_index")),
                "log_index": min((int(event.get("log_index") or 0) for event in events), default=0),
                "receipt_status": status.get("status"),
                "evidence_source": "venus_local_history_csv_plus_rpc_receipt_status" if status else "venus_local_history_csv",
            }
        )

    attackers = []
    candidates_by_account = {_norm_addr(row.get("address", "")): row for row in candidate_rows}
    for account in sorted(candidate_accounts):
        candidate = candidates_by_account.get(account, {})
        events = sorted(attacker_events.get(account, []), key=_local_event_sort_key)
        deposit_txs = {_norm_hash(event.get("tx_hash", "")) for event in (deposits.get(account, {}).get("events") or [])}
        borrow_txs = {_norm_hash(event.get("tx_hash", "")) for event in (borrows.get(account, {}).get("events") or [])}
        attackers.append(
            {
                "case": case_id,
                "address": account,
                "role": "attacker",
                "luna_deposit_amount": str(candidate.get("luna_deposit_amount", _decimal_text(deposits.get(account, {}).get("amount", Decimal(0))))),
                "borrowed_usd_known": str(candidate.get("borrowed_usd_known", _decimal_text(borrows.get(account, {}).get("amount", Decimal(0))))),
                "deposit_tx_count": len(deposit_txs),
                "borrow_tx_count": len(borrow_txs),
                "lifecycle_tx_count": len(deposit_txs | borrow_txs),
                "first_tx_time": _local_event_time(events[0]) if events else "",
                "last_tx_time": _local_event_time(events[-1]) if events else "",
            }
        )

    last_lifecycle = max((item for item in attack_txs if item.get("block_time")), key=lambda item: item["block_time"], default={})
    last_borrow = max((item for item in attack_txs if item.get("block_time") and "BORROW" in item["tx_role"]), key=lambda item: item["block_time"], default={})
    start_text = _local_event_time({"block_timestamp": int(start_time.timestamp())})
    boundary_logs = [
        {
            "case": case_id,
            "boundary_type": "STALE_ORACLE_START",
            "tx_hash": oracle["tx_hash"],
            "block_number": oracle["block_number"],
            "block_time": start_text,
            "actor": "",
            "target": VENUS_LUNA_FEED,
            "receipt_status": 1,
            "reason": "Last LUNA/USD answer before Venus continued to accept LUNA collateral.",
        },
        {
            "case": case_id,
            "boundary_type": "LAST_CONFIRMED_LIFECYCLE_TX",
            "tx_hash": last_lifecycle.get("tx_hash", ""),
            "block_number": last_lifecycle.get("block_number"),
            "block_time": last_lifecycle.get("block_time", ""),
            "actor": last_lifecycle.get("actor", ""),
            "target": "",
            "receipt_status": last_lifecycle.get("receipt_status"),
            "reason": "Natural end from the latest local lifecycle transaction in the stale window.",
        },
        {
            "case": case_id,
            "boundary_type": "LAST_CONFIRMED_BORROW_TX",
            "tx_hash": last_borrow.get("tx_hash", ""),
            "block_number": last_borrow.get("block_number"),
            "block_time": last_borrow.get("block_time", ""),
            "actor": last_borrow.get("actor", ""),
            "target": VENUS_VBUSD,
            "receipt_status": last_borrow.get("receipt_status"),
            "reason": "Latest local BUSD borrow transaction in the stale window.",
        },
    ]

    summary = {
        "case": case_id,
        "attacker_count": len(attackers),
        "deposit_tx_count": sum(1 for item in attack_txs if "SUPPLY_LUNA" in item["tx_role"]),
        "borrow_tx_count": sum(1 for item in attack_txs if "BORROW" in item["tx_role"]),
        "lifecycle_tx_count": len(attack_txs),
        "natural_window_start": start_text,
        "window_end": end_text,
        "last_lifecycle_time": last_lifecycle.get("block_time", ""),
        "last_lifecycle_tx": last_lifecycle.get("tx_hash", ""),
        "last_borrow_time": last_borrow.get("block_time", ""),
        "last_borrow_tx": last_borrow.get("tx_hash", ""),
        "candidate_source": "local DSC-Guard Venus history CSV, expanded from representative account trace to full lifecycle tx set",
    }
    findings["window"] = {
        **(findings.get("window") or {}),
        "natural_start": start_text,
        "end": end_text,
        "last_confirmed_lifecycle_time": summary["last_lifecycle_time"],
        "last_confirmed_lifecycle_tx": summary["last_lifecycle_tx"],
        "last_confirmed_borrow_time": summary["last_borrow_time"],
        "last_confirmed_borrow_tx": summary["last_borrow_tx"],
    }
    findings["summary"] = {**(findings.get("summary") or {}), **summary}
    write_json(findings_path, findings)
    _write_case_tables(case_id, attackers, attack_txs, boundary_logs, summary)
    _write_venus_trace(attack_txs, boundary_logs)
    return summary


def _write_venus_trace(attack_txs: List[Dict[str, Any]], boundary_logs: List[Dict[str, Any]]) -> None:
    records: List[Dict[str, Any]] = []
    stale = next((item for item in boundary_logs if item.get("boundary_type") == "STALE_ORACLE_START"), None)
    if stale:
        records.append(
            {
                "case": "venus_luna",
                "event_type": "STALE_ORACLE_START",
                "block_number": int(stale.get("block_number") or 0),
                "block_timestamp": int(_parse_time(stale.get("block_time", "")).timestamp()),
                "transaction_index": 0,
                "log_index": 0,
                "tx_hash": stale.get("tx_hash", ""),
                "address": stale.get("target", ""),
                "decoded": {
                    "asset": "LUNA",
                    "feed": stale.get("target", ""),
                    "reason": stale.get("reason", ""),
                    "evidence_quality": "venus_local_history_csv",
                },
            }
        )
    for index, tx in enumerate(attack_txs, start=1):
        role = tx.get("tx_role", "")
        event_type = "BORROW" if "BORROW" in role else "SUPPLY"
        if event_type == "BORROW":
            decoded = {
                "borrower": tx.get("actor", ""),
                "collateral_asset": "LUNA",
                "borrow_asset": "BUSD",
                "borrow_amount": tx.get("busd_borrowed", ""),
                "borrow_amount_usd": tx.get("busd_borrowed", ""),
                "source": "incident_tables_full_lifecycle",
            }
        else:
            decoded = {
                "supplier": tx.get("actor", ""),
                "asset": "LUNA",
                "amount": tx.get("luna_supplied", ""),
                "receiver": VENUS_VLUNA,
                "source": "incident_tables_full_lifecycle",
            }
        decoded["receipt_status"] = tx.get("receipt_status")
        decoded["evidence_quality"] = tx.get("evidence_source")
        records.append(
            {
                "case": "venus_luna",
                "event_type": event_type,
                "block_number": int(tx.get("block_number") or 0),
                "block_timestamp": int(_parse_time(tx.get("block_time", "")).timestamp()) if tx.get("block_time") else 0,
                "transaction_index": int(tx.get("transaction_index") or index),
                "log_index": int(tx.get("log_index") or index),
                "tx_hash": tx.get("tx_hash", ""),
                "address": VENUS_VBUSD if event_type == "BORROW" else VENUS_VLUNA,
                "decoded": decoded,
            }
        )
    write_jsonl(repo_path("artifacts", "log_trace", "venus_luna.jsonl"), records)


def build_blizz_tables(refresh_rpc_statuses: bool) -> Dict[str, Any]:
    case_id = "blizz_luna"
    candidates = read_jsonl(repo_path("artifacts", "blizz_luna_locator", "dune_candidates_full.jsonl"))
    findings_path = repo_path("artifacts", "blizz_luna_locator", "dune_findings.json")
    findings = read_json(findings_path)
    tx_roles: Dict[str, Dict[str, Any]] = {}
    for candidate in candidates:
        attacker = _norm_addr(candidate.get("address", ""))
        for tx_hash in candidate.get("luna_deposit_txs") or []:
            tx_roles.setdefault(_norm_hash(tx_hash), {"roles": set(), "actors": set(), "assets": set()})
            tx_roles[_norm_hash(tx_hash)]["roles"].add("SUPPLY_LUNA")
            tx_roles[_norm_hash(tx_hash)]["actors"].add(attacker)
            tx_roles[_norm_hash(tx_hash)]["assets"].add("LUNA")
        for tx_hash in candidate.get("borrow_txs") or []:
            tx_roles.setdefault(_norm_hash(tx_hash), {"roles": set(), "actors": set(), "assets": set()})
            tx_roles[_norm_hash(tx_hash)]["roles"].add("BORROW")
            tx_roles[_norm_hash(tx_hash)]["actors"].add(attacker)
            for asset in candidate.get("borrowed_assets") or []:
                tx_roles[_norm_hash(tx_hash)]["assets"].add(asset)

    statuses = refresh_receipt_status(case_id, tx_roles) if refresh_rpc_statuses else _read_statuses(case_id)
    attack_txs = []
    for tx_hash, detail in sorted(tx_roles.items(), key=lambda item: statuses.get(item[0], {}).get("block_timestamp", 0)):
        status = statuses.get(tx_hash, {})
        attack_txs.append(
            {
                "case": case_id,
                "tx_hash": tx_hash,
                "attack_tier": "lifecycle",
                "tx_role": "+".join(sorted(detail["roles"])),
                "actor": ",".join(sorted(detail["actors"])),
                "asset": ",".join(sorted(detail["assets"])),
                "block_number": status.get("block_number"),
                "block_time": status.get("block_time"),
                "receipt_status": status.get("status"),
                "evidence_source": "dune_candidates_plus_rpc_receipt_status" if status else "dune_candidates",
            }
        )

    attackers = []
    for candidate in candidates:
        attacker = _norm_addr(candidate.get("address", ""))
        lifecycle_hashes = {_norm_hash(tx) for tx in (candidate.get("luna_deposit_txs") or []) + (candidate.get("borrow_txs") or [])}
        timed = [statuses.get(tx) for tx in lifecycle_hashes if statuses.get(tx)]
        timed = [item for item in timed if item.get("block_timestamp")]
        attackers.append(
            {
                "case": case_id,
                "address": attacker,
                "role": "attacker",
                "luna_deposit_amount": str(candidate.get("luna_deposit_amount", "")),
                "borrowed_usd_known": str(candidate.get("borrowed_usd_known", "")),
                "deposit_tx_count": int(candidate.get("luna_deposit_tx_count") or len(candidate.get("luna_deposit_txs") or [])),
                "borrow_tx_count": int(candidate.get("borrow_tx_count") or len(candidate.get("borrow_txs") or [])),
                "lifecycle_tx_count": len(lifecycle_hashes),
                "first_tx_time": min((item["block_time"] for item in timed), default=candidate.get("first_luna_deposit_time")),
                "last_tx_time": max((item["block_time"] for item in timed), default=""),
            }
        )

    last_lifecycle = max((item for item in attack_txs if item.get("block_time")), key=lambda item: item["block_time"], default={})
    last_borrow = max((item for item in attack_txs if item.get("block_time") and "BORROW" in item["tx_role"]), key=lambda item: item["block_time"], default={})
    feed = (findings.get("identified_contracts") or {}).get("luna_usd_feed_candidate") or {}
    boundary_logs = [
        {
            "case": case_id,
            "boundary_type": "STALE_ORACLE_START",
            "tx_hash": feed.get("last_update_tx") or BLIZZ_STALE_TX,
            "block_number": feed.get("last_update_block"),
            "block_time": BLIZZ_NATURAL_START,
            "actor": "",
            "target": feed.get("address", ""),
            "receipt_status": 1,
            "reason": "Last LUNA/USD answer before stale lower-bound window.",
        },
        {
            "case": case_id,
            "boundary_type": "LAST_CONFIRMED_LIFECYCLE_TX",
            "tx_hash": last_lifecycle.get("tx_hash", ""),
            "block_number": last_lifecycle.get("block_number"),
            "block_time": last_lifecycle.get("block_time"),
            "actor": last_lifecycle.get("actor", ""),
            "target": "",
            "receipt_status": last_lifecycle.get("receipt_status"),
            "reason": "Natural end from the latest confirmed local lifecycle transaction.",
        },
        {
            "case": case_id,
            "boundary_type": "LAST_CONFIRMED_BORROW_TX",
            "tx_hash": last_borrow.get("tx_hash", ""),
            "block_number": last_borrow.get("block_number"),
            "block_time": last_borrow.get("block_time"),
            "actor": last_borrow.get("actor", ""),
            "target": "",
            "receipt_status": last_borrow.get("receipt_status"),
            "reason": "Latest confirmed borrow transaction in the local lifecycle set.",
        },
    ]

    summary = {
        "case": case_id,
        "attacker_count": len(attackers),
        "deposit_tx_count": sum(1 for item in attack_txs if "SUPPLY_LUNA" in item["tx_role"]),
        "borrow_tx_count": sum(1 for item in attack_txs if "BORROW" in item["tx_role"]),
        "lifecycle_tx_count": len(attack_txs),
        "natural_window_start": BLIZZ_NATURAL_START,
        "last_lifecycle_time": last_lifecycle.get("block_time", ""),
        "last_lifecycle_tx": last_lifecycle.get("tx_hash", ""),
        "last_borrow_time": last_borrow.get("block_time", ""),
        "last_borrow_tx": last_borrow.get("tx_hash", ""),
        "candidate_source": "existing Dune full-market candidate execution; SQL start moved to stale marker for future refresh",
    }
    findings["window"] = {
        "natural_start": BLIZZ_NATURAL_START,
        "previous_query_start": "2022-05-13T00:00:00Z",
        "previous_query_end": "2022-05-13T12:00:00Z",
        "last_confirmed_lifecycle_time": summary["last_lifecycle_time"],
        "last_confirmed_lifecycle_tx": summary["last_lifecycle_tx"],
        "last_confirmed_borrow_time": summary["last_borrow_time"],
        "last_confirmed_borrow_tx": summary["last_borrow_tx"],
    }
    findings["summary"] = {**(findings.get("summary") or {}), **summary}
    write_json(findings_path, findings)
    _write_case_tables(case_id, attackers, attack_txs, boundary_logs, summary)
    _write_blizz_trace(attack_txs, boundary_logs)
    return summary


def _write_blizz_trace(attack_txs: List[Dict[str, Any]], boundary_logs: List[Dict[str, Any]]) -> None:
    records: List[Dict[str, Any]] = []
    stale = next((item for item in boundary_logs if item.get("boundary_type") == "STALE_ORACLE_START"), None)
    if stale:
        records.append(
            {
                "case": "blizz_luna",
                "event_type": "STALE_ORACLE_START",
                "block_number": int(stale.get("block_number") or 0),
                "block_timestamp": int(_parse_time(stale.get("block_time", "")).timestamp()),
                "transaction_index": 0,
                "log_index": 0,
                "tx_hash": stale.get("tx_hash", ""),
                "address": stale.get("target", ""),
                "decoded": {
                    "asset": "LUNA",
                    "feed": stale.get("target", ""),
                    "reason": stale.get("reason", ""),
                    "evidence_quality": "dune_candidates_plus_rpc_receipt_status",
                },
            }
        )
    for index, tx in enumerate(attack_txs, start=1):
        role = tx.get("tx_role", "")
        event_type = "BORROW" if "BORROW" in role else "SUPPLY"
        decoded: Dict[str, Any]
        if event_type == "BORROW":
            decoded = {
                "borrower": tx.get("actor", ""),
                "collateral_asset": "LUNA",
                "borrow_asset": tx.get("asset", ""),
                "source": "incident_tables_full_lifecycle",
            }
        else:
            decoded = {
                "supplier": tx.get("actor", ""),
                "asset": "LUNA",
                "source": "incident_tables_full_lifecycle",
            }
        decoded["receipt_status"] = tx.get("receipt_status")
        decoded["evidence_quality"] = tx.get("evidence_source")
        records.append(
            {
                "case": "blizz_luna",
                "event_type": event_type,
                "block_number": int(tx.get("block_number") or 0),
                "block_timestamp": int(_parse_time(tx.get("block_time", "")).timestamp()) if tx.get("block_time") else 0,
                "transaction_index": index,
                "log_index": index,
                "tx_hash": tx.get("tx_hash", ""),
                "address": "dune:blizz_lifecycle",
                "decoded": decoded,
            }
        )
    write_jsonl(repo_path("artifacts", "log_trace", "blizz_luna.jsonl"), records)


def build_moonwell_tables(refresh_rpc_statuses: bool) -> Dict[str, Any]:
    case_id = "moonwell_cbeth"
    rows = load_moonwell_full_events()
    if not rows:
        raise PipelineError("Missing Moonwell full Dune events. Run with --refresh-moonwell-dune first.")
    tx_hashes = {_norm_hash(row.get("evt_tx_hash", "")) for row in rows}
    tx_hashes.add(MOONWELL_TRIGGER["tx_hash"])
    statuses = refresh_receipt_status(case_id, tx_hashes) if refresh_rpc_statuses else _read_statuses(case_id)

    by_tx: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        tx_hash = _norm_hash(row.get("evt_tx_hash", ""))
        entry = by_tx.setdefault(
            tx_hash,
            {
                "case": case_id,
                "tx_hash": tx_hash,
                "attack_tier": "lifecycle",
                "tx_role": set(),
                "actor": set(),
                "asset": set(),
                "event_count": 0,
                "borrow_cbeth": Decimal(0),
                "seized_mtoken_raw": Decimal(0),
            },
        )
        entry["tx_role"].add(str(row.get("event_type", "")))
        entry["actor"].add(_norm_addr(row.get("actor", "")))
        entry["asset"].add("cbETH")
        entry["event_count"] += 1
        entry["borrow_cbeth"] += _decimal(row.get("borrow_cbeth"))
        entry["seized_mtoken_raw"] += _decimal(row.get("seize_mtoken_raw"))

    attack_txs = []
    for tx_hash, entry in sorted(by_tx.items(), key=lambda item: statuses.get(item[0], {}).get("block_timestamp", 0)):
        status = statuses.get(tx_hash, {})
        attack_txs.append(
            {
                **{key: value for key, value in entry.items() if key not in {"tx_role", "actor", "asset", "borrow_cbeth", "seized_mtoken_raw"}},
                "tx_role": "+".join(sorted(entry["tx_role"])),
                "actor": ",".join(sorted(entry["actor"])),
                "asset": ",".join(sorted(entry["asset"])),
                "borrow_cbeth": _decimal_text(entry["borrow_cbeth"]),
                "seized_mtoken_raw": _decimal_text(entry["seized_mtoken_raw"]),
                "block_number": status.get("block_number"),
                "block_time": status.get("block_time"),
                "receipt_status": status.get("status"),
                "evidence_source": "dune_full_events_plus_rpc_receipt_status" if status else "dune_full_events",
            }
        )

    actor_roles: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in rows:
        if row.get("event_type") == "LIQUIDATE_CBETH_COLLATERAL":
            role = "liquidator"
            address = _norm_addr(row.get("actor", ""))
        else:
            role = "borrower"
            address = _norm_addr(row.get("borrower", ""))
        entry = actor_roles.setdefault((role, address), {"case": case_id, "address": address, "role": role, "tx_hashes": set(), "event_count": 0})
        entry["tx_hashes"].add(_norm_hash(row.get("evt_tx_hash", "")))
        entry["event_count"] += 1
    attackers = []
    for entry in actor_roles.values():
        txs = entry.pop("tx_hashes")
        times = [statuses.get(tx, {}).get("block_time") for tx in txs if statuses.get(tx, {}).get("block_time")]
        attackers.append(
            {
                **entry,
                "tx_count": len(txs),
                "first_tx_time": min(times) if times else "",
                "last_tx_time": max(times) if times else "",
            }
        )

    trigger_status = statuses.get(MOONWELL_TRIGGER["tx_hash"], {})
    boundary_logs = [
        {
            "case": case_id,
            "boundary_type": MOONWELL_TRIGGER["event_type"],
            "tx_hash": MOONWELL_TRIGGER["tx_hash"],
            "block_number": trigger_status.get("block_number", MOONWELL_TRIGGER["block_number"]),
            "block_time": trigger_status.get("block_time", MOONWELL_TRIGGER["block_time"]),
            "actor": MOONWELL_TRIGGER["actor"],
            "target": MOONWELL_TRIGGER["target"],
            "receipt_status": trigger_status.get("status"),
            "reason": MOONWELL_TRIGGER["reason"],
        },
        {
            "case": case_id,
            "boundary_type": "CAP_REDUCTION_TX_NOT_CONFIRMED",
            "tx_hash": "",
            "block_number": None,
            "block_time": "",
            "actor": "",
            "target": "0xfbb21d0380bee3312b33c4353c8936a0f13ef26c",
            "receipt_status": None,
            "reason": "Public post-mortem says cbETH caps were lowered to 0.01, but no local receipt-backed cap tx has been confirmed yet.",
        },
    ]
    last_attack = max((item for item in attack_txs if item.get("block_time")), key=lambda item: item["block_time"], default={})
    summary = {
        "case": case_id,
        "actor_count": len(attackers),
        "unique_attack_tx_count": len(attack_txs),
        "event_count": len(rows),
        "liquidation_event_count": sum(1 for row in rows if row.get("event_type") == "LIQUIDATE_CBETH_COLLATERAL"),
        "borrow_event_count": sum(1 for row in rows if row.get("event_type") == "BORROW_CBETH"),
        "last_attack_time": last_attack.get("block_time", ""),
        "last_attack_tx": last_attack.get("tx_hash", ""),
        **MOONWELL_PUBLIC_METRICS,
    }
    _write_case_tables(case_id, attackers, attack_txs, boundary_logs, summary)
    return summary


def build_moonwell_wrseth_tables(refresh_rpc_statuses: bool) -> Dict[str, Any]:
    case_id = "moonwell_wrseth"
    findings_path = repo_path("artifacts", "moonwell_wrseth_locator", "wrseth_findings.json")
    findings = read_json(findings_path)
    source_txs = findings.get("attack_txs") or read_jsonl(repo_path("artifacts", "moonwell_wrseth_locator", "attack_txs.jsonl"))
    tx_hashes = {_norm_hash(item.get("tx_hash", "")) for item in source_txs}
    statuses = refresh_receipt_status(case_id, tx_hashes) if refresh_rpc_statuses else _read_statuses(case_id)

    contracts = findings.get("identified_contracts") or {}
    attack_txs = []
    for index, item in enumerate(source_txs, start=1):
        tx_hash = _norm_hash(item.get("tx_hash", ""))
        status = statuses.get(tx_hash, {})
        attack_txs.append(
            {
                "case": case_id,
                "tx_hash": tx_hash,
                "attack_tier": "lifecycle",
                "tx_role": item.get("tx_role", "BORROW_AGAINST_OVERVALUED_WRSETH+SWAP_TO_WETH"),
                "actor": _norm_addr(item.get("actor", contracts.get("attacker_eoa", ""))),
                "executor_contract": _norm_addr(item.get("executor_contract", contracts.get("attacker_contract", ""))),
                "borrow_asset": item.get("borrow_asset", ""),
                "borrow_amount_reported": item.get("borrow_amount_reported", ""),
                "block_number": status.get("block_number", item.get("block_number")),
                "block_time": status.get("block_time", item.get("block_time", "")),
                "transaction_index": status.get("transaction_index", item.get("transaction_index")),
                "receipt_status": status.get("status", item.get("receipt_status")),
                "evidence_source": "moonwell_forum_seed_plus_rpc_receipt" if status else item.get("evidence_source", "moonwell_forum_canonical_seed"),
            }
        )

    times = [item.get("block_time") for item in attack_txs if item.get("block_time")]
    attackers = [
        {
            "case": case_id,
            "address": _norm_addr(contracts.get("attacker_eoa", "")),
            "role": "attacker_eoa",
            "tx_count": len(attack_txs),
            "first_tx_time": min(times) if times else "",
            "last_tx_time": max(times) if times else "",
        },
        {
            "case": case_id,
            "address": _norm_addr(contracts.get("attacker_contract", "")),
            "role": "attacker_contract",
            "tx_count": len(attack_txs),
            "first_tx_time": min(times) if times else "",
            "last_tx_time": max(times) if times else "",
        },
    ]

    boundary_logs = findings.get("boundary_logs") or []
    summary = {
        "case": case_id,
        "attacker_count": len(attackers),
        "lifecycle_tx_count": len(attack_txs),
        "borrow_tx_count": len(attack_txs),
        "boundary_log_count": len(boundary_logs),
        "natural_window_start": ((findings.get("oracle_malfunction") or {}).get("time") or ""),
        "last_attack_time": max(times) if times else "",
        "last_attack_tx": max((item for item in attack_txs if item.get("block_time")), key=lambda row: row["block_time"], default={}).get("tx_hash", ""),
        "public_bad_debt_usd": ((findings.get("summary") or {}).get("public_bad_debt_usd") or ""),
        "candidate_source": "Moonwell forum canonical attack tx list; RPC receipt fill optional",
    }
    findings["summary"] = {**(findings.get("summary") or {}), **summary}
    write_json(findings_path, findings)
    _write_case_tables(case_id, attackers, attack_txs, boundary_logs, summary)
    return summary


def build_blueberry_tables(refresh_rpc_statuses: bool) -> Dict[str, Any]:
    case_id = "blueberry_faulty_oracle"
    findings_path = repo_path("artifacts", "blueberry_faulty_oracle_locator", "blueberry_findings.json")
    findings = read_json(findings_path)
    source_txs = findings.get("attack_txs") or read_jsonl(repo_path("artifacts", "blueberry_faulty_oracle_locator", "attack_txs.jsonl"))
    tx_hashes = {_norm_hash(item.get("tx_hash", "")) for item in source_txs}
    statuses = refresh_receipt_status(case_id, tx_hashes) if refresh_rpc_statuses else _read_statuses(case_id)

    contracts = findings.get("identified_contracts") or {}
    attack_txs = []
    for item in source_txs:
        tx_hash = _norm_hash(item.get("tx_hash", ""))
        status = statuses.get(tx_hash, {})
        attack_txs.append(
            {
                "case": case_id,
                "tx_hash": tx_hash,
                "attack_tier": "lifecycle",
                "tx_role": item.get("tx_role", "FLASHLOAN+SUPPLY_WETH+BORROW_UNDERPRICED_ASSETS+SWAP_TO_ETH"),
                "actor": _norm_addr(item.get("actor", contracts.get("attacker_eoa", ""))),
                "executor_contract": _norm_addr(item.get("executor_contract", contracts.get("attacker_contract", ""))),
                "flashloan_asset": item.get("flashloan_asset", "WETH"),
                "flashloan_amount": item.get("flashloan_amount", "1"),
                "borrow_assets": item.get("borrow_assets", []),
                "borrow_amounts_reported": item.get("borrow_amounts_reported", {}),
                "borrow_amount_reported": item.get("borrow_amount_reported", ""),
                "proceeds_eth_reported": item.get("proceeds_eth_reported", ""),
                "block_number": status.get("block_number", item.get("block_number")),
                "block_time": status.get("block_time", item.get("block_time", "")),
                "transaction_index": status.get("transaction_index", item.get("transaction_index")),
                "receipt_status": status.get("status", item.get("receipt_status")),
                "evidence_source": "blueberry_postmortem_seed_plus_rpc_receipt" if status else item.get("evidence_source", "blueberry_postmortem_canonical_seed"),
            }
        )

    times = [item.get("block_time") for item in attack_txs if item.get("block_time")]
    attackers = [
        {
            "case": case_id,
            "address": _norm_addr(contracts.get("attacker_eoa", "")),
            "role": "attacker_eoa",
            "tx_count": len(attack_txs),
            "first_tx_time": min(times) if times else "",
            "last_tx_time": max(times) if times else "",
        },
        {
            "case": case_id,
            "address": _norm_addr(contracts.get("attacker_contract", "")),
            "role": "attacker_contract",
            "tx_count": len(attack_txs),
            "first_tx_time": min(times) if times else "",
            "last_tx_time": max(times) if times else "",
        },
    ]

    boundary_logs = findings.get("boundary_logs") or []
    summary = {
        "case": case_id,
        "attacker_count": len(attackers),
        "lifecycle_tx_count": len(attack_txs),
        "borrow_tx_count": len(attack_txs),
        "boundary_log_count": len(boundary_logs),
        "natural_window_start": ((findings.get("oracle_mismatch") or {}).get("time") or ""),
        "last_attack_time": max(times) if times else "",
        "last_attack_tx": max((item for item in attack_txs if item.get("block_time")), key=lambda row: row["block_time"], default={}).get("tx_hash", ""),
        "reported_proceeds_eth": ((findings.get("summary") or {}).get("reported_proceeds_eth") or ""),
        "reported_protocol_retained_eth": ((findings.get("summary") or {}).get("reported_protocol_retained_eth") or ""),
        "candidate_source": "Blueberry post-mortem canonical attack transaction; RPC receipt fill optional",
    }
    findings["summary"] = {**(findings.get("summary") or {}), **summary}
    write_json(findings_path, findings)
    _write_case_tables(case_id, attackers, attack_txs, boundary_logs, summary)
    return summary


def build_feed_binding_tables(case_id: str) -> Dict[str, Any]:
    evidence = read_json(repo_path("artifacts", "feed_binding_locator", f"{case_id}_evidence.json"))
    config = evidence["transactions"]["config"]
    exploit = evidence["transactions"]["exploit"]
    boundary_logs = [
        {
            "case": case_id,
            "boundary_type": "ORACLE_FEED_SET",
            "tx_hash": config["hash"],
            "block_number": config["block_number"],
            "block_time": config["block_time"],
            "actor": config["from"],
            "target": config["to"],
            "receipt_status": config["status"],
            "reason": "Misconfigured oracle feed transaction.",
        }
    ]
    for boundary in evidence.get("boundary_logs") or []:
        boundary_logs.append(
            {
                "case": case_id,
                "boundary_type": boundary["event_type"],
                "tx_hash": boundary["hash"],
                "block_number": boundary["block_number"],
                "block_time": boundary["block_time"],
                "actor": boundary["from"],
                "target": boundary["to"],
                "receipt_status": boundary["status"],
                "reason": boundary.get("note", ""),
                "feed_after": boundary.get("feed_after", ""),
            }
        )
    attackers = [
        {
            "case": case_id,
            "address": exploit["from"],
            "role": "attacker",
            "tx_count": 1,
            "first_tx_time": exploit["block_time"],
            "last_tx_time": exploit["block_time"],
        }
    ]
    attack_txs = [
        {
            "case": case_id,
            "tx_hash": exploit["hash"],
            "attack_tier": "core_exploit",
            "tx_role": "SUPPLY+BORROW",
            "actor": exploit["from"],
            "asset": "",
            "block_number": exploit["block_number"],
            "block_time": exploit["block_time"],
            "receipt_status": exploit["status"],
            "evidence_source": "rpc_receipt",
        }
    ]
    summary = {
        "case": case_id,
        "attacker_count": 1,
        "core_exploit_tx_count": 1,
        "boundary_log_count": len(boundary_logs),
        "config_time": config["block_time"],
        "exploit_time": exploit["block_time"],
        "last_boundary_time": max(item["block_time"] for item in boundary_logs if item.get("block_time")),
        "feed_identity_verification": evidence.get("feed_identity_verification") or {},
    }
    _write_case_tables(case_id, attackers, attack_txs, boundary_logs, summary)
    return summary


def _write_case_tables(
    case_id: str,
    attackers: List[Dict[str, Any]],
    attack_txs: List[Dict[str, Any]],
    boundary_logs: List[Dict[str, Any]],
    summary: Dict[str, Any],
) -> None:
    base = repo_path("artifacts", "incident_tables", case_id)
    ensure_dir(base)
    write_jsonl(base / "attackers.jsonl", attackers)
    write_jsonl(base / "attack_txs.jsonl", attack_txs)
    write_jsonl(base / "boundary_logs.jsonl", boundary_logs)
    write_json(base / "summary.json", summary)


def _pre_attack_counts(case_id: str) -> Dict[str, int]:
    path = repo_path("artifacts", "incident_tables", case_id, "pre_attack_logs.jsonl")
    if not path.exists():
        return {"pre_attack_logs": 0, "pre_attack_logs_with_topics": 0}
    rows = read_jsonl(path)
    return {
        "pre_attack_logs": len(rows),
        "pre_attack_logs_with_topics": sum(1 for row in rows if row.get("topics")),
    }


def render_report(summaries: Dict[str, Dict[str, Any]]) -> str:
    lines = [
        "# Oracle Misconfiguration Incident Tables",
        "",
        "## Scope",
        "",
        "- Times are UTC.",
        "- `attack_txs` separates core exploit transactions from lifecycle transactions.",
        "- `boundary_logs` contains config, stale, cap, repair, and recovery boundary records; those are not counted as attack transactions.",
        "",
        "## Case Summary",
        "",
        "| case | actors | attack txs/events | boundary logs | pre-attack logs | pre-attack logs with topics | natural window / note |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for case_id in ("venus_luna", "blizz_luna", "moonwell_cbeth", "moonwell_wrseth", "blueberry_faulty_oracle", "ploutos"):
        summary = summaries.get(case_id) or {}
        actor_count = summary.get("attacker_count", summary.get("actor_count", ""))
        attack_count = summary.get("lifecycle_tx_count", summary.get("unique_attack_tx_count", summary.get("core_exploit_tx_count", "")))
        boundary_count = summary.get("boundary_log_count", "")
        if not boundary_count:
            boundary_path = repo_path("artifacts", "incident_tables", case_id, "boundary_logs.jsonl")
            boundary_count = len(_load_jsonl_if_exists(boundary_path))
        pre_counts = _pre_attack_counts(case_id)
        note = summary.get("natural_window_start") or summary.get("last_attack_time") or summary.get("last_boundary_time") or ""
        lines.append(
            f"| `{case_id}` | {actor_count} | {attack_count} | {boundary_count} | "
            f"{pre_counts['pre_attack_logs']} | {pre_counts['pre_attack_logs_with_topics']} | {note} |"
        )
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "- Per-case tables: `artifacts/incident_tables/<case>/{attackers,attack_txs,boundary_logs}.jsonl`",
            "- Per-case pre-attack logs: `artifacts/incident_tables/<case>/pre_attack_logs.jsonl`",
            "- Per-case summaries: `artifacts/incident_tables/<case>/summary.json`",
            "- Moonwell full Dune event cache: `artifacts/moonwell_cbeth_locator/dune_full_events.jsonl`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build unified attackers, attack_txs, and boundary_logs tables.")
    parser.add_argument("--refresh-moonwell-dune", action="store_true", help="Fetch the cached Moonwell Dune execution result via the Dune API.")
    parser.add_argument("--refresh-rpc-status", action="store_true", help="Fetch receipt status/block time for all table transaction hashes.")
    args = parser.parse_args()

    if args.refresh_moonwell_dune:
        rows = refresh_moonwell_full_events()
        rebuild_moonwell_candidates(rows)
    else:
        rows = load_moonwell_full_events()
        if rows:
            rebuild_moonwell_candidates(rows)

    summaries = {
        "venus_luna": build_venus_tables(args.refresh_rpc_status),
        "blizz_luna": build_blizz_tables(args.refresh_rpc_status),
        "moonwell_cbeth": build_moonwell_tables(args.refresh_rpc_status),
        "moonwell_wrseth": build_moonwell_wrseth_tables(args.refresh_rpc_status),
        "blueberry_faulty_oracle": build_blueberry_tables(args.refresh_rpc_status),
        "ploutos": build_feed_binding_tables("ploutos"),
    }
    materialize_pre_attack_cases(
        PRE_ATTACK_CASE_ORDER,
        allow_rpc_fill=False,
        max_rpc_requests=0,
        preserve_existing=True,
    )
    report = render_report(summaries)
    report_path = repo_path("results", "incident_tables.md")
    ensure_dir(report_path.parent)
    report_path.write_text(report, encoding="utf-8")
    print(f"Wrote incident table report: {report_path}")


if __name__ == "__main__":
    main()
