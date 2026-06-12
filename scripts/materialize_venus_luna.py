#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, DefaultDict, Dict, List, Optional, Tuple

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
from locate_blizz_luna import (
    ANSWER_UPDATED_TOPIC,
    COMPOUND_BORROW_TOPIC,
    COMPOUND_MINT_TOPIC,
    DEFAULT_VENUS_END,
    VENUS_HISTORY_DIR,
    VENUS_LUNA_FEED,
    VENUS_VBUSD,
    VENUS_VLUNA,
    _decode_answer_updated_row,
    _decode_compound_borrow,
    _decode_compound_mint,
    _decimal_string,
    _load_csv,
    _norm_addr,
    _parse_time,
)


REQUIRED_LOCAL_FIELDS = (
    "block_timestamp",
    "block_number",
    "transaction_hash",
    "transaction_index",
    "log_index",
)
SYNTHETIC_VENUS_ATTACKER = "0x4444444444444444444444444444444444444444"


def _int_field(row: Dict[str, Any], key: str, default: int = 0) -> int:
    value = row.get(key)
    if value in (None, ""):
        return default
    return int(value)


def _unix_timestamp(value: str) -> int:
    return int(_parse_time(value).timestamp())


def row_needs_rpc_fill(row: Dict[str, Any]) -> bool:
    return any(row.get(field) in (None, "") for field in REQUIRED_LOCAL_FIELDS)


class RpcFiller:
    def __init__(self, *, offline: bool, allow_rpc_fill: bool, max_requests: int):
        self.offline = offline
        self.allow_rpc_fill = allow_rpc_fill and not offline
        self.max_requests = max_requests
        self.requests = 0
        self.rpc_url: Optional[str] = None
        self.receipts: Dict[str, Dict[str, Any]] = {}
        self.blocks: Dict[int, Dict[str, Any]] = {}

    def _rpc_url(self) -> str:
        if self.rpc_url:
            return self.rpc_url
        case = get_case("venus_luna")
        env = load_env()
        self.rpc_url = resolve_template(case["rpc_url_template"], env)
        return self.rpc_url

    def _call(self, method: str, params: List[Any]) -> Any:
        if self.requests >= self.max_requests:
            raise PipelineError(f"RPC fallback request cap exceeded: {self.max_requests}")
        self.requests += 1
        return rpc_call(self._rpc_url(), method, params, timeout=60)

    def receipt(self, tx_hash: str) -> Dict[str, Any]:
        if tx_hash not in self.receipts:
            receipt = self._call("eth_getTransactionReceipt", [tx_hash])
            if not receipt:
                raise PipelineError(f"No receipt returned for Venus tx {tx_hash}")
            self.receipts[tx_hash] = receipt
        return self.receipts[tx_hash]

    def block_timestamp(self, block_number: int) -> int:
        if block_number not in self.blocks:
            block = self._call("eth_getBlockByNumber", [hex(block_number), False])
            if not block:
                raise PipelineError(f"No block returned for Venus block {block_number}")
            self.blocks[block_number] = block
        return int(self.blocks[block_number].get("timestamp", "0x0"), 16)

    def fill_metadata(self, row: Dict[str, Any]) -> Dict[str, Any]:
        if not row_needs_rpc_fill(row):
            return row
        if not self.allow_rpc_fill:
            raise PipelineError(
                f"Local Venus CSV row is missing replay metadata and RPC fill is disabled: "
                f"{row.get('transaction_hash', '<missing tx>')}"
            )

        filled = dict(row)
        tx_hash = filled.get("transaction_hash", "")
        receipt = self.receipt(tx_hash)
        block_number = int(receipt.get("blockNumber", "0x0"), 16)
        filled.setdefault("block_number", str(block_number))
        if not filled.get("block_number"):
            filled["block_number"] = str(block_number)
        if not filled.get("transaction_index"):
            filled["transaction_index"] = str(int(receipt.get("transactionIndex", "0x0"), 16))
        if not filled.get("log_index"):
            filled["log_index"] = str(_find_log_index(filled, receipt))
        if not filled.get("block_timestamp"):
            filled["block_timestamp"] = _iso_from_unix(self.block_timestamp(block_number))
        return filled


