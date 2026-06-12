from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]


class PipelineError(RuntimeError):
    """Raised for expected pipeline failures with actionable messages."""


def repo_path(*parts: str) -> Path:
    return REPO_ROOT.joinpath(*parts)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_env(path: Optional[Path] = None) -> Dict[str, str]:
    env_path = path or repo_path(".env")
    values: Dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    values.update({k: v for k, v in os.environ.items() if k not in values})
    return values


def load_cases() -> Dict[str, Dict[str, Any]]:
    return read_json(repo_path("config", "cases.json"))


def get_case(case_id: str) -> Dict[str, Any]:
    cases = load_cases()
    if case_id not in cases:
        available = ", ".join(sorted(cases))
        raise PipelineError(f"Unknown case '{case_id}'. Available cases: {available}")
    case = dict(cases[case_id])
    case["id"] = case_id
    return case


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise PipelineError(f"Missing JSONL file: {path}")
    records: List[Dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise PipelineError(f"Invalid JSONL at {path}:{lineno}: {exc}") from exc
    return records


def write_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def command_available(name: str) -> bool:
    return shutil.which(name) is not None


def run_command(
    args: List[str],
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd or REPO_ROOT),
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def http_json(url: str, params: Dict[str, Any], timeout: int = 30) -> Any:
    clean_params = {k: v for k, v in params.items() if v is not None}
    encoded = urllib.parse.urlencode(clean_params)
    request_url = f"{url}?{encoded}" if encoded else url
    request = urllib.request.Request(request_url, headers={"User-Agent": "dsc-guard-mvp/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def rpc_call(url: str, method: str, params: List[Any], timeout: int = 30) -> Any:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(
        "utf-8"
    )
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "dsc-guard-mvp/0.1"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "error" in payload:
        raise PipelineError(f"RPC error from {method}: {payload['error']}")
    return payload.get("result")


def resolve_template(template: str, env: Dict[str, str]) -> str:
    try:
        return template.format(**env)
    except KeyError as exc:
        missing = exc.args[0]
        raise PipelineError(f"Missing environment key required by template: {missing}") from exc


def short_id(value: str, chars: int = 10) -> str:
    if not value:
        return ""
    if len(value) <= chars * 2:
        return value
    return f"{value[:chars]}...{value[-chars:]}"


def normalize_symbol(value: str) -> str:
    return value.strip().lower().replace(" ", "")


def print_status(message: str) -> None:
    print(message, file=sys.stderr)
