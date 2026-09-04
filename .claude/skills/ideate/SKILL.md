---
name: ideate
description: "Generate, judge and refine hackathon project ideas with the ideation system (hybrid RAG + multi-agent + LLM-judge panel + outcome memory). Use when the user asks for hackathon ideas, to evaluate ideas, or to record a hackathon outcome."
---

# ideate

## 1. Locate the tool

Look for `ideation/` at the repo root. If it is there, use it as-is:
`pip install -e "ideation[anthropic]"` (or run `PYTHONPATH=ideation/src python -m ideate`
instead of `ideate`). If it is not there, install it from the template branch:

```bash
pip install "ideate[anthropic] @ git+https://github.com/phazon2/hack-template@claude/hackathon-ideation-system-hlsks3#subdirectory=ideation"
```

## 2. Run it

Parse from the user's message: the theme, hours (`--hours`, default 24), team size
(`--team`, default 3), judging criteria (`--criteria "innovation:40,impact:30,demo:30"`),
preferred tech (`--prefer a,b`), things to avoid (`--avoid a,b`), tracks (`--tracks a,b`)
and any event notes (write them to a file and pass `--notes-file`). Drop event pages,
sponsor API docs and the rubric into `ideation/src/ideate/corpus/event/` with `kind: event`
when the user has them. Then:

```bash
ideate run "<theme>" --hours 24 --team 3 [--criteria ...] [--prefer ...] [--avoid ...] [--tracks ...] [--notes-file event.md] --out IDEAS.md --json .ideate/last.json
```

Show the user the "Build this" section of `IDEAS.md`, the ranking table and the human
dependencies. To score ideas the user already has, write them to a JSON list of
`{"title", "description"}` objects and run `ideate judge IDEAS.json --theme "<theme>"`.

## 3. Say which provider ran

The first stderr line is `ideate: provider=<provider> model=<model>`. If the provider is
`mock`, say so plainly: the report is a placeholder that proves the pipeline works, not a
set of ideas anyone evaluated. Keep its banner (`PROVIDER: mock — placeholder content, not
evidence`) on anything you quote. Never present mock output as evidence, never summarise it
as if a model had produced it, and never write a receipt or claim a call happened.

## 4. Offer to learn after the event

When the user reports how the hackathon went, write `{"placed", "success", "judge_feedback",
"what_was_cut", "demo_worked", "notes"}` to `outcome.json` and run
`ideate learn outcome.json --run <run_id>` (the run id is in `.ideate/last.json` and on the
`ideate: run <id> saved to ...` line). The patterns feed the next run.

## 5. Never handle credentials

If the run needs a real provider and there is no key, stop and tell the user exactly this
is a **do-it-myself** step: they set `ANTHROPIC_API_KEY` in their own shell (or log in with
the Anthropic CLI and set `IDEATE_PROVIDER=anthropic`) and run `ideate probe` once. Do not
ask for the key, do not read it, do not write it to any file, and do not drive a signup or
login flow. Report other failures with the blocker kind the CLI prints (config-fixable,
do-it-myself, genuinely human-only) and its `fix:` line.
