"""
evidence_bundle.py
------------------
Assembles the Evidence Bundle — a structured data package that becomes
the shared context for all debate agents.

Aggregates outputs from:
  - Vector engine (skill similarities)
  - Skill graph (matched/missing/extra)
  - Scorer (deterministic scores)
  - GitHub/Codeforces scrapers
"""

import logging
from typing import Optional

from backend.scorer import ScoringResult
from backend.skill_graph import SkillGraphAnalysis
from backend.vector_engine import VectorMatchResult

logger = logging.getLogger(__name__)


def build_evidence_bundle(
    vector_result: VectorMatchResult,
    graph_analysis: SkillGraphAnalysis,
    scoring_result: ScoringResult,
    jd_text: str,
    work_history: list[dict] = None,
    github_data: dict = None,
    codeforces_data: dict = None,
) -> dict:
    """
    Build the evidence bundle for the debate agents.

    This is the single source of truth that all agents reason from.
    No agent should make claims not supported by this bundle.
    """
    work_history = work_history or []
    github_data = github_data or {}
    codeforces_data = codeforces_data or {}

    # Experience analysis
    experience_analysis = []
    for job in work_history:
        role = job.get("role", "Unknown")
        company = job.get("company", "")
        months = job.get("duration_months", 0)
        achievements = job.get("key_achievements", [])
        experience_analysis.append({
            "role": role,
            "company": company,
            "duration_months": months,
            "years": round(months / 12, 1),
            "achievements": achievements,
        })

    # GitHub evidence
    github_evidence = {
        "has_profile": bool(github_data.get("username")),
        "repos_analyzed": len(github_data.get("top_repos", [])),
        "verified_deps": github_data.get("verified_dependencies", []),
        "languages": github_data.get("language_distribution", {}),
        "top_repos": [
            {
                "name": r["name"],
                "stars": r.get("stars", 0),
                "language": r.get("language", "Unknown"),
                "description": r.get("description", ""),
            }
            for r in github_data.get("top_repos", [])[:5]
        ],
        "code_signals_count": len(github_data.get("code_signals", {})),
    }

    # Codeforces evidence
    cf_evidence = None
    if codeforces_data and codeforces_data.get("max_rating"):
        cf_evidence = {
            "handle": codeforces_data.get("handle"),
            "max_rating": codeforces_data.get("max_rating"),
            "rank": codeforces_data.get("rank"),
            "contests": codeforces_data.get("contests_participated", 0),
            "solved_approx": codeforces_data.get("solved_problems_approx", 0),
        }

    # Skill match details
    skill_match_details = [
        {
            "jd_skill": m.jd_skill,
            "candidate_skill": m.candidate_skill,
            "similarity": m.similarity,
        }
        for m in vector_result.skill_matches
    ]

    bundle = {
        # Overall scores
        "overall_similarity": vector_result.overall_similarity,
        "deterministic_score": scoring_result.final_score,
        "score_breakdown": scoring_result.component_breakdown,

        # Skill analysis
        "skill_matches": skill_match_details,
        "matched_skills": graph_analysis.matched_skills,
        "missing_skills": graph_analysis.missing_skills,
        "extra_skills": graph_analysis.extra_skills,
        "match_percentage": graph_analysis.match_percentage,

        # Verification
        "verified_skills": scoring_result.verified_skills,
        "unverified_skills": scoring_result.unverified_skills,

        # Reasoning
        "graph_reasoning": graph_analysis.graph_reasoning,

        # Experience
        "experience_analysis": experience_analysis,
        "total_experience_years": round(
            sum(j.get("duration_months", 0) for j in work_history) / 12, 1
        ) if work_history else 0,

        # External profiles
        "github_evidence": github_evidence,
        "codeforces_evidence": cf_evidence,

        # JD context
        "jd_text_snippet": jd_text[:500],
    }

    logger.info(
        "Evidence bundle built: overall_sim=%.2f, match_pct=%.1f%%, "
        "%d matched, %d missing, %d verified, %d unverified",
        bundle["overall_similarity"],
        bundle["match_percentage"],
        len(bundle["matched_skills"]),
        len(bundle["missing_skills"]),
        len(bundle["verified_skills"]),
        len(bundle["unverified_skills"]),
    )
    return bundle


def format_evidence_for_prompt(bundle: dict) -> str:
    """
    Format the evidence bundle as a readable string for LLM prompts.
    Used by the debate agents.
    """
    lines = []
    lines.append(f"OVERALL SIMILARITY: {bundle['overall_similarity']:.2f}")
    lines.append(f"DETERMINISTIC SCORE: {bundle['deterministic_score']:.4f}")
    lines.append(f"SKILL MATCH PERCENTAGE: {bundle['match_percentage']:.1f}%")
    lines.append("")

    # Score breakdown
    breakdown = bundle.get("score_breakdown", {})
    if breakdown:
        lines.append("SCORE BREAKDOWN:")
        for key, val in breakdown.items():
            if isinstance(val, dict):
                lines.append(f"  {key}: {val.get('value', 0):.4f} (weight: {val.get('weight', 0):.0%})")
            else:
                lines.append(f"  {key}: {val}")
        lines.append("")

    # Skill matches
    lines.append("SKILL MATCHES:")
    for m in bundle.get("skill_matches", []):
        lines.append(f"  {m['jd_skill']} ↔ {m['candidate_skill']}: {m['similarity']:.2f}")
    lines.append("")

    lines.append(f"MATCHED SKILLS: {', '.join(bundle.get('matched_skills', [])) or 'None'}")
    lines.append(f"MISSING SKILLS: {', '.join(bundle.get('missing_skills', [])) or 'None'}")
    lines.append(f"EXTRA SKILLS: {', '.join(bundle.get('extra_skills', [])) or 'None'}")
    lines.append("")

    lines.append(f"VERIFIED (GitHub): {', '.join(bundle.get('verified_skills', [])) or 'None'}")
    lines.append(f"UNVERIFIED: {', '.join(bundle.get('unverified_skills', [])) or 'None'}")
    lines.append("")

    # Reasoning
    lines.append("SKILL GRAPH ANALYSIS:")
    for r in bundle.get("graph_reasoning", []):
        lines.append(f"  • {r}")
    lines.append("")

    # Experience
    lines.append(f"TOTAL EXPERIENCE: {bundle.get('total_experience_years', 0)} years")
    for exp in bundle.get("experience_analysis", []):
        lines.append(f"  - {exp['role']} at {exp['company']} ({exp['years']}yr)")
    lines.append("")

    # GitHub
    gh = bundle.get("github_evidence", {})
    if gh.get("has_profile"):
        lines.append(f"GITHUB: {gh.get('repos_analyzed', 0)} repos analyzed, "
                     f"{len(gh.get('verified_deps', []))} deps verified")
        if gh.get("top_repos"):
            for r in gh["top_repos"][:3]:
                lines.append(f"  ⭐ {r['name']} ({r['language']}) — {r['stars']} stars")
    else:
        lines.append("GITHUB: No profile found")
    lines.append("")

    # Codeforces
    cf = bundle.get("codeforces_evidence")
    if cf:
        lines.append(f"CODEFORCES: {cf['rank']} (max rating: {cf['max_rating']}, "
                     f"contests: {cf['contests']}, solved: ~{cf['solved_approx']})")
    else:
        lines.append("CODEFORCES: No profile found")

    return "\n".join(lines)
