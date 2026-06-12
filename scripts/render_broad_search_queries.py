#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, List

from common import ensure_dir, read_json, repo_path


DEFAULT_START = "2022-01-01"
DEFAULT_END = "2026-12-31"
DEFAULT_CHAINS = "ethereum,bnb,avalanche,base"
CHAIN_ALIASES = {
    "bsc": "bnb",
    "bnb": "bnb",
    "avalanche": "avalanche_c",
    "avalanche_c": "avalanche_c",
}


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _values(rows: Iterable[Iterable[str]]) -> str:
    return ",\n".join("(" + ", ".join(_sql_string(value) for value in row) + ")" for row in rows)


def parse_chains(value: str | Iterable[str] | None) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = value.split(",")
    else:
        raw_items = list(value)
    chains: List[str] = []
    for item in raw_items:
        chain = CHAIN_ALIASES.get(str(item).strip().lower(), str(item).strip().lower())
        if chain and chain not in chains:
            chains.append(chain)
    return chains


def _chain_filter(column: str, chains: List[str]) -> str:
    if not chains:
        return ""
    values = ", ".join(_sql_string(chain) for chain in chains)
    return f"\n    AND {column} IN ({values})"


def _chain_filter_with_legacy_variants(column: str, chains: List[str]) -> str:
    if not chains:
        return ""
    values = set(chains)
    if "avalanche_c" in values:
        values.add("avalanche")
    ordered = sorted(values)
    return f"\n    AND {column} IN ({', '.join(_sql_string(chain) for chain in ordered)})"


def _normalized_chain_expr(column: str) -> str:
    return f"CASE WHEN {column} = 'avalanche' THEN 'avalanche_c' ELSE {column} END"


def _protocol_cluster_expr(label_expr: str) -> str:
    return f"""CASE
      WHEN regexp_like(lower({label_expr}), 'aave') THEN 'aave'
      WHEN regexp_like(lower({label_expr}), 'compound') THEN 'compound'
      WHEN regexp_like(lower({label_expr}), 'venus') THEN 'venus'
      WHEN regexp_like(lower({label_expr}), 'moonwell') THEN 'moonwell'
      WHEN regexp_like(lower({label_expr}), 'blizz') THEN 'blizz'
      WHEN regexp_like(lower({label_expr}), 'ploutos') THEN 'ploutos'
      WHEN regexp_like(lower({label_expr}), 'benqi') THEN 'benqi'
      WHEN regexp_like(lower({label_expr}), 'morpho') THEN 'morpho'
      WHEN regexp_like(lower({label_expr}), 'radiant') THEN 'radiant'
      WHEN regexp_like(lower({label_expr}), 'silo') THEN 'silo'
      WHEN regexp_like(lower({label_expr}), 'granary') THEN 'granary'
      WHEN regexp_like(lower({label_expr}), 'lodestar') THEN 'lodestar'
      WHEN regexp_like(lower({label_expr}), 'geist') THEN 'geist'
      WHEN regexp_like(lower({label_expr}), 'cream') THEN 'cream'
      WHEN regexp_like(lower({label_expr}), 'euler') THEN 'euler'
      WHEN regexp_like(lower({label_expr}), 'inverse|iron bank') THEN 'inverse_iron_bank'
      WHEN regexp_like(lower({label_expr}), 'hundred finance') THEN 'hundred_finance'
      ELSE regexp_replace(lower(regexp_replace({label_expr}, '[^A-Za-z0-9 ]', ' ')), '\\\\s+', '_')
    END"""


def _asset_identity_expr(label_expr: str) -> str:
    return f"""CASE
      WHEN regexp_like(lower({label_expr}), 'cbeth') THEN 'CBETH'
      WHEN regexp_like(lower({label_expr}), 'wsteth') THEN 'WSTETH'
      WHEN regexp_like(lower({label_expr}), 'reth') THEN 'RETH'
      WHEN regexp_like(lower({label_expr}), '(btc|wbtc)') THEN 'BTC'
      WHEN regexp_like(lower({label_expr}), '(eth|weth)') THEN 'ETH'
      WHEN regexp_like(lower({label_expr}), 'usdc') THEN 'USDC'
      WHEN regexp_like(lower({label_expr}), 'usdt') THEN 'USDT'
      WHEN regexp_like(lower({label_expr}), 'dai') THEN 'DAI'
      WHEN regexp_like(lower({label_expr}), 'busd') THEN 'BUSD'
      WHEN regexp_like(lower({label_expr}), 'luna') THEN 'LUNA'
      WHEN regexp_like(lower({label_expr}), 'avax') THEN 'AVAX'
      WHEN regexp_like(lower({label_expr}), 'bnb') THEN 'BNB'
      WHEN regexp_like(lower({label_expr}), 'link') THEN 'LINK'
      ELSE NULL
    END"""


def _market_token_asset_expr(symbol_expr: str, name_expr: str) -> str:
    label_expr = f"COALESCE({symbol_expr}, '') || ' ' || COALESCE({name_expr}, '')"
    return f"""CASE
      WHEN regexp_like(lower(COALESCE({symbol_expr}, '')), '^(a|b|c|m|v)cbeth(\\\\.e)?$')
        OR regexp_like(lower({label_expr}), '(^|[^a-z0-9])cbeth([^a-z0-9]|$)') THEN 'CBETH'
      WHEN regexp_like(lower(COALESCE({symbol_expr}, '')), '^(a|b|c|m|v)wsteth(\\\\.e)?$')
        OR regexp_like(lower({label_expr}), '(^|[^a-z0-9])wsteth([^a-z0-9]|$)') THEN 'WSTETH'
      WHEN regexp_like(lower(COALESCE({symbol_expr}, '')), '^(a|b|c|m|v)reth(\\\\.e)?$')
        OR regexp_like(lower({label_expr}), '(^|[^a-z0-9])reth([^a-z0-9]|$)') THEN 'RETH'
      WHEN regexp_like(lower(COALESCE({symbol_expr}, '')), '^(a|b|c|m|v)(wbtc|btc)(\\\\.e)?$')
        OR regexp_like(lower({label_expr}), '(^|[^a-z0-9])(wbtc|btc)([^a-z0-9]|$)') THEN 'BTC'
      WHEN regexp_like(lower(COALESCE({symbol_expr}, '')), '^(a|b|c|m|v)(weth|eth)(\\\\.e)?$')
        OR regexp_like(lower({label_expr}), '(^|[^a-z0-9])(weth|eth)([^a-z0-9]|$)') THEN 'ETH'
      WHEN regexp_like(lower(COALESCE({symbol_expr}, '')), '^(a|b|c|m|v)usdc(\\\\.e|bc)?$')
        OR regexp_like(lower({label_expr}), '(^|[^a-z0-9])(usdc|usd coin)([^a-z0-9]|$)') THEN 'USDC'
      WHEN regexp_like(lower(COALESCE({symbol_expr}, '')), '^(a|b|c|m|v)usdt(\\\\.e)?$')
        OR regexp_like(lower({label_expr}), '(^|[^a-z0-9])usdt([^a-z0-9]|$)') THEN 'USDT'
      WHEN regexp_like(lower(COALESCE({symbol_expr}, '')), '^(a|b|c|m|v)dai(\\\\.e)?$')
        OR regexp_like(lower({label_expr}), '(^|[^a-z0-9])dai([^a-z0-9]|$)') THEN 'DAI'
      WHEN regexp_like(lower(COALESCE({symbol_expr}, '')), '^(a|b|c|m|v)busd(\\\\.e)?$')
        OR regexp_like(lower({label_expr}), '(^|[^a-z0-9])busd([^a-z0-9]|$)') THEN 'BUSD'
      WHEN regexp_like(lower(COALESCE({symbol_expr}, '')), '^(a|b|c|m|v)luna(\\\\.e)?$')
        OR regexp_like(lower({label_expr}), '(^|[^a-z0-9])luna([^a-z0-9]|$)') THEN 'LUNA'
      WHEN regexp_like(lower(COALESCE({symbol_expr}, '')), '^(a|b|c|m|v)(wavax|avax)(\\\\.e)?$')
        OR regexp_like(lower({label_expr}), '(^|[^a-z0-9])(wavax|avax)([^a-z0-9]|$)') THEN 'AVAX'
      WHEN regexp_like(lower(COALESCE({symbol_expr}, '')), '^(a|b|c|m|v)bnb(\\\\.e)?$')
        OR regexp_like(lower({label_expr}), '(^|[^a-z0-9])bnb([^a-z0-9]|$)') THEN 'BNB'
      WHEN regexp_like(lower(COALESCE({symbol_expr}, '')), '^(a|b|c|m|v)link(\\\\.e)?$')
        OR regexp_like(lower({label_expr}), '(^|[^a-z0-9])link([^a-z0-9]|$)') THEN 'LINK'
      WHEN regexp_like(lower(COALESCE({symbol_expr}, '')), '^(a|b|c|m|v)aave(\\\\.e)?$')
        OR regexp_like(lower({label_expr}), '(^|[^a-z0-9])aave([^a-z0-9]|$)') THEN 'AAVE'
      WHEN regexp_like(lower(COALESCE({symbol_expr}, '')), '^(a|b|c|m|v)mim(\\\\.e)?$')
        OR regexp_like(lower({label_expr}), '(^|[^a-z0-9])mim([^a-z0-9]|$)') THEN 'MIM'
      WHEN regexp_like(lower(COALESCE({symbol_expr}, '')), '^(a|b|c|m|v)qi(\\\\.e)?$')
        OR regexp_like(lower({label_expr}), '(^|[^a-z0-9])qi([^a-z0-9]|$)') THEN 'QI'
      WHEN regexp_like(lower(COALESCE({symbol_expr}, '')), '^(a|b|c|m|v)spell(\\\\.e)?$')
        OR regexp_like(lower({label_expr}), '(^|[^a-z0-9])spell([^a-z0-9]|$)') THEN 'SPELL'
      WHEN regexp_like(lower(COALESCE({symbol_expr}, '')), '^(a|b|c|m|v)joe(\\\\.e)?$')
        OR regexp_like(lower({label_expr}), '(^|[^a-z0-9])joe([^a-z0-9]|$)') THEN 'JOE'
      WHEN regexp_like(lower(COALESCE({symbol_expr}, '')), '^(a|b|c|m|v)crv(\\\\.e)?$')
        OR regexp_like(lower({label_expr}), '(^|[^a-z0-9])crv([^a-z0-9]|$)') THEN 'CRV'
      WHEN regexp_like(lower(COALESCE({symbol_expr}, '')), '^(a|b|c|m|v)tusd(\\\\.e)?$')
        OR regexp_like(lower({label_expr}), '(^|[^a-z0-9])tusd([^a-z0-9]|$)') THEN 'TUSD'
      WHEN regexp_like(lower(COALESCE({symbol_expr}, '')), '^(a|b|c|m|v)alpha(\\\\.e)?$')
        OR regexp_like(lower({label_expr}), '(^|[^a-z0-9])alpha([^a-z0-9]|$)') THEN 'ALPHA'
      ELSE NULL
    END"""


