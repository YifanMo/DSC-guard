#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from common import PipelineError, get_case, print_status, read_json, repo_path, write_json


ORACLE_KEYWORDS = (
    "latestRoundData",
    "latestAnswer",
    "getUnderlyingPrice",
    "getPrice",
    "price",
    "oracle",
)
ACTION_KEYWORDS = ("borrow", "liquidate", "mint", "supply", "redeem", "transfer", "pause")
FRESHNESS_KEYWORDS = ("updatedAt", "answeredInRound", "heartbeat", "stale", "block.timestamp")


def _clean_statement(value: str) -> str:
    return " ".join(value.strip().split())


def _iter_sol_files(path: Path) -> List[Path]:
    if path.is_file() and path.suffix == ".sol":
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.sol"))
    return []


def _parse_events(source: str) -> Dict[str, Dict[str, Any]]:
    events: Dict[str, Dict[str, Any]] = {}
    for match in re.finditer(r"event\s+(\w+)\s*\((.*?)\)\s*;", source, flags=re.S):
        args = []
        for raw_arg in match.group(2).split(","):
            raw_arg = raw_arg.strip()
            if not raw_arg:
                continue
            pieces = [piece for piece in raw_arg.split() if piece != "indexed"]
            arg_name = pieces[-1] if pieces else raw_arg
            arg_type = " ".join(pieces[:-1]) if len(pieces) > 1 else ""
            args.append({"name": arg_name, "type": arg_type})
        events[match.group(1)] = {"name": match.group(1), "arguments": args}
    return events


def _find_function_bodies(source: str) -> Iterable[Tuple[str, str, str]]:
    pattern = re.compile(r"function\s+(\w+)\s*\(([^;{}]*)\)[^{;]*\{", flags=re.S)
    for match in pattern.finditer(source):
        name = match.group(1)
        args = match.group(2)
        start = match.end() - 1
        depth = 0
        end = start
        for index in range(start, len(source)):
            char = source[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        yield name, args, source[start:end]


def _statement_list(body: str) -> List[str]:
    statements = []
    for raw in re.split(r";|\n", body):
        stmt = _clean_statement(raw)
        if stmt and stmt not in {"{", "}"}:
            statements.append(stmt)
    return statements


def _lhs_assignments(body: str) -> List[str]:
    writes = []
    for match in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]+\])?)\s*=(?!=)", body):
        writes.append(_clean_statement(match.group(1)))
    return sorted(set(writes))


def _external_calls(body: str) -> List[str]:
    calls = []
    for match in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", body):
        calls.append(f"{match.group(1)}.{match.group(2)}")
    return sorted(set(calls))


def _emits(body: str) -> List[Dict[str, Any]]:
    emits = []
    for match in re.finditer(r"emit\s+(\w+)\s*\((.*?)\)", body, flags=re.S):
        args = [_clean_statement(arg) for arg in match.group(2).split(",") if arg.strip()]
        emits.append({"event": match.group(1), "arguments": args})
    return emits


def _classify_function(name: str, body: str) -> List[str]:
    text = f"{name} {body}".lower()
    tags = []
    if "set" in name.lower() and ("feed" in text or "oracle" in text or "source" in text):
        tags.append("oracle-setter")
    if any(keyword.lower() in text for keyword in ORACLE_KEYWORDS):
        tags.append("oracle-read")
    if any(keyword in text for keyword in ("updatedat", "answeredinround", "heartbeat", "stale")):
        tags.append("freshness-check")
    for keyword in ACTION_KEYWORDS:
        if keyword in text:
            tags.append(keyword)
    return sorted(set(tags))


