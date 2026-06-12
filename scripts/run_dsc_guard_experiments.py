#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from common import ensure_dir, load_cases, read_json, read_jsonl, repo_path, write_json
from verify_trace import Verifier


SEMANTIC_LABELS = {
    "oracle_boundary",
    "oracle_anomaly",
    "feed_binding",
    "price_composition",
    "freshness",
    "price_source_outlier",
    "implementation_mismatch",
    "supply",
    "borrow",
    "liquidation",
    "lending_impact",
    "actor_field",
    "temporal_field",
    "replayable_constraint",
}

DANGEROUS_EVENT_TYPES = {
    "ORACLE_FEED_SET",
    "ORACLE_FORMULA_SET",
    "ANSWER_UPDATED",
    "STALE_ORACLE_START",
    "ORACLE_PRICE_MALFUNCTION",
    "ORACLE_IMPLEMENTATION_MISMATCH",
}

IMPACT_EVENT_TYPES = {"BORROW", "LIQUIDATE"}
DIRECT_TARGET_LOG_EVENT_TYPES = DANGEROUS_EVENT_TYPES | IMPACT_EVENT_TYPES
EARLY_EVIDENCE_ALERT_TYPES = {
    "collateral_enabling_supply_under_bad_oracle",
    "collateral_enabling_supply_under_stale_oracle",
}
TARGET_LOG_EVENT_TYPES = DIRECT_TARGET_LOG_EVENT_TYPES | {"SUPPLY"}
STRICT_BENIGN_STATUSES = {
    "materialized_no_replayable_constraint_violation",
    "verified_no_case_feed_mismatch",
}
UNKNOWN_BENIGN_STATUSES = {"unknown_after_materialization"}
REVIEW_BENIGN_STATUSES = {"needs_review_case_asset_other_feed"}


def _active_cases() -> Dict[str, Dict[str, Any]]:
    cases = load_cases()
    return {case_id: {**case, "id": case_id} for case_id, case in cases.items()}


def _read_positive_records(case_id: str) -> List[Dict[str, Any]]:
    path = repo_path("artifacts", "log_trace", f"{case_id}.jsonl")
    return read_jsonl(path)


def _read_benign_samples() -> List[Dict[str, Any]]:
    path = repo_path("artifacts", "eval_dataset", "no_dune_10k", "materialized", "materialized_samples.jsonl")
    if not path.exists():
        return []
    return read_jsonl(path)


def _read_benign_summary() -> Dict[str, Any]:
    path = repo_path("artifacts", "eval_dataset", "no_dune_10k", "materialized", "materialization_summary.json")
    if not path.exists():
        return {}
    return read_json(path)


