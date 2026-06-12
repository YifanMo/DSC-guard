#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from common import PipelineError, ensure_dir, read_json, repo_path, write_json, write_jsonl


DEFAULT_START = "2022-01-01"
DEFAULT_END = "2026-05-12"
DEFAULT_CHAINS = ["ethereum", "bnb", "base", "avalanche_c"]
DEFAULT_OUTPUT_DIR = repo_path("artifacts", "eval_dataset")
ALLOWED_LABELS = {"positive", "benign_verified", "unknown_negative"}

CHAIN_ALIASES = {
    "bsc": "bnb",
    "bnb": "bnb",
    "avalanche": "avalanche_c",
    "avalanche_c": "avalanche_c",
    "eth": "ethereum",
}
DISPLAY_CHAIN = {"bnb": "bsc", "avalanche_c": "avalanche"}

ANSWER_UPDATED_TOPIC = "0x0559884fd3a460db3073b7fc896cc77986f16e378210ded43186175bf646fc5f"
NEW_ROUND_TOPIC = "0x0109fc6f55cf40689f02fbaad7af7fe7bbac8a3d2186600afc7d3e10cac60271"
NEW_TRANSMISSION_TOPIC = "0xf6a97944f31ea060dfde0566e4167c1a1082551e64b60ecb14d599a9d023d451"

ORACLE_TOPICS = [
    (
        NEW_TRANSMISSION_TOPIC,
        "S1",
        "S1_ORACLE_PRICE_REPORTING",
        "Chainlink OCR NewTransmission",
        False,
    ),
    (NEW_ROUND_TOPIC, "S1", "S1_ORACLE_PRICE_REPORTING", "Chainlink NewRound", False),
    (ANSWER_UPDATED_TOPIC, "S1", "S1_ORACLE_PRICE_REPORTING", "Chainlink AnswerUpdated", False),
    (
        "0x22c5b7b2d8561d39f7f210b6b326a1aa69f15311163082308ac4877db6339dc1",
        "S2",
        "S2_FEED_BINDING_CONFIG",
        "asset/feed binding update",
        False,
    ),
    (
        "0xd9e7d1778ca05570ced72c9aeb12a41fcc76f7f57ea25853dea228f8836d0022",
        "S2",
        "S2_FEED_BINDING_CONFIG",
        "oracle wrapper setFeed-style config",
        False,
    ),
    (
        "0xaef9ecb0b33da1a5a170fdeed3accb3e88c5257f51d6faa019cea841b864d049",
        "S2",
        "S2_FEED_BINDING_CONFIG",
        "SetTokenPriceFeed",
        False,
    ),
    (
        "0xd52b2b9b7e9ee655fcb95d2e5b9e0c9f69e7ef2b8e9d2d0ea78402d576d22e22",
        "S2",
        "S2_FEED_BINDING_CONFIG",
        "NewPriceOracle",
        False,
    ),
    (
        "0xa8c96090e146ce1076efa81e5424d56e13d5c3854943f7926406c12d15d6dbe9",
        "S3",
        "S3_PRICE_COMPOSITION_OR_ROUTE_CONFIG",
        "SetRoute",
        False,
    ),
    (
        "0xd1b3641b73e6c323671a85001b02db34d4e63a7fa6d264896138094dd6b8bfdf",
        "S3",
        "S3_PRICE_COMPOSITION_OR_ROUTE_CONFIG",
        "SetTimeGap",
        False,
    ),
    (
        "0xdb99134445c07379338e9d1d3ca5cd958bd95af80ce8e9b6d73882f9b12002e4",
        "S3",
        "S3_PRICE_COMPOSITION_OR_ROUTE_CONFIG",
        "token remapping",
        False,
    ),
    (
        "0xd6b3a81dd8b7dc419d8d0f20797397ea2eaba914386b89898aa638438803a1ec",
        "S4",
        "S4_GOVERNANCE_EXECUTED_ORACLE_CONFIG",
        "governance executed oracle change",
        False,
    ),
    (
        "0x7f26b83ff96e1f2b6a682f133852f6798a09c465da95921460cefb3847402498",
        "S5",
        "S5_CONTEXTUAL_ORACLE_PROXY_WIRING",
        "Initialized on oracle-path contract",
        True,
    ),
    (
        "0x8be0079c531659141344cd1fd0a4f28419497f9722a3daafe3b4186f6b6457e0",
        "S5",
        "S5_CONTEXTUAL_ORACLE_PROXY_WIRING",
        "OwnershipTransferred on oracle-path contract",
        True,
    ),
]

IMPACT_TOPICS = [
    ("0x3ab23ab0d51cccc0c3085aec51f99228625aa1a922b3a8ca89a26b0f2027a1a5", "MarketEntered"),
    ("0x4c209b5fc8ad50758f13e2e1088ba56a560dff690a1c6fef26394f4c03821c4f", "Compound Mint"),
    ("0x4dec04e750ca11537cabcd8a9eab06494de08da3735bc8871cd41250e190bc04", "ERC4626 Deposit"),
    ("0xde6857219544bb5b7746f48ed30be6386fefc61b2f864cacf559893bf50fd951", "Aave Deposit"),
    ("0x13ed6866d4e1ee6da46f845c46d7e54120883d75c5ea9a2dacc1c4ca8984ab80", "Compound Borrow"),
    ("0xc6a898309e823ee50bac64e45ca8adba6690e99e7841c45d754e2a38e9019d9b", "Aave Borrow"),
    ("0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52", "LiquidateBorrow"),
    ("0x00058a56ea94653cdf4f152d227ace22d4c00ad99e2a43f58cb7d9e3feb295f2", "ReserveUsedAsCollateralEnabled"),
]