def _find_log_index(row: Dict[str, Any], receipt: Dict[str, Any]) -> int:
    row_address = _norm_addr(row.get("address", ""))
    row_topic0 = (row.get("topic0") or "").lower()
    row_data = (row.get("data") or "").lower()
    for log in receipt.get("logs", []):
        topics = [topic.lower() for topic in log.get("topics", [])]
        if _norm_addr(log.get("address", "")) != row_address:
            continue
        if row_topic0 and (not topics or topics[0] != row_topic0):
            continue
        if row_data and (log.get("data") or "").lower() != row_data:
            continue
        return int(log.get("logIndex", "0x0"), 16)
    return 0


def _iso_from_unix(timestamp: int) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(timestamp, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_oracle_marker(filler: RpcFiller) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    price_rows = [
        filler.fill_metadata(row)
        for row in _load_csv(VENUS_HISTORY_DIR / "price.csv")
        if (row.get("topic0") or "").lower() == ANSWER_UPDATED_TOPIC
        and _norm_addr(row.get("address", "")) == VENUS_LUNA_FEED
    ]
    if not price_rows:
        raise PipelineError("No Venus LUNA AnswerUpdated rows found.")
    row = max(price_rows, key=lambda item: _int_field(item, "block_number"))
    return row, _decode_answer_updated_row(row)


def _row_sort_key(row: Dict[str, Any]) -> Tuple[int, int, int]:
    return (
        _int_field(row, "block_number"),
        _int_field(row, "transaction_index"),
        _int_field(row, "log_index"),
    )


def _collect_deposits(start_time: Any, end_time: Any, filler: RpcFiller) -> DefaultDict[str, Dict[str, Any]]:
    deposits: DefaultDict[str, Dict[str, Any]] = defaultdict(
        lambda: {"amount": Decimal(0), "tx_hashes": set(), "events": [], "first": None}
    )
    for raw_row in _load_csv(VENUS_HISTORY_DIR / "deposit.csv"):
        if _norm_addr(raw_row.get("address", "")) != VENUS_VLUNA:
            continue
        if (raw_row.get("topic0") or "").lower() != COMPOUND_MINT_TOPIC:
            continue
        row = filler.fill_metadata(raw_row)
        block_time = _parse_time(row["block_timestamp"])
        if not (start_time <= block_time <= end_time):
            continue
        decoded = _decode_compound_mint(row, decimals=6)
        if not decoded:
            continue
        account = decoded["account"]
        event = {
            "account": account,
            "amount": decoded["amount"],
            "tx_hash": row["transaction_hash"],
            "block_number": _int_field(row, "block_number"),
            "block_timestamp": _unix_timestamp(row["block_timestamp"]),
            "transaction_index": _int_field(row, "transaction_index"),
            "log_index": _int_field(row, "log_index"),
        }
        entry = deposits[account]
        entry["amount"] += decoded["amount"]
        entry["tx_hashes"].add(row["transaction_hash"])
        entry["events"].append(event)
        if entry["first"] is None or _row_sort_key(row) < _event_sort_key(entry["first"]):
            entry["first"] = event
    return deposits


def _collect_borrows(start_time: Any, end_time: Any, filler: RpcFiller) -> DefaultDict[str, Dict[str, Any]]:
    borrows: DefaultDict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "amount": Decimal(0),
            "tx_hashes": set(),
            "events": [],
            "first": None,
            "largest": None,
            "largest_amount": Decimal(0),
        }
    )
    for raw_row in _load_csv(VENUS_HISTORY_DIR / "borrow.csv"):
        if _norm_addr(raw_row.get("address", "")) != VENUS_VBUSD:
            continue
        if (raw_row.get("topic0") or "").lower() != COMPOUND_BORROW_TOPIC:
            continue
        row = filler.fill_metadata(raw_row)
        block_time = _parse_time(row["block_timestamp"])
        if not (start_time <= block_time <= end_time):
            continue
        decoded = _decode_compound_borrow(row, decimals=18)
        if not decoded:
            continue
        account = decoded["account"]
        event = {
            "account": account,
            "amount": decoded["amount"],
            "tx_hash": row["transaction_hash"],
            "block_number": _int_field(row, "block_number"),
            "block_timestamp": _unix_timestamp(row["block_timestamp"]),
            "transaction_index": _int_field(row, "transaction_index"),
            "log_index": _int_field(row, "log_index"),
        }
        entry = borrows[account]
        entry["amount"] += decoded["amount"]
        entry["tx_hashes"].add(row["transaction_hash"])
        entry["events"].append(event)
        if entry["first"] is None or _event_sort_key(event) < _event_sort_key(entry["first"]):
            entry["first"] = event
        if decoded["amount"] > entry["largest_amount"]:
            entry["largest_amount"] = decoded["amount"]
            entry["largest"] = event
    return borrows


