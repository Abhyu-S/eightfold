"""
verification_agent.py
----------------------
Cross-checks resume claims (projects, skills) against scraped evidence from
GitHub, Codeforces, and LeetCode, and produces a confidence-scored
verification report per project plus an overall trust score for the candidate.

Two-tier approach for GitHub projects:
  1. Deterministic pre-check: match claimed tech_stack against verified
     dependencies/language from the scraper. Cheap, instant, auditable.
  2. LLM judgment: only invoked when the deterministic signal is ambiguous,
     or to assess qualitative claims (README depth, code quality signals,
     commit activity) that a keyword match can't capture.

Codeforces and LeetCode have no per-item tech claim to diff against, so
they're verified as coarse activity checks instead (see verify_codeforces_claim
/ verify_leetcode_claim) and folded into overall_confidence as informational,
lower-weighted signals — light or absent activity there should not aggressively
penalize a candidate who never leaned on that platform.

Every verdict carries provenance (verified_at, evidence_url/source) so a
human can trace exactly what was checked and when, not just trust the label.
A separate extract_red_flags() pulls all discrepancies into one flat,
skimmable list instead of leaving them buried in prose reasoning.
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

from backend.llm import get_llm
from backend.github_scraper import (
    fetch_repo_code_signals,
    _fetch_file_content_pygithub,
    _get_github_client,
    _extract_deps_from_requirements,
    _extract_deps_from_package_json,
)
from backend.codeforces_scraper import fetch_codeforces_profile
from backend.leetcode_scraper import fetch_leetcode_profile
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

CP_RELATED_KEYWORDS = {
    "competitive programming", "data structures & algorithms",
    "data structures and algorithms", "dsa", "algorithms",
    "problem solving", "codeforces", "leetcode",
}

VerdictType = Literal["supported", "partially_supported", "unsupported", "insufficient_evidence"]

_VERDICT_WEIGHT = {
    "supported": 1.0,
    "partially_supported": 0.5,
    "unsupported": 0.0,
}


def _now_iso() -> str:
    """UTC timestamp for provenance — stdlib only, no external deps."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ============================================================
# SCHEMAS
# ============================================================
class ProjectVerification(BaseModel):
    verdict: VerdictType
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    matched_tech: list[str] = Field(default_factory=list)
    unmatched_claims: list[str] = Field(default_factory=list)
    evidence_source: Literal["deterministic", "llm", "none"] = "none"
    verified_at: Optional[str] = None
    evidence_url: Optional[str] = None


class PlatformVerification(BaseModel):
    """Shared shape for Codeforces / LeetCode activity checks."""
    platform: Literal["codeforces", "leetcode"]
    verdict: VerdictType
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    stats: dict = Field(default_factory=dict)
    verified_at: Optional[str] = None
    evidence_url: Optional[str] = None


class CandidateVerificationReport(BaseModel):
    overall_confidence: float = Field(ge=0.0, le=1.0)
    projects_verified: int
    projects_supported: int
    projects_flagged: int
    project_verifications: list[dict]
    platform_verifications: list[dict] = Field(default_factory=list)
    skills_corroborated: list[str] = Field(default_factory=list)
    skills_unverifiable: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    summary: str


# ============================================================
# LLM PROMPT — used only when GitHub deterministic check is inconclusive
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
# GITHUB: deterministic pre-check
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


def _extract_owner_repo(url: str) -> Optional[tuple[str, str]]:
    match = re.search(r"github\.com/([a-zA-Z0-9\-]+)/([a-zA-Z0-9_\-\.]+)", url)
    if not match:
        return None
    return match.group(1), match.group(2).rstrip("/")


# ============================================================
# GITHUB: per-project verification (deterministic + LLM fallback)
# ============================================================
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
            verified_at=_now_iso(),
            evidence_url=url or None,
        ).model_dump()
        return project

    owner, repo_name = owner_repo

    cache_key = f"verify_project:{_make_key(project.get('name', '') + url + str(claimed_stack))}"
    cached = cache_get(cache_key)
    if cached is not None:
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
            verified_at=_now_iso(),
            evidence_url=url,
        ).model_dump()
        return project

    if signals.get("error") == "repo_not_found":
        project["verification"] = ProjectVerification(
            verdict="unsupported",
            confidence=0.9,
            reasoning="The claimed GitHub repository does not exist or is private.",
            unmatched_claims=claimed_stack,
            evidence_source="deterministic",
            verified_at=_now_iso(),
            evidence_url=url,
        ).model_dump()
        return project

    # Deterministic pre-check against verified deps + language.
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

    if not det_result["unmatched"] and signals.get("readme"):
        verification = ProjectVerification(
            verdict="supported",
            confidence=0.9,
            reasoning="All claimed technologies found in verified dependency files, "
                      "and a substantive README corroborates the project.",
            matched_tech=det_result["matched"],
            unmatched_claims=[],
            evidence_source="deterministic",
            verified_at=_now_iso(),
            evidence_url=url,
        )
        project["verification"] = verification.model_dump()
        cache_set(cache_key, verification.model_dump_json())
        return project

    if not signals.get("readme") and not signals.get("code_files") and not det_result["matched"]:
        verification = ProjectVerification(
            verdict="unsupported",
            confidence=0.85,
            reasoning="Repository has no README, no inspectable code files, and no "
                      "dependency evidence matching the claimed tech stack.",
            unmatched_claims=claimed_stack,
            evidence_source="deterministic",
            verified_at=_now_iso(),
            evidence_url=url,
        )
        project["verification"] = verification.model_dump()
        cache_set(cache_key, verification.model_dump_json())
        return project

    # Ambiguous case — ask the LLM to weigh README/code evidence
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
    result.matched_tech = list(set(result.matched_tech) | set(det_result["matched"]))
    result.verified_at = _now_iso()
    result.evidence_url = url

    project["verification"] = result.model_dump()
    cache_set(cache_key, result.model_dump_json())
    return project


