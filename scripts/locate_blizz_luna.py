#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, DefaultDict, Dict, Iterable, List, Optional, Tuple

from common import (
    PipelineError,
    ensure_dir,
    get_case,
    load_env,
    print_status,
    read_jsonl,
    repo_path,
    resolve_template,
    rpc_call,
    write_json,
    write_jsonl,
)


ANSWER_UPDATED_TOPIC = "0x0559884fd3a460db3073b7fc896cc77986f16e378210ded43186175bf646fc5f"
ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
COMPOUND_MINT_TOPIC = "0x4c209b5fc8ad50758f13e2e1088ba56a560dff690a1c6fef26394f4c03821c4f"
COMPOUND_BORROW_TOPIC = "0x13ed6866d4e1ee6da46f845c46d7e54120883d75c5ea9a2dacc1c4ca8984ab80"

VENUS_LUNA_FEED = "0xec72d46011d67a6ac4fa7d3f476fa2049dc807ee"
VENUS_VLUNA = "0xb91a659e88b51474767cd97ef3196a3e7cedd2c8"
VENUS_VBUSD = "0x95c78222b3d6e262426483d42cfa53685a67ab9d"
VENUS_HISTORY_DIR = repo_path("background", "DSC-Guard_ref_Venus", "venus", "history_data")

DEFAULT_START = "2022-05-12T11:39:06Z"
DEFAULT_END = "2022-05-13T12:00:00Z"
DEFAULT_VENUS_END = "2022-05-13T12:00:00Z"
PUBLIC_BLIZZ_LOSS_USD = Decimal("8280000")
SLOWMIST_BLIZZ_LOSS_USD = Decimal("8300000")

DEFAULT_AVALANCHE_BORROW_TOKENS = [
    {"symbol": "USDC", "address": "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E", "decimals": 6},
    {"symbol": "USDT.e", "address": "0xc7198437980c041c805A1EDcbA50c1Ce5db95118", "decimals": 6},
    {"symbol": "USDC.e", "address": "0xA7D7079b0FEaD91F3e65f86E8915Cb59c1a4C664", "decimals": 6},
    {"symbol": "DAI.e", "address": "0xd586E7F844cEa2F87f50152665BCbc2C279D8d70", "decimals": 18},
    {"symbol": "WAVAX", "address": "0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7", "decimals": 18},
    {"symbol": "WETH.e", "address": "0x49D5c2BdFfac6CE2BFdB6640F4F80f226bc10bAB", "decimals": 18},
    {"symbol": "WBTC.e", "address": "0x50b7545627a5162F82A992c33b87aDc75187B218", "decimals": 8},
]


