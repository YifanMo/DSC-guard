#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from common import ensure_dir, load_cases, repo_path, write_json


CASE_ORDER = ["ploutos", "moonwell_cbeth", "moonwell_wrseth", "blueberry_faulty_oracle", "venus_luna", "blizz_luna"]
TRIGGER_ALERT_TYPES = {"feed_mismatch", "formula_mismatch", "stale_oracle", "price_source_outlier", "decimal_semantics_mismatch"}


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _audit_by_case() -> Dict[str, Dict[str, Any]]:
    audit = _load_json(repo_path("artifacts", "dataset_audit.json"))
    return {item["case"]: item for item in audit.get("cases", [])}


def _manifest_by_case() -> Dict[str, Dict[str, Any]]:
    manifest = _load_json(repo_path("artifacts", "dataset_manifest.json"))
    return {item["case"]: item for item in manifest.get("cases", [])}


def _evidence(case_id: str) -> Dict[str, Any]:
    return _load_json(repo_path("results", f"{case_id}_evidence.json"))


def _locator(case_id: str) -> Dict[str, Any]:
    paths = {
        "ploutos": repo_path("artifacts", "feed_binding_locator", "ploutos_evidence.json"),
        "moonwell_cbeth": repo_path("artifacts", "moonwell_cbeth_locator", "moonwell_evidence.json"),
        "moonwell_wrseth": repo_path("artifacts", "moonwell_wrseth_locator", "wrseth_findings.json"),
        "blueberry_faulty_oracle": repo_path("artifacts", "blueberry_faulty_oracle_locator", "blueberry_findings.json"),
        "venus_luna": repo_path("artifacts", "venus_luna_locator", "venus_findings.json"),
        "blizz_luna": repo_path("artifacts", "blizz_luna_locator", "dune_findings.json"),
    }
    return _load_json(paths[case_id])


def _trigger_tx(case_id: str, evidence: Dict[str, Any]) -> str:
    for alert in evidence.get("alerts", []):
        if alert.get("type") in TRIGGER_ALERT_TYPES and alert.get("tx_hash"):
            return alert["tx_hash"]
    known = evidence.get("known_txs") or {}
    fallback_keys = (
        "config",
        "mip_x43_execute",
        "stale_oracle_last_update",
        "sample_luna_deposit",
    )
    for key in fallback_keys:
        if known.get(key):
            return known[key]
    if case_id == "moonwell_cbeth":
        return str((_locator(case_id).get("oracle_trigger") or {}).get("tx_hash", ""))
    return ""


def _impact_txs(evidence: Dict[str, Any]) -> List[str]:
    txs = {
        tx_hash
        for candidate in evidence.get("attacker_candidates", [])
        for tx_hash in candidate.get("tx_hashes", [])
        if tx_hash
    }
    return sorted(txs)


def _incident_table_count(case_id: str, name: str) -> Optional[int]:
    path = repo_path("artifacts", "incident_tables", case_id, f"{name}.jsonl")
    if not path.exists():
        return None
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _pre_attack_topic_counts(case_id: str) -> Dict[str, Any]:
    path = repo_path("artifacts", "incident_tables", case_id, "pre_attack_logs.jsonl")
    if not path.exists():
        return {"pre_attack_log_count": 0, "pre_attack_topic_log_count": 0, "pre_attack_topic_coverage": "0/0"}
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    topic_rows = sum(1 for row in rows if row.get("topics"))
    return {
        "pre_attack_log_count": len(rows),
        "pre_attack_topic_log_count": topic_rows,
        "pre_attack_topic_coverage": f"{topic_rows}/{len(rows)}" if rows else "0/0",
    }


def _request_counts(case_id: str, locator: Dict[str, Any]) -> Dict[str, Any]:
    if case_id == "ploutos":
        budget = locator.get("request_budget") or {}
        return {
            "rpc_requests": budget.get("rpc_used", 0),
            "abi_requests": budget.get("abi_used", 0),
            "dune_queries": 0,
        }
    if case_id == "moonwell_cbeth":
        return {
            "rpc_requests": (locator.get("request_budget") or {}).get("rpc_used", 0),
            "abi_requests": 0,
            "dune_queries": len((_load_json(repo_path("artifacts", "moonwell_cbeth_locator", "dune_findings.json")).get("dune_queries") or {})),
        }
    if case_id in {"moonwell_wrseth", "blueberry_faulty_oracle"}:
        return {
            "rpc_requests": (locator.get("request_budget") or {}).get("rpc_used", 0),
            "abi_requests": 0,
            "dune_queries": 0,
        }
    if case_id == "venus_luna":
        fallback = locator.get("rpc_fallback") or {}
        return {
            "rpc_requests": fallback.get("requests", 0),
            "abi_requests": 0,
            "dune_queries": 0,
        }
    if case_id == "blizz_luna":
        return {
            "rpc_requests": 0,
            "abi_requests": 0,
            "dune_queries": len(locator.get("dune_queries") or {}),
        }
    return {"rpc_requests": 0, "abi_requests": 0, "dune_queries": 0}


def _loss_metrics(case_id: str, audit_item: Dict[str, Any], locator: Dict[str, Any]) -> Dict[str, Any]:
    if case_id == "ploutos":
        estimate = _load_json(repo_path("artifacts", "feed_binding_locator", f"{case_id}_loss_estimate.json"))
        if estimate:
            return {
                "loss_metric": estimate.get("estimation_scope", ""),
                "detected_loss": estimate.get("primary_amount", ""),
                "public_reference": "not_estimated",
                "coverage": estimate.get("confidence", ""),
                "loss_confidence": estimate.get("confidence", ""),
                "primary_amount": estimate.get("primary_amount", ""),
                "known_usd_estimate": estimate.get("known_usd_estimate", ""),
                "unknown_or_internal_flow_count": estimate.get("unknown_or_internal_flow_count", ""),
            }
    summary = locator.get("summary") or {}
    if case_id == "venus_luna":
        return {
            "loss_metric": "BUSD borrowed",
            "detected_loss": str(summary.get("total_busd_borrowed", "")),
            "public_reference": str(summary.get("public_narrative_busd", "11411700")),
            "coverage": "main accounts exceed public narrative" if summary.get("total_busd_borrowed") else "",
            "loss_confidence": "protocol_event_decoded",
            "primary_amount": f"{summary.get('total_busd_borrowed', '')} BUSD",
            "known_usd_estimate": str(summary.get("total_busd_borrowed", "")),
            "unknown_or_internal_flow_count": 0,
        }
    if case_id == "blizz_luna":
        return {
            "loss_metric": "known borrowed USD",
            "detected_loss": str(summary.get("borrowed_usd_known", "")),
            "public_reference": str(summary.get("public_loss_usd_halborn_chaincatcher", "8280000")),
            "coverage": f"{summary.get('coverage_vs_828m_pct', '')}%",
            "loss_confidence": "dune_amount_usd_known",
            "primary_amount": f"{summary.get('borrowed_usd_known', '')} USD",
            "known_usd_estimate": str(summary.get("borrowed_usd_known", "")),
            "unknown_or_internal_flow_count": summary.get("borrowed_usd_missing_price_count", ""),
        }
    if case_id == "moonwell_cbeth":
        return {
            "loss_metric": "cbETH borrowed",
            "detected_loss": str(summary.get("total_borrowed_cbeth", "")),
            "public_reference": "not_estimated",
            "coverage": "representative materialized amount",
            "loss_confidence": "protocol_event_decoded",
            "primary_amount": f"{summary.get('total_borrowed_cbeth', '')} cbETH",
            "known_usd_estimate": "",
            "unknown_or_internal_flow_count": "",
        }
    if case_id == "moonwell_wrseth":
        summary = locator.get("summary") or {}
        return {
            "loss_metric": "public bad debt USD",
            "detected_loss": str(summary.get("public_bad_debt_usd", "3700000")),
            "public_reference": "3700000",
            "coverage": "forum canonical attack tx list",
            "loss_confidence": "public_postmortem_reference",
            "primary_amount": f"{summary.get('public_bad_debt_usd', '3700000')} USD",
            "known_usd_estimate": str(summary.get("public_bad_debt_usd", "3700000")),
            "unknown_or_internal_flow_count": "",
        }
    if case_id == "blueberry_faulty_oracle":
        summary = locator.get("summary") or {}
        return {
            "loss_metric": "reported proceeds ETH",
            "detected_loss": str(summary.get("reported_proceeds_eth", "457")),
            "public_reference": "457",
            "coverage": "postmortem canonical attack transaction",
            "loss_confidence": "public_postmortem_reference",
            "primary_amount": f"{summary.get('reported_proceeds_eth', '457')} ETH proceeds",
            "known_usd_estimate": "",
            "unknown_or_internal_flow_count": "",
        }
    return {
        "loss_metric": "not_estimated",
        "detected_loss": audit_item.get("loss_summary", ""),
        "public_reference": "not_estimated",
        "coverage": "",
        "loss_confidence": "not_decodable",
        "primary_amount": "not_estimated",
        "known_usd_estimate": "",
        "unknown_or_internal_flow_count": "",
    }