# ============================================================
# CODEFORCES VERIFICATION
# ============================================================
def verify_codeforces_claim(handle: str, claimed_skills: Optional[list[str]] = None) -> dict:
    """
    Verifies a candidate's Codeforces handle. No per-item tech claim to diff
    here — the signal is (a) does the handle exist, (b) how much real
    activity backs it up, cross-referenced against whether the resume leans
    on CP-related skills at all.
    """
    claimed_skills = claimed_skills or []
    claims_cp_skill = any(
        kw in s.lower() for s in claimed_skills for kw in CP_RELATED_KEYWORDS
    )

    profile = fetch_codeforces_profile(handle)
    evidence_url = f"https://codeforces.com/profile/{handle}"

    if profile.get("error"):
        verdict = "unsupported" if claims_cp_skill else "insufficient_evidence"
        return PlatformVerification(
            platform="codeforces",
            verdict=verdict,
            confidence=0.8 if claims_cp_skill else 0.3,
            reasoning=f"Codeforces handle '{handle}' could not be verified: {profile['error']}",
            verified_at=_now_iso(),
            evidence_url=evidence_url,
        ).model_dump()

    rating = profile.get("current_rating")
    solved = profile.get("solved_problems_approx", 0)
    contests = profile.get("contests_participated", 0)
    rank = profile.get("rank")

    if solved == 0 and contests == 0:
        verdict, confidence, reasoning = (
            "unsupported" if claims_cp_skill else "insufficient_evidence",
            0.7,
            f"Codeforces handle '{handle}' exists but shows zero solved problems "
            f"and zero contest participation.",
        )
    elif solved < 20 and contests < 3:
        verdict, confidence, reasoning = (
            "partially_supported", 0.5,
            f"Codeforces handle '{handle}' shows minimal activity ({solved} solved, "
            f"{contests} contests).",
        )
    else:
        verdict, confidence, reasoning = (
            "supported", 0.9,
            f"Codeforces handle '{handle}' shows substantive activity: {solved} problems "
            f"solved across {contests} contests, current rating {rating} ({rank}).",
        )

    return PlatformVerification(
        platform="codeforces",
        verdict=verdict,
        confidence=confidence,
        reasoning=reasoning,
        stats={"current_rating": rating, "rank": rank, "solved": solved, "contests": contests},
        verified_at=_now_iso(),
        evidence_url=evidence_url,
    ).model_dump()


# ============================================================
# LEETCODE VERIFICATION
# ============================================================
def verify_leetcode_claim(username: str, claimed_skills: Optional[list[str]] = None) -> dict:
    """
    Verifies a candidate's LeetCode handle and checks whether solve activity
    plausibly supports DSA/problem-solving claims. Informational signal —
    weak activity should not aggressively penalize overall_confidence, since
    many strong engineers simply don't grind LeetCode.
    """
    claimed_skills = claimed_skills or []
    claims_cp_skill = any(
        kw in s.lower() for s in claimed_skills for kw in CP_RELATED_KEYWORDS
    )

    profile = fetch_leetcode_profile(username)
    evidence_url = f"https://leetcode.com/u/{username}/"

    if profile.get("error"):
        verdict = "unsupported" if claims_cp_skill else "insufficient_evidence"
        return PlatformVerification(
            platform="leetcode",
            verdict=verdict,
            confidence=0.8 if claims_cp_skill else 0.3,
            reasoning=f"LeetCode handle '{username}' could not be verified: {profile['error']}",
            verified_at=_now_iso(),
            evidence_url=evidence_url,
        ).model_dump()

    total = profile["solved"]["total"]
    raw_rating = profile["contest"]["rating"]
    # LeetCode's API returns high-precision floats (e.g. 1550.871432945877) —
    # round for any human-facing report; stdlib round(), no extra deps.
    rating = round(raw_rating, 1) if raw_rating is not None else None

    if total == 0:
        verdict, confidence, reasoning = (
            "unsupported" if claims_cp_skill else "insufficient_evidence",
            0.6,
            f"LeetCode handle '{username}' exists but shows zero solved problems.",
        )
    elif total < 30:
        verdict, confidence, reasoning = (
            "partially_supported", 0.5,
            f"LeetCode handle '{username}' shows light activity ({total} problems solved).",
        )
    else:
        verdict, confidence, reasoning = (
            "supported", 0.85,
            f"LeetCode handle '{username}' shows substantive activity: {total} problems solved"
            + (f", contest rating {rating}." if rating else "."),
        )

    return PlatformVerification(
        platform="leetcode",
        verdict=verdict,
        confidence=confidence,
        reasoning=reasoning,
        stats={"total_solved": total, "contest_rating": rating},
        verified_at=_now_iso(),
        evidence_url=evidence_url,
    ).model_dump()


