#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from common import PipelineError, repo_path


CASES = ["ploutos", "moonwell_cbeth", "moonwell_wrseth", "blueberry_faulty_oracle", "venus_luna", "blizz_luna"]


def _run(args: List[str]) -> None:
    completed = subprocess.run(
        [sys.executable, *args],
        cwd=str(repo_path()),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    if completed.returncode != 0:
        raise PipelineError(f"Command failed: {' '.join(args)}")


def _moonwell_has_receipt_backed_evidence() -> bool:
    raw_path = repo_path("artifacts", "moonwell_cbeth_locator", "raw_evidence.json")
    if not raw_path.exists():
        return False
    import json

    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    txs = raw.get("transactions") or {}
    return raw.get("mode") == "rpc" and bool(txs)


def verify_existing() -> None:
    for case_id in CASES:
        _run(["scripts/verify_trace.py", "--case", case_id])
    for case_id in ("ploutos",):
        _run(["scripts/estimate_feed_binding_loss.py", "--case", case_id])
    _run(["scripts/build_incident_tables.py"])
    _run(["scripts/render_seed_candidates.py"])
    _run(["scripts/audit_dataset_evidence.py"])
    _run(["scripts/render_paper_tables.py"])
    _run(["scripts/render_benign_stratified_report.py"])


def rebuild_offline() -> None:
    _run(["scripts/materialize_feed_binding_case.py", "--case", "ploutos", "--offline"])
    _run(["scripts/materialize_moonwell_wrseth.py", "--offline"])
    _run(["scripts/materialize_blueberry_faulty_oracle.py", "--offline"])
    _run(["scripts/materialize_venus_luna.py", "--end", "2022-05-13T12:00:00Z", "--offline"])
    _run(["scripts/materialize_pre_attack_logs.py", "--case", "all", "--offline"])
    if _moonwell_has_receipt_backed_evidence():
        print("Skipping Moonwell offline materialization to preserve receipt-backed evidence.")
    else:
        _run(["scripts/materialize_moonwell_cbeth.py", "--offline"])
    verify_existing()


def rebuild_rpc(case_id: Optional[str], max_rpc_requests: int) -> None:
    if case_id == "moonwell_cbeth":
        _run(
            [
                "scripts/materialize_moonwell_cbeth.py",
                "--allow-rpc-fill",
                "--max-rpc-requests",
                str(max_rpc_requests),
            ]
        )
        _run(["scripts/materialize_pre_attack_logs.py", "--case", "moonwell_cbeth", "--allow-rpc-fill", "--max-rpc-requests", str(max_rpc_requests)])
    elif case_id == "blueberry_faulty_oracle":
        _run(
            [
                "scripts/materialize_blueberry_faulty_oracle.py",
                "--allow-rpc-fill",
                "--max-rpc-requests",
                str(max_rpc_requests),
            ]
        )
        _run(["scripts/materialize_pre_attack_logs.py", "--case", "blueberry_faulty_oracle", "--allow-rpc-fill", "--max-rpc-requests", str(max_rpc_requests)])
    elif case_id in CASES:
        _run(["scripts/materialize_pre_attack_logs.py", "--case", case_id, "--allow-rpc-fill", "--max-rpc-requests", str(max_rpc_requests)])
    elif case_id in (None, "all"):
        _run(["scripts/materialize_pre_attack_logs.py", "--case", "all", "--allow-rpc-fill", "--max-rpc-requests", str(max_rpc_requests)])
    else:
        raise PipelineError("RPC rebuild requires --case all or one active case.")
    verify_existing()


def main() -> None:
    parser = argparse.ArgumentParser(description="Reproduce local DSC-Guard MVP evidence artifacts.")
    parser.add_argument(
        "--mode",
        choices=["verify", "rebuild-offline", "rebuild-rpc"],
        default="verify",
        help="Default verify mode does not run materializers or RPC.",
    )
    parser.add_argument("--case", choices=["all"] + CASES, default="", help="Required only for rebuild-rpc.")
    parser.add_argument("--max-rpc-requests", type=int, default=80)
    args = parser.parse_args()

    try:
        if args.mode == "verify":
            verify_existing()
        elif args.mode == "rebuild-offline":
            rebuild_offline()
        elif args.mode == "rebuild-rpc":
            rebuild_rpc(args.case or None, args.max_rpc_requests)
    except PipelineError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