def heuristic_mine(case_id: str, source_paths: List[Path]) -> Dict[str, Any]:
    contracts = []
    event_semantics = []
    for source_path in source_paths:
        source = source_path.read_text(encoding="utf-8")
        contract_name_match = re.search(r"contract\s+(\w+)", source)
        contract_name = contract_name_match.group(1) if contract_name_match else source_path.stem
        events = _parse_events(source)
        functions = []
        for function_name, raw_args, body in _find_function_bodies(source):
            statements = _statement_list(body)
            emits = _emits(body)
            writes = _lhs_assignments(body)
            external_calls = _external_calls(body)
            freshness = any(keyword in body for keyword in FRESHNESS_KEYWORDS)
            oracle_reads = [
                call
                for call in external_calls
                if any(keyword.lower() in call.lower() for keyword in ORACLE_KEYWORDS)
            ]
            tags = _classify_function(function_name, body)
            pruned_nodes = []
            for statement in statements:
                lower = statement.lower()
                if (
                    "emit " in lower
                    or any(write.lower().split("[")[0] in lower for write in writes)
                    or any(keyword.lower() in lower for keyword in ORACLE_KEYWORDS)
                    or any(keyword.lower() in lower for keyword in FRESHNESS_KEYWORDS)
                ):
                    pruned_nodes.append(statement)
            function_ir = {
                "name": function_name,
                "arguments": _clean_statement(raw_args),
                "tags": tags,
                "event_emits": emits,
                "state_writes": writes,
                "external_calls": external_calls,
                "oracle_reads": oracle_reads,
                "freshness_check": freshness,
                "cfg_nodes": statements,
                "pruned_cfg_nodes": pruned_nodes,
            }
            functions.append(function_ir)
            for emit in emits:
                event_semantics.append(
                    {
                        "contract": contract_name,
                        "function": function_name,
                        "event": emit["event"],
                        "event_arguments": emit["arguments"],
                        "state_writes": writes,
                        "oracle_reads": oracle_reads,
                        "freshness_check": freshness,
                        "transition_tags": tags,
                        "pruned_cfg_nodes": pruned_nodes,
                    }
                )
        contracts.append(
            {
                "name": contract_name,
                "source": str(source_path.relative_to(repo_path())),
                "events": list(events.values()),
                "functions": functions,
            }
        )

    return {
        "case": case_id,
        "backend": "heuristic-fallback",
        "contracts": contracts,
        "event_semantics": event_semantics,
        "warnings": ["Slither was not used for this IR; install slither-analyzer and rerun without --fixture."],
    }


def _safe_names(values: Iterable[Any]) -> List[str]:
    output = []
    for value in values or []:
        name = getattr(value, "name", None)
        output.append(str(name if name is not None else value))
    return sorted(set(output))


