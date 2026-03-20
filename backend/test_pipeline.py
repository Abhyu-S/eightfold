import argparse
import json
import os
from backend.core.logger import logger
from backend.ingestion.document_parser import parse_document
from backend.ingestion.link_extractor import extract_urls, extract_project_links
from backend.security.legitimacy_checker import check_link_legitimacy
from backend.scrapers.github_deep_scraper import (
    scrape_github_repo, scrape_github_profile, is_profile_url
)
from backend.scrapers.codeforces_scraper import fetch_codeforces_stats
from backend.agents.role_analyzer import analyze_role_requirements
from backend.agents.code_reviewer import review_code_quality
from backend.agents.nuanced_evaluator import evaluate_candidate
from backend.agents.decision_verifier import verify_decision


def read_resume(resume_path: str) -> str:
    """Read resume from a PDF file or plain text file."""
    if not os.path.isfile(resume_path):
        print(f"❌ File not found: {resume_path}")
        return ""

    if resume_path.lower().endswith(".pdf"):
        with open(resume_path, "rb") as f:
            file_bytes = f.read()
        print(f"📄 Parsing PDF resume: {resume_path} ({len(file_bytes)} bytes)")
        text = parse_document(file_bytes, "application/pdf")
        print(f"📝 Extracted {len(text)} characters from PDF.")
        return text
    else:
        with open(resume_path, "r") as f:
            return f.read()


