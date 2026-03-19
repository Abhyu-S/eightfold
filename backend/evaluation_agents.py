"""
evaluation_agents.py
---------------------
The Agentic Reasoning Panel — three LangChain-powered agents that analyze
a candidate profile and produce scored, explainable evaluations.

Agents:
  ┌─────────────────────────────────────────────────────────────────────┐
  │ 1. TechLeadAgent     – Resume skills vs GitHub verified deps        │
  │ 2. TrajectoryAgent   – Learning velocity score 1–5                  │
  │ 3. ExplainabilityAgent – 3-sentence recruiter justification         │
  └─────────────────────────────────────────────────────────────────────┘

Synthesizer:
  evaluate_candidate(candidate_profile, github_data, codeforces_data, jd_text)
  → Returns the final unified CandidateReview dict.
"""

import json
import logging
import os
from typing import Any, Optional

from dotenv import load_dotenv
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

load_dotenv()
logger = logging.getLogger(__name__)

USE_MOCK_DATA: bool = os.getenv("USE_MOCK_DATA", "False").lower() == "true"


# ============================================================
# MOCK OUTPUT
# ============================================================
MOCK_EVALUATION = {
    "tech_lead": {
        "verified_skills": ["Python", "FastAPI", "scikit-learn", "Docker", "Redis"],
        "unverified_claims": ["Kubernetes", "Spark"],
        "verification_rate": 0.71,
        "verdict": "Strong alignment. Most core skills are GitHub-verified.",
    },
    "trajectory": {
        "score": 4,
        "reasoning": (
            "Candidate shows a consistent upward trajectory: from junior Python → ML pipelines → "
            "distributed systems. Codeforces rating improvement of +320 over 2 years indicates "
            "strong algorithmic growth."
        ),
    },
    "explainability": {
        "summary": (
            "This candidate demonstrates a verified and well-rounded backend engineering profile "
            "with strong Python and FastAPI skills confirmed through GitHub dependency analysis. "
            "Their competitive programming history (Codeforces Expert) indicates solid algorithmic "
            "thinking. Overall, a high-confidence match for the Senior Backend Engineer role."
        )
    },
}


# ============================================================
# LLM FACTORY
# ============================================================

def _build_llm():
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    model = os.getenv("LLM_MODEL", "gpt-4o")
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY not set.")
        return ChatOpenAI(model=model, temperature=0.2, openai_api_key=api_key)
    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        api_key = os.getenv("GOOGLE_API_KEY", "")
        if not api_key:
            raise EnvironmentError("GOOGLE_API_KEY not set.")
        return ChatGoogleGenerativeAI(model=model, temperature=0.2, google_api_key=api_key)
    raise ValueError(f"Unsupported LLM_PROVIDER: '{provider}'")


def _parse_json_robust(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("```"))
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(raw[start:end])
        raise ValueError(f"Cannot parse JSON from agent output:\n{raw}")


# ============================================================
# AGENT 1: TECH LEAD AGENT
# ============================================================

TECH_LEAD_SYSTEM = """\
You are a senior Tech Lead performing a technical skills verification audit.

You will receive:
  1. A list of skills the candidate CLAIMS on their resume
  2. A list of libraries/frameworks VERIFIED from their GitHub repositories (actual dependency files)

Your job:
  - Identify which claimed skills are verified by GitHub evidence.
  - Identify which claimed skills have NO GitHub evidence (unverified claims).
  - Calculate a verification_rate: verified / total_claimed (0.0–1.0, 2 decimal places).
  - Write a one-sentence verdict summarizing the technical trustworthiness.

Output ONLY valid JSON, no markdown:
{
  "verified_skills": ["string"],
  "unverified_claims": ["string"],
  "verification_rate": float,
  "verdict": "string"
}
"""

TECH_LEAD_HUMAN = """\
Claimed Resume Skills:
{claimed_skills}

GitHub Verified Dependencies:
{github_deps}

Perform the verification audit and return JSON.
"""


def run_tech_lead_agent(
    claimed_skills: list[str],
    github_deps: list[str],
    llm=None,
) -> dict:
    """
    Compare resume-claimed skills against GitHub-verified dependencies.

    Returns dict with: verified_skills, unverified_claims, verification_rate, verdict.
    """
    if USE_MOCK_DATA:
        return dict(MOCK_EVALUATION["tech_lead"])

    if llm is None:
        llm = _build_llm()

    prompt = ChatPromptTemplate.from_messages([
        ("system", TECH_LEAD_SYSTEM),
        ("human", TECH_LEAD_HUMAN),
    ])
    chain = prompt | llm | StrOutputParser()

    raw = chain.invoke({
        "claimed_skills": ", ".join(claimed_skills) if claimed_skills else "None listed",
        "github_deps":    ", ".join(github_deps)    if github_deps    else "No GitHub data",
    })

    result = _parse_json_robust(raw)
    logger.info(
        "TechLeadAgent done. Verified: %d, Unverified: %d, Rate: %.2f",
        len(result.get("verified_skills", [])),
        len(result.get("unverified_claims", [])),
        result.get("verification_rate", 0),
    )
    return result


