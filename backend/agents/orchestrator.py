"""
orchestrator.py
---------------
LangGraph StateGraph that runs the multi-agent debate.

Flow: START → advocate → critic → fairness → (continue/decide) → judge → END

The orchestrator:
  1. Runs N rounds of debate (default 2)
  2. Each round: Advocate → Critic → Fairness
  3. After N rounds, the Judge (orchestrator itself) renders a final verdict
  4. All entries are recorded in the immutable ConversationLog
"""

import json
import logging
from typing import TypedDict, Optional

import google.generativeai as genai

from backend.config import settings
from backend.agents.advocate import run_advocate
from backend.agents.critic import run_critic
from backend.agents.fairness import run_fairness
from backend.agents.conversation_log import ConversationLog
from backend.evidence_bundle import format_evidence_for_prompt

logger = logging.getLogger(__name__)

genai.configure(api_key=settings.GOOGLE_API_KEY)

# Default number of debate rounds
DEFAULT_ROUNDS = 2


# ── LangGraph-style State (pure Python, no dependency on langgraph for now) ──
class DebateState(TypedDict):
    evidence_bundle: dict
    conversation_log: object  # ConversationLog instance
    current_round: int
    max_rounds: int
    advocate_results: list
    critic_results: list
    fairness_results: list
    verdict: Optional[dict]


JUDGE_PROMPT = """\
You are the JUDGE (Orchestrator) in a multi-agent hiring debate system.

You have observed {num_rounds} round(s) of debate between an Advocate (argues FOR) \
and a Critic (argues AGAINST), moderated by a Fairness agent (fact-checker).

Your job: Render the FINAL VERDICT based on:
1. The mathematical evidence bundle (deterministic scores)
2. The quality of arguments from both sides
3. The fairness agent's fact-check results
4. The overall strength of evidence

EVIDENCE BUNDLE:
{evidence}

COMPLETE DEBATE LOG:
{debate_log}

IMPORTANT:
- The deterministic score ({score:.4f}) is the mathematical truth — you cannot override it.
- Your verdict explains the score and synthesizes the debate.
- Be fair, balanced, and transparent.

Respond as JSON with this schema:
{{
  "recommendation": "strongly_recommend, recommend, neutral, not_recommend, strongly_not_recommend",
  "confidence": "high, medium, or low",
  "verdict_summary": "string (2-3 sentences)",
  "key_strengths": ["string"],
  "key_concerns": ["string"],
  "debate_quality": "string (how well the agents argued)",
  "fairness_assessment": "string (were the arguments balanced and factual?)"
}}
"""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "recommendation": {
            "type": "string",
            "description": "Hiring recommendation: strongly_recommend, recommend, neutral, not_recommend, strongly_not_recommend",
        },
        "confidence": {
            "type": "string",
            "description": "Confidence level: high, medium, or low",
        },
        "verdict_summary": {
            "type": "string",
            "description": "2-3 sentence final verdict",
        },
        "key_strengths": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Top strengths identified after debate",
        },
        "key_concerns": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Remaining concerns after debate",
        },
        "debate_quality": {
            "type": "string",
            "description": "Assessment of the debate quality",
        },
        "fairness_assessment": {
            "type": "string",
            "description": "Were the arguments balanced and factual?",
        },
    },
    "required": ["recommendation", "confidence", "verdict_summary", "key_strengths", "key_concerns"],
}


def _build_debate_context(state: DebateState) -> str:
    """Build context string from previous rounds for the agents."""
    lines = []
    for i, (adv, crit, fair) in enumerate(
        zip(state["advocate_results"], state["critic_results"], state["fairness_results"])
    ):
        lines.append(f"=== Round {i+1} ===")
        lines.append(f"ADVOCATE: {json.dumps(adv, indent=1)}")
        lines.append(f"CRITIC: {json.dumps(crit, indent=1)}")
        lines.append(f"FAIRNESS: {json.dumps(fair, indent=1)}")
        lines.append("")
    return "\n".join(lines)


