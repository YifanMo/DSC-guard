#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from common import PipelineError, ensure_dir, get_case, repo_path, write_json
from materialize_feed_binding_case import (
    ERC20_TRANSFER_TOPIC,
    _format_amount,
    _hex_to_int,
    _norm_addr,
    decode_erc20_transfer,
)


SUPPORTED_CASES = {"ploutos"}
COMPOUND_MINT_TOPIC = "0x4c209b5fc8ad50758f13e2e1088ba56a560dff690a1c6fef26394f4c03821c4f"
COMPOUND_BORROW_TOPIC = "0x13ed6866d4e1ee6da46f845c46d7e54120883d75c5ea9a2dacc1c4ca8984ab80"
COMPOUND_ACCRUE_INTEREST_TOPIC = "0x4dec04e750ca11537cabcd8a9eab06494de08da3735bc8871cd41250e190bc04"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
STABLE_SYMBOLS = {"USDC", "USDT", "USDC.e", "USDT.e", "DAI", "DAI.e", "BUSD", "USDbC"}


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise PipelineError(f"Missing required artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _words(data: str) -> List[str]:
    body = (data or "0x")[2:]
    return [body[index : index + 64] for index in range(0, len(body), 64) if body[index : index + 64]]


def _word_to_uint(word: str) -> int:
    return int(word or "0", 16)


def _word_to_address(word: str) -> str:
    return _norm_addr(word[-40:])


def _topics(log: Dict[str, Any]) -> List[str]:
    return [str(topic).lower() for topic in (log.get("topics") or [])]


def _decode_compound_borrow(log: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    topics = _topics(log)
    if not topics or topics[0] != COMPOUND_BORROW_TOPIC:
        return None
    words = _words(log.get("data", ""))
    if len(words) < 4:
        return None
    return {
        "event": "Borrow",
        "market_address": _norm_addr(log.get("address", "")),
        "borrower": _word_to_address(words[0]),
        "borrow_amount_raw": str(_word_to_uint(words[1])),
        "account_borrows_raw": str(_word_to_uint(words[2])),
        "total_borrows_raw": str(_word_to_uint(words[3])),
        "log_index": _hex_to_int(log.get("logIndex", "0x0")),
        "tx_hash": log.get("transactionHash", ""),
    }


def _decode_compound_mint(log: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    topics = _topics(log)
    if not topics or topics[0] != COMPOUND_MINT_TOPIC:
        return None
    words = _words(log.get("data", ""))
    if len(words) < 3:
        return None
    return {
        "event": "Mint",
        "market_address": _norm_addr(log.get("address", "")),
        "minter": _word_to_address(words[0]),
        "mint_amount_raw": str(_word_to_uint(words[1])),
        "mint_tokens_raw": str(_word_to_uint(words[2])),
        "log_index": _hex_to_int(log.get("logIndex", "0x0")),
        "tx_hash": log.get("transactionHash", ""),
    }


def _decode_accrue_interest(log: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    topics = _topics(log)
    if not topics or topics[0] != COMPOUND_ACCRUE_INTEREST_TOPIC:
        return None
    words = _words(log.get("data", ""))
    if len(words) < 4:
        return None
    return {
        "event": "AccrueInterest",
        "market_address": _norm_addr(log.get("address", "")),
        "cash_prior_raw": str(_word_to_uint(words[0])),
        "interest_accumulated_raw": str(_word_to_uint(words[1])),
        "borrow_index_raw": str(_word_to_uint(words[2])),
        "total_borrows_raw": str(_word_to_uint(words[3])),
        "log_index": _hex_to_int(log.get("logIndex", "0x0")),
        "tx_hash": log.get("transactionHash", ""),
    }


def decode_compound_events(logs: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    events = {"borrows": [], "mints": [], "accrue_interest": []}
    for log in logs:
        borrow = _decode_compound_borrow(log)
        if borrow:
            events["borrows"].append(borrow)
            continue
        mint = _decode_compound_mint(log)
        if mint:
            events["mints"].append(mint)
            continue
        accrue = _decode_accrue_interest(log)
        if accrue:
            events["accrue_interest"].append(accrue)
    return events


def decode_transfers(logs: Iterable[Dict[str, Any]], chain: str) -> List[Dict[str, Any]]:
    transfers = []
    for log in logs:
        transfer = decode_erc20_transfer(log, chain)
        if not transfer:
            continue
        transfer["from"] = _norm_addr(transfer["from"])
        transfer["to"] = _norm_addr(transfer["to"])
        transfer["token_address"] = _norm_addr(transfer["token_address"])
        transfer["classification"] = classify_transfer(transfer)
        transfers.append(transfer)
    return sorted(transfers, key=lambda item: item["log_index"])


def classify_transfer(transfer: Dict[str, Any]) -> str:
    if transfer.get("from") == ZERO_ADDRESS or transfer.get("to") == ZERO_ADDRESS:
        return "mint_or_burn"
    if transfer.get("symbol") == "UNKNOWN" or transfer.get("decimals") is None:
        return "unknown_or_internal"
    return "known_token_flow"


def _infer_underlying_from_transfer(
    borrow: Dict[str, Any],
    transfers: List[Dict[str, Any]],
) -> Dict[str, Any]:
    market = _norm_addr(borrow["market_address"])
    raw = str(borrow["borrow_amount_raw"])
    borrow_index = int(borrow["log_index"])
    for transfer in transfers:
        if transfer["log_index"] < borrow_index:
            continue
        if transfer["from"] != market:
            continue
        if str(transfer["amount_raw"]) != raw:
            continue
        return {
            "borrow_asset": transfer["symbol"],
            "borrow_token_address": transfer["token_address"],
            "borrow_amount": transfer["amount"],
            "borrow_decimals": transfer["decimals"],
            "matched_transfer_log_index": transfer["log_index"],
            "recipient": transfer["to"],
        }
    return {
        "borrow_asset": "UNKNOWN",
        "borrow_token_address": "",
        "borrow_amount": raw,
        "borrow_decimals": None,
        "matched_transfer_log_index": None,
        "recipient": "",
    }


def _known_usd_estimate(asset: str, amount: str) -> str:
    if asset not in STABLE_SYMBOLS:
        return ""
    try:
        return str(Decimal(amount))
    except Exception:
        return ""


def _observable_flows(transfers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    flows = []
    for transfer in transfers:
        item = {
            "log_index": transfer["log_index"],
            "token_address": transfer["token_address"],
            "symbol": transfer["symbol"],
            "amount": transfer["amount"],
            "amount_raw": transfer["amount_raw"],
            "from": transfer["from"],
            "to": transfer["to"],
            "classification": transfer["classification"],
        }
        flows.append(item)
    return flows


def _largest_known_flow(transfers: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    known = [item for item in transfers if item.get("classification") == "known_token_flow"]
    if not known:
        return None
    # This is only a presentation helper. Do not compare values across token symbols for loss accounting.
    return max(known, key=lambda item: Decimal(str(item.get("amount") or "0")))


def _summary_from_borrow(
    case_id: str,
    borrow: Dict[str, Any],
    transfers: List[Dict[str, Any]],
) -> Dict[str, Any]:
    inferred = _infer_underlying_from_transfer(borrow, transfers)
    amount = inferred["borrow_amount"]
    asset = inferred["borrow_asset"]
    known_usd = _known_usd_estimate(asset, amount)
    return {
        "confidence": "protocol_event_decoded",
        "estimation_scope": "compound_borrow_event_with_underlying_transfer_match",
        "primary_amount": f"{amount} {asset}",
        "primary_asset": asset,
        "primary_amount_raw": borrow["borrow_amount_raw"],
        "known_usd_estimate": known_usd,
        "loss_summary": f"protocol_event_decoded: {amount} {asset} borrowed",
        "protocol_borrow": {**borrow, **inferred},
        "notes": [
            "Borrow amount is decoded from a Compound-style Borrow event.",
            "Underlying token is inferred from a same-transaction ERC20 Transfer from the market with matching raw amount.",
        ],
    }


def _summary_from_receipt_flow(transfers: List[Dict[str, Any]]) -> Dict[str, Any]:
    largest = _largest_known_flow(transfers)
    unknown_or_internal = sum(1 for item in transfers if item.get("classification") != "known_token_flow")
    if not largest:
        return {
            "confidence": "not_decodable",
            "estimation_scope": "only_unknown_or_internal_receipt_flows",
            "primary_amount": "not_decodable",
            "primary_asset": "UNKNOWN",
            "known_usd_estimate": "",
            "loss_summary": "not_decodable",
            "unknown_or_internal_flow_count": unknown_or_internal,
            "notes": ["No known-token ERC20 flow was available for a conservative impact estimate."],
        }
    amount = largest["amount"]
    asset = largest["symbol"]
    return {
        "confidence": "receipt_flow_estimated",
        "estimation_scope": "largest_known_token_flow_in_exploit_receipt_not_protocol_loss",
        "primary_amount": f"{amount} {asset}",
        "primary_asset": asset,
        "primary_amount_raw": largest["amount_raw"],
        "known_usd_estimate": _known_usd_estimate(asset, amount),
        "loss_summary": f"receipt_flow_estimated: largest known-token flow {amount} {asset}",
        "representative_flow": largest,
        "unknown_or_internal_flow_count": unknown_or_internal,
        "notes": [
            "No standard Compound-style Borrow event was decoded in the exploit receipt.",
            "This is an observable receipt-flow impact estimate, not a protocol-level loss amount.",
            "Mint/burn, AMM swap, and unknown/internal token flows are not counted as protocol loss.",
        ],
    }


def build_estimate(case_id: str) -> Dict[str, Any]:
    if case_id not in SUPPORTED_CASES:
        raise PipelineError(f"Unsupported case: {case_id}. Expected one of {sorted(SUPPORTED_CASES)}")
    case = get_case(case_id)
    materialized = _load_json(repo_path("artifacts", "feed_binding_locator", f"{case_id}_evidence.json"))
    raw = _load_json(repo_path("artifacts", "feed_binding_locator", f"{case_id}_raw_evidence.json"))
    receipt = raw["transactions"]["exploit"]["receipt"]
    logs = receipt.get("logs") or []
    compound = decode_compound_events(logs)
    transfers = decode_transfers(logs, case["chain"])

    if compound["borrows"]:
        summary = _summary_from_borrow(case_id, compound["borrows"][0], transfers)
    else:
        summary = _summary_from_receipt_flow(transfers)
        summary.setdefault("unknown_or_internal_flow_count", sum(1 for item in transfers if item.get("classification") != "known_token_flow"))

    estimate = {
        "case": case_id,
        "case_name": case["name"],
        "chain": case["chain"],
        "scope": "offline loss/impact estimate from historical receipt evidence",
        "safety": {
            "offline_only": True,
            "no_network": True,
            "no_write_calls": True,
            "no_private_keys": True,
            "no_simulation": True,
        },
        "exploit_tx": materialized["transactions"]["exploit"]["hash"],
        "attacker_candidate": materialized["transactions"]["exploit"]["from"],
        "tx_target": materialized["transactions"]["exploit"]["to"],
        "confidence": summary["confidence"],
        "estimation_scope": summary["estimation_scope"],
        "primary_amount": summary["primary_amount"],
        "primary_asset": summary["primary_asset"],
        "known_usd_estimate": summary.get("known_usd_estimate", ""),
        "unknown_or_internal_flow_count": summary.get(
            "unknown_or_internal_flow_count",
            sum(1 for item in transfers if item.get("classification") != "known_token_flow"),
        ),
        "loss_summary": summary["loss_summary"],
        "summary": summary,
        "compound_events": compound,
        "observable_flows": _observable_flows(transfers),
        "artifact_inputs": {
            "materialized_evidence": f"artifacts/feed_binding_locator/{case_id}_evidence.json",
            "raw_evidence": f"artifacts/feed_binding_locator/{case_id}_raw_evidence.json",
        },
    }
    return estimate


def render_markdown(estimate: Dict[str, Any]) -> str:
    lines = [
        f"# {estimate['case_name']} Loss / Impact Estimate",
        "",
        "## Scope",
        "",
        "- Input: local historical receipt evidence only.",
        "- No RPC, Dune, explorer API, write call, private key, or transaction simulation is used.",
        "- The estimate is evidence-scoped; it does not fabricate protocol amounts when protocol events are unavailable.",
        "",
        "## Estimate",
        "",
        f"- Confidence: `{estimate['confidence']}`",
        f"- Estimation scope: `{estimate['estimation_scope']}`",
        f"- Primary amount: `{estimate['primary_amount']}`",
        f"- Known USD estimate: `{estimate['known_usd_estimate'] or 'not_priced'}`",
        f"- Unknown/internal flow count: `{estimate['unknown_or_internal_flow_count']}`",
        f"- Exploit tx: `{estimate['exploit_tx']}`",
        f"- Attacker candidate: `{estimate['attacker_candidate']}`",
        "",
        "## Notes",
        "",
    ]
    for note in estimate.get("summary", {}).get("notes", []):
        lines.append(f"- {note}")
    lines.extend(["", "## Decoded Protocol Events", ""])
    borrows = estimate.get("compound_events", {}).get("borrows") or []
    if borrows:
        for borrow in borrows:
            lines.append(
                f"- Borrow at log `{borrow['log_index']}` market `{borrow['market_address']}` "
                f"borrower `{borrow['borrower']}` raw `{borrow['borrow_amount_raw']}`"
            )
    else:
        lines.append("- No standard Compound-style Borrow event decoded.")
    lines.extend(["", "## Observable Transfer Flow", ""])
    for flow in estimate.get("observable_flows", []):
        lines.append(
            f"- log `{flow['log_index']}` {flow['classification']}: {flow['amount']} {flow['symbol']} "
            f"from `{flow['from']}` to `{flow['to']}`"
        )
    lines.append("")
    return "\n".join(lines)


def estimate(case_id: str) -> Dict[str, Path]:
    estimate_data = build_estimate(case_id)
    output_json = repo_path("artifacts", "feed_binding_locator", f"{case_id}_loss_estimate.json")
    output_md = repo_path("results", f"{case_id}_loss_estimate.md")
    write_json(output_json, estimate_data)
    ensure_dir(output_md.parent)
    output_md.write_text(render_markdown(estimate_data), encoding="utf-8")
    return {"json": output_json, "report": output_md}


def main() -> None:
    parser = argparse.ArgumentParser(description="Estimate Ploutos/Rho feed-binding impact from local receipt evidence.")
    parser.add_argument("--case", required=True, choices=sorted(SUPPORTED_CASES))
    args = parser.parse_args()
    try:
        outputs = estimate(args.case)
    except PipelineError as exc:
        raise SystemExit(str(exc)) from exc
    print("Wrote feed-binding loss estimate:")
    for key, path in outputs.items():
        print(f"- {key}: {path}")


if __name__ == "__main__":
    main()