def _generic_market_cluster_expr(label_expr: str) -> str:
    return f"""COALESCE(
      NULLIF(
        regexp_replace(
          regexp_replace(
            regexp_replace(
              lower(COALESCE({label_expr}, 'unknown_market')),
              '(^|[^a-z0-9])(cbeth|wsteth|reth|wbtc|btc|weth|eth|usdc|usd coin|usdt|dai|busd|luna|wavax|avax|bnb|link|aave|mim|qi|spell|joe|crv|tusd|alpha)([^a-z0-9]|$)',
              ' '
            ),
            '[^a-z0-9]+',
            '_'
          ),
          '^_+|_+$',
          ''
        ),
        ''
      ),
      'unknown_market_cluster'
    )"""


def _inventory_cte(chains: List[str]) -> str:
    label_chain_filter = _chain_filter("blockchain", chains)
    token_chain_filter = _chain_filter("blockchain", chains)
    protocol_pattern = "(aave|compound|venus|moonwell|blizz|ploutos|benqi|morpho|radiant|silo|granary|lodestar|geist|cream|euler|inverse|iron bank|hundred finance)"
    market_token_pattern = "(venus|moonwell|blizz|ploutos|benqi|aave|compound|morpho|radiant|silo|granary|lodestar|geist|cream|euler|inverse|iron bank|^c(usdc|usdt|dai|weth|wbtc|eth|luna|bnb|avax|cbeth|wsteth|reth|link|btc|busd|usdbc)($|[^a-z0-9])|^v(usdc|usdt|dai|weth|wbtc|eth|luna|bnb|avax|busd)($|[^a-z0-9])|^m(usdc|usdt|dai|weth|wbtc|eth|cbeth)($|[^a-z0-9])|^b(usdc|usdt|dai|weth|wbtc|eth|luna|avax)($|[^a-z0-9])|^a(usdc|usdt|dai|weth|wbtc|eth|avax|link)($|[^a-z0-9]))"
    return f"""lending_market_inventory AS (
  SELECT DISTINCT
    blockchain,
    address,
    name AS protocol_label,
    {_protocol_cluster_expr("name")} AS protocol_cluster_id,
    CASE
      WHEN regexp_like(lower(name), '(oracle|price|feed|chainlink)') THEN 'oracle_or_feed'
      WHEN regexp_like(lower(name), '(govern|timelock|admin|proxy)') THEN 'governance_or_admin'
      ELSE 'lending_label'
    END AS inventory_role,
    'labels.addresses' AS inventory_source
  FROM labels.addresses
  WHERE regexp_like(lower(name), '{protocol_pattern}')
    {label_chain_filter.strip()}

  UNION

  SELECT DISTINCT
    blockchain,
    contract_address AS address,
    COALESCE(name, symbol, 'unknown_market_token') AS protocol_label,
    {_protocol_cluster_expr("COALESCE(name, symbol, 'unknown_market_token')")} AS protocol_cluster_id,
    'market_token' AS inventory_role,
    'tokens.erc20' AS inventory_source
  FROM tokens.erc20
  WHERE regexp_like(lower(COALESCE(symbol, '') || ' ' || COALESCE(name, '')), '{market_token_pattern}')
    {token_chain_filter.strip()}
)"""


def seed_case_sql(manifest: Dict) -> str:
    rows = [
        (
            case["case"],
            case["chain"],
            case["failure_class"],
            case["trigger_event"],
            ",".join(case["impact_events"]),
        )
        for case in manifest["cases"]
    ]
    return f"""-- Seed set distilled from the local MVP evidence dataset.
-- This table is small and is used only to document how broad-search rules were derived.
WITH seed_cases(case_id, chain, failure_class, trigger_event, impact_events) AS (
  VALUES
{_values(rows)}
)
SELECT *
FROM seed_cases
ORDER BY failure_class, case_id;
"""


EVIDENCE_ORDER_BY = """ORDER BY
  CASE evidence_tier
    WHEN 'A_replayable' THEN 1
    WHEN 'B_high_confidence_incomplete' THEN 2
    WHEN 'C_remote_anomaly_only' THEN 3
    ELSE 4
  END,
  has_replayable_constraint DESC,
  has_actor DESC,
  trigger_to_impact_seconds ASC NULLS LAST,
  impact_usd_known DESC,
  impact_tx_count DESC,
  source_quality_rank ASC"""


