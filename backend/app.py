"""
app.py
------
Streamlit frontend for the AI Resume Screener.
Calls the FastAPI backend API for evaluation.
"""

import json
import time

import requests
import streamlit as st

# ── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Resume Screener",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

* { font-family: 'Inter', sans-serif; }

.stApp {
    background: linear-gradient(135deg, #0f0c29 0%, #1a1a3e 50%, #24243e 100%);
}

.main-header {
    text-align: center;
    padding: 1.5rem 0 1rem;
    background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 2.5rem;
    font-weight: 800;
    letter-spacing: -1px;
}

.sub-header {
    text-align: center;
    color: #a0a0b8;
    font-size: 1rem;
    margin-bottom: 2rem;
    font-weight: 300;
}

.score-container {
    text-align: center;
    padding: 2rem;
    background: linear-gradient(145deg, rgba(102,126,234,0.15), rgba(118,75,162,0.15));
    border-radius: 20px;
    border: 1px solid rgba(102,126,234,0.3);
    margin: 1rem 0;
}

.score-number {
    font-size: 4.5rem;
    font-weight: 800;
    background: linear-gradient(135deg, #667eea, #764ba2, #f093fb);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    line-height: 1;
}

.score-label {
    color: #a0a0b8;
    font-size: 0.9rem;
    margin-top: 0.25rem;
    text-transform: uppercase;
    letter-spacing: 2px;
}

.bias-badge-pass {
    display: inline-block;
    padding: 0.4rem 1.2rem;
    background: linear-gradient(135deg, #00c853, #1de9b6);
    color: #0a0a0a;
    border-radius: 50px;
    font-weight: 700;
    font-size: 0.85rem;
    letter-spacing: 1px;
}

.bias-badge-fail {
    display: inline-block;
    padding: 0.4rem 1.2rem;
    background: linear-gradient(135deg, #ff5252, #ff1744);
    color: white;
    border-radius: 50px;
    font-weight: 700;
    font-size: 0.85rem;
}

.metric-card {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 12px;
    padding: 1.2rem;
    text-align: center;
}

.metric-value {
    font-size: 1.8rem;
    font-weight: 700;
    color: #667eea;
}

.metric-label {
    font-size: 0.75rem;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-top: 0.25rem;
}

.pro-item {
    padding: 0.5rem 0.8rem;
    background: rgba(0,200,83,0.1);
    border-left: 3px solid #00c853;
    border-radius: 0 8px 8px 0;
    margin: 0.4rem 0;
    color: #e0e0e0;
    font-size: 0.9rem;
}

.con-item {
    padding: 0.5rem 0.8rem;
    background: rgba(255,82,82,0.1);
    border-left: 3px solid #ff5252;
    border-radius: 0 8px 8px 0;
    margin: 0.4rem 0;
    color: #e0e0e0;
    font-size: 0.9rem;
}

.skill-verified {
    display: inline-block;
    padding: 0.2rem 0.6rem;
    background: rgba(0,200,83,0.15);
    border: 1px solid rgba(0,200,83,0.3);
    border-radius: 20px;
    color: #69f0ae;
    font-size: 0.8rem;
    margin: 0.15rem;
}

.skill-unverified {
    display: inline-block;
    padding: 0.2rem 0.6rem;
    background: rgba(255,152,0,0.15);
    border: 1px solid rgba(255,152,0,0.3);
    border-radius: 20px;
    color: #ffb74d;
    font-size: 0.8rem;
    margin: 0.15rem;
}

.glass-card {
    background: rgba(255,255,255,0.05);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 16px;
    padding: 1.5rem;
    margin: 0.5rem 0;
}

div[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a1a3e 0%, #0f0c29 100%);
}

.stButton>button {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border: none;
    padding: 0.75rem 2rem;
    border-radius: 12px;
    font-weight: 600;
    font-size: 1rem;
    width: 100%;
    transition: all 0.3s ease;
}

.stButton>button:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 25px rgba(102,126,234,0.4);
}
</style>
""", unsafe_allow_html=True)

# ── Config ───────────────────────────────────────────────────────────────────
API_BASE = "http://localhost:8000"


# ── Header ───────────────────────────────────────────────────────────────────
st.markdown('<h1 class="main-header">🎯 AI Resume Screener</h1>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Bias-free • Deterministic • Explainable</p>', unsafe_allow_html=True)


# ── Sidebar: Job Description ────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📋 Job Description")
    st.markdown("*Paste the role requirements below*")
    job_description = st.text_area(
        "Job Description",
        height=300,
        placeholder="e.g., We are looking for a Senior Python Backend Engineer with strong experience in FastAPI, PostgreSQL, and ML pipelines...",
        label_visibility="collapsed",
    )
    st.divider()
    st.markdown("### 📄 Resume Upload")
    uploaded_file = st.file_uploader(
        "Upload Resume (PDF)",
        type=["pdf"],
        label_visibility="collapsed",
    )
    st.divider()
    evaluate_btn = st.button("🚀 Evaluate Candidate", type="primary", use_container_width=True)


# ── Main Content ─────────────────────────────────────────────────────────────
def render_results(data: dict):
    """Render the evaluation results in a beautiful layout."""

    # ── Score + Bias Badge ───────────────────────────────────────────────
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        score_pct = data.get("final_score_pct", 0)
        st.markdown(f"""
        <div class="score-container">
            <div class="score-number">{score_pct:.1f}%</div>
            <div class="score-label">Match Score</div>
        </div>
        """, unsafe_allow_html=True)

    # Bias check
    bias = data.get("bias_check", {})
    is_bias_free = bias.get("is_bias_free", False)
    delta = bias.get("delta", 0)

    col1, col2, col3 = st.columns(3)
    with col1:
        if is_bias_free:
            st.markdown(f'<div style="text-align:center"><span class="bias-badge-pass">✅ BIAS FREE</span></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div style="text-align:center"><span class="bias-badge-fail">⚠️ BIAS DETECTED (Δ={delta:.4f})</span></div>', unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{bias.get('redacted_score', 0):.4f}</div>
            <div class="metric-label">Redacted Score</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{bias.get('original_score', 0):.4f}</div>
            <div class="metric-label">Original Score</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ── Score Breakdown ──────────────────────────────────────────────────
    st.markdown("### 📊 Score Breakdown")
    breakdown = data.get("score_breakdown", {})

    cols = st.columns(4)
    components = [
        ("Semantic\nMatch", "semantic_match", "🧠"),
        ("Evidence\nMatch", "evidence_match", "🔍"),
        ("Verification\nRatio", "verification_ratio", "✅"),
        ("Experience\nSignal", "experience_signal", "💼"),
    ]

    for i, (label, key, emoji) in enumerate(components):
        comp = breakdown.get(key, {})
        value = comp.get("value", 0)
        weight = comp.get("weight", 0)
        weighted = comp.get("weighted", 0)
        with cols[i]:
            st.markdown(f"""
            <div class="metric-card">
                <div style="font-size:1.5rem">{emoji}</div>
                <div class="metric-value">{value:.2%}</div>
                <div class="metric-label">{label}</div>
                <div style="color:#666;font-size:0.7rem;margin-top:0.3rem">
                    Weight: {weight:.0%} → {weighted:.4f}
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    # ── Skills ───────────────────────────────────────────────────────────
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### ✅ Verified Skills")
        skills_data = data.get("skills", {})
        verified = skills_data.get("verified", [])
        if verified:
            html = "".join(f'<span class="skill-verified">{s}</span>' for s in verified)
            st.markdown(html, unsafe_allow_html=True)
        else:
            st.info("No skills verified via GitHub")

    with col2:
        st.markdown("### ⚠️ Unverified Claims")
        unverified = skills_data.get("unverified", [])
        if unverified:
            html = "".join(f'<span class="skill-unverified">{s}</span>' for s in unverified)
            st.markdown(html, unsafe_allow_html=True)
        else:
            st.success("All claimed skills are verified!")

    st.markdown("---")

    # ── Explanation ──────────────────────────────────────────────────────
    explanation = data.get("explanation", {})

    st.markdown("### 💡 Explanation")
    summary = explanation.get("summary", "")
    if summary:
        st.markdown(f'<div class="glass-card">{summary}</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Strengths")
        for pro in explanation.get("pros", []):
            st.markdown(f'<div class="pro-item">✅ {pro}</div>', unsafe_allow_html=True)

    with col2:
        st.markdown("#### Weaknesses / Risks")
        for con in explanation.get("cons", []):
            st.markdown(f'<div class="con-item">❌ {con}</div>', unsafe_allow_html=True)

    # ── Skill Evidence Table ─────────────────────────────────────────────
    skill_evidence = explanation.get("skill_evidence", [])
    if skill_evidence:
        st.markdown("---")
        st.markdown("### 🔗 Skill Evidence Chain")
        evidence_rows = []
        for ev in skill_evidence:
            evidence_rows.append({
                "Skill": ev.get("skill", ""),
                "Source": ev.get("source", ""),
                "Evidence": ev.get("file_or_commit", ""),
            })
        st.table(evidence_rows)

    # ── GitHub Summary ───────────────────────────────────────────────────
    gh = data.get("github_summary", {})
    cf = data.get("codeforces_summary", {})

    with st.expander("🐙 GitHub Analysis", expanded=False):
        if gh.get("username"):
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Username", gh["username"])
                st.metric("Repos Analyzed", gh.get("repos_analyzed", 0))
            with col2:
                langs = gh.get("languages", {})
                if langs:
                    st.markdown("**Language Distribution:**")
                    for lang, pct in list(langs.items())[:5]:
                        st.progress(pct / 100, text=f"{lang}: {pct}%")

            top_repos = gh.get("top_repos", [])
            if top_repos:
                st.markdown("**Top Repositories:**")
                for repo in top_repos:
                    st.markdown(f"- ⭐ **{repo['name']}** ({repo.get('language', 'N/A')}) — {repo.get('stars', 0)} stars")

            deps = gh.get("verified_deps", [])
            if deps:
                st.markdown("**Verified Dependencies:**")
                st.code(", ".join(deps[:15]))
        else:
            st.info("No GitHub profile found in resume")

    with st.expander("🏆 Codeforces Analysis", expanded=False):
        if cf.get("handle") and cf.get("max_rating"):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Handle", cf["handle"])
                st.metric("Max Rating", cf.get("max_rating", "N/A"))
            with col2:
                st.metric("Rank", cf.get("rank", "N/A"))
                st.metric("Contests", cf.get("contests", 0))
            with col3:
                st.metric("Problems Solved", f"~{cf.get('solved_approx', 0)}")

            dist = cf.get("problem_distribution", {})
            if dist:
                st.markdown("**Problem Rating Distribution:**")
                import pandas as pd
                df = pd.DataFrame(list(dist.items()), columns=["Rating", "Count"])
                st.bar_chart(df.set_index("Rating"))
        else:
            st.info("No Codeforces profile found in resume")

    # ── Raw JSON (collapsible) ───────────────────────────────────────────
    with st.expander("🔧 Raw API Response", expanded=False):
        st.json(data)


# ── Run Evaluation ───────────────────────────────────────────────────────────
if evaluate_btn:
    if not job_description.strip():
        st.error("Please enter a Job Description in the sidebar.")
    elif not uploaded_file:
        st.error("Please upload a resume PDF.")
    else:
        with st.spinner("🔄 Processing resume... This may take 30-60 seconds."):
            start = time.time()
            try:
                files = {"resume_pdf": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
                form_data = {"job_description": job_description}

                resp = requests.post(
                    f"{API_BASE}/api/evaluate",
                    files=files,
                    data=form_data,
                    timeout=120,
                )

                if resp.status_code == 200:
                    data = resp.json()
                    elapsed = time.time() - start
                    st.success(f"✅ Evaluation complete in {elapsed:.1f}s")
                    render_results(data)
                else:
                    st.error(f"API error {resp.status_code}: {resp.text}")

            except requests.ConnectionError:
                st.error(
                    "❌ Cannot connect to the backend API. "
                    "Please start it with: `python -m backend.main`"
                )
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
else:
    # ── Landing state ────────────────────────────────────────────────────
    st.markdown("""
    <div class="glass-card" style="text-align:center; margin-top:3rem;">
        <h3 style="color:#e0e0e0;">How it works</h3>
        <p style="color:#a0a0b8;">
            1. Paste a <strong>Job Description</strong> in the sidebar<br>
            2. Upload a <strong>Resume PDF</strong><br>
            3. Click <strong>Evaluate</strong> to get a bias-free, explainable score
        </p>
        <br>
        <div style="display:flex; justify-content:center; gap:2rem; flex-wrap:wrap;">
            <div class="metric-card" style="flex:1; min-width:200px; max-width:250px;">
                <div style="font-size:2rem;">🧠</div>
                <div style="color:#667eea; font-weight:600;">Semantic Match</div>
                <div style="color:#888; font-size:0.8rem;">JD ↔ Resume similarity</div>
            </div>
            <div class="metric-card" style="flex:1; min-width:200px; max-width:250px;">
                <div style="font-size:2rem;">🔍</div>
                <div style="color:#667eea; font-weight:600;">Evidence Match</div>
                <div style="color:#888; font-size:0.8rem;">JD ↔ GitHub code</div>
            </div>
            <div class="metric-card" style="flex:1; min-width:200px; max-width:250px;">
                <div style="font-size:2rem;">✅</div>
                <div style="color:#667eea; font-weight:600;">Skill Verification</div>
                <div style="color:#888; font-size:0.8rem;">Claims ↔ GitHub evidence</div>
            </div>
            <div class="metric-card" style="flex:1; min-width:200px; max-width:250px;">
                <div style="font-size:2rem;">🛡️</div>
                <div style="color:#667eea; font-weight:600;">Bias Check</div>
                <div style="color:#888; font-size:0.8rem;">PII has zero score impact</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
