#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Any, Dict, List

from common import PipelineError, command_available, get_case, read_json, repo_path, run_command


def _k_comment(value: str) -> str:
    return value.replace("\n", " ")


def _rule_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")
    return cleaned or "anonymous"


def render_k(case: Dict[str, Any], ir: Dict[str, Any]) -> str:
    constraints = case.get("constraints", [])
    semantics = ir.get("event_semantics", [])
    lines: List[str] = []
    lines.append('requires "domains.md"')
    lines.append("")
    lines.append(f"module DSC-GUARD-{case['id'].upper().replace('_', '-')}-SYNTAX")
    lines.append("  imports INT")
    lines.append("  imports STRING")
    lines.append("  imports LIST")
    lines.append("  imports MAP")
    lines.append("")
    lines.append("  syntax Event ::= oracleFeedSet(String, String, String, String)")
    lines.append("                 | oracleAnswer(String, String, Int, Int, Int, Int, String)")
    lines.append("                 | oracleFormulaSet(String, String, String, String)")
    lines.append("                 | supply(String, String, String, String)")
    lines.append("                 | borrow(String, String, String, String, String)")
    lines.append("                 | liquidate(String, String, String, String, String)")
    lines.append("                 | pauseMarket(String, String)")
    lines.append("                 | rawLog(String)")
    lines.append("  syntax Events ::= List")
    lines.append("endmodule")
    lines.append("")
    lines.append(f"module DSC-GUARD-{case['id'].upper().replace('_', '-')}")
    lines.append(f"  imports DSC-GUARD-{case['id'].upper().replace('_', '-')}-SYNTAX")
    lines.append("  imports INT")
    lines.append("  imports STRING")
    lines.append("  imports LIST")
    lines.append("  imports MAP")
    lines.append("")
    lines.append("  configuration")
    lines.append("    <dscGuard>")
    lines.append("      <k> $PGM:Events </k>")
    lines.append("      <block> 0 </block>")
    lines.append('      <tx> "" </tx>')
    lines.append("      <log> .List </log>")
    lines.append("      <oracleMap> .Map </oracleMap>")
    lines.append("      <oracleAnswer> .Map </oracleAnswer>")
    lines.append("      <marketState> .Map </marketState>")
    lines.append("      <balances> .Map </balances>")
    lines.append("      <positions> .Map </positions>")
    lines.append("      <alerts> .List </alerts>")
    lines.append("    </dscGuard>")
    lines.append("")
    lines.append("  // Generic log-driven transition rules.")
    lines.append("  rule <k> ListItem(oracleFeedSet(ASSET, EXPECTED, ACTUAL, TX)) => . ... </k>")
    lines.append("       <tx> _ => TX </tx>")
    lines.append("       <oracleMap> OM => OM [ ASSET <- ACTUAL ] </oracleMap>")
    lines.append('       <alerts> A => A ListItem("feed-mismatch:" +String TX) </alerts>')
    lines.append("    requires EXPECTED =/=String ACTUAL")
    lines.append("")
    lines.append("  rule <k> ListItem(oracleAnswer(ASSET, FEED, ANSWER, UPDATEDAT, ROUNDID, ANSWEREDINROUND, TX)) => . ... </k>")
    lines.append("       <tx> _ => TX </tx>")
    lines.append(
        '       <oracleAnswer> OA => OA [ ASSET <- FEED +String ":" +String Int2String(ANSWER) +String ":" +String Int2String(UPDATEDAT) ] </oracleAnswer>'
    )
    lines.append("       <log> L => L ListItem(TX) </log>")
    lines.append("")
    lines.append("  rule <k> ListItem(oracleFormulaSet(ASSET, EXPECTED, ACTUAL, TX)) => . ... </k>")
    lines.append("       <tx> _ => TX </tx>")
    lines.append('       <alerts> A => A ListItem("formula-mismatch:" +String TX) </alerts>')
    lines.append("    requires EXPECTED =/=String ACTUAL")
    lines.append("")
    lines.append("  rule <k> ListItem(supply(ACCOUNT, ASSET, AMOUNT, TX)) => . ... </k>")
    lines.append("       <tx> _ => TX </tx>")
    lines.append("       <positions> P => P [ ACCOUNT +String \":supply:\" +String ASSET <- AMOUNT ] </positions>")
    lines.append("")
    lines.append("  rule <k> ListItem(borrow(ACCOUNT, COLLATERAL, BORROWASSET, AMOUNT, TX)) => . ... </k>")
    lines.append("       <tx> _ => TX </tx>")
    lines.append("       <positions> P => P [ ACCOUNT +String \":borrow:\" +String BORROWASSET <- AMOUNT ] </positions>")
    lines.append("")
    lines.append("  rule <k> ListItem(liquidate(LIQUIDATOR, BORROWER, COLLATERAL, AMOUNT, TX)) => . ... </k>")
    lines.append("       <tx> _ => TX </tx>")
    lines.append("       <positions> P => P [ LIQUIDATOR +String \":liquidate:\" +String COLLATERAL <- AMOUNT ] </positions>")
    lines.append("")
    lines.append("  rule <k> ListItem(pauseMarket(ASSET, TX)) => . ... </k>")
    lines.append("       <tx> _ => TX </tx>")
    lines.append('       <marketState> M => M [ ASSET <- "paused" ] </marketState>')
    lines.append("")
    lines.append("  // Case constraints embedded for auditability.")
    for constraint in constraints:
        lines.append(
            f"  // constraint {_k_comment(constraint['id'])}: type={constraint['type']} severity={constraint.get('severity', 'unknown')}"
        )
    lines.append("")
    lines.append("  // Slither-mined event semantics.")
    for semantic in semantics:
        lines.append(
            "  // "
            + _rule_name(f"{semantic.get('contract')}-{semantic.get('function')}-{semantic.get('event')}")
            + ": "
            + _k_comment(", ".join(semantic.get("transition_tags", [])))
        )
        for node in semantic.get("pruned_cfg_nodes", [])[:5]:
            lines.append(f"  //   cfg: {_k_comment(node)}")
    lines.append("endmodule")
    lines.append("")
    return "\n".join(lines)