def _event_sort_key(event: Dict[str, Any]) -> Tuple[int, int, int]:
    return (
        int(event.get("block_number") or 0),
        int(event.get("transaction_index") or 0),
        int(event.get("log_index") or 0),
    )


def _serialize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "account": event["account"],
        "amount": _decimal_string(event["amount"]),
        "tx_hash": event["tx_hash"],
        "block_number": event["block_number"],
        "block_timestamp": event["block_timestamp"],
        "block_time": _iso_from_unix(int(event["block_timestamp"])),
        "transaction_index": event["transaction_index"],
        "log_index": event["log_index"],
    }


def build_venus_materialization(end: str, *, offline: bool, allow_rpc_fill: bool, max_rpc_requests: int) -> Dict[str, Any]:
    filler = RpcFiller(offline=offline, allow_rpc_fill=allow_rpc_fill, max_requests=max_rpc_requests)
    oracle_row, oracle = _load_oracle_marker(filler)
    start_time = _parse_time(oracle["block_timestamp"])
    end_time = _parse_time(end)
    deposits = _collect_deposits(start_time, end_time, filler)
    borrows = _collect_borrows(start_time, end_time, filler)

    candidates = []
    for account, borrow in borrows.items():
        deposit = deposits.get(account)
        if not deposit:
            continue
        candidate = {
            "address": account,
            "luna_deposit_amount": _decimal_string(deposit["amount"]),
            "borrowed_asset": "BUSD",
            "borrowed_usd_known": _decimal_string(borrow["amount"]),
            "luna_deposit_tx_count": len(deposit["tx_hashes"]),
            "borrow_tx_count": len(borrow["tx_hashes"]),
            "luna_deposit_txs": sorted(deposit["tx_hashes"]),
            "borrow_txs": sorted(borrow["tx_hashes"]),
            "luna_deposit_events": [_serialize_event(event) for event in sorted(deposit["events"], key=_event_sort_key)],
            "borrow_events": [_serialize_event(event) for event in sorted(borrow["events"], key=_event_sort_key)],
            "first_luna_deposit_tx": deposit["first"]["tx_hash"],
            "first_borrow_tx": borrow["first"]["tx_hash"],
            "largest_borrow_tx": borrow["largest"]["tx_hash"] if borrow["largest"] else "",
            "first_luna_deposit_block": deposit["first"]["block_number"],
            "first_borrow_block": borrow["first"]["block_number"],
            "first_luna_deposit_time": _iso_from_unix(deposit["first"]["block_timestamp"]),
            "first_borrow_time": _iso_from_unix(borrow["first"]["block_timestamp"]),
        }
        candidates.append(candidate)
    candidates.sort(key=lambda item: Decimal(item["borrowed_usd_known"]), reverse=True)

    trace_records = build_trace_records(oracle_row, oracle, candidates)
    total_luna_deposit = sum(Decimal(item["luna_deposit_amount"]) for item in candidates)
    total_busd_borrowed = sum(Decimal(item["borrowed_usd_known"]) for item in candidates)
    top_two_busd = sum(Decimal(item["borrowed_usd_known"]) for item in candidates[:2])
    findings = {
        "scope": "read-only historical forensic materialization for the Venus LUNA stale-oracle incident",
        "source": str(VENUS_HISTORY_DIR),
        "window": {
            "start": _iso_from_unix(_unix_timestamp(oracle["block_timestamp"])),
            "end": _iso_from_unix(int(end_time.timestamp())),
        },
        "identified_contracts": {
            "luna_usd_feed": VENUS_LUNA_FEED,
            "vluna_market": VENUS_VLUNA,
            "vbusd_market": VENUS_VBUSD,
        },
        "oracle": {
            "feed": oracle["feed"],
            "last_update_tx": oracle["tx_hash"],
            "last_update_block": oracle["block_number"],
            "last_update_time": oracle["block_timestamp"],
            "last_answer": _decimal_string(oracle["answer"], places=8),
            "updated_at": oracle["updated_at"],
            "round_id": oracle["round_id"],
        },
        "summary": {
            "candidate_count": len(candidates),
            "deposit_tx_count": sum(item["luna_deposit_tx_count"] for item in candidates),
            "borrow_tx_count": sum(item["borrow_tx_count"] for item in candidates),
            "total_luna_deposit": _decimal_string(total_luna_deposit),
            "total_busd_borrowed": _decimal_string(total_busd_borrowed),
            "top_two_busd_borrowed": _decimal_string(top_two_busd),
            "public_narrative_busd": "11411700",
        },
        "rpc_fallback": {
            "offline": offline,
            "allow_rpc_fill": allow_rpc_fill and not offline,
            "requests": filler.requests,
            "max_requests": max_rpc_requests,
        },
        "full_artifacts": {
            "candidates_jsonl": "artifacts/venus_luna_locator/venus_candidates_full.jsonl",
            "trace_jsonl": "artifacts/log_trace/venus_luna.jsonl",
        },
        "top_candidates": candidates[:5],
    }
    return {"candidates": candidates, "trace_records": trace_records, "findings": findings}


