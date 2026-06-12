#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from common import PipelineError, ensure_dir, load_env, read_json, repo_path, write_json
from run_broad_dune_queries import (
    _execute_sql,
    _fetch_all_rows,
    _poll_execution,
    _write_rows_csv,
    _write_rows_json,
)


DEFAULT_START = "2022-01-01"
DEFAULT_END = "2026-05-12"
DEFAULT_CHAINS = "ethereum,bsc,base,avalanche_c"
DEFAULT_RULES = "feed_binding_failure,price_composition_failure,freshness_handling_failure"
DEFAULT_QUERY_TYPES = "raw_count,rule_count,case_hit"
OUTPUT_DIR = repo_path("artifacts", "broad_search", "case_coverage")

CHAIN_ALIASES = {
    "bsc": "bnb",
    "bnb": "bnb",
    "avalanche": "avalanche_c",
    "avalanche_c": "avalanche_c",
    "eth": "ethereum",
}
DISPLAY_CHAIN = {
    "bnb": "bsc",
    "avalanche_c": "avalanche",
}
BROAD_CLASS_ALIASES = {
    "price_semantics_mismatch": "price_composition_failure",
}


@dataclass(frozen=True)
class CoverageShard:
    shard_id: str
    query_type: str
    chain: str
    start: str
    end: str
    failure_class: str = ""


def _date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _year_windows(start: str, end: str) -> List[tuple[str, str]]:
    start_date = _date(start)
    end_date = _date(end)
    if end_date < start_date:
        raise PipelineError(f"End date {end} is earlier than start date {start}")
    windows: List[tuple[str, str]] = []
    current = start_date
    while current <= end_date:
        year_end = date(current.year, 12, 31)
        window_end = min(year_end, end_date)
        windows.append((current.isoformat(), window_end.isoformat()))
        current = window_end + date.resolution
    return windows


