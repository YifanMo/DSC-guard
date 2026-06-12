#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any, DefaultDict, Dict, List, Optional, Set, Tuple

from common import PipelineError, get_case, normalize_symbol, read_jsonl, repo_path, write_json


MATERIAL_COLLATERAL_INCREASE_RATIO = 0.10


class Verifier:
    def __init__(self, case: Dict[str, Any], records: List[Dict[str, Any]]):
        self.case = case
        self.records = sorted(
            records,
            key=lambda item: (
                int(item.get("block_number", 0)),
                int(item.get("transaction_index", 0)),
                int(item.get("log_index", 0)),
            ),
        )
        self.constraints = case.get("constraints", [])
        self.oracle_map: Dict[str, Dict[str, Any]] = {}
        self.stale_assets: Dict[str, Dict[str, Any]] = {}
        self.formula_violations: Dict[str, Dict[str, Any]] = {}
        self.price_source_outliers: Dict[str, Dict[str, Any]] = {}
        self.implementation_mismatches: Dict[str, Dict[str, Any]] = {}
        self.alerts: List[Dict[str, Any]] = []
        self.attackers: DefaultDict[str, Dict[str, Any]] = defaultdict(
            lambda: {"roles": set(), "tx_hashes": set(), "profit_summary": []}
        )
        self.collateral_enabling_supply_indices, self.collateral_enabling_supply_reasons = (
            self._compute_collateral_enabling_supply_indices()
        )

    def _constraint_matches_asset(self, constraint: Dict[str, Any], asset: str) -> bool:
        candidates = [constraint.get("asset", "")]
        candidates.extend(constraint.get("asset_aliases", []) or [])
        return normalize_symbol(asset) in {normalize_symbol(candidate) for candidate in candidates if candidate}

    def _add_alert(self, alert: Dict[str, Any]) -> None:
        role_by_type = {
            "feed_mismatch": "oracle_boundary",
            "formula_mismatch": "oracle_boundary",
            "stale_oracle": "oracle_boundary",
            "price_source_outlier": "oracle_boundary",
            "decimal_semantics_mismatch": "oracle_boundary",
            "collateral_enabling_supply_under_bad_oracle": "early_evidence",
            "collateral_enabling_supply_under_stale_oracle": "early_evidence",
            "attacker_localization": "impact",
        }
        alert.setdefault("case", self.case["id"])
        alert.setdefault("severity", "medium")
        alert.setdefault("constraint_id", alert.get("id", ""))
        alert.setdefault("record_role", role_by_type.get(alert.get("type", ""), "constraint_alert"))
        tx_hash = alert.get("tx_hash")
        alert.setdefault("evidence_tx_hashes", [tx_hash] if tx_hash else [])
        alert.setdefault("candidate_actor_roles", {})
        self.alerts.append(alert)

    def _mark_attacker(self, address: str, role: str, tx_hash: str, summary: str) -> None:
        if not address:
            return
        candidate = self.attackers[address]
        candidate["roles"].add(role)
        candidate["tx_hashes"].add(tx_hash)
        if summary:
            candidate["profit_summary"].append(summary)

    def _supply_actor(self, decoded: Dict[str, Any]) -> str:
        return decoded.get("supplier") or decoded.get("account") or decoded.get("actor", "")

    def _impact_actor(self, event_type: str, decoded: Dict[str, Any]) -> str:
        if event_type == "LIQUIDATE":
            return decoded.get("borrower") or decoded.get("account") or decoded.get("liquidator", "")
        return decoded.get("borrower") or decoded.get("account") or decoded.get("actor", "")

    def _apply_oracle_boundary_to_sets(
        self,
        record: Dict[str, Any],
        bad_assets: Dict[str, Set[str]],
    ) -> None:
        decoded = record.get("decoded") or {}
        event_type = record.get("event_type")
        asset = decoded.get("asset", "")
        asset_key = normalize_symbol(asset)
        if not asset_key:
            return
        if event_type == "ORACLE_FEED_SET":
            actual = decoded.get("actual_feed", "")
            expected = decoded.get("expected_feed", "")
            for constraint in self.constraints:
                if constraint.get("type") != "feed_mismatch" or not self._constraint_matches_asset(constraint, asset):
                    continue
                forbidden = constraint.get("forbidden_feed")
                mismatch = bool(forbidden and normalize_symbol(actual) == normalize_symbol(forbidden))
                mismatch = mismatch or (
                    constraint.get("expected_feed")
                    and normalize_symbol(actual) != normalize_symbol(constraint["expected_feed"])
                )
                if mismatch:
                    bad_assets[asset_key].add("feed_mismatch")
        elif event_type == "ORACLE_FORMULA_SET":
            actual = decoded.get("actual_formula", "")
            expected = decoded.get("expected_formula", "")
            for constraint in self.constraints:
                if constraint.get("type") != "formula_mismatch" or not self._constraint_matches_asset(constraint, asset):
                    continue
                if normalize_symbol(actual) != normalize_symbol(constraint.get("expected_formula", expected)):
                    bad_assets[asset_key].add("formula_mismatch")
        elif event_type in {"ANSWER_UPDATED", "STALE_ORACLE_START"}:
            for constraint in self.constraints:
                if constraint.get("type") == "stale_oracle" and self._constraint_matches_asset(constraint, asset):
                    if event_type == "STALE_ORACLE_START":
                        bad_assets[asset_key].add("stale_oracle")
                        continue
                    block_timestamp = int(record.get("block_timestamp") or 0)
                    updated_at = int(decoded.get("updated_at") or block_timestamp)
                    heartbeat = int(constraint.get("heartbeat_seconds") or 0)
                    stale = heartbeat > 0 and block_timestamp - updated_at > heartbeat
                    if stale or bool(decoded.get("lower_bound_hit")):
                        bad_assets[asset_key].add("stale_oracle")
        elif event_type == "ORACLE_PRICE_MALFUNCTION":
            for constraint in self.constraints:
                if constraint.get("type") == "price_source_outlier" and self._constraint_matches_asset(constraint, asset):
                    bad_assets[asset_key].add("price_source_outlier")
        elif event_type == "ORACLE_IMPLEMENTATION_MISMATCH":
            for constraint in self.constraints:
                if constraint.get("type") == "decimal_semantics_mismatch" and self._constraint_matches_asset(constraint, asset):
                    bad_assets[asset_key].add("decimal_semantics_mismatch")

    def _compute_collateral_enabling_supply_indices(self) -> Tuple[Set[int], Dict[int, List[str]]]:
        """Find supply logs that causally enable a later impact under an active oracle anomaly.

        A supply is treated as early evidence only when it is bound to an active
        bad-oracle asset and the same actor later produces a borrow/liquidation
        impact. To avoid marking every repeated deposit, the log-only
        approximation keeps the first risky collateral supply for an actor and
        the latest risky top-up before each downstream impact.
        """
        bad_assets: DefaultDict[str, Set[str]] = defaultdict(set)
        first_supply_by_actor_asset: Dict[Tuple[str, str], int] = {}
        latest_supply_by_actor_asset: Dict[Tuple[str, str], int] = {}
        material_supply_by_actor_asset: DefaultDict[Tuple[str, str], Set[int]] = defaultdict(set)
        cumulative_supply_amount_by_actor_asset: DefaultDict[Tuple[str, str], float] = defaultdict(float)
        selected: Set[int] = set()
        reasons_by_index: DefaultDict[int, Set[str]] = defaultdict(set)

        for idx, record in enumerate(self.records):
            event_type = record.get("event_type")
            decoded = record.get("decoded") or {}
            self._apply_oracle_boundary_to_sets(record, bad_assets)

            if event_type == "SUPPLY":
                asset_key = normalize_symbol(decoded.get("asset", ""))
                actor = normalize_symbol(self._supply_actor(decoded))
                if not actor or not asset_key or asset_key not in bad_assets:
                    continue
                key = (actor, asset_key)
                latest_supply_by_actor_asset[key] = idx
                first_supply_by_actor_asset.setdefault(key, idx)
                amount = _float_or_none(decoded.get("amount"))
                previous_amount = cumulative_supply_amount_by_actor_asset[key]
                if amount is not None and amount > 0:
                    if previous_amount <= 0 or amount / previous_amount >= MATERIAL_COLLATERAL_INCREASE_RATIO:
                        material_supply_by_actor_asset[key].add(idx)
                    cumulative_supply_amount_by_actor_asset[key] = previous_amount + amount
                continue

            if event_type not in {"BORROW", "LIQUIDATE"}:
                continue
            collateral_key = normalize_symbol(decoded.get("collateral_asset", ""))
            actor = normalize_symbol(self._impact_actor(event_type, decoded))
            if not actor or not collateral_key or collateral_key not in bad_assets:
                continue
            key = (actor, collateral_key)
            first_idx = first_supply_by_actor_asset.get(key)
            latest_idx = latest_supply_by_actor_asset.get(key)
            reason_prefix = "stale_oracle" if "stale_oracle" in bad_assets[collateral_key] else "bad_oracle"
            if first_idx is not None:
                selected.add(first_idx)
                reasons_by_index[first_idx].add(f"{reason_prefix}:first_risky_collateral_supply")
            if latest_idx is not None:
                selected.add(latest_idx)
                reasons_by_index[latest_idx].add(f"{reason_prefix}:latest_topup_before_impact")
            for material_idx in material_supply_by_actor_asset.get(key, set()):
                selected.add(material_idx)
                reasons_by_index[material_idx].add(
                    f"{reason_prefix}:material_collateral_increase_>={MATERIAL_COLLATERAL_INCREASE_RATIO:.0%}"
                )

        return selected, {idx: sorted(reasons) for idx, reasons in reasons_by_index.items()}

    def _handle_oracle_feed_set(self, record: Dict[str, Any], decoded: Dict[str, Any]) -> None:
        asset = decoded.get("asset", "")
        expected = decoded.get("expected_feed", "")
        actual = decoded.get("actual_feed", "")
        self.oracle_map[normalize_symbol(asset)] = {
            "asset": asset,
            "expected_feed": expected,
            "actual_feed": actual,
            "tx_hash": record.get("tx_hash"),
            "block_number": record.get("block_number"),
        }
        for constraint in self.constraints:
            if constraint.get("type") != "feed_mismatch" or not self._constraint_matches_asset(constraint, asset):
                continue
            forbidden = constraint.get("forbidden_feed")
            mismatch = bool(forbidden and normalize_symbol(actual) == normalize_symbol(forbidden))
            mismatch = mismatch or (
                constraint.get("expected_feed")
                and normalize_symbol(actual) != normalize_symbol(constraint["expected_feed"])
            )
            if mismatch:
                self._add_alert(
                    {
                        "id": constraint["id"],
                        "type": "feed_mismatch",
                        "severity": constraint.get("severity", "critical"),
                        "tx_hash": record.get("tx_hash"),
                        "block_number": record.get("block_number"),
                        "details": {
                            "asset": asset,
                            "expected_feed": constraint.get("expected_feed", expected),
                            "actual_feed": actual,
                        },
                    }
                )

    def _handle_formula_set(self, record: Dict[str, Any], decoded: Dict[str, Any]) -> None:
        asset = decoded.get("asset", "")
        actual = decoded.get("actual_formula", "")
        expected = decoded.get("expected_formula", "")
        self.formula_violations[normalize_symbol(asset)] = {
            "asset": asset,
            "expected_formula": expected,
            "actual_formula": actual,
            "tx_hash": record.get("tx_hash"),
        }
        for constraint in self.constraints:
            if constraint.get("type") != "formula_mismatch" or not self._constraint_matches_asset(constraint, asset):
                continue
            if normalize_symbol(actual) != normalize_symbol(constraint.get("expected_formula", expected)):
                self._add_alert(
                    {
                        "id": constraint["id"],
                        "type": "formula_mismatch",
                        "severity": constraint.get("severity", "critical"),
                        "tx_hash": record.get("tx_hash"),
                        "block_number": record.get("block_number"),
                        "details": {
                            "asset": asset,
                            "expected_formula": constraint.get("expected_formula", expected),
                            "actual_formula": actual,
                        },
                    }
                )

    def _handle_answer_updated(self, record: Dict[str, Any], decoded: Dict[str, Any]) -> None:
        asset = decoded.get("asset", "")
        block_timestamp = int(record.get("block_timestamp") or 0)
        updated_at = int(decoded.get("updated_at") or block_timestamp)
        lower_bound_hit = bool(decoded.get("lower_bound_hit"))
        for constraint in self.constraints:
            if constraint.get("type") != "stale_oracle" or not self._constraint_matches_asset(constraint, asset):
                continue
            heartbeat = int(constraint.get("heartbeat_seconds") or 0)
            stale = heartbeat > 0 and block_timestamp - updated_at > heartbeat
            if stale or lower_bound_hit:
                self.stale_assets[normalize_symbol(asset)] = {
                    "asset": asset,
                    "feed": decoded.get("feed"),
                    "answer": decoded.get("answer"),
                    "updated_at": updated_at,
                    "block_timestamp": block_timestamp,
                    "tx_hash": record.get("tx_hash"),
                    "reason": "lower_bound_hit" if lower_bound_hit else "heartbeat_exceeded",
                }
                self._add_alert(
                    {
                        "id": constraint["id"],
                        "type": "stale_oracle",
                        "severity": constraint.get("severity", "critical"),
                        "tx_hash": record.get("tx_hash"),
                        "block_number": record.get("block_number"),
                        "details": self.stale_assets[normalize_symbol(asset)],
                    }
                )

    def _handle_stale_start(self, record: Dict[str, Any], decoded: Dict[str, Any]) -> None:
        asset = decoded.get("asset", "")
        self.stale_assets[normalize_symbol(asset)] = {
            "asset": asset,
            "feed": decoded.get("feed"),
            "answer": decoded.get("answer"),
            "updated_at": decoded.get("updated_at"),
            "block_timestamp": record.get("block_timestamp"),
            "tx_hash": record.get("tx_hash"),
            "reason": decoded.get("reason", "explicit_stale_marker"),
        }
        for constraint in self.constraints:
            if constraint.get("type") == "stale_oracle" and self._constraint_matches_asset(constraint, asset):
                self._add_alert(
                    {
                        "id": constraint["id"],
                        "type": "stale_oracle",
                        "severity": constraint.get("severity", "critical"),
                        "tx_hash": record.get("tx_hash"),
                        "block_number": record.get("block_number"),
                        "details": self.stale_assets[normalize_symbol(asset)],
                    }
                )

    def _handle_price_malfunction(self, record: Dict[str, Any], decoded: Dict[str, Any]) -> None:
        asset = decoded.get("asset", "")
        self.price_source_outliers[normalize_symbol(asset)] = {
            "asset": asset,
            "feed": decoded.get("feed"),
            "quote_asset": decoded.get("quote_asset"),
            "reported_rate": decoded.get("reported_rate"),
            "block_timestamp": record.get("block_timestamp"),
            "tx_hash": record.get("tx_hash"),
            "reason": decoded.get("actual_fault", "price_source_outlier"),
        }
        for constraint in self.constraints:
            if constraint.get("type") == "price_source_outlier" and self._constraint_matches_asset(constraint, asset):
                self._add_alert(
                    {
                        "id": constraint["id"],
                        "type": "price_source_outlier",
                        "severity": constraint.get("severity", "critical"),
                        "tx_hash": record.get("tx_hash"),
                        "block_number": record.get("block_number"),
                        "details": self.price_source_outliers[normalize_symbol(asset)],
                    }
                )

    def _handle_implementation_mismatch(self, record: Dict[str, Any], decoded: Dict[str, Any]) -> None:
        asset = decoded.get("asset", "")
        self.implementation_mismatches[normalize_symbol(asset)] = {
            "asset": asset,
            "expected_oracle": decoded.get("expected_oracle"),
            "actual_oracle": decoded.get("actual_oracle"),
            "expected_semantics": decoded.get("expected_semantics"),
            "actual_semantics": decoded.get("actual_semantics"),
            "block_timestamp": record.get("block_timestamp"),
            "tx_hash": record.get("tx_hash"),
            "reason": decoded.get("actual_fault", "oracle_implementation_mismatch"),
        }
        for constraint in self.constraints:
            if constraint.get("type") == "decimal_semantics_mismatch" and self._constraint_matches_asset(constraint, asset):
                self._add_alert(
                    {
                        "id": constraint["id"],
                        "type": "decimal_semantics_mismatch",
                        "severity": constraint.get("severity", "critical"),
                        "tx_hash": record.get("tx_hash"),
                        "block_number": record.get("block_number"),
                        "details": self.implementation_mismatches[normalize_symbol(asset)],
                    }
                )

    def _handle_borrow(self, record: Dict[str, Any], decoded: Dict[str, Any]) -> None:
        borrower = decoded.get("borrower") or decoded.get("account", "")
        collateral = decoded.get("collateral_asset", "")
        borrow_asset = decoded.get("borrow_asset", "")
        collateral_key = normalize_symbol(collateral)
        borrow_asset_key = normalize_symbol(borrow_asset)
        tx_hash = record.get("tx_hash", "")
        bad_reasons = []
        if collateral_key in self.oracle_map:
            bad_reasons.append("feed_mismatch")
        if collateral_key in self.stale_assets:
            bad_reasons.append("stale_oracle")
        if collateral_key in self.formula_violations:
            bad_reasons.append("formula_mismatch")
        if collateral_key in self.price_source_outliers:
            bad_reasons.append("price_source_outlier")
        if collateral_key in self.implementation_mismatches:
            bad_reasons.append("decimal_semantics_mismatch")
        if borrow_asset_key in self.formula_violations:
            bad_reasons.append("borrow_asset_formula_mismatch")
        reported = _float_or_none(decoded.get("collateral_value_usd_reported"))
        expected = _float_or_none(decoded.get("collateral_value_usd_expected"))
        if reported is not None and expected is not None and expected > 0 and reported / expected > 10:
            bad_reasons.append("collateral_value_inflated")
        if bad_reasons:
            self._add_alert(
                {
                    "id": "BORROW_AFTER_ORACLE_VIOLATION",
                    "type": "attacker_localization",
                    "severity": "critical",
                    "tx_hash": tx_hash,
                    "block_number": record.get("block_number"),
                    "record_role": "borrow",
                    "candidate_actor_roles": {
                        "borrower": borrower,
                        "actor": decoded.get("actor", ""),
                    },
                    "details": {
                        "borrower": borrower,
                        "collateral_asset": collateral,
                        "borrow_asset": decoded.get("borrow_asset"),
                        "borrow_amount": decoded.get("borrow_amount"),
                        "reasons": sorted(set(bad_reasons)),
                    },
                }
            )
            summary = f"borrowed {decoded.get('borrow_amount')} {decoded.get('borrow_asset')} against {collateral}"
            self._mark_attacker(borrower, "borrower", tx_hash, summary)
            actor = decoded.get("actor", "")
            if actor and normalize_symbol(actor) != normalize_symbol(borrower):
                self._mark_attacker(actor, "actor", tx_hash, summary)

    def _handle_supply(self, record_index: int, record: Dict[str, Any], decoded: Dict[str, Any]) -> None:
        if record_index not in self.collateral_enabling_supply_indices:
            return
        asset = decoded.get("asset", "")
        asset_key = normalize_symbol(asset)
        supplier = self._supply_actor(decoded)
        reasons = self.collateral_enabling_supply_reasons.get(record_index, [])
        alert_type = (
            "collateral_enabling_supply_under_stale_oracle"
            if asset_key in self.stale_assets
            else "collateral_enabling_supply_under_bad_oracle"
        )
        self._add_alert(
            {
                "id": "COLLATERAL_ENABLING_SUPPLY",
                "type": alert_type,
                "severity": "high",
                "tx_hash": record.get("tx_hash"),
                "block_number": record.get("block_number"),
                "record_role": "early_evidence",
                "candidate_actor_roles": {
                    "supplier": supplier,
                    "actor": decoded.get("actor", ""),
                },
                "details": {
                    "supplier": supplier,
                    "asset": asset,
                    "amount": decoded.get("amount"),
                    "reasons": reasons,
                    "evidence_rule": "first risky collateral supply or latest top-up before same-actor impact",
                },
            }
        )

    def _handle_liquidate(self, record: Dict[str, Any], decoded: Dict[str, Any]) -> None:
        liquidator = decoded.get("liquidator", "")
        collateral = decoded.get("collateral_asset", "")
        collateral_key = normalize_symbol(collateral)
        if collateral_key not in self.formula_violations and collateral_key not in self.oracle_map:
            return
        tx_hash = record.get("tx_hash", "")
        self._add_alert(
            {
                "id": "LIQUIDATION_AFTER_ORACLE_VIOLATION",
                "type": "attacker_localization",
                "severity": "high",
                "tx_hash": tx_hash,
                "block_number": record.get("block_number"),
                "record_role": "liquidation",
                "candidate_actor_roles": {
                    "liquidator": liquidator,
                    "borrower": decoded.get("borrower", ""),
                },
                "details": decoded,
            }
        )
        summary = f"liquidated {decoded.get('seized_amount')} {collateral}"
        self._mark_attacker(liquidator, "liquidator", tx_hash, summary)

    def replay(self) -> Dict[str, Any]:
        for idx, record in enumerate(self.records):
            decoded = record.get("decoded") or {}
            event_type = record.get("event_type")
            if event_type == "ORACLE_FEED_SET":
                self._handle_oracle_feed_set(record, decoded)
            elif event_type == "ORACLE_FORMULA_SET":
                self._handle_formula_set(record, decoded)
            elif event_type == "ANSWER_UPDATED":
                self._handle_answer_updated(record, decoded)
            elif event_type == "STALE_ORACLE_START":
                self._handle_stale_start(record, decoded)
            elif event_type == "ORACLE_PRICE_MALFUNCTION":
                self._handle_price_malfunction(record, decoded)
            elif event_type == "ORACLE_IMPLEMENTATION_MISMATCH":
                self._handle_implementation_mismatch(record, decoded)
            elif event_type == "SUPPLY":
                self._handle_supply(idx, record, decoded)
            elif event_type == "BORROW":
                self._handle_borrow(record, decoded)
            elif event_type == "LIQUIDATE":
                self._handle_liquidate(record, decoded)
        return self.result()

    def result(self) -> Dict[str, Any]:
        attackers = []
        for address, data in self.attackers.items():
            attackers.append(
                {
                    "address": address,
                    "roles": sorted(data["roles"]),
                    "tx_hashes": sorted(data["tx_hashes"]),
                    "profit_summary": data["profit_summary"],
                }
            )
        return {
            "case": self.case["id"],
            "case_name": self.case["name"],
            "chain": self.case["chain"],
            "alerts": self.alerts,
            "attacker_candidates": attackers,
            "oracle_map": self.oracle_map,
            "stale_assets": self.stale_assets,
            "formula_violations": self.formula_violations,
            "price_source_outliers": self.price_source_outliers,
            "implementation_mismatches": self.implementation_mismatches,
            "input_records": len(self.records),
            "known_txs": self.case.get("known_txs", {}),
        }


