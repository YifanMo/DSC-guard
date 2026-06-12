#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, List

from common import ensure_dir, repo_path


DEFAULT_START = "2022-01-01"
DEFAULT_END = "2026-05-23"
DEFAULT_CHAINS = ["ethereum", "bnb", "base", "avalanche_c"]
OUTPUT_DIR = repo_path("artifacts", "broad_search", "oracle_scope_minimal_filter")


def _sql_string(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _chains(values: Iterable[str]) -> List[str]:
    aliases = {"bsc": "bnb", "avalanche": "avalanche_c", "eth": "ethereum"}
    chains: List[str] = []
    for raw in values:
        chain = aliases.get(raw.strip().lower(), raw.strip().lower())
        if chain and chain not in chains:
            chains.append(chain)
    return chains


def _chains_values(chains: Iterable[str]) -> str:
    return ",\n    ".join(f"({_sql_string(chain)})" for chain in chains)


def _chains_in(chains: Iterable[str]) -> str:
    return ", ".join(_sql_string(chain) for chain in chains)


def _params_cte(start: str, end: str, chains: Iterable[str]) -> str:
    return f"""params AS (
  SELECT DATE {_sql_string(start)} AS start_date, DATE {_sql_string(end)} AS end_date
),
chains(chain) AS (
  VALUES
    {_chains_values(chains)}
)"""


def _oracle_topic_rules(include_contextual_s5: bool = False) -> str:
    rows = [
        (
            "0xf6a97944f31ea060dfde0566e4167c1a1082551e64b60ecb14d599a9d023d451",
            "S1_ORACLE_PRICE_REPORTING",
            "R_S1_CHAINLINK_NEW_TRANSMISSION",
            "Chainlink OCR NewTransmission",
            "false",
        ),
        (
            "0x0109fc6f55cf40689f02fbaad7af7fe7bbac8a3d2186600afc7d3e10cac60271",
            "S1_ORACLE_PRICE_REPORTING",
            "R_S1_CHAINLINK_NEW_ROUND",
            "Chainlink NewRound",
            "false",
        ),
        (
            "0x0559884fd3a460db3073b7fc896cc77986f16e378210ded43186175bf646fc5f",
            "S1_ORACLE_PRICE_REPORTING",
            "R_S1_CHAINLINK_ANSWER_UPDATED",
            "Chainlink AnswerUpdated",
            "false",
        ),
        (
            "0x22c5b7b2d8561d39f7f210b6b326a1aa69f15311163082308ac4877db6339dc1",
            "S2_FEED_BINDING_CONFIG",
            "R_S2_FEED_BINDING_UPDATE",
            "asset/feed binding update",
            "false",
        ),
        (
            "0xd9e7d1778ca05570ced72c9aeb12a41fcc76f7f57ea25853dea228f8836d0022",
            "S2_FEED_BINDING_CONFIG",
            "R_S2_MOONWELL_SET_FEED",
            "oracle wrapper setFeed-style config",
            "false",
        ),
        (
            "0xaef9ecb0b33da1a5a170fdeed3accb3e88c5257f51d6faa019cea841b864d049",
            "S2_FEED_BINDING_CONFIG",
            "R_S2_SET_TOKEN_PRICE_FEED",
            "SetTokenPriceFeed",
            "false",
        ),
        (
            "0xd52b2b9b7e9ee655fcb95d2e5b9e0c9f69e7ef2b8e9d2d0ea78402d576d22e22",
            "S2_FEED_BINDING_CONFIG",
            "R_S2_NEW_PRICE_ORACLE",
            "NewPriceOracle",
            "false",
        ),
        (
            "0xa8c96090e146ce1076efa81e5424d56e13d5c3854943f7926406c12d15d6dbe9",
            "S3_PRICE_COMPOSITION_OR_ROUTE_CONFIG",
            "R_S3_SET_ROUTE",
            "SetRoute",
            "false",
        ),
        (
            "0xd1b3641b73e6c323671a85001b02db34d4e63a7fa6d264896138094dd6b8bfdf",
            "S3_PRICE_COMPOSITION_OR_ROUTE_CONFIG",
            "R_S3_SET_TIME_GAP",
            "SetTimeGap",
            "false",
        ),
        (
            "0xdb99134445c07379338e9d1d3ca5cd958bd95af80ce8e9b6d73882f9b12002e4",
            "S3_PRICE_COMPOSITION_OR_ROUTE_CONFIG",
            "R_S3_TOKEN_REMAPPING",
            "token remapping",
            "false",
        ),
        (
            "0xd6b3a81dd8b7dc419d8d0f20797397ea2eaba914386b89898aa638438803a1ec",
            "S4_GOVERNANCE_EXECUTED_ORACLE_CONFIG",
            "R_S4_GOVERNANCE_EXECUTED_ORACLE_CHANGE",
            "governance executed oracle change",
            "false",
        ),
    ]
    if include_contextual_s5:
        rows.extend(
            [
                (
                    "0x7f26b83ff96e1f2b6a682f133852f6798a09c465da95921460cefb3847402498",
                    "S5_CONTEXTUAL_ORACLE_PROXY_WIRING",
                    "R_S5_CONTEXTUAL_INITIALIZED",
                    "Initialized on oracle-path contract",
                    "true",
                ),
                (
                    "0x8be0079c531659141344cd1fd0a4f28419497f9722a3daafe3b4186f6b6457e0",
                    "S5_CONTEXTUAL_ORACLE_PROXY_WIRING",
                    "R_S5_CONTEXTUAL_OWNERSHIP_TRANSFERRED",
                    "OwnershipTransferred on oracle-path contract",
                    "true",
                ),
            ]
        )
    values = ",\n    ".join(
        f"({topic}, {_sql_string(scope)}, {_sql_string(rule)}, {_sql_string(name)}, {is_contextual})"
        for topic, scope, rule, name, is_contextual in rows
    )
    return f"""oracle_topic_rules(topic0, scope_class, rule_id, topic_name, contextual_only) AS (
  VALUES
    {values}
)"""


def _impact_topic_rules() -> str:
    values = [
        ("0x3ab23ab0d51cccc0c3085aec51f99228625aa1a922b3a8ca89a26b0f2027a1a5", "R_IMPACT_MARKET_ENTERED", "MarketEntered"),
        ("0x4c209b5fc8ad50758f13e2e1088ba56a560dff690a1c6fef26394f4c03821c4f", "R_IMPACT_SUPPLY_OR_MINT", "Compound Mint"),
        ("0x4dec04e750ca11537cabcd8a9eab06494de08da3735bc8871cd41250e190bc04", "R_IMPACT_SUPPLY_OR_MINT", "ERC4626 Deposit"),
        ("0xde6857219544bb5b7746f48ed30be6386fefc61b2f864cacf559893bf50fd951", "R_IMPACT_SUPPLY_OR_MINT", "Aave Deposit"),
        ("0x13ed6866d4e1ee6da46f845c46d7e54120883d75c5ea9a2dacc1c4ca8984ab80", "R_IMPACT_BORROW", "Compound Borrow"),
        ("0xc6a898309e823ee50bac64e45ca8adba6690e99e7841c45d754e2a38e9019d9b", "R_IMPACT_BORROW", "Aave Borrow"),
        ("0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52", "R_IMPACT_LIQUIDATION", "LiquidateBorrow"),
        ("0x00058a56ea94653cdf4f152d227ace22d4c00ad99e2a43f58cb7d9e3feb295f2", "R_IMPACT_COLLATERAL_ENABLED", "ReserveUsedAsCollateralEnabled"),
    ]
    return "impact_topic_rules(topic0, impact_rule_id, topic_name) AS (\n  VALUES\n    " + ",\n    ".join(
        f"({topic}, {_sql_string(rule)}, {_sql_string(name)})" for topic, rule, name in values
    ) + "\n)"


def broad_count_sql(start: str, end: str, chains: Iterable[str]) -> str:
    return f"""-- Layer 1: Broad oracle activity count.
-- Counts oracle_activity_log_scope remotely in Dune. This is not a suspicious
-- candidate count and it does not download log rows locally.
WITH
{_params_cte(start, end, chains)},
{_oracle_topic_rules(include_contextual_s5=False)},
oracle_scope_logs AS (
  SELECT
    l.blockchain AS chain,
    year(l.block_time) AS year,
    r.scope_class,
    l.tx_hash,
    l.contract_address,
    CAST(l.tx_hash AS varchar) || ':' || CAST(l.index AS varchar) AS log_key
  FROM evms.logs l
  JOIN chains c ON c.chain = l.blockchain
  JOIN oracle_topic_rules r ON r.topic0 = l.topic0
  JOIN params p ON l.block_date BETWEEN p.start_date AND p.end_date
  WHERE r.contextual_only = false
)
SELECT
  chain,
  year,
  scope_class,
  COUNT(*) AS oracle_scope_log_count,
  approx_distinct(tx_hash) AS oracle_scope_tx_count,
  approx_distinct(contract_address) AS oracle_scope_contract_count,
  'broad_oracle_activity_surface' AS dataset_layer
FROM oracle_scope_logs
GROUP BY 1, 2, 3
UNION ALL
SELECT
  'all_active_case_chains' AS chain,
  year,
  scope_class,
  COUNT(*) AS oracle_scope_log_count,
  approx_distinct(tx_hash) AS oracle_scope_tx_count,
  approx_distinct(contract_address) AS oracle_scope_contract_count,
  'broad_oracle_activity_surface' AS dataset_layer
FROM oracle_scope_logs
GROUP BY 2, 3
ORDER BY chain, year, scope_class;
"""


def _closure_ctes(start: str, end: str, chains: Iterable[str]) -> str:
    return f"""WITH
{_params_cte(start, end, chains)},
{_oracle_topic_rules(include_contextual_s5=True)},
{_impact_topic_rules()},
oracle_path_contracts AS (
  SELECT DISTINCT
    blockchain AS chain,
    address AS contract_address
  FROM labels.addresses
  WHERE blockchain IN ({_chains_in(chains)})
    AND regexp_like(lower(COALESCE(name, '')), '(oracle|price|feed|aggregator|router|wrapper)')
),
oracle_boundary_logs AS (
  SELECT
    l.blockchain AS chain,
    year(l.block_time) AS trigger_year,
    l.block_time AS trigger_time,
    l.block_number AS trigger_block,
    l.tx_hash AS boundary_tx_hash,
    l.contract_address AS boundary_contract,
    l.topic0,
    r.scope_class,
    r.rule_id AS boundary_rule_id,
    r.topic_name AS boundary_topic_name,
    CASE
      WHEN r.scope_class = 'S1_ORACLE_PRICE_REPORTING'
        THEN abs(CAST(bytearray_to_int256(l.topic1) AS double) / 1e8)
      ELSE NULL
    END AS normalized_answer
  FROM evms.logs l
  JOIN chains c ON c.chain = l.blockchain
  JOIN oracle_topic_rules r ON r.topic0 = l.topic0
  LEFT JOIN oracle_path_contracts opc
    ON opc.chain = l.blockchain
   AND opc.contract_address = l.contract_address
  JOIN params p ON l.block_date BETWEEN p.start_date AND p.end_date
  WHERE r.contextual_only = false
     OR opc.contract_address IS NOT NULL
),
market_inventory AS (
  SELECT DISTINCT
    e.blockchain AS chain,
    e.contract_address AS market_contract,
    e.symbol,
    e.name,
    regexp_extract(lower(COALESCE(e.symbol, '') || ' ' || COALESCE(e.name, '')), '(^|[^a-z0-9])([abcmv][a-z0-9]{{2,}})', 2) AS market_token_source,
    regexp_replace(lower(COALESCE(e.name, e.symbol, 'unknown')), '( token| market| lending| pool| collateral| debt| stable| variable)', '') AS protocol_cluster_id
  FROM tokens.erc20 e
  WHERE e.blockchain IN ({_chains_in(chains)})
    AND regexp_like(lower(COALESCE(e.symbol, '') || ' ' || COALESCE(e.name, '')), '(^|[^a-z0-9])([abcmv][a-z0-9]{{2,}})')
    AND NOT regexp_like(lower(COALESCE(e.symbol, '') || ' ' || COALESCE(e.name, '')), '(debt|variabledebt|stabledebt|reward|staking|farm|lp token)')
),
impact_lending_logs AS (
  SELECT
    l.blockchain AS chain,
    l.block_time AS impact_time,
    l.block_number AS impact_block,
    l.tx_hash AS impact_tx_hash,
    tx."from" AS actor,
    l.contract_address AS market_contract,
    mi.protocol_cluster_id,
    ir.impact_rule_id,
    CAST(l.tx_hash AS varchar) || ':' || CAST(l.index AS varchar) AS impact_log_key
  FROM evms.logs l
  JOIN impact_topic_rules ir ON ir.topic0 = l.topic0
  JOIN market_inventory mi
    ON mi.chain = l.blockchain
   AND mi.market_contract = l.contract_address
  JOIN evms.transactions tx
    ON tx.blockchain = l.blockchain
   AND tx.hash = l.tx_hash
   AND tx.block_date BETWEEN DATE {_sql_string(start)} AND DATE {_sql_string(end)}
  JOIN params p ON l.block_date BETWEEN p.start_date AND p.end_date
),
same_protocol_oracle_config_impact AS (
  SELECT
    b.chain,
    b.trigger_year,
    CASE
      WHEN b.scope_class = 'S2_FEED_BINDING_CONFIG' THEN 'feed_binding_failure'
      ELSE 'price_composition_failure'
    END AS failure_class,
    b.boundary_tx_hash AS trigger_tx,
    b.trigger_block,
    b.trigger_time,
    MIN(i.impact_time) AS first_impact_time,
    MIN_BY(i.impact_tx_hash, i.impact_time) AS first_impact_tx,
    ARRAY_AGG(DISTINCT CAST(i.impact_tx_hash AS varchar)) AS impact_txs,
    COUNT(DISTINCT i.impact_tx_hash) AS impact_tx_count,
    approx_distinct(i.actor) AS actor_count,
    approx_distinct(i.market_contract) AS market_count,
    MIN_BY(i.protocol_cluster_id, i.impact_time) AS protocol_cluster_id,
    b.boundary_rule_id AS matched_rule,
    b.scope_class,
    CAST(NULL AS double) AS normalized_answer
  FROM oracle_boundary_logs b
  JOIN impact_lending_logs i
    ON i.chain = b.chain
   AND i.impact_time > b.trigger_time
   AND i.impact_time <= b.trigger_time + INTERVAL '72' HOUR
  WHERE b.scope_class IN (
    'S2_FEED_BINDING_CONFIG',
    'S3_PRICE_COMPOSITION_OR_ROUTE_CONFIG',
    'S4_GOVERNANCE_EXECUTED_ORACLE_CONFIG',
    'S5_CONTEXTUAL_ORACLE_PROXY_WIRING'
  )
  GROUP BY 1, 2, 3, 4, 5, 6, 14, 15
),
abnormal_oracle_impact AS (
  SELECT
    b.chain,
    b.trigger_year,
    'price_composition_failure' AS failure_class,
    b.boundary_tx_hash AS trigger_tx,
    b.trigger_block,
    b.trigger_time,
    MIN(i.impact_time) AS first_impact_time,
    MIN_BY(i.impact_tx_hash, i.impact_time) AS first_impact_tx,
    ARRAY_AGG(DISTINCT CAST(i.impact_tx_hash AS varchar)) AS impact_txs,
    COUNT(DISTINCT i.impact_tx_hash) AS impact_tx_count,
    approx_distinct(i.actor) AS actor_count,
    approx_distinct(i.market_contract) AS market_count,
    MIN_BY(i.protocol_cluster_id, i.impact_time) AS protocol_cluster_id,
    'R2_S1_ABNORMAL_PRICE_THEN_LENDING_IMPACT' AS matched_rule,
    b.scope_class,
    b.normalized_answer
  FROM oracle_boundary_logs b
  JOIN impact_lending_logs i
    ON i.chain = b.chain
   AND i.impact_time > b.trigger_time
   AND i.impact_time <= b.trigger_time + INTERVAL '24' HOUR
  WHERE b.scope_class = 'S1_ORACLE_PRICE_REPORTING'
    AND b.normalized_answer IS NOT NULL
    AND (b.normalized_answer <= 1 OR b.normalized_answer >= 100000)
  GROUP BY 1, 2, 3, 4, 5, 6, 14, 15, 16
),
same_actor_lending_impact AS (
  SELECT
    s.chain,
    s.actor,
    MIN(s.impact_time) AS first_supply_time,
    MIN_BY(s.impact_tx_hash, s.impact_time) AS first_supply_tx,
    MIN(b.impact_time) AS first_borrow_time,
    MIN_BY(b.impact_tx_hash, b.impact_time) AS first_borrow_tx,
    ARRAY_AGG(DISTINCT CAST(b.impact_tx_hash AS varchar)) AS borrow_txs,
    COUNT(DISTINCT b.impact_tx_hash) AS borrow_tx_count,
    MIN_BY(b.protocol_cluster_id, b.impact_time) AS protocol_cluster_id
  FROM impact_lending_logs s
  JOIN impact_lending_logs b
    ON b.chain = s.chain
   AND b.actor = s.actor
   AND b.impact_time > s.impact_time
   AND b.impact_time <= s.impact_time + INTERVAL '6' HOUR
  WHERE s.impact_rule_id IN ('R_IMPACT_SUPPLY_OR_MINT', 'R_IMPACT_COLLATERAL_ENABLED', 'R_IMPACT_MARKET_ENTERED')
    AND b.impact_rule_id = 'R_IMPACT_BORROW'
  GROUP BY 1, 2
),
freshness_candidates AS (
  SELECT
    b.chain,
    b.trigger_year,
    'freshness_handling_failure' AS failure_class,
    b.boundary_tx_hash AS trigger_tx,
    b.trigger_block,
    b.trigger_time,
    MIN(i.first_borrow_time) AS first_impact_time,
    MIN_BY(i.first_borrow_tx, i.first_borrow_time) AS first_impact_tx,
    ARRAY_AGG(DISTINCT CAST(u.tx AS varchar)) AS impact_txs,
    SUM(i.borrow_tx_count) AS impact_tx_count,
    approx_distinct(i.actor) AS actor_count,
    CAST(1 AS bigint) AS market_count,
    MIN_BY(i.protocol_cluster_id, i.first_borrow_time) AS protocol_cluster_id,
    'R3_LOWER_BOUND_OR_STALE_ANSWER_THEN_SUPPLY_BORROW_CLOSURE' AS matched_rule,
    b.scope_class,
    b.normalized_answer
  FROM oracle_boundary_logs b
  JOIN same_actor_lending_impact i
    ON i.chain = b.chain
   AND i.first_supply_time > b.trigger_time
   AND i.first_supply_time <= b.trigger_time + INTERVAL '48' HOUR
  CROSS JOIN UNNEST(ARRAY[i.first_supply_tx, i.first_borrow_tx]) AS u(tx)
  WHERE b.scope_class = 'S1_ORACLE_PRICE_REPORTING'
    AND b.normalized_answer > 0
    AND b.normalized_answer <= 1
  GROUP BY 1, 2, 3, 4, 5, 6, 14, 15, 16
),
closure_candidates AS (
  SELECT * FROM same_protocol_oracle_config_impact
  UNION ALL
  SELECT * FROM abnormal_oracle_impact
  UNION ALL
  SELECT * FROM freshness_candidates
)"""


def closure_candidates_sql(start: str, end: str, chains: Iterable[str]) -> str:
    return _closure_ctes(start, end, chains) + """
SELECT
  chain,
  trigger_year AS year,
  failure_class,
  CASE
    WHEN actor_count > 0 AND market_count > 0 AND impact_tx_count > 0
      AND failure_class IN ('feed_binding_failure', 'freshness_handling_failure')
      THEN 'A_replayable'
    WHEN impact_tx_count > 0 THEN 'B_high_confidence_incomplete'
    ELSE 'C_remote_anomaly_only'
  END AS evidence_tier,
  true AS has_trigger,
  true AS has_oracle_anomaly,
  impact_tx_count > 0 AS has_lending_impact,
  actor_count > 0 AS has_actor,
  first_impact_time > trigger_time AS has_temporal_order,
  impact_tx_count > 0 AND first_impact_tx IS NOT NULL AS has_replayable_constraint,
  trigger_tx AS boundary_tx_hash,
  trigger_block,
  trigger_time,
  first_impact_tx,
  impact_txs,
  impact_tx_count,
  actor_count AS candidate_actor_count,
  market_count AS candidate_market_count,
  date_diff('second', trigger_time, first_impact_time) AS trigger_to_impact_seconds,
  CAST(NULL AS double) AS impact_usd_known,
  protocol_cluster_id,
  matched_rule,
  CASE
    WHEN failure_class = 'feed_binding_failure' THEN 'S2 binding config plus same-window lending impact'
    WHEN failure_class = 'freshness_handling_failure' THEN 'lower-bound oracle answer plus same-actor supply-to-borrow closure'
    ELSE 'oracle config or abnormal oracle answer plus downstream borrow/liquidation'
  END AS closure_reason,
  CASE
    WHEN failure_class = 'freshness_handling_failure' AND normalized_answer <= 1 THEN 'impact_led_lower_bound'
    WHEN scope_class = 'S1_ORACLE_PRICE_REPORTING' THEN 'oracle_answer_outlier'
    ELSE 'oracle_config_log'
  END AS source_quality,
  CASE
    WHEN failure_class = 'freshness_handling_failure' THEN 2
    WHEN scope_class IN ('S2_FEED_BINDING_CONFIG', 'S3_PRICE_COMPOSITION_OR_ROUTE_CONFIG') THEN 1
    ELSE 2
  END AS source_quality_rank,
  'remote_candidate' AS dataset_layer,
  false AS already_materialized
FROM closure_candidates
WHERE first_impact_time > trigger_time
ORDER BY
  CASE
    WHEN actor_count > 0 AND market_count > 0 AND impact_tx_count > 0
      AND failure_class IN ('feed_binding_failure', 'freshness_handling_failure') THEN 1
    WHEN impact_tx_count > 0 THEN 2
    ELSE 3
  END,
  trigger_to_impact_seconds ASC NULLS LAST,
  impact_tx_count DESC,
  source_quality_rank ASC,
  chain,
  year;
"""


def minimal_replay_queue_sql(start: str, end: str, chains: Iterable[str]) -> str:
    return _closure_ctes(start, end, chains) + """
, tiered_candidates AS (
  SELECT
    chain,
    trigger_year AS year,
    failure_class,
    CASE
      WHEN actor_count > 0 AND market_count > 0 AND impact_tx_count > 0
        AND failure_class IN ('feed_binding_failure', 'freshness_handling_failure')
        THEN 'A_replayable'
      WHEN impact_tx_count > 0 THEN 'B_high_confidence_incomplete'
      ELSE 'C_remote_anomaly_only'
    END AS evidence_tier,
    trigger_tx AS boundary_tx_hash,
    first_impact_tx,
    impact_txs,
    impact_tx_count,
    date_diff('second', trigger_time, first_impact_time) AS trigger_to_impact_seconds,
    protocol_cluster_id,
    matched_rule,
    CASE
      WHEN failure_class = 'feed_binding_failure' THEN 1
      WHEN failure_class = 'price_composition_failure' THEN 2
      WHEN failure_class = 'freshness_handling_failure' THEN 2
      ELSE 1
    END AS max_impact_receipts,
    CASE
      WHEN failure_class = 'price_composition_failure' THEN 3
      ELSE 2
    END AS estimated_abi_requests
  FROM closure_candidates
  WHERE first_impact_time > trigger_time
)
SELECT
  chain,
  year,
  failure_class,
  evidence_tier,
  boundary_tx_hash,
  first_impact_tx,
  slice(impact_txs, 1, max_impact_receipts) AS minimal_replay_txs,
  1 AS estimated_trigger_receipts,
  least(impact_tx_count, max_impact_receipts) AS estimated_impact_receipts,
  1 + least(impact_tx_count, max_impact_receipts) AS estimated_total_rpc_requests,
  estimated_abi_requests,
  trigger_to_impact_seconds,
  protocol_cluster_id,
  matched_rule,
  'download_minimal_causal_trace' AS materialization_action
FROM tiered_candidates
WHERE evidence_tier = 'A_replayable'
   OR (
      evidence_tier = 'B_high_confidence_incomplete'
      AND impact_tx_count > 0
      AND trigger_to_impact_seconds IS NOT NULL
      AND trigger_to_impact_seconds BETWEEN 0 AND 259200
   )
ORDER BY
  CASE evidence_tier
    WHEN 'A_replayable' THEN 1
    WHEN 'B_high_confidence_incomplete' THEN 2
    ELSE 3
  END,
  trigger_to_impact_seconds ASC NULLS LAST,
  impact_tx_count DESC,
  chain,
  year;
"""


def case_hit_validation_sql(chains: Iterable[str]) -> str:
    chain_in = _chains_in(chains)
    return f"""-- Case-hit validation for the minimal oracle-scope filter.
-- Known case tx hashes are used only as an evaluation set. The broad candidate
-- query above does not depend on these hashes.
WITH evidence_txs(case_id, chain, failure_class, evidence_scope, tx_hash, tx_date, expected_rule) AS (
  VALUES
    ('ploutos', 'ethereum', 'feed_binding_failure', 'pre_attack_boundary_tx', 0xcfedf63b37a6cd45b21bc94e3de5412fee0765e7dad6b7c8561a01cebd193ab6, DATE '2026-02-26', 'R1'),
    ('ploutos', 'ethereum', 'feed_binding_failure', 'first_attack_tx', 0xa17dc37e1b65c65d20042212fb834974f7faaa961442e3fc05393778705f8474, DATE '2026-02-26', 'R1'),
    ('moonwell_cbeth', 'base', 'price_composition_failure', 'pre_attack_boundary_tx', 0xd26baf29dcba7bf66db4be17b46a49bb4dacca41ace968c98c8a5b09a03ae812, DATE '2026-02-15', 'R2'),
    ('moonwell_cbeth', 'base', 'price_composition_failure', 'first_attack_tx', 0xa49a27498d82db8b093b2fcf969f2091f74dab437ee24ab2c43a182927335c84, DATE '2026-02-15', 'R2'),
    ('moonwell_wrseth', 'base', 'price_composition_failure', 'pre_attack_boundary_tx', 0x05098c93b19d707b54282e904756ad7975a73f5472355bd1c336a681b099dd36, DATE '2025-11-04', 'R2'),
    ('moonwell_wrseth', 'base', 'price_composition_failure', 'first_attack_tx', 0x229caeb87e0b6c31afad950150d2ba05a8d7fe823c9e5c05af63b4150b8f6cc6, DATE '2025-11-04', 'R2'),
    ('blueberry_faulty_oracle', 'ethereum', 'price_composition_failure', 'pre_attack_boundary_tx', 0xebc5b8def4a740070abdea92597dafa415df71c8160baad53bf8304546ba5fd4, DATE '2024-02-22', 'R2'),
    ('blueberry_faulty_oracle', 'ethereum', 'price_composition_failure', 'first_attack_tx', 0xf0464b01d962f714eee9d4392b2494524d0e10ce3eb3723873afd1346b8b06e4, DATE '2024-02-23', 'R2'),
    ('venus_luna', 'bnb', 'freshness_handling_failure', 'pre_attack_boundary_tx', 0xa73bcdba45d34dde372a3284ef4749004a76b2e04be345c602c99d60f4048d4f, DATE '2022-05-12', 'R3'),
    ('venus_luna', 'bnb', 'freshness_handling_failure', 'first_attack_tx', 0xf5004eb392b1e9403cb5d5e40d11981352d6afe9214d0896cc55fb111e0ff41f, DATE '2022-05-12', 'R3'),
    ('blizz_luna', 'avalanche_c', 'freshness_handling_failure', 'pre_attack_boundary_tx', 0x6b5f6f5b620489aa6616c7e0b4fdd9df712ef47fbd9ba9acf9dedb8cd2207473, DATE '2022-05-12', 'R3'),
    ('blizz_luna', 'avalanche_c', 'freshness_handling_failure', 'first_attack_tx', 0xde6ed25cc454d434fb1cb9838bd366672b08cb9e43ff71162f5425524e850214, DATE '2022-05-13', 'R3')
),
topic_rules(topic0, rule_family, rule_id, semantic_boundary) AS (
  VALUES
    (0xf6a97944f31ea060dfde0566e4167c1a1082551e64b60ecb14d599a9d023d451, 'R2_R3_ORACLE_UPDATE', 'R_PRE_CHAINLINK_ORACLE_UPDATE', true),
    (0x0109fc6f55cf40689f02fbaad7af7fe7bbac8a3d2186600afc7d3e10cac60271, 'R2_R3_ORACLE_UPDATE', 'R_PRE_CHAINLINK_ORACLE_UPDATE', true),
    (0x0559884fd3a460db3073b7fc896cc77986f16e378210ded43186175bf646fc5f, 'R2_R3_ORACLE_UPDATE', 'R_PRE_CHAINLINK_ORACLE_UPDATE', true),
    (0x22c5b7b2d8561d39f7f210b6b326a1aa69f15311163082308ac4877db6339dc1, 'R1_CONFIG', 'R_PRE_FEED_BINDING_CONFIG', true),
    (0xd9e7d1778ca05570ced72c9aeb12a41fcc76f7f57ea25853dea228f8836d0022, 'R2_CONFIG', 'R_PRE_PRICE_COMPOSITION_CONFIG', true),
    (0xd6b3a81dd8b7dc419d8d0f20797397ea2eaba914386b89898aa638438803a1ec, 'R2_CONFIG', 'R_PRE_GOVERNANCE_EXECUTION', true),
    (0xa8c96090e146ce1076efa81e5424d56e13d5c3854943f7926406c12d15d6dbe9, 'R2_CONFIG', 'R_PRE_ORACLE_PATH_CONFIG', true),
    (0xaef9ecb0b33da1a5a170fdeed3accb3e88c5257f51d6faa019cea841b864d049, 'R2_CONFIG', 'R_PRE_ORACLE_PATH_CONFIG', true),
    (0xd1b3641b73e6c323671a85001b02db34d4e63a7fa6d264896138094dd6b8bfdf, 'R2_CONFIG', 'R_PRE_ORACLE_PATH_CONFIG', true),
    (0x3ab23ab0d51cccc0c3085aec51f99228625aa1a922b3a8ca89a26b0f2027a1a5, 'IMPACT', 'R_IMPACT_MARKET_ENTERED', true),
    (0x4c209b5fc8ad50758f13e2e1088ba56a560dff690a1c6fef26394f4c03821c4f, 'IMPACT', 'R_IMPACT_SUPPLY_OR_MINT', true),
    (0xde6857219544bb5b7746f48ed30be6386fefc61b2f864cacf559893bf50fd951, 'IMPACT', 'R_IMPACT_SUPPLY_OR_MINT', true),
    (0x13ed6866d4e1ee6da46f845c46d7e54120883d75c5ea9a2dacc1c4ca8984ab80, 'IMPACT', 'R_IMPACT_BORROW', true),
    (0xc6a898309e823ee50bac64e45ca8adba6690e99e7841c45d754e2a38e9019d9b, 'IMPACT', 'R_IMPACT_BORROW', true),
    (0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52, 'IMPACT', 'R_IMPACT_LIQUIDATION', true),
    (0x00058a56ea94653cdf4f152d227ace22d4c00ad99e2a43f58cb7d9e3feb295f2, 'IMPACT', 'R_IMPACT_COLLATERAL_ENABLED', true)
),
receipt_logs AS (
  SELECT
    e.case_id,
    e.chain,
    e.failure_class,
    e.evidence_scope,
    e.tx_hash,
    e.expected_rule,
    l.topic0,
    l.contract_address,
    l.index AS log_index
  FROM evidence_txs e
  LEFT JOIN evms.logs l
    ON l.blockchain = e.chain
   AND l.tx_hash = e.tx_hash
   AND l.block_date = e.tx_date
  WHERE e.chain IN ({chain_in})
),
topic_hits AS (
  SELECT
    r.*,
    t.rule_family,
    t.rule_id,
    t.semantic_boundary
  FROM receipt_logs r
  LEFT JOIN topic_rules t ON t.topic0 = r.topic0
)
SELECT
  case_id,
  chain,
  failure_class,
  evidence_scope,
  expected_rule,
  CAST(tx_hash AS varchar) AS tx_hash,
  COUNT(topic0) AS receipt_log_count,
  COUNT_IF(rule_id IS NOT NULL) AS matched_log_count,
  COUNT_IF(semantic_boundary) AS semantic_log_count,
  ARRAY_JOIN(ARRAY_SORT(ARRAY_AGG(DISTINCT rule_id) FILTER (WHERE rule_id IS NOT NULL)), ', ') AS matched_rules,
  COUNT_IF(semantic_boundary) > 0 AS covered_by_minimal_filter
FROM topic_hits
GROUP BY 1, 2, 3, 4, 5, 6
ORDER BY case_id, CASE evidence_scope WHEN 'pre_attack_boundary_tx' THEN 1 ELSE 2 END;
"""


def write_artifacts(output_dir: Path, start: str, end: str, chains: List[str]) -> None:
    ensure_dir(output_dir)
    files = {
        "01_broad_oracle_scope_count.sql": broad_count_sql(start, end, chains),
        "02_closure_candidates.sql": closure_candidates_sql(start, end, chains),
        "03_minimal_replay_queue.sql": minimal_replay_queue_sql(start, end, chains),
        "04_case_hit_validation.sql": case_hit_validation_sql(chains),
    }
    for name, sql in files.items():
        (output_dir / name).write_text(sql, encoding="utf-8")
    manifest = {
        "dataset": "oracle_scope_minimal_filter",
        "start": start,
        "end": end,
        "chains": chains,
        "layers": [
            "broad_oracle_activity_surface",
            "evidence_closure_candidates",
            "minimal_replay_bundle_queue",
            "case_hit_validation",
        ],
        "selection_policy": "evidence-closure gate only; no top-k, weighted score, or amount-ranked truncation",
        "local_download_policy": "download only minimal causal tx bundles for A_replayable and eligible B_high_confidence_incomplete candidates",
        "safety_boundary": "read-only historical Dune SQL generation; no RPC calls, no chain writes, no simulation, no private keys",
        "files": sorted(files),
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = [
        "# Oracle-Scope Minimal Filter",
        "",
        "This artifact renders Dune SQL for the three-layer dataset story: broad oracle activity, evidence-closure candidates, and minimal replay bundles.",
        "",
        f"- Time range: `{start}` to `{end}`",
        f"- Chains: `{', '.join(chains)}`",
        "- Selection: evidence-closure gates only; no top-k, candidate score, weighted score, or amount-ranked truncation.",
        "- Local download: first causal trace only.",
        "",
        "## SQL Files",
        "",
        "| file | purpose |",
        "|---|---|",
        "| `01_broad_oracle_scope_count.sql` | Count broad oracle activity logs by chain/year/scope class. |",
        "| `02_closure_candidates.sql` | Build R1/R2/R3 remote candidates with evidence tiers. |",
        "| `03_minimal_replay_queue.sql` | Select only A/B candidates for minimal receipt download. |",
        "| `04_case_hit_validation.sql` | Verify the six active cases against boundary and first-impact tx logs. |",
    ]
    (output_dir / "README.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    strategy = [
        "# Oracle-Scope Minimal Filter Strategy",
        "",
        "This strategy turns the broad oracle activity surface into a small local validation dataset without using top-k, weighted scores, or amount-ranked truncation.",
        "",
        "## Layers",
        "",
        "- Layer 1 counts `oracle_activity_log_scope` logs on Dune. This is the broad research surface, not the suspicious-candidate count.",
        "- Layer 2 keeps only candidates with an oracle boundary followed by lending impact under R1/R2/R3 evidence-closure rules.",
        "- Layer 3 schedules only the minimal causal replay bundle for A/B tier candidates.",
        "",
        "## Case Coverage",
        "",
        "- R1 covers Ploutos through feed-binding config plus downstream lending/flow impact.",
        "- R2 covers Moonwell cbETH, Moonwell wrsETH, and Blueberry through oracle config, abnormal oracle update, or oracle-path wiring plus borrow/liquidation impact.",
        "- R3 covers Venus and Blizz through lower-bound/stale Chainlink update plus same-account lending impact closure.",
        "",
        "## Safety Boundary",
        "",
        "- Dune SQL generation and optional Dune execution are read-only historical analysis.",
        "- The default script does not execute Dune, RPC, chain writes, simulations, or private-key operations.",
        "",
        f"Rendered SQL artifacts: `{output_dir}`",
    ]
    results_path = repo_path("results", "oracle_scope_minimal_filter_strategy.md")
    ensure_dir(results_path.parent)
    results_path.write_text("\n".join(strategy) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render oracle-scope minimal filter Dune SQL.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--chains", default=",".join(DEFAULT_CHAINS))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()
    chains = _chains(args.chains.split(","))
    write_artifacts(Path(args.output_dir), args.start, args.end, chains)
    print("Rendered oracle-scope minimal filter SQL.")
    print(f"- output: {args.output_dir}")
    print("- Dune was not executed.")


if __name__ == "__main__":
    main()