# ============================================================
# AGENT 2: TRAJECTORY AGENT
# ============================================================

TRAJECTORY_SYSTEM = """\
You are a Talent Trajectory Analyst specializing in assessing developer growth and learning velocity.

You will receive:
  - Candidate's work history (roles, durations, achievements)
  - Skills progression (inferred from work history and projects)
  - Codeforces contest history (optional, may be empty)

Your job:
  - Analyze the career arc: is the candidate growing in skill complexity, responsibility, and impact?
  - Factor in Codeforces performance trend if available (improving rating = positive signal).
  - Score learning velocity from 1–5:
      1 = Stagnant (no visible growth, repetitive roles)
      2 = Slow growth (some progression but minor)
      3 = Steady (consistent growth, reasonable)
      4 = Fast (clear skill expansion, increasing complexity)
      5 = Exceptional (rapid multi-domain growth, leadership, innovation)

Output ONLY valid JSON, no markdown:
{
  "score": integer (1-5),
  "reasoning": "2–3 sentence explanation of your score"
}
"""

TRAJECTORY_HUMAN = """\
Work History:
{work_history}

Projects:
{projects}

Codeforces Contest History (last 5):
{cf_contests}

Codeforces Max Rating: {cf_max_rating}
Current Rating: {cf_current_rating}

Analyze the learning trajectory and return JSON.
"""


def run_trajectory_agent(
    profile: dict,
    codeforces_data: dict,
    llm=None,
) -> dict:
    """
    Score the candidate's learning velocity (1–5) with reasoning.

    Returns dict with: score (int 1–5), reasoning (str).
    """
    if USE_MOCK_DATA:
        return dict(MOCK_EVALUATION["trajectory"])

    if llm is None:
        llm = _build_llm()

    # Format work history for the prompt
    wh_lines = []
    for job in profile.get("work_history", []):
        line = (
            f"- {job.get('role')} at {job.get('company')} "
            f"({job.get('duration_months', 0)} months): "
            + "; ".join(job.get("key_achievements", []))
        )
        wh_lines.append(line)
    work_history_str = "\n".join(wh_lines) if wh_lines else "No work history available."

    proj_lines = []
    for p in profile.get("projects", []):
        proj_lines.append(
            f"- {p.get('name')}: {p.get('description')} [{', '.join(p.get('tech_stack', []))}]"
        )
    projects_str = "\n".join(proj_lines) if proj_lines else "No projects listed."

    cf_contests = codeforces_data.get("recent_contests", [])
    if cf_contests:
        contest_str = "\n".join(
            f"- {c['contest']}: rank {c.get('rank')}, Δ{c.get('rating_change', 0):+d}"
            for c in cf_contests
        )
    else:
        contest_str = "No Codeforces contest history."

    prompt = ChatPromptTemplate.from_messages([
        ("system", TRAJECTORY_SYSTEM),
        ("human", TRAJECTORY_HUMAN),
    ])
    chain = prompt | llm | StrOutputParser()

    raw = chain.invoke({
        "work_history": work_history_str,
        "projects": projects_str,
        "cf_contests": contest_str,
        "cf_max_rating": codeforces_data.get("max_rating") or "N/A",
        "cf_current_rating": codeforces_data.get("current_rating") or "N/A",
    })

    result = _parse_json_robust(raw)
    score = max(1, min(5, int(result.get("score", 3))))  # Clamp to [1,5]
    result["score"] = score
    logger.info("TrajectoryAgent done. Score: %d/5", score)
    return result


# ============================================================
# AGENT 3: EXPLAINABILITY AGENT
# ============================================================

EXPLAINABILITY_SYSTEM = """\
You are an AI Recruitment Advisor writing justifications for hiring managers.

You will receive:
  - The Job Description the candidate is being matched against
  - A vector similarity match score (0.0–1.0)
  - Tech Lead verification findings (verified skills, unverified claims, rate)
  - Trajectory score (1–5) and its reasoning

Your job:
  Write EXACTLY 3 sentences explaining WHY this candidate is or isn't a good match.
  - Sentence 1: Summarize the strongest technical evidence (verified skills / GitHub alignment).
  - Sentence 2: Mention the learning trajectory or growth potential.
  - Sentence 3: Provide the overall hiring recommendation with confidence level.

Be objective and use specific facts from the input. Avoid generic statements.

Output ONLY valid JSON, no markdown:
{
  "summary": "Sentence 1. Sentence 2. Sentence 3."
}
"""

EXPLAINABILITY_HUMAN = """\
Job Description (excerpt):
{jd_text}

Vector Match Score: {match_score}

Tech Lead Findings:
- Verified Skills: {verified_skills}
- Unverified Claims: {unverified_claims}
- Verification Rate: {verification_rate}
- Verdict: {tech_verdict}

Trajectory Score: {trajectory_score}/5
Trajectory Reasoning: {trajectory_reasoning}

Write the 3-sentence recruiter justification.
"""