def main():
    parser = argparse.ArgumentParser(description="Test the Eightfold V1 Audit Flow")
    parser.add_argument("--jd", type=str, required=True,
                        help="Job Description text string")
    parser.add_argument("--resume", type=str, required=True,
                        help="Path to a PDF resume file, or a .txt file")
    args = parser.parse_args()

    # ── Step 1: Analyze the JD ────────────────────────────────────────────
    print("\n" + "="*60)
    print("  STEP 1: Analyzing Job Description")
    print("="*60)
    rubric = analyze_role_requirements(args.jd)
    print(f"\n🎯 JD Rubric: {json.dumps(rubric, indent=2)}")

    # ── Step 2: Parse Resume ──────────────────────────────────────────────
    print("\n" + "="*60)
    print("  STEP 2: Parsing Resume")
    print("="*60)
    text = read_resume(args.resume)
    if not text:
        print("❌ Could not extract text from the resume. Exiting.")
        return
    print(f"\n📄 Resume Preview (first 500 chars):\n{text[:500]}...")

    # ── Step 3: Project-aware link extraction ─────────────────────────────
    print("\n" + "="*60)
    print("  STEP 3: Extracting Projects & Links from Resume")
    print("="*60)
    projects = extract_project_links(text)
    print(f"\n📋 Found {len(projects)} project(s):")
    for i, proj in enumerate(projects, 1):
        print(f"\n  [{i}] {proj.get('project_name', 'Unnamed')}")
        print(f"      Description: {proj.get('description', 'N/A')}")
        print(f"      Tech: {', '.join(proj.get('claimed_tech', []))}")
        print(f"      URLs: {proj.get('urls', [])}")

    # ── Step 4: Validate & Scrape Links ───────────────────────────────────
    print("\n" + "="*60)
    print("  STEP 4: Validating & Scraping Links (per project)")
    print("="*60)
    candidate_data = {
        "projects": [],
        "all_github_code": {},
        "github_profile": {},
        "codeforces_stats": {},
        "resume_text": text,
        "other_links": []
    }

    for proj in projects:
        project_entry = {
            "project_name": proj.get("project_name", "Unknown"),
            "description": proj.get("description", ""),
            "claimed_tech": proj.get("claimed_tech", []),
            "github_code": {},
            "github_files_scraped": 0,
        }
        urls = proj.get("urls", [])

        for url in urls:
            if not check_link_legitimacy(url):
                print(f"  ⚠️  Skipping illegitimate URL: {url}")
                continue

            if "github.com" in url:
                if is_profile_url(url):
                    # ── Profile-level scraping ──
                    print(f"\n  👤 [{proj.get('project_name')}] GitHub PROFILE detected: {url}")
                    profile_data = scrape_github_profile(url)
                    candidate_data["github_profile"] = profile_data
                    # Also extract code from profile repos into global pool
                    for repo in profile_data.get("repos", []):
                        for fpath, code in repo.get("key_files", {}).items():
                            key = f"{repo.get('name', 'unknown')}/{fpath}"
                            candidate_data["all_github_code"][key] = code
                else:
                    # ── Repo-level scraping ──
                    print(f"\n  🐙 [{proj.get('project_name')}] Scraping GitHub REPO: {url}")
                    repo_data = scrape_github_repo(url)
                    print(f"     Files scraped: {repo_data['files_scraped']}")
                    if repo_data["files_scraped"] > 0:
                        project_entry["github_code"] = repo_data["content"]
                        project_entry["github_files_scraped"] = repo_data["files_scraped"]
                        for filepath, code in repo_data["content"].items():
                            candidate_data["all_github_code"][f"{proj.get('project_name')}/{filepath}"] = code

            elif "codeforces.com/profile/" in url or "codeforces.com/profile/" in url.replace("www.", ""):
                handle = url.rstrip("/").split("/")[-1]
                print(f"\n  🏆 Fetching Codeforces: {handle}")
                stats = fetch_codeforces_stats(handle)
                candidate_data["codeforces_stats"] = stats
                print(f"     Stats: {stats}")
            else:
                candidate_data["other_links"].append(url)
                print(f"  🔗 Other link: {url}")

        candidate_data["projects"].append(project_entry)

    # Print profile summary if found
    if candidate_data["github_profile"]:
        gp = candidate_data["github_profile"]
        print(f"\n  📊 GitHub Profile Summary:")
        print(f"     User: {gp.get('username')}, Followers: {gp.get('followers')}, Repos: {gp.get('public_repos')}")
        for r in gp.get("repos", []):
            print(f"     • {r.get('name')} ({r.get('language')}, ⭐{r.get('stars')}) — {len(r.get('key_files', {}))} key files, {len(r.get('recent_commits', []))} commits")

    # ── Step 5: Code Review ───────────────────────────────────────────────
    print("\n" + "="*60)
    print("  STEP 5: Code Review (GitHub)")
    print("="*60)
    if candidate_data["all_github_code"]:
        print(f"  Reviewing {len(candidate_data['all_github_code'])} files...")
        review_results = review_code_quality(candidate_data["all_github_code"], rubric)
        candidate_data["code_review"] = review_results
        print(f"\n  ✅ Pros:")
        for pro in review_results.get('pros', []):
            print(f"     + {pro}")
        print(f"\n  ❌ Cons:")
        for con in review_results.get('cons', []):
            print(f"     - {con}")
    else:
        print("  ⏭️  No GitHub code found, skipping code review.")
        candidate_data["code_review"] = {"pros": [], "cons": []}

    # ── Step 6: Initial Evaluation ────────────────────────────────────────
    print("\n" + "="*60)
    print("  STEP 6: Initial AI Evaluation")
    print("="*60)
    initial_decision = evaluate_candidate(candidate_data, rubric)

    rec = initial_decision.get('recommendation', 'Unknown')
    emoji = "✅" if rec == "Hire" else "❌"
    print(f"\n  {emoji} Initial Decision: {rec}")
    print(f"  Pros: {initial_decision.get('final_pros', [])}")
    print(f"  Cons: {initial_decision.get('final_cons', [])}")

    # ── Step 7: Chain-of-Verification ─────────────────────────────────────
    print("\n" + "="*60)
    print("  STEP 7: Chain-of-Verification (CoVe)")
    print("="*60)
    verified = verify_decision(initial_decision, candidate_data, rubric)

    print(f"\n{'='*60}")
    vrec = verified.get('verified_recommendation', 'Unknown')
    vemoji = "✅" if vrec == "Hire" else "❌"
    conf = verified.get('confidence_score', 0)
    changed = verified.get('changed', False)

    print(f"  {vemoji} VERIFIED RECOMMENDATION: {vrec}")
    print(f"  📊 Confidence: {conf:.0%}")
    if changed:
        print(f"  🔄 Decision was REVISED from '{rec}' → '{vrec}'")
    else:
        print(f"  ✅ Decision UPHELD from initial assessment")
    print(f"  📝 {verified.get('verification_summary', '')}")
    print(f"{'='*60}")

    # Verification Details
    details = verified.get("verification_details", [])
    if details:
        supported = sum(1 for d in details if d.get("supported"))
        print(f"\n  Verification Audit: {supported}/{len(details)} claims supported\n")
        for d in details:
            s = "✅" if d.get("supported") else "❌"
            print(f"    {s} Q: {d.get('question', '')[:80]}")
            print(f"       A: {d.get('answer', '')[:100]}")
            print()


if __name__ == "__main__":
    main()