def _clean_hex(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "0x"
    return value if value.startswith("0x") else f"0x{value}"


def _norm_addr(value: str) -> str:
    value = _clean_hex(value)
    if value == "0x":
        return value
    body = value[2:].lower()
    if len(body) > 40:
        raise PipelineError(f"Address is longer than 20 bytes: {value}")
    return "0x" + body.rjust(40, "0")


def _topic_address(topic: str) -> str:
    topic = _clean_hex(topic)
    return _norm_addr(topic[-40:])


def _topic_from_address(address: str) -> str:
    return "0x" + _norm_addr(address)[2:].rjust(64, "0")


def _hex_to_uint(value: str) -> int:
    value = _clean_hex(value)
    if value == "0x":
        return 0
    return int(value, 16)


def _hex_to_int256(value: str) -> int:
    number = _hex_to_uint(value)
    if number >= 2**255:
        number -= 2**256
    return number


def _words(data: str) -> List[str]:
    body = _clean_hex(data)[2:]
    if not body:
        return []
    return [body[index : index + 64] for index in range(0, len(body), 64)]


def _word_to_uint(word: str) -> int:
    return int(word or "0", 16)


def _word_to_address(word: str) -> str:
    return _norm_addr(word[-40:])


def _decimal_amount(raw: int, decimals: int) -> Decimal:
    return Decimal(raw) / (Decimal(10) ** decimals)


def _decimal_string(value: Decimal, places: int = 6) -> str:
    quant = Decimal(10) ** -places
    text = format(value.quantize(quant), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _parse_decimal(value: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise PipelineError(f"Invalid decimal value: {value}") from exc


def _parse_time(value: str) -> datetime:
    clean = value.strip()
    if clean.endswith(" UTC"):
        clean = clean[:-4].strip() + "+00:00"
    if clean.endswith("Z"):
        clean = clean[:-1] + "+00:00"
    if "." in clean and "+" not in clean and clean.count(":") >= 2:
        clean += "+00:00"
    return datetime.fromisoformat(clean).astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        raise PipelineError(f"Missing CSV file: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _decode_compound_mint(row: Dict[str, str], decimals: int) -> Optional[Dict[str, Any]]:
    if (row.get("topic0") or "").lower() != COMPOUND_MINT_TOPIC:
        return None
    words = _words(row.get("data", ""))
    if len(words) < 3:
        return None
    return {
        "account": _word_to_address(words[0]),
        "amount_raw": _word_to_uint(words[1]),
        "amount": _decimal_amount(_word_to_uint(words[1]), decimals),
        "mint_tokens_raw": _word_to_uint(words[2]),
    }


def _decode_compound_borrow(row: Dict[str, str], decimals: int) -> Optional[Dict[str, Any]]:
    if (row.get("topic0") or "").lower() != COMPOUND_BORROW_TOPIC:
        return None
    words = _words(row.get("data", ""))
    if len(words) < 4:
        return None
    return {
        "account": _word_to_address(words[0]),
        "amount_raw": _word_to_uint(words[1]),
        "amount": _decimal_amount(_word_to_uint(words[1]), decimals),
        "account_borrows_raw": _word_to_uint(words[2]),
        "total_borrows_raw": _word_to_uint(words[3]),
    }


def _decode_answer_updated_row(row: Dict[str, str], decimals: int = 8) -> Dict[str, Any]:
    data_words = _words(row.get("data", ""))
    updated_at = _word_to_uint(data_words[0]) if data_words else 0
    answer_raw = _hex_to_int256(row.get("topic1", "0x0"))
    round_id = _hex_to_uint(row.get("topic2", "0x0"))
    return {
        "feed": _norm_addr(row.get("address", "")),
        "tx_hash": row.get("transaction_hash", ""),
        "block_number": int(row.get("block_number") or 0),
        "block_timestamp": row.get("block_timestamp", ""),
        "updated_at": updated_at,
        "answer_raw": answer_raw,
        "answer": _decimal_amount(answer_raw, decimals),
        "round_id": round_id,
    }


def extract_venus_reference(top: int = 5, end: str = DEFAULT_VENUS_END) -> Dict[str, Any]:
    price_rows = _load_csv(VENUS_HISTORY_DIR / "price.csv")
    price_rows = [
        row
        for row in price_rows
        if (row.get("topic0") or "").lower() == ANSWER_UPDATED_TOPIC
        and _norm_addr(row.get("address", "")) == VENUS_LUNA_FEED
    ]
    if not price_rows:
        raise PipelineError("No Venus LUNA AnswerUpdated rows found.")
    last_price = max(price_rows, key=lambda item: int(item["block_number"]))
    oracle = _decode_answer_updated_row(last_price)
    start_time = _parse_time(oracle["block_timestamp"])
    end_time = _parse_time(end)

    deposits_by_account: DefaultDict[str, Dict[str, Any]] = defaultdict(
        lambda: {"amount": Decimal(0), "tx_hashes": [], "first_tx": "", "first_block": 0}
    )
    borrows_by_account: DefaultDict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "amount": Decimal(0),
            "tx_hashes": [],
            "first_tx": "",
            "first_block": 0,
            "largest_tx": "",
            "largest_amount": Decimal(0),
        }
    )

    for row in _load_csv(VENUS_HISTORY_DIR / "deposit.csv"):
        if _norm_addr(row.get("address", "")) != VENUS_VLUNA:
            continue
        block_time = _parse_time(row["block_timestamp"])
        if not (start_time <= block_time <= end_time):
            continue
        decoded = _decode_compound_mint(row, decimals=6)
        if not decoded:
            continue
        account = decoded["account"]
        entry = deposits_by_account[account]
        entry["amount"] += decoded["amount"]
        entry["tx_hashes"].append(row["transaction_hash"])
        if not entry["first_tx"] or int(row["block_number"]) < entry["first_block"]:
            entry["first_tx"] = row["transaction_hash"]
            entry["first_block"] = int(row["block_number"])

    for row in _load_csv(VENUS_HISTORY_DIR / "borrow.csv"):
        if _norm_addr(row.get("address", "")) != VENUS_VBUSD:
            continue
        block_time = _parse_time(row["block_timestamp"])
        if not (start_time <= block_time <= end_time):
            continue
        decoded = _decode_compound_borrow(row, decimals=18)
        if not decoded:
            continue
        account = decoded["account"]
        entry = borrows_by_account[account]
        entry["amount"] += decoded["amount"]
        entry["tx_hashes"].append(row["transaction_hash"])
        if not entry["first_tx"] or int(row["block_number"]) < entry["first_block"]:
            entry["first_tx"] = row["transaction_hash"]
            entry["first_block"] = int(row["block_number"])
        if decoded["amount"] > entry["largest_amount"]:
            entry["largest_amount"] = decoded["amount"]
            entry["largest_tx"] = row["transaction_hash"]

    attackers = []
    for account, borrow in borrows_by_account.items():
        deposit = deposits_by_account.get(account)
        if not deposit:
            continue
        attackers.append(
            {
                "address": account,
                "luna_deposit": _decimal_string(deposit["amount"]),
                "borrowed_asset": "BUSD",
                "borrowed_usd": _decimal_string(borrow["amount"]),
                "deposit_tx_hashes": sorted(set(deposit["tx_hashes"])),
                "borrow_tx_hashes": sorted(set(borrow["tx_hashes"])),
                "first_deposit_tx": deposit["first_tx"],
                "first_borrow_tx": borrow["first_tx"],
                "largest_borrow_tx": borrow["largest_tx"],
            }
        )
    attackers.sort(key=lambda item: Decimal(item["borrowed_usd"]), reverse=True)

    total_borrow = sum(Decimal(item["borrowed_usd"]) for item in attackers[:top])
    return {
        "source": str(VENUS_HISTORY_DIR),
        "oracle": {
            "feed": oracle["feed"],
            "last_update_tx": oracle["tx_hash"],
            "last_update_block": oracle["block_number"],
            "last_update_time": oracle["block_timestamp"],
            "answer": _decimal_string(oracle["answer"], places=8),
            "updated_at": oracle["updated_at"],
            "answer_updated_topic": ANSWER_UPDATED_TOPIC,
        },
        "window": {
            "start": _iso(start_time),
            "end": _iso(end_time),
        },
        "features": [
            "Chainlink LUNA/USD answer stopped near $0.107.",
            "Large LUNA mint/deposit events appear after the stale marker.",
            "The same accounts borrow BUSD shortly after LUNA deposits.",
            "Ranking by borrowed USD isolates two dominant accounts.",
        ],
        "attackers": attackers[:top],
        "top_total_borrowed_usd": _decimal_string(total_borrow),
    }


def _address_list_sql(addresses: Iterable[str]) -> str:
    values = [_norm_addr(address) for address in addresses if address]
    if not values:
        return "/* fill with 0x... addresses */"
    return ", ".join(values)


def _token_value_sql(tokens: List[Dict[str, Any]]) -> str:
    if not tokens:
        return "/* symbol, token_address, decimals */\n    ('USDC', 0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E, 6)"
    rows = []
    for token in tokens:
        rows.append(
            f"    ('{token['symbol']}', {_norm_addr(token['address'])}, {int(token['decimals'])})"
        )
    return ",\n".join(rows)


def render_dune_queries(
    start: str,
    end: str,
    min_luna: Decimal,
    luna_token: Optional[str],
    blizz_addresses: List[str],
    borrow_tokens: List[Dict[str, Any]],
) -> Dict[str, str]:
    start_dt = _parse_time(start)
    end_dt = _parse_time(end)
    start_sql = _iso(start_dt).replace("T", " ").replace("Z", "")
    end_sql = _iso(end_dt).replace("T", " ").replace("Z", "")
    start_date_sql = _iso(start_dt).split("T")[0]
    trace_end_date_sql = _iso(end_dt + timedelta(days=1)).split("T")[0]
    luna_filter = (
        f"AND t.contract_address = {_norm_addr(luna_token)}"
        if luna_token
        else "AND t.contract_address IN (SELECT contract_address FROM luna_tokens)"
    )

    discovery = f"""-- Discover Avalanche LUNA token candidates around the Blizz incident.
SELECT
  blockchain,
  contract_address,
  symbol,
  name,
  decimals
FROM tokens.erc20
WHERE blockchain IN ('avalanche', 'avalanche_c')
  AND (lower(symbol) LIKE '%luna%' OR lower(name) LIKE '%luna%')
ORDER BY symbol, contract_address;
"""

    contracts = """-- Discover Blizz-related Avalanche addresses. If labels are sparse, use this only
-- as a seed and fall back to the transfer graph query below.
SELECT
  blockchain,
  address,
  name,
  category
FROM labels.addresses
WHERE blockchain IN ('avalanche', 'avalanche_c')
  AND lower(name) LIKE '%blizz%'
ORDER BY address;
"""

    market_inventory = """-- Discover the full Blizz lending-market inventory from token metadata.
-- This intentionally keeps duplicate market versions such as bUSDC/bUSDT/bWETH.
WITH all_blizz_markets AS (
  SELECT
    contract_address AS market_address,
    symbol AS market_symbol,
    name AS market_name,
    decimals AS market_decimals
  FROM tokens.erc20
  WHERE blockchain = 'avalanche_c'
    AND lower(name) LIKE 'blizz %'
    AND lower(symbol) LIKE 'b%'
    AND lower(symbol) <> 'bliz'
    AND lower(symbol) <> 'blzz'
    AND lower(symbol) NOT LIKE 'variabledebt%'
    AND lower(symbol) NOT LIKE 'stabledebt%'
    AND lower(name) NOT LIKE '%variable debt%'
)
SELECT *
FROM all_blizz_markets
ORDER BY market_symbol, market_address;
"""

    candidates = f"""-- Venus-derived Blizz LUNA candidate search.
-- Read-only historical forensic query. It discovers Blizz bToken markets from metadata,
-- keeps all candidate accounts, and intentionally has no LIMIT.
WITH
params AS (
  SELECT
    TIMESTAMP '{start_sql}' AS start_time,
    TIMESTAMP '{end_sql}' AS end_time,
    CAST({min_luna} AS DOUBLE) AS min_luna_amount
),
luna_tokens AS (
  SELECT contract_address, decimals
  FROM tokens.erc20
  WHERE blockchain IN ('avalanche', 'avalanche_c')
    AND (lower(symbol) LIKE '%luna%' OR lower(name) LIKE '%luna%')
),
all_blizz_markets AS (
  SELECT
    contract_address AS market_address,
    symbol AS market_symbol,
    name AS market_name,
    decimals AS market_decimals
  FROM tokens.erc20
  WHERE blockchain = 'avalanche_c'
    AND lower(name) LIKE 'blizz %'
    AND lower(symbol) LIKE 'b%'
    AND lower(symbol) <> 'bliz'
    AND lower(symbol) <> 'blzz'
    AND lower(symbol) NOT LIKE 'variabledebt%'
    AND lower(symbol) NOT LIKE 'stabledebt%'
    AND lower(name) NOT LIKE '%variable debt%'
),
bluna_markets AS (
  SELECT *
  FROM all_blizz_markets
  WHERE lower(market_symbol) = 'bluna'
),
borrow_markets AS (
  SELECT *
  FROM all_blizz_markets
  WHERE lower(market_symbol) <> 'bluna'
),
luna_deposit_events AS (
  SELECT
    t.block_time,
    t.block_number,
    t.tx_hash,
    t."from" AS attacker,
    t."to" AS protocol_address,
    t.contract_address AS luna_token,
    t.amount AS luna_amount,
    t.amount_usd AS luna_amount_usd
  FROM tokens.transfers t, params p
  WHERE t.blockchain IN ('avalanche', 'avalanche_c')
    AND t.block_date BETWEEN DATE '{start_date_sql}' AND DATE '{trace_end_date_sql}'
    AND t.block_time >= p.start_time
    AND t.block_time < p.end_time
    {luna_filter}
    AND t."to" IN (SELECT market_address FROM bluna_markets)
    AND t.amount >= p.min_luna_amount
),
deposit_accounts AS (
  SELECT
    attacker,
    SUM(luna_amount) AS luna_deposit_amount,
    COUNT(DISTINCT tx_hash) AS luna_deposit_tx_count,
    ARRAY_AGG(DISTINCT tx_hash) AS luna_deposit_txs,
    MIN_BY(tx_hash, block_number) AS first_luna_deposit_tx,
    MIN(block_time) AS first_luna_deposit_time,
    MIN(block_number) AS first_luna_deposit_block,
    COUNT(DISTINCT protocol_address) AS bluna_market_count
  FROM luna_deposit_events
  GROUP BY attacker
),
erc20_borrow_outflows AS (
  SELECT
    t.block_time,
    t.block_number,
    t.tx_hash,
    t."to" AS attacker,
    t."from" AS protocol_address,
    bm.market_symbol AS source_market,
    t.contract_address AS borrow_token,
    tok.symbol AS borrow_symbol,
    t.amount AS borrow_amount,
    t.amount_usd AS borrow_amount_usd,
    CAST(t.amount_usd IS NULL AS BOOLEAN) AS missing_usd_price,
    CAST(false AS BOOLEAN) AS native_avax
  FROM tokens.transfers t
  JOIN borrow_markets bm ON t."from" = bm.market_address
  JOIN deposit_accounts d
    ON t."to" = d.attacker
   AND t.block_time >= d.first_luna_deposit_time
   AND t.block_time < d.first_luna_deposit_time + INTERVAL '6' HOUR
  LEFT JOIN tokens.erc20 tok
    ON tok.blockchain = t.blockchain
   AND tok.contract_address = t.contract_address
  WHERE t.blockchain IN ('avalanche', 'avalanche_c')
    AND t.block_date BETWEEN DATE '{start_date_sql}' AND DATE '{trace_end_date_sql}'
    AND t.contract_address NOT IN (SELECT DISTINCT luna_token FROM luna_deposit_events)
),
native_avax_outflows AS (
  SELECT
    tr.block_time,
    tr.block_number,
    tr.tx_hash,
    tr."to" AS attacker,
    tr."from" AS protocol_address,
    bm.market_symbol AS source_market,
    CAST(NULL AS varbinary) AS borrow_token,
    'AVAX' AS borrow_symbol,
    CAST(tr.value AS DOUBLE) / 1e18 AS borrow_amount,
    CAST(NULL AS DOUBLE) AS borrow_amount_usd,
    CAST(true AS BOOLEAN) AS missing_usd_price,
    CAST(true AS BOOLEAN) AS native_avax
  FROM avalanche_c.traces tr
  JOIN borrow_markets bm
    ON tr."from" = bm.market_address
   AND lower(bm.market_symbol) = 'bavax'
  JOIN deposit_accounts d
    ON tr."to" = d.attacker
   AND tr.block_time >= d.first_luna_deposit_time
   AND tr.block_time < d.first_luna_deposit_time + INTERVAL '6' HOUR
  WHERE tr.block_date BETWEEN DATE '{start_date_sql}' AND DATE '{trace_end_date_sql}'
    AND tr.success = true
    AND tr.value > UINT256 '0'
),
borrow_outflows AS (
  SELECT * FROM erc20_borrow_outflows
  UNION ALL
  SELECT * FROM native_avax_outflows
),
borrow_accounts AS (
  SELECT
    attacker,
    SUM(COALESCE(borrow_amount_usd, 0)) AS borrowed_usd_known,
    SUM(CASE WHEN missing_usd_price THEN 1 ELSE 0 END) AS borrowed_usd_missing_price_count,
    SUM(CASE WHEN native_avax THEN borrow_amount ELSE 0 END) AS native_avax_amount,
    COUNT(DISTINCT tx_hash) AS borrow_tx_count,
    ARRAY_AGG(DISTINCT tx_hash) FILTER (WHERE tx_hash IS NOT NULL) AS borrow_txs,
    MIN_BY(tx_hash, block_number) FILTER (WHERE tx_hash IS NOT NULL) AS first_borrow_tx,
    ARRAY_AGG(DISTINCT source_market) FILTER (WHERE source_market IS NOT NULL) AS source_markets,
    ARRAY_AGG(DISTINCT borrow_symbol) FILTER (WHERE borrow_symbol IS NOT NULL) AS borrowed_assets,
    MIN(block_time) AS first_borrow_time,
    MIN(block_number) AS first_borrow_block
  FROM borrow_outflows
  GROUP BY attacker
)
SELECT
  d.attacker,
  d.luna_deposit_amount,
  b.borrowed_usd_known,
  b.borrowed_usd_missing_price_count,
  b.native_avax_amount,
  d.luna_deposit_tx_count,
  b.borrow_tx_count,
  d.luna_deposit_txs,
  b.borrow_txs,
  d.first_luna_deposit_tx,
  b.first_borrow_tx,
  b.source_markets,
  b.borrowed_assets,
  d.first_luna_deposit_block,
  d.first_luna_deposit_time,
  b.first_borrow_block,
  b.first_borrow_time,
  d.bluna_market_count
FROM deposit_accounts d
JOIN borrow_accounts b ON d.attacker = b.attacker
ORDER BY b.borrowed_usd_known DESC, d.luna_deposit_amount DESC;
"""

    oracle = f"""-- Chainlink AnswerUpdated scan for the Avalanche LUNA/USD feed.
-- Set `feed_address` after resolving the historical LUNA/USD feed contract.
WITH params AS (
  SELECT
    TIMESTAMP '{start_sql}' AS start_time,
    TIMESTAMP '{end_sql}' AS end_time,
    /* feed_address */ 0x0000000000000000000000000000000000000000 AS feed_address
)
SELECT
  l.block_time,
  l.block_number,
  l.tx_hash,
  l.contract_address AS feed,
  bytearray_to_int256(l.topic1) / 1e8 AS answer,
  bytearray_to_uint256(l.topic2) AS round_id,
  bytearray_to_uint256(l.data) AS updated_at
FROM avalanche_c.logs l, params p
WHERE l.block_time >= p.start_time
  AND l.block_time < p.end_time
  AND l.contract_address = p.feed_address
  AND l.topic0 = {ANSWER_UPDATED_TOPIC}
ORDER BY l.block_number, l.index;
"""
    return {
        "01_discover_luna_tokens.sql": discovery,
        "02_discover_blizz_addresses.sql": contracts,
        "03_find_blizz_luna_candidates.sql": candidates,
        "04_find_luna_oracle_updates.sql": oracle,
        "05_discover_full_blizz_markets.sql": market_inventory,
    }


def write_dune_queries(queries: Dict[str, str]) -> List[Path]:
    sql_dir = repo_path("artifacts", "blizz_luna_locator", "sql")
    ensure_dir(sql_dir)
    paths = []
    for name, text in queries.items():
        path = sql_dir / name
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    return paths


def _block_number(result: Any) -> int:
    if isinstance(result, str):
        return int(result, 16)
    if isinstance(result, int):
        return result
    raise PipelineError(f"Unexpected block number result: {result!r}")


def _block_timestamp(rpc_url: str, block_number: int) -> int:
    block = rpc_call(rpc_url, "eth_getBlockByNumber", [hex(block_number), False])
    if not block:
        raise PipelineError(f"Missing block {block_number}")
    return int(block["timestamp"], 16)


def block_by_timestamp(rpc_url: str, target_timestamp: int) -> int:
    latest = _block_number(rpc_call(rpc_url, "eth_blockNumber", []))
    low, high = 0, latest
    while low < high:
        mid = (low + high) // 2
        if _block_timestamp(rpc_url, mid) < target_timestamp:
            low = mid + 1
        else:
            high = mid
    return low


def fetch_logs_paginated(
    rpc_url: str,
    address: Optional[str],
    topics: List[Optional[str]],
    from_block: int,
    to_block: int,
    step: int = 2048,
) -> List[Dict[str, Any]]:
    logs: List[Dict[str, Any]] = []
    current = from_block
    while current <= to_block:
        end = min(current + step - 1, to_block)
        params: Dict[str, Any] = {
            "fromBlock": hex(current),
            "toBlock": hex(end),
            "topics": topics,
        }
        if address:
            params["address"] = _norm_addr(address)
        chunk = rpc_call(rpc_url, "eth_getLogs", [params], timeout=60)
        logs.extend(chunk or [])
        current = end + 1
    return logs


def _decode_answer_updated_log(log: Dict[str, Any], decimals: int = 8) -> Dict[str, Any]:
    topics = log.get("topics") or []
    data_words = _words(log.get("data", ""))
    return {
        "feed": _norm_addr(log.get("address", "")),
        "tx_hash": log.get("transactionHash", ""),
        "block_number": int(log.get("blockNumber", "0x0"), 16),
        "transaction_index": int(log.get("transactionIndex", "0x0"), 16),
        "log_index": int(log.get("logIndex", "0x0"), 16),
        "answer_raw": _hex_to_int256(topics[1]) if len(topics) > 1 else 0,
        "answer": _decimal_amount(_hex_to_int256(topics[1]), decimals) if len(topics) > 1 else Decimal(0),
        "round_id": _hex_to_uint(topics[2]) if len(topics) > 2 else 0,
        "updated_at": _word_to_uint(data_words[0]) if data_words else 0,
    }


def _decode_transfer_log(log: Dict[str, Any], decimals: int, symbol: str) -> Dict[str, Any]:
    topics = log.get("topics") or []
    return {
        "token": _norm_addr(log.get("address", "")),
        "symbol": symbol,
        "tx_hash": log.get("transactionHash", ""),
        "block_number": int(log.get("blockNumber", "0x0"), 16),
        "transaction_index": int(log.get("transactionIndex", "0x0"), 16),
        "log_index": int(log.get("logIndex", "0x0"), 16),
        "from": _topic_address(topics[1]) if len(topics) > 1 else "",
        "to": _topic_address(topics[2]) if len(topics) > 2 else "",
        "amount_raw": _hex_to_uint(log.get("data", "0x0")),
        "amount": _decimal_amount(_hex_to_uint(log.get("data", "0x0")), decimals),
    }


def locate_with_alchemy(
    start: str,
    end: str,
    luna_token: str,
    luna_feed: str,
    blizz_addresses: List[str],
    borrow_tokens: List[Dict[str, Any]],
    min_luna: Decimal,
) -> Dict[str, Any]:
    if not luna_token or not luna_feed or not blizz_addresses:
        raise PipelineError(
            "Alchemy scan requires --luna-token, --luna-feed and at least one --blizz-address."
        )
    env = load_env()
    case = get_case("blizz_luna")
    rpc_url = resolve_template(case["rpc_url_template"], env)
    start_dt = _parse_time(start)
    end_dt = _parse_time(end)
    print_status("Resolving Avalanche block window from timestamps.")
    from_block = block_by_timestamp(rpc_url, int(start_dt.timestamp()))
    to_block = block_by_timestamp(rpc_url, int(end_dt.timestamp()))

    print_status(f"Fetching AnswerUpdated logs for LUNA feed {luna_feed}.")
    answer_logs = fetch_logs_paginated(
        rpc_url,
        luna_feed,
        [ANSWER_UPDATED_TOPIC],
        max(0, from_block - 20000),
        to_block,
    )
    answers = [_decode_answer_updated_log(log) for log in answer_logs]
    stale_answer = answers[-1] if answers else None

    protocol_addresses = {_norm_addr(address) for address in blizz_addresses}
    deposits: List[Dict[str, Any]] = []
    for protocol_address in sorted(protocol_addresses):
        print_status(f"Scanning LUNA transfers into Blizz address {protocol_address}.")
        logs = fetch_logs_paginated(
            rpc_url,
            luna_token,
            [ERC20_TRANSFER_TOPIC, None, _topic_from_address(protocol_address)],
            from_block,
            to_block,
        )
        for log in logs:
            decoded = _decode_transfer_log(log, decimals=18, symbol="LUNA")
            if decoded["amount"] >= min_luna:
                deposits.append(decoded)

    attackers = {_norm_addr(item["from"]) for item in deposits}
    borrows: List[Dict[str, Any]] = []
    for token in borrow_tokens:
        for attacker in sorted(attackers):
            print_status(f"Scanning {token['symbol']} outflows to {attacker}.")
            logs = fetch_logs_paginated(
                rpc_url,
                token["address"],
                [ERC20_TRANSFER_TOPIC, None, _topic_from_address(attacker)],
                from_block,
                min(to_block + 2000, _block_number(rpc_call(rpc_url, "eth_blockNumber", []))),
            )
            for log in logs:
                decoded = _decode_transfer_log(log, int(token["decimals"]), token["symbol"])
                if _norm_addr(decoded["from"]) in protocol_addresses:
                    borrows.append(decoded)

    grouped: DefaultDict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "address": "",
            "luna_deposit": Decimal(0),
            "borrowed_assets": set(),
            "borrow_count": 0,
            "deposit_tx_hashes": set(),
            "borrow_tx_hashes": set(),
        }
    )
    for deposit in deposits:
        account = _norm_addr(deposit["from"])
        entry = grouped[account]
        entry["address"] = account
        entry["luna_deposit"] += deposit["amount"]
        entry["deposit_tx_hashes"].add(deposit["tx_hash"])
    for borrow in borrows:
        account = _norm_addr(borrow["to"])
        entry = grouped[account]
        entry["address"] = account
        entry["borrowed_assets"].add(borrow["symbol"])
        entry["borrow_count"] += 1
        entry["borrow_tx_hashes"].add(borrow["tx_hash"])

    candidates = []
    for entry in grouped.values():
        if not entry["borrow_tx_hashes"]:
            continue
        candidates.append(
            {
                "address": entry["address"],
                "luna_deposit": _decimal_string(entry["luna_deposit"]),
                "borrowed_assets": sorted(entry["borrowed_assets"]),
                "borrow_tx_count": entry["borrow_count"],
                "deposit_tx_hashes": sorted(entry["deposit_tx_hashes"]),
                "borrow_tx_hashes": sorted(entry["borrow_tx_hashes"]),
            }
        )
    candidates.sort(key=lambda item: (item["borrow_tx_count"], Decimal(item["luna_deposit"])), reverse=True)

    return {
        "window": {
            "start": _iso(start_dt),
            "end": _iso(end_dt),
            "from_block": from_block,
            "to_block": to_block,
        },
        "stale_oracle": stale_answer,
        "deposit_logs": deposits,
        "borrow_logs": borrows,
        "candidates": candidates,
    }