def feed_binding_sql(start: str, end: str, chains: List[str] | None = None) -> str:
    parsed_chains = parse_chains(chains)
    inventory_cte = _inventory_cte(parsed_chains)
    return f"""-- R1: feed-binding failure broad search, Semantic Binding Closure v2.
-- Goal: find historical lending-protocol candidates where an asset-to-price-source
-- binding change is observable, the asset/feed identities appear inconsistent,
-- and same-protocol lending impact follows. Selector matches are not the primary
-- search scope; decoded metadata and evidence closure drive triage. Raw calldata
-- address binding is used only after decoded binding metadata narrows candidate
-- transactions.
-- This index-level candidate query is intentionally not top-k limited; local
-- downloads are bounded later by the materialization queue. Candidates are
-- tiered by evidence closure, not a weighted score.
WITH
params AS (
  SELECT
    DATE '{start}' AS start_date,
    DATE '{end}' AS end_date
),
{inventory_cte},
price_source_inventory AS (
  SELECT DISTINCT
    blockchain,
    address,
    name AS feed_label,
    CASE
      WHEN regexp_like(lower(name), '(btc|wbtc)') THEN 'BTC'
      WHEN regexp_like(lower(name), '(eth|weth)') THEN 'ETH'
      WHEN regexp_like(lower(name), 'usdc') THEN 'USDC'
      WHEN regexp_like(lower(name), 'usdt') THEN 'USDT'
      WHEN regexp_like(lower(name), 'dai') THEN 'DAI'
      WHEN regexp_like(lower(name), 'luna') THEN 'LUNA'
      WHEN regexp_like(lower(name), 'avax') THEN 'AVAX'
      WHEN regexp_like(lower(name), 'bnb') THEN 'BNB'
      WHEN regexp_like(lower(name), 'cbeth') THEN 'CBETH'
      WHEN regexp_like(lower(name), 'wsteth') THEN 'WSTETH'
      ELSE NULL
    END AS feed_identity
  FROM labels.addresses
  WHERE regexp_like(lower(name), '(chainlink|oracle|price|feed|aggregator)')
    {_chain_filter("blockchain", parsed_chains).strip()}
),
lending_surface AS (
  SELECT DISTINCT
    tx.blockchain,
    inv.protocol_cluster_id,
    inv.protocol_label,
    tx."to" AS market_contract,
    COALESCE(td.function_name, 'unknown_lending_transition') AS transition_name
  FROM lending_market_inventory inv
  JOIN evms.transactions tx
    ON tx.blockchain = inv.blockchain
   AND tx."to" = inv.address
   AND tx.block_date BETWEEN (SELECT start_date FROM params) AND (SELECT end_date FROM params)
  LEFT JOIN evms.traces_decoded td
    ON td.blockchain = tx.blockchain
   AND td.tx_hash = tx.hash
   AND td.block_date BETWEEN (SELECT start_date FROM params) AND (SELECT end_date FROM params)
  WHERE tx.success = true
    AND inv.inventory_role IN ('market_token', 'lending_label')
    AND regexp_like(lower(COALESCE(td.function_name, '')), '(borrow|mint|supply|deposit|repay|redeem|withdraw|liquidat)')
),
protocol_cluster AS (
  SELECT DISTINCT
    inv.blockchain,
    inv.address,
    inv.protocol_label,
    inv.protocol_cluster_id,
    inv.inventory_role,
    inv.inventory_source
  FROM lending_market_inventory inv
  JOIN (
    SELECT DISTINCT blockchain, protocol_cluster_id
    FROM lending_surface
  ) surface
    ON surface.blockchain = inv.blockchain
   AND surface.protocol_cluster_id = inv.protocol_cluster_id
),
binding_change_candidates AS (
  SELECT
    tx.blockchain,
    tx.block_time,
    tx.block_number,
    tx.hash AS trigger_tx,
    tx."from" AS actor,
    tx."to" AS binding_contract,
    tx.data AS tx_data,
    pc.protocol_label,
    pc.protocol_cluster_id,
    pc.inventory_role,
    COALESCE(td.function_name, 'unknown_binding_change') AS function_name
  FROM protocol_cluster pc
  JOIN evms.transactions tx
    ON tx.blockchain = pc.blockchain
   AND tx."to" = pc.address
   AND tx.block_date BETWEEN (SELECT start_date FROM params) AND (SELECT end_date FROM params)
  LEFT JOIN evms.traces_decoded td
    ON td.blockchain = tx.blockchain
   AND td.tx_hash = tx.hash
   AND td.block_date BETWEEN (SELECT start_date FROM params) AND (SELECT end_date FROM params)
  WHERE tx.success = true
    AND pc.inventory_role IN ('oracle_or_feed', 'governance_or_admin', 'lending_label')
    AND regexp_like(lower(COALESCE(td.function_name, '')), '(oracle|price|feed|source|aggregator|asset|underlying)')
),
asset_feed_identity AS (
  SELECT
    b.*,
    asset.address AS affected_asset_address,
    asset.protocol_label AS affected_asset_label,
    CASE
      WHEN regexp_like(lower(asset.protocol_label), 'usdc') THEN 'USDC'
      WHEN regexp_like(lower(asset.protocol_label), 'usdt') THEN 'USDT'
      WHEN regexp_like(lower(asset.protocol_label), 'dai') THEN 'DAI'
      WHEN regexp_like(lower(asset.protocol_label), '(btc|wbtc)') THEN 'BTC'
      WHEN regexp_like(lower(asset.protocol_label), '(eth|weth)') THEN 'ETH'
      WHEN regexp_like(lower(asset.protocol_label), 'luna') THEN 'LUNA'
      WHEN regexp_like(lower(asset.protocol_label), 'avax') THEN 'AVAX'
      WHEN regexp_like(lower(asset.protocol_label), 'bnb') THEN 'BNB'
      WHEN regexp_like(lower(asset.protocol_label), 'cbeth') THEN 'CBETH'
      WHEN regexp_like(lower(asset.protocol_label), 'wsteth') THEN 'WSTETH'
      ELSE NULL
    END AS asset_identity,
    feed.address AS feed_address,
    feed.feed_label,
    feed.feed_identity,
    CASE
      WHEN regexp_like(lower(asset.protocol_label), 'usdc') THEN 'USDC'
      WHEN regexp_like(lower(asset.protocol_label), 'usdt') THEN 'USDT'
      WHEN regexp_like(lower(asset.protocol_label), 'dai') THEN 'DAI'
      WHEN regexp_like(lower(asset.protocol_label), '(btc|wbtc)') THEN 'BTC'
      WHEN regexp_like(lower(asset.protocol_label), '(eth|weth)') THEN 'ETH'
      WHEN regexp_like(lower(asset.protocol_label), 'luna') THEN 'LUNA'
      WHEN regexp_like(lower(asset.protocol_label), 'avax') THEN 'AVAX'
      WHEN regexp_like(lower(asset.protocol_label), 'bnb') THEN 'BNB'
      WHEN regexp_like(lower(asset.protocol_label), 'cbeth') THEN 'CBETH'
      WHEN regexp_like(lower(asset.protocol_label), 'wsteth') THEN 'WSTETH'
      ELSE NULL
    END IS NOT NULL AS asset_identity_observed,
    feed.feed_identity IS NOT NULL AS feed_identity_observed,
    asset.address IS NOT NULL
      AND feed.address IS NOT NULL
      AND feed.feed_identity IS NOT NULL
      AND CASE
        WHEN regexp_like(lower(asset.protocol_label), 'usdc') THEN 'USDC'
        WHEN regexp_like(lower(asset.protocol_label), 'usdt') THEN 'USDT'
        WHEN regexp_like(lower(asset.protocol_label), 'dai') THEN 'DAI'
        WHEN regexp_like(lower(asset.protocol_label), '(btc|wbtc)') THEN 'BTC'
        WHEN regexp_like(lower(asset.protocol_label), '(eth|weth)') THEN 'ETH'
        WHEN regexp_like(lower(asset.protocol_label), 'luna') THEN 'LUNA'
        WHEN regexp_like(lower(asset.protocol_label), 'avax') THEN 'AVAX'
        WHEN regexp_like(lower(asset.protocol_label), 'bnb') THEN 'BNB'
        WHEN regexp_like(lower(asset.protocol_label), 'cbeth') THEN 'CBETH'
        WHEN regexp_like(lower(asset.protocol_label), 'wsteth') THEN 'WSTETH'
        ELSE NULL
      END IS NOT NULL
      AND CASE
        WHEN regexp_like(lower(asset.protocol_label), 'usdc') THEN 'USDC'
        WHEN regexp_like(lower(asset.protocol_label), 'usdt') THEN 'USDT'
        WHEN regexp_like(lower(asset.protocol_label), 'dai') THEN 'DAI'
        WHEN regexp_like(lower(asset.protocol_label), '(btc|wbtc)') THEN 'BTC'
        WHEN regexp_like(lower(asset.protocol_label), '(eth|weth)') THEN 'ETH'
        WHEN regexp_like(lower(asset.protocol_label), 'luna') THEN 'LUNA'
        WHEN regexp_like(lower(asset.protocol_label), 'avax') THEN 'AVAX'
        WHEN regexp_like(lower(asset.protocol_label), 'bnb') THEN 'BNB'
        WHEN regexp_like(lower(asset.protocol_label), 'cbeth') THEN 'CBETH'
        WHEN regexp_like(lower(asset.protocol_label), 'wsteth') THEN 'WSTETH'
        ELSE NULL
      END <> feed.feed_identity AS identity_mismatch_hint
  FROM binding_change_candidates b
  LEFT JOIN protocol_cluster asset
    ON asset.blockchain = b.blockchain
   AND asset.protocol_cluster_id = b.protocol_cluster_id
   AND asset.inventory_role IN ('market_token', 'lending_label')
   AND strpos(lower(to_hex(b.tx_data)), lower(to_hex(asset.address))) > 0
  LEFT JOIN price_source_inventory feed
    ON feed.blockchain = b.blockchain
   AND strpos(lower(to_hex(b.tx_data)), lower(to_hex(feed.address))) > 0
),
same_protocol_impact AS (
  SELECT
    a.blockchain,
    a.trigger_tx,
    COUNT(DISTINCT tx.hash) AS impact_tx_count,
    CAST(0 AS double) AS impact_usd_known,
    MIN(tx.block_time) AS first_impact_time,
    array_join(slice(array_agg(CAST(tx.hash AS varchar) ORDER BY tx.block_time), 1, 1), ';') AS impact_txs
  FROM asset_feed_identity a
  JOIN lending_surface surface
    ON surface.blockchain = a.blockchain
   AND surface.protocol_cluster_id = a.protocol_cluster_id
  JOIN evms.transactions tx
    ON tx.blockchain = surface.blockchain
   AND tx."to" = surface.market_contract
   AND tx.block_time >= a.block_time
   AND tx.block_time < a.block_time + INTERVAL '24' HOUR
   AND tx.block_date BETWEEN (SELECT start_date FROM params) AND (SELECT end_date FROM params)
  LEFT JOIN evms.traces_decoded td
    ON td.blockchain = tx.blockchain
   AND td.tx_hash = tx.hash
   AND td.block_date BETWEEN (SELECT start_date FROM params) AND (SELECT end_date FROM params)
  WHERE tx.success = true
    AND regexp_like(lower(COALESCE(td.function_name, '')), '(borrow|mint|supply|deposit|repay|redeem|withdraw|liquidat)')
  GROUP BY 1, 2
),
features AS (
  SELECT
    a.blockchain AS chain,
    COALESCE(l.name, a.protocol_label, 'unknown_protocol') AS protocol,
    'feed_binding_failure' AS failure_class,
    a.trigger_tx,
    a.block_number AS trigger_block,
    a.block_time AS trigger_time,
    COALESCE(a.asset_identity, a.affected_asset_label) AS affected_asset,
    a.asset_identity_observed,
    a.feed_identity_observed,
    a.identity_mismatch_hint,
    a.feed_label,
    a.feed_identity,
    TRUE AS has_trigger,
    a.identity_mismatch_hint
      OR NOT (a.asset_identity_observed AND a.feed_identity_observed) AS has_oracle_anomaly,
    COALESCE(i.impact_tx_count, 0) AS impact_tx_count,
    COALESCE(i.impact_usd_known, 0) AS impact_usd_known,
    COALESCE(i.impact_txs, '') AS impact_txs,
    COALESCE(i.impact_tx_count, 0) > 0 AS has_lending_impact,
    a.actor IS NOT NULL AS has_actor,
    i.first_impact_time IS NOT NULL AND i.first_impact_time >= a.block_time AS has_temporal_order,
    COALESCE(i.impact_tx_count, 0) > 0
      AND a.actor IS NOT NULL
      AND a.identity_mismatch_hint
      AND i.first_impact_time IS NOT NULL
      AND i.first_impact_time >= a.block_time AS has_replayable_constraint,
    date_diff('second', a.block_time, i.first_impact_time) AS trigger_to_impact_seconds,
    CASE
      WHEN a.identity_mismatch_hint AND COALESCE(i.impact_tx_count, 0) > 0 THEN 'decoded_binding_closure'
      WHEN regexp_like(lower(a.function_name), '(oracle|price|feed|source|aggregator|asset|underlying)') THEN 'decoded_protocol_event'
      WHEN a.asset_identity_observed OR a.feed_identity_observed THEN 'identity_metadata_partial'
      ELSE 'label_match'
    END AS source_quality,
    CASE
      WHEN a.identity_mismatch_hint AND COALESCE(i.impact_tx_count, 0) > 0 THEN 1
      WHEN regexp_like(lower(a.function_name), '(oracle|price|feed|source|aggregator|asset|underlying)') THEN 2
      WHEN a.asset_identity_observed OR a.feed_identity_observed THEN 3
      ELSE 4
    END AS source_quality_rank
  FROM asset_feed_identity a
  LEFT JOIN same_protocol_impact i
    ON i.blockchain = a.blockchain
   AND i.trigger_tx = a.trigger_tx
  LEFT JOIN labels.addresses l
    ON l.blockchain = a.blockchain
   AND l.address = a.binding_contract
),
tiered AS (
  SELECT
    *,
    CASE
      WHEN has_trigger AND identity_mismatch_hint AND has_lending_impact AND has_actor
        AND has_temporal_order AND has_replayable_constraint THEN 'A_replayable'
      WHEN has_trigger AND has_oracle_anomaly AND has_lending_impact AND has_temporal_order
        THEN 'B_high_confidence_incomplete'
      WHEN has_trigger AND has_oracle_anomaly THEN 'C_remote_anomaly_only'
      ELSE 'reject_out_of_scope'
    END AS evidence_tier,
    CASE
      WHEN has_trigger AND identity_mismatch_hint AND has_lending_impact AND has_actor
        AND has_temporal_order AND has_replayable_constraint
        THEN 'asset-feed binding change, identity mismatch hint, same-protocol lending impact, actor, temporal order, and replayable fields are present'
      WHEN has_trigger AND has_oracle_anomaly AND has_lending_impact AND has_temporal_order
        THEN 'asset-feed binding change and same-protocol lending impact are present, but identity/source/replay fields are incomplete'
      WHEN has_trigger AND has_oracle_anomaly
        THEN 'asset-feed binding anomaly is visible remotely, but same-protocol lending impact is not closed'
      ELSE 'outside lending oracle-consumption scope'
    END AS closure_reason
  FROM features
)
SELECT *
FROM tiered
WHERE evidence_tier IN ('A_replayable', 'B_high_confidence_incomplete', 'C_remote_anomaly_only')
{EVIDENCE_ORDER_BY};
"""