def _run_judge(state: DebateState) -> dict:
    """Run the judge to render final verdict."""
    evidence_text = format_evidence_for_prompt(state["evidence_bundle"])
    debate_log_text = state["conversation_log"].export_to_markdown()

    prompt = JUDGE_PROMPT.format(
        num_rounds=state["current_round"],
        evidence=evidence_text,
        debate_log=debate_log_text,
        score=state["evidence_bundle"]["deterministic_score"],
    )

    model = genai.GenerativeModel(
        settings.GEMINI_MODEL_FLASH,
        generation_config=genai.types.GenerationConfig(
            response_mime_type="application/json",
            response_schema=JUDGE_SCHEMA,
            temperature=0.0,
        ),
    )

    response = model.generate_content(prompt)
    verdict = json.loads(response.text)

    logger.info(
        "Judge verdict: %s (confidence: %s)",
        verdict.get("recommendation"),
        verdict.get("confidence"),
    )
    return verdict


def run_debate(
    evidence_bundle: dict,
    num_rounds: int = DEFAULT_ROUNDS,
) -> dict:
    """
    Run the full multi-agent debate pipeline.

    Parameters
    ----------
    evidence_bundle : the shared evidence bundle
    num_rounds : number of debate rounds (default 2)

    Returns
    -------
    dict with:
      - verdict: the judge's final verdict
      - debate_log: list of log entries
      - debate_markdown: formatted markdown of the debate
      - rounds: list of round data
    """
    conv_log = ConversationLog()

    state: DebateState = {
        "evidence_bundle": evidence_bundle,
        "conversation_log": conv_log,
        "current_round": 0,
        "max_rounds": num_rounds,
        "advocate_results": [],
        "critic_results": [],
        "fairness_results": [],
        "verdict": None,
    }

    logger.info("Starting multi-agent debate: %d rounds", num_rounds)

    for round_num in range(1, num_rounds + 1):
        state["current_round"] = round_num
        context = _build_debate_context(state)

        logger.info("=== Debate Round %d/%d ===", round_num, num_rounds)

        # 1. Advocate argues FOR
        advocate_result = run_advocate(evidence_bundle, context, round_num)
        state["advocate_results"].append(advocate_result)
        conv_log.add_entry(
            agent="advocate",
            content=json.dumps(advocate_result, indent=2),
            round_num=round_num,
            entry_type="argument",
        )

        # 2. Critic argues AGAINST
        # Include advocate's arguments in context for rebuttal
        updated_context = context + f"\n\nADVOCATE (Round {round_num}):\n{json.dumps(advocate_result, indent=1)}"
        critic_result = run_critic(evidence_bundle, updated_context, round_num)
        state["critic_results"].append(critic_result)
        conv_log.add_entry(
            agent="critic",
            content=json.dumps(critic_result, indent=2),
            round_num=round_num,
            entry_type="argument",
        )

        # 3. Fairness fact-checks both sides
        fairness_result = run_fairness(evidence_bundle, advocate_result, critic_result, round_num)
        state["fairness_results"].append(fairness_result)
        conv_log.add_entry(
            agent="fairness",
            content=json.dumps(fairness_result, indent=2),
            round_num=round_num,
            entry_type="review",
        )

    # 4. Judge renders final verdict
    logger.info("=== Judge Rendering Verdict ===")
    verdict = _run_judge(state)
    state["verdict"] = verdict
    conv_log.add_entry(
        agent="orchestrator",
        content=json.dumps(verdict, indent=2),
        round_num=state["current_round"] + 1,
        entry_type="verdict",
    )
    conv_log.freeze()

    # Build rounds summary
    rounds_data = []
    for i in range(num_rounds):
        rounds_data.append({
            "round": i + 1,
            "advocate": state["advocate_results"][i],
            "critic": state["critic_results"][i],
            "fairness": state["fairness_results"][i],
        })

    result = {
        "verdict": verdict,
        "debate_log": conv_log.to_dict_list(),
        "debate_markdown": conv_log.export_to_markdown(),
        "rounds": rounds_data,
        "num_rounds": num_rounds,
    }

    logger.info(
        "Debate complete: %d rounds, verdict=%s, %d log entries",
        num_rounds,
        verdict.get("recommendation"),
        len(conv_log.entries),
    )
    return result
