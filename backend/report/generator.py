"""
report/generator.py
-------------------
Builds the comprehensive final report combining:
  - Deterministic scoring
  - Evidence bundle analysis
  - Multi-agent debate results
  - Verdict and recommendations

The report is the complete, auditable output of the pipeline.
"""

import logging
from typing import Optional

from backend.scorer import ScoringResult
from backend.skill_graph import SkillGraphAnalysis

logger = logging.getLogger(__name__)


def generate_report(
    scoring_result: ScoringResult,
    evidence_bundle: dict,
    debate_result: dict,
    graph_analysis: SkillGraphAnalysis,
    jd_text: str,
    github_data: dict = None,
    codeforces_data: dict = None,
    bias_check: dict = None,
    explanation: dict = None,
) -> dict:
    """
    Generate the comprehensive final report.

    Combines all pipeline outputs into a single auditable report.
    """
    github_data = github_data or {}
    codeforces_data = codeforces_data or {}
    bias_check = bias_check or {}
    explanation = explanation or {}

    verdict = debate_result.get("verdict", {})

    # Determine recommendation label and emoji
    rec = verdict.get("recommendation", "neutral")
    rec_labels = {
        "strongly_recommend": {"label": "Strongly Recommend", "emoji": "🟢", "color": "#10b981"},
        "recommend": {"label": "Recommend", "emoji": "🟢", "color": "#34d399"},
        "neutral": {"label": "Neutral", "emoji": "🟡", "color": "#f59e0b"},
        "not_recommend": {"label": "Do Not Recommend", "emoji": "🔴", "color": "#ef4444"},
        "strongly_not_recommend": {"label": "Strongly Do Not Recommend", "emoji": "🔴", "color": "#dc2626"},
    }
    rec_info = rec_labels.get(rec, rec_labels["neutral"])

    report = {
        # ── Overview ──────────────────────────────────────────────
        "final_score": scoring_result.final_score,
        "final_score_pct": round(scoring_result.final_score * 100, 2),
        "recommendation": rec,
        "recommendation_label": rec_info["label"],
        "recommendation_emoji": rec_info["emoji"],
        "recommendation_color": rec_info["color"],
        "confidence": verdict.get("confidence", "medium"),
        "verdict_summary": verdict.get("verdict_summary", ""),

        # ── Score Breakdown ───────────────────────────────────────
        "score_breakdown": scoring_result.component_breakdown,

        # ── Bias Check ────────────────────────────────────────────
        "bias_check": bias_check,

        # ── Skills ────────────────────────────────────────────────
        "skills": {
            "verified": scoring_result.verified_skills,
            "unverified": scoring_result.unverified_skills,
            "matched": graph_analysis.matched_skills,
            "missing": graph_analysis.missing_skills,
            "extra": graph_analysis.extra_skills,
            "match_percentage": graph_analysis.match_percentage,
        },

        # ── Skill Match Details ───────────────────────────────────
        "skill_matches": evidence_bundle.get("skill_matches", []),

        # ── Evidence Bundle ───────────────────────────────────────
        "evidence_bundle": {
            "overall_similarity": evidence_bundle.get("overall_similarity", 0),
            "graph_reasoning": evidence_bundle.get("graph_reasoning", []),
            "graph_data": graph_analysis.graph_data,
        },

        # ── Debate ────────────────────────────────────────────────
        "debate": {
            "num_rounds": debate_result.get("num_rounds", 0),
            "rounds": debate_result.get("rounds", []),
            "verdict": verdict,
            "log": debate_result.get("debate_log", []),
        },

        # ── Strengths & Concerns ──────────────────────────────────
        "key_strengths": verdict.get("key_strengths", []),
        "key_concerns": verdict.get("key_concerns", []),

        # ── Explanation (Gemini) ──────────────────────────────────
        "explanation": explanation,

        # ── GitHub Summary ────────────────────────────────────────
        "github_summary": {
            "username": github_data.get("username"),
            "repos_analyzed": len(github_data.get("top_repos", [])),
            "languages": github_data.get("language_distribution", {}),
            "verified_deps": github_data.get("verified_dependencies", [])[:20],
            "top_repos": [
                {"name": r["name"], "stars": r.get("stars", 0), "language": r.get("language", "Unknown")}
                for r in github_data.get("top_repos", [])[:5]
            ],
        },

        # ── Codeforces Summary ────────────────────────────────────
        "codeforces_summary": {
            "handle": codeforces_data.get("handle"),
            "max_rating": codeforces_data.get("max_rating"),
            "rank": codeforces_data.get("rank"),
            "contests": codeforces_data.get("contests_participated", 0),
            "solved_approx": codeforces_data.get("solved_problems_approx", 0),
            "problem_distribution": codeforces_data.get("problem_rating_distribution", {}),
        },
    }

    logger.info(
        "Report generated: score=%.2f%%, recommendation=%s, confidence=%s, %d debate rounds",
        report["final_score_pct"],
        report["recommendation"],
        report["confidence"],
        report["debate"]["num_rounds"],
    )
    return report
