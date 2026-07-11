"""
verification_agent.py
----------------------
Cross-checks resume claims (projects, skills) against scraped evidence from
GitHub (and, when available, Codeforces) and produces a confidence-scored
verification report per project plus an overall trust score for the candidate.

Two-tier approach:
  1. Deterministic pre-check: match claimed tech_stack against verified
     dependencies/language from the scraper. Cheap, instant, auditable.
  2. LLM judgment: only invoked when the deterministic signal is ambiguous,
     or to assess qualitative claims (README depth, code quality signals,
     commit activity) that a keyword match can't capture.
"""

import logging
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

from backend.llm import get_llm
from backend.github_scraper import fetch_repo_code_signals, extract_github_username
from backend.cache import cache_get, cache_set, _make_key

logger = logging.getLogger(__name__)


# ============================================================
# TECH ALIAS MAP — for deterministic matching
# ============================================================
TECH_ALIASES = {
    "pytorch": "torch",
    "hugging face": "transformers",
    "huggingface": "transformers",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "tensorflow": "tensorflow",
    "langchain": "langchain",
    "langgraph": "langgraph",
    "chromadb": "chromadb",
    "fastapi": "fastapi",
    "next.js": "next",
    "nextjs": "next",
    "react": "react",
    "flask": "flask",
    "faiss": "faiss-cpu",
    "sentence-bert": "sentence-transformers",
    "sentence bert": "sentence-transformers",
}


