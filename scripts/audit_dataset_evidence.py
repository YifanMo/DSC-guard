#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

from common import ensure_dir, load_cases, read_jsonl, repo_path, write_json


ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]{40}")
TX_RE = re.compile(r"0x[0-9a-fA-F]{64}")


def _walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _without_transfer_flows(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_transfer_flows(item)
            for key, item in value.items()
            if key != "transfer_flow_summary"
        }
    if isinstance(value, list):
        return [_without_transfer_flows(item) for item in value]
    return value


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _is_placeholder_address(value: str) -> bool:
    body = value.lower().removeprefix("0x")
    if len(body) != 40:
        return False
    if len(set(body)) == 1:
        return True
    return value.lower() in {
        "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    }


def _is_placeholder_tx(value: str) -> bool:
    body = value.lower().removeprefix("0x")
    return len(body) == 64 and len(set(body)) <= 2 and body[:40] == body[0] * 40


def _placeholder_values(values: Iterable[Any]) -> List[str]:
    found: Set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        for address in ADDRESS_RE.findall(value):
            if _is_placeholder_address(address):
                found.add(address.lower())
        for tx_hash in TX_RE.findall(value):
            if _is_placeholder_tx(tx_hash):
                found.add(tx_hash.lower())
    return sorted(found)


def _synthetic_markers(values: Iterable[Any]) -> List[str]:
    markers = []
    for value in values:
        if not isinstance(value, str):
            continue
        lower = value.lower()
        if any(token in lower for token in ("synthetic", "fixture", "placeholder")):
            markers.append(value)
    return sorted(set(markers))[:20]


def _evidence_quality(trace: List[Dict[str, Any]]) -> List[str]:
    quality = set()
    for record in trace:
        decoded = record.get("decoded") or {}
        if decoded.get("evidence_quality"):
            quality.add(str(decoded["evidence_quality"]))
        if decoded.get("source"):
            quality.add(str(decoded["source"]))
    return sorted(quality)


def _transfer_flow_count(trace: List[Dict[str, Any]]) -> int:
    seen = set()
    for record in trace:
        for item in (record.get("decoded") or {}).get("transfer_flow_summary") or []:
            key = (
                item.get("tx_hash"),
                item.get("log_index"),
                item.get("token_address"),
                item.get("from"),
                item.get("to"),
                item.get("amount_raw"),
            )
            seen.add(key)
    return len(seen)


def _pre_attack_logs(case_id: str) -> List[Dict[str, Any]]:
    path = repo_path("artifacts", "incident_tables", case_id, "pre_attack_logs.jsonl")
    return read_jsonl(path) if path.exists() else []


def _pre_attack_scan(case_id: str) -> Dict[str, Any]:
    path = repo_path("artifacts", "pre_attack_log_scans", f"{case_id}.json")
    return _load_json(path) or {}


def _has_real_attacker(evidence: Dict[str, Any]) -> bool:
    attackers = evidence.get("attacker_candidates") or []
    if not attackers:
        return False
    return any(not _is_placeholder_address(item.get("address", "")) for item in attackers)


def _raw_receipt_present(raw_evidence: Dict[str, Any]) -> bool:
    txs = raw_evidence.get("transactions") if isinstance(raw_evidence, dict) else {}
    if not isinstance(txs, dict):
        return False
    if txs and all(
        (item or {}).get("receipt") and (item or {}).get("transaction") and (item or {}).get("block")
        for item in txs.values()
        if isinstance(item, dict)
    ):
        return True
    for role in ("config", "exploit"):
        receipt = (txs.get(role) or {}).get("receipt")
        transaction = (txs.get(role) or {}).get("transaction")
        block = (txs.get(role) or {}).get("block")
        if not receipt or not transaction or not block:
            return False
    return True


def _has_raw_config_log(raw_evidence: Dict[str, Any]) -> bool:
    txs = raw_evidence.get("transactions") if isinstance(raw_evidence, dict) else {}
    receipt = ((txs or {}).get("config") or {}).get("receipt") if isinstance(txs, dict) else None
    if not receipt and isinstance(txs, dict):
        for item in txs.values():
            if not isinstance(item, dict) or item.get("role") != "oracle_trigger":
                continue
            receipt = item.get("receipt")
            break
    return bool(receipt and receipt.get("logs"))


def _moonwell_full_candidate_trace(trace: List[Dict[str, Any]], materialized: Dict[str, Any]) -> bool:
    if not trace:
        return False
    has_trigger = any(record.get("event_type") == "ORACLE_FORMULA_SET" for record in trace)
    borrow_txs = {record.get("tx_hash") for record in trace if record.get("event_type") == "BORROW"}
    expected = int(((materialized.get("summary") or {}).get("borrow_tx_count") or 14))
    has_dune_quality = any(
        (record.get("decoded") or {}).get("evidence_quality") in {
            "dune_decoded_event",
            "rpc_receipt_backed",
            "receipt_flow_decoded",
        }
        for record in trace
    )
    return has_trigger and len(borrow_txs) >= expected and expected >= 14 and has_dune_quality


def _moonwell_wrseth_trace(trace: List[Dict[str, Any]]) -> bool:
    if not trace:
        return False
    has_trigger = any(record.get("event_type") == "ORACLE_PRICE_MALFUNCTION" for record in trace)
    borrow_txs = {record.get("tx_hash") for record in trace if record.get("event_type") == "BORROW" and record.get("tx_hash")}
    return has_trigger and len(borrow_txs) >= 12


def _blueberry_trace(trace: List[Dict[str, Any]]) -> bool:
    if not trace:
        return False
    has_trigger = any(record.get("event_type") == "ORACLE_IMPLEMENTATION_MISMATCH" for record in trace)
    borrow_txs = {record.get("tx_hash") for record in trace if record.get("event_type") == "BORROW" and record.get("tx_hash")}
    return has_trigger and len(borrow_txs) >= 1


def _status_for_case(
    case_id: str,
    trace: List[Dict[str, Any]],
    placeholders: List[str],
    fixture_tx_hits: List[str],
    qualities: List[str],
    locator_exists: bool,
    raw_receipt_present: bool,
    transfer_flow_count: int,
    has_real_attacker: bool,
    has_raw_config_log: bool,
    materialized_evidence: Dict[str, Any] | None = None,
) -> str:
    if placeholders or fixture_tx_hits:
        return "fixture_only"
    if case_id == "moonwell_cbeth" and _moonwell_full_candidate_trace(trace, materialized_evidence or {}):
        if raw_receipt_present and has_raw_config_log:
            return "real_materialized"
        return "real_materialized_with_dune_decode"
    if case_id == "moonwell_wrseth" and _moonwell_wrseth_trace(trace):
        return "real_materialized"
    if case_id == "blueberry_faulty_oracle" and _blueberry_trace(trace):
        return "real_materialized"
    if raw_receipt_present and transfer_flow_count > 0 and has_real_attacker and has_raw_config_log:
        return "real_tx_with_receipt_flow_decode"
    if any("inferred" in item or "unknown" in json.dumps(record.get("decoded", {})) for item in qualities for record in trace):
        return "real_tx_with_inferred_decode"
    if case_id == "moonwell_cbeth":
        return "representative_real_events"
    if locator_exists and trace:
        return "real_materialized"
    return "real_tx_with_inferred_decode" if trace else "fixture_only"


def _loss_summary(case_id: str) -> str:
    if case_id == "ploutos":
        estimate = _load_json(repo_path("artifacts", "feed_binding_locator", f"{case_id}_loss_estimate.json")) or {}
        if estimate:
            return estimate.get("loss_summary", "not_estimated")
    if case_id == "venus_luna":
        findings = _load_json(repo_path("artifacts", "venus_luna_locator", "venus_findings.json")) or {}
        summary = findings.get("summary", {})
        return f"total_borrowed_busd={summary.get('total_busd_borrowed', 'unknown')}; top_two={summary.get('top_two_busd_borrowed', 'unknown')}"
    if case_id == "blizz_luna":
        findings = _load_json(repo_path("artifacts", "blizz_luna_locator", "dune_findings.json")) or {}
        summary = findings.get("summary", {})
        return (
            f"known_borrowed_usd={summary.get('known_borrowed_usd', summary.get('borrowed_usd_known', 'unknown'))}; "
            f"public_loss_usd={summary.get('public_loss_usd_halborn_chaincatcher', summary.get('public_loss_usd', '8280000'))}; "
            f"coverage={summary.get('coverage_vs_828m_pct', summary.get('coverage_ratio', 'unknown'))}"
        )
    if case_id == "moonwell_cbeth":
        findings = _load_json(repo_path("artifacts", "moonwell_cbeth_locator", "dune_findings.json")) or {}
        summary = findings.get("summary", {})
        return f"cbeth_borrowed={summary.get('total_borrowed_cbeth', summary.get('total_cbeth_borrowed', 'representative'))}"
    if case_id == "moonwell_wrseth":
        findings = _load_json(repo_path("artifacts", "moonwell_wrseth_locator", "wrseth_findings.json")) or {}
        summary = findings.get("summary", {})
        return f"public_bad_debt_usd={summary.get('public_bad_debt_usd', '3700000')}; canonical_attack_txs={summary.get('attack_tx_count', '12')}"
    if case_id == "blueberry_faulty_oracle":
        findings = _load_json(repo_path("artifacts", "blueberry_faulty_oracle_locator", "blueberry_findings.json")) or {}
        summary = findings.get("summary", {})
        return (
            f"reported_proceeds_eth={summary.get('reported_proceeds_eth', '457')}; "
            f"canonical_attack_txs={summary.get('attack_tx_count', '1')}"
        )
    return "not_estimated"


def audit_case(case_id: str, case: Dict[str, Any]) -> Dict[str, Any]:
    trace_path = repo_path("artifacts", "log_trace", f"{case_id}.jsonl")
    evidence_path = repo_path("results", f"{case_id}_evidence.json")
    locator_path = repo_path("results", f"{case_id}_locator.md")
    if case_id == "moonwell_cbeth":
        raw_evidence_path = repo_path("artifacts", "moonwell_cbeth_locator", "raw_evidence.json")
    elif case_id == "moonwell_wrseth":
        raw_evidence_path = repo_path("artifacts", "moonwell_wrseth_locator", "raw_evidence.json")
    elif case_id == "blueberry_faulty_oracle":
        raw_evidence_path = repo_path("artifacts", "blueberry_faulty_oracle_locator", "raw_evidence.json")
    else:
        raw_evidence_path = repo_path("artifacts", "feed_binding_locator", f"{case_id}_raw_evidence.json")
    materialized_evidence_path = repo_path("artifacts", "moonwell_cbeth_locator", "moonwell_evidence.json") if case_id == "moonwell_cbeth" else None
    incident_dir = repo_path("artifacts", "incident_tables", case_id)

    trace = read_jsonl(trace_path) if trace_path.exists() else []
    evidence = _load_json(evidence_path) or {}
    raw_evidence = _load_json(raw_evidence_path) or {}
    materialized_evidence = _load_json(materialized_evidence_path) if materialized_evidence_path else {}
    materialized_evidence = materialized_evidence or {}
    placeholder_values = list(_walk(_without_transfer_flows(trace))) + list(_walk(evidence))
    values = list(_walk(trace)) + list(_walk(evidence))
    placeholders = _placeholder_values(placeholder_values)
    synthetic = _synthetic_markers(values)
    fixture_tx_hits = sorted({(record.get("tx_hash") or "").lower() for record in trace if _is_placeholder_tx(record.get("tx_hash") or "")})
    qualities = _evidence_quality(trace)
    locator_exists = locator_path.exists()
    flow_count = _transfer_flow_count(trace)
    pre_attack_logs = _pre_attack_logs(case_id)
    pre_attack_log_count = len(pre_attack_logs)
    pre_attack_topic_log_count = sum(1 for row in pre_attack_logs if row.get("topics"))
    pre_attack_scan = _pre_attack_scan(case_id)
    has_attacker = _has_real_attacker(evidence)
    has_raw = _raw_receipt_present(raw_evidence)
    has_config_log = _has_raw_config_log(raw_evidence)
    status = _status_for_case(
        case_id,
        trace,
        placeholders,
        fixture_tx_hits,
        qualities,
        locator_exists,
        has_raw,
        flow_count,
        has_attacker,
        has_config_log,
        materialized_evidence,
    )
    incident_attackers = read_jsonl(incident_dir / "attackers.jsonl") if (incident_dir / "attackers.jsonl").exists() else []
    incident_attack_txs = read_jsonl(incident_dir / "attack_txs.jsonl") if (incident_dir / "attack_txs.jsonl").exists() else []
    attackers = evidence.get("attacker_candidates") or []
    attack_txs = sorted({tx for item in attackers for tx in item.get("tx_hashes", [])})
    attacker_count = len(incident_attackers) if incident_attackers else len(attackers)
    attack_tx_count = len(incident_attack_txs) if incident_attack_txs else len(attack_txs)

    return {
        "case": case_id,
        "name": case["name"],
        "chain": case["chain"],
        "failure_class": _failure_class(case_id),
        "status": status,
        "trace_path": str(trace_path),
        "evidence_path": str(evidence_path),
        "locator_path": str(locator_path) if locator_exists else "",
        "raw_evidence_path": str(raw_evidence_path) if raw_evidence_path.exists() else "",
        "materialized_evidence_path": str(materialized_evidence_path) if materialized_evidence_path and materialized_evidence_path.exists() else "",
        "raw_receipt_present": has_raw,
        "transfer_flow_count": flow_count,
        "pre_attack_logs_path": str(repo_path("artifacts", "incident_tables", case_id, "pre_attack_logs.jsonl"))
        if repo_path("artifacts", "incident_tables", case_id, "pre_attack_logs.jsonl").exists()
        else "",
        "pre_attack_log_count": pre_attack_log_count,
        "pre_attack_topic_log_count": pre_attack_topic_log_count,
        "pre_attack_topic_coverage": f"{pre_attack_topic_log_count}/{pre_attack_log_count}" if pre_attack_log_count else "0/0",
        "missing_pre_attack_receipt_reason": pre_attack_scan.get("missing_pre_attack_receipt_reason", ""),
        "has_real_attacker": has_attacker,
        "has_raw_config_log": has_config_log,
        "trace_records": len(trace),
        "alerts": len(evidence.get("alerts") or []),
        "attacker_candidates": attacker_count,
        "attack_transactions": attack_tx_count,
        "incident_tables_path": str(incident_dir) if incident_dir.exists() else "",
        "placeholder_values": placeholders,
        "fixture_tx_hits": fixture_tx_hits,
        "synthetic_markers": synthetic,
        "evidence_quality": qualities,
        "loss_summary": _loss_summary(case_id),
        "limitations": _limitations(status, placeholders, fixture_tx_hits, qualities, case_id),
    }


def _failure_class(case_id: str) -> str:
    manifest = _load_json(repo_path("artifacts", "dataset_manifest.json")) or {}
    for case in manifest.get("cases", []):
        if case.get("case") == case_id:
            return case.get("failure_class", "")
    return ""


def _limitations(status: str, placeholders: List[str], fixture_tx_hits: List[str], qualities: List[str], case_id: str = "") -> List[str]:
    limitations = []
    if placeholders:
        limitations.append("placeholder values remain in trace/evidence")
    if fixture_tx_hits:
        limitations.append("fixture transaction hashes remain in trace")
    if status in ("real_tx_with_inferred_decode", "real_tx_with_receipt_flow_decode"):
        limitations.append("some protocol-specific event fields are inferred from known transactions rather than fully ABI-decoded")
    if any("unknown" in item for item in qualities):
        limitations.append("some decoded amounts remain unknown")
    if case_id == "ploutos":
        estimate = _load_json(repo_path("artifacts", "feed_binding_locator", f"{case_id}_loss_estimate.json")) or {}
        if estimate.get("confidence") == "receipt_flow_estimated":
            limitations.append("loss is a receipt-flow impact estimate, not a fully protocol-decoded loss amount")
    scan = _pre_attack_scan(case_id) if case_id else {}
    missing_pre_attack = scan.get("missing_pre_attack_receipt_reason")
    if missing_pre_attack:
        limitations.append(f"pre-attack receipt/log topics incomplete: {missing_pre_attack}")
    return limitations


def render_audit_markdown(audit: Dict[str, Any]) -> str:
    lines = [
        "# Dataset Evidence Audit",
        "",
        "This audit checks whether MVP evidence is backed by historical records or still contains fixture/synthetic values.",
        "",
        "| Case | Status | Records | Alerts | Attackers | Attack txs | Flow logs | Pre-attack logs | Topic coverage | Placeholders | Loss / coverage |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in audit["cases"]:
        lines.append(
            f"| `{item['case']}` | `{item['status']}` | {item['trace_records']} | {item['alerts']} | "
            f"{item['attacker_candidates']} | {item['attack_transactions']} | {item['transfer_flow_count']} | "
            f"{item.get('pre_attack_log_count', 0)} | {item.get('pre_attack_topic_coverage', '0/0')} | "
            f"{len(item['placeholder_values'])} | {item['loss_summary']} |"
        )
    lines.extend(["", "## Limitations", ""])
    for item in audit["cases"]:
        if not item["limitations"]:
            continue
        lines.append(f"- `{item['case']}`: " + "; ".join(item["limitations"]))
    lines.append("")
    return "\n".join(lines)


def render_paper_readiness(audit: Dict[str, Any]) -> str:
    status_counts: Dict[str, int] = {}
    for item in audit["cases"]:
        status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1
    lines = [
        "# Paper Readiness Snapshot",
        "",
        "## Evidence Status",
        "",
    ]
    for status, count in sorted(status_counts.items()):
        lines.append(f"- `{status}`: {count} case(s)")
    lines.extend(
        [
            "",
            "## Current Claim Boundary",
            "",
            "- The dataset supports a bounded study of price-oracle consumption failures in EVM lending protocols.",
            "- The implementation should be described as Slither-derived semantic IR plus K-style replay semantics for oracle-consumption constraints.",
            "- Fixture traces are retained for pipeline tests only and should not be described as paper evidence.",
            "",
            "## Case Summary",
            "",
        ]
    )
    for item in audit["cases"]:
        lines.append(
            f"- `{item['case']}` ({item['failure_class']}): {item['status']}, "
            f"{item['attacker_candidates']} attacker candidate(s), {item['attack_transactions']} attack tx(s), "
            f"{item.get('pre_attack_log_count', 0)} pre-attack log(s), {item['loss_summary']}."
        )
    lines.append("")
    return "\n".join(lines)


def run_audit() -> Dict[str, Any]:
    cases = load_cases()
    audit = {
        "scope": "read-only audit of local DSC-Guard MVP evidence artifacts",
            "status_definitions": {
                "real_materialized": "Trace is backed by historical materialized events without placeholder values.",
                "real_materialized_with_dune_decode": "Trace is fully materialized from Dune decoded historical protocol events; raw receipts are optional evidence.",
                "representative_real_events": "Trace uses real events but intentionally keeps representative evidence rather than full incident coverage.",
                "real_tx_with_receipt_flow_decode": "Trace uses real historical transactions and receipt-backed ERC20 transfer flow, while some protocol-specific decoded fields are inferred or unknown.",
                "real_tx_with_inferred_decode": "Trace uses real historical transactions, while some protocol-specific decoded fields are inferred or unknown.",
                "fixture_only": "Trace/evidence still contains fixture or placeholder values.",
            },
        "cases": [audit_case(case_id, case) for case_id, case in cases.items()],
    }
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit local MVP evidence quality for paper readiness.")
    parser.parse_args()
    audit = run_audit()
    write_json(repo_path("artifacts", "dataset_audit.json"), audit)
    audit_md = repo_path("results", "dataset_audit.md")
    readiness_md = repo_path("results", "paper_readiness.md")
    ensure_dir(audit_md.parent)
    audit_md.write_text(render_audit_markdown(audit), encoding="utf-8")
    readiness_md.write_text(render_paper_readiness(audit), encoding="utf-8")
    print(f"Wrote dataset audit: {audit_md}")
    print(f"Wrote paper readiness snapshot: {readiness_md}")


if __name__ == "__main__":
    main()
