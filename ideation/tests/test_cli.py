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
    assert "index rebuilt" in proc.stderr and "20 docs" in proc.stderr
    assert (Path(cli_env["IDEATE_INDEX_DIR"]) / "vectors.json").exists()
    proc = run_cli(["index"], cli_env, tmp_path)
    assert proc.returncode == 0 and "index rebuilt" not in proc.stderr and "20 docs" in proc.stderr
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


# --------------------------------------------------------------------------- meta layer (DESIGN-META §18.6)
RULES_TEXT = (
    "# Team operating rules\n\n"
    "Ship a public URL before hour nine of the hackathon. Never drive a signup, 2FA or SSO flow: "
    "the human creates every account in five minutes on a phone.\n\n"
    "Mock output is never evidence. A receipt only counts when a real probe produced it.\n"
)
RULES_THEME = "public URL deploy rules and account signup for a hackathon team"


def write_rules(tmp_path: Path, text: str = RULES_TEXT) -> Path:
    path = tmp_path / "CLAUDE.md"
    path.write_text(text, encoding="utf-8")
    return path


def meta_records(env: dict) -> list[dict]:
    path = Path(env["IDEATE_META_PATH"])
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def test_ingest_then_meta_sources_then_a_run_retrieves_it(cli_env, tmp_path):
    rules = write_rules(tmp_path)
    proc = run_cli(["ingest", str(rules), "--reindex"], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    source_id = proc.stdout.strip()
    assert source_id.startswith("src-") and proc.stdout == source_id + "\n"
    assert f"ingested {rules}: rules, 1 record(s), 1 document(s)" in proc.stderr
    assert "index rebuilt" in proc.stderr

    proc = run_cli(["meta", "--sources"], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.splitlines()
    assert len(lines) == 1 and lines[0].startswith(source_id)
    assert "rules" in lines[0] and str(rules) in lines[0] and "CLAUDE.md" in lines[0]

    proc = run_cli(["run", RULES_THEME, "--json", "-"], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    knowledge = [rc["chunk"]["id"] for rc in json.loads(proc.stdout)["knowledge"]]
    assert any(cid.startswith(source_id) for cid in knowledge), knowledge


def test_ingest_unchanged_is_a_no_op_that_exits_zero(cli_env, tmp_path):
    rules = write_rules(tmp_path)
    first = run_cli(["ingest", str(rules)], cli_env, tmp_path)
    assert first.returncode == 0, first.stderr
    assert "ingested" in first.stderr and "run 'ideate index'" in first.stderr
    second = run_cli(["ingest", str(rules)], cli_env, tmp_path)
    assert second.returncode == 0, second.stderr
    assert "unchanged" in second.stderr and second.stdout == first.stdout
    assert len([r for r in meta_records(cli_env) if r["type"] == "memory_source"]) == 1

    rules.write_text(RULES_TEXT + "\nAlways name a blocker config-fixable or do-it-myself.\n", encoding="utf-8")
    third = run_cli(["ingest", str(rules)], cli_env, tmp_path)
    assert third.returncode == 0 and "ingested" in third.stderr and third.stdout == first.stdout
    assert len([r for r in meta_records(cli_env) if r["type"] == "memory_source"]) == 1


def test_ingest_an_unsupported_path_exits_1(cli_env, tmp_path):
    weird = tmp_path / "notes.bin"
    weird.write_text("x")
    proc = run_cli(["ingest", str(weird)], cli_env, tmp_path)
    assert proc.returncode == 1 and proc.stdout == ""
    assert proc.stderr.startswith("error: ") and "notes.bin" in proc.stderr


def test_ingesting_new_material_invalidates_the_index(cli_env, tmp_path):
    assert run_cli(["index"], cli_env, tmp_path).returncode == 0
    assert "index rebuilt" not in run_cli(["index"], cli_env, tmp_path).stderr
    assert run_cli(["ingest", str(write_rules(tmp_path))], cli_env, tmp_path).returncode == 0
    proc = run_cli(["index"], cli_env, tmp_path)
    assert proc.returncode == 0 and "index rebuilt" in proc.stderr and "21 docs" in proc.stderr


def test_strategy_prints_a_watermarked_plan(cli_env, tmp_path):
    proc = run_cli(["strategy", THEME, "--hours", "36", "--criteria", "innovation:60,demo:40"], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.splitlines()
    assert lines[0] == BANNER_LINE and lines[2] == "# Strategy"
    assert any(line.startswith("- Problem type: ") for line in lines)
    assert any(line.startswith("- Emphasised techniques: ") for line in lines)
    assert any(line.startswith("- Why: ") for line in lines)
    assert PLACEHOLDER_BANNER in proc.stderr
    assert run_dirs(cli_env) == [] and not Path(cli_env["IDEATE_META_PATH"]).exists()


def test_strategy_json_to_stdout(cli_env, tmp_path):
    proc = run_cli(["strategy", THEME, "--json", "-", "--prefer", "python"], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["is_placeholder"] is True and data["placeholder_notice"] == PLACEHOLDER_BANNER
    plan = data["strategy"]
    assert 2 <= len(plan["emphasis_techniques"]) <= 4 and plan["problem_type"]
    assert all(0.5 <= m <= 2.0 for m in plan["rubric_emphasis"].values())


def test_reflect_on_a_saved_run(cli_env, tmp_path):
    proc = run_cli(["run", THEME, "--json", "-", "--no-reflector"], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["reflection"] is None and meta_records(cli_env) == []

    proc = run_cli(["reflect", "--run", result["run_id"]], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines()[0] == BANNER_LINE
    assert f"# What the system learned: {THEME}" in proc.stdout
    assert "### Process changes" in proc.stdout and "### Meta-patterns written" in proc.stdout
    assert f"reflection for run {result['run_id']} saved to" in proc.stderr
    records = meta_records(cli_env)
    reflections = [r for r in records if r["type"] == "reflection"]
    assert len(reflections) == 1 and reflections[0]["run_id"] == result["run_id"]
    assert all(r["provider"] == "mock" for r in records)

    proc = run_cli(["reflect", "--run", "nope"], cli_env, tmp_path)
    assert proc.returncode == 1 and "run 'nope' not found" in proc.stderr


def test_reflect_json_and_meta_listing(cli_env, tmp_path):
    result = json.loads(run_cli(["run", THEME, "--json", "-"], cli_env, tmp_path).stdout)
    proc = run_cli(["reflect", "--run", result["run_id"], "--json", "-"], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["reflection"]["run_id"] == result["run_id"] and data["is_placeholder"] is True
    assert all(p["source_run_id"] == result["run_id"] for p in data["meta_patterns"])

    proc = run_cli(["meta"], cli_env, tmp_path)
    assert proc.returncode == 0 and proc.stdout == ""
    assert "no meta-patterns (pass --include-mock" in proc.stderr

    proc = run_cli(["meta", "--include-mock"], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.splitlines()
    assert lines and all(line.startswith("[mock] meta-") for line in lines)
    assert all("conf 0." in line and "seen " in line for line in lines)

    proc = run_cli(["meta", "--include-mock", "--scope", "global"], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert all("  global " in line for line in proc.stdout.splitlines())

    kinds = {line.split()[2] for line in lines}
    for kind in ("strategy", "process", "pitfall"):
        proc = run_cli(["meta", "--include-mock", "--kind", kind], cli_env, tmp_path)
        assert proc.returncode == 0, proc.stderr
        assert all(f"  {kind} " in line for line in proc.stdout.splitlines())
        assert bool(proc.stdout.splitlines()) == (kind in kinds)


def test_run_without_the_meta_layer_matches_the_baseline_trace(cli_env, tmp_path):
    proc = run_cli(["run", THEME, "--json", "-", "--no-strategist", "--no-reflector"], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["strategy"] is None and data["reflection"] is None
    assert data["settings"]["strategist"] is False and data["settings"]["reflector"] is False
    personas = len(data["settings"]["judge_personas"])
    assert len(data["trace"]) == (
        1 + data["retrieval_rounds"] + 1 + data["iterations"] * (1 + personas) + 1
    )
    assert not any(t["agent"] in ("strategist", "reflector") for t in data["trace"])
    assert meta_records(cli_env) == []
    report = (run_dirs(cli_env)[0] / "report.md").read_text()
    assert "## 1a. Strategy" not in report and "## 10. What the system learned" not in report


def test_run_report_carries_both_meta_sections(cli_env, tmp_path):
    proc = run_cli(["run", THEME], cli_env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "## 1a. Strategy" in proc.stdout and "## 10. What the system learned" in proc.stdout
    assert proc.stdout.index("## 1a. Strategy") < proc.stdout.index("## 1. Build this")
    assert proc.stdout.index("## 9. Trace summary") < proc.stdout.index("## 10. What the system learned")
    assert "reflection recorded in" in proc.stderr
    report = (run_dirs(cli_env)[0] / "report.md").read_text()
    assert report == proc.stdout
    assert "### Meta-patterns written" in report and "- [" in report[report.index("### Meta-patterns written"):]
