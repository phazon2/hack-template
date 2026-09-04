"""CLI behaviour through subprocesses (DESIGN §13, §17); stdout carries only report/JSON."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ideate.cli import main
from ideate.report import PLACEHOLDER_BANNER

THEME = "AI for climate resilience"
BANNER_LINE = f"> **{PLACEHOLDER_BANNER}**"


def run_cli(args: list[str], env: dict, cwd: Path, **extra_env: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "ideate", *args],
        env={**env, **extra_env},
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )


def run_dirs(env: dict) -> list[Path]:
    runs = Path(env["IDEATE_RUNS_DIR"])
    return sorted(p for p in runs.iterdir() if p.is_dir()) if runs.exists() else []


# --------------------------------------------------------------------------- run
def test_run_json_stdout_carries_only_json_and_always_writes_run_dir(cli_env, tmp_path):
    proc = run_cli(["run", THEME, "--json", "-", "--hours", "36", "--team", "4", "--prefer", "python,fastapi"], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["placeholder_notice"] == PLACEHOLDER_BANNER and data["is_placeholder"] is True
    assert data["constraints"]["hours"] == 36 and data["constraints"]["tech_preferences"] == ["python", "fastapi"]
    assert data["proposal"]["idea_id"] == data["ranking"][0]
    assert "ideate: provider=mock model=mock-1" in proc.stderr
    assert PLACEHOLDER_BANNER in proc.stderr
    dirs = run_dirs(cli_env)
    assert len(dirs) == 1 and dirs[0].name == data["run_id"]
    assert sorted(p.name for p in dirs[0].iterdir()) == ["report.md", "result.json"]
    assert json.loads((dirs[0] / "result.json").read_text())["run_id"] == data["run_id"]


def test_run_out_writes_markdown_starting_with_banner(cli_env, tmp_path):
    out = tmp_path / "report.md"
    proc = run_cli(["run", THEME, "--out", str(out), "--criteria", "innovation:40,impact:30,demo:30", "--avoid", "blockchain"], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""
    text = out.read_text()
    assert text.splitlines()[0] == BANNER_LINE and text.splitlines()[1] == ""
    assert "## 6. All ideas" in text
    assert f"written {out}" in proc.stderr
    assert len(run_dirs(cli_env)) == 1


def test_run_prints_markdown_to_stdout_by_default(cli_env, tmp_path):
    notes = tmp_path / "event.md"
    notes.write_text("Sponsor track: open data\n")
    proc = run_cli(["run", THEME, "--notes-file", str(notes), "--ideas", "4", "--tracks", "open data,health"], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines()[0] == BANNER_LINE
    result = json.loads((run_dirs(cli_env)[0] / "result.json").read_text())
    assert result["constraints"]["notes"] == "Sponsor track: open data"
    assert result["constraints"]["tracks"] == ["open data", "health"]
    assert result["settings"]["ideas_per_round"] == 4
    assert len(result["ideas"]) == 4 * result["iterations"]


# --------------------------------------------------------------------------- judge
def test_judge_accepts_title_description_items(cli_env, tmp_path):
    ideas = tmp_path / "ideas.json"
    ideas.write_text(json.dumps([{"title": "Flood alert bot", "description": "warns farmers"}, {"title": "Heat map", "description": "maps heat islands"}]))
    proc = run_cli(["judge", str(ideas), "--theme", "climate", "--criteria", "innovation,impact", "--json", "-"], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert sorted(data["ranking"]) == ["idea-0-1", "idea-0-2"]
    assert [i["id"] for i in data["ideas"]] == ["idea-0-1", "idea-0-2"]
    assert {v["idea_id"] for v in data["verdicts"]} == {"idea-0-1", "idea-0-2"}
    names = [s["name"] for s in data["verdicts"][0]["consensus"]["scores"]]
    assert names == ["novelty", "impact", "feasibility"]
    assert data["placeholder_notice"] == PLACEHOLDER_BANNER
    assert PLACEHOLDER_BANNER in proc.stderr


def test_judge_markdown_by_default_and_json_file(cli_env, tmp_path):
    ideas = tmp_path / "ideas.json"
    ideas.write_text(json.dumps([{"title": "Only idea", "description": "d"}]))
    proc = run_cli(["judge", str(ideas), "--theme", "climate"], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines()[0] == BANNER_LINE and "| 1 | Only idea (idea-0-1) |" in proc.stdout
    out = tmp_path / "verdicts.json"
    proc = run_cli(["judge", str(ideas), "--theme", "climate", "--json", str(out)], cli_env, tmp_path)
    assert proc.returncode == 0 and proc.stdout == ""
    assert json.loads(out.read_text())["ranking"] == ["idea-0-1"]


def test_judge_rejects_items_without_title(cli_env, tmp_path):
    ideas = tmp_path / "ideas.json"
    ideas.write_text(json.dumps([{"description": "no title"}]))
    proc = run_cli(["judge", str(ideas), "--theme", "climate"], cli_env, tmp_path)
    assert proc.returncode == 1 and proc.stderr.startswith("error: ") and "item 1" in proc.stderr


# --------------------------------------------------------------------------- learn + memory
def test_learn_and_memory_round_trip_with_mock_mark(cli_env, tmp_path):
    outcome = tmp_path / "outcome.json"
    outcome.write_text(json.dumps({"hackathon": "ClimateHack", "idea_title": "Flood alert bot", "success": True, "placed": "2nd"}))
    proc = run_cli(["learn", str(outcome)], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "provider is mock: patterns saved with provider=mock and ignored by real runs" in proc.stderr
    patterns = json.loads(proc.stdout)
    assert patterns and all(p["provider"] == "mock" and "ClimateHack" in p["tags"] for p in patterns)

    proc = run_cli(["memory"], cli_env, tmp_path)
    assert proc.returncode == 0 and proc.stdout == "" and "no patterns" in proc.stderr

    proc = run_cli(["memory", "--include-mock"], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.splitlines()
    assert len(lines) == len(patterns)
    assert all(line.startswith("[mock] pat-") for line in lines)
    assert all(p["id"] in proc.stdout for p in patterns)

    proc = run_cli(["memory", "--include-mock", "--kind", "success"], cli_env, tmp_path)
    assert all("  success  " in line for line in proc.stdout.splitlines())
    assert len(proc.stdout.splitlines()) == sum(p["kind"] == "success" for p in patterns)


def test_learn_prefills_from_saved_run(cli_env, tmp_path):
    proc = run_cli(["run", THEME, "--json", "-"], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    top = next(i for i in result["ideas"] if i["id"] == result["ranking"][0])
    outcome = tmp_path / "outcome.json"
    outcome.write_text(json.dumps({"hackathon": "ClimateHack", "judge_feedback": "great demo"}))
    proc = run_cli(["learn", str(outcome), "--run", result["run_id"]], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    records = [json.loads(line) for line in Path(cli_env["IDEATE_MEMORY_PATH"]).read_text().splitlines()]
    outcomes = [r for r in records if r["type"] == "outcome"]
    assert len(outcomes) == 1
    assert outcomes[0]["run_id"] == result["run_id"] and outcomes[0]["idea_id"] == top["id"]
    assert outcomes[0]["idea_title"] == top["title"] and outcomes[0]["idea_summary"] == top["one_liner"]
    assert outcomes[0]["hackathon"] == "ClimateHack" and outcomes[0]["recorded_at"]

    proc = run_cli(["learn", str(outcome), "--run", result["run_id"], "--idea", "idea-9-9"], cli_env, tmp_path)
    assert proc.returncode == 1 and "idea-9-9" in proc.stderr


def test_learn_requires_hackathon_and_title(cli_env, tmp_path):
    outcome = tmp_path / "outcome.json"
    outcome.write_text(json.dumps({"notes": "nothing else"}))
    proc = run_cli(["learn", str(outcome)], cli_env, tmp_path)
    assert proc.returncode == 1 and "'hackathon' is required" in proc.stderr
    proc = run_cli(["learn", str(outcome), "--idea", "idea-1-1"], cli_env, tmp_path)
    assert proc.returncode == 1 and "--idea requires --run" in proc.stderr
    proc = run_cli(["learn", str(outcome), "--run", "nope"], cli_env, tmp_path)
    assert proc.returncode == 1 and "run 'nope' not found" in proc.stderr


# --------------------------------------------------------------------------- probe
def test_probe_under_mock_exits_2_and_writes_nothing(cli_env, tmp_path):
    proc = run_cli(["probe"], cli_env, tmp_path)
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert "blocker (config-fixable): probe requires a real provider; current provider is mock" in proc.stderr
    assert "  fix: set IDEATE_PROVIDER=anthropic and credentials" in proc.stderr
    assert not Path(cli_env["IDEATE_RECEIPTS_DIR"]).exists()
    assert not Path(cli_env["IDEATE_INDEX_DIR"]).exists()


# --------------------------------------------------------------------------- index
def test_index_prints_stats_to_stderr_only(cli_env, tmp_path):
    proc = run_cli(["index"], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""
    assert "index rebuilt" in proc.stderr and "12 docs" in proc.stderr
    assert (Path(cli_env["IDEATE_INDEX_DIR"]) / "vectors.json").exists()
    proc = run_cli(["index"], cli_env, tmp_path)
    assert proc.returncode == 0 and "index rebuilt" not in proc.stderr and "12 docs" in proc.stderr
    proc = run_cli(["index", "--force"], cli_env, tmp_path)
    assert proc.returncode == 0 and "index rebuilt" in proc.stderr


def test_index_warns_on_empty_corpus(cli_env, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    proc = run_cli(["index", "--no-bundled-corpus", "--corpus", str(empty), "--index", str(tmp_path / "idx2")], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "0 documents loaded" in proc.stderr
    assert (tmp_path / "idx2" / "meta.json").exists()


# --------------------------------------------------------------------------- errors / exit codes
def test_missing_input_file_exits_1(cli_env, tmp_path):
    proc = run_cli(["learn", str(tmp_path / "missing.json")], cli_env, tmp_path)
    assert proc.returncode == 1 and proc.stderr.startswith("error: ")


def test_invalid_setting_is_a_config_blocker(cli_env, tmp_path):
    proc = run_cli(["memory"], cli_env, tmp_path, IDEATE_EFFORT="bogus")
    assert proc.returncode == 2
    assert proc.stderr.startswith("blocker (config-fixable): effort must be")


def test_unknown_subcommand_is_a_usage_error(cli_env, tmp_path):
    proc = run_cli(["frobnicate"], cli_env, tmp_path)
    assert proc.returncode == 2 and "invalid choice" in proc.stderr


def test_main_in_process(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("IDEATE_PROVIDER", "mock")
    monkeypatch.setenv("IDEATE_MEMORY_PATH", str(tmp_path / "memory.jsonl"))
    assert main(["memory"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "" and "no patterns" in captured.err
    with pytest.raises(SystemExit):
        main(["--version"])
    assert capsys.readouterr().out.startswith("ideate 0.1.0")


@pytest.mark.skipif(os.name != "posix", reason="path handling is posix-specific here")
def test_run_dir_is_created_under_runs_dir_from_env(cli_env, tmp_path):
    proc = run_cli(["run", THEME, "--json", str(tmp_path / "nested" / "result.json")], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "nested" / "result.json").exists()
    assert run_dirs(cli_env)[0].parent == Path(cli_env["IDEATE_RUNS_DIR"])


# --------------------------------------------------------------------------- probe without credentials (in-process, no network)
class _NoCredentialsClient:
    """Fake SDK client whose request build raises the SDK's missing-credentials TypeError (no I/O ever happens)."""

    def __init__(self) -> None:
        from types import SimpleNamespace

        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        raise TypeError('"Could not resolve authentication method. Expected one of api_key, auth_token, or credentials to be set."')


def test_probe_without_credentials_is_a_do_it_myself_blocker(tmp_path, monkeypatch, capsys):
    pytest.importorskip("anthropic", reason="anthropic SDK not installed")
    import ideate.pipeline as pipeline
    from ideate.llm.anthropic_provider import CREDENTIALS_HINT, AnthropicLLM

    monkeypatch.setenv("IDEATE_RECEIPTS_DIR", str(tmp_path / "receipts"))
    monkeypatch.setattr(pipeline, "make_llm", lambda settings: AnthropicLLM(settings.model, client=_NoCredentialsClient()))
    assert main(["probe", "--provider", "anthropic"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    lines = captured.err.splitlines()
    assert lines[-2] == "blocker (do-it-myself): no Anthropic credentials found: the SDK could not resolve an authentication method"
    assert lines[-1] == f"  fix: {CREDENTIALS_HINT}"
    assert not (tmp_path / "receipts").exists()