def feed_binding_preflight_count_sql(start: str, end: str, chains: List[str] | None = None) -> str:
    parsed_chains = parse_chains(chains)
    inventory_cte = _inventory_cte(parsed_chains)
    return f"""-- R1 preflight counts: feed-binding Semantic Binding Closure v2.
-- Goal: estimate stage cardinalities before running the full candidate query.
-- This query returns compact counts only; it does not emit candidates, download
-- receipts, call contract methods, scan raw calldata broadly, or scan for future
-- targets.
WITH
params AS (
  SELECT
    DATE '{start}' AS start_date,
    DATE '{end}' AS end_date
),
{inventory_cte},
price_source_inventory AS (
  SELECT DISTINCT
    blockchain,
    address,
    name AS feed_label,
    CASE
      WHEN regexp_like(lower(name), '(btc|wbtc)') THEN 'BTC'
      WHEN regexp_like(lower(name), '(eth|weth)') THEN 'ETH'
      WHEN regexp_like(lower(name), 'usdc') THEN 'USDC'
      WHEN regexp_like(lower(name), 'usdt') THEN 'USDT'
      WHEN regexp_like(lower(name), 'dai') THEN 'DAI'
      WHEN regexp_like(lower(name), 'luna') THEN 'LUNA'
      WHEN regexp_like(lower(name), 'avax') THEN 'AVAX'
      WHEN regexp_like(lower(name), 'bnb') THEN 'BNB'
      WHEN regexp_like(lower(name), 'cbeth') THEN 'CBETH'
      WHEN regexp_like(lower(name), 'wsteth') THEN 'WSTETH'
      ELSE NULL
    END AS feed_identity
  FROM labels.addresses
  WHERE regexp_like(lower(name), '(chainlink|oracle|price|feed|aggregator)')
    {_chain_filter("blockchain", parsed_chains).strip()}
),
lending_surface AS (
  SELECT
    tx.blockchain,
    inv.protocol_cluster_id,
    inv.protocol_label,
    tx."to" AS market_contract,
    COUNT(DISTINCT tx.hash) AS lending_transition_tx_count
  FROM lending_market_inventory inv
  JOIN evms.transactions tx
    ON tx.blockchain = inv.blockchain
   AND tx."to" = inv.address
   AND tx.block_date BETWEEN (SELECT start_date FROM params) AND (SELECT end_date FROM params)
  LEFT JOIN evms.traces_decoded td
    ON td.blockchain = tx.blockchain
   AND td.tx_hash = tx.hash
   AND td.block_date BETWEEN (SELECT start_date FROM params) AND (SELECT end_date FROM params)
  WHERE tx.success = true
    AND inv.inventory_role IN ('market_token', 'lending_label')
    AND regexp_like(lower(COALESCE(td.function_name, '')), '(borrow|mint|supply|deposit|repay|redeem|withdraw|liquidat)')
  GROUP BY 1, 2, 3, 4
),
active_protocol_clusters AS (
  SELECT DISTINCT blockchain, protocol_cluster_id
  FROM lending_surface
),
protocol_cluster AS (
  SELECT DISTINCT
    inv.blockchain,
    inv.address,
    inv.protocol_label,
    inv.protocol_cluster_id,
    inv.inventory_role,
    inv.inventory_source
  FROM lending_market_inventory inv
  JOIN active_protocol_clusters surface
    ON surface.blockchain = inv.blockchain
   AND surface.protocol_cluster_id = inv.protocol_cluster_id
),
binding_change_candidates AS (
  SELECT DISTINCT
    tx.blockchain,
    tx.hash AS trigger_tx,
    tx.data AS tx_data,
    pc.protocol_cluster_id,
    pc.protocol_label,
    pc.inventory_role,
    COALESCE(td.function_name, 'unknown_binding_change') AS function_name
  FROM protocol_cluster pc
  JOIN evms.transactions tx
    ON tx.blockchain = pc.blockchain
   AND tx."to" = pc.address
   AND tx.block_date BETWEEN (SELECT start_date FROM params) AND (SELECT end_date FROM params)
  LEFT JOIN evms.traces_decoded td
    ON td.blockchain = tx.blockchain
   AND td.tx_hash = tx.hash
   AND td.block_date BETWEEN (SELECT start_date FROM params) AND (SELECT end_date FROM params)
  WHERE tx.success = true
    AND pc.inventory_role IN ('oracle_or_feed', 'governance_or_admin', 'lending_label')
    AND regexp_like(lower(COALESCE(td.function_name, '')), '(oracle|price|feed|source|aggregator|asset|underlying)')
),
asset_identity_lookup AS (
  SELECT
    blockchain,
    address,
    protocol_label,
    protocol_cluster_id,
    CASE
      WHEN regexp_like(lower(protocol_label), 'usdc') THEN 'USDC'
      WHEN regexp_like(lower(protocol_label), 'usdt') THEN 'USDT'
      WHEN regexp_like(lower(protocol_label), 'dai') THEN 'DAI'
      WHEN regexp_like(lower(protocol_label), '(btc|wbtc)') THEN 'BTC'
      WHEN regexp_like(lower(protocol_label), '(eth|weth)') THEN 'ETH'
      WHEN regexp_like(lower(protocol_label), 'luna') THEN 'LUNA'
      WHEN regexp_like(lower(protocol_label), 'avax') THEN 'AVAX'
      WHEN regexp_like(lower(protocol_label), 'bnb') THEN 'BNB'
      WHEN regexp_like(lower(protocol_label), 'cbeth') THEN 'CBETH'
      WHEN regexp_like(lower(protocol_label), 'wsteth') THEN 'WSTETH'
      ELSE NULL
    END AS asset_identity
  FROM protocol_cluster
  WHERE inventory_role IN ('market_token', 'lending_label')
),
identity_flags AS (
  SELECT
    b.blockchain,
    b.trigger_tx,
    b.protocol_cluster_id,
    MAX(CASE WHEN asset.asset_identity IS NOT NULL THEN 1 ELSE 0 END) AS asset_identity_observed,
    MAX(CASE WHEN feed.feed_identity IS NOT NULL THEN 1 ELSE 0 END) AS feed_identity_observed,
    MAX(CASE
      WHEN asset.asset_identity IS NOT NULL
        AND feed.feed_identity IS NOT NULL
        AND asset.asset_identity <> feed.feed_identity THEN 1
      ELSE 0
    END) AS identity_mismatch_hint
  FROM binding_change_candidates b
  LEFT JOIN asset_identity_lookup asset
    ON asset.blockchain = b.blockchain
   AND asset.protocol_cluster_id = b.protocol_cluster_id
   AND strpos(lower(to_hex(b.tx_data)), lower(to_hex(asset.address))) > 0
  LEFT JOIN price_source_inventory feed
    ON feed.blockchain = b.blockchain
   AND strpos(lower(to_hex(b.tx_data)), lower(to_hex(feed.address))) > 0
  GROUP BY 1, 2, 3
),
stage_counts AS (
  SELECT
    'inventory_addresses' AS preflight_stage,
    blockchain AS chain,
    COUNT(*) AS row_count,
    COUNT(DISTINCT address) AS address_count,
    COUNT(DISTINCT protocol_cluster_id) AS protocol_cluster_count,
    CAST(NULL AS bigint) AS tx_count
  FROM lending_market_inventory
  GROUP BY 1, 2

  UNION ALL

  SELECT
    'price_source_addresses' AS preflight_stage,
    blockchain AS chain,
    COUNT(*) AS row_count,
    COUNT(DISTINCT address) AS address_count,
    CAST(NULL AS bigint) AS protocol_cluster_count,
    CAST(NULL AS bigint) AS tx_count
  FROM price_source_inventory
  GROUP BY 1, 2

  UNION ALL

  SELECT
    'lending_surface' AS preflight_stage,
    blockchain AS chain,
    COUNT(*) AS row_count,
    COUNT(DISTINCT market_contract) AS address_count,
    COUNT(DISTINCT protocol_cluster_id) AS protocol_cluster_count,
    SUM(lending_transition_tx_count) AS tx_count
  FROM lending_surface
  GROUP BY 1, 2

  UNION ALL

  SELECT
    'active_protocol_clusters' AS preflight_stage,
    blockchain AS chain,
    COUNT(*) AS row_count,
    CAST(NULL AS bigint) AS address_count,
    COUNT(DISTINCT protocol_cluster_id) AS protocol_cluster_count,
    CAST(NULL AS bigint) AS tx_count
  FROM active_protocol_clusters
  GROUP BY 1, 2

  UNION ALL

  SELECT
    'binding_change_candidates' AS preflight_stage,
    blockchain AS chain,
    COUNT(*) AS row_count,
    CAST(NULL AS bigint) AS address_count,
    COUNT(DISTINCT protocol_cluster_id) AS protocol_cluster_count,
    COUNT(DISTINCT trigger_tx) AS tx_count
  FROM binding_change_candidates
  GROUP BY 1, 2

  UNION ALL

  SELECT
    'asset_identity_observed' AS preflight_stage,
    blockchain AS chain,
    SUM(asset_identity_observed) AS row_count,
    CAST(NULL AS bigint) AS address_count,
    COUNT(DISTINCT CASE WHEN asset_identity_observed = 1 THEN protocol_cluster_id END) AS protocol_cluster_count,
    COUNT(DISTINCT CASE WHEN asset_identity_observed = 1 THEN trigger_tx END) AS tx_count
  FROM identity_flags
  GROUP BY 1, 2

  UNION ALL

  SELECT
    'feed_identity_observed' AS preflight_stage,
    blockchain AS chain,
    SUM(feed_identity_observed) AS row_count,
    CAST(NULL AS bigint) AS address_count,
    COUNT(DISTINCT CASE WHEN feed_identity_observed = 1 THEN protocol_cluster_id END) AS protocol_cluster_count,
    COUNT(DISTINCT CASE WHEN feed_identity_observed = 1 THEN trigger_tx END) AS tx_count
  FROM identity_flags
  GROUP BY 1, 2

  UNION ALL

  SELECT
    'identity_mismatch_hint' AS preflight_stage,
    blockchain AS chain,
    SUM(identity_mismatch_hint) AS row_count,
    CAST(NULL AS bigint) AS address_count,
    COUNT(DISTINCT CASE WHEN identity_mismatch_hint = 1 THEN protocol_cluster_id END) AS protocol_cluster_count,
    COUNT(DISTINCT CASE WHEN identity_mismatch_hint = 1 THEN trigger_tx END) AS tx_count
  FROM identity_flags
  GROUP BY 1, 2
)
SELECT
  chain,
  'feed_binding_failure' AS failure_class,
  preflight_stage,
  DATE '{start}' AS start_date,
  DATE '{end}' AS end_date,
  row_count,
  address_count,
  protocol_cluster_count,
  tx_count
FROM stage_counts
ORDER BY chain, preflight_stage;
"""