def build_trace_records(scan: Dict[str, Any]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    stale = scan.get("stale_oracle")
    if stale:
        records.append(
            {
                "case": "blizz_luna",
                "event_type": "STALE_ORACLE_START",
                "block_number": stale["block_number"],
                "block_timestamp": stale.get("updated_at"),
                "transaction_index": stale.get("transaction_index", 0),
                "log_index": stale.get("log_index", 0),
                "tx_hash": stale["tx_hash"],
                "address": stale["feed"],
                "decoded": {
                    "asset": "LUNA",
                    "feed": stale["feed"],
                    "answer": _decimal_string(stale["answer"], places=8),
                    "updated_at": stale.get("updated_at"),
                    "reason": "chainlink_answer_stopped_near_lower_bound",
                },
            }
        )
    for deposit in scan.get("deposit_logs", []):
        records.append(
            {
                "case": "blizz_luna",
                "event_type": "SUPPLY",
                "block_number": deposit["block_number"],
                "transaction_index": deposit["transaction_index"],
                "log_index": deposit["log_index"],
                "tx_hash": deposit["tx_hash"],
                "address": deposit["token"],
                "decoded": {
                    "supplier": deposit["from"],
                    "asset": "LUNA",
                    "amount": _decimal_string(deposit["amount"]),
                    "receiver": deposit["to"],
                },
            }
        )
    for borrow in scan.get("borrow_logs", []):
        records.append(
            {
                "case": "blizz_luna",
                "event_type": "BORROW",
                "block_number": borrow["block_number"],
                "transaction_index": borrow["transaction_index"],
                "log_index": borrow["log_index"],
                "tx_hash": borrow["tx_hash"],
                "address": borrow["token"],
                "decoded": {
                    "borrower": borrow["to"],
                    "collateral_asset": "LUNA",
                    "borrow_asset": borrow["symbol"],
                    "borrow_amount": _decimal_string(borrow["amount"]),
                    "source": borrow["from"],
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


def build_trace_records_from_dune_candidates(
    candidates: List[Dict[str, Any]],
    dune_findings: Dict[str, Any],
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    feed = (dune_findings.get("identified_contracts", {}) or {}).get("luna_usd_feed_candidate", {})
    if feed:
        updated_at = int(_parse_time(str(feed.get("last_update_time"))).timestamp()) if feed.get("last_update_time") else 0
        records.append(
            {
                "case": "blizz_luna",
                "event_type": "STALE_ORACLE_START",
                "block_number": int(feed.get("last_update_block") or 0),
                "block_timestamp": updated_at,
                "transaction_index": 0,
                "log_index": 0,
                "tx_hash": feed.get("last_update_tx", ""),
                "address": feed.get("address", ""),
                "decoded": {
                    "asset": "LUNA",
                    "feed": feed.get("address", ""),
                    "answer": str(feed.get("last_answer", "")),
                    "updated_at": updated_at,
                    "reason": "chainlink_answer_stopped_near_lower_bound",
                },
            }
        )

    token = (dune_findings.get("identified_contracts", {}) or {}).get("luna_token", {})
    bluna = (dune_findings.get("identified_contracts", {}) or {}).get("bluna_market", {})
    for index, candidate in enumerate(candidates, start=1):
        deposit_txs = candidate.get("luna_deposit_txs") or []
        borrow_txs = candidate.get("borrow_txs") or []
        first_deposit_tx = candidate.get("first_luna_deposit_tx") or (deposit_txs[0] if deposit_txs else "")
        first_borrow_tx = candidate.get("first_borrow_tx") or (borrow_txs[0] if borrow_txs else "")
        deposit_block = int(candidate.get("first_luna_deposit_block") or 0)
        borrow_block = int(candidate.get("first_borrow_block") or deposit_block)
        address = candidate.get("address") or candidate.get("attacker") or ""
        source_markets = candidate.get("source_markets") or []
        borrowed_assets = candidate.get("borrowed_assets") or []
        borrowed_usd = str(candidate.get("borrowed_usd_known", ""))

        records.append(
            {
                "case": "blizz_luna",
                "event_type": "SUPPLY",
                "block_number": deposit_block,
                "transaction_index": 0,
                "log_index": index * 2,
                "tx_hash": first_deposit_tx,
                "address": token.get("address", ""),
                "decoded": {
                    "supplier": address,
                    "asset": "LUNA",
                    "amount": str(candidate.get("luna_deposit_amount", "")),
                    "receiver": bluna.get("address", ""),
                    "all_deposit_txs": deposit_txs,
                    "source": "dune_full_market_candidates",
                },
            }
        )
        records.append(
            {
                "case": "blizz_luna",
                "event_type": "BORROW",
                "block_number": borrow_block,
                "transaction_index": 1,
                "log_index": index * 2 + 1,
                "tx_hash": first_borrow_tx,
                "address": "dune:blizz_borrow_markets",
                "decoded": {
                    "borrower": address,
                    "collateral_asset": "LUNA",
                    "borrow_asset": ", ".join(borrowed_assets),
                    "borrow_amount": borrowed_usd,
                    "borrow_amount_usd": borrowed_usd,
                    "borrowed_assets": borrowed_assets,
                    "source_markets": source_markets,
                    "all_borrow_txs": borrow_txs,
                    "missing_usd_price_count": candidate.get("borrowed_usd_missing_price_count", 0),
                    "native_avax_amount": candidate.get("native_avax_amount", 0),
                    "source": "dune_full_market_candidates",
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


def materialize_dune_trace_from_artifacts() -> Path:
    findings = load_optional_dune_findings()
    if not findings:
        raise PipelineError("Missing artifacts/blizz_luna_locator/dune_findings.json.")
    candidates_path = repo_path("artifacts", "blizz_luna_locator", "dune_candidates_full.jsonl")
    candidates = read_jsonl(candidates_path)
    trace_path = repo_path("artifacts", "log_trace", "blizz_luna.jsonl")
    write_jsonl(trace_path, build_trace_records_from_dune_candidates(candidates, findings))
    return trace_path


def _parse_borrow_token_specs(specs: List[str]) -> List[Dict[str, Any]]:
    if not specs:
        return list(DEFAULT_AVALANCHE_BORROW_TOKENS)
    tokens = []
    for spec in specs:
        parts = spec.split(":")
        if len(parts) != 3:
            raise PipelineError("--borrow-token must use SYMBOL:ADDRESS:DECIMALS")
        tokens.append({"symbol": parts[0], "address": parts[1], "decimals": int(parts[2])})
    return tokens


def render_report(
    venus: Dict[str, Any],
    sql_paths: List[Path],
    env_summary: Dict[str, bool],
    scan: Optional[Dict[str, Any]],
    executed_alchemy: bool,
    dune_findings: Optional[Dict[str, Any]] = None,
) -> str:
    lines = [
        "# Blizz LUNA Attack Locator",
        "",
        "## Safety scope",
        "",
        "- Scope: read-only historical incident detection and forensic reporting.",
        "- The locator queries archived public chain data and writes evidence artifacts only.",
        "- It does not submit transactions, deploy contracts, call protocol write methods, handle private keys, or generate exploit execution steps.",
        "",
        "## Venus-derived signal",
        "",
        f"- LUNA/USD feed: `{venus['oracle']['feed']}`",
        f"- Last Venus update: block `{venus['oracle']['last_update_block']}`, tx `{venus['oracle']['last_update_tx']}`, answer `${venus['oracle']['answer']}`",
        f"- Reference window: `{venus['window']['start']}` to `{venus['window']['end']}`",
        f"- Top reference borrow total: `${venus['top_total_borrowed_usd']}` BUSD",
        "",
        "Top Venus reference accounts:",
    ]
    for attacker in venus["attackers"]:
        lines.append(
            f"- `{attacker['address']}` deposited `{attacker['luna_deposit']}` LUNA, borrowed `${attacker['borrowed_usd']}` BUSD"
        )
        lines.append(f"  - deposit tx: `{attacker['first_deposit_tx']}`")
        lines.append(f"  - first borrow tx: `{attacker['first_borrow_tx']}`")
        lines.append(f"  - largest borrow tx: `{attacker['largest_borrow_tx']}`")

    lines.extend(
        [
            "",
            "## Data-source status",
            "",
            f"- `ALCHEMY_KEY`: `{'present' if env_summary.get('ALCHEMY_KEY') else 'missing'}`",
            f"- `ETHERSCAN_KEY`: `{'present' if env_summary.get('ETHERSCAN_KEY') else 'missing'}`",
            f"- `DUNE_MCP_KEY`: `{'present' if env_summary.get('DUNE_MCP_KEY') else 'missing'}`",
            "",
            "## Dune coarse-screen queries",
            "",
        ]
    )
    for path in sql_paths:
        lines.append(f"- `{path}`")

    if dune_findings:
        contracts = dune_findings.get("identified_contracts", {})
        summary = dune_findings.get("summary", {})
        full_artifacts = dune_findings.get("full_artifacts", {})
        feed = contracts.get("luna_usd_feed_candidate", {})
        token = contracts.get("luna_token", {})
        bluna = contracts.get("bluna_market", {})
        lines.extend(["", "## Dune-confirmed historical findings", ""])
        if token:
            lines.append(
                f"- LUNA token: `{token.get('address')}` ({token.get('name')}, decimals `{token.get('decimals')}`)"
            )
        if bluna:
            lines.append(f"- Blizz bLUNA market: `{bluna.get('address')}`")
        if feed:
            lines.append(
                f"- LUNA/USD stale marker: feed `{feed.get('address')}`, tx `{feed.get('last_update_tx')}`, block `{feed.get('last_update_block')}`, answer `${feed.get('last_answer')}`"
            )
        if summary:
            borrowed_known = _as_decimal(summary.get("borrowed_usd_known"))
            public_gap = PUBLIC_BLIZZ_LOSS_USD - borrowed_known
            coverage = borrowed_known / PUBLIC_BLIZZ_LOSS_USD * Decimal(100) if PUBLIC_BLIZZ_LOSS_USD else Decimal(0)
            lines.extend(
                [
                    "",
                    "## Full-market coverage",
                    "",
                    f"- Blizz lending markets: `{summary.get('market_count', 0)}` total, `{summary.get('bluna_market_count', 0)}` bLUNA, `{summary.get('borrow_market_count', 0)}` borrow markets.",
                    f"- Full candidate accounts: `{summary.get('candidate_count', 0)}`.",
                    f"- Full evidence counts: `{summary.get('deposit_tx_count', 0)}` LUNA deposit tx, `{summary.get('borrow_tx_count', 0)}` borrow tx.",
                    f"- Known borrowed USD: `${_decimal_string(borrowed_known)}` vs public Blizz loss `${_decimal_string(PUBLIC_BLIZZ_LOSS_USD)}`; coverage `{_decimal_string(coverage, places=2)}%`, gap `${_decimal_string(public_gap)}`.",
                    f"- SlowMist comparison point: `${_decimal_string(SLOWMIST_BLIZZ_LOSS_USD)}`.",
                    f"- Missing USD price borrow events: `{summary.get('borrowed_usd_missing_price_count', 0)}`; raw token amounts remain in full artifacts.",
                ]
            )
            if full_artifacts:
                lines.append(
                    f"- Full candidates JSONL: `{full_artifacts.get('candidates_jsonl', 'artifacts/blizz_luna_locator/dune_candidates_full.jsonl')}`."
                )
        lines.append("- Top historical candidate accounts from Dune preview:")
        for candidate in dune_findings.get("top_candidates", [])[:5]:
            assets = ", ".join(candidate.get("borrowed_assets", []))
            lines.append(
                f"  - `{candidate['address']}` deposited `{candidate['luna_deposit_amount']}` LUNA and borrowed about `${candidate.get('borrowed_usd_known', candidate.get('borrowed_usd'))}` across `{assets}`"
            )
            for tx_hash in candidate.get("borrow_txs", [])[:4]:
                lines.append(f"    - borrow tx: `{tx_hash}`")

    lines.extend(["", "## Blizz candidate status", ""])
    if not executed_alchemy:
        lines.append(
            "- Alchemy verification was not executed. Provide `--luna-token`, `--luna-feed`, one or more `--blizz-address`, and `--execute-alchemy` after Dune resolves the Blizz address set."
        )
        lines.append(
            "- No synthetic Blizz transaction hashes were written by this locator. Existing fixture traces remain only for pipeline tests."
        )
    elif scan and scan.get("candidates"):
        lines.append(
            f"- Alchemy window: blocks `{scan['window']['from_block']}` to `{scan['window']['to_block']}`."
        )
        stale = scan.get("stale_oracle")
        if stale:
            lines.append(
                f"- Stale oracle marker: tx `{stale['tx_hash']}`, block `{stale['block_number']}`, answer `${_decimal_string(stale['answer'], places=8)}`."
            )
        for candidate in scan["candidates"]:
            lines.append(
                f"- `{candidate['address']}` deposited `{candidate['luna_deposit']}` LUNA, borrow tx count `{candidate['borrow_tx_count']}`, assets `{', '.join(candidate['borrowed_assets'])}`"
            )
            lines.append(
                "  - LUNA deposit txs: "
                + ", ".join(f"`{tx}`" for tx in candidate["deposit_tx_hashes"][:5])
            )
            lines.append(
                "  - borrow txs: " + ", ".join(f"`{tx}`" for tx in candidate["borrow_tx_hashes"][:8])
            )
    else:
        lines.append("- Alchemy verification ran, but no account matched `large LUNA deposit -> protocol asset outflow`.")
    lines.append("")
    return "\n".join(lines)


def load_optional_dune_findings() -> Optional[Dict[str, Any]]:
    path = repo_path("artifacts", "blizz_luna_locator", "dune_findings.json")
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _as_decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal(0)
    return Decimal(str(value))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Locate Blizz Finance LUNA attack candidates using Venus-derived stale-oracle features."
    )
    parser.add_argument("--start", default=DEFAULT_START, help="Blizz search start timestamp, UTC ISO-8601.")
    parser.add_argument("--end", default=DEFAULT_END, help="Blizz search end timestamp, UTC ISO-8601.")
    parser.add_argument("--venus-end", default=DEFAULT_VENUS_END, help="End timestamp for local Venus reference extraction.")
    parser.add_argument("--min-luna", default="1000000", help="Minimum LUNA deposit amount for candidate screening.")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--luna-token", default="", help="Avalanche LUNA ERC20 address for Alchemy verification.")
    parser.add_argument("--luna-feed", default="", help="Avalanche Chainlink LUNA/USD feed address.")
    parser.add_argument("--blizz-address", action="append", default=[], help="Blizz pool/reserve/aToken address.")
    parser.add_argument(
        "--borrow-token",
        action="append",
        default=[],
        help="Borrow token in SYMBOL:ADDRESS:DECIMALS form. Defaults to major Avalanche assets.",
    )
    parser.add_argument(
        "--execute-alchemy",
        action="store_true",
        help="Run Avalanche RPC verification. Without this flag the script writes Venus features and Dune SQL only.",
    )
    parser.add_argument(
        "--materialize-dune-trace",
        action="store_true",
        help="Build artifacts/log_trace/blizz_luna.jsonl from the full Dune candidate artifact.",
    )
    args = parser.parse_args()

    try:
        min_luna = _parse_decimal(args.min_luna)
        borrow_tokens = _parse_borrow_token_specs(args.borrow_token)
        venus = extract_venus_reference(top=args.top, end=args.venus_end)
        write_json(repo_path("artifacts", "blizz_luna_locator", "venus_reference.json"), venus)

        queries = render_dune_queries(
            start=args.start,
            end=args.end,
            min_luna=min_luna,
            luna_token=args.luna_token or None,
            blizz_addresses=args.blizz_address,
            borrow_tokens=borrow_tokens,
        )
        sql_paths = write_dune_queries(queries)

        scan: Optional[Dict[str, Any]] = None
        if args.execute_alchemy:
            scan = locate_with_alchemy(
                start=args.start,
                end=args.end,
                luna_token=args.luna_token,
                luna_feed=args.luna_feed,
                blizz_addresses=args.blizz_address,
                borrow_tokens=borrow_tokens,
                min_luna=min_luna,
            )
            serializable_scan = _json_safe(scan)
            write_json(repo_path("artifacts", "blizz_luna_locator", "alchemy_scan.json"), serializable_scan)
            if scan.get("candidates"):
                trace_records = build_trace_records(scan)
                write_jsonl(repo_path("artifacts", "log_trace", "blizz_luna.jsonl"), trace_records)

        env = load_env()
        report = render_report(
            venus=venus,
            sql_paths=sql_paths,
            env_summary={key: bool(env.get(key)) for key in ("ALCHEMY_KEY", "ETHERSCAN_KEY", "DUNE_MCP_KEY")},
            scan=scan,
            executed_alchemy=args.execute_alchemy,
            dune_findings=load_optional_dune_findings(),
        )
        report_path = repo_path("results", "blizz_luna_locator.md")
        ensure_dir(report_path.parent)
        report_path.write_text(report, encoding="utf-8")
        trace_path: Optional[Path] = None
        if args.materialize_dune_trace:
            trace_path = materialize_dune_trace_from_artifacts()
    except PipelineError as exc:
        raise SystemExit(str(exc)) from exc

    print(f"Wrote locator report: {report_path}")
    if trace_path:
        print(f"Wrote full Dune replay trace: {trace_path}")
    print("Wrote Dune SQL:")
    for path in sql_paths:
        print(f"- {path}")


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _decimal_string(value)
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


if __name__ == "__main__":
    main()