def normalize_chain(value: str) -> str:
    return CHAIN_ALIASES.get(str(value or "").strip().lower(), str(value or "").strip().lower())


def display_chain(value: str) -> str:
    return DISPLAY_CHAIN.get(value, value)


def _valid_hash(value: Any, nbytes: int = 32) -> bool:
    text = str(value or "").lower()
    return len(text) == 2 + nbytes * 2 and text.startswith("0x") and all(
        ch in "0123456789abcdef" for ch in text[2:]
    )


def _valid_address(value: Any) -> bool:
    return _valid_hash(value, nbytes=20)


def _sql_string(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _sql_varbinary(value: str) -> str:
    if not (value.startswith("0x") and all(ch in "0123456789abcdef" for ch in value[2:].lower())):
        raise PipelineError(f"Invalid hex literal for Dune SQL: {value}")
    return value.lower()


def _parse_csv(value: str | Iterable[str]) -> List[str]:
    raw = value.split(",") if isinstance(value, str) else list(value)
    chains: List[str] = []
    for item in raw:
        chain = normalize_chain(str(item))
        if chain and chain not in chains:
            chains.append(chain)
    return chains


def _parse_time(value: Any) -> Optional[datetime]:
    if value in (None, "", 0):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(int(value), timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return datetime.fromtimestamp(int(text), timezone.utc)
    if text.endswith(" UTC"):
        text = text[:-4] + "+00:00"
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _dune_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _year(timestamp: Any) -> int:
    parsed = _parse_time(timestamp)
    return parsed.year if parsed else 0


def _read_jsonl_if_exists(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _read_trace(case_id: str) -> List[Dict[str, Any]]:
    return _read_jsonl_if_exists(repo_path("artifacts", "log_trace", f"{case_id}.jsonl"))


def _active_cases(chains: Sequence[str]) -> List[Dict[str, Any]]:
    active = set(read_json(repo_path("config", "cases.json")).keys())
    chain_filter = set(chains)
    manifest = read_json(repo_path("artifacts", "dataset_manifest.json"))
    rows: List[Dict[str, Any]] = []
    for case in manifest.get("cases", []):
        case_id = case.get("case", "")
        chain = normalize_chain(case.get("chain", ""))
        if case_id in active and chain in chain_filter:
            item = dict(case)
            item["dune_chain"] = chain
            item["display_chain"] = display_chain(chain)
            rows.append(item)
    return rows


def _scope_for_case(case: Dict[str, Any]) -> str:
    failure_class = case.get("failure_class", "")
    if failure_class == "feed_binding_failure":
        return "S2"
    if failure_class in {"price_composition_failure", "price_semantics_mismatch"}:
        return "S3"
    if failure_class == "freshness_handling_failure":
        return "S1"
    return ""


def _primary_boundary_log(case_id: str) -> Dict[str, Any]:
    logs = _read_jsonl_if_exists(repo_path("artifacts", "incident_tables", case_id, "pre_attack_logs.jsonl"))
    primary = next((row for row in logs if row.get("is_primary_boundary_log")), None)
    return primary or (logs[0] if logs else {})


def _incident_summary(case_id: str) -> Dict[str, Any]:
    path = repo_path("artifacts", "incident_tables", case_id, "summary.json")
    return read_json(path) if path.exists() else {}


def _case_window(case_id: str, trace: List[Dict[str, Any]]) -> Tuple[datetime, datetime]:
    summary = _incident_summary(case_id)
    start_keys = ("natural_window_start", "config_time", "first_attack_time")
    end_keys = ("window_end", "last_lifecycle_time", "last_attack_time", "exploit_time", "last_boundary_time")
    start = next((_parse_time(summary.get(key)) for key in start_keys if _parse_time(summary.get(key))), None)
    end = next((_parse_time(summary.get(key)) for key in end_keys if _parse_time(summary.get(key))), None)
    if not start and trace:
        start = min((_parse_time(row.get("block_timestamp")) for row in trace if _parse_time(row.get("block_timestamp"))), default=None)
    if not end and trace:
        end = max((_parse_time(row.get("block_timestamp")) for row in trace if _parse_time(row.get("block_timestamp"))), default=None)
    if not start:
        start = datetime(1970, 1, 1, tzinfo=timezone.utc)
    if not end or end < start:
        end = start + timedelta(hours=24)
    return start, end


def _known_case_txs(case_id: str, case: Dict[str, Any], trace: List[Dict[str, Any]]) -> List[str]:
    txs = set()
    for value in (case.get("known_txs") or {}).values():
        if _valid_hash(value):
            txs.add(str(value).lower())
    for row in trace:
        tx_hash = str(row.get("tx_hash") or "").lower()
        if _valid_hash(tx_hash):
            txs.add(tx_hash)
    for folder in ("incident_tables",):
        case_dir = repo_path("artifacts", folder, case_id)
        for name in ("pre_attack_logs.jsonl", "boundary_logs.jsonl", "attack_txs.jsonl"):
            for row in _read_jsonl_if_exists(case_dir / name):
                tx_hash = str(row.get("tx_hash") or "").lower()
                if _valid_hash(tx_hash):
                    txs.add(tx_hash)
    return sorted(txs)


def _known_case_contracts(case_id: str, case: Dict[str, Any], trace: List[Dict[str, Any]]) -> List[str]:
    contracts = set()
    for row in trace:
        value = str(row.get("address") or "").lower()
        if _valid_address(value):
            contracts.add(value)
        decoded = row.get("decoded") or {}
        for key in ("feed", "oracle_contract", "target", "actual_oracle", "expected_oracle"):
            value = str(decoded.get(key) or "").lower()
            if _valid_address(value):
                contracts.add(value)
    for path in (
        repo_path("artifacts", "incident_tables", case_id, "pre_attack_logs.jsonl"),
        repo_path("artifacts", "incident_tables", case_id, "boundary_logs.jsonl"),
    ):
        for row in _read_jsonl_if_exists(path):
            for key in ("address", "target"):
                value = str(row.get(key) or "").lower()
                if _valid_address(value):
                    contracts.add(value)
    for obj in (case.get("stale_oracle") or {}, case.get("oracle_malfunction") or {}, case.get("oracle_mismatch") or {}):
        for key in ("feed", "eth_usd_feed", "actual_oracle", "expected_oracle"):
            value = str(obj.get(key) or "").lower()
            if _valid_address(value):
                contracts.add(value)
    return sorted(contracts)


def _valid_or_fallback(*values: Any) -> str:
    for value in values:
        text = str(value or "").lower()
        if _valid_address(text):
            return text
    for value in values:
        text = str(value or "").lower()
        if text:
            return text
    return ""


def _normal_oracle_bounds(case: Dict[str, Any]) -> Optional[Tuple[str, float, float, int]]:
    case_id = case.get("case", "")
    if case_id in {"venus_luna", "blizz_luna"}:
        feed = (case.get("stale_oracle") or {}).get("feed")
        if _valid_address(feed):
            return str(feed).lower(), 1.0, 500.0, 8
    if case_id == "moonwell_wrseth":
        feed = (case.get("oracle_malfunction") or {}).get("feed")
        if _valid_address(feed):
            return str(feed).lower(), 0.5, 2.0, 8
    return None


def _case_context_rows(chains: Sequence[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for case in _active_cases(chains):
        case_id = case["case"]
        trace = _read_trace(case_id)
        start, end = _case_window(case_id, trace)
        primary = _primary_boundary_log(case_id)
        rows.append(
            {
                "case_id": case_id,
                "chain": case["dune_chain"],
                "display_chain": case["display_chain"],
                "failure_class": case.get("failure_class", ""),
                "scope_class": _scope_for_case(case),
                "incident_start": start,
                "incident_end": end,
                "primary_topic0": str(primary.get("topic0") or "").lower(),
                "primary_contract": str(primary.get("address") or primary.get("target") or "").lower(),
                "known_txs": _known_case_txs(case_id, case, trace),
                "known_contracts": _known_case_contracts(case_id, case, trace),
                "normal_oracle_bounds": _normal_oracle_bounds(case),
                "trace_path": str(repo_path("artifacts", "log_trace", f"{case_id}.jsonl")),
            }
        )
    return rows


def build_positive_cases(chains: Sequence[str]) -> List[Dict[str, Any]]:
    positives: List[Dict[str, Any]] = []
    for index, case in enumerate(_active_cases(chains), start=1):
        case_id = case["case"]
        trace = _read_trace(case_id)
        trigger_event = case.get("trigger_event")
        impact_events = set(case.get("impact_events") or [])
        trigger = next((row for row in trace if row.get("event_type") == trigger_event), trace[0] if trace else {})
        impact = next((row for row in trace if row.get("event_type") in impact_events and _valid_hash(row.get("tx_hash"))), {})
        chosen = trigger or impact
        primary_log = _primary_boundary_log(case_id)
        trigger_tx = str(trigger.get("tx_hash") or primary_log.get("tx_hash") or "").lower()
        impact_tx = str(impact.get("tx_hash") or "").lower()
        tx_hash = trigger_tx or impact_tx
        positives.append(
            {
                "sample_id": f"positive-{index:03d}-{case_id}",
                "label": "positive",
                "benign_stratum": "",
                "case_id": case_id,
                "case_related_to": case_id,
                "chain": case["dune_chain"],
                "display_chain": case["display_chain"],
                "year": _year(chosen.get("block_timestamp") or primary_log.get("block_time")),
                "failure_class": case.get("failure_class", ""),
                "scope_class": _scope_for_case(case),
                "tx_hash": tx_hash,
                "trigger_tx_hash": trigger_tx,
                "first_impact_tx_hash": impact_tx,
                "contract_address": _valid_or_fallback(chosen.get("address"), primary_log.get("address")),
                "trigger_contract_address": _valid_or_fallback(trigger.get("address"), primary_log.get("address")),
                "first_impact_contract_address": _valid_or_fallback(impact.get("address")),
                "topic0": str(primary_log.get("topic0") or "").lower(),
                "expected_violation": True,
                "exclusion_reason": "positive_case_existing_materialized_trace",
                "materialization_status": "existing_trace",
                "trace_path": str(repo_path("artifacts", "log_trace", f"{case_id}.jsonl")),
                "evidence_path": case.get("artifacts", {}).get("evidence", ""),
            }
        )
    return positives


def _values_case_windows(contexts: Sequence[Dict[str, Any]]) -> str:
    rows = []
    for ctx in contexts:
        rows.append(
            "("
            + ", ".join(
                [
                    _sql_string(ctx["case_id"]),
                    _sql_string(ctx["chain"]),
                    f"TIMESTAMP {_sql_string(_dune_timestamp(ctx['incident_start']))}",
                    f"TIMESTAMP {_sql_string(_dune_timestamp(ctx['incident_end']))}",
                ]
            )
            + ")"
        )
    return ",\n    ".join(rows) if rows else "('none', 'none', TIMESTAMP '1970-01-01 00:00:00', TIMESTAMP '1970-01-02 00:00:00')"


def _values_known_txs(contexts: Sequence[Dict[str, Any]]) -> str:
    rows = []
    for ctx in contexts:
        for tx_hash in ctx["known_txs"]:
            rows.append(f"({_sql_string(ctx['case_id'])}, {_sql_string(ctx['chain'])}, {_sql_varbinary(tx_hash)})")
    return ",\n    ".join(rows) if rows else "('none', 'none', 0x0000000000000000000000000000000000000000000000000000000000000000)"


def _values_known_contracts(contexts: Sequence[Dict[str, Any]]) -> str:
    rows = []
    for ctx in contexts:
        for address in ctx["known_contracts"]:
            rows.append(f"({_sql_string(ctx['case_id'])}, {_sql_string(ctx['chain'])}, {_sql_varbinary(address)})")
    return ",\n    ".join(rows) if rows else "('none', 'none', 0x0000000000000000000000000000000000000000)"


def _values_oracle_bounds(contexts: Sequence[Dict[str, Any]]) -> str:
    rows = []
    for ctx in contexts:
        bounds = ctx.get("normal_oracle_bounds")
        if not bounds:
            continue
        feed, normal_min, normal_max, decimals = bounds
        rows.append(
            "("
            + ", ".join(
                [
                    _sql_string(ctx["case_id"]),
                    _sql_string(ctx["chain"]),
                    _sql_varbinary(feed),
                    str(float(normal_min)),
                    str(float(normal_max)),
                    str(int(decimals)),
                    f"TIMESTAMP {_sql_string(_dune_timestamp(ctx['incident_start']))}",
                    f"TIMESTAMP {_sql_string(_dune_timestamp(ctx['incident_end']))}",
                ]
            )
            + ")"
        )
    return ",\n    ".join(rows) if rows else "('none', 'none', 0x0000000000000000000000000000000000000000, 0.0, 0.0, 8, TIMESTAMP '1970-01-01 00:00:00', TIMESTAMP '1970-01-02 00:00:00')"


def _values_protocol_contracts(contexts: Sequence[Dict[str, Any]]) -> str:
    rows = []
    for ctx in contexts:
        for address in ctx["known_contracts"]:
            rows.append(
                "("
                + ", ".join(
                    [
                        _sql_string(ctx["case_id"]),
                        _sql_string(ctx["chain"]),
                        _sql_varbinary(address),
                        _sql_string(ctx["failure_class"]),
                        f"TIMESTAMP {_sql_string(_dune_timestamp(ctx['incident_start']))}",
                        f"TIMESTAMP {_sql_string(_dune_timestamp(ctx['incident_end']))}",
                    ]
                )
                + ")"
            )
    return ",\n    ".join(rows) if rows else "('none', 'none', 0x0000000000000000000000000000000000000000, 'none', TIMESTAMP '1970-01-01 00:00:00', TIMESTAMP '1970-01-02 00:00:00')"


def _oracle_topic_values(include_contextual_s5: bool) -> str:
    rows = []
    for topic0, short_scope, full_scope, topic_name, contextual in ORACLE_TOPICS:
        if contextual and not include_contextual_s5:
            continue
        rows.append(
            f"({_sql_varbinary(topic0)}, {_sql_string(short_scope)}, {_sql_string(full_scope)}, {_sql_string(topic_name)}, {str(contextual).lower()})"
        )
    return ",\n    ".join(rows)


def _impact_topic_values() -> str:
    return ",\n    ".join(f"({_sql_varbinary(topic0)}, {_sql_string(name)})" for topic0, name in IMPACT_TOPICS)


def _protocol_topic_values() -> str:
    rows = [
        f"({_sql_varbinary(topic0)}, {_sql_string(short_scope)}, {_sql_string(topic_name)})"
        for topic0, short_scope, _full_scope, topic_name, _contextual in ORACLE_TOPICS
    ]
    rows.extend(f"({_sql_varbinary(topic0)}, 'IMPACT', {_sql_string(name)})" for topic0, name in IMPACT_TOPICS)
    return ",\n    ".join(rows)


def _bucket_values(bucket_count: int) -> List[str]:
    count = max(1, min(256, int(bucket_count)))
    if count == 256:
        return [f"{i:02x}" for i in range(256)]
    step = 256 / count
    return sorted({f"{int(i * step):02x}" for i in range(count)})


def _bucket_sql(bucket_count: int) -> str:
    return ", ".join(_sql_string(bucket) for bucket in _bucket_values(bucket_count))


def same_oracle_sql(
    start: str,
    end: str,
    chains: Sequence[str],
    contexts: Sequence[Dict[str, Any]],
    bucket_count: int,
    guard_hours: int,
) -> str:
    return f"""-- Same-oracle benign candidates.
-- Uses deterministic tx_hash buckets and no rank truncation, scores, amount ranking, or nondeterministic sampling.
WITH
case_oracles(case_id, chain, feed_address, normal_min, normal_max, answer_decimals, incident_start, incident_end) AS (
  VALUES
    {_values_oracle_bounds(contexts)}
),
known_case_txs(case_id, chain, tx_hash) AS (
  VALUES
    {_values_known_txs(contexts)}
),
answer_logs AS (
  SELECT
    'same_oracle' AS benign_stratum,
    o.case_id AS case_related_to,
    l.blockchain AS chain,
    year(l.block_time) AS year,
    l.block_time,
    l.tx_hash,
    l.contract_address,
    l.topic0,
    o.normal_min,
    o.normal_max,
    abs(CAST(bytearray_to_int256(l.topic1) AS double) / pow(10, o.answer_decimals)) AS normalized_answer
  FROM evms.logs l
  JOIN case_oracles o
    ON o.chain = l.blockchain
   AND o.feed_address = l.contract_address
  LEFT JOIN known_case_txs kt
    ON kt.chain = l.blockchain
   AND kt.tx_hash = l.tx_hash
  WHERE l.blockchain IN ({", ".join(_sql_string(chain) for chain in chains)})
    AND l.block_date BETWEEN DATE {_sql_string(start)} AND DATE {_sql_string(end)}
    AND l.topic0 = {_sql_varbinary(ANSWER_UPDATED_TOPIC)}
    AND kt.tx_hash IS NULL
    AND NOT (
      l.block_time BETWEEN o.incident_start - INTERVAL '{guard_hours}' HOUR
                       AND o.incident_end + INTERVAL '{guard_hours}' HOUR
    )
    AND substr(lower(CAST(l.tx_hash AS varchar)), 3, 2) IN ({_bucket_sql(bucket_count)})
)
SELECT
  'benign-' || benign_stratum || '-' || chain || '-' || CAST(tx_hash AS varchar) AS sample_id,
  CASE
    WHEN normalized_answer BETWEEN normal_min AND normal_max THEN 'benign_verified'
    ELSE 'unknown_negative'
  END AS label,
  benign_stratum,
  chain,
  year,
  'S1' AS scope_class,
  CAST(tx_hash AS varchar) AS tx_hash,
  CAST(contract_address AS varchar) AS contract_address,
  CAST(topic0 AS varchar) AS topic0,
  case_related_to,
  false AS expected_violation,
  'same oracle feed outside incident window with normal answer bounds' AS exclusion_reason,
  'remote_candidate_pending_receipt_replay' AS materialization_status,
  normalized_answer
FROM answer_logs
ORDER BY chain, year, case_related_to, tx_hash;
"""


def same_protocol_sql(
    start: str,
    end: str,
    chains: Sequence[str],
    contexts: Sequence[Dict[str, Any]],
    bucket_count: int,
    guard_hours: int,
) -> str:
    return f"""-- Same-protocol hard negative candidates.
-- Rows start as unknown_negative until local replay proves no constraint violation.
WITH
case_protocol_contracts(case_id, chain, contract_address, failure_class, incident_start, incident_end) AS (
  VALUES
    {_values_protocol_contracts(contexts)}
),
known_case_txs(case_id, chain, tx_hash) AS (
  VALUES
    {_values_known_txs(contexts)}
),
topic_rules(topic0, scope_class, topic_name) AS (
  VALUES
    {_protocol_topic_values()}
),
same_protocol_logs AS (
  SELECT
    'same_protocol' AS benign_stratum,
    c.case_id AS case_related_to,
    c.failure_class,
    l.blockchain AS chain,
    year(l.block_time) AS year,
    l.tx_hash,
    l.contract_address,
    l.topic0,
    tr.scope_class,
    tr.topic_name
  FROM evms.logs l
  JOIN case_protocol_contracts c
    ON c.chain = l.blockchain
   AND c.contract_address = l.contract_address
  JOIN topic_rules tr ON tr.topic0 = l.topic0
  LEFT JOIN known_case_txs kt
    ON kt.chain = l.blockchain
   AND kt.tx_hash = l.tx_hash
  WHERE l.blockchain IN ({", ".join(_sql_string(chain) for chain in chains)})
    AND l.block_date BETWEEN DATE {_sql_string(start)} AND DATE {_sql_string(end)}
    AND kt.tx_hash IS NULL
    AND NOT (
      l.block_time BETWEEN c.incident_start - INTERVAL '{guard_hours}' HOUR
                       AND c.incident_end + INTERVAL '{guard_hours}' HOUR
    )
    AND substr(lower(CAST(l.tx_hash AS varchar)), 3, 2) IN ({_bucket_sql(bucket_count)})
)
SELECT
  'benign-' || benign_stratum || '-' || chain || '-' || CAST(tx_hash AS varchar) AS sample_id,
  'unknown_negative' AS label,
  benign_stratum,
  chain,
  year,
  scope_class,
  CAST(tx_hash AS varchar) AS tx_hash,
  CAST(contract_address AS varchar) AS contract_address,
  CAST(topic0 AS varchar) AS topic0,
  case_related_to,
  false AS expected_violation,
  'same protocol/topic shape outside incident window; requires local replay before FP denominator' AS exclusion_reason,
  'remote_candidate_pending_receipt_replay' AS materialization_status,
  failure_class,
  topic_name
FROM same_protocol_logs
ORDER BY chain, year, case_related_to, tx_hash;
"""


def cross_protocol_sql(
    start: str,
    end: str,
    chains: Sequence[str],
    contexts: Sequence[Dict[str, Any]],
    bucket_count: int,
    guard_hours: int,
) -> str:
    return f"""-- Cross-protocol oracle-scope background candidates.
-- Deterministic hash sampling keeps the local queue bounded without rank truncation.
WITH
oracle_topic_rules(topic0, scope_class, full_scope_class, topic_name, contextual_only) AS (
  VALUES
    {_oracle_topic_values(include_contextual_s5=False)}
),
case_windows(case_id, chain, incident_start, incident_end) AS (
  VALUES
    {_values_case_windows(contexts)}
),
known_case_txs(case_id, chain, tx_hash) AS (
  VALUES
    {_values_known_txs(contexts)}
),
known_case_contracts(case_id, chain, contract_address) AS (
  VALUES
    {_values_known_contracts(contexts)}
),
oracle_scope_logs AS (
  SELECT
    'cross_protocol' AS benign_stratum,
    l.blockchain AS chain,
    year(l.block_time) AS year,
    l.block_time,
    l.tx_hash,
    l.contract_address,
    l.topic0,
    r.scope_class,
    r.topic_name,
    count(kt.tx_hash) AS known_tx_hits,
    count(kc.contract_address) AS known_contract_hits,
    count_if(l.block_time BETWEEN w.incident_start - INTERVAL '{guard_hours}' HOUR
                            AND w.incident_end + INTERVAL '{guard_hours}' HOUR) AS incident_window_hits
  FROM evms.logs l
  JOIN oracle_topic_rules r ON r.topic0 = l.topic0
  LEFT JOIN known_case_txs kt
    ON kt.chain = l.blockchain
   AND kt.tx_hash = l.tx_hash
  LEFT JOIN known_case_contracts kc
    ON kc.chain = l.blockchain
   AND kc.contract_address = l.contract_address
  LEFT JOIN case_windows w ON w.chain = l.blockchain
  WHERE l.blockchain IN ({", ".join(_sql_string(chain) for chain in chains)})
    AND l.block_date BETWEEN DATE {_sql_string(start)} AND DATE {_sql_string(end)}
    AND r.contextual_only = false
    AND substr(lower(CAST(l.tx_hash AS varchar)), 3, 2) IN ({_bucket_sql(bucket_count)})
  GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9
)
SELECT
  'benign-' || benign_stratum || '-' || chain || '-' || CAST(tx_hash AS varchar) AS sample_id,
  'unknown_negative' AS label,
  benign_stratum,
  chain,
  year,
  scope_class,
  CAST(tx_hash AS varchar) AS tx_hash,
  CAST(contract_address AS varchar) AS contract_address,
  CAST(topic0 AS varchar) AS topic0,
  '' AS case_related_to,
  false AS expected_violation,
  'cross-protocol oracle-scope log excluding known case txs/contracts/windows; requires local replay before FP denominator' AS exclusion_reason,
  'remote_candidate_pending_receipt_replay' AS materialization_status,
  topic_name
FROM oracle_scope_logs
WHERE known_tx_hits = 0
  AND known_contract_hits = 0
  AND incident_window_hits = 0
ORDER BY chain, year, scope_class, tx_hash;
"""


def write_sql(sql_dir: Path, start: str, end: str, chains: Sequence[str], contexts: Sequence[Dict[str, Any]], args: argparse.Namespace) -> None:
    ensure_dir(sql_dir)
    files = {
        "01_same_oracle_benign_candidates.sql": same_oracle_sql(
            start,
            end,
            chains,
            contexts,
            args.same_oracle_buckets,
            args.incident_guard_hours,
        ),
        "02_same_protocol_benign_candidates.sql": same_protocol_sql(
            start,
            end,
            chains,
            contexts,
            args.same_protocol_buckets,
            args.incident_guard_hours,
        ),
        "03_cross_protocol_benign_candidates.sql": cross_protocol_sql(
            start,
            end,
            chains,
            contexts,
            args.cross_protocol_buckets,
            args.incident_guard_hours,
        ),
    }
    for name, sql in files.items():
        (sql_dir / name).write_text(sql, encoding="utf-8")
    write_json(
        sql_dir / "manifest.json",
        {
            "dataset": "benign_eval_dataset_sql",
            "start": start,
            "end": end,
            "chains": chains,
            "deterministic_hash_sampling": {
                "same_oracle_buckets": _bucket_values(args.same_oracle_buckets),
                "same_protocol_buckets": _bucket_values(args.same_protocol_buckets),
                "cross_protocol_buckets": _bucket_values(args.cross_protocol_buckets),
            },
            "selection_policy": "case-aware hard benign sampling; no rank truncation, scoring formula, amount ranking, or nondeterministic sampling",
            "files": sorted(files),
        },
    )


def _read_export_rows(input_dir: Optional[Path]) -> List[Dict[str, Any]]:
    if not input_dir:
        return []
    if not input_dir.exists():
        raise PipelineError(f"Missing input directory: {input_dir}")
    rows: List[Dict[str, Any]] = []
    for path in sorted(input_dir.rglob("*")):
        if path.is_dir():
            continue
        if path.suffix.lower() == ".jsonl":
            rows.extend(_read_jsonl_if_exists(path))
        elif path.suffix.lower() == ".json":
            payload = read_json(path)
            if isinstance(payload, list):
                rows.extend(payload)
            elif isinstance(payload, dict):
                if isinstance(payload.get("rows"), list):
                    rows.extend(payload["rows"])
                elif isinstance(payload.get("result"), dict) and isinstance(payload["result"].get("rows"), list):
                    rows.extend(payload["result"]["rows"])
        elif path.suffix.lower() == ".csv":
            with path.open(newline="", encoding="utf-8") as handle:
                rows.extend(dict(row) for row in csv.DictReader(handle))
    return rows


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "verified"}


def _normalize_export_row(row: Dict[str, Any], index: int, known_txs: set[str]) -> Optional[Dict[str, Any]]:
    tx_hash = str(row.get("tx_hash") or row.get("hash") or "").lower()
    if tx_hash and not _valid_hash(tx_hash):
        return None
    if tx_hash in known_txs:
        return None
    stratum = str(row.get("benign_stratum") or row.get("stratum") or "cross_protocol").strip()
    if stratum not in {"same_oracle", "same_protocol", "cross_protocol"}:
        stratum = "cross_protocol"
    label = str(row.get("label") or "").strip()
    if label not in ALLOWED_LABELS:
        label = "benign_verified" if _truthy(row.get("verified_normality")) else "unknown_negative"
    if label == "positive":
        label = "unknown_negative"
    chain = normalize_chain(str(row.get("chain") or row.get("blockchain") or ""))
    sample_id = str(row.get("sample_id") or "")
    if not sample_id:
        sample_id = f"benign-{stratum}-{index:06d}-{chain}-{tx_hash[:10] if tx_hash else 'nohash'}"
    return {
        "sample_id": sample_id,
        "label": label,
        "benign_stratum": stratum,
        "case_id": "",
        "case_related_to": str(row.get("case_related_to") or row.get("case_id") or ""),
        "chain": chain,
        "display_chain": display_chain(chain),
        "year": int(row.get("year") or row.get("block_year") or 0),
        "failure_class": str(row.get("failure_class") or ""),
        "scope_class": str(row.get("scope_class") or ""),
        "tx_hash": tx_hash,
        "contract_address": str(row.get("contract_address") or row.get("address") or "").lower(),
        "topic0": str(row.get("topic0") or "").lower(),
        "expected_violation": False,
        "exclusion_reason": str(row.get("exclusion_reason") or "exported benign candidate; local replay required unless label is benign_verified"),
        "materialization_status": str(row.get("materialization_status") or "remote_candidate_pending_receipt_replay"),
    }


def ingest_benign_exports(rows: Sequence[Dict[str, Any]], contexts: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    known_txs = {tx for ctx in contexts for tx in ctx["known_txs"]}
    buckets = {"same_oracle": [], "same_protocol": [], "cross_protocol": []}
    seen: set[Tuple[str, str]] = set()
    for index, row in enumerate(rows, start=1):
        normalized = _normalize_export_row(row, index, known_txs)
        if not normalized:
            continue
        key = (
            normalized["benign_stratum"],
            normalized["case_related_to"],
            normalized["tx_hash"],
            normalized["topic0"],
            normalized["contract_address"],
        )
        if key in seen:
            continue
        seen.add(key)
        buckets[normalized["benign_stratum"]].append(normalized)
    return buckets


def _count_by(rows: Sequence[Dict[str, Any]], field: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        key = str(row.get(field) or "")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def write_reports(
    output_dir: Path,
    positives: Sequence[Dict[str, Any]],
    benign: Dict[str, List[Dict[str, Any]]],
    sql_dir: Path,
    results_dir: Path,
    args: argparse.Namespace,
) -> None:
    all_benign = [row for rows in benign.values() for row in rows]
    verified = [row for row in all_benign if row.get("label") == "benign_verified"]
    unknown = [row for row in all_benign if row.get("label") == "unknown_negative"]
    manifest = {
        "dataset": "case_aware_benign_eval_dataset",
        "start": args.start,
        "end": args.end,
        "chains": _parse_csv(args.chains),
        "positive_count": len(positives),
        "benign_candidate_count": len(all_benign),
        "benign_verified_count": len(verified),
        "unknown_negative_count": len(unknown),
        "false_positive_denominator": len(verified),
        "by_benign_stratum": {key: len(value) for key, value in benign.items()},
        "by_label": _count_by(all_benign, "label"),
        "targets": {
            "same_oracle": args.target_same_oracle,
            "same_protocol": args.target_same_protocol,
            "cross_protocol": args.target_cross_protocol,
        },
        "sql_dir": str(sql_dir),
        "selection_policy": "hard benign candidates using same-oracle, same-protocol, and deterministic cross-protocol hash sampling; no rank truncation, scoring, or nondeterministic sampling",
        "safety_boundary": "read-only historical Dune/RPC evidence; no chain writes, no write methods, no private keys, no attack simulation",
    }
    write_json(output_dir / "eval_manifest.json", manifest)

    design = [
        "# Benign Evaluation Dataset",
        "",
        "This dataset is case-aware: positives come from the six active materialized cases, while benign candidates are sampled from the same oracle-scope surface without using rank truncation, scoring formulas, amount ranking, or nondeterministic random sampling.",
        "",
        "## Current Counts",
        "",
        f"- Positive cases: `{len(positives)}`",
        f"- Benign candidates: `{len(all_benign)}`",
        f"- Benign verified rows: `{len(verified)}`",
        f"- Unknown negatives: `{len(unknown)}`",
        f"- False-positive denominator: `{len(verified)}`",
        "",
        "## Strata",
        "",
        f"- Same-oracle: `{len(benign['same_oracle'])}`",
        f"- Same-protocol: `{len(benign['same_protocol'])}`",
        f"- Cross-protocol oracle-scope: `{len(benign['cross_protocol'])}`",
        "",
        "## Local Verification Policy",
        "",
        "Only `benign_verified` rows enter the false-positive denominator. `unknown_negative` rows are a review/materialization queue and must be replayed locally before being treated as safe negatives.",
        "",
        "## SQL",
        "",
        f"Rendered Dune SQL: `{sql_dir}`",
    ]
    results_design = results_dir / "benign_eval_dataset_design.md"
    ensure_dir(results_design.parent)
    results_design.write_text("\n".join(design) + "\n", encoding="utf-8")

    fp_report = [
        "# Benign False Positive Report",
        "",
        "Replay has not been executed by this builder. It prepares the labelled evaluation inputs and separates verified benign rows from unknown negatives.",
        "",
        f"- Positive recall denominator: `{len(positives)}`",
        f"- False-positive denominator: `{len(verified)}`",
        "- Expected benign replay result: `violation=false`, no attacker localization, no violated K-style constraint.",
        "",
        "Run the local verifier/materializer over `artifacts/eval_dataset/*.jsonl` before reporting final FP metrics.",
    ]
    fp_path = results_dir / "eval_false_positive_report.md"
    fp_path.write_text("\n".join(fp_report) + "\n", encoding="utf-8")


def build_dataset(args: argparse.Namespace) -> Dict[str, Path]:
    chains = _parse_csv(args.chains)
    output_dir = Path(args.output_dir)
    results_dir = Path(args.results_dir)
    sql_dir = output_dir / "sql"
    ensure_dir(output_dir)

    contexts = _case_context_rows(chains)
    positives = build_positive_cases(chains)
    write_sql(sql_dir, args.start, args.end, chains, contexts, args)

    export_rows = _read_export_rows(Path(args.input_dir) if args.input_dir else None)
    benign = ingest_benign_exports(export_rows, contexts)

    outputs = {
        "positive_cases": output_dir / "positive_cases.jsonl",
        "same_oracle": output_dir / "benign_same_oracle.jsonl",
        "same_protocol": output_dir / "benign_same_protocol.jsonl",
        "cross_protocol": output_dir / "benign_cross_protocol.jsonl",
        "manifest": output_dir / "eval_manifest.json",
        "sql_manifest": sql_dir / "manifest.json",
        "design_report": results_dir / "benign_eval_dataset_design.md",
        "fp_report": results_dir / "eval_false_positive_report.md",
    }
    write_jsonl(outputs["positive_cases"], positives)
    write_jsonl(outputs["same_oracle"], benign["same_oracle"])
    write_jsonl(outputs["same_protocol"], benign["same_protocol"])
    write_jsonl(outputs["cross_protocol"], benign["cross_protocol"])
    write_reports(output_dir, positives, benign, sql_dir, results_dir, args)
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the case-aware benign evaluation dataset scaffold.")
    parser.add_argument("--chains", default=",".join(DEFAULT_CHAINS))
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--target-same-oracle", type=int, default=200)
    parser.add_argument("--target-same-protocol", type=int, default=200)
    parser.add_argument("--target-cross-protocol", type=int, default=500)
    parser.add_argument("--same-oracle-buckets", type=int, default=32)
    parser.add_argument("--same-protocol-buckets", type=int, default=8)
    parser.add_argument("--cross-protocol-buckets", type=int, default=1)
    parser.add_argument("--incident-guard-hours", type=int, default=24)
    parser.add_argument("--input-dir", default="", help="Optional Dune export directory to ingest into benign JSONL files.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--results-dir", default=str(repo_path("results")))
    args = parser.parse_args()

    outputs = build_dataset(args)
    print("Built benign evaluation dataset scaffold.")
    for name, path in outputs.items():
        print(f"- {name}: {path}")
    if not args.input_dir:
        print("- Dune was not executed and no Dune export was ingested.")


if __name__ == "__main__":
    main()