def price_composition_sql(start: str, end: str, chains: List[str] | None = None) -> str:
    parsed_chains = parse_chains(chains)
    token_chain_filter = _chain_filter("e.blockchain", parsed_chains)
    inventory_cte = _inventory_cte(parsed_chains)
    return f"""-- R2: price-composition failure broad search.
-- Goal: find derivative-asset oracle wrapper or governance configuration events
-- where the valuation formula may omit a base/USD operand, then keep candidates
-- with liquidation or borrow-like activity. This index-level candidate query is
-- intentionally not top-k limited; local downloads are bounded later by the
-- materialization queue. Candidates are tiered by evidence closure, not a
-- weighted score.
-- Inventory-first guardrail: derivative assets, oracle/governance triggers,
-- and impact transfers are all joined through lending_market_inventory.
WITH
params AS (
  SELECT
    DATE '{start}' AS start_date,
    DATE '{end}' AS end_date
),
{inventory_cte},
derivative_assets AS (
  SELECT e.blockchain, e.contract_address, e.symbol, e.name
  FROM tokens.erc20 e
  JOIN lending_market_inventory inv
    ON inv.blockchain = e.blockchain
   AND inv.address = e.contract_address
  WHERE regexp_like(lower(symbol || ' ' || name), '(cbeth|wsteth|reth|rs?eth|lst|lrt|staked|wrapped)')
    {token_chain_filter.strip()}
),
oracle_wrapper_txs AS (
  SELECT
    tx.blockchain,
    tx.block_time,
    tx.block_number,
    tx.hash AS trigger_tx,
    tx."from" AS actor,
    tx."to" AS oracle_or_governance_contract,
    tx.data AS tx_data,
    inv.protocol_label AS inventory_label,
    inv.inventory_role,
    COALESCE(td.function_name, 'unknown_formula_config') AS function_name
  FROM lending_market_inventory inv
  JOIN evms.transactions tx
    ON tx.blockchain = inv.blockchain
   AND tx."to" = inv.address
   AND tx.block_date BETWEEN (SELECT start_date FROM params) AND (SELECT end_date FROM params)
  LEFT JOIN evms.traces_decoded td
    ON td.blockchain = tx.blockchain
   AND td.tx_hash = tx.hash
   AND td.block_date BETWEEN (SELECT start_date FROM params) AND (SELECT end_date FROM params)
  WHERE tx.success = true
    AND regexp_like(lower(COALESCE(td.function_name, '') || ' ' || to_hex(tx.data)), '(oracle|feed|source|ratio|rate|price|govern|execute)')
),
affected_asset_hint AS (
  SELECT
    o.*,
    a.symbol AS affected_asset,
    a.contract_address AS affected_asset_address
  FROM oracle_wrapper_txs o
  JOIN derivative_assets a
    ON a.blockchain = o.blockchain
   AND (
     lower(COALESCE(o.function_name, '')) LIKE '%' || lower(a.symbol) || '%'
     OR strpos(lower(to_hex(o.tx_data)), lower(to_hex(a.contract_address))) > 0
   )
),
impact_activity AS (
  SELECT
    a.blockchain,
    a.trigger_tx,
    COUNT(DISTINCT t.tx_hash) AS impact_tx_count,
    SUM(COALESCE(t.amount_usd, 0)) AS impact_usd_known,
    MIN(t.block_time) AS first_impact_time,
    array_join(slice(array_agg(CAST(t.tx_hash AS varchar) ORDER BY t.block_time), 1, 1), ';') AS impact_txs
  FROM affected_asset_hint a
  JOIN lending_market_inventory market
    ON market.blockchain = a.blockchain
   AND market.inventory_role IN ('market_token', 'lending_label')
  JOIN tokens.transfers t
    ON t.blockchain = a.blockchain
   AND (
     t.contract_address = a.affected_asset_address
     OR t."from" = market.address
     OR t."to" = market.address
   )
   AND t.block_time >= a.block_time
   AND t.block_time < a.block_time + INTERVAL '24' HOUR
   AND t.block_date BETWEEN (SELECT start_date FROM params) AND (SELECT end_date FROM params)
  GROUP BY 1, 2
),
features AS (
  SELECT
    a.blockchain AS chain,
    COALESCE(l.name, a.inventory_label, 'unknown_protocol') AS protocol,
    'price_composition_failure' AS failure_class,
    a.trigger_tx,
    a.block_number AS trigger_block,
    a.block_time AS trigger_time,
    a.affected_asset,
    TRUE AS has_trigger,
    TRUE AS has_oracle_anomaly,
    COALESCE(i.impact_tx_count, 0) AS impact_tx_count,
    COALESCE(i.impact_usd_known, 0) AS impact_usd_known,
    COALESCE(i.impact_txs, '') AS impact_txs,
    COALESCE(i.impact_tx_count, 0) > 0 AS has_lending_impact,
    a.actor IS NOT NULL AS has_actor,
    i.first_impact_time IS NOT NULL AND i.first_impact_time >= a.block_time AS has_temporal_order,
    COALESCE(i.impact_tx_count, 0) > 0
      AND a.actor IS NOT NULL
      AND a.affected_asset IS NOT NULL
      AND i.first_impact_time IS NOT NULL
      AND i.first_impact_time >= a.block_time AS has_replayable_constraint,
    date_diff('second', a.block_time, i.first_impact_time) AS trigger_to_impact_seconds,
    CASE
      WHEN regexp_like(lower(a.function_name), '(oracle|feed|price|execute|govern)') THEN 'decoded_protocol_event'
      WHEN l.name IS NOT NULL THEN 'label_match'
      ELSE 'raw_transfer_heuristic'
    END AS source_quality,
    CASE
      WHEN regexp_like(lower(a.function_name), '(oracle|feed|price|execute|govern)') THEN 1
      WHEN l.name IS NOT NULL THEN 2
      ELSE 4
    END AS source_quality_rank
  FROM affected_asset_hint a
  LEFT JOIN impact_activity i
    ON i.blockchain = a.blockchain
   AND i.trigger_tx = a.trigger_tx
  LEFT JOIN labels.addresses l
    ON l.blockchain = a.blockchain
   AND l.address = a.oracle_or_governance_contract
),
tiered AS (
  SELECT
    *,
    CASE
      WHEN has_trigger AND has_oracle_anomaly AND has_lending_impact AND has_actor
        AND has_temporal_order AND has_replayable_constraint THEN 'A_replayable'
      WHEN has_trigger AND has_oracle_anomaly AND has_lending_impact AND has_temporal_order
        THEN 'B_high_confidence_incomplete'
      WHEN has_trigger AND has_oracle_anomaly THEN 'C_remote_anomaly_only'
      ELSE 'reject_out_of_scope'
    END AS evidence_tier,
    CASE
      WHEN has_trigger AND has_oracle_anomaly AND has_lending_impact AND has_actor
        AND has_temporal_order AND has_replayable_constraint
        THEN 'formula/config trigger, derivative asset hint, follow-up lending impact, actor, temporal order, and replayable fields are present'
      WHEN has_trigger AND has_oracle_anomaly AND has_lending_impact AND has_temporal_order
        THEN 'formula/config trigger and lending impact are present, but actor or replay fields are incomplete'
      WHEN has_trigger AND has_oracle_anomaly
        THEN 'formula/config anomaly is visible remotely, but lending impact is not closed'
      ELSE 'outside lending oracle-consumption scope'
    END AS closure_reason
  FROM features
)
SELECT *
FROM tiered
WHERE evidence_tier IN ('A_replayable', 'B_high_confidence_incomplete', 'C_remote_anomaly_only')
{EVIDENCE_ORDER_BY};
"""


