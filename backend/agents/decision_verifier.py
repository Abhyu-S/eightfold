"""
decision_verifier.py
--------------------
Implements Chain-of-Verification (CoVe) to validate the AI's hiring decision.

Pipeline:
  1. Generate verification questions about the initial decision
  2. Answer each question using ONLY raw evidence (not the initial decision)
  3. Reconcile: uphold or revise the decision based on verification answers
"""

import json
import google.generativeai as genai
from backend.core.logger import logger
from backend.core.config import settings


def _clean_json(text: str) -> str:
    """Strip markdown code fences from LLM output."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _generate_verification_questions(model, initial_decision: dict, rubric: dict) -> list[str]:
    """Step 1: Generate factual verification questions about the initial decision."""
    prompt = f"""
    You are a Quality Assurance auditor reviewing an AI hiring decision.
    
    The AI made the following hiring decision:
    {json.dumps(initial_decision, indent=2)}
    
    Based on this rubric:
    {json.dumps(rubric, indent=2)}
    
    Generate exactly 4 factual verification questions that can be answered 
    by examining the raw candidate evidence (code, stats, resume text).
    These questions should check whether the AI's claims are actually supported by evidence.
    
    Focus on:
    - Did the AI correctly identify technologies present in the code?
    - Are the pros/cons actually supported by the scraped data?
    - Did the AI miss any important red flags or strengths?
    - Is the recommendation consistent with the evidence?
    
    Return ONLY a JSON array of question strings:
    ["Question 1?", "Question 2?", "Question 3?", "Question 4?"]
    """
    response = model.generate_content(prompt)
    questions = json.loads(_clean_json(response.text))
    if not isinstance(questions, list):
        questions = [questions]
    return questions[:5]


def _answer_questions_from_evidence(model, questions: list[str], candidate_data: dict) -> list[dict]:
    """Step 2: Answer each question using ONLY the raw evidence."""
    # Build a concise evidence summary (avoid token overflow)
    evidence_parts = []
    
    # Resume text
    resume = candidate_data.get("resume_text", "")
    if resume:
        evidence_parts.append(f"RESUME TEXT (first 2000 chars):\n{resume[:2000]}")
    
    # GitHub code
    github_code = candidate_data.get("all_github_code", {})
    if github_code:
        for filepath, code in list(github_code.items())[:5]:
            evidence_parts.append(f"FILE: {filepath}\n{code[:1500]}")
    
    # Profile data
    profile_data = candidate_data.get("github_profile", {})
    if profile_data:
        repos_summary = []
        for r in profile_data.get("repos", [])[:5]:
            repos_summary.append({
                "name": r.get("name"),
                "language": r.get("language"),
                "stars": r.get("stars"),
                "topics": r.get("topics"),
                "commit_messages": [c.get("message", "")[:80] for c in r.get("recent_commits", [])[:5]],
            })
        evidence_parts.append(f"GITHUB REPOS:\n{json.dumps(repos_summary, indent=2)}")
    
    # Codeforces
    cf = candidate_data.get("codeforces_stats", {})
    if cf:
        evidence_parts.append(f"CODEFORCES STATS: {json.dumps(cf)}")
    
    # Code review
    code_review = candidate_data.get("code_review", {})
    if code_review:
        evidence_parts.append(f"CODE REVIEW: {json.dumps(code_review)}")
    
    evidence_str = "\n\n---\n\n".join(evidence_parts)
    
    qa_results = []
    for q in questions:
        prompt = f"""
        You are a fact-checker. Answer the following question using ONLY the raw evidence provided below.
        Do NOT use any prior knowledge or assumptions. If the evidence doesn't contain enough 
        information to answer, say "Insufficient evidence."
        
        Question: {q}
        
        Raw Evidence:
        {evidence_str}
        
        Return ONLY a JSON object:
        {{
            "question": "{q}",
            "answer": "Your factual answer based on evidence",
            "supported": true or false (whether the evidence supports the AI's claim)
        }}
        """
        try:
            response = model.generate_content(prompt)
            qa = json.loads(_clean_json(response.text))
            qa_results.append(qa)
        except Exception as e:
            logger.error(f"Error answering verification question: {e}")
            qa_results.append({
                "question": q,
                "answer": f"Error during verification: {str(e)}",
                "supported": False
            })
    
    return qa_results


def _reconcile_decision(model, initial_decision: dict, verification_qa: list[dict], rubric: dict) -> dict:
    """Step 3: Reconcile initial decision with verification answers."""
    supported_count = sum(1 for qa in verification_qa if qa.get("supported", False))
    total = len(verification_qa) if verification_qa else 1
    
    prompt = f"""
    You are a Senior Hiring Committee reviewer performing a final quality check.
    
    An AI hiring agent made this initial decision:
    {json.dumps(initial_decision, indent=2)}
    
    A verification audit was then performed. Here are the results:
    {json.dumps(verification_qa, indent=2)}
    
    Verification summary: {supported_count}/{total} claims were supported by evidence.
    
    Based on this rubric:
    {json.dumps(rubric, indent=2)}
    
    Your job:
    1. If the verification mostly supports the initial decision (>= 50% supported), UPHOLD it.
    2. If the verification reveals significant unsupported claims, REVISE the decision.
    3. Provide a confidence score (0.0 to 1.0) for the final decision.
    4. Explain what the verification found.
    
    Return ONLY a valid JSON object:
    {{
        "verified_recommendation": "Hire" or "Reject",
        "confidence_score": float (0.0 to 1.0),
        "verification_summary": "2-3 sentence explanation of what verification found",
        "changed": true or false (whether the decision was changed from the original),
        "supported_claims": int,
        "total_claims_checked": int
    }}
    """
    response = model.generate_content(prompt)
    return json.loads(_clean_json(response.text))


def verify_decision(initial_decision: dict, candidate_data: dict, rubric: dict) -> dict:
    """
    Run the full Chain-of-Verification (CoVe) pipeline.
    
    Steps:
      1. Generate verification questions about the initial AI decision
      2. Answer each question independently using only raw evidence
      3. Reconcile and either uphold or revise the decision
    
    Returns:
        {
            "verified_recommendation": "Hire" or "Reject",
            "confidence_score": float,
            "verification_summary": str,
            "changed": bool,
            "verification_details": [{"question", "answer", "supported"}],
            "supported_claims": int,
            "total_claims_checked": int
        }
    """
    logger.info("Running Chain-of-Verification (CoVe) on hiring decision...")
    
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set. Skipping verification.")
        return {
            "verified_recommendation": initial_decision.get("recommendation", "Reject"),
            "confidence_score": 0.0,
            "verification_summary": "Verification skipped — no API key.",
            "changed": False,
            "verification_details": [],
        }
    
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    try:
        # Step 1: Generate verification questions
        print("\n    🔍 CoVe Step 1: Generating verification questions...")
        questions = _generate_verification_questions(model, initial_decision, rubric)
        for i, q in enumerate(questions, 1):
            print(f"       Q{i}: {q}")
        
        # Step 2: Answer questions from evidence
        print("\n    📋 CoVe Step 2: Answering from raw evidence...")
        qa_results = _answer_questions_from_evidence(model, questions, candidate_data)
        for qa in qa_results:
            status = "✅" if qa.get("supported") else "❌"
            print(f"       {status} {qa.get('question', '')[:60]}...")
            print(f"          → {qa.get('answer', '')[:100]}...")
        
        # Step 3: Reconcile
        print("\n    ⚖️  CoVe Step 3: Reconciling decision...")
        reconciled = _reconcile_decision(model, initial_decision, qa_results, rubric)
        reconciled["verification_details"] = qa_results
        
        changed_str = "🔄 CHANGED" if reconciled.get("changed") else "✅ UPHELD"
        print(f"       {changed_str} — Confidence: {reconciled.get('confidence_score', 0):.0%}")
        
        return reconciled
        
    except Exception as e:
        logger.error(f"Error during Chain-of-Verification: {e}")
        return {
            "verified_recommendation": initial_decision.get("recommendation", "Reject"),
            "confidence_score": 0.0,
            "verification_summary": f"Verification failed: {str(e)}",
            "changed": False,
            "verification_details": [],
        }
