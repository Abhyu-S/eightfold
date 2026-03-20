"""
skill_graph.py
--------------
NetworkX weighted directed graph for skill analysis.
Edges weighted by similarity score + experience years.

Computes:
  - Matched skills (JD ↔ candidate)
  - Missing skills (JD requires, candidate lacks)
  - Extra skills (candidate has, JD doesn't need)
  - Match percentage
  - Human-readable reasoning strings

Used by the debate agents for evidence-based arguments.
"""

import logging
from dataclasses import dataclass, field

import networkx as nx

from backend.vector_engine import SkillMatch

logger = logging.getLogger(__name__)


@dataclass
class SkillGraphAnalysis:
    """Result of skill graph analysis."""
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    extra_skills: list[str] = field(default_factory=list)
    match_percentage: float = 0.0
    graph_reasoning: list[str] = field(default_factory=list)
    graph_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "matched_skills": self.matched_skills,
            "missing_skills": self.missing_skills,
            "extra_skills": self.extra_skills,
            "match_percentage": self.match_percentage,
            "graph_reasoning": self.graph_reasoning,
        }


# ── Thresholds ───────────────────────────────────────────────────────────────
STRONG_MATCH_THRESHOLD = 0.75
WEAK_MATCH_THRESHOLD = 0.50
MISSING_THRESHOLD = 0.50  # Below this = considered missing


def build_skill_graph(
    jd_skills: list[str],
    candidate_skills: list[str],
    skill_matches: list[SkillMatch],
    work_history: list[dict] = None,
    verified_skills: list[str] = None,
) -> SkillGraphAnalysis:
    """
    Build a weighted skill graph and analyze matches/gaps.

    Parameters
    ----------
    jd_skills : normalized JD skills
    candidate_skills : normalized candidate skills
    skill_matches : per-skill similarity from vector engine
    work_history : work experience entries
    verified_skills : skills verified via GitHub

    Returns
    -------
    SkillGraphAnalysis with matched/missing/extra skills and reasoning
    """
    G = nx.DiGraph()
    work_history = work_history or []
    verified_skills = verified_skills or []
    verified_set = {s.lower() for s in verified_skills}

    # Add JD skills as requirement nodes
    for skill in jd_skills:
        G.add_node(f"jd:{skill}", type="requirement", skill=skill)

    # Add candidate skills as evidence nodes
    for skill in candidate_skills:
        G.add_node(f"cand:{skill}", type="evidence", skill=skill)

    # Build match lookup
    match_lookup = {m.jd_skill: m for m in skill_matches}

    # Add edges based on similarity
    matched = []
    missing = []
    reasoning = []

    for jd_skill in jd_skills:
        match = match_lookup.get(jd_skill)
        if match and match.similarity >= WEAK_MATCH_THRESHOLD:
            # This JD skill has a match
            weight = match.similarity
            G.add_edge(
                f"jd:{jd_skill}", f"cand:{match.candidate_skill}",
                weight=weight,
                similarity=match.similarity,
            )
            matched.append(jd_skill)

            # Generate reasoning
            strength = "strong" if match.similarity >= STRONG_MATCH_THRESHOLD else "partial"
            is_verified = match.candidate_skill.lower() in verified_set

            if jd_skill == match.candidate_skill:
                reason = f"Candidate has {jd_skill} ({strength} match, sim={match.similarity:.2f})"
            else:
                reason = f"Candidate's {match.candidate_skill} matches JD's {jd_skill} ({strength}, sim={match.similarity:.2f})"

            if is_verified:
                reason += " — verified via GitHub"
            else:
                reason += " — claimed on resume"

            reasoning.append(reason)
        else:
            missing.append(jd_skill)
            sim = match.similarity if match else 0.0
            reasoning.append(
                f"Candidate lacks {jd_skill} → critical gap (best match sim={sim:.2f})"
            )

    # Extra skills (candidate has, JD doesn't need)
    jd_set = set(jd_skills)
    matched_candidate_skills = {m.candidate_skill for m in skill_matches if m.similarity >= WEAK_MATCH_THRESHOLD}
    extra = [s for s in candidate_skills if s not in jd_set and s not in matched_candidate_skills]

    if extra:
        reasoning.append(
            f"Candidate has {len(extra)} extra skills not required by JD: {', '.join(extra[:5])}"
        )

    # Experience-based reasoning
    if work_history:
        total_months = sum(job.get("duration_months", 0) for job in work_history)
        years = total_months / 12
        reasoning.append(
            f"Candidate has ~{years:.1f} years of professional experience across {len(work_history)} roles"
        )

    # Match percentage
    match_pct = (len(matched) / len(jd_skills) * 100) if jd_skills else 0.0

    analysis = SkillGraphAnalysis(
        matched_skills=sorted(matched),
        missing_skills=sorted(missing),
        extra_skills=sorted(extra),
        match_percentage=round(match_pct, 1),
        graph_reasoning=reasoning,
        graph_data={
            "nodes": len(G.nodes),
            "edges": len(G.edges),
            "strong_matches": sum(1 for m in skill_matches if m.similarity >= STRONG_MATCH_THRESHOLD),
            "weak_matches": sum(1 for m in skill_matches if WEAK_MATCH_THRESHOLD <= m.similarity < STRONG_MATCH_THRESHOLD),
        },
    )

    logger.info(
        "Skill graph built: %d matched, %d missing, %d extra, %.1f%% match",
        len(matched), len(missing), len(extra), match_pct,
    )
    return analysis


# ── CLI quick-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    from backend.vector_engine import SkillMatch

    test_matches = [
        SkillMatch(jd_skill="python", candidate_skill="python", similarity=0.98),
        SkillMatch(jd_skill="fastapi", candidate_skill="fastapi", similarity=0.95),
        SkillMatch(jd_skill="kubernetes", candidate_skill="docker", similarity=0.71),
        SkillMatch(jd_skill="aws", candidate_skill="redis", similarity=0.35),
        SkillMatch(jd_skill="terraform", candidate_skill="docker", similarity=0.42),
    ]

    analysis = build_skill_graph(
        jd_skills=["python", "fastapi", "kubernetes", "aws", "terraform"],
        candidate_skills=["python", "fastapi", "docker", "redis", "postgresql", "graphql"],
        skill_matches=test_matches,
        work_history=[{"role": "Backend Engineer", "duration_months": 36}],
        verified_skills=["python", "fastapi", "docker"],
    )

    print(f"Match: {analysis.match_percentage}%")
    print(f"Matched: {analysis.matched_skills}")
    print(f"Missing: {analysis.missing_skills}")
    print(f"Extra: {analysis.extra_skills}")
    print("Reasoning:")
    for r in analysis.graph_reasoning:
        print(f"  • {r}")