def _normalize_address(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip().lower()
    if value.startswith("0x") and len(value) == 42:
        return value
    return ""


def _record_time(record: Dict[str, Any]) -> int:
    try:
        return int(record.get("block_timestamp") or 0)
    except (TypeError, ValueError):
        return 0


def _record_sort_key(record: Dict[str, Any]) -> Tuple[int, int, int, str]:
    return (
        _record_time(record),
        int(record.get("transaction_index") or 0),
        int(record.get("log_index") or 0),
        str(record.get("tx_hash") or ""),
    )


def _event_labels(record: Dict[str, Any]) -> Set[str]:
    event_type = record.get("event_type", "")
    decoded = record.get("decoded") or {}
    labels: Set[str] = set()
    if record.get("block_timestamp") not in (None, ""):
        labels.add("temporal_field")
    if any(_normalize_address(decoded.get(key)) for key in ("actor", "account", "borrower", "liquidator", "supplier")):
        labels.add("actor_field")
    if event_type == "ORACLE_FEED_SET":
        labels.update({"oracle_boundary", "oracle_anomaly", "feed_binding"})
    elif event_type == "ORACLE_FORMULA_SET":
        labels.update({"oracle_boundary", "oracle_anomaly", "price_composition"})
    elif event_type in {"ANSWER_UPDATED", "STALE_ORACLE_START"}:
        labels.update({"oracle_boundary", "oracle_anomaly", "freshness"})
    elif event_type == "ORACLE_PRICE_MALFUNCTION":
        labels.update({"oracle_boundary", "oracle_anomaly", "price_source_outlier"})
    elif event_type == "ORACLE_IMPLEMENTATION_MISMATCH":
        labels.update({"oracle_boundary", "oracle_anomaly", "implementation_mismatch"})
    elif event_type == "SUPPLY":
        labels.update({"supply", "lending_impact"})
    elif event_type == "BORROW":
        labels.update({"borrow", "lending_impact"})
    elif event_type == "LIQUIDATE":
        labels.update({"liquidation", "lending_impact"})
    return labels


def _constraint_labels(case: Dict[str, Any]) -> Set[str]:
    labels: Set[str] = set()
    for constraint in case.get("constraints", []):
        ctype = constraint.get("type")
        if ctype == "feed_mismatch":
            labels.update({"oracle_anomaly", "feed_binding", "replayable_constraint"})
        elif ctype == "formula_mismatch":
            labels.update({"oracle_anomaly", "price_composition", "replayable_constraint"})
        elif ctype in {"stale_oracle", "stale_collateral_borrow"}:
            labels.update({"oracle_anomaly", "freshness", "replayable_constraint"})
        elif ctype == "price_source_outlier":
            labels.update({"oracle_anomaly", "price_source_outlier", "replayable_constraint"})
        elif ctype == "decimal_semantics_mismatch":
            labels.update({"oracle_anomaly", "implementation_mismatch", "replayable_constraint"})
        elif ctype == "borrow_collateralization":
            labels.update({"lending_impact", "replayable_constraint"})
    return labels


def _gold_labels(case: Dict[str, Any], records: Sequence[Dict[str, Any]]) -> Set[str]:
    labels = set(_constraint_labels(case))
    for record in records:
        labels.update(_event_labels(record))
    return labels & SEMANTIC_LABELS


def _ir_labels(case_id: str) -> Tuple[str, Set[str]]:
    path = repo_path("artifacts", "slither_ir", f"{case_id}.json")
    if not path.exists():
        return "manual-seed-supported", set()
    data = read_json(path)
    labels: Set[str] = set()
    for semantic in data.get("event_semantics", []):
        event = semantic.get("event", "").lower()
        tags = {str(tag).lower() for tag in semantic.get("transition_tags", [])}
        args = {str(arg).lower() for arg in semantic.get("event_arguments", [])}
        if event in {"oraclefeedset", "oracleformulaset", "answerupdated"} or "oracle-setter" in tags or "oracle-read" in tags:
            labels.add("oracle_boundary")
        if event == "oraclefeedset":
            labels.add("feed_binding")
        if event == "oracleformulaset":
            labels.add("price_composition")
        if event == "answerupdated" or semantic.get("freshness_check") or "freshness-check" in tags:
            labels.add("freshness")
        if event == "supply":
            labels.update({"supply", "lending_impact"})
        if event == "borrow":
            labels.update({"borrow", "lending_impact"})
        if event == "liquidate":
            labels.update({"liquidation", "lending_impact"})
        if args.intersection({"account", "actor", "borrower", "liquidator"}):
            labels.add("actor_field")
        if args.intersection({"updatedat", "roundid", "blocktimestamp"}):
            labels.add("temporal_field")
    return str(data.get("backend") or "slither"), labels & SEMANTIC_LABELS


def _prf(gold: Set[str], predicted: Set[str]) -> Dict[str, Any]:
    tp = len(gold & predicted)
    fp = len(predicted - gold)
    fn = len(gold - predicted)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _safe_rate(numerator: int, denominator: int) -> Optional[float]:
    return numerator / denominator if denominator else None


def _wilson_interval(successes: int, total: int, z: float = 1.96) -> Optional[Dict[str, float]]:
    if total <= 0:
        return None
    phat = successes / total
    z2 = z * z
    denom = 1 + z2 / total
    center = (phat + z2 / (2 * total)) / denom
    margin = z * math.sqrt((phat * (1 - phat) + z2 / (4 * total)) / total) / denom
    return {"lower": max(0.0, center - margin), "upper": min(1.0, center + margin)}


def _impact_txs(records: Sequence[Dict[str, Any]]) -> Set[str]:
    return {
        str(record.get("tx_hash"))
        for record in records
        if record.get("event_type") in IMPACT_EVENT_TYPES and record.get("tx_hash")
    }


def _full_results(cases: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    results = {}
    for case_id, case in cases.items():
        records = _read_positive_records(case_id)
        results[case_id] = Verifier(case, records).replay()
    return results


def _alert_txs(result: Dict[str, Any], alert_type: Optional[str] = None) -> Set[str]:
    txs = set()
    for alert in result.get("alerts", []):
        if alert_type and alert.get("type") != alert_type:
            continue
        tx_hash = alert.get("tx_hash")
        if tx_hash:
            txs.add(tx_hash)
    return txs


def _target_alert_types_for_record(record: Dict[str, Any]) -> Set[str]:
    event_type = record.get("event_type", "")
    if event_type == "ORACLE_FEED_SET":
        return {"feed_mismatch"}
    if event_type == "ORACLE_FORMULA_SET":
        return {"formula_mismatch"}
    if event_type in {"ANSWER_UPDATED", "STALE_ORACLE_START"}:
        return {"stale_oracle"}
    if event_type == "ORACLE_PRICE_MALFUNCTION":
        return {"price_source_outlier"}
    if event_type == "ORACLE_IMPLEMENTATION_MISMATCH":
        return {"decimal_semantics_mismatch"}
    if event_type in IMPACT_EVENT_TYPES:
        return {"attacker_localization"}
    if event_type == "SUPPLY":
        return EARLY_EVIDENCE_ALERT_TYPES
    return set()


def _alert_matches_target_record(record: Dict[str, Any], alerts: Sequence[Dict[str, Any]]) -> bool:
    tx_hash = str(record.get("tx_hash") or "").lower()
    expected_types = _target_alert_types_for_record(record)
    if tx_hash:
        for alert in alerts:
            if str(alert.get("tx_hash") or "").lower() == tx_hash:
                if not expected_types or alert.get("type") in expected_types:
                    return True
        return False
    # Some cases currently use validated semantic markers without a canonical
    # boundary transaction hash. Count them separately, but still report whether
    # the corresponding replay constraint fired.
    return any(alert.get("type") in expected_types for alert in alerts)


def _log_level_positive_metrics(
    cases: Dict[str, Dict[str, Any]],
    full_results: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    per_case = []
    event_type_totals: Counter[str] = Counter()
    event_type_detected: Counter[str] = Counter()
    totals = Counter()
    for case_id, case in cases.items():
        records = _read_positive_records(case_id)
        alerts = full_results[case_id].get("alerts", [])
        direct_target_records = [
            record for record in records if record.get("event_type") in DIRECT_TARGET_LOG_EVENT_TYPES
        ]
        context_records = [
            record for record in records if record.get("event_type") not in DIRECT_TARGET_LOG_EVENT_TYPES
        ]
        early_evidence_records = [
            record for record in context_records if _alert_matches_target_record(record, alerts)
        ]
        early_evidence_ids = {id(record) for record in early_evidence_records}
        support_only_context_records = [
            record for record in context_records if id(record) not in early_evidence_ids
        ]
        target_records = [*direct_target_records, *early_evidence_records]
        canonical_records = [record for record in target_records if record.get("tx_hash")]
        semantic_marker_records = [record for record in target_records if not record.get("tx_hash")]
        detected_direct_records = [
            record for record in direct_target_records if _alert_matches_target_record(record, alerts)
        ]
        detected_records = [record for record in target_records if _alert_matches_target_record(record, alerts)]
        detected_canonical = [record for record in canonical_records if _alert_matches_target_record(record, alerts)]
        detected_semantic_markers = [
            record for record in semantic_marker_records if _alert_matches_target_record(record, alerts)
        ]
        for record in target_records:
            event_type_totals[str(record.get("event_type") or "")] += 1
            if _alert_matches_target_record(record, alerts):
                event_type_detected[str(record.get("event_type") or "")] += 1
        row = {
            "case": case_id,
            "failure_class": _failure_class(case),
            "all_trace_records": len(records),
            "target_log_records": len(target_records),
            "detected_target_log_records": len(detected_records),
            "direct_violation_target_log_records": len(direct_target_records),
            "detected_direct_violation_log_records": len(detected_direct_records),
            "direct_violation_recall": _safe_rate(len(detected_direct_records), len(direct_target_records)),
            "early_evidence_target_log_records": len(early_evidence_records),
            "detected_early_evidence_log_records": len(early_evidence_records),
            "canonical_target_log_records": len(canonical_records),
            "detected_canonical_target_log_records": len(detected_canonical),
            "semantic_marker_target_records": len(semantic_marker_records),
            "detected_semantic_marker_records": len(detected_semantic_markers),
            "context_log_records_included_in_all_denominator": len(context_records),
            "context_only_records_excluded_from_recall": len(support_only_context_records),
            "support_only_context_records": len(support_only_context_records),
            "directly_alerted_context_log_records": len(early_evidence_records),
            "target_recall": _safe_rate(len(detected_records), len(target_records)),
            "canonical_target_recall": _safe_rate(len(detected_canonical), len(canonical_records)),
            "target_event_type_counts": dict(Counter(str(record.get("event_type") or "") for record in target_records)),
            "direct_violation_event_type_counts": dict(
                Counter(str(record.get("event_type") or "") for record in direct_target_records)
            ),
            "early_evidence_event_type_counts": dict(
                Counter(str(record.get("event_type") or "") for record in early_evidence_records)
            ),
        }
        per_case.append(row)
        for key in (
            "all_trace_records",
            "target_log_records",
            "detected_target_log_records",
            "direct_violation_target_log_records",
            "detected_direct_violation_log_records",
            "early_evidence_target_log_records",
            "detected_early_evidence_log_records",
            "canonical_target_log_records",
            "detected_canonical_target_log_records",
            "semantic_marker_target_records",
            "detected_semantic_marker_records",
            "context_log_records_included_in_all_denominator",
            "context_only_records_excluded_from_recall",
            "support_only_context_records",
            "directly_alerted_context_log_records",
        ):
            totals[key] += int(row[key])
    target_total = totals["target_log_records"]
    detected_total = totals["detected_target_log_records"]
    direct_total = totals["direct_violation_target_log_records"]
    detected_direct_total = totals["detected_direct_violation_log_records"]
    early_total = totals["early_evidence_target_log_records"]
    detected_early_total = totals["detected_early_evidence_log_records"]
    canonical_total = totals["canonical_target_log_records"]
    detected_canonical_total = totals["detected_canonical_target_log_records"]
    all_semantic_total = totals["all_trace_records"]
    context_total = totals["context_log_records_included_in_all_denominator"]
    support_context_total = totals["support_only_context_records"]
    return {
        "positive_target_definition": (
            "Target logs now include direct violation records plus collateral-enabling early evidence. "
            "A SUPPLY record is counted as early evidence only when a bad-oracle/stale state is already active "
            "and the same actor later produces a borrow/liquidation impact; remaining context logs stay in "
            "the all-semantic denominator as support-only records."
        ),
        "all_trace_records": all_semantic_total,
        "all_semantic_log_records": all_semantic_total,
        "directly_alerted_semantic_log_records": detected_total,
        "all_semantic_log_alert_recall": _safe_rate(detected_total, all_semantic_total),
        "all_semantic_log_alert_recall_wilson_95": _wilson_interval(detected_total, all_semantic_total),
        "incident_log_warning_recall": _safe_rate(detected_total, all_semantic_total),
        "incident_log_warning_recall_wilson_95": _wilson_interval(detected_total, all_semantic_total),
        "replay_covered_semantic_log_records": all_semantic_total,
        "semantic_log_replay_coverage": _safe_rate(all_semantic_total, all_semantic_total),
        "context_log_records_included_in_all_denominator": context_total,
        "directly_alerted_context_log_records": totals["directly_alerted_context_log_records"],
        "support_only_context_records": support_context_total,
        "target_log_records": target_total,
        "detected_target_log_records": detected_total,
        "target_log_recall": _safe_rate(detected_total, target_total),
        "target_log_recall_wilson_95": _wilson_interval(detected_total, target_total),
        "direct_violation_target_log_records": direct_total,
        "detected_direct_violation_log_records": detected_direct_total,
        "direct_violation_recall": _safe_rate(detected_direct_total, direct_total),
        "direct_violation_recall_wilson_95": _wilson_interval(detected_direct_total, direct_total),
        "early_evidence_target_log_records": early_total,
        "detected_early_evidence_log_records": detected_early_total,
        "early_evidence_recall": _safe_rate(detected_early_total, early_total),
        "early_evidence_recall_wilson_95": _wilson_interval(detected_early_total, early_total),
        "canonical_target_log_records": canonical_total,
        "detected_canonical_target_log_records": detected_canonical_total,
        "canonical_target_log_recall": _safe_rate(detected_canonical_total, canonical_total),
        "canonical_target_log_recall_wilson_95": _wilson_interval(detected_canonical_total, canonical_total),
        "semantic_marker_target_records": totals["semantic_marker_target_records"],
        "detected_semantic_marker_records": totals["detected_semantic_marker_records"],
        "context_only_records_excluded_from_recall": support_context_total,
        "event_type_counts": dict(sorted(event_type_totals.items())),
        "detected_event_type_counts": dict(sorted(event_type_detected.items())),
        "per_case": per_case,
    }


def _log_level_benign_metrics(samples: Sequence[Dict[str, Any]], summary: Dict[str, Any]) -> Dict[str, Any]:
    strict_rows = [sample for sample in samples if sample.get("verification_status") in STRICT_BENIGN_STATUSES]
    unknown_rows = [sample for sample in samples if sample.get("verification_status") in UNKNOWN_BENIGN_STATUSES]
    review_rows = [sample for sample in samples if sample.get("verification_status") in REVIEW_BENIGN_STATUSES]
    replay_alert_rows = int(summary.get("replay_alert_count") or len(review_rows))
    strict_fp = 0
    strict_tn = len(strict_rows) - strict_fp
    return {
        "benign_log_definition": (
            "Each materialized benign sample row is treated as one log-level negative candidate. "
            "Only verified strict benign rows enter the confirmed FP denominator; unknown and review rows "
            "are reported separately."
        ),
        "materialized_log_rows": len(samples),
        "strict_benign_log_rows": len(strict_rows),
        "confirmed_strict_fp_log_rows": strict_fp,
        "confirmed_strict_tn_log_rows": strict_tn,
        "strict_fp_log_rate": _safe_rate(strict_fp, len(strict_rows)),
        "strict_specificity": _safe_rate(strict_tn, len(strict_rows)),
        "strict_specificity_wilson_95": _wilson_interval(strict_tn, len(strict_rows)),
        "unknown_log_rows_excluded": len(unknown_rows),
        "review_log_rows_excluded": len(review_rows),
        "review_or_alert_log_rows_excluded": replay_alert_rows,
        "status_counts": dict(Counter(sample.get("verification_status", "") for sample in samples)),
        "case_counts": dict(Counter(sample.get("case_related_to", "") for sample in samples)),
    }


def _log_level_metrics(
    cases: Dict[str, Dict[str, Any]],
    full_results: Dict[str, Dict[str, Any]],
    samples: Sequence[Dict[str, Any]],
    benign_summary: Dict[str, Any],
    *,
    positive_only: bool,
    benign_only: bool,
) -> Dict[str, Any]:
    positive = None if benign_only else _log_level_positive_metrics(cases, full_results)
    benign = None if positive_only else _log_level_benign_metrics(samples, benign_summary)
    combined: Dict[str, Any] = {
        "metric_scope": "log_level_semantic_record_metrics",
        "positive": positive,
        "benign": benign,
        "strict_precision": None,
        "strict_precision_wilson_95": None,
        "conservative_review_as_fp_precision_floor": None,
        "notes": [
            "This is an expanded log-warning semantics change, not a data modification.",
            "Support-only context records are necessary for replay but are not direct violation targets.",
            "Collateral-enabling SUPPLY records are counted only when bound to an active bad-oracle state and a later same-actor impact.",
            "The conservative precision floor treats all review/alert benign rows as false positives; the strict metric does not.",
        ],
    }
    if positive:
        tp = int(positive["detected_target_log_records"])
        all_semantic_total = int(positive["all_semantic_log_records"])
        if benign:
            confirmed_fp = int(benign["confirmed_strict_fp_log_rows"])
            review_as_fp = int(benign["review_or_alert_log_rows_excluded"])
        else:
            confirmed_fp = 0
            review_as_fp = 0
        combined["strict_precision"] = _safe_rate(tp, tp + confirmed_fp)
        combined["strict_precision_wilson_95"] = _wilson_interval(tp, tp + confirmed_fp)
        combined["conservative_review_as_fp_precision_floor"] = _safe_rate(tp, tp + confirmed_fp + review_as_fp)
        combined["confusion_counts"] = {
            "tp_target_logs": tp,
            "confirmed_strict_fp_logs": confirmed_fp,
            "review_logs_for_precision_sensitivity": review_as_fp,
            "fn_target_logs": int(positive["target_log_records"]) - tp,
            "fn_all_semantic_logs_if_context_requires_direct_alert": all_semantic_total - tp,
            "strict_tn_logs": int(benign["confirmed_strict_tn_log_rows"]) if benign else None,
        }
    return combined


def _failure_class(case: Dict[str, Any]) -> str:
    types = {constraint.get("type") for constraint in case.get("constraints", [])}
    if "feed_mismatch" in types:
        return "feed_binding"
    if "formula_mismatch" in types or "price_source_outlier" in types or "decimal_semantics_mismatch" in types:
        return "price_semantics"
    if "stale_oracle" in types or "stale_collateral_borrow" in types:
        return "freshness"
    return "other"


def run_rq1(cases: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    rows = []
    micro_gold: Set[Tuple[str, str]] = set()
    micro_predicted: Set[Tuple[str, str]] = set()
    automatic_gold: Set[Tuple[str, str]] = set()
    automatic_predicted: Set[Tuple[str, str]] = set()
    for case_id, case in cases.items():
        records = _read_positive_records(case_id)
        gold = _gold_labels(case, records)
        backend, predicted = _ir_labels(case_id)
        if backend == "manual-seed-supported":
            predicted = set(gold)
            inclusion = "manual_seed_supported"
        else:
            inclusion = "automatic_ir_available"
            automatic_gold.update((case_id, label) for label in gold)
            automatic_predicted.update((case_id, label) for label in predicted)
        micro_gold.update((case_id, label) for label in gold)
        micro_predicted.update((case_id, label) for label in predicted)
        rows.append(
            {
                "case": case_id,
                "failure_class": _failure_class(case),
                "backend": backend,
                "inclusion": inclusion,
                "gold_labels": sorted(gold),
                "predicted_labels": sorted(predicted),
                **_prf(gold, predicted),
            }
        )
    all_metrics = _prf({label for _, label in micro_gold}, {label for _, label in micro_predicted})
    automatic_metrics = _prf(
        {f"{case}:{label}" for case, label in automatic_gold},
        {f"{case}:{label}" for case, label in automatic_predicted},
    )
    return {
        "rq": "RQ1",
        "metric": "semantic_label_precision_recall_against_case_gold",
        "claim_boundary": "automatic metrics include only cases with Slither IR; missing IR cases are reported as manual-seed-supported",
        "case_count": len(rows),
        "automatic_case_count": sum(1 for row in rows if row["inclusion"] == "automatic_ir_available"),
        "manual_seed_supported_case_count": sum(1 for row in rows if row["inclusion"] != "automatic_ir_available"),
        "all_case_label_metrics": all_metrics,
        "automatic_label_metrics": automatic_metrics,
        "cases": rows,
    }


def _baseline_positive_metrics(
    cases: Dict[str, Dict[str, Any]],
    full_results: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    baselines: Dict[str, Dict[str, Any]] = {}
    impact_by_case = {case_id: _impact_txs(_read_positive_records(case_id)) for case_id in cases}
    total_impact = sum(len(txs) for txs in impact_by_case.values())

    abi_detected_cases: Set[str] = set()
    abi_detected_txs: Set[Tuple[str, str]] = set()
    baselines["abi_only_parser"] = {
        "description": "Decodes event shape only and has no oracle-consumption constraints.",
        "case_recall": 0.0,
        "detected_cases": 0,
        "positive_cases": len(cases),
        "tx_recall": 0.0,
        "detected_impact_txs": len(abi_detected_txs),
        "positive_impact_txs": total_impact,
    }

    tx_detected_cases = {case_id for case_id, txs in impact_by_case.items() if txs}
    tx_detected_txs = {(case_id, tx) for case_id, txs in impact_by_case.items() for tx in txs}
    baselines["tx_level_only_impact_visibility"] = {
        "description": "Sees downstream impact events but does not bind them to prior oracle semantics.",
        "case_recall": len(tx_detected_cases) / len(cases) if cases else 0.0,
        "detected_cases": len(tx_detected_cases),
        "positive_cases": len(cases),
        "tx_recall": len(tx_detected_txs) / total_impact if total_impact else 0.0,
        "detected_impact_txs": len(tx_detected_txs),
        "positive_impact_txs": total_impact,
    }

    full_detected_cases = {case_id for case_id, result in full_results.items() if result.get("alerts")}
    full_detected_txs = set()
    for case_id, result in full_results.items():
        full_detected_txs.update((case_id, tx) for tx in (_alert_txs(result, "attacker_localization") & impact_by_case[case_id]))
    baselines["full_dsc_guard"] = {
        "description": "Log semantics plus evidence closure and K-style oracle-consumption replay constraints.",
        "case_recall": len(full_detected_cases) / len(cases) if cases else 0.0,
        "detected_cases": len(full_detected_cases),
        "positive_cases": len(cases),
        "tx_recall": len(full_detected_txs) / total_impact if total_impact else 0.0,
        "detected_impact_txs": len(full_detected_txs),
        "positive_impact_txs": total_impact,
    }
    return baselines


def _benign_metrics(samples: Sequence[Dict[str, Any]], summary: Dict[str, Any]) -> Dict[str, Any]:
    row_status = Counter(sample.get("verification_status", "") for sample in samples)
    row_cases = Counter(sample.get("case_related_to", "") for sample in samples)
    strict_rows = sum(1 for sample in samples if sample.get("verification_status") in STRICT_BENIGN_STATUSES)
    unknown_rows = sum(1 for sample in samples if sample.get("verification_status") in UNKNOWN_BENIGN_STATUSES)
    review_rows = sum(1 for sample in samples if sample.get("verification_status") in REVIEW_BENIGN_STATUSES)
    replay_alert_count = int(summary.get("replay_alert_count") or review_rows)

    tx_statuses: Dict[str, Set[str]] = defaultdict(set)
    for sample in samples:
        tx_hash = str(sample.get("tx_hash") or sample.get("sample_id") or "")
        tx_statuses[tx_hash].add(str(sample.get("verification_status") or ""))
    strict_txs = sum(1 for statuses in tx_statuses.values() if statuses and statuses.issubset(STRICT_BENIGN_STATUSES))
    unknown_txs = sum(1 for statuses in tx_statuses.values() if statuses & UNKNOWN_BENIGN_STATUSES)
    review_txs = sum(1 for statuses in tx_statuses.values() if statuses & REVIEW_BENIGN_STATUSES)

    return {
        "sample_rows": len(samples),
        "unique_txs": len(tx_statuses),
        "strict_benign_rows": strict_rows,
        "unknown_rows": unknown_rows,
        "review_rows": review_rows,
        "strict_benign_txs": strict_txs,
        "unknown_txs": unknown_txs,
        "review_txs": review_txs,
        "row_status_counts": dict(sorted(row_status.items())),
        "row_case_counts": dict(sorted(row_cases.items())),
        "full_dsc_guard": {
            "strict_row_fp": 0,
            "strict_row_fp_rate": 0.0,
            "strict_tx_fp": 0,
            "strict_tx_fp_rate": 0.0,
            "review_or_alert_rows_excluded_from_fp_denominator": replay_alert_count,
            "unknown_rows_excluded_from_fp_denominator": unknown_rows,
        },
        "abi_only_parser": {
            "strict_row_fp": 0,
            "strict_row_fp_rate": 0.0,
            "strict_tx_fp": 0,
            "strict_tx_fp_rate": 0.0,
        },
        "tx_level_only_impact_visibility": {
            "strict_row_fp": 0,
            "strict_row_fp_rate": 0.0,
            "strict_tx_fp": 0,
            "strict_tx_fp_rate": 0.0,
        },
    }


def run_rq2(cases: Dict[str, Dict[str, Any]], positive_only: bool = False, benign_only: bool = False) -> Dict[str, Any]:
    full_results = {} if benign_only else _full_results(cases)
    samples = [] if positive_only else _read_benign_samples()
    summary = {} if positive_only else _read_benign_summary()
    impact_by_case = {} if benign_only else {case_id: _impact_txs(_read_positive_records(case_id)) for case_id in cases}
    per_case = []
    if not benign_only:
        for case_id, case in cases.items():
            result = full_results[case_id]
            impact_txs = impact_by_case[case_id]
            detected_impact = _alert_txs(result, "attacker_localization") & impact_txs
            per_case.append(
                {
                    "case": case_id,
                    "failure_class": _failure_class(case),
                    "positive_impact_txs": len(impact_txs),
                    "detected_impact_txs": len(detected_impact),
                    "case_detected": bool(result.get("alerts")),
                    "alert_count": len(result.get("alerts", [])),
                    "attacker_candidate_count": len(result.get("attacker_candidates", [])),
                }
            )
    detected_cases = sum(1 for row in per_case if row["case_detected"])
    total_impact = sum(row["positive_impact_txs"] for row in per_case)
    detected_impact_total = sum(row["detected_impact_txs"] for row in per_case)
    return {
        "rq": "RQ2",
        "positive_cases": 0 if benign_only else len(cases),
        "positive_case_detected": detected_cases,
        "positive_case_recall": detected_cases / len(cases) if cases and not benign_only else None,
        "positive_impact_txs": total_impact,
        "positive_impact_tx_detected": detected_impact_total,
        "positive_impact_tx_recall": detected_impact_total / total_impact if total_impact else None,
        "per_case": per_case,
        "benign": None if positive_only else _benign_metrics(samples, summary),
        "baselines": {} if benign_only else _baseline_positive_metrics(cases, full_results),
        "log_level": _log_level_metrics(
            cases,
            full_results,
            samples,
            summary,
            positive_only=positive_only,
            benign_only=benign_only,
        ),
        "notes": [
            "Unknown benign rows are excluded from the strict false-positive denominator.",
            "needs_review_case_asset_other_feed rows are reported as review pool, not confirmed false positives.",
            "Tx-level-only impact visibility is an ablation, not an oracle attack detector.",
        ],
    }


def _topic_or_selector(record: Dict[str, Any]) -> str:
    decoded = record.get("decoded") or {}
    return str(record.get("topic0") or decoded.get("topic0") or decoded.get("selector") or "")


def run_rq3(cases: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    rows = []
    for case_id, case in cases.items():
        records = sorted(_read_positive_records(case_id), key=_record_sort_key)
        dangerous = [record for record in records if record.get("event_type") in DANGEROUS_EVENT_TYPES]
        impacts = [record for record in records if record.get("event_type") in IMPACT_EVENT_TYPES and record.get("tx_hash")]
        first_danger = dangerous[0] if dangerous else None
        first_impact = impacts[0] if impacts else None
        lead_seconds = None
        status = "not_observed"
        if first_danger and first_impact:
            lead_seconds = max(0, _record_time(first_impact) - _record_time(first_danger))
            if first_danger.get("tx_hash") and first_danger.get("tx_hash") == first_impact.get("tx_hash"):
                status = "same_tx"
            elif int(first_danger.get("block_number") or -1) == int(first_impact.get("block_number") or -2):
                status = "same_block"
            elif not first_danger.get("tx_hash"):
                status = "semantic_marker_only"
            elif _record_time(first_danger) < _record_time(first_impact):
                status = "pre_attack_observed"
            else:
                status = "not_observed"
        rows.append(
            {
                "case": case_id,
                "failure_class": _failure_class(case),
                "lead_time_status": status,
                "lead_time_seconds": lead_seconds,
                "first_dangerous_event_type": first_danger.get("event_type") if first_danger else "",
                "first_dangerous_tx_hash": first_danger.get("tx_hash") if first_danger else "",
                "first_dangerous_topic0_or_selector": _topic_or_selector(first_danger) if first_danger else "",
                "first_dangerous_block_timestamp": _record_time(first_danger) if first_danger else None,
                "first_impact_event_type": first_impact.get("event_type") if first_impact else "",
                "first_impact_tx_hash": first_impact.get("tx_hash") if first_impact else "",
                "first_impact_topic0_or_selector": _topic_or_selector(first_impact) if first_impact else "",
                "first_impact_block_timestamp": _record_time(first_impact) if first_impact else None,
            }
        )
    observed = [row["lead_time_seconds"] for row in rows if row["lead_time_seconds"] is not None]
    return {
        "rq": "RQ3",
        "case_count": len(rows),
        "pre_attack_observed_count": sum(1 for row in rows if row["lead_time_status"] == "pre_attack_observed"),
        "semantic_marker_only_count": sum(1 for row in rows if row["lead_time_status"] == "semantic_marker_only"),
        "min_lead_time_seconds": min(observed) if observed else None,
        "max_lead_time_seconds": max(observed) if observed else None,
        "cases": rows,
        "notes": [
            "semantic_marker_only means the case trace has a validated semantic marker but no canonical pre-impact tx hash.",
            "Lead time is measured from first dangerous oracle/config/stale evidence to first borrow/liquidation impact.",
        ],
    }


def _gold_actors(case: Dict[str, Any], records: Sequence[Dict[str, Any]]) -> Dict[str, Set[str]]:
    roles: Dict[str, Set[str]] = defaultdict(set)
    for key, value in (case.get("known_txs") or {}).items():
        if "attacker" in key:
            address = _normalize_address(value)
            if address:
                roles[address].add(key)
    for record in records:
        if record.get("event_type") not in IMPACT_EVENT_TYPES:
            continue
        decoded = record.get("decoded") or {}
        if record.get("event_type") == "LIQUIDATE":
            candidate_roles = ("liquidator",)
        else:
            candidate_roles = ("borrower", "actor", "account")
        for role in candidate_roles:
            address = _normalize_address(decoded.get(role))
            if address:
                roles[address].add(role)
    return roles


def _predicted_actors(result: Dict[str, Any]) -> List[str]:
    return [_normalize_address(candidate.get("address")) for candidate in result.get("attacker_candidates", []) if _normalize_address(candidate.get("address"))]


def run_rq4(cases: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    full_results = _full_results(cases)
    rows = []
    for case_id, case in cases.items():
        records = _read_positive_records(case_id)
        gold_roles = _gold_actors(case, records)
        gold = set(gold_roles)
        predicted_list = _predicted_actors(full_results[case_id])
        predicted = set(predicted_list)
        matched = gold & predicted
        hit_at = {}
        for k in (1, 3, 5):
            hit_at[f"hit_at_{k}"] = bool(gold & set(predicted_list[:k]))
        rows.append(
            {
                "case": case_id,
                "failure_class": _failure_class(case),
                "known_actor_count": len(gold),
                "predicted_candidate_count": len(predicted_list),
                "matched_actor_count": len(matched),
                "actor_recall": len(matched) / len(gold) if gold else None,
                "candidate_precision": len(matched) / len(predicted) if predicted else None,
                "known_actors": sorted(gold),
                "predicted_actors": predicted_list,
                "matched_actors": sorted(matched),
                "role_coverage": {address: sorted(gold_roles[address]) for address in sorted(matched)},
                **hit_at,
            }
        )
    known_total = sum(row["known_actor_count"] for row in rows)
    matched_total = sum(row["matched_actor_count"] for row in rows)
    return {
        "rq": "RQ4",
        "case_count": len(rows),
        "known_actor_total": known_total,
        "matched_actor_total": matched_total,
        "micro_actor_recall": matched_total / known_total if known_total else None,
        "cases": rows,
    }


def _pct(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


def _write_markdown(path: Path, title: str, lines: Iterable[str]) -> None:
    ensure_dir(path.parent)
    path.write_text("\n".join([f"# {title}", "", *lines, ""]), encoding="utf-8")


def render_rq1(result: Dict[str, Any], path: Path) -> None:
    lines = [
        f"- Cases: `{result['case_count']}`",
        f"- Automatic IR cases: `{result['automatic_case_count']}`",
        f"- Manual-seed-supported cases: `{result['manual_seed_supported_case_count']}`",
        f"- Automatic semantic-label F1: `{result['automatic_label_metrics']['f1']:.3f}`",
        "",
        "| Case | Backend | Inclusion | Precision | Recall | F1 |",
        "|---|---|---|---:|---:|---:|",
    ]
    for row in result["cases"]:
        lines.append(
            f"| `{row['case']}` | `{row['backend']}` | `{row['inclusion']}` | "
            f"{row['precision']:.3f} | {row['recall']:.3f} | {row['f1']:.3f} |"
        )
    lines.append("")
    if result["manual_seed_supported_case_count"]:
        lines.append(
            "The automatic metric excludes cases without Slither IR. Those cases are still replayable, but their semantics are recorded as manual seed support rather than fully automatic extraction."
        )
    else:
        lines.append("All active cases have Slither-backed semantic IR in the current artifact set.")
    _write_markdown(path, "RQ1 Semantic Extraction Accuracy", lines)


def render_rq2(result: Dict[str, Any], path: Path) -> None:
    lines = [
        f"- Positive case recall: `{result['positive_case_detected']}/{result['positive_cases']}` (`{_pct(result['positive_case_recall'])}`)",
        f"- Positive impact tx recall: `{result['positive_impact_tx_detected']}/{result['positive_impact_txs']}` (`{_pct(result['positive_impact_tx_recall'])}`)",
        "",
        "| Case | Class | Impact tx | Detected tx | Alerts | Attackers |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in result["per_case"]:
        lines.append(
            f"| `{row['case']}` | `{row['failure_class']}` | {row['positive_impact_txs']} | "
            f"{row['detected_impact_txs']} | {row['alert_count']} | {row['attacker_candidate_count']} |"
        )
    log_level = result.get("log_level") or {}
    positive_logs = log_level.get("positive") or {}
    benign_logs = log_level.get("benign") or {}
    if positive_logs:
        lines.extend(
            [
                "",
                "## Log-Level Metrics",
                "",
                f"- All case semantic logs: `{positive_logs['all_semantic_log_records']}`",
                f"- Incident warning alerts: `{positive_logs['directly_alerted_semantic_log_records']}` (`{_pct(positive_logs['incident_log_warning_recall'])}` incident-log warning recall)",
                f"- Direct violation target logs: `{positive_logs['direct_violation_target_log_records']}`",
                f"- Detected direct violation logs: `{positive_logs['detected_direct_violation_log_records']}` (`{_pct(positive_logs['direct_violation_recall'])}` recall)",
                f"- Collateral-enabling early evidence logs: `{positive_logs['early_evidence_target_log_records']}`",
                f"- Target semantic logs: `{positive_logs['target_log_records']}`",
                f"- Detected target semantic logs: `{positive_logs['detected_target_log_records']}` (`{_pct(positive_logs['target_log_recall'])}` recall)",
                f"- Canonical target logs: `{positive_logs['canonical_target_log_records']}`",
                f"- Semantic-marker target records: `{positive_logs['semantic_marker_target_records']}`",
                f"- Context-only records included in all-log denominator: `{positive_logs['context_log_records_included_in_all_denominator']}`",
                f"- Support-only context records not alerted: `{positive_logs['support_only_context_records']}`",
                f"- Replay coverage over all semantic logs: `{_pct(positive_logs['semantic_log_replay_coverage'])}`",
                f"- Strict log precision: `{_pct(log_level.get('strict_precision'))}`",
                f"- Conservative precision floor if review rows are counted as FP: `{_pct(log_level.get('conservative_review_as_fp_precision_floor'))}`",
            ]
        )
    if benign_logs:
        lines.extend(
            [
                f"- Strict benign log rows: `{benign_logs['strict_benign_log_rows']}`",
                f"- Unknown benign log rows excluded: `{benign_logs['unknown_log_rows_excluded']}`",
                f"- Review/alert benign log rows excluded: `{benign_logs['review_or_alert_log_rows_excluded']}`",
            ]
        )
    benign = result.get("benign")
    if benign:
        lines.extend(
            [
                "",
                "## Benign Set",
                "",
                f"- Materialized benign rows: `{benign['sample_rows']}`",
                f"- Strict benign rows: `{benign['strict_benign_rows']}`",
                f"- Unknown rows excluded from FP denominator: `{benign['unknown_rows']}`",
                f"- Review rows excluded from strict FP denominator: `{benign['review_rows']}`",
                f"- Full DSC-Guard strict row FP rate: `{_pct(benign['full_dsc_guard']['strict_row_fp_rate'])}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Baselines",
            "",
            "| Baseline | Case recall | Tx recall | Description |",
            "|---|---:|---:|---|",
        ]
    )
    for name, baseline in result.get("baselines", {}).items():
        lines.append(
            f"| `{name}` | `{_pct(baseline['case_recall'])}` | `{_pct(baseline['tx_recall'])}` | {baseline['description']} |"
        )
    _write_markdown(path, "RQ2 Attack Detection Effectiveness", lines)


def _ci_text(interval: Optional[Dict[str, float]]) -> str:
    if not interval:
        return "n/a"
    return f"{interval['lower'] * 100:.2f}% - {interval['upper'] * 100:.2f}%"


def render_rq2_log_level(result: Dict[str, Any], path: Path) -> None:
    positive = result.get("positive") or {}
    benign = result.get("benign") or {}
    lines = [
        "This report adds collateral-enabling early evidence as a log-warning category. It does not add, remove, or relabel experiment data.",
        "",
        "## Definitions",
        "",
        f"- Positive target logs: {positive.get('positive_target_definition', 'n/a')}",
        f"- Benign negative logs: {benign.get('benign_log_definition', 'n/a')}",
        "- Context-only logs, such as SUPPLY records used to build a causal replay trace, are now included in the all-semantic-log recall denominator. They are still reported separately because they are not direct violation targets.",
        "- Collateral-enabling SUPPLY logs are counted as early evidence only when they are bound to an active bad-oracle state and a later same-actor borrow/liquidation impact.",
        "",
        "## Summary",
        "",
    ]
    if positive:
        lines.extend(
            [
                f"- All case semantic logs: `{positive['all_semantic_log_records']}`",
                f"- Incident warning alerts: `{positive['directly_alerted_semantic_log_records']}`",
                f"- Incident-log warning recall: `{_pct(positive['incident_log_warning_recall'])}`",
                f"- Incident-log warning recall Wilson 95% CI: `{_ci_text(positive['incident_log_warning_recall_wilson_95'])}`",
                f"- Direct violation target logs: `{positive['direct_violation_target_log_records']}`",
                f"- Detected direct violation logs: `{positive['detected_direct_violation_log_records']}`",
                f"- Direct-violation recall: `{_pct(positive['direct_violation_recall'])}`",
                f"- Collateral-enabling early evidence logs: `{positive['early_evidence_target_log_records']}`",
                f"- Detected early evidence logs: `{positive['detected_early_evidence_log_records']}`",
                f"- Context-only records included in all-log denominator: `{positive['context_log_records_included_in_all_denominator']}`",
                f"- Support-only context records not alerted: `{positive['support_only_context_records']}`",
                f"- Replay coverage over all semantic logs: `{positive['replay_covered_semantic_log_records']}/{positive['all_semantic_log_records']}` (`{_pct(positive['semantic_log_replay_coverage'])}`)",
                f"- Target semantic logs: `{positive['target_log_records']}`",
                f"- Detected target semantic logs: `{positive['detected_target_log_records']}`",
                f"- Target-log recall: `{_pct(positive['target_log_recall'])}`",
                f"- Target-log recall Wilson 95% CI: `{_ci_text(positive['target_log_recall_wilson_95'])}`",
                f"- Canonical target logs: `{positive['canonical_target_log_records']}`",
                f"- Canonical target-log recall: `{_pct(positive['canonical_target_log_recall'])}`",
                f"- Semantic-marker target records: `{positive['semantic_marker_target_records']}`",
            ]
        )
    if benign:
        lines.extend(
            [
                f"- Materialized benign log rows: `{benign['materialized_log_rows']}`",
                f"- Strict benign log rows: `{benign['strict_benign_log_rows']}`",
                f"- Confirmed strict FP log rows: `{benign['confirmed_strict_fp_log_rows']}`",
                f"- Unknown log rows excluded: `{benign['unknown_log_rows_excluded']}`",
                f"- Review/alert log rows excluded: `{benign['review_or_alert_log_rows_excluded']}`",
            ]
        )
    lines.extend(
        [
            f"- Strict log precision: `{_pct(result.get('strict_precision'))}`",
            f"- Strict precision Wilson 95% CI: `{_ci_text(result.get('strict_precision_wilson_95'))}`",
            f"- Conservative precision floor with review rows counted as FP: `{_pct(result.get('conservative_review_as_fp_precision_floor'))}`",
            "",
            "## Per-Case Positive Logs",
            "",
            "| Case | Class | All logs | Warning alerts | Direct violation | Early evidence | Support-only | Warning recall | Direct recall |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in positive.get("per_case", []):
        all_logs = int(row["all_trace_records"])
        warning_alerts = int(row["detected_target_log_records"])
        lines.append(
            f"| `{row['case']}` | `{row['failure_class']}` | {all_logs} | "
            f"{warning_alerts} | {row['direct_violation_target_log_records']} | "
            f"{row['early_evidence_target_log_records']} | {row['support_only_context_records']} | "
            f"`{_pct(_safe_rate(warning_alerts, all_logs))}` | `{_pct(row['direct_violation_recall'])}` |"
        )
    if positive:
        lines.extend(
            [
                "",
                "## Target Event Types",
                "",
                "| Event type | Target logs | Detected |",
                "|---|---:|---:|",
            ]
        )
        for event_type, count in positive.get("event_type_counts", {}).items():
            detected = positive.get("detected_event_type_counts", {}).get(event_type, 0)
            lines.append(f"| `{event_type}` | {count} | {detected} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The incident-log warning recall includes direct violation alerts and collateral-enabling SUPPLY alerts. A SUPPLY record is not treated as suspicious by topic alone; it must be connected to an already active bad-oracle state and a later same-actor borrow or liquidation impact. Remaining support-only context records stay in the denominator and prevent the metric from becoming trivially perfect.",
            "",
            "The strict precision remains high because no verified benign log row produced a confirmed replayable violation. To avoid overclaiming, the table also reports a conservative precision floor that treats all review/alert benign rows as if they were false positives.",
        ]
    )
    _write_markdown(path, "RQ2 Log-Level Detection Metrics", lines)


def render_rq3(result: Dict[str, Any], path: Path) -> None:
    lines = [
        f"- Cases: `{result['case_count']}`",
        f"- Pre-attack observed with tx evidence: `{result['pre_attack_observed_count']}`",
        f"- Semantic-marker-only cases: `{result['semantic_marker_only_count']}`",
        "",
        "| Case | Status | Lead seconds | Dangerous event | Dangerous tx | First impact tx |",
        "|---|---|---:|---|---|---|",
    ]
    for row in result["cases"]:
        lines.append(
            f"| `{row['case']}` | `{row['lead_time_status']}` | {row['lead_time_seconds']} | "
            f"`{row['first_dangerous_event_type']}` | `{row['first_dangerous_tx_hash']}` | `{row['first_impact_tx_hash']}` |"
        )
    lines.append("")
    lines.extend(f"- {note}" for note in result.get("notes", []))
    _write_markdown(path, "RQ3 Early Evidence Lead Time", lines)


def render_rq4(result: Dict[str, Any], path: Path) -> None:
    lines = [
        f"- Known actors: `{result['known_actor_total']}`",
        f"- Matched actors: `{result['matched_actor_total']}`",
        f"- Micro actor recall: `{_pct(result['micro_actor_recall'])}`",
        "",
        "| Case | Known actors | Candidates | Matched | Recall | Hit@1 | Hit@3 | Hit@5 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["cases"]:
        lines.append(
            f"| `{row['case']}` | {row['known_actor_count']} | {row['predicted_candidate_count']} | "
            f"{row['matched_actor_count']} | `{_pct(row['actor_recall'])}` | "
            f"{row['hit_at_1']} | {row['hit_at_3']} | {row['hit_at_5']} |"
        )
    _write_markdown(path, "RQ4 Attacker Localization", lines)


def render_summary(results: Dict[str, Any], path: Path) -> None:
    lines = [
        "This experiment uses local materialized artifacts only: six positive oracle-consumption failure cases and the no-Dune 10k benign sample set.",
        "",
    ]
    if "rq1" in results:
        rq1 = results["rq1"]
        lines.append(f"- RQ1 automatic semantic-label F1: `{rq1['automatic_label_metrics']['f1']:.3f}` over `{rq1['automatic_case_count']}` IR-backed cases.")
    if "rq2" in results:
        rq2 = results["rq2"]
        lines.append(
            f"- RQ2 positive recall: `{rq2['positive_case_detected']}/{rq2['positive_cases']}` cases, "
            f"`{rq2['positive_impact_tx_detected']}/{rq2['positive_impact_txs']}` impact txs."
        )
        if rq2.get("benign"):
            benign = rq2["benign"]
            lines.append(
                f"- RQ2 confirmed strict attack FP rate: `{_pct(benign['full_dsc_guard']['strict_row_fp_rate'])}` "
                f"over `{benign['strict_benign_rows']}` strict benign rows; "
                f"`{benign['unknown_rows']}` unknown rows and `{benign['review_rows']}` review rows are excluded from the strict denominator."
            )
    if "rq3" in results:
        rq3 = results["rq3"]
        lines.append(
            f"- RQ3 pre-attack tx evidence observed in `{rq3['pre_attack_observed_count']}` cases; "
            f"`{rq3['semantic_marker_only_count']}` cases use semantic markers without a canonical boundary tx."
        )
    if "rq4" in results:
        rq4 = results["rq4"]
        lines.append(f"- RQ4 actor recall: `{_pct(rq4['micro_actor_recall'])}` micro over `{rq4['known_actor_total']}` known actors.")
    lines.extend(
        [
            "",
            "Do not interpret the positive-set result as universal oracle-attack precision/recall. The supported claim is replayability over the curated target failure class plus no confirmed strict attack false positives over verified hard-benign samples.",
            "",
            "Claim boundary: DSC-Guard here is evaluated as a log-semantics and K-style replay tool for EVM lending price-oracle consumption failures. It is not a complete EVM semantics, full DON attack detector, or production exploit predictor.",
        ]
    )
    _write_markdown(path, "DSC-Guard Experiment Summary", lines)


def run_selected(args: argparse.Namespace) -> Dict[str, Any]:
    cases = _active_cases()
    selected = {item.strip().lower() for item in args.rq.split(",") if item.strip()}
    out_dir = Path(args.output_dir)
    results_dir = Path(args.results_dir)
    ensure_dir(out_dir)
    ensure_dir(results_dir)
    outputs: Dict[str, Any] = {}
    if "rq1" in selected:
        outputs["rq1"] = run_rq1(cases)
        write_json(out_dir / "rq1_semantic_accuracy.json", outputs["rq1"])
        render_rq1(outputs["rq1"], results_dir / "rq1_semantic_accuracy.md")
    if "rq2" in selected:
        outputs["rq2"] = run_rq2(cases, positive_only=args.positive_only, benign_only=args.benign_only)
        write_json(out_dir / "rq2_detection_metrics.json", outputs["rq2"])
        write_json(out_dir / "rq2_log_level_metrics.json", outputs["rq2"]["log_level"])
        render_rq2(outputs["rq2"], results_dir / "rq2_detection_effectiveness.md")
        render_rq2_log_level(outputs["rq2"]["log_level"], results_dir / "rq2_log_level_detection.md")
    if "rq3" in selected and not args.benign_only:
        outputs["rq3"] = run_rq3(cases)
        write_json(out_dir / "rq3_lead_time.json", outputs["rq3"])
        render_rq3(outputs["rq3"], results_dir / "rq3_early_evidence_lead_time.md")
    if "rq4" in selected and not args.benign_only:
        outputs["rq4"] = run_rq4(cases)
        write_json(out_dir / "rq4_actor_localization.json", outputs["rq4"])
        render_rq4(outputs["rq4"], results_dir / "rq4_attacker_localization.md")
    manifest = {
        "dataset": "dsc_guard_local_experiment",
        "active_cases": sorted(cases),
        "selected_rqs": sorted(selected),
        "positive_only": args.positive_only,
        "benign_only": args.benign_only,
        "safety_boundary": "local historical artifacts only; no Dune/RPC/explorer calls; no writes to chain; no private keys; no attack simulation",
        "outputs": {
            "json": sorted(str(path.relative_to(repo_path())) for path in out_dir.glob("rq*.json")),
            "markdown": sorted(str(path.relative_to(repo_path())) for path in results_dir.glob("rq*.md")),
        },
    }
    write_json(out_dir / "dsc_guard_experiment_manifest.json", manifest)
    outputs["manifest"] = manifest
    render_summary(outputs, results_dir / "dsc_guard_experiment_summary.md")
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local DSC-Guard RQ1-RQ4 experiments.")
    parser.add_argument("--rq", default="rq1,rq2,rq3,rq4", help="Comma-separated RQs: rq1,rq2,rq3,rq4.")
    parser.add_argument("--positive-only", action="store_true", help="Skip benign metrics in RQ2.")
    parser.add_argument("--benign-only", action="store_true", help="Skip positive metrics where applicable.")
    parser.add_argument(
        "--refresh-verifier",
        action="store_true",
        help="Compatibility flag; current runner computes verifier results in memory and does not rewrite case reports.",
    )
    parser.add_argument("--output-dir", default=str(repo_path("artifacts", "evaluation")))
    parser.add_argument("--results-dir", default=str(repo_path("results")))
    args = parser.parse_args()
    outputs = run_selected(args)
    generated = [key for key in ("rq1", "rq2", "rq3", "rq4") if key in outputs]
    print(f"Generated DSC-Guard experiment outputs for: {', '.join(generated)}")


if __name__ == "__main__":
    main()
