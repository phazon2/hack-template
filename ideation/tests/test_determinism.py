"""Determinism guarantees (DESIGN §17): same input -> same output, across processes and hash seeds."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

from ideate.llm.base import LLMRequest
from ideate.llm.mock import MockLLM
from ideate.llm.schema import arr, obj, str_
from ideate.models import HackathonConstraints
from ideate.pipeline import IdeationSystem

SRC = Path(__file__).resolve().parents[1] / "src"
THEME = "AI for climate resilience"
VOLATILE_TRACE = {"duration_ms": 0, "started_at": ""}


def normalized(data: dict) -> dict:
    """A result dict with run id, timestamps and durations zeroed."""
    d = json.loads(json.dumps(data))
    d["run_id"] = ""
    d["created_at"] = ""
    d["trace"] = [dict(step, **VOLATILE_TRACE) for step in d["trace"]]
    return d


def run_cli(args: list[str], env: dict, cwd: Path, hashseed: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "ideate", *args],
        env={**env, "PYTHONHASHSEED": hashseed},
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )


# --------------------------------------------------------------------------- (a) mock
def test_mock_same_input_identical_and_tag_sensitive():
    schema = obj({"items": arr(str_(), 3, 3)})
    request = LLMRequest(system="s", prompt="climate flood sensors rivers", tag="research", json_schema=schema)
    a = MockLLM(seed=0).complete(request)
    b = MockLLM(seed=0).complete(request)
    assert a.text == b.text and a.data == b.data
    other = MockLLM(seed=0).complete(LLMRequest(system="s", prompt=request.prompt, tag="creativity", json_schema=schema))
    assert other.data != a.data


# --------------------------------------------------------------------------- (b) pipeline in-process
def test_pipeline_twice_in_process_identical(settings):
    constraints = HackathonConstraints(hours=36, tech_preferences=["python"], judging_criteria=["innovation:40", "impact:30", "demo:30"])
    first = IdeationSystem(settings, llm=MockLLM(seed=0)).ideate(THEME, constraints)
    second = IdeationSystem(settings, llm=MockLLM(seed=0)).ideate(THEME, constraints)
    assert first.run_id != second.run_id
    assert normalized(first.to_dict()) == normalized(second.to_dict())
    assert first.queries == second.queries


# --------------------------------------------------------------------------- (c) CLI across hash seeds
def test_cli_run_identical_across_pythonhashseed(cli_env, tmp_path):
    args = ["run", THEME, "--json", "-", "--prefer", "python", "--criteria", "innovation:40,impact:30,demo:30"]
    one = run_cli(args, cli_env, tmp_path, "1")
    two = run_cli(args, cli_env, tmp_path, "4242")
    assert one.returncode == 0, one.stderr
    assert two.returncode == 0, two.stderr
    assert normalized(json.loads(one.stdout)) == normalized(json.loads(two.stdout))


# --------------------------------------------------------------------------- (d) index across processes
def test_index_built_twice_in_separate_processes_is_byte_identical(cli_env, tmp_path):
    dirs = [tmp_path / "index-a", tmp_path / "index-b"]
    for index_dir, seed in zip(dirs, ("1", "4242")):
        proc = run_cli(["index", "--index", str(index_dir)], cli_env, tmp_path, seed)
        assert proc.returncode == 0, proc.stderr
    for name in ("vectors.json", "chunks.json", "bm25.json", "embedder.json"):
        assert (dirs[0] / name).read_bytes() == (dirs[1] / name).read_bytes(), name
    metas = [json.loads((d / "meta.json").read_text()) for d in dirs]
    assert {k: v for k, v in metas[0].items() if k != "built_at"} == {k: v for k, v in metas[1].items() if k != "built_at"}


# --------------------------------------------------------------------------- static guard
def test_no_builtin_hash_calls_in_the_codebase():
    """``hash()`` on str/bytes varies with PYTHONHASHSEED; the codebase must never call it."""
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "hash":
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno}")
    assert offenders == []