def price_composition_preflight_count_sql(start: str, end: str, chains: List[str] | None = None) -> str:
    parsed_chains = parse_chains(chains)
    token_chain_filter = _chain_filter("e.blockchain", parsed_chains)
    inventory_cte = _inventory_cte(parsed_chains)
    return f"""-- R2 preflight counts: price-composition closure.
-- This compact query reports stage cardinalities before running the full
-- candidate query. It does not download receipts, call contract methods, or
-- produce future-looking targets.
WITH
params AS (
  SELECT
    DATE '{start}' AS start_date,
    DATE '{end}' AS end_date
),
{inventory_cte},
derivative_assets AS (
  SELECT e.blockchain, e.contract_address, e.symbol, e.name
  FROM tokens.erc20 e
  JOIN lending_market_inventory inv
    ON inv.blockchain = e.blockchain
   AND inv.address = e.contract_address
  WHERE regexp_like(lower(symbol || ' ' || name), '(cbeth|wsteth|reth|rs?eth|lst|lrt|staked|wrapped)')
    {token_chain_filter.strip()}
),
oracle_wrapper_txs AS (
  SELECT
    tx.blockchain,
    tx.block_time,
    tx.hash AS trigger_tx,
    tx."from" AS actor,
    tx."to" AS oracle_or_governance_contract,
    tx.data AS tx_data,
    inv.protocol_label AS inventory_label,
    inv.inventory_role,
    COALESCE(td.function_name, 'unknown_formula_config') AS function_name
  FROM lending_market_inventory inv
  JOIN evms.transactions tx
    ON tx.blockchain = inv.blockchain
   AND tx."to" = inv.address
   AND tx.block_date BETWEEN (SELECT start_date FROM params) AND (SELECT end_date FROM params)
  LEFT JOIN evms.traces_decoded td
    ON td.blockchain = tx.blockchain
   AND td.tx_hash = tx.hash
   AND td.block_date BETWEEN (SELECT start_date FROM params) AND (SELECT end_date FROM params)
  WHERE tx.success = true
    AND regexp_like(lower(COALESCE(td.function_name, '') || ' ' || to_hex(tx.data)), '(oracle|feed|source|ratio|rate|price|govern|execute)')
),
affected_asset_hint AS (
  SELECT
    o.*,
    a.symbol AS affected_asset,
    a.contract_address AS affected_asset_address
  FROM oracle_wrapper_txs o
  JOIN derivative_assets a
    ON a.blockchain = o.blockchain
   AND (
     lower(COALESCE(o.function_name, '')) LIKE '%' || lower(a.symbol) || '%'
     OR strpos(lower(to_hex(o.tx_data)), lower(to_hex(a.contract_address))) > 0
   )
),
impact_activity AS (
  SELECT
    a.blockchain,
    a.trigger_tx,
    COUNT(DISTINCT t.tx_hash) AS impact_tx_count,
    MIN(t.block_time) AS first_impact_time
  FROM affected_asset_hint a
  JOIN lending_market_inventory market
    ON market.blockchain = a.blockchain
   AND market.inventory_role IN ('market_token', 'lending_label')
  JOIN tokens.transfers t
    ON t.blockchain = a.blockchain
   AND (
     t.contract_address = a.affected_asset_address
     OR t."from" = market.address
     OR t."to" = market.address
   )
   AND t.block_time >= a.block_time
   AND t.block_time < a.block_time + INTERVAL '24' HOUR
   AND t.block_date BETWEEN (SELECT start_date FROM params) AND (SELECT end_date FROM params)
  GROUP BY 1, 2
),
tiered_candidates AS (
  SELECT
    a.blockchain,
    a.trigger_tx,
    CASE
      WHEN a.actor IS NOT NULL AND COALESCE(i.impact_tx_count, 0) > 0 AND i.first_impact_time >= a.block_time THEN 'A_replayable'
      WHEN COALESCE(i.impact_tx_count, 0) > 0 AND i.first_impact_time >= a.block_time THEN 'B_high_confidence_incomplete'
      ELSE 'C_remote_anomaly_only'
    END AS evidence_tier
  FROM affected_asset_hint a
  LEFT JOIN impact_activity i
    ON i.blockchain = a.blockchain
   AND i.trigger_tx = a.trigger_tx
),
stage_counts AS (
  SELECT
    'inventory_addresses' AS preflight_stage,
    blockchain AS chain,
    COUNT(*) AS row_count,
    COUNT(DISTINCT address) AS address_count,
    COUNT(DISTINCT protocol_cluster_id) AS protocol_cluster_count,
    CAST(NULL AS bigint) AS tx_count
  FROM lending_market_inventory
  GROUP BY 1, 2

  UNION ALL

  SELECT
    'derivative_assets' AS preflight_stage,
    blockchain AS chain,
    COUNT(*) AS row_count,
    COUNT(DISTINCT contract_address) AS address_count,
    CAST(NULL AS bigint) AS protocol_cluster_count,
    CAST(NULL AS bigint) AS tx_count
  FROM derivative_assets
  GROUP BY 1, 2

  UNION ALL

  SELECT
    'oracle_wrapper_txs' AS preflight_stage,
    blockchain AS chain,
    COUNT(*) AS row_count,
    COUNT(DISTINCT oracle_or_governance_contract) AS address_count,
    CAST(NULL AS bigint) AS protocol_cluster_count,
    COUNT(DISTINCT trigger_tx) AS tx_count
  FROM oracle_wrapper_txs
  GROUP BY 1, 2

  UNION ALL

  SELECT
    'affected_asset_hint' AS preflight_stage,
    blockchain AS chain,
    COUNT(*) AS row_count,
    COUNT(DISTINCT affected_asset_address) AS address_count,
    CAST(NULL AS bigint) AS protocol_cluster_count,
    COUNT(DISTINCT trigger_tx) AS tx_count
  FROM affected_asset_hint
  GROUP BY 1, 2

  UNION ALL

  SELECT
    'impact_activity' AS preflight_stage,
    blockchain AS chain,
    COUNT(*) AS row_count,
    CAST(NULL AS bigint) AS address_count,
    CAST(NULL AS bigint) AS protocol_cluster_count,
    COUNT(DISTINCT trigger_tx) AS tx_count
  FROM impact_activity
  GROUP BY 1, 2

  UNION ALL

  SELECT
    'tiered_candidates' AS preflight_stage,
    blockchain AS chain,
    COUNT(*) AS row_count,
    CAST(NULL AS bigint) AS address_count,
    CAST(NULL AS bigint) AS protocol_cluster_count,
    COUNT(DISTINCT trigger_tx) AS tx_count
  FROM tiered_candidates
  GROUP BY 1, 2
)
SELECT
  chain,
  'price_composition_failure' AS failure_class,
  preflight_stage,
  DATE '{start}' AS start_date,
  DATE '{end}' AS end_date,
  row_count,
  address_count,
  protocol_cluster_count,
  tx_count
FROM stage_counts
ORDER BY chain, preflight_stage;
"""


