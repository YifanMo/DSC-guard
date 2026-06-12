#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from common import (
    PipelineError,
    ensure_dir,
    get_case,
    http_json,
    load_env,
    print_status,
    repo_path,
    write_json,
)


def _extract_result(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    result = payload.get("result")
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return [result]
    raise PipelineError(f"Explorer response did not contain a list result: {payload}")


def _source_filename(address: str) -> str:
    return address.lower().replace("0x", "") + ".source.json"


def _abi_filename(address: str) -> str:
    return address.lower().replace("0x", "") + ".abi.json"


def _safe_source_path(root: Path, raw_name: str, fallback: str) -> Path:
    name = (raw_name or fallback).strip().replace("\\", "/")
    if not name or name in {".", "/"}:
        name = fallback
    if not name.endswith(".sol"):
        name = f"{name}.sol"
    clean_parts = []
    for part in name.split("/"):
        if not part or part in {".", ".."}:
            continue
        clean_parts.append(re.sub(r"[^A-Za-z0-9._ -]", "_", part))
    if not clean_parts:
        clean_parts = [fallback]
    return root.joinpath(*clean_parts)


def _parse_multisource(source_code: str) -> Dict[str, Any] | None:
    text = source_code.strip()
    if not text:
        return None
    if text.startswith("{{") and text.endswith("}}"):
        text = text[1:-1]
    if not text.startswith("{"):
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def write_source_files(case_id: str, address: str, result: Dict[str, Any], source_dir: Path) -> List[str]:
    source_code = result.get("SourceCode") or ""
    if not source_code or source_code == "Contract source code not verified":
        return []
    address_dir = source_dir / address.lower()
    ensure_dir(address_dir)
    contract_name = result.get("ContractName") or address.lower().replace("0x", "")
    fallback = f"{contract_name}.sol"
    written: List[str] = []
    parsed = _parse_multisource(source_code)
    if parsed and isinstance(parsed.get("sources"), dict):
        for raw_name, source_obj in parsed["sources"].items():
            if isinstance(source_obj, dict):
                content = source_obj.get("content") or ""
            else:
                content = str(source_obj)
            if not content.strip():
                continue
            path = _safe_source_path(address_dir, raw_name, fallback)
            ensure_dir(path.parent)
            path.write_text(content.rstrip() + "\n", encoding="utf-8")
            written.append(str(path.relative_to(repo_path())))
    else:
        filename = result.get("ContractFileName") or result.get("FileName") or fallback
        path = _safe_source_path(address_dir, filename, fallback)
        ensure_dir(path.parent)
        path.write_text(source_code.rstrip() + "\n", encoding="utf-8")
        written.append(str(path.relative_to(repo_path())))
    return written


def fetch_source(case: Dict[str, Any], address: str, env: Dict[str, str]) -> Dict[str, Any]:
    api_key_env = case.get("api_key_env")
    api_key = env.get(api_key_env, "") if api_key_env else ""
    params: Dict[str, Any] = {
        "module": "contract",
        "action": "getsourcecode",
        "address": address,
        "apikey": api_key,
    }
    if "/v2/" in case.get("explorer_api", ""):
        params["chainid"] = case["chain_id"]
    return http_json(case["explorer_api"], params)


def collect_sources(case_id: str) -> Dict[str, Any]:
    case = get_case(case_id)
    env = load_env()
    targets = list(case.get("source_targets") or [])
    source_dir = repo_path("cache", "sources", case_id)
    abi_dir = repo_path("cache", "abi", case_id)
    ensure_dir(source_dir)
    ensure_dir(abi_dir)

    manifest: Dict[str, Any] = {
        "case": case_id,
        "chain": case["chain"],
        "targets": targets,
        "collected": [],
        "skipped": [],
    }

    if not targets:
        manifest["skipped"].append(
            {
                "reason": "no source_targets configured",
                "hint": "Add protocol contracts to config/cases.json, or use --fixture in slither_mine.py.",
            }
        )
        write_json(source_dir / "manifest.json", manifest)
        return manifest

    queue = list(dict.fromkeys(targets))
    seen = set()
    while queue:
        address = queue.pop(0)
        if address.lower() in seen:
            continue
        seen.add(address.lower())
        print_status(f"Fetching verified source for {case_id}:{address}")
        payload = fetch_source(case, address, env)
        write_json(source_dir / _source_filename(address), payload)
        results = _extract_result(payload)
        if not results:
            manifest["skipped"].append({"address": address, "reason": "empty result"})
            continue
        result = results[0]
        abi = result.get("ABI")
        if abi and abi != "Contract source code not verified":
            (abi_dir / _abi_filename(address)).write_text(abi + "\n", encoding="utf-8")
        source_files = write_source_files(case_id, address, result, source_dir)
        implementation = (result.get("Implementation") or "").strip()
        if implementation and implementation != "0x0000000000000000000000000000000000000000":
            queue.append(implementation)
        manifest["collected"].append(
            {
                "address": address,
                "contract_name": result.get("ContractName"),
                "compiler": result.get("CompilerVersion"),
                "proxy": result.get("Proxy"),
                "implementation": implementation,
                "source_files": source_files,
            }
        )

    write_json(source_dir / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect verified Solidity sources for a case.")
    parser.add_argument("--case", required=True, help="Case id from config/cases.json")
    args = parser.parse_args()
    try:
        manifest = collect_sources(args.case)
    except PipelineError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Wrote source manifest for {args.case}: {Path('cache') / 'sources' / args.case / 'manifest.json'}")
    if manifest.get("skipped"):
        print("No online source targets were collected; use fixture mode or configure source_targets.")


if __name__ == "__main__":
    main()
