"""LLM judges: one batched structured call per persona, a panel, and tiered ranking (docs/DESIGN.md §8.3)."""

from __future__ import annotations

from ideate.evaluation.rubric import FEASIBILITY, Rubric
from ideate.evaluation.scoring import NEUTRAL_SCORE, aggregate, agreement, clamp_score
from ideate.llm.base import LLM, LLMBadOutput, LLMRequest
from ideate.llm.schema import arr, bool_, enum, num, obj, str_
from ideate.models import CriterionScore, HackathonConstraints, Idea, IdeaEvaluation, PanelVerdict, slug

DEFAULT_PERSONA = "hackathon judge"
JUDGE_EFFORT = "medium"  # "effort light" (Settings.effort_light default)
MISSING_RATIONALE = "[missing]"
FEASIBILITY_SINK = 2.0  # consensus feasibility at or below this drops an idea to tier 2
JUDGING_RULES = (
    "Score relative to the other ideas in this batch. "
    "Disqualify ideas that violate must-avoid, need an account the team lacks, or cannot be demoed live."
)


def evaluation_schema(ids: list[str], rubric: Rubric) -> dict:
    """The batched judge schema: exactly one evaluation per idea id, every rubric criterion scored."""
    names = rubric.names()
    n = len(names)
    return obj(
        {
            "evaluations": arr(
                obj(
                    {
                        "idea_id": enum(ids),
                        "scores": arr(obj({"name": enum(names), "score": num(1, 5), "rationale": str_()}), n, n),
                        "strengths": arr(str_(), 1, 4),
                        "weaknesses": arr(str_(), 1, 4),
                        "suggestions": arr(str_(), 1, 4),
                        "risks": arr(str_(), 0, 4),
                        "closest_existing": str_(),
                        "demo_break_risk": str_(),
                        "disqualified": bool_(),
                        "disqualify_reason": str_(),
                    }
                ),
                len(ids),
                len(ids),
            )
        }
    )


def _idea_block(idea: Idea) -> str:
    rows = [
        ("One-liner", idea.one_liner),
        ("Target user", idea.target_user),
        ("Description", idea.description),
        ("Key innovation", idea.key_innovation),
        ("Technique", idea.technique),
        ("Technical approach", idea.technical_approach),
        ("Demo strategy", idea.demo_strategy),
        ("Demo moment", idea.demo_moment),
        ("Data sources", "; ".join(idea.data_sources)),
        ("MVP scope", "; ".join(idea.mvp_scope)),
        ("Cut first", "; ".join(idea.cut_first)),
        ("Closest existing", idea.closest_existing),
        ("Build hours estimate", str(idea.build_hours_estimate)),
        ("Risks", "; ".join(idea.risks)),
    ]
    body = "\n".join(f"{label}: {value}" for label, value in rows if value)
    return f"### {idea.id}: {idea.title}\n{body}"