def _freshness_common_ctes(start: str, end: str, chains: List[str] | None = None) -> str:
    parsed_chains = parse_chains(chains)
    token_chain_filter = _chain_filter("blockchain", parsed_chains)
    transfer_chain_filter = _chain_filter_with_legacy_variants("t.blockchain", parsed_chains)
    log_chain_filter = _chain_filter("l.blockchain", parsed_chains)
    market_asset_expr = _market_token_asset_expr("symbol", "name")
    transfer_asset_expr = _asset_identity_expr("COALESCE(tok.symbol, '') || ' ' || COALESCE(tok.name, '')")
    generic_symbol_pattern = (
        "^(a|b|c|m|v)"
        "(cbeth|wsteth|reth|wbtc|btc|weth|eth|usdc|usdbc|usdt|dai|busd|luna|"
        "wavax|avax|bnb|link|aave|mim|qi|spell|joe|crv|tusd|alpha)"
        "(\\\\.e)?$"
    )
    cluster_expr = _generic_market_cluster_expr("COALESCE(name, symbol, 'unknown_market')")
    return f"""WITH
params AS (
  SELECT DATE '{start}' AS start_date, DATE '{end}' AS end_date
),
market_token_source AS (
  SELECT
    blockchain,
    contract_address AS market_address,
    COALESCE(symbol, '') AS market_symbol,
    COALESCE(name, symbol, 'unknown_market') AS protocol_label,
    {market_asset_expr} AS market_asset_identity,
    {cluster_expr} AS protocol_cluster_id
  FROM tokens.erc20
  WHERE regexp_like(lower(COALESCE(symbol, '')), '{generic_symbol_pattern}')
    AND NOT regexp_like(lower(COALESCE(symbol, '') || ' ' || COALESCE(name, '')), '(variabledebt|stabledebt|debt token|governance|reward|staking|lp token)')
    {token_chain_filter.strip()}
),
market_inventory AS (
  SELECT DISTINCT
    blockchain,
    market_address,
    market_symbol,
    protocol_label,
    protocol_cluster_id,
    market_asset_identity
  FROM market_token_source
  WHERE market_asset_identity IS NOT NULL
    AND protocol_cluster_id <> 'unknown_market_cluster'
),
transfer_events AS (
  SELECT
    {_normalized_chain_expr("t.blockchain")} AS blockchain,
    t.block_time,
    t.block_date,
    t.block_number,
    t.tx_hash,
    t."from",
    t."to",
    t.contract_address,
    t.amount,
    t.amount_usd,
    {transfer_asset_expr} AS transfer_asset_identity
  FROM tokens.transfers t
  LEFT JOIN tokens.erc20 tok
    ON tok.blockchain = t.blockchain
   AND tok.contract_address = t.contract_address
  WHERE t.block_date BETWEEN (SELECT start_date FROM params) AND (SELECT end_date FROM params)
    {transfer_chain_filter.strip()}
),
collateral_supply_events AS (
  SELECT
    t.blockchain,
    cm.protocol_cluster_id,
    cm.protocol_label,
    cm.market_address AS collateral_market,
    cm.market_asset_identity AS collateral_asset,
    t.contract_address AS collateral_token,
    t."from" AS actor,
    t."to" AS protocol_address,
    t.tx_hash AS supply_tx,
    t.block_number AS supply_block,
    t.block_time AS supply_time,
    t.amount AS collateral_amount,
    t.amount_usd AS collateral_amount_usd
  FROM market_inventory cm
  JOIN transfer_events t
    ON t.blockchain = cm.blockchain
   AND t."to" = cm.market_address
  WHERE cm.market_asset_identity IS NOT NULL
    AND t.amount > 0
    AND t."from" <> 0x0000000000000000000000000000000000000000
    AND t.transfer_asset_identity = cm.market_asset_identity
    AND (
      t.amount_usd IS NULL
      OR t.amount_usd >= 10000
      OR (
        cm.market_asset_identity NOT IN ('USDC', 'USDT', 'DAI', 'BUSD')
        AND t.amount >= 1000000
      )
    )
),
borrow_outflow_events AS (
  SELECT
    s.blockchain,
    s.protocol_cluster_id,
    s.protocol_label,
    s.collateral_market,
    s.collateral_asset,
    s.collateral_token,
    s.actor,
    s.supply_tx,
    s.supply_block,
    s.supply_time,
    bm.market_address AS borrow_market,
    bm.market_asset_identity AS borrow_asset,
    t.contract_address AS borrow_token,
    t.tx_hash AS borrow_tx,
    t.block_number AS borrow_block,
    t.block_time AS borrow_time,
    t.amount AS borrow_amount,
    t.amount_usd AS borrow_amount_usd
  FROM collateral_supply_events s
  JOIN market_inventory bm
    ON bm.blockchain = s.blockchain
   AND bm.protocol_cluster_id = s.protocol_cluster_id
   AND bm.market_address <> s.collateral_market
   AND bm.market_asset_identity IS NOT NULL
   AND bm.market_asset_identity <> s.collateral_asset
  JOIN transfer_events t
    ON t.blockchain = s.blockchain
   AND t."from" = bm.market_address
   AND t."to" = s.actor
   AND t.block_time >= s.supply_time
   AND t.block_time < s.supply_time + INTERVAL '6' HOUR
  WHERE t.amount > 0
    AND (t.amount_usd IS NULL OR t.amount_usd >= 10000)
),
same_actor_impact AS (
  SELECT
    blockchain,
    protocol_cluster_id,
    protocol_label,
    collateral_market,
    collateral_asset,
    collateral_token,
    actor,
    supply_tx,
    supply_block,
    supply_time AS first_supply_time,
    MIN(borrow_time) AS first_borrow_time,
    MIN_BY(borrow_tx, borrow_time) AS first_borrow_tx,
    COUNT(DISTINCT borrow_tx) + 1 AS impact_tx_count,
    SUM(COALESCE(borrow_amount_usd, 0)) AS impact_usd_known,
    CONCAT(CAST(supply_tx AS varchar), ';', array_join(slice(array_agg(CAST(borrow_tx AS varchar) ORDER BY borrow_time), 1, 1), ';')) AS impact_txs,
    array_join(array_distinct(array_agg(borrow_asset ORDER BY borrow_asset)), ',') AS borrowed_assets
  FROM borrow_outflow_events
  GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
),
answer_updated_logs AS (
  SELECT
    l.blockchain,
    l.block_time,
    l.block_number,
    l.tx_hash,
    l.contract_address AS feed,
    bytearray_to_int256(l.topic1) AS answer_raw,
    CAST(bytearray_to_int256(l.topic1) AS double) / 1e8 AS answer_decimal,
    bytearray_to_uint256(bytearray_substring(l.data, 1, 32)) AS updated_at,
    lab.name AS feed_label,
    {_asset_identity_expr("COALESCE(lab.name, '')")} AS feed_identity,
    CAST(NULL AS timestamp with time zone) AS next_update_time
  FROM evms.logs l
  LEFT JOIN labels.addresses lab
    ON lab.blockchain = l.blockchain
   AND lab.address = l.contract_address
  WHERE l.topic0 = 0x0559884fd3a460db3073b7fc896cc77986f16e378210ded43186175bf646fc5f
    AND l.block_date BETWEEN (SELECT start_date FROM params) - INTERVAL '7' DAY AND (SELECT end_date FROM params)
    {log_chain_filter.strip()}
),
label_matched_answer_updated AS (
  SELECT
    i.*,
    a.feed,
    a.feed_label,
    a.feed_identity,
    'label_matched' AS feed_identity_source,
    a.tx_hash AS trigger_tx,
    a.block_number AS trigger_block,
    a.block_time AS trigger_time,
    a.answer_raw,
    a.answer_decimal,
    a.updated_at,
    a.next_update_time,
    1 AS answer_match_rank
  FROM same_actor_impact i
  JOIN answer_updated_logs a
    ON a.blockchain = i.blockchain
   AND a.feed_identity = i.collateral_asset
   AND a.block_time <= i.first_supply_time
   AND a.block_time >= i.first_supply_time - INTERVAL '7' DAY
),
lower_bound_unlabeled_answer_updated AS (
  SELECT
    i.*,
    a.feed,
    a.feed_label,
    a.feed_identity,
    'impact_led_lower_bound_unresolved' AS feed_identity_source,
    a.tx_hash AS trigger_tx,
    a.block_number AS trigger_block,
    a.block_time AS trigger_time,
    a.answer_raw,
    a.answer_decimal,
    a.updated_at,
    a.next_update_time,
    2 AS answer_match_rank
  FROM same_actor_impact i
  JOIN answer_updated_logs a
    ON a.blockchain = i.blockchain
   AND a.block_time <= i.first_supply_time
   AND a.block_time >= i.first_supply_time - INTERVAL '7' DAY
   AND a.feed_identity IS NULL
   AND i.collateral_asset NOT IN ('USDC', 'USDT', 'DAI', 'BUSD')
   AND abs(a.answer_decimal) > 0
   AND abs(a.answer_decimal) <= 1
),
answer_candidates AS (
  SELECT * FROM label_matched_answer_updated
  UNION ALL
  SELECT * FROM lower_bound_unlabeled_answer_updated
),
latest_prior_answer_updated AS (
  SELECT *
  FROM (
    SELECT
      i.*,
      a.feed,
      a.feed_label,
      a.feed_identity,
      a.trigger_tx,
      a.trigger_block,
      a.trigger_time,
      a.answer_raw,
      a.answer_decimal,
      a.updated_at,
      a.next_update_time,
      a.feed_identity_source,
      a.answer_match_rank,
      row_number() OVER (
        PARTITION BY i.blockchain, i.protocol_cluster_id, i.actor, i.supply_tx
        ORDER BY a.answer_match_rank ASC, a.trigger_time DESC, a.trigger_block DESC
      ) AS answer_rank
    FROM same_actor_impact i
    JOIN answer_candidates a
      ON a.blockchain = i.blockchain
     AND a.protocol_cluster_id = i.protocol_cluster_id
     AND a.actor = i.actor
     AND a.supply_tx = i.supply_tx
  )
  WHERE answer_rank = 1
),
features AS (
  SELECT
    i.blockchain AS chain,
    COALESCE(i.protocol_label, i.protocol_cluster_id, 'unknown_protocol') AS protocol,
    'freshness_handling_failure' AS failure_class,
    i.trigger_tx,
    i.trigger_block,
    i.trigger_time,
    i.collateral_asset AS affected_asset,
    i.feed_identity,
    i.feed_identity_source,
    TRUE AS has_trigger,
    (
      i.feed_identity_source = 'impact_led_lower_bound_unresolved'
      OR date_diff('hour', i.trigger_time, i.first_borrow_time) >= 1
      OR (abs(i.answer_decimal) > 0 AND abs(i.answer_decimal) <= 1)
    ) AS has_oracle_anomaly,
    i.impact_tx_count,
    i.impact_usd_known,
    i.impact_txs,
    i.impact_tx_count > 1 AS has_lending_impact,
    i.actor IS NOT NULL AS has_actor,
    i.first_supply_time >= i.trigger_time AND i.first_borrow_time >= i.first_supply_time AS has_temporal_order,
    i.impact_tx_count > 1
      AND i.actor IS NOT NULL
      AND i.feed_identity_source = 'label_matched'
      AND i.feed_identity IS NOT NULL
      AND i.first_supply_time >= i.trigger_time
      AND i.first_borrow_time >= i.first_supply_time AS has_replayable_constraint,
    date_diff('second', i.trigger_time, i.first_supply_time) AS trigger_to_impact_seconds,
    CASE
      WHEN i.feed_identity_source = 'label_matched' AND i.impact_tx_count > 1 THEN 'impact_led_answerupdated_closure'
      WHEN i.feed_identity_source = 'impact_led_lower_bound_unresolved' AND i.impact_tx_count > 1 THEN 'impact_led_lower_bound_unresolved'
      WHEN i.feed_identity_source = 'label_matched' THEN 'answerupdated_identity_match'
      ELSE 'raw_transfer_heuristic'
    END AS source_quality,
    CASE
      WHEN i.feed_identity_source = 'label_matched' AND i.impact_tx_count > 1 THEN 1
      WHEN i.feed_identity_source = 'impact_led_lower_bound_unresolved' AND i.impact_tx_count > 1 THEN 2
      WHEN i.feed_identity_source = 'label_matched' THEN 2
      ELSE 4
    END AS source_quality_rank
  FROM latest_prior_answer_updated i
),
tiered AS (
  SELECT
    *,
    CASE
      WHEN has_trigger AND has_oracle_anomaly AND has_lending_impact AND has_actor
        AND has_temporal_order AND has_replayable_constraint THEN 'A_replayable'
      WHEN has_trigger AND has_oracle_anomaly AND has_lending_impact AND has_temporal_order
        THEN 'B_high_confidence_incomplete'
      WHEN has_trigger AND has_oracle_anomaly THEN 'C_remote_anomaly_only'
      ELSE 'reject_out_of_scope'
    END AS evidence_tier,
    CASE
      WHEN has_trigger AND has_oracle_anomaly AND has_lending_impact AND has_actor
        AND has_temporal_order AND has_replayable_constraint
        THEN 'latest prior AnswerUpdated, same-account collateral supply, borrow outflow, actor, temporal order, and replayable fields are present'
      WHEN has_trigger AND has_oracle_anomaly AND has_lending_impact AND has_temporal_order
        AND source_quality = 'impact_led_lower_bound_unresolved'
        THEN 'lower-bound stale marker and same-account lending impact are present, but feed identity metadata is incomplete'
      WHEN has_trigger AND has_oracle_anomaly AND has_lending_impact AND has_temporal_order
        THEN 'freshness anomaly and same-account lending impact are present, but source metadata or replay fields are incomplete'
      WHEN has_trigger AND has_oracle_anomaly
        THEN 'freshness anomaly is visible remotely, but lending impact is not closed'
      ELSE 'outside lending oracle-consumption scope'
    END AS closure_reason
  FROM features
)
"""