def build_rows() -> Dict[str, List[Dict[str, Any]]]:
    cases = load_cases()
    audit = _audit_by_case()
    manifest = _manifest_by_case()
    case_rows: List[Dict[str, Any]] = []
    closure_rows: List[Dict[str, Any]] = []
    loss_rows: List[Dict[str, Any]] = []

    for case_id in CASE_ORDER:
        case = cases[case_id]
        evidence = _evidence(case_id)
        locator = _locator(case_id)
        audit_item = audit.get(case_id, {})
        manifest_item = manifest.get(case_id, {})
        trigger_tx = _trigger_tx(case_id, evidence)
        impact_txs = _impact_txs(evidence)
        incident_attack_txs = _incident_table_count(case_id, "attack_txs")
        incident_attackers = _incident_table_count(case_id, "attackers")
        requests = _request_counts(case_id, locator)
        losses = _loss_metrics(case_id, audit_item, locator)
        limitations = "; ".join(audit_item.get("limitations") or [])
        pre_attack = _pre_attack_topic_counts(case_id)

        case_rows.append(
            {
                "case": case_id,
                "name": case.get("name", ""),
                "failure_class": audit_item.get("failure_class") or manifest_item.get("failure_class", ""),
                "chain": case.get("chain", ""),
                "evidence_status": audit_item.get("status", ""),
                "trigger_tx": trigger_tx,
                "impact_tx_count": incident_attack_txs if incident_attack_txs is not None else len(impact_txs),
                "attacker_candidates": incident_attackers if incident_attackers is not None else audit_item.get("attacker_candidates", 0),
                "pre_attack_log_count": pre_attack["pre_attack_log_count"],
                "pre_attack_topic_coverage": pre_attack["pre_attack_topic_coverage"],
                "trace_records": audit_item.get("trace_records", 0),
                "alerts": audit_item.get("alerts", 0),
                "rpc_requests": requests["rpc_requests"],
                "abi_requests": requests["abi_requests"],
                "dune_queries": requests["dune_queries"],
                "limitations": limitations,
            }
        )

        closure_rows.append(
            {
                "case": case_id,
                "has_trigger": bool(trigger_tx or evidence.get("price_source_outliers") or evidence.get("implementation_mismatches")),
                "has_oracle_anomaly": bool(
                    evidence.get("oracle_map")
                    or evidence.get("formula_violations")
                    or evidence.get("stale_assets")
                    or evidence.get("price_source_outliers")
                    or evidence.get("implementation_mismatches")
                ),
                "has_lending_impact": bool((incident_attack_txs or 0) if incident_attack_txs is not None else impact_txs),
                "has_actor": bool((incident_attackers or 0) if incident_attackers is not None else evidence.get("attacker_candidates")),
                "has_temporal_order": bool(audit_item.get("trace_records", 0)),
                "has_replayable_constraint": bool(evidence.get("alerts")),
                "raw_receipt_present": bool(audit_item.get("raw_receipt_present")),
                "transfer_flow_count": audit_item.get("transfer_flow_count", 0),
                "pre_attack_log_count": pre_attack["pre_attack_log_count"],
                "pre_attack_topic_log_count": pre_attack["pre_attack_topic_log_count"],
                "pre_attack_topic_coverage": pre_attack["pre_attack_topic_coverage"],
                "has_pre_attack_topics": pre_attack["pre_attack_topic_log_count"] > 0,
                "evidence_status": audit_item.get("status", ""),
            }
        )

        loss_rows.append(
            {
                "case": case_id,
                "loss_metric": losses["loss_metric"],
                "detected_loss": losses["detected_loss"],
                "public_reference": losses["public_reference"],
                "coverage": losses["coverage"],
                "loss_confidence": losses["loss_confidence"],
                "primary_amount": losses["primary_amount"],
                "known_usd_estimate": losses["known_usd_estimate"],
                "unknown_or_internal_flow_count": losses["unknown_or_internal_flow_count"],
                "loss_summary": audit_item.get("loss_summary", ""),
            }
        )

    return {
        "case_table": case_rows,
        "evidence_closure": closure_rows,
        "loss_coverage": loss_rows,
        "broad_dataset": _broad_dataset_rows(),
    }