def _module_name(case_id: str) -> str:
    return f"DSC-GUARD-{case_id.upper().replace('_', '-')}"


def _syntax_module_name(case_id: str) -> str:
    return f"{_module_name(case_id)}-SYNTAX"


def _k_env() -> Dict[str, str]:
    env = dict(os.environ)
    homebrew_java = Path("/opt/homebrew/opt/openjdk")
    if homebrew_java.exists() and not env.get("JAVA_HOME"):
        env["JAVA_HOME"] = str(homebrew_java)
    java_bin = homebrew_java / "bin"
    if java_bin.exists():
        env["PATH"] = f"{java_bin}:{env.get('PATH', '')}"
    return env


def generate(case_id: str, kompile: bool = False) -> str:
    case = get_case(case_id)
    ir_path = repo_path("artifacts", "slither_ir", f"{case_id}.json")
    if not ir_path.exists():
        raise PipelineError(f"Missing semantic IR: {ir_path}. Run scripts/slither_mine.py first.")
    ir = read_json(ir_path)
    text = render_k(case, ir)
    output_path = repo_path("artifacts", "k", f"{case_id}.k")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    if kompile:
        if not command_available("kompile"):
            raise PipelineError("K Framework 'kompile' command was not found.")
        result = run_command(
            [
                "kompile",
                output_path.name,
                "--main-module",
                _module_name(case_id),
                "--syntax-module",
                _syntax_module_name(case_id),
            ],
            cwd=output_path.parent,
            env=_k_env(),
        )
        if result.returncode != 0:
            raise PipelineError(
                "kompile failed:\nSTDOUT:\n"
                + result.stdout
                + "\nSTDERR:\n"
                + result.stderr
            )
    return str(output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate K semantics from mined log semantics.")
    parser.add_argument("--case", required=True)
    parser.add_argument("--kompile", action="store_true", help="Run K Framework kompile after generation.")
    args = parser.parse_args()
    try:
        output = generate(args.case, kompile=args.kompile)
    except PipelineError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Wrote K module: {output}")


if __name__ == "__main__":
    main()