# ============================================================
# RED FLAGS — flat, skimmable discrepancy list
# ============================================================
def extract_red_flags(verified_projects: list[dict], platform_results: list[dict]) -> list[str]:
    """
    Pulls concrete, human-scannable discrepancies out of verification
    results, instead of leaving them buried inside prose 'reasoning' text.
    Intended for a recruiter-facing summary or UI badge list.
    """
    flags: list[str] = []

    for p in verified_projects:
        v = p.get("verification", {})
        name = p.get("name", "Unnamed project")

        if v.get("verdict") == "unsupported":
            flags.append(f"{name}: verdict UNSUPPORTED — repository evidence does not back this claim.")
        elif v.get("verdict") == "insufficient_evidence":
            flags.append(f"{name}: could not be checked ({v.get('reasoning', 'no reason given')}).")

        if v.get("unmatched_claims"):
            flags.append(
                f"{name}: claimed {', '.join(v['unmatched_claims'])} — "
                f"not confirmed by repository evidence."
            )

    for pr in platform_results:
        if pr["verdict"] in ("unsupported", "insufficient_evidence"):
            flags.append(f"{pr['platform'].capitalize()}: {pr['reasoning']}")

    return flags


# ============================================================
# FULL CANDIDATE VERIFICATION
# ============================================================
def verify_candidate(profile: dict) -> dict:
    """
    Runs verification on every project, plus Codeforces/LeetCode if handles
    were claimed, and attaches a top-level 'verification_report'.
    """
    projects = profile.get("projects", [])
    verified_projects = [verify_project(dict(p)) for p in projects]
    profile["projects"] = verified_projects

    supported = sum(1 for p in verified_projects if p["verification"]["verdict"] == "supported")
    partial = sum(1 for p in verified_projects if p["verification"]["verdict"] == "partially_supported")
    unsupported = sum(1 for p in verified_projects if p["verification"]["verdict"] == "unsupported")
    insufficient = sum(1 for p in verified_projects if p["verification"]["verdict"] == "insufficient_evidence")

    weighted_scores = [_VERDICT_WEIGHT[p["verification"]["verdict"]]
                        for p in verified_projects
                        if p["verification"]["verdict"] in _VERDICT_WEIGHT]

    platform_results = []
    claimed_skills = profile.get("skills", [])

    if profile.get("codeforces_handle"):
        cf_result = verify_codeforces_claim(profile["codeforces_handle"], claimed_skills)
        profile["codeforces_verification"] = cf_result
        platform_results.append(cf_result)
        if cf_result["verdict"] in _VERDICT_WEIGHT:
            weighted_scores.append(_VERDICT_WEIGHT[cf_result["verdict"]])

    if profile.get("leetcode_username"):
        lc_result = verify_leetcode_claim(profile["leetcode_username"], claimed_skills)
        profile["leetcode_verification"] = lc_result
        platform_results.append(lc_result)
        if lc_result["verdict"] in _VERDICT_WEIGHT:
            weighted_scores.append(_VERDICT_WEIGHT[lc_result["verdict"]])

    overall_confidence = round(sum(weighted_scores) / len(weighted_scores), 2) if weighted_scores else 0.0

    all_claimed_skills = set(claimed_skills)
    corroborated = set()
    for p in verified_projects:
        corroborated.update(p["verification"].get("matched_tech", []))
    skills_corroborated = sorted(corroborated & all_claimed_skills)
    skills_unverifiable = sorted(all_claimed_skills - corroborated)

    red_flags = extract_red_flags(verified_projects, platform_results)

    summary_parts = [
        f"{supported}/{len(verified_projects)} projects fully supported by GitHub evidence, "
        f"{partial} partially supported, {unsupported} unsupported"
        + (f", {insufficient} could not be checked" if insufficient else "") + "."
    ]
    for pr in platform_results:
        summary_parts.append(f"{pr['platform'].capitalize()}: {pr['reasoning']}")

    report = CandidateVerificationReport(
        overall_confidence=overall_confidence,
        projects_verified=len(verified_projects),
        projects_supported=supported,
        projects_flagged=unsupported + partial,
        project_verifications=[
            {"name": p.get("name"), **p["verification"]} for p in verified_projects
        ],
        platform_verifications=platform_results,
        skills_corroborated=skills_corroborated,
        skills_unverifiable=skills_unverifiable,
        red_flags=red_flags,
        summary=" ".join(summary_parts),
    )

    profile["verification_report"] = report.model_dump()
    logger.info("Verification complete for candidate: %s", report.summary)
    return profile