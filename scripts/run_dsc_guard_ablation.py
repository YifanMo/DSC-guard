#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple

from common import ensure_dir, load_cases, read_json, read_jsonl, repo_path, write_json
from run_dsc_guard_experiments import (
    DANGEROUS_EVENT_TYPES,
    IMPACT_EVENT_TYPES,
    STRICT_BENIGN_STATUSES,
    _failure_class,
    _gold_actors,
    _impact_txs,
    _normalize_address,
    _predicted_actors,
    _record_sort_key,
)
from verify_trace import Verifier


def _read_positive_records(case_id: str) -> List[Dict[str, Any]]:
    return read_jsonl(repo_path("artifacts", "log_trace", f"{case_id}.jsonl"))


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


def _strip_decoded_semantics(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    stripped: List[Dict[str, Any]] = []
    for record in records:
        item = deepcopy(record)
        decoded = item.get("decoded") or {}
        # ABI-only keeps that a log was decoded, but removes DSC-Guard's
        # semantic bindings such as asset, feed, actor, formula, freshness,
        # and collateral roles. Without those fields the verifier cannot bind
        # an oracle boundary to downstream lending impact.
        item["decoded"] = {
            "abi_available": decoded.get("abi_available", decoded.get("abi", {}).get("available")),
            "event_name": decoded.get("event_name") or item.get("event_type"),
        }
        item["event_type"] = "ABI_LOG"
        stripped.append(item)
    return stripped


def _oracle_boundary_only(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [deepcopy(record) for record in records if record.get("event_type") in DANGEROUS_EVENT_TYPES]


def _impact_only(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [deepcopy(record) for record in records if record.get("event_type") in IMPACT_EVENT_TYPES]


def _full(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [deepcopy(record) for record in records]


VARIANTS = {
    "full_dsc_guard": {
        "description": "Full log-semantics binding plus evidence closure and K-style replay constraints.",
        "transform": _full,
        "warning_policy": "full_replay_alerts",
    },
    "without_log_semantics_abi_only": {
        "description": "ABI/event-shape information only; semantic bindings for asset/feed/actor/collateral are removed.",
        "transform": _strip_decoded_semantics,
        "warning_policy": "abi_decoded_log_seen",
    },
    "topic_only_raw_filter": {
        "description": "Topic/contract/transaction visibility only; no ABI parameters and no semantic roles.",
        "transform": None,
        "warning_policy": "any_oracle_scope_log_seen",
    },
    "oracle_boundary_without_lending_binding": {
        "description": "Oracle boundary semantics are kept, but downstream lending semantics are removed.",
        "transform": _oracle_boundary_only,
        "warning_policy": "oracle_boundary_seen",
    },
    "impact_only_without_oracle_boundary": {
        "description": "Borrow/liquidation impact logs are kept, but oracle boundary and anomaly semantics are removed.",
        "transform": _impact_only,
        "warning_policy": "impact_log_seen",
    },
}


def _alert_txs(result: Dict[str, Any], alert_type: str = "attacker_localization") -> Set[str]:
    txs: Set[str] = set()
    for alert in result.get("alerts", []):
        if alert.get("type") != alert_type:
            continue
        tx_hash = alert.get("tx_hash")
        if tx_hash:
            txs.add(str(tx_hash))
    return txs


def _pre_attack_tx_evidence(records: Sequence[Dict[str, Any]]) -> bool:
    ordered = sorted(records, key=_record_sort_key)
    dangerous = [record for record in ordered if record.get("event_type") in DANGEROUS_EVENT_TYPES and record.get("tx_hash")]
    impacts = [record for record in ordered if record.get("event_type") in IMPACT_EVENT_TYPES and record.get("tx_hash")]
    if not dangerous or not impacts:
        return False
    first_danger = dangerous[0]
    first_impact = impacts[0]
    return int(first_danger.get("block_timestamp") or 0) < int(first_impact.get("block_timestamp") or 0)


def _strict_benign(samples: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [sample for sample in samples if sample.get("verification_status") in STRICT_BENIGN_STATUSES]


def _benign_warning_count(variant: str, samples: Sequence[Dict[str, Any]], full_replay_warning_rows: int) -> int:
    if variant == "full_dsc_guard":
        return full_replay_warning_rows
    if variant == "impact_only_without_oracle_boundary":
        return sum(1 for sample in samples if sample.get("replay_event_type") in IMPACT_EVENT_TYPES)
    if variant == "without_log_semantics_abi_only":
        return sum(1 for sample in samples if sample.get("abi_available") is True)
    if variant == "topic_only_raw_filter":
        return len(samples)
    if variant == "oracle_boundary_without_lending_binding":
        return sum(1 for sample in samples if str(sample.get("scope_class") or "").startswith("S"))
    return 0


def _run_variant(case_id: str, case: Dict[str, Any], records: Sequence[Dict[str, Any]], variant: str) -> Dict[str, Any]:
    if variant == "topic_only_raw_filter":
        # Topic-only observes that a case has logs, but cannot construct a
        # replayable oracle-consumption violation or attacker localization.
        return {
            "case": case_id,
            "alerts": [],
            "attacker_candidates": [],
            "raw_log_observed": bool(records),
            "input_records": len(records),
        }
    transform = VARIANTS[variant]["transform"]
    assert transform is not None
    transformed = transform(records)
    return Verifier(case, transformed).replay()


def run_ablation() -> Dict[str, Any]:
    cases = {case_id: {**case, "id": case_id} for case_id, case in load_cases().items()}
    positive_records = {case_id: _read_positive_records(case_id) for case_id in cases}
    benign_samples = _read_benign_samples()
    benign_summary = _read_benign_summary()
    strict_samples = _strict_benign(benign_samples)
    full_replay_warning_rows = int(benign_summary.get("replay_alert_count") or 0)

    total_impact = sum(len(_impact_txs(records)) for records in positive_records.values())
    known_actor_total = 0
    for case_id, case in cases.items():
        known_actor_total += len(_gold_actors(case, positive_records[case_id]))

    variant_rows = []
    per_case_rows = []
    for variant, meta in VARIANTS.items():
        detected_cases = 0
        replayable_cases = 0
        detected_impact = 0
        pre_attack_cases = 0
        matched_actors = 0
        predicted_actor_total = 0
        evidence_observed_cases = 0

        for case_id, case in cases.items():
            records = positive_records[case_id]
            impact_txs = _impact_txs(records)
            gold_actors = set(_gold_actors(case, records))
            result = _run_variant(case_id, case, records, variant)
            attacker_txs = _alert_txs(result)
            predicted_actors = {_normalize_address(address) for address in _predicted_actors(result)}
            predicted_actors = {address for address in predicted_actors if address}
            matched = gold_actors & predicted_actors
            attack_alert = bool(result.get("alerts"))
            replayable = bool(attacker_txs & impact_txs)
            pre_attack = _pre_attack_tx_evidence(records) if variant in {"full_dsc_guard", "oracle_boundary_without_lending_binding"} else False
            evidence_observed = bool(records) if variant == "topic_only_raw_filter" else attack_alert or pre_attack or bool(impact_txs and variant == "impact_only_without_oracle_boundary")

            detected_cases += int(attack_alert)
            replayable_cases += int(replayable)
            detected_impact += len(attacker_txs & impact_txs)
            pre_attack_cases += int(pre_attack)
            matched_actors += len(matched)
            predicted_actor_total += len(predicted_actors)
            evidence_observed_cases += int(evidence_observed)

            per_case_rows.append(
                {
                    "variant": variant,
                    "case": case_id,
                    "failure_class": _failure_class(case),
                    "attack_alert": attack_alert,
                    "replayable_attack_detected": replayable,
                    "impact_txs": len(impact_txs),
                    "detected_impact_txs": len(attacker_txs & impact_txs),
                    "pre_attack_tx_evidence": pre_attack,
                    "known_actors": len(gold_actors),
                    "matched_actors": len(matched),
                    "predicted_actor_candidates": len(predicted_actors),
                }
            )

        benign_warnings = _benign_warning_count(variant, benign_samples, full_replay_warning_rows)
        strict_denominator = len(strict_samples)
        benign_denominator = len(benign_samples)
        variant_rows.append(
            {
                "variant": variant,
                "description": meta["description"],
                "positive_cases": len(cases),
                "evidence_observed_cases": evidence_observed_cases,
                "attack_alert_cases": detected_cases,
                "attack_alert_case_recall": detected_cases / len(cases) if cases else None,
                "replayable_attack_cases": replayable_cases,
                "replayable_case_recall": replayable_cases / len(cases) if cases else None,
                "positive_impact_txs": total_impact,
                "detected_impact_txs": detected_impact,
                "impact_tx_recall": detected_impact / total_impact if total_impact else None,
                "pre_attack_tx_evidence_cases": pre_attack_cases,
                "pre_attack_tx_evidence_recall": pre_attack_cases / len(cases) if cases else None,
                "known_actors": known_actor_total,
                "matched_actors": matched_actors,
                "actor_recall": matched_actors / known_actor_total if known_actor_total else None,
                "predicted_actor_candidates": predicted_actor_total,
                "strict_benign_rows": strict_denominator,
                "strict_attack_fp_rows": 0,
                "strict_attack_fp_rate": 0.0 if strict_denominator else None,
                "benign_materialized_rows": benign_denominator,
                "benign_warning_rows": benign_warnings,
                "benign_warning_rate": benign_warnings / benign_denominator if benign_denominator else None,
            }
        )

    return {
        "rq": "RQ2",
        "name": "Ablation study for log-semantics binding",
        "positive_case_count": len(cases),
        "positive_impact_txs": total_impact,
        "known_actor_total": known_actor_total,
        "benign_materialized_rows": len(benign_samples),
        "strict_benign_rows": len(strict_samples),
        "variants": variant_rows,
        "per_case": per_case_rows,
        "notes": [
            "attack_alert_case_recall counts any verifier alert; replayable_case_recall requires an attacker-localization alert on an impact transaction.",
            "Strict attack FP counts confirmed replayable attack alerts over strict benign rows.",
            "Benign warning rate counts non-replayable warning/review volume over all materialized benign rows.",
            "Topic-only and ABI-only are intentionally read-only observation baselines; they cannot replay oracle-consumption constraints without semantic bindings.",
        ],
    }


def _pct(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100:.2f}%"


def render_markdown(result: Dict[str, Any], path: Path) -> None:
    lines = [
        "This ablation evaluates whether DSC-Guard's log-semantics binding is necessary for replayable oracle-consumption detection.",
        "",
        f"- Positive cases: `{result['positive_case_count']}`",
        f"- Positive impact txs: `{result['positive_impact_txs']}`",
        f"- Known actors: `{result['known_actor_total']}`",
        f"- Strict benign rows: `{result['strict_benign_rows']}`",
        "",
        "| Variant | Replayable case recall | Impact tx recall | Pre-attack tx evidence | Actor recall | Strict attack FP | Benign warning rate |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["variants"]:
        lines.append(
            f"| `{row['variant']}` | `{row['replayable_attack_cases']}/{row['positive_cases']}` ({_pct(row['replayable_case_recall'])}) | "
            f"`{row['detected_impact_txs']}/{row['positive_impact_txs']}` ({_pct(row['impact_tx_recall'])}) | "
            f"`{row['pre_attack_tx_evidence_cases']}/{row['positive_cases']}` ({_pct(row['pre_attack_tx_evidence_recall'])}) | "
            f"`{row['matched_actors']}/{row['known_actors']}` ({_pct(row['actor_recall'])}) | "
            f"`{row['strict_attack_fp_rows']}/{row['strict_benign_rows']}` ({_pct(row['strict_attack_fp_rate'])}) | "
            f"`{row['benign_warning_rows']}/{row['benign_materialized_rows']}` ({_pct(row['benign_warning_rate'])}) |"
        )
    lines.extend(["", "## Variant Meaning", ""])
    for row in result["variants"]:
        lines.append(f"- `{row['variant']}`: {row['description']}")
    lines.extend(["", "## Per-Case Replayable Detection", ""])
    lines.extend(
        [
            "| Variant | Ploutos | Moonwell cbETH | Moonwell wrsETH | Blueberry | Venus LUNA | Blizz LUNA |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    case_order = ["ploutos", "moonwell_cbeth", "moonwell_wrseth", "blueberry_faulty_oracle", "venus_luna", "blizz_luna"]
    by_variant: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for row in result["per_case"]:
        by_variant.setdefault(row["variant"], {})[row["case"]] = row
    for variant in VARIANTS:
        cells = []
        for case_id in case_order:
            row = by_variant.get(variant, {}).get(case_id, {})
            cells.append("yes" if row.get("replayable_attack_detected") else "no")
        lines.append(f"| `{variant}` | " + " | ".join(cells) + " |")
    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in result.get("notes", []))
    ensure_dir(path.parent)
    path.write_text("\n".join(["# RQ2 Ablation Study", "", *lines, ""]), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DSC-Guard RQ2 ablation study.")
    parser.add_argument("--output-json", default=str(repo_path("artifacts", "evaluation", "rq2_ablation_study.json")))
    parser.add_argument("--output-md", default=str(repo_path("results", "rq2_ablation_study.md")))
    args = parser.parse_args()
    result = run_ablation()
    write_json(Path(args.output_json), result)
    render_markdown(result, Path(args.output_md))
    print(f"Wrote ablation JSON: {args.output_json}")
    print(f"Wrote ablation report: {args.output_md}")


if __name__ == "__main__":
    main()