def _sql_string(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _tx_literal(tx_hash: str) -> str:
    value = tx_hash.lower()
    if not _valid_tx_hash(value):
        raise PipelineError(f"Invalid transaction hash for Dune VALUES literal: {tx_hash}")
    return value


def _valid_tx_hash(value: Any) -> bool:
    text = str(value or "").lower()
    return len(text) == 66 and text.startswith("0x") and all(ch in "0123456789abcdef" for ch in text[2:])


def normalize_chain(value: str) -> str:
    return CHAIN_ALIASES.get(value.strip().lower(), value.strip().lower())


def display_chain(value: str) -> str:
    return DISPLAY_CHAIN.get(value, value)


def parse_csv(value: str | Iterable[str]) -> List[str]:
    if isinstance(value, str):
        raw = value.split(",")
    else:
        raw = list(value)
    items: List[str] = []
    for item in raw:
        normalized = normalize_chain(str(item))
        if normalized and normalized not in items:
            items.append(normalized)
    return items


def broad_failure_class(failure_class: str) -> str:
    return BROAD_CLASS_ALIASES.get(failure_class, failure_class)


def _read_trace(case_id: str) -> List[Dict[str, Any]]:
    path = repo_path("artifacts", "log_trace", f"{case_id}.jsonl")
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _active_manifest_cases(chains: Iterable[str]) -> List[Dict[str, Any]]:
    active_cases = set(read_json(repo_path("config", "cases.json")).keys())
    chain_filter = set(chains)
    manifest = read_json(repo_path("artifacts", "dataset_manifest.json"))
    cases = []
    for case in manifest.get("cases", []):
        case_id = case.get("case", "")
        chain = normalize_chain(case.get("chain", ""))
        if case_id in active_cases and chain in chain_filter:
            item = dict(case)
            item["dune_chain"] = chain
            item["display_chain"] = display_chain(chain)
            item["broad_failure_class"] = broad_failure_class(item.get("failure_class", ""))
            cases.append(item)
    return cases


def build_attack_tx_manifest(chains: Iterable[str]) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    cases = _active_manifest_cases(chains)
    for case in cases:
        case_id = case["case"]
        impact_events = set(case.get("impact_events") or [])
        seen: set[str] = set()
        for record in _read_trace(case_id):
            tx_hash = str(record.get("tx_hash") or "").lower()
            if record.get("event_type") not in impact_events or not _valid_tx_hash(tx_hash) or tx_hash in seen:
                continue
            timestamp = int(record.get("block_timestamp") or 0)
            rows.append(
                {
                    "case_id": case_id,
                    "case_name": case.get("name", ""),
                    "chain": case["dune_chain"],
                    "display_chain": case["display_chain"],
                    "original_failure_class": case.get("failure_class", ""),
                    "broad_failure_class": case["broad_failure_class"],
                    "event_type": record.get("event_type", ""),
                    "tx_hash": tx_hash,
                    "block_number_local": int(record.get("block_number") or 0),
                    "block_timestamp_local": timestamp,
                    "year_local": datetime.fromtimestamp(timestamp or 0, timezone.utc).year,
                }
            )
            seen.add(tx_hash)
    by_case: Dict[str, int] = {}
    by_chain: Dict[str, int] = {}
    by_broad_class: Dict[str, int] = {}
    for row in rows:
        by_case[row["case_id"]] = by_case.get(row["case_id"], 0) + 1
        by_chain[row["display_chain"]] = by_chain.get(row["display_chain"], 0) + 1
        by_broad_class[row["broad_failure_class"]] = by_broad_class.get(row["broad_failure_class"], 0) + 1
    return {
        "dataset": "case_attack_tx_manifest",
        "active_case_count": len(cases),
        "attack_tx_count": len(rows),
        "chains": sorted({case["display_chain"] for case in cases}),
        "dune_chains": sorted({case["dune_chain"] for case in cases}),
        "cases": [
            {
                "case_id": case["case"],
                "name": case.get("name", ""),
                "chain": case["display_chain"],
                "original_failure_class": case.get("failure_class", ""),
                "broad_failure_class": case["broad_failure_class"],
            }
            for case in cases
        ],
        "by_case": dict(sorted(by_case.items())),
        "by_chain": dict(sorted(by_chain.items())),
        "by_broad_failure_class": dict(sorted(by_broad_class.items())),
        "attack_txs": rows,
    }


def raw_count_sql(chain: str, start: str, end: str) -> str:
    return f"""-- Dune Broad Search raw coverage count.
-- Counts only remote index rows; no receipt/log materialization is performed.
WITH tx_counts AS (
  SELECT
    blockchain AS chain,
    year(block_time) AS block_year,
    COUNT(*) AS tx_count,
    approx_distinct("to") AS unique_tx_to_contract_count
  FROM evms.transactions
  WHERE blockchain = {_sql_string(chain)}
    AND block_date BETWEEN DATE {_sql_string(start)} AND DATE {_sql_string(end)}
  GROUP BY 1, 2
),
log_counts AS (
  SELECT
    blockchain AS chain,
    year(block_time) AS block_year,
    COUNT(*) AS log_count,
    approx_distinct(contract_address) AS unique_log_contract_count
  FROM evms.logs
  WHERE blockchain = {_sql_string(chain)}
    AND block_date BETWEEN DATE {_sql_string(start)} AND DATE {_sql_string(end)}
  GROUP BY 1, 2
)
SELECT
  COALESCE(tx_counts.chain, log_counts.chain) AS chain,
  COALESCE(tx_counts.block_year, log_counts.block_year) AS year,
  COALESCE(tx_count, 0) AS tx_count,
  COALESCE(log_count, 0) AS log_count,
  GREATEST(COALESCE(unique_tx_to_contract_count, 0), COALESCE(unique_log_contract_count, 0)) AS unique_contract_count,
  'raw_index_coverage' AS coverage_layer
FROM tx_counts
FULL OUTER JOIN log_counts
  ON log_counts.chain = tx_counts.chain
 AND log_counts.block_year = tx_counts.block_year
ORDER BY chain, year
"""


def rule_count_sql(chain: str, start: str, end: str, failure_class: str) -> str:
    if failure_class == "feed_binding_failure":
        return _feed_binding_rule_count_sql(chain, start, end)
    if failure_class == "price_composition_failure":
        return _price_composition_rule_count_sql(chain, start, end)
    if failure_class == "freshness_handling_failure":
        return _freshness_rule_count_sql(chain, start, end)
    raise PipelineError(f"Unknown coverage failure class: {failure_class}")


def _suspicious_count_select(failure_class: str, source_cte: str) -> str:
    return f"""SELECT
  chain,
  block_year AS year,
  {_sql_string(failure_class)} AS failure_class,
  COUNT(DISTINCT tx_hash) AS suspicious_tx_count,
  COUNT(DISTINCT log_key) AS suspicious_log_count,
  approx_distinct(actor) AS candidate_actor_count,
  approx_distinct(market_contract) AS candidate_market_count,
  'rule_suspicious_coverage' AS coverage_layer
FROM {source_cte}
GROUP BY 1, 2, 3
ORDER BY chain, year, failure_class
"""


def _feed_binding_rule_count_sql(chain: str, start: str, end: str) -> str:
    return f"""-- R1 rule-suspicious yearly count: feed-binding evidence closure surface.
WITH lending_markets AS (
  SELECT DISTINCT
    blockchain,
    contract_address AS market_contract
  FROM tokens.erc20
  WHERE blockchain = {_sql_string(chain)}
    AND regexp_like(lower(COALESCE(symbol, '') || ' ' || COALESCE(name, '')), '(aave|compound|venus|moonwell|blizz|ploutos|benqi|morpho|radiant|silo|granary|lodestar|geist|cream|euler|^c[a-z0-9]+|^v[a-z0-9]+|^m[a-z0-9]+|^b[a-z0-9]+|^a[a-z0-9]+)')
),
decoded_binding_or_impact AS (
  SELECT
    tx.blockchain AS chain,
    year(tx.block_time) AS block_year,
    tx.hash AS tx_hash,
    tx."from" AS actor,
    tx."to" AS market_contract,
    CAST(NULL AS varchar) AS log_key
  FROM evms.transactions tx
  JOIN evms.traces_decoded td
    ON td.blockchain = tx.blockchain
   AND td.tx_hash = tx.hash
   AND td.block_date BETWEEN DATE {_sql_string(start)} AND DATE {_sql_string(end)}
  LEFT JOIN lending_markets lm
    ON lm.blockchain = tx.blockchain
   AND lm.market_contract = tx."to"
  WHERE tx.blockchain = {_sql_string(chain)}
    AND tx.block_date BETWEEN DATE {_sql_string(start)} AND DATE {_sql_string(end)}
    AND tx.success = true
    AND (
      regexp_like(lower(COALESCE(td.function_name, '')), '(oracle|price|feed|source|aggregator|asset|underlying)')
      OR (
        lm.market_contract IS NOT NULL
        AND regexp_like(lower(COALESCE(td.function_name, '')), '(borrow|mint|supply|deposit|liquidat)')
      )
    )
),
log_support AS (
  SELECT
    d.chain,
    d.block_year,
    d.tx_hash,
    d.actor,
    d.market_contract,
    CAST(l.tx_hash AS varchar) || ':' || CAST(l.index AS varchar) AS log_key
  FROM decoded_binding_or_impact d
  LEFT JOIN evms.logs l
    ON l.blockchain = d.chain
   AND l.tx_hash = d.tx_hash
   AND l.block_date BETWEEN DATE {_sql_string(start)} AND DATE {_sql_string(end)}
)
{_suspicious_count_select("feed_binding_failure", "log_support")}"""


def _price_composition_rule_count_sql(chain: str, start: str, end: str) -> str:
    return f"""-- R2 rule-suspicious yearly count: price-composition and price-semantics surface.
WITH derivative_or_oracle_txs AS (
  SELECT
    tx.blockchain AS chain,
    year(tx.block_time) AS block_year,
    tx.hash AS tx_hash,
    tx."from" AS actor,
    tx."to" AS market_contract,
    CAST(NULL AS varchar) AS log_key
  FROM evms.transactions tx
  LEFT JOIN evms.traces_decoded td
    ON td.blockchain = tx.blockchain
   AND td.tx_hash = tx.hash
   AND td.block_date BETWEEN DATE {_sql_string(start)} AND DATE {_sql_string(end)}
  WHERE tx.blockchain = {_sql_string(chain)}
    AND tx.block_date BETWEEN DATE {_sql_string(start)} AND DATE {_sql_string(end)}
    AND tx.success = true
    AND regexp_like(
      lower(COALESCE(td.function_name, '') || ' ' || to_hex(tx.data)),
      '(oracle|price|feed|source|ratio|rate|exchange|wrapper|govern|execute|cbeth|wsteth|wrseth|reth|ohm)'
    )
),
log_support AS (
  SELECT
    d.chain,
    d.block_year,
    d.tx_hash,
    d.actor,
    d.market_contract,
    CAST(l.tx_hash AS varchar) || ':' || CAST(l.index AS varchar) AS log_key
  FROM derivative_or_oracle_txs d
  LEFT JOIN evms.logs l
    ON l.blockchain = d.chain
   AND l.tx_hash = d.tx_hash
   AND l.block_date BETWEEN DATE {_sql_string(start)} AND DATE {_sql_string(end)}
)
{_suspicious_count_select("price_composition_failure", "log_support")}"""


def _freshness_rule_count_sql(chain: str, start: str, end: str) -> str:
    return f"""-- R3 rule-suspicious yearly count: stale/lower-bound oracle and lending impact surface.
WITH chainlink_lower_bound AS (
  SELECT
    l.blockchain AS chain,
    year(l.block_time) AS block_year,
    l.tx_hash AS tx_hash,
    CAST(NULL AS varbinary) AS actor,
    l.contract_address AS market_contract,
    CAST(l.tx_hash AS varchar) || ':' || CAST(l.index AS varchar) AS log_key
  FROM evms.logs l
  WHERE l.blockchain = {_sql_string(chain)}
    AND l.block_date BETWEEN DATE {_sql_string(start)} AND DATE {_sql_string(end)}
    AND l.topic0 = 0x0559884fd3a460db3073b7fc896cc77986f16e378210ded43186175bf646fc5f
    AND abs(CAST(bytearray_to_int256(l.topic1) AS double) / 1e8) > 0
    AND abs(CAST(bytearray_to_int256(l.topic1) AS double) / 1e8) <= 1
),
lending_transfer_impact AS (
  SELECT
    t.blockchain AS chain,
    year(t.block_time) AS block_year,
    t.tx_hash,
    t."to" AS actor,
    t."from" AS market_contract,
    CAST(t.tx_hash AS varchar) || ':' || CAST(t.evt_index AS varchar) AS log_key
  FROM tokens.transfers t
  LEFT JOIN tokens.erc20 tok
    ON tok.blockchain = t.blockchain
   AND tok.contract_address = t."from"
  WHERE t.blockchain = {_sql_string(chain)}
    AND t.block_date BETWEEN DATE {_sql_string(start)} AND DATE {_sql_string(end)}
    AND t.amount > 0
    AND (t.amount_usd IS NULL OR t.amount_usd >= 10000)
    AND regexp_like(lower(COALESCE(tok.symbol, '') || ' ' || COALESCE(tok.name, '')), '(^|[^a-z0-9])(a|b|c|m|v)[a-z0-9]+')
),
suspicious AS (
  SELECT * FROM chainlink_lower_bound
  UNION ALL
  SELECT * FROM lending_transfer_impact
)
{_suspicious_count_select("freshness_handling_failure", "suspicious")}"""


def _case_values_sql(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        raise PipelineError("No active attack tx rows are available for case-hit validation")
    values = []
    for row in rows:
        values.append(
            "("
            + ", ".join(
                [
                    _sql_string(row["case_id"]),
                    _sql_string(row["case_name"]),
                    _sql_string(row["chain"]),
                    _sql_string(row["display_chain"]),
                    _sql_string(row["original_failure_class"]),
                    _sql_string(row["broad_failure_class"]),
                    _sql_string(row["event_type"]),
                    _tx_literal(row["tx_hash"]),
                ]
            )
            + ")"
        )
    return ",\n".join(values)


def case_hit_sql(rows: List[Dict[str, Any]], start: str, end: str, chains: Iterable[str]) -> str:
    chain_values = ", ".join(_sql_string(chain) for chain in chains)
    return f"""-- Case-hit validation for the Dune Broad Search coverage layer.
-- The VALUES table is the local evaluation set; it is used only to verify that
-- known historical attack transactions are present in the remote transaction
-- index. Detailed receipt/log semantics remain in local materialized evidence;
-- this query intentionally avoids joining yearly logs/traces/transfers.
WITH attack_txs(case_id, case_name, chain, display_chain, original_failure_class, broad_failure_class, event_type, tx_hash) AS (
  VALUES
{_case_values_sql(rows)}
),
raw_tx_hits AS (
  SELECT
    m.*,
    t.block_time,
    t.block_date AS tx_block_date,
    t.block_number,
    t.success,
    t."from" AS tx_from,
    t."to" AS tx_to
  FROM attack_txs m
  LEFT JOIN evms.transactions t
    ON t.blockchain = m.chain
   AND t.hash = m.tx_hash
   AND t.block_date BETWEEN DATE {_sql_string(start)} AND DATE {_sql_string(end)}
  WHERE m.chain IN ({chain_values})
)
SELECT
  r.case_id,
  r.case_name,
  r.display_chain AS chain,
  r.original_failure_class,
  r.broad_failure_class AS expected_broad_failure_class,
  r.event_type,
  CAST(r.tx_hash AS varchar) AS tx_hash,
  r.block_number,
  r.block_time,
  r.success,
  r.tx_from,
  r.tx_to,
  r.block_number IS NOT NULL AS found_in_dune,
  CAST(0 AS bigint) AS matched_log_count,
  CAST(0 AS bigint) AS decoded_rule_signal_count,
  CAST(0 AS bigint) AS transfer_signal_count,
  CASE
    WHEN r.block_number IS NOT NULL THEN r.broad_failure_class
    ELSE NULL
  END AS matched_failure_class,
  CASE
    WHEN r.block_number IS NULL THEN 'not_found_in_dune_transactions'
    ELSE 'raw_transaction_in_scope'
  END AS matched_rule_stage,
  CAST('transaction_only_validation' AS varchar) AS decoded_function_names
FROM raw_tx_hits r
ORDER BY r.case_id, r.block_time, r.tx_hash
"""


def build_shards(start: str, end: str, chains: Iterable[str], rules: Iterable[str]) -> List[CoverageShard]:
    shards: List[CoverageShard] = []
    for window_start, window_end in _year_windows(start, end):
        year_key = window_start[:4]
        for chain in chains:
            shards.append(CoverageShard(f"raw_{year_key}_{chain}", "raw_count", chain, window_start, window_end))
            for rule in rules:
                shards.append(CoverageShard(f"rule_{year_key}_{chain}_{rule}", "rule_count", chain, window_start, window_end, rule))
    return shards


def attack_rows_for_shard(rows: List[Dict[str, Any]], shard: CoverageShard) -> List[Dict[str, Any]]:
    if shard.query_type != "case_hit" or shard.chain == "all":
        return rows
    start_year = int(shard.start[:4])
    end_year = int(shard.end[:4])
    return [
        row
        for row in rows
        if row.get("chain") == shard.chain and start_year <= int(row.get("year_local") or 0) <= end_year
    ]


def build_case_hit_shards(manifest_data: Dict[str, Any], start: str, end: str, chains: Iterable[str]) -> List[CoverageShard]:
    allowed_chains = set(chains)
    start_year = int(start[:4])
    end_year = int(end[:4])
    chain_years = sorted(
        {
            (row["chain"], int(row.get("year_local") or 0))
            for row in manifest_data.get("attack_txs", [])
            if row.get("chain") in allowed_chains and start_year <= int(row.get("year_local") or 0) <= end_year
        }
    )
    return [
        CoverageShard(
            shard_id=f"case_hit_{year}_{chain}",
            query_type="case_hit",
            chain=chain,
            start=f"{year}-01-01",
            end=f"{year}-12-31" if year < end_year else end,
        )
        for chain, year in chain_years
    ]


def render_shard_sql(shard: CoverageShard, attack_rows: Optional[List[Dict[str, Any]]] = None, chains: Optional[List[str]] = None) -> str:
    if shard.query_type == "raw_count":
        return raw_count_sql(shard.chain, shard.start, shard.end)
    if shard.query_type == "rule_count":
        return rule_count_sql(shard.chain, shard.start, shard.end, shard.failure_class)
    if shard.query_type == "case_hit":
        rows = attack_rows_for_shard(attack_rows or [], shard)
        shard_chains = [shard.chain] if shard.chain != "all" else (chains or [])
        return case_hit_sql(rows, shard.start, shard.end, shard_chains)
    raise PipelineError(f"Unknown coverage shard query type: {shard.query_type}")


def _paths(output_dir: Path, shard: CoverageShard) -> Dict[str, Path]:
    shard_dir = output_dir / "dune_shards" / shard.shard_id
    return {
        "dir": shard_dir,
        "sql": shard_dir / "query.sql",
        "manifest": shard_dir / "manifest.json",
        "json": shard_dir / "result.json",
        "csv": shard_dir / "result.csv",
    }


def _completed(paths: Dict[str, Path]) -> bool:
    if not paths["manifest"].exists() or not paths["json"].exists():
        return False
    try:
        manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return manifest.get("status") == "completed"


def run_coverage_shards(
    shards: List[CoverageShard],
    *,
    output_dir: Path,
    dry_run: bool,
    execute_dune: bool,
    resume: bool,
    performance: str,
    page_size: int,
    poll_interval: int,
    timeout_seconds: int,
    max_execution_credits: Optional[float],
    max_total_credits: Optional[float],
    attack_rows: Optional[List[Dict[str, Any]]] = None,
    chains: Optional[List[str]] = None,
    max_shards: Optional[int] = None,
) -> Dict[str, Any]:
    if execute_dune and dry_run:
        raise PipelineError("--execute-dune and --dry-run cannot both be enabled")
    selected = shards[:max_shards] if max_shards is not None else shards
    ensure_dir(output_dir)
    env = load_env()
    api_key = env.get("DUNE_MCP_KEY") or env.get("DUNE_API_KEY")
    if execute_dune and not api_key:
        raise PipelineError("Missing DUNE_MCP_KEY or DUNE_API_KEY in .env/environment")

    total_credits = 0.0
    stop_reason = ""
    combined_by_type: Dict[str, List[Dict[str, Any]]] = {"raw_count": [], "rule_count": [], "case_hit": []}
    manifest: Dict[str, Any] = {
        "dataset": "case_coverage_broad_search",
        "dry_run": dry_run,
        "execute_dune": execute_dune,
        "performance": performance,
        "output_dir": str(output_dir),
        "shard_count": len(selected),
        "max_execution_credits": max_execution_credits,
        "max_total_credits": max_total_credits,
        "contains_api_keys": False,
        "shards": [],
    }

    for shard in selected:
        started = time.time()
        paths = _paths(output_dir, shard)
        ensure_dir(paths["dir"])
        shard_attack_rows = attack_rows_for_shard(attack_rows or [], shard)
        sql = render_shard_sql(shard, attack_rows=attack_rows, chains=chains)
        paths["sql"].write_text(sql, encoding="utf-8")
        shard_manifest: Dict[str, Any] = {
            "shard_id": shard.shard_id,
            "query_type": shard.query_type,
            "chain": shard.chain,
            "failure_class": shard.failure_class,
            "start": shard.start,
            "end": shard.end,
            "sql_path": str(paths["sql"]),
            "result_json": str(paths["json"]),
            "result_csv": str(paths["csv"]),
            "contains_api_keys": False,
            "attack_tx_count": len(shard_attack_rows) if shard.query_type == "case_hit" else 0,
        }
        if stop_reason:
            shard_manifest.update(
                {
                    "status": "skipped_after_submit_error",
                    "skip_reason": stop_reason,
                    "duration_seconds": round(time.time() - started, 3),
                }
            )
            paths["manifest"].write_text(json.dumps(shard_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            manifest["shards"].append(shard_manifest)
            continue
        if resume and _completed(paths):
            existing = json.loads(paths["manifest"].read_text(encoding="utf-8"))
            rows = json.loads(paths["json"].read_text(encoding="utf-8")).get("rows", [])
            combined_by_type.setdefault(shard.query_type, []).extend(rows)
            existing["resume_skipped"] = True
            manifest["shards"].append(existing)
            total_credits += float(existing.get("execution_cost_credits") or 0)
            continue
        if max_total_credits is not None and total_credits >= max_total_credits and execute_dune:
            shard_manifest.update({"status": "skipped_budget", "skip_reason": "max_total_credits_reached"})
            paths["manifest"].write_text(json.dumps(shard_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            manifest["shards"].append(shard_manifest)
            continue
        if dry_run or not execute_dune:
            shard_manifest.update({"status": "dry_run", "row_count": 0, "duration_seconds": round(time.time() - started, 3)})
            paths["manifest"].write_text(json.dumps(shard_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            manifest["shards"].append(shard_manifest)
            continue

        try:
            execution = _execute_sql(sql, api_key or "", performance)
        except PipelineError as exc:
            error_text = str(exc)
            shard_manifest.update(
                {
                    "status": "failed",
                    "error": error_text,
                    "duration_seconds": round(time.time() - started, 3),
                }
            )
            paths["manifest"].write_text(json.dumps(shard_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            manifest["shards"].append(shard_manifest)
            if "HTTP 402" in error_text or "datapoint limit" in error_text.lower():
                stop_reason = "dune_billing_cycle_datapoint_limit"
            continue
        execution_id = execution.get("execution_id")
        if not execution_id:
            shard_manifest.update({"status": "failed", "error": execution})
            paths["manifest"].write_text(json.dumps(shard_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            manifest["shards"].append(shard_manifest)
            continue
        shard_manifest.update(
            {
                "status": "submitted",
                "state": "QUERY_STATE_SUBMITTED",
                "execution_id": execution_id,
                "submitted_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            }
        )
        paths["manifest"].write_text(json.dumps(shard_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        status = _poll_execution(
            execution_id,
            api_key or "",
            poll_interval=poll_interval,
            timeout_seconds=timeout_seconds,
            max_execution_credits=max_execution_credits,
        )
        total_credits += float(status.get("execution_cost_credits") or 0)
        shard_manifest.update(
            {
                "state": status.get("state"),
                "execution_cost_credits": status.get("execution_cost_credits"),
                "duration_seconds": round(time.time() - started, 3),
                "status_payload": {k: v for k, v in status.items() if k != "result"},
            }
        )
        if status.get("state") != "QUERY_STATE_COMPLETED":
            shard_manifest["status"] = "cancelled" if status.get("state") == "QUERY_STATE_CANCELLED" else "failed"
            paths["manifest"].write_text(json.dumps(shard_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            manifest["shards"].append(shard_manifest)
            continue
        rows, final_payload = _fetch_all_rows(execution_id, api_key or "", page_size=page_size)
        _write_rows_json(paths["json"], rows)
        _write_rows_csv(paths["csv"], rows)
        combined_by_type.setdefault(shard.query_type, []).extend(rows)
        shard_manifest.update(
            {
                "status": "completed",
                "row_count": len(rows),
                "metadata": (final_payload.get("result") or {}).get("metadata") or {},
                "expires_at": final_payload.get("expires_at") or status.get("expires_at"),
            }
        )
        paths["manifest"].write_text(json.dumps(shard_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest["shards"].append(shard_manifest)

    manifest["completed_count"] = sum(1 for shard in manifest["shards"] if shard.get("status") == "completed")
    manifest["dry_run_count"] = sum(1 for shard in manifest["shards"] if shard.get("status") == "dry_run")
    manifest["failed_count"] = sum(1 for shard in manifest["shards"] if shard.get("status") == "failed")
    manifest["cancelled_count"] = sum(1 for shard in manifest["shards"] if shard.get("status") == "cancelled")
    manifest["skipped_budget_count"] = sum(1 for shard in manifest["shards"] if shard.get("status") == "skipped_budget")
    manifest["skipped_after_submit_error_count"] = sum(
        1 for shard in manifest["shards"] if shard.get("status") == "skipped_after_submit_error"
    )
    manifest["observed_execution_credits"] = total_credits
    manifest["combined_row_count_by_type"] = {key: len(value) for key, value in combined_by_type.items()}
    write_json(output_dir / "run_manifest.json", manifest)
    return {"manifest": manifest, "rows_by_type": combined_by_type}


def summarize_case_hits(rows: List[Dict[str, Any]], expected_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    expected_by_case: Dict[str, int] = {}
    for row in expected_rows:
        expected_by_case[row["case_id"]] = expected_by_case.get(row["case_id"], 0) + 1
    observed_by_case: Dict[str, Dict[str, int]] = {case_id: {"found": 0, "rule_matched": 0} for case_id in expected_by_case}
    for row in rows:
        case_id = row.get("case_id")
        if case_id not in observed_by_case:
            continue
        if row.get("found_in_dune"):
            observed_by_case[case_id]["found"] += 1
        if row.get("matched_failure_class"):
            observed_by_case[case_id]["rule_matched"] += 1
    case_summaries = []
    for case_id, expected in sorted(expected_by_case.items()):
        observed = observed_by_case.get(case_id, {"found": 0, "rule_matched": 0})
        case_summaries.append(
            {
                "case_id": case_id,
                "expected_attack_tx_count": expected,
                "found_in_dune_count": observed["found"],
                "rule_matched_count": observed["rule_matched"],
                "all_attack_txs_found_in_dune": observed["found"] == expected,
                "has_representative_rule_match": observed["rule_matched"] > 0,
            }
        )
    return {
        "case_count": len(expected_by_case),
        "expected_attack_tx_count": len(expected_rows),
        "observed_hit_rows": len(rows),
        "all_attack_txs_found_in_dune": bool(case_summaries) and all(item["all_attack_txs_found_in_dune"] for item in case_summaries),
        "all_cases_have_representative_rule_match": bool(case_summaries)
        and all(item["has_representative_rule_match"] for item in case_summaries),
        "cases": case_summaries,
    }


def write_outputs(
    output_dir: Path,
    manifest_data: Dict[str, Any],
    rows_by_type: Dict[str, List[Dict[str, Any]]],
    run_manifest: Dict[str, Any],
) -> None:
    ensure_dir(output_dir)
    write_json(output_dir / "case_attack_tx_manifest.json", manifest_data)
    raw_payload = {
        "dataset": "yearly_raw_counts",
        "rows": rows_by_type.get("raw_count", []),
    }
    rule_payload = {
        "dataset": "yearly_rule_counts",
        "rows": rows_by_type.get("rule_count", []),
    }
    hit_payload = {
        "dataset": "case_hit_validation",
        "summary": summarize_case_hits(rows_by_type.get("case_hit", []), manifest_data["attack_txs"]),
        "rows": rows_by_type.get("case_hit", []),
    }
    write_json(output_dir / "yearly_raw_counts.json", raw_payload)
    write_json(output_dir / "yearly_rule_counts.json", rule_payload)
    write_json(output_dir / "case_hit_validation.json", hit_payload)
    write_report(output_dir, manifest_data, raw_payload, rule_payload, hit_payload, run_manifest)


def write_report(
    output_dir: Path,
    manifest_data: Dict[str, Any],
    raw_payload: Dict[str, Any],
    rule_payload: Dict[str, Any],
    hit_payload: Dict[str, Any],
    run_manifest: Dict[str, Any],
) -> None:
    output = repo_path("results", "broad_search_case_coverage.md")
    ensure_dir(output.parent)
    lines = [
        "# Broad Search Case Coverage",
        "",
        "This report is an index-level Dune coverage artifact. It counts remote historical rows and validates known attack transactions without downloading bulk receipts or logs locally.",
        "",
        "## Run",
        "",
        f"- Dry run: `{run_manifest.get('dry_run')}`",
        f"- Execute Dune: `{run_manifest.get('execute_dune')}`",
        f"- Output directory: `{output_dir}`",
        f"- Shards: `{run_manifest.get('shard_count')}`",
        f"- Completed: `{run_manifest.get('completed_count')}`",
        f"- Failed: `{run_manifest.get('failed_count')}`",
        f"- Skipped after submit error: `{run_manifest.get('skipped_after_submit_error_count', 0)}`",
        f"- Observed credits: `{run_manifest.get('observed_execution_credits')}`",
        "",
        "## Case Manifest",
        "",
        f"- Active cases: `{manifest_data['active_case_count']}`",
        f"- Canonical attack transactions: `{manifest_data['attack_tx_count']}`",
        f"- Chains: `{', '.join(manifest_data['chains'])}`",
        "",
        "| case | chain | broad class | attack txs |",
        "|---|---|---|---:|",
    ]
    for case in manifest_data["cases"]:
        lines.append(
            f"| `{case['case_id']}` | `{case['chain']}` | `{case['broad_failure_class']}` | `{manifest_data['by_case'].get(case['case_id'], 0)}` |"
        )
    lines.extend(["", "## Yearly Raw Counts", ""])
    raw_rows = raw_payload.get("rows", [])
    if raw_rows:
        lines.extend(["| chain | year | tx_count | log_count | unique_contract_count |", "|---|---:|---:|---:|---:|"])
        for row in raw_rows:
            lines.append(
                f"| `{display_chain(str(row.get('chain', '')) )}` | {row.get('year', '')} | {row.get('tx_count', 0)} | {row.get('log_count', 0)} | {row.get('unique_contract_count', 0)} |"
            )
    else:
        lines.append("_No Dune raw-count results are present yet. Run with `--execute-dune` to populate this section._")
    lines.extend(["", "## Rule-Suspicious Counts", ""])
    rule_rows = rule_payload.get("rows", [])
    if rule_rows:
        lines.extend(
            [
                "| chain | year | failure_class | suspicious_tx_count | suspicious_log_count | candidate_actor_count | candidate_market_count |",
                "|---|---:|---|---:|---:|---:|---:|",
            ]
        )
        for row in rule_rows:
            lines.append(
                f"| `{display_chain(str(row.get('chain', '')) )}` | {row.get('year', '')} | `{row.get('failure_class', '')}` | {row.get('suspicious_tx_count', 0)} | {row.get('suspicious_log_count', 0)} | {row.get('candidate_actor_count', 0)} | {row.get('candidate_market_count', 0)} |"
            )
    else:
        lines.append("_No Dune rule-count results are present yet. Run with `--execute-dune` to populate this section._")
    lines.extend(["", "## Case-Hit Validation", ""])
    hit_summary = hit_payload.get("summary", {})
    lines.append(f"- All attack txs found in Dune raw tx layer: `{hit_summary.get('all_attack_txs_found_in_dune', False)}`")
    lines.append(f"- All cases have representative rule match: `{hit_summary.get('all_cases_have_representative_rule_match', False)}`")
    lines.extend(["", "| case | expected txs | found in Dune | rule matched | raw complete | representative rule match |", "|---|---:|---:|---:|---|---|"])
    for case in hit_summary.get("cases", []):
        lines.append(
            f"| `{case['case_id']}` | {case['expected_attack_tx_count']} | {case['found_in_dune_count']} | {case['rule_matched_count']} | `{case['all_attack_txs_found_in_dune']}` | `{case['has_representative_rule_match']}` |"
        )
    lines.extend(
        [
            "",
            "## Safety Boundary",
            "",
            "- Read-only historical Dune index queries only.",
            "- No RPC receipt download in this runner.",
            "- No chain writes, write-method calls, private keys, attack simulation, or future-target prediction.",
        ]
    )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Dune index-level broad-search coverage and case-hit validation.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--chains", default=DEFAULT_CHAINS)
    parser.add_argument("--rules", default=DEFAULT_RULES)
    parser.add_argument("--query-types", default=DEFAULT_QUERY_TYPES, help="Comma-separated query types: raw_count,rule_count,case_hit.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--execute-dune", action="store_true", help="Execute paid Dune SQL. Default is dry-run SQL rendering only.")
    parser.add_argument("--dry-run", action="store_true", help="Render SQL and reports without calling Dune. This is the default unless --execute-dune is set.")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--performance", choices=["small", "medium", "large"], default="small")
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--poll-interval", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--max-execution-credits", type=float, default=None)
    parser.add_argument("--max-total-credits", type=float, default=None)
    parser.add_argument("--max-shards", type=int, default=None, help="Optional smoke-test shard cap.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    chains = parse_csv(args.chains)
    rules = parse_csv(args.rules)
    query_types = parse_csv(args.query_types)
    unknown = sorted(set(rules) - set(parse_csv(DEFAULT_RULES)))
    if unknown:
        raise SystemExit(f"Unknown rules: {', '.join(unknown)}")
    unknown_query_types = sorted(set(query_types) - set(parse_csv(DEFAULT_QUERY_TYPES)))
    if unknown_query_types:
        raise SystemExit(f"Unknown query types: {', '.join(unknown_query_types)}")

    manifest_data = build_attack_tx_manifest(chains)
    shards: List[CoverageShard] = []
    if "raw_count" in query_types or "rule_count" in query_types:
        base_shards = build_shards(args.start, args.end, chains, rules)
        if "raw_count" not in query_types:
            base_shards = [shard for shard in base_shards if shard.query_type != "raw_count"]
        if "rule_count" not in query_types:
            base_shards = [shard for shard in base_shards if shard.query_type != "rule_count"]
        shards.extend(base_shards)
    if "case_hit" in query_types:
        shards.extend(build_case_hit_shards(manifest_data, args.start, args.end, chains))
    execute = bool(args.execute_dune)
    dry_run = bool(args.dry_run or not execute)
    result = run_coverage_shards(
        shards,
        output_dir=output_dir,
        dry_run=dry_run,
        execute_dune=execute,
        resume=args.resume,
        performance=args.performance,
        page_size=args.page_size,
        poll_interval=args.poll_interval,
        timeout_seconds=args.timeout_seconds,
        max_execution_credits=args.max_execution_credits,
        max_total_credits=args.max_total_credits,
        attack_rows=manifest_data["attack_txs"],
        chains=chains,
        max_shards=args.max_shards,
    )
    write_outputs(output_dir, manifest_data, result["rows_by_type"], result["manifest"])
    print("Case-coverage broad search summary:")
    print(f"- dry run: {dry_run}")
    print(f"- execute dune: {execute}")
    print(f"- active cases: {manifest_data['active_case_count']}")
    print(f"- attack txs: {manifest_data['attack_tx_count']}")
    print(f"- shards: {result['manifest']['shard_count']}")
    print(f"- completed: {result['manifest']['completed_count']}")
    print(f"- failed: {result['manifest']['failed_count']}")
    print(f"- skipped after submit error: {result['manifest'].get('skipped_after_submit_error_count', 0)}")
    print(f"- output: {output_dir}")


if __name__ == "__main__":
    main()