def build_trace_records(
    oracle_row: Dict[str, Any],
    oracle: Dict[str, Any],
    candidates: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = [
        {
            "case": "venus_luna",
            "event_type": "STALE_ORACLE_START",
            "block_number": oracle["block_number"],
            "block_timestamp": _unix_timestamp(oracle["block_timestamp"]),
            "transaction_index": _int_field(oracle_row, "transaction_index"),
            "log_index": _int_field(oracle_row, "log_index"),
            "tx_hash": oracle["tx_hash"],
            "address": oracle["feed"],
            "decoded": {
                "asset": "LUNA",
                "feed": oracle["feed"],
                "answer": _decimal_string(oracle["answer"], places=8),
                "updated_at": oracle["updated_at"],
                "round_id": oracle["round_id"],
                "reason": "chainlink_answer_stopped_near_lower_bound",
            },
        }
    ]
    for candidate in candidates:
        for event in candidate.get("luna_deposit_events") or []:
            records.append(
                {
                    "case": "venus_luna",
                    "event_type": "SUPPLY",
                    "block_number": event["block_number"],
                    "block_timestamp": event["block_timestamp"],
                    "transaction_index": event["transaction_index"],
                    "log_index": event["log_index"],
                    "tx_hash": event["tx_hash"],
                    "address": VENUS_VLUNA,
                    "decoded": {
                        "account": candidate["address"],
                        "supplier": candidate["address"],
                        "asset": "LUNA",
                        "amount": event["amount"],
                        "receiver": VENUS_VLUNA,
                        "source": "venus_local_history_csv",
                    },
                }
            )
        for event in candidate.get("borrow_events") or []:
            records.append(
                {
                    "case": "venus_luna",
                    "event_type": "BORROW",
                    "block_number": event["block_number"],
                    "block_timestamp": event["block_timestamp"],
                    "transaction_index": event["transaction_index"],
                    "log_index": event["log_index"],
                    "tx_hash": event["tx_hash"],
                    "address": VENUS_VBUSD,
                    "decoded": {
                        "borrower": candidate["address"],
                        "collateral_asset": "LUNA",
                        "borrow_asset": "BUSD",
                        "borrow_amount": event["amount"],
                        "borrow_amount_usd": event["amount"],
                        "source": "venus_local_history_csv",
                    },
                }
            )
    return sorted(
        records,
        key=lambda item: (
            int(item.get("block_number", 0)),
            int(item.get("transaction_index", 0)),
            int(item.get("log_index", 0)),
        ),
    )


def render_report(findings: Dict[str, Any]) -> str:
    summary = findings["summary"]
    oracle = findings["oracle"]
    lines = [
        "# Venus LUNA Materialized Trace",
        "",
        "## Safety scope",
        "",
        "- Scope: read-only historical incident detection and forensic reporting.",
        "- Data source priority: local CSV first; RPC only fills missing historical metadata.",
        "- It does not submit transactions, call protocol write methods, handle private keys, or generate exploit execution steps.",
        "",
        "## Findings",
        "",
        f"- Stale oracle marker: tx `{oracle['last_update_tx']}`, block `{oracle['last_update_block']}`, answer `${oracle['last_answer']}`.",
        f"- Candidate accounts: `{summary['candidate_count']}`.",
        f"- Evidence counts: `{summary['deposit_tx_count']}` vLUNA deposit tx, `{summary['borrow_tx_count']}` vBUSD borrow tx.",
        f"- Total LUNA deposit: `{summary['total_luna_deposit']}`.",
        f"- Total BUSD borrowed: `${summary['total_busd_borrowed']}`.",
        f"- Top two BUSD borrowed: `${summary['top_two_busd_borrowed']}` vs public narrative `${summary['public_narrative_busd']}`.",
        f"- RPC fallback requests: `{findings['rpc_fallback']['requests']}`.",
        "",
        "## Top Candidates",
        "",
    ]
    for candidate in findings.get("top_candidates", []):
        lines.append(
            f"- `{candidate['address']}` deposited `{candidate['luna_deposit_amount']}` LUNA and borrowed `${candidate['borrowed_usd_known']}` BUSD"
        )
        lines.append(f"  - first deposit tx: `{candidate['first_luna_deposit_tx']}`")
        lines.append(f"  - first borrow tx: `{candidate['first_borrow_tx']}`")
    lines.append("")
    return "\n".join(lines)


def write_outputs(materialized: Dict[str, Any]) -> None:
    candidates_path = repo_path("artifacts", "venus_luna_locator", "venus_candidates_full.jsonl")
    findings_path = repo_path("artifacts", "venus_luna_locator", "venus_findings.json")
    trace_path = repo_path("artifacts", "log_trace", "venus_luna.jsonl")
    report_path = repo_path("results", "venus_luna_locator.md")
    write_jsonl(candidates_path, materialized["candidates"])
    write_json(findings_path, materialized["findings"])
    write_jsonl(trace_path, materialized["trace_records"])
    ensure_dir(report_path.parent)
    report_path.write_text(render_report(materialized["findings"]), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize a real Venus LUNA stale-oracle replay trace.")
    parser.add_argument("--end", default=DEFAULT_VENUS_END, help="End timestamp for the Venus stale window.")
    parser.add_argument("--offline", action="store_true", help="Disable RPC fallback and use local CSV only.")
    parser.add_argument(
        "--allow-rpc-fill",
        action="store_true",
        default=True,
        help="Allow read-only RPC fallback for missing local metadata. Enabled by default unless --offline is set.",
    )
    parser.add_argument("--max-rpc-requests", type=int, default=500)
    args = parser.parse_args()

    materialized = build_venus_materialization(
        args.end,
        offline=args.offline,
        allow_rpc_fill=args.allow_rpc_fill,
        max_rpc_requests=args.max_rpc_requests,
    )
    if SYNTHETIC_VENUS_ATTACKER in {item["address"] for item in materialized["candidates"]}:
        raise SystemExit("Refusing to write Venus materialization containing synthetic fixture attacker.")
    write_outputs(materialized)
    print("Wrote Venus materialized artifacts:")
    print(f"- {repo_path('artifacts', 'venus_luna_locator', 'venus_candidates_full.jsonl')}")
    print(f"- {repo_path('artifacts', 'venus_luna_locator', 'venus_findings.json')}")
    print(f"- {repo_path('artifacts', 'log_trace', 'venus_luna.jsonl')}")
    print(f"- {repo_path('results', 'venus_luna_locator.md')}")


if __name__ == "__main__":
    main()
