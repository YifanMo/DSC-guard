#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from common import PipelineError, ensure_dir, repo_path, write_json
from ingest_broad_search_results import ingest
from materialize_broad_queue import run_queue
from run_broad_dune_queries import build_shards, parse_chains, run_shards


DEFAULT_START = "2022-01-01"
DEFAULT_END = "2026-05-12"
DEFAULT_RULE = "freshness_handling_failure"


def _date_key(value: str) -> str:
    return value.replace("-", "")


def _experiment_dir(output_root: Path, chain_label: str, start: str, end: str) -> Path:
    safe_chain = chain_label.replace(",", "_").replace("_c", "")
    start_key = start[:4] if start.endswith("-01-01") else _date_key(start)
    return output_root / f"{safe_chain}_{start_key}_{_date_key(end)}"


def _rule_list(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _dune_dir(base_dir: Path, rules: List[str]) -> Path:
    if rules == [DEFAULT_RULE]:
        return base_dir / "dune_r3"
    return base_dir / "dune"


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _summarize_dune_dir(dune_output_dir: Path) -> Dict[str, Any]:
    shard_manifests = [_load_json(path) for path in sorted(dune_output_dir.glob("*/manifest.json"))]
    shard_manifests = [item for item in shard_manifests if item]
    return {
        "shard_count": len(shard_manifests),
        "completed_count": sum(1 for item in shard_manifests if item.get("status") == "completed"),
        "submitted_count": sum(1 for item in shard_manifests if item.get("status") in {"submitted", "resumed"}),
        "failed_count": sum(1 for item in shard_manifests if item.get("status") == "failed"),
        "cancelled_count": sum(1 for item in shard_manifests if item.get("status") == "cancelled"),
        "row_count": sum(int(item.get("row_count") or 0) for item in shard_manifests),
        "observed_credits": round(sum(float(item.get("execution_cost_credits") or 0) for item in shard_manifests), 6),
        "shards": [
            {
                "shard_id": item.get("shard_id", ""),
                "status": item.get("status", ""),
                "state": item.get("state", ""),
                "credits": item.get("execution_cost_credits"),
                "rows": item.get("row_count"),
                "execution_id": item.get("execution_id", ""),
            }
            for item in shard_manifests
        ],
    }


def _write_report(base_dir: Path, manifest: Dict[str, Any], dune_output_dir: Path, index_dir: Path, materialization_dir: Path) -> None:
    dune_summary = _summarize_dune_dir(dune_output_dir)
    candidate_summary = _load_json(index_dir / "candidate_summary.json")
    materialization = _load_json(materialization_dir / "materialization_dry_run.json")
    lines = [
        "# Single-Chain Broad Search Experiment",
        "",
        f"- Chain: `{manifest['chain_label']}` / Dune `{', '.join(manifest['dune_chains'])}`",
        f"- Time range: `{manifest['start']}` to `{manifest['end']}`",
        f"- Rules: `{', '.join(manifest['rules'])}`",
        f"- Output dir: `{manifest['output_dir']}`",
        "",
        "## Dune Remote Index Run",
        "",
        f"- Shard manifests observed: `{dune_summary['shard_count']}`",
        f"- Completed shards: `{dune_summary['completed_count']}`",
        f"- Submitted or stale-local shards: `{dune_summary['submitted_count']}`",
        f"- Failed shards: `{dune_summary['failed_count']}`",
        f"- Cancelled shards: `{dune_summary['cancelled_count']}`",
        f"- Candidate rows returned by completed local exports: `{dune_summary['row_count']}`",
        f"- Observed completed-shard Dune credits: `{dune_summary['observed_credits']}`",
        "",
        "| shard_id | status | state | credits | rows | execution_id |",
        "|---|---|---|---:|---:|---|",
    ]
    for shard in dune_summary["shards"]:
        lines.append(
            f"| {shard['shard_id']} | {shard['status']} | {shard['state']} | {shard['credits'] or ''} | {shard['rows'] if shard['rows'] is not None else ''} | {shard['execution_id']} |"
        )
    lines.extend(
        [
            "",
            "## Local Ingest And Queue",
            "",
            f"- Candidate count: `{candidate_summary.get('candidate_count', 'not_run')}`",
            f"- Materialization queue count: `{candidate_summary.get('materialization_queue_count', 'not_run')}`",
            f"- Estimated queue RPC requests: `{candidate_summary.get('estimated_queue_rpc_requests', 'not_run')}`",
            f"- Materialization dry-run mode: `{materialization.get('mode', 'not_run')}`",
            f"- Selected for download: `{materialization.get('selected_for_download_count', 'not_run')}`",
            "",
            "## Safety Boundary",
            "",
            "- Historical index queries and receipt planning only.",
            "- No chain writes, private keys, write-method calls, or attack simulation.",
            "- Empty candidate results are preserved as experiment evidence rather than converted into local receipt downloads.",
            "",
        ]
    )
    (base_dir / "single_chain_experiment_report.md").write_text("\n".join(lines), encoding="utf-8")


def run_single_chain_experiment(
    *,
    chain: str,
    dune_chain: str,
    start: str,
    end: str,
    rules: List[str],
    output_root: Path,
    dry_run: bool,
    execute_dune: bool,
    ingest_results: bool,
    materialize_dry_run: bool,
    split_by: str,
    performance: str,
    resume: bool,
    stop_on_cancel: bool,
    max_execution_credits: float,
    max_total_credits: float,
    max_per_class: int,
    candidate_limit: int,
    max_shards: int | None,
    page_size: int,
    poll_interval: int,
    timeout_seconds: int,
) -> Dict[str, Any]:
    base_dir = _experiment_dir(output_root, chain, start, end)
    ensure_dir(base_dir)
    parsed_chains = parse_chains([dune_chain])
    shards = build_shards(start, end, parsed_chains, split_by, rules)
    dune_output_dir = _dune_dir(base_dir, rules)
    index_dir = base_dir / "local_index"
    materialization_dir = base_dir / "materialization"
    manifest: Dict[str, Any] = {
        "experiment": "single_chain_broad_search",
        "scope": "read-only historical index search and bounded evidence-slice planning",
        "chain_label": chain,
        "dune_chains": parsed_chains,
        "start": start,
        "end": end,
        "rules": rules,
        "split_by": split_by,
        "output_dir": str(base_dir),
        "safety": {
            "no_write_calls": True,
            "no_private_keys": True,
            "no_attack_simulation": True,
            "historical_read_only": True,
        },
        "steps": [],
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }

    if dry_run:
        result = run_shards(
            shards,
            output_dir=dune_output_dir,
            performance=performance,
            resume=False,
            dry_run=True,
            page_size=page_size,
            poll_interval=poll_interval,
            timeout_seconds=timeout_seconds,
            max_shards=max_shards,
            max_execution_credits=max_execution_credits,
            max_total_credits=max_total_credits,
            stop_on_cancel=stop_on_cancel,
        )
        manifest["steps"].append({"name": "dune_dry_run", "result": result})
        write_json(base_dir / "single_chain_experiment_manifest.json", manifest)

    if execute_dune:
        result = run_shards(
            shards,
            output_dir=dune_output_dir,
            performance=performance,
            resume=resume,
            dry_run=False,
            page_size=page_size,
            poll_interval=poll_interval,
            timeout_seconds=timeout_seconds,
            max_shards=max_shards,
            max_execution_credits=max_execution_credits,
            max_total_credits=max_total_credits,
            stop_on_cancel=stop_on_cancel,
        )
        manifest["steps"].append({"name": "dune_execute", "result": result})
        write_json(base_dir / "single_chain_experiment_manifest.json", manifest)

    if ingest_results:
        outputs = ingest(dune_output_dir, max_per_class=max_per_class, output_dir=index_dir, allow_empty=True)
        manifest["steps"].append({"name": "ingest", "outputs": {key: str(path) for key, path in outputs.items()}})
        write_json(base_dir / "single_chain_experiment_manifest.json", manifest)

    if materialize_dry_run:
        queue_path = index_dir / "materialization_queue.jsonl"
        result = run_queue(
            queue_path,
            dry_run=True,
            allow_rpc_fill=False,
            candidate_limit=candidate_limit,
            output_dir=materialization_dir,
        )
        manifest["steps"].append({"name": "materialize_dry_run", "result": result})
        write_json(base_dir / "single_chain_experiment_manifest.json", manifest)

    write_json(base_dir / "single_chain_experiment_manifest.json", manifest)
    _write_report(base_dir, manifest, dune_output_dir, index_dir, materialization_dir)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a single-chain broad-search experiment workflow.")
    parser.add_argument("--chain", default="avalanche", help="Human-readable chain label for output paths.")
    parser.add_argument("--dune-chain", default="avalanche", help="Chain name passed through the Dune chain alias parser.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--rules", default=DEFAULT_RULE)
    parser.add_argument("--split-by", default="month,chain,rule")
    parser.add_argument("--performance", choices=["small", "medium", "large"], default="medium")
    parser.add_argument("--output-root", default=str(repo_path("artifacts", "broad_search", "single_chain")))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute-dune", action="store_true")
    parser.add_argument("--ingest", action="store_true")
    parser.add_argument("--materialize-dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.add_argument("--stop-on-cancel", action="store_true", default=True)
    parser.add_argument("--continue-after-cancel", dest="stop_on_cancel", action="store_false")
    parser.add_argument("--max-execution-credits", type=float, default=20.0)
    parser.add_argument("--max-total-credits", type=float, default=250.0)
    parser.add_argument("--max-per-class", type=int, default=1_000_000)
    parser.add_argument("--candidate-limit", type=int, default=1_000_000)
    parser.add_argument("--max-shards", type=int, default=None)
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--poll-interval", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    args = parser.parse_args()

    if not any([args.dry_run, args.execute_dune, args.ingest, args.materialize_dry_run]):
        args.dry_run = True

    try:
        result = run_single_chain_experiment(
            chain=args.chain,
            dune_chain=args.dune_chain,
            start=args.start,
            end=args.end,
            rules=_rule_list(args.rules),
            output_root=Path(args.output_root),
            dry_run=args.dry_run,
            execute_dune=args.execute_dune,
            ingest_results=args.ingest,
            materialize_dry_run=args.materialize_dry_run,
            split_by=args.split_by,
            performance=args.performance,
            resume=args.resume,
            stop_on_cancel=args.stop_on_cancel,
            max_execution_credits=args.max_execution_credits,
            max_total_credits=args.max_total_credits,
            max_per_class=args.max_per_class,
            candidate_limit=args.candidate_limit,
            max_shards=args.max_shards,
            page_size=args.page_size,
            poll_interval=args.poll_interval,
            timeout_seconds=args.timeout_seconds,
        )
    except PipelineError as exc:
        raise SystemExit(str(exc)) from exc

    print("Single-chain broad-search experiment summary:")
    print(f"- chain: {result['chain_label']}")
    print(f"- dune chains: {', '.join(result['dune_chains'])}")
    print(f"- rules: {', '.join(result['rules'])}")
    print(f"- steps: {len(result['steps'])}")
    print(f"- output: {result['output_dir']}")


if __name__ == "__main__":
    main()