def freshness_sql(start: str, end: str, chains: List[str] | None = None) -> str:
    return f"""-- R3: freshness-handling failure broad search, impact-led lower-bound stale closure.
-- Goal: find same-account lending closures where collateral supply/deposit is
-- followed by non-collateral borrow outflow, then associate the impact with the
-- latest prior Chainlink AnswerUpdated. Label-matched feeds can be replayable;
-- lower-bound stale markers with incomplete feed metadata are retained as
-- high-confidence incomplete candidates for local historical validation.
-- This index-level candidate query is intentionally not top-k limited; local
-- downloads are bounded later by the materialization queue. Candidates are
-- tiered by evidence closure, not a weighted score.
-- Cost guardrail: impact transfers are limited to generic lending market-token
-- inventory before oracle logs are joined.
{_freshness_common_ctes(start, end, chains)}
SELECT *
FROM tiered
WHERE evidence_tier IN ('A_replayable', 'B_high_confidence_incomplete', 'C_remote_anomaly_only')
{EVIDENCE_ORDER_BY};
"""


def freshness_preflight_count_sql(start: str, end: str, chains: List[str] | None = None) -> str:
    return f"""-- R3 preflight counts: freshness-handling impact-led lower-bound stale closure.
-- This compact query reports stage cardinalities before running the full
-- candidate query. It does not download receipts, call contract methods, or
-- produce future-looking targets.
{_freshness_common_ctes(start, end, chains)},
stage_counts AS (
  SELECT
    'market_inventory' AS preflight_stage,
    blockchain AS chain,
    COUNT(*) AS row_count,
    COUNT(DISTINCT market_address) AS address_count,
    COUNT(DISTINCT protocol_cluster_id) AS protocol_cluster_count,
    CAST(NULL AS bigint) AS tx_count
  FROM market_inventory
  GROUP BY 1, 2

  UNION ALL

  SELECT
    'collateral_supply_events' AS preflight_stage,
    blockchain AS chain,
    COUNT(*) AS row_count,
    COUNT(DISTINCT collateral_market) AS address_count,
    COUNT(DISTINCT protocol_cluster_id) AS protocol_cluster_count,
    COUNT(DISTINCT supply_tx) AS tx_count
  FROM collateral_supply_events
  GROUP BY 1, 2

  UNION ALL

  SELECT
    'borrow_outflow_events' AS preflight_stage,
    blockchain AS chain,
    COUNT(*) AS row_count,
    COUNT(DISTINCT borrow_market) AS address_count,
    COUNT(DISTINCT protocol_cluster_id) AS protocol_cluster_count,
    COUNT(DISTINCT borrow_tx) AS tx_count
  FROM borrow_outflow_events
  GROUP BY 1, 2

  UNION ALL

  SELECT
    'same_actor_impact' AS preflight_stage,
    blockchain AS chain,
    COUNT(*) AS row_count,
    COUNT(DISTINCT collateral_market) AS address_count,
    COUNT(DISTINCT protocol_cluster_id) AS protocol_cluster_count,
    COUNT(DISTINCT first_borrow_tx) AS tx_count
  FROM same_actor_impact
  GROUP BY 1, 2

  UNION ALL

  SELECT
    'label_matched_answer_updated' AS preflight_stage,
    blockchain AS chain,
    COUNT(*) AS row_count,
    COUNT(DISTINCT feed) AS address_count,
    COUNT(DISTINCT protocol_cluster_id) AS protocol_cluster_count,
    COUNT(DISTINCT trigger_tx) AS tx_count
  FROM label_matched_answer_updated
  GROUP BY 1, 2

  UNION ALL

  SELECT
    'lower_bound_unlabeled_answer_updated' AS preflight_stage,
    blockchain AS chain,
    COUNT(*) AS row_count,
    COUNT(DISTINCT feed) AS address_count,
    COUNT(DISTINCT protocol_cluster_id) AS protocol_cluster_count,
    COUNT(DISTINCT trigger_tx) AS tx_count
  FROM lower_bound_unlabeled_answer_updated
  GROUP BY 1, 2

  UNION ALL

  SELECT
    'latest_prior_join' AS preflight_stage,
    blockchain AS chain,
    COUNT(*) AS row_count,
    COUNT(DISTINCT feed) AS address_count,
    COUNT(DISTINCT protocol_cluster_id) AS protocol_cluster_count,
    COUNT(DISTINCT trigger_tx) AS tx_count
  FROM latest_prior_answer_updated
  GROUP BY 1, 2

  UNION ALL

  SELECT
    'tiered_candidates' AS preflight_stage,
    chain,
    COUNT(*) AS row_count,
    CAST(NULL AS bigint) AS address_count,
    CAST(NULL AS bigint) AS protocol_cluster_count,
    COUNT(DISTINCT trigger_tx) AS tx_count
  FROM tiered
  WHERE evidence_tier IN ('A_replayable', 'B_high_confidence_incomplete', 'C_remote_anomaly_only')
  GROUP BY 1, 2
)
SELECT
  chain,
  'freshness_handling_failure' AS failure_class,
  preflight_stage,
  DATE '{start}' AS start_date,
  DATE '{end}' AS end_date,
  row_count,
  address_count,
  protocol_cluster_count,
  tx_count
FROM stage_counts
ORDER BY chain, preflight_stage;
"""


def materialization_queue_sql() -> str:
    return f"""-- Union search outputs into a local-materialization queue.
-- Replace the CTE bodies below with saved Dune query result tables or uploaded CSVs.
-- Only evidence tiers A/B enter the local download queue. Tier C stays remote
-- unless it is manually promoted after additional historical evidence appears.
-- This queue is gate-only: it does not use top-k, weighted scores, or
-- amount-based truncation. If the accepted set is too large, tighten the
-- evidence-closure predicates in the candidate queries instead of cutting rows.
WITH
feed_binding_candidates AS (
  SELECT * FROM query_0000000 -- R1 output placeholder
),
price_composition_candidates AS (
  SELECT * FROM query_0000001 -- R2 output placeholder
),
freshness_candidates AS (
  SELECT * FROM query_0000002 -- R3 output placeholder
),
all_candidates AS (
  SELECT * FROM feed_binding_candidates
  UNION ALL
  SELECT * FROM price_composition_candidates
  UNION ALL
  SELECT * FROM freshness_candidates
)
SELECT
  chain,
  protocol,
  failure_class,
  trigger_tx,
  trigger_block,
  trigger_time,
  affected_asset,
  evidence_tier,
  closure_reason,
  has_trigger,
  has_oracle_anomaly,
  has_lending_impact,
  has_actor,
  has_temporal_order,
  has_replayable_constraint,
  trigger_to_impact_seconds,
  impact_tx_count,
  impact_usd_known,
  impact_txs,
  source_quality,
  source_quality_rank,
  'download_minimal_causal_trace' AS materialization_action
FROM all_candidates
WHERE
  evidence_tier = 'A_replayable'
  OR (
    evidence_tier = 'B_high_confidence_incomplete'
    AND has_lending_impact = TRUE
    AND has_temporal_order = TRUE
    AND source_quality_rank <= 2
    AND impact_tx_count > 0
    AND trigger_to_impact_seconds >= 0
    AND trigger_to_impact_seconds <= CASE failure_class
      WHEN 'feed_binding_failure' THEN 86400
      WHEN 'price_composition_failure' THEN 86400
      WHEN 'freshness_handling_failure' THEN 86400
      ELSE 86400
    END
  )
{EVIDENCE_ORDER_BY};
"""


def render_queries(start: str, end: str, chains: List[str] | None = None) -> Dict[str, str]:
    manifest = read_json(repo_path("artifacts", "dataset_manifest.json"))
    parsed_chains = parse_chains(chains)
    return {
        "01_seed_set.sql": seed_case_sql(manifest),
        "02_feed_binding_candidates.sql": feed_binding_sql(start, end, parsed_chains),
        "03_price_composition_candidates.sql": price_composition_sql(start, end, parsed_chains),
        "04_freshness_candidates.sql": freshness_sql(start, end, parsed_chains),
        "05_materialization_queue.sql": materialization_queue_sql(),
    }


def write_queries(queries: Dict[str, str]) -> List[Path]:
    out_dir = repo_path("artifacts", "broad_search", "sql")
    ensure_dir(out_dir)
    paths: List[Path] = []
    for name, sql in queries.items():
        path = out_dir / name
        path.write_text(sql, encoding="utf-8")
        paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render read-only Dune SQL templates for broad oracle-consumption failure search."
    )
    parser.add_argument("--start", default=DEFAULT_START, help="Inclusive start date in YYYY-MM-DD.")
    parser.add_argument("--end", default=DEFAULT_END, help="Inclusive end date in YYYY-MM-DD.")
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Deprecated compatibility flag; ignored because broad-search queues are evidence-gate only.",
    )
    parser.add_argument(
        "--chains",
        default=DEFAULT_CHAINS,
        help="Comma-separated Dune chain names or aliases. Use an empty string to omit a chain filter.",
    )
    args = parser.parse_args()

    paths = write_queries(render_queries(args.start, args.end, parse_chains(args.chains)))
    print("Wrote broad-search SQL templates:")
    for path in paths:
        print(f"- {path}")
    if args.top_k is not None:
        print("--top-k is deprecated and ignored; queue size is controlled by evidence-closure gates.")
    print("No Dune query was executed and no paid API call was made.")


if __name__ == "__main__":
    main()