def slither_mine(case_id: str, target: Path) -> Dict[str, Any]:
    try:
        from slither.slither import Slither  # type: ignore
    except Exception as exc:
        raise PipelineError(
            "Slither Python package is not installed. Install slither-analyzer or rerun with --fixture."
        ) from exc

    try:
        slither = Slither(str(target))
    except Exception as exc:
        raise PipelineError(f"Slither failed to parse {target}: {exc}") from exc

    contracts = []
    event_semantics = []
    for contract in slither.contracts:
        functions = []
        events = [
            {"name": event.name, "arguments": [str(arg) for arg in getattr(event, "elems", [])]}
            for event in getattr(contract, "events", [])
        ]
        for function in getattr(contract, "functions_declared", []):
            nodes = getattr(function, "nodes", [])
            cfg_nodes = []
            pruned_nodes = []
            event_emits = []
            external_calls = []
            for node in nodes:
                expression = _clean_statement(str(getattr(node, "expression", "") or ""))
                if expression:
                    cfg_nodes.append(expression)
                for ir in getattr(node, "irs", []) or []:
                    ir_text = _clean_statement(str(ir))
                    ir_type = type(ir).__name__
                    if "Event" in ir_type or ir_text.startswith("Emit "):
                        event_name = getattr(ir, "name", None) or ir_text.split("(")[0].replace("Emit", "").strip()
                        args = [str(arg) for arg in getattr(ir, "arguments", []) or []]
                        event_emits.append({"event": str(event_name), "arguments": args})
                    if "HighLevelCall" in ir_type or "." in ir_text:
                        external_calls.append(ir_text)
                if any(keyword.lower() in expression.lower() for keyword in ORACLE_KEYWORDS + FRESHNESS_KEYWORDS):
                    pruned_nodes.append(expression)

            reads = _safe_names(getattr(function, "state_variables_read", []))
            writes = _safe_names(getattr(function, "state_variables_written", []))
            freshness = any(
                keyword.lower() in " ".join(cfg_nodes).lower() for keyword in FRESHNESS_KEYWORDS
            )
            oracle_reads = [
                call
                for call in sorted(set(external_calls))
                if any(keyword.lower() in call.lower() for keyword in ORACLE_KEYWORDS)
            ]
            tags = _classify_function(function.name, " ".join(cfg_nodes))
            for node in cfg_nodes:
                if any(write.lower() in node.lower() for write in writes) and node not in pruned_nodes:
                    pruned_nodes.append(node)
            function_ir = {
                "name": function.name,
                "arguments": ", ".join(str(param) for param in getattr(function, "parameters", []) or []),
                "tags": tags,
                "event_emits": event_emits,
                "state_reads": reads,
                "state_writes": writes,
                "external_calls": sorted(set(external_calls)),
                "oracle_reads": oracle_reads,
                "freshness_check": freshness,
                "cfg_nodes": cfg_nodes,
                "pruned_cfg_nodes": pruned_nodes,
            }
            functions.append(function_ir)
            for emit in event_emits:
                event_semantics.append(
                    {
                        "contract": contract.name,
                        "function": function.name,
                        "event": emit["event"],
                        "event_arguments": emit["arguments"],
                        "state_reads": reads,
                        "state_writes": writes,
                        "oracle_reads": oracle_reads,
                        "freshness_check": freshness,
                        "transition_tags": tags,
                        "pruned_cfg_nodes": pruned_nodes,
                    }
                )
        contracts.append({"name": contract.name, "events": events, "functions": functions})

    return {
        "case": case_id,
        "backend": "slither",
        "target": str(target),
        "contracts": contracts,
        "event_semantics": event_semantics,
        "warnings": [],
    }


def _merge_slither_irs(case_id: str, irs: List[Dict[str, Any]], warnings: List[str]) -> Dict[str, Any]:
    contracts = []
    event_semantics = []
    targets = []
    for ir in irs:
        contracts.extend(ir.get("contracts", []))
        event_semantics.extend(ir.get("event_semantics", []))
        if ir.get("target"):
            targets.append(ir["target"])
    return {
        "case": case_id,
        "backend": "slither",
        "target": targets[0] if len(targets) == 1 else targets,
        "contracts": contracts,
        "event_semantics": event_semantics,
        "warnings": warnings,
    }


def _compile_targets(source_dir: Path, paths: List[Path]) -> List[Path]:
    if len(paths) == 1:
        return [paths[0]]
    targets: List[Path] = []
    seen = set()
    for path in paths:
        try:
            rel = path.relative_to(source_dir)
        except ValueError:
            rel = path
        target = source_dir / rel.parts[0] if len(rel.parts) > 1 else path
        key = str(target)
        if key not in seen:
            seen.add(key)
            targets.append(target)
    return targets


def _compiler_versions_by_address(source_dir: Path) -> Dict[str, str]:
    manifest_path = source_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    manifest = read_json(manifest_path)
    versions: Dict[str, str] = {}
    for item in manifest.get("collected", []):
        address = str(item.get("address") or "").lower()
        compiler = str(item.get("compiler") or "")
        match = re.search(r"v?(\d+\.\d+\.\d+)", compiler)
        if address and match:
            versions[address] = match.group(1)
    return versions


def _compiler_version_for_target(source_dir: Path, target: Path, versions: Dict[str, str]) -> Optional[str]:
    try:
        rel = target.relative_to(source_dir)
    except ValueError:
        return None
    if not rel.parts:
        return None
    return versions.get(rel.parts[0].lower())