def _idea_ids(ideas: list[Idea]) -> list[str]:
    ids = [idea.id for idea in ideas]
    if any(not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("every idea needs a unique, non-empty id before judging")
    return ids


class LLMJudge:
    """One persona judging a whole batch of ideas in a single structured call."""

    def __init__(
        self,
        llm: LLM,
        rubric: Rubric,
        persona: str = DEFAULT_PERSONA,
        *,
        constraints: HackathonConstraints | None = None,
        effort: str = JUDGE_EFFORT,
    ) -> None:
        self.llm = llm
        self.rubric = rubric
        self.persona = persona
        self.constraints = constraints
        self.effort = effort

    @property
    def tag(self) -> str:
        return f"judge:{slug(self.persona)}"

    def system_prompt(self) -> str:
        """Persona, rubric text and the batch judging rules."""
        return f"You are a {self.persona}.\n\n{self.rubric.to_prompt(self.constraints)}\n\n{JUDGING_RULES}"

    def evaluate_many(self, ideas: list[Idea], context: str) -> list[IdeaEvaluation]:
        """Evaluate every idea in one call; results follow the input order."""
        if not ideas:
            return []
        ids = _idea_ids(ideas)
        prompt = (
            f"{context}\n\nIdeas to evaluate ({len(ideas)}):\n\n"
            + "\n\n".join(_idea_block(idea) for idea in ideas)
            + "\n\nReturn exactly one evaluation for each of these idea ids, scoring every rubric criterion: "
            + ", ".join(ids)
        )
        request = LLMRequest(
            system=self.system_prompt(),
            prompt=prompt,
            tag=self.tag,
            json_schema=evaluation_schema(ids, self.rubric),
            effort=self.effort,
        )
        response = self.llm.complete(request)
        return self._parse(response.data, ids)

    def evaluate(self, idea: Idea, context: str) -> IdeaEvaluation:
        """Evaluate a single idea (a batch of one)."""
        return self.evaluate_many([idea], context)[0]

    def _parse(self, data: object, ids: list[str]) -> list[IdeaEvaluation]:
        """Post-process: first evaluation per id, rubric-only criteria filled and clamped."""
        if not isinstance(data, dict) or not isinstance(data.get("evaluations"), list):
            raise LLMBadOutput(f"{self.tag}: response has no 'evaluations' list")
        by_id: dict[str, dict] = {}
        for raw in data["evaluations"]:
            if isinstance(raw, dict):
                by_id.setdefault(str(raw.get("idea_id", "")), raw)
        missing = [i for i in ids if i not in by_id]
        if missing:
            raise LLMBadOutput(f"{self.tag}: no evaluation for idea ids {missing}")
        return [self._evaluation(by_id[idea_id], idea_id) for idea_id in ids]

    def _evaluation(self, raw: dict, idea_id: str) -> IdeaEvaluation:
        given: dict[str, CriterionScore] = {}
        for item in raw.get("scores", []) or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", ""))
            if name in given or name not in self.rubric.names():
                continue
            given[name] = CriterionScore(name=name, score=clamp_score(item.get("score", NEUTRAL_SCORE)), rationale=str(item.get("rationale", "")))
        scores = [given[name] if name in given else CriterionScore(name=name, score=NEUTRAL_SCORE, rationale=MISSING_RATIONALE) for name in self.rubric.names()]
        return IdeaEvaluation(
            idea_id=idea_id,
            scores=scores,
            weighted_score=self.rubric.weighted_score({s.name: s.score for s in scores}),
            strengths=_strings(raw.get("strengths")),
            weaknesses=_strings(raw.get("weaknesses")),
            suggestions=_strings(raw.get("suggestions")),
            risks=_strings(raw.get("risks")),
            closest_existing=str(raw.get("closest_existing", "")),
            demo_break_risk=str(raw.get("demo_break_risk", "")),
            disqualified=bool(raw.get("disqualified", False)),
            disqualify_reason=str(raw.get("disqualify_reason", "")),
            judge=self.persona,
        )


def _strings(value: object) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


class PanelJudge:
    """Several personas judging the same batch; consensus by ``aggregate``, spread by ``agreement``."""

    def __init__(
        self,
        llm: LLM,
        rubric: Rubric,
        personas: list[str],
        *,
        constraints: HackathonConstraints | None = None,
        effort: str = JUDGE_EFFORT,
    ) -> None:
        if not personas:
            raise ValueError("a panel needs at least one persona")
        self.rubric = rubric
        self.judges = [LLMJudge(llm, rubric, persona, constraints=constraints, effort=effort) for persona in personas]

    @property
    def personas(self) -> list[str]:
        return [judge.persona for judge in self.judges]

    def evaluate_many(self, ideas: list[Idea], context: str) -> list[PanelVerdict]:
        """One call per persona; one verdict per idea, in input order."""
        if not ideas:
            return []
        per_judge = [judge.evaluate_many(ideas, context) for judge in self.judges]
        verdicts: list[PanelVerdict] = []
        for position, idea in enumerate(ideas):
            evals = [results[position] for results in per_judge]
            verdicts.append(
                PanelVerdict(idea_id=idea.id, evaluations=evals, consensus=aggregate(evals, self.rubric), agreement=agreement(evals))
            )
        return verdicts

    def evaluate(self, idea: Idea, context: str) -> PanelVerdict:
        """Verdict for a single idea (a batch of one)."""
        return self.evaluate_many([idea], context)[0]


def rank_ideas(ideas: list[Idea], verdicts: list[PanelVerdict]) -> list[str]:
    """Tiered ranking, a permutation of all idea ids.

    Tier 1: not disqualified and consensus feasibility > 2; tier 2: not disqualified with
    feasibility <= 2; tier 3: disqualified. Within a tier: ``(-weighted_score, title, id)``.
    Ideas without a feasibility criterion count as feasibility 3.
    """
    by_id = {v.idea_id: v for v in verdicts}
    missing = [idea.id for idea in ideas if idea.id not in by_id]
    if missing:
        raise ValueError(f"no verdict for idea ids {missing}")

    def key(idea: Idea) -> tuple[int, float, str, str]:
        consensus = by_id[idea.id].consensus
        if consensus.disqualified:
            tier = 3
        elif consensus.score_for(FEASIBILITY, NEUTRAL_SCORE) <= FEASIBILITY_SINK:
            tier = 2
        else:
            tier = 1
        return (tier, -consensus.weighted_score, idea.title, idea.id)

    return [idea.id for idea in sorted(ideas, key=key)]


def compare_ideas(panel: PanelJudge, ideas: list[Idea], context: str) -> tuple[list[PanelVerdict], list[str]]:
    """Judge a batch with the panel and rank it (see ``rank_ideas``)."""
    verdicts = panel.evaluate_many(ideas, context)
    return verdicts, rank_ideas(ideas, verdicts)