def _float_or_none(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def render_markdown(result: Dict[str, Any]) -> str:
    lines = [
        f"# {result['case_name']}",
        "",
        f"- Case: `{result['case']}`",
        f"- Chain: `{result['chain']}`",
        f"- Input records: `{result['input_records']}`",
        f"- Alerts: `{len(result['alerts'])}`",
        "",
        "## Key Transactions",
        "",
    ]
    known = result.get("known_txs") or {}
    if known:
        for role, tx_hash in known.items():
            lines.append(f"- {role}: `{tx_hash}`")
    else:
        lines.append("- No canonical transaction hashes configured yet; use fixture evidence or fill `known_txs`.")
    lines.extend(["", "## Alerts", ""])
    if result["alerts"]:
        for alert in result["alerts"]:
            tx_hash = alert.get("tx_hash", "")
            details = alert.get("details", {})
            lines.append(
                f"- `{alert['id']}` ({alert['type']}, {alert.get('severity')}) at block `{alert.get('block_number')}`, tx `{tx_hash}`"
            )
            if details:
                detail_text = ", ".join(f"{key}={value}" for key, value in details.items() if value not in (None, ""))
                lines.append(f"  - {detail_text}")
    else:
        lines.append("- No alerts.")
    lines.extend(["", "## Attacker Candidates", ""])
    if result["attacker_candidates"]:
        for candidate in result["attacker_candidates"]:
            txs = ", ".join(f"`{tx}`" for tx in candidate["tx_hashes"])
            lines.append(
                f"- `{candidate['address']}` roles={candidate['roles']} txs={txs}"
            )
            for summary in candidate.get("profit_summary", []):
                lines.append(f"  - {summary}")
    else:
        lines.append("- No attacker candidates identified.")
    lines.append("")
    return "\n".join(lines)


def verify(case_id: str, trace_path: Optional[Path] = None, results_dir: Optional[Path] = None) -> Dict[str, Any]:
    case = get_case(case_id)
    input_path = trace_path or repo_path("artifacts", "log_trace", f"{case_id}.jsonl")
    if not input_path.exists():
        raise PipelineError(f"Missing log trace: {input_path}. Run scripts/log_collect.py first.")
    records = read_jsonl(input_path)
    result = Verifier(case, records).replay()
    output_dir = results_dir or repo_path("results")
    evidence_path = output_dir / f"{case_id}_evidence.json"
    report_path = output_dir / f"{case_id}_detection.md"
    write_json(evidence_path, result)
    report_path.write_text(render_markdown(result), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay log trace and verify oracle constraints.")
    parser.add_argument("--case", required=True)
    parser.add_argument("--trace-path", default="", help="Optional input trace path for test isolation.")
    parser.add_argument("--results-dir", default="", help="Optional output directory for report/evidence.")
    args = parser.parse_args()
    try:
        result = verify(
            args.case,
            trace_path=Path(args.trace_path) if args.trace_path else None,
            results_dir=Path(args.results_dir) if args.results_dir else None,
        )
    except PipelineError as exc:
        raise SystemExit(str(exc)) from exc
    print(
        f"Wrote detection report: results/{args.case}_detection.md "
        f"({len(result['alerts'])} alerts, {len(result['attacker_candidates'])} attacker candidates)"
    )


if __name__ == "__main__":
    main()