def _broad_dataset_rows() -> List[Dict[str, Any]]:
    summary = _load_json(repo_path("artifacts", "broad_search", "candidate_summary.json")) or {}
    seed_summary = _load_json(repo_path("artifacts", "broad_search", "seed_candidate_summary.json")) or {}
    seed_count = int(seed_summary.get("seed_evaluation_count") or len(CASE_ORDER))
    if not summary:
        return [
            {
                "dataset_layer": "seed_evaluation_dataset",
                "seed_set_size": seed_count,
                "remote_candidate_count": 0,
                "local_materialization_queue_count": 0,
                "validated_local_case_count": seed_count,
                "materialization_rate": "",
                "estimated_rpc_requests": 0,
                "estimated_abi_requests": 0,
                "notes": "Broad candidate exports have not been ingested yet.",
            }
        ]
    rows = [
        {
            "dataset_layer": "index_level_candidate_dataset",
            "seed_set_size": seed_count,
            "remote_candidate_count": summary.get("remote_candidate_count", summary.get("candidate_count", 0)),
            "local_materialization_queue_count": summary.get("materialization_queue_count", 0),
            "validated_local_case_count": seed_count,
            "materialization_rate": _rate(summary.get("materialization_queue_count", 0), summary.get("remote_candidate_count", summary.get("candidate_count", 0))),
            "estimated_rpc_requests": summary.get("estimated_queue_rpc_requests", 0),
            "estimated_abi_requests": summary.get("estimated_queue_abi_requests", 0),
            "notes": "Seed cases are already materialized; remote candidates are compact index rows and only the queue is eligible for local receipt materialization.",
        }
    ]
    class_totals: Dict[str, int] = {}
    for key, count in (summary.get("by_class_tier") or {}).items():
        failure_class, tier = key.split("|", 1)
        class_totals[failure_class] = class_totals.get(failure_class, 0) + int(count)
    class_queue = {key: int(value) for key, value in (summary.get("queue_by_class") or {}).items()}
    for failure_class in sorted(class_totals):
        rows.append(
            {
                "dataset_layer": failure_class,
                "seed_set_size": "",
                "remote_candidate_count": class_totals[failure_class],
                "local_materialization_queue_count": class_queue.get(failure_class, 0),
                "validated_local_case_count": "",
                "materialization_rate": _rate(class_queue.get(failure_class, 0), class_totals[failure_class]),
                "estimated_rpc_requests": "",
                "estimated_abi_requests": "",
                "notes": "Per-class remote candidate coverage and local materialization eligibility.",
            }
        )
    return rows


def _rate(numerator: Any, denominator: Any) -> str:
    try:
        denominator = float(denominator)
        numerator = float(numerator)
    except (TypeError, ValueError):
        return ""
    if denominator <= 0:
        return ""
    return f"{(numerator / denominator) * 100:.2f}%"


def _markdown_table(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ""
    headers = list(rows[0].keys())
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        values = [str(row.get(header, "")).replace("\n", " ") for header in headers]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    headers = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def render_tables() -> Dict[str, Path]:
    tables = build_rows()
    outputs = {
        "case_md": repo_path("results", "paper_case_table.md"),
        "closure_md": repo_path("results", "paper_evidence_closure_table.md"),
        "loss_md": repo_path("results", "paper_loss_coverage_table.md"),
        "broad_md": repo_path("results", "paper_broad_dataset_table.md"),
        "case_csv": repo_path("artifacts", "paper_tables", "paper_case_table.csv"),
        "closure_csv": repo_path("artifacts", "paper_tables", "paper_evidence_closure_table.csv"),
        "loss_csv": repo_path("artifacts", "paper_tables", "paper_loss_coverage_table.csv"),
        "broad_csv": repo_path("artifacts", "paper_tables", "paper_broad_dataset_table.csv"),
        "summary_json": repo_path("artifacts", "paper_tables", "paper_tables.json"),
    }
    ensure_dir(outputs["case_md"].parent)
    ensure_dir(outputs["case_csv"].parent)
    outputs["case_md"].write_text("# Paper Case Table\n\n" + _markdown_table(tables["case_table"]), encoding="utf-8")
    outputs["closure_md"].write_text("# Evidence Closure Table\n\n" + _markdown_table(tables["evidence_closure"]), encoding="utf-8")
    outputs["loss_md"].write_text("# Loss Coverage Table\n\n" + _markdown_table(tables["loss_coverage"]), encoding="utf-8")
    outputs["broad_md"].write_text("# Broad Dataset Table\n\n" + _markdown_table(tables["broad_dataset"]), encoding="utf-8")
    _write_csv(outputs["case_csv"], tables["case_table"])
    _write_csv(outputs["closure_csv"], tables["evidence_closure"])
    _write_csv(outputs["loss_csv"], tables["loss_coverage"])
    _write_csv(outputs["broad_csv"], tables["broad_dataset"])
    write_json(outputs["summary_json"], tables)
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Render paper-ready tables from local DSC-Guard MVP artifacts.")
    parser.parse_args()
    outputs = render_tables()
    print("Wrote paper tables:")
    for key, path in outputs.items():
        print(f"- {key}: {path}")


if __name__ == "__main__":
    main()