def _with_solc_version(version: Optional[str]):
    class _SolcVersionContext:
        def __enter__(self) -> None:
            self.old_version = os.environ.get("SOLC_VERSION")
            self.old_path = os.environ.get("PATH", "")
            if version:
                os.environ["SOLC_VERSION"] = version
                os.environ["PATH"] = f"/opt/anaconda3/bin:{self.old_path}"

        def __exit__(self, exc_type, exc, tb) -> None:
            if self.old_version is None:
                os.environ.pop("SOLC_VERSION", None)
            else:
                os.environ["SOLC_VERSION"] = self.old_version
            os.environ["PATH"] = self.old_path

    return _SolcVersionContext()


def _slither_mine_with_version(case_id: str, target: Path, version: Optional[str]) -> Dict[str, Any]:
    with _with_solc_version(version):
        ir = slither_mine(case_id, target)
    if version:
        ir["solc_version"] = version
    return ir


def slither_mine_many(case_id: str, source_dir: Path, paths: List[Path]) -> Dict[str, Any]:
    successes: List[Dict[str, Any]] = []
    warnings: List[str] = []
    attempted: List[Path] = []
    compiler_versions = _compiler_versions_by_address(source_dir)
    for target in _compile_targets(source_dir, paths):
        version = _compiler_version_for_target(source_dir, target, compiler_versions)
        attempted.append(target)
        try:
            successes.append(_slither_mine_with_version(case_id, target, version))
            continue
        except PipelineError as exc:
            warnings.append(f"Slither failed for {target}: {exc}")
        if target.is_dir():
            for sol_file in sorted(target.rglob("*.sol")):
                version = _compiler_version_for_target(source_dir, sol_file, compiler_versions)
                attempted.append(sol_file)
                try:
                    successes.append(_slither_mine_with_version(case_id, sol_file, version))
                except PipelineError as exc:
                    warnings.append(f"Slither failed for {sol_file}: {exc}")
    if not successes:
        attempted_text = ", ".join(str(item) for item in attempted)
        raise PipelineError(f"Slither failed for all source targets: {attempted_text}")
    return _merge_slither_irs(case_id, successes, warnings)


def source_paths_for_case(case: Dict[str, Any], fixture: bool) -> List[Path]:
    if fixture:
        return _iter_sol_files(repo_path(case["fixture_source"]))
    source_dir = repo_path("cache", "sources", case["id"])
    paths = _iter_sol_files(source_dir)
    if paths:
        return paths
    fixture_path = repo_path(case["fixture_source"])
    print_status(
        f"No Solidity sources found in {source_dir}; using fixture source {fixture_path.relative_to(repo_path())}."
    )
    return _iter_sol_files(fixture_path)


def mine(case_id: str, fixture: bool = False, require_slither: bool = False) -> Dict[str, Any]:
    case = get_case(case_id)
    paths = source_paths_for_case(case, fixture)
    if not paths:
        raise PipelineError(f"No Solidity sources found for case {case_id}.")
    output_path = repo_path("artifacts", "slither_ir", f"{case_id}.json")
    if not fixture:
        try:
            source_dir = repo_path("cache", "sources", case["id"])
            if source_dir.exists() and any(path.is_relative_to(source_dir) for path in paths):
                ir = slither_mine_many(case_id, source_dir, paths)
            else:
                target = paths[0] if len(paths) == 1 else paths[0].parent
                ir = slither_mine(case_id, target)
        except PipelineError:
            if require_slither:
                raise
            ir = heuristic_mine(case_id, paths)
    else:
        ir = heuristic_mine(case_id, paths)
    ir["case_name"] = case["name"]
    write_json(output_path, ir)
    return ir


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine log semantics from Solidity sources.")
    parser.add_argument("--case", required=True)
    parser.add_argument("--fixture", action="store_true", help="Use local fixture sources.")
    parser.add_argument(
        "--require-slither",
        action="store_true",
        help="Fail if Slither is unavailable instead of using heuristic fallback.",
    )
    args = parser.parse_args()
    try:
        ir = mine(args.case, fixture=args.fixture, require_slither=args.require_slither)
    except PipelineError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Wrote semantic IR with backend={ir['backend']}: artifacts/slither_ir/{args.case}.json")


if __name__ == "__main__":
    main()
