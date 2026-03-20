"""
explainer.py
------------
Glass-box explainability engine.
Uses Gemini Pro (heavy reasoning) to translate mathematical scores
into human-readable justifications.

CRITICAL: The LLM is NEVER allowed to alter the numerical score.
It only explains the math that already happened.
"""

import json
import logging
from typing import Optional

from google import genai
from google.genai import types

from backend.cache import cache_get, cache_set, _make_key
from backend.config import settings
from backend.scorer import ScoringResult

logger = logging.getLogger(__name__)

client = genai.Client(api_key=settings.GOOGLE_API_KEY)


EXPLANATION_SCHEMA = {
    "type": "object",
    "properties": {
        "pros": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Specific strengths backed by evidence from code/resume"
        },
        "cons": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Specific weaknesses, gaps, or risks identified"
        },
        "summary": {
            "type": "string",
            "description": "2-3 sentence overall assessment explaining why the candidate matches or doesn't match"
        },
        "skill_evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "skill": {"type": "string"},
                    "source": {"type": "string", "description": "Where this skill was verified: github_code, github_deps, resume_only"},
                    "file_or_commit": {"type": "string", "description": "Specific file path or commit message that proves this skill"}
                },
                "required": ["skill", "source"]
            },
            "description": "Evidence chain linking each skill to its verification source"
        }
    },
    "required": ["pros", "cons", "summary", "skill_evidence"]
}


EXPLANATION_PROMPT = """\
You are an AI Explainability Engine for a hiring assessment system.

You are given a pre-computed mathematical score and its breakdown. Your job is to EXPLAIN \
the score, NOT to change it.

RULES:
1. You MUST NOT suggest a different score. The score is final and computed mathematically.
2. You MUST link every pro/con to specific evidence (a GitHub file, a dependency, a commit message, or a resume claim).
3. For each verified skill, cite exactly WHERE it was verified (repo name, file path, or dependency file).
4. For unverified skills, state they are "claimed on resume but not found in code repositories".
5. Be objective and factual. Avoid generic praise.
6. The summary must explain the mathematical components in plain English.

DATA PROVIDED:
- Final Score: {final_score} / 1.0
- Semantic Match (JD-Resume similarity): {semantic_match} (weight: 30%)
- Evidence Match (JD-Code similarity): {evidence_match} (weight: 30%)
- Verification Ratio (skills verified via GitHub): {verification_ratio} (weight: 25%)
- Experience Signal: {experience_signal} (weight: 15%)

Job Description:
{jd_text}

Verified Skills (found in GitHub code):
{verified_skills}

Unverified Skills (claimed on resume, not found in code):
{unverified_skills}

GitHub Repository Names Analyzed:
{repo_names}

Code Files Analyzed:
{code_file_paths}

Recent Commit Messages:
{commit_messages}

Work History Summary:
{work_summary}

Codeforces Summary:
{cf_summary}

Generate the explanation as JSON matching the schema.
"""


def generate_explanation(
    scoring_result: ScoringResult,
    jd_text: str,
    github_data: dict,
    codeforces_data: Optional[dict] = None,
    work_history: Optional[list] = None,
) -> dict:
    """
    Generate a glass-box explanation for the scoring result.
    Uses Gemini Pro with structured output. Results are cached.

    The LLM CANNOT change the score — it only explains it.
    """
    # Build the prompt context
    repo_names = list(github_data.get("code_signals", {}).keys())
    code_file_paths = []
    commit_messages = []
    for repo_name, signals in github_data.get("code_signals", {}).items():
        for f in signals.get("code_files", []):
            code_file_paths.append(f"{repo_name}/{f['path']}")
        commit_messages.extend(signals.get("recent_commits", [])[:5])

    work_summary = "No work history provided."
    if work_history:
        lines = []
        for job in work_history:
            role = job.get('role', 'Unknown')
            company = job.get('company', '')
            months = job.get('duration_months', 0)
            achievements = "; ".join(job.get('key_achievements', []))
            lines.append(f"- {role} at {company} ({months}mo): {achievements}")
        work_summary = "\n".join(lines)

    cf_summary = "No Codeforces data."
    if codeforces_data and codeforces_data.get("max_rating"):
        cf_summary = (
            f"Max Rating: {codeforces_data['max_rating']}, "
            f"Rank: {codeforces_data.get('rank', 'N/A')}, "
            f"Contests: {codeforces_data.get('contests_participated', 0)}, "
            f"Solved: ~{codeforces_data.get('solved_problems_approx', 0)}"
        )

    prompt_text = EXPLANATION_PROMPT.format(
        final_score=f"{scoring_result.final_score:.4f}",
        semantic_match=f"{scoring_result.semantic_match:.4f}",
        evidence_match=f"{scoring_result.evidence_match:.4f}",
        verification_ratio=f"{scoring_result.verification_ratio:.4f}",
        experience_signal=f"{scoring_result.experience_signal:.4f}",
        jd_text=jd_text[:2000],
        verified_skills=", ".join(scoring_result.verified_skills) or "None",
        unverified_skills=", ".join(scoring_result.unverified_skills) or "None",
        repo_names=", ".join(repo_names) or "None analyzed",
        code_file_paths="\n".join(code_file_paths[:10]) or "None",
        commit_messages="\n".join(commit_messages[:10]) or "None",
        work_summary=work_summary,
        cf_summary=cf_summary,
    )

    # Check cache
    cache_key = f"explanation:{_make_key(prompt_text)}"
    cached = cache_get(cache_key)
    if cached is not None:
        try:
            logger.info("Explanation loaded from cache")
            return json.loads(cached)
        except json.JSONDecodeError:
            pass

    # Call Gemini Pro
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL_FLASH,
        contents=prompt_text,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=EXPLANATION_SCHEMA,
            temperature=0.0,
        ),
    )
    explanation = json.loads(response.text)

    # Cache the result
    cache_set(cache_key, json.dumps(explanation, ensure_ascii=False))

    logger.info(
        "Explanation generated: %d pros, %d cons, %d skill evidence items",
        len(explanation.get("pros", [])),
        len(explanation.get("cons", [])),
        len(explanation.get("skill_evidence", [])),
    )
    return explanation


# ── CLI quick-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Quick test with mock data
    from backend.scorer import ScoringResult

    mock_result = ScoringResult(
        final_score=0.72,
        semantic_match=0.85,
        evidence_match=0.65,
        verification_ratio=0.71,
        experience_signal=0.8,
        verified_skills=["Python", "FastAPI", "scikit-learn"],
        unverified_skills=["Kubernetes", "Spark"],
        component_breakdown={},
    )

    explanation = generate_explanation(
        scoring_result=mock_result,
        jd_text="Senior Python Backend Engineer with FastAPI and ML experience.",
        github_data={"code_signals": {}},
    )

    import pprint
    pprint.pprint(explanation)