def run_explainability_agent(
    jd_text: str,
    match_score: float,
    tech_lead_result: dict,
    trajectory_result: dict,
    llm=None,
) -> dict:
    """
    Produce a 3-sentence recruiter-facing justification.

    Returns dict with: summary (str).
    """
    if USE_MOCK_DATA:
        return dict(MOCK_EVALUATION["explainability"])

    if llm is None:
        llm = _build_llm()

    prompt = ChatPromptTemplate.from_messages([
        ("system", EXPLAINABILITY_SYSTEM),
        ("human", EXPLAINABILITY_HUMAN),
    ])
    chain = prompt | llm | StrOutputParser()

    raw = chain.invoke({
        "jd_text": jd_text[:1500],  # Trim to avoid token overflow
        "match_score": f"{match_score:.2%}",
        "verified_skills": ", ".join(tech_lead_result.get("verified_skills", [])),
        "unverified_claims": ", ".join(tech_lead_result.get("unverified_claims", [])) or "None",
        "verification_rate": f"{tech_lead_result.get('verification_rate', 0):.0%}",
        "tech_verdict": tech_lead_result.get("verdict", ""),
        "trajectory_score": trajectory_result.get("score", "N/A"),
        "trajectory_reasoning": trajectory_result.get("reasoning", ""),
    })

    result = _parse_json_robust(raw)
    logger.info("ExplainabilityAgent done.")
    return result


# ============================================================
# SYNTHESIZER — Runs all 3 agents and combines results
# ============================================================

def evaluate_candidate(
    candidate_profile: dict,
    github_data: dict,
    codeforces_data: dict,
    jd_text: str,
    match_score: float,
    candidate_id: str = "unknown",
    llm=None,
) -> dict:
    """
    Run all three evaluation agents for a candidate and synthesize the final review.

    Parameters
    ----------
    candidate_profile : dict   Anonymized + structured profile (from anonymizer_agent)
    github_data       : dict   Output from github_scraper
    codeforces_data   : dict   Output from codeforces_scraper
    jd_text           : str    The Job Description text
    match_score       : float  Vector similarity score (0–1)
    candidate_id      : str    Identifier for logging

    Returns
    -------
    dict with keys:
        candidate_id, match_score, tech_lead, trajectory, explainability,
        final_score (weighted composite), candidate_profile
    """
    logger.info("=== Evaluating candidate '%s' ===", candidate_id)

    # Build LLM once and reuse across all agents
    if llm is None and not USE_MOCK_DATA:
        llm = _build_llm()

    claimed_skills = candidate_profile.get("skills", [])
    gh_deps = github_data.get("verified_dependencies", [])

    # ── Run agents (sequential — each depends on data, not each other) ──
    tech_result = run_tech_lead_agent(claimed_skills, gh_deps, llm=llm)
    traj_result = run_trajectory_agent(candidate_profile, codeforces_data, llm=llm)
    expl_result = run_explainability_agent(
        jd_text, match_score, tech_result, traj_result, llm=llm
    )

    # ── Composite final score (weighted) ─────────────────────────────────
    # Vector similarity (40%) + Verification rate (30%) + Trajectory (30%)
    vector_component       = match_score * 0.40
    verification_component = tech_result.get("verification_rate", 0) * 0.30
    trajectory_normalized  = (traj_result.get("score", 3) / 5) * 0.30
    final_score = round(vector_component + verification_component + trajectory_normalized, 4)

    review = {
        "candidate_id": candidate_id,
        "match_score": round(match_score, 4),
        "final_score": final_score,
        "tech_lead": tech_result,
        "trajectory": traj_result,
        "explainability": expl_result,
        "candidate_profile": candidate_profile,
        "github_summary": {
            "top_language": max(
                github_data.get("language_distribution", {"Unknown": 1}),
                key=github_data.get("language_distribution", {"Unknown": 1}).get,
            ),
            "verified_dep_count": len(gh_deps),
            "top_repo": (github_data.get("top_repos") or [{}])[0].get("name", "N/A"),
        },
        "codeforces_summary": {
            "max_rating": codeforces_data.get("max_rating"),
            "rank": codeforces_data.get("rank"),
            "contests": codeforces_data.get("contests_participated", 0),
        },
    }

    logger.info(
        "Evaluation complete for '%s': final_score=%.4f",
        candidate_id,
        final_score,
    )
    return review


# ── CLI quick-test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import pprint
    from backend.github_scraper import MOCK_GITHUB_DATA
    from backend.codeforces_scraper import MOCK_CF_DATA
    from backend.anonymizer_agent import MOCK_ANONYMIZED_PROFILE

    review = evaluate_candidate(
        candidate_profile=MOCK_ANONYMIZED_PROFILE,
        github_data=MOCK_GITHUB_DATA,
        codeforces_data=MOCK_CF_DATA,
        jd_text="Senior Python engineer with FastAPI, ML, and competitive programming background.",
        match_score=0.87,
        candidate_id="test_candidate",
    )
    pprint.pprint(review)