# ============================================================
# SCHEMA
# ============================================================
class ProjectVerification(BaseModel):
    verdict: Literal["supported", "partially_supported", "unsupported", "insufficient_evidence"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    matched_tech: list[str] = Field(default_factory=list)
    unmatched_claims: list[str] = Field(default_factory=list)
    evidence_source: Literal["deterministic", "llm", "none"] = "none"


class CandidateVerificationReport(BaseModel):
    overall_confidence: float = Field(ge=0.0, le=1.0)
    projects_verified: int
    projects_supported: int
    projects_flagged: int
    project_verifications: list[dict]  # name -> ProjectVerification.model_dump()
    skills_corroborated: list[str] = Field(default_factory=list)
    skills_unverifiable: list[str] = Field(default_factory=list)
    summary: str


# ============================================================
# LLM PROMPT — used only when deterministic check is inconclusive
# ============================================================
VERIFICATION_PROMPT = """\
You are a technical verification AI. Compare a candidate's RESUME CLAIM about \
a project against REAL EVIDENCE pulled from their GitHub repository.

Judge honestly — do not give benefit of the doubt. A repo with a thin README \
and no matching dependencies does NOT support a claim, even if the repo name \
matches. Conversely, a well-documented README with matching architecture \
descriptions and real code strongly supports a claim even if not every \
individual library is explicitly listed as a dependency.

RESUME CLAIM:
Project: {project_name}
Claimed tech stack: {claimed_stack}

GITHUB EVIDENCE:
Detected primary language: {language}
README (may be truncated): {readme}
Sample code file snippets: {code_snippets}
Recent commit messages: {commits}
Deterministic dependency match already found: {deterministic_matched}
Deterministic dependency match NOT found (needs your judgment): {deterministic_unmatched}

For each item in "NOT found", decide based on the README and code whether \
there is still credible evidence it was used (e.g. mentioned in README, \
visible in code logic) even though it wasn't in a dependency file. \
Return your verdict.
"""


# ============================================================
# STEP 1: Deterministic pre-check
# ============================================================
def _normalize(term: str) -> str:
    key = term.lower().strip()
    return TECH_ALIASES.get(key, key)


def deterministic_tech_match(
    claimed_stack: list[str],
    verified_dependencies: list[str],
    language: Optional[str] = None,
) -> dict:
    """
    Cheap, auditable first-pass match between resume-claimed tech and
    scraper-verified dependencies (+ detected primary language).
    Returns matched/unmatched lists — no LLM call.
    """
    dep_pool = set(d.lower() for d in verified_dependencies)
    if language:
        dep_pool.add(language.lower())

    matched, unmatched = [], []
    for claim in claimed_stack:
        target = _normalize(claim)
        if target in dep_pool or any(target in d for d in dep_pool):
            matched.append(claim)
        else:
            unmatched.append(claim)
    return {"matched": matched, "unmatched": unmatched}


# ============================================================
# STEP 2: Per-project verification (deterministic + LLM fallback)
# ============================================================
def _extract_owner_repo(url: str) -> Optional[tuple[str, str]]:
    match = re.search(r"github\.com/([a-zA-Z0-9\-]+)/([a-zA-Z0-9_\-\.]+)", url)
    if not match:
        return None
    return match.group(1), match.group(2).rstrip("/")


def verify_project(project: dict) -> dict:
    """
    Verifies a single project dict (name, tech_stack, url) against scraped
    GitHub evidence. Returns the project dict with a 'verification' key added.
    """
    url = project.get("url", "")
    claimed_stack = project.get("tech_stack", [])
    owner_repo = _extract_owner_repo(url) if url else None

    if not owner_repo:
        project["verification"] = ProjectVerification(
            verdict="insufficient_evidence",
            confidence=0.0,
            reasoning="No valid GitHub repo URL to verify against.",
            unmatched_claims=claimed_stack,
            evidence_source="none",
        ).model_dump()
        return project

    owner, repo_name = owner_repo

    # cache the full verification result per project+URL
    cache_key = f"verify_project:{_make_key(project.get('name', '') + url + str(claimed_stack))}"
    cached = cache_get(cache_key)
    if cached is not None:
        import json
        project["verification"] = json.loads(cached)
        return project

    signals = fetch_repo_code_signals(owner, repo_name)

    if signals.get("rate_limited"):
        project["verification"] = ProjectVerification(
            verdict="insufficient_evidence",
            confidence=0.0,
            reasoning="GitHub API rate-limited during verification — retry later.",
            unmatched_claims=claimed_stack,
            evidence_source="none",
        ).model_dump()
        return project

    if signals.get("error") == "repo_not_found":
        project["verification"] = ProjectVerification(
            verdict="unsupported",
            confidence=0.9,
            reasoning="The claimed GitHub repository does not exist or is private.",
            unmatched_claims=claimed_stack,
            evidence_source="deterministic",
        ).model_dump()
        return project

    # STEP 1: deterministic pre-check against verified deps + language.
    # Note: fetch_repo_code_signals doesn't scan requirements.txt itself —
    # reuse the same file-fetch helper here for a project-scoped dep check.
    from backend.github_scraper import _fetch_file_content_pygithub, _get_github_client, _extract_deps_from_requirements, _extract_deps_from_package_json
    verified_deps = []
    try:
        g = _get_github_client()
        repo = g.get_repo(f"{owner}/{repo_name}")
        req_text = _fetch_file_content_pygithub(repo, "requirements.txt")
        if req_text:
            verified_deps += _extract_deps_from_requirements(req_text)
        pkg_text = _fetch_file_content_pygithub(repo, "package.json")
        if pkg_text:
            verified_deps += _extract_deps_from_package_json(pkg_text)
    except Exception as exc:
        logger.warning(f"Could not fetch dependency files for {owner}/{repo_name}: {exc}")

    det_result = deterministic_tech_match(claimed_stack, verified_deps, signals.get("language"))

    # If everything matched deterministically AND there's a real README,
    # skip the LLM call entirely — high-confidence, auditable, free.
    if not det_result["unmatched"] and signals.get("readme"):
        verification = ProjectVerification(
            verdict="supported",
            confidence=0.9,
            reasoning="All claimed technologies found in verified dependency files, "
                      "and a substantive README corroborates the project.",
            matched_tech=det_result["matched"],
            unmatched_claims=[],
            evidence_source="deterministic",
        )
        project["verification"] = verification.model_dump()
        cache_set(cache_key, verification.model_dump_json())
        return project

    # If there's no README AND no code files AND no matched deps at all —
    # skip the LLM too, it's an obvious unsupported/empty-repo case.
    if not signals.get("readme") and not signals.get("code_files") and not det_result["matched"]:
        verification = ProjectVerification(
            verdict="unsupported",
            confidence=0.85,
            reasoning="Repository has no README, no inspectable code files, and no "
                      "dependency evidence matching the claimed tech stack.",
            unmatched_claims=claimed_stack,
            evidence_source="deterministic",
        )
        project["verification"] = verification.model_dump()
        cache_set(cache_key, verification.model_dump_json())
        return project

    # STEP 2: ambiguous case — ask the LLM to weigh README/code evidence
    # against the deterministically-unmatched claims.
    llm = get_llm(temperature=0.0)
    structured_llm = llm.with_structured_output(ProjectVerification)

    code_snippets = "\n\n".join(
        f"{f['path']}:\n{f['content'][:500]}" for f in signals.get("code_files", [])
    ) or "None available"

    prompt = VERIFICATION_PROMPT.format(
        project_name=project.get("name", ""),
        claimed_stack=", ".join(claimed_stack),
        language=signals.get("language") or "unknown",
        readme=(signals.get("readme") or "None")[:1500],
        code_snippets=code_snippets,
        commits=", ".join(signals.get("recent_commits", [])[:5]) or "None",
        deterministic_matched=", ".join(det_result["matched"]) or "None",
        deterministic_unmatched=", ".join(det_result["unmatched"]) or "None",
    )

    result: ProjectVerification = structured_llm.invoke(prompt)
    result.evidence_source = "llm"
    # merge deterministic matches in, in case the LLM didn't repeat them
    result.matched_tech = list(set(result.matched_tech) | set(det_result["matched"]))

    project["verification"] = result.model_dump()
    cache_set(cache_key, result.model_dump_json())
    return project


# ============================================================
# STEP 3: Full candidate verification
# ============================================================
def verify_candidate(profile: dict) -> dict:
    """
    Runs verification on every project in a candidate profile and attaches
    a top-level 'verification_report' summarizing overall trust.
    """
    projects = profile.get("projects", [])
    verified_projects = [verify_project(dict(p)) for p in projects]
    profile["projects"] = verified_projects

    supported = sum(1 for p in verified_projects if p["verification"]["verdict"] == "supported")
    partial = sum(1 for p in verified_projects if p["verification"]["verdict"] == "partially_supported")
    unsupported = sum(1 for p in verified_projects if p["verification"]["verdict"] == "unsupported")
    insufficient = sum(1 for p in verified_projects if p["verification"]["verdict"] == "insufficient_evidence")

    total_scored = supported + partial + unsupported  # exclude insufficient_evidence from scoring
    if total_scored > 0:
        overall_confidence = round(
            (supported * 1.0 + partial * 0.5) / total_scored, 2
        )
    else:
        overall_confidence = 0.0

    # Aggregate which claimed skills show up verified across all projects
    all_claimed_skills = set(profile.get("skills", []))
    corroborated = set()
    for p in verified_projects:
        corroborated.update(p["verification"].get("matched_tech", []))
    skills_corroborated = sorted(corroborated & all_claimed_skills)
    skills_unverifiable = sorted(all_claimed_skills - corroborated)

    summary = (
        f"{supported}/{len(verified_projects)} projects fully supported by GitHub evidence, "
        f"{partial} partially supported, {unsupported} unsupported"
        + (f", {insufficient} could not be checked" if insufficient else "") + "."
    )

    report = CandidateVerificationReport(
        overall_confidence=overall_confidence,
        projects_verified=len(verified_projects),
        projects_supported=supported,
        projects_flagged=unsupported + partial,
        project_verifications=[
            {"name": p.get("name"), **p["verification"]} for p in verified_projects
        ],
        skills_corroborated=skills_corroborated,
        skills_unverifiable=skills_unverifiable,
        summary=summary,
    )

    profile["verification_report"] = report.model_dump()
    logger.info("Verification complete for candidate: %s", summary)
    return profile


# ============================================================
# CODEFORCES — placeholder until codeforces_scraper.py exists
# ============================================================
def verify_codeforces_claim(handle: str) -> dict:
    """
    Placeholder for Codeforces verification. Requires codeforces_scraper.py
    (public API: https://codeforces.com/api/user.info?handles={handle} and
    user.status for submission history) before this can be implemented.
    """
    logger.warning("Codeforces verification requested but codeforces_scraper.py is not yet implemented.")
    return {
        "verdict": "insufficient_evidence",
        "confidence": 0.0,
        "reasoning": "Codeforces scraper not yet implemented.",
    }


# ── CLI quick-test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    import sys

    # Minimal manual test — paste a profile dict here or load from Step 3 output
    test_profile = {
        "skills": ["Python", "PyTorch", "FastAPI"],
        "projects": [
            {
                "name": "AgriPrice Forecaster",
                "tech_stack": ["PyTorch", "PatchTST Transformer", "Gemini AI", "Sentence-BERT"],
                "url": "https://github.com/RagS8i/Agricultural-Commodity-Price-Prediction",
            }
        ],
    }
    result = verify_candidate(test_profile)
    print(json.dumps(result["verification_report"], indent=2))