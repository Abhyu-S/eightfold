import json
from typing import List, Dict, Any
from backend.candidate_schema import SemanticChunk, ChunkMetadata

def chunk_profile(
    candidate_id: str,
    profile_dict: Dict[str, Any],
    github_data: Dict[str, Any] = None,
    codeforces_data: Dict[str, Any] = None,
    leetcode_data: Dict[str, Any] = None
) -> List[SemanticChunk]:
    chunks = []

    # 1. Technical Skills
    skills = profile_dict.get("skills", [])
    if skills:
        skills_text = "Technical Skills:\n"
        for s in skills:
            if isinstance(s, dict):
                skills_text += f"- {s.get('name', '')} ({s.get('kind', '')})\n"
            else:
                skills_text += f"- {s}\n"
        
        chunks.append(SemanticChunk(
            text=skills_text,
            metadata=ChunkMetadata(
                candidate_id=candidate_id,
                chunk_type="Technical Skills",
                source="resume"
            )
        ))

    # 2. Work Experience
    work_history = profile_dict.get("work_history", [])
    for job in work_history:
        job_text = f"Role: {job.get('role', 'Unknown')}\n"
        if job.get('company'):
            job_text += f"Company: {job.get('company')}\n"
        if job.get('duration_months'):
            job_text += f"Duration: {job.get('duration_months')} months\n"
        achievements = job.get("key_achievements", [])
        if achievements:
            job_text += "Achievements:\n"
            for ach in achievements:
                job_text += f"- {ach}\n"
        
        chunks.append(SemanticChunk(
            text=job_text,
            metadata=ChunkMetadata(
                candidate_id=candidate_id,
                chunk_type="Work Experience",
                source="resume"
            )
        ))

    # 3. Projects
    projects = profile_dict.get("projects", [])
    for proj in projects:
        proj_text = f"Project: {proj.get('name', 'Unknown')}\n"
        if proj.get('description'):
            proj_text += f"Description: {proj.get('description')}\n"
        tech_stack = proj.get("tech_stack", [])
        if tech_stack:
            proj_text += f"Tech Stack: {', '.join(tech_stack)}\n"
        if proj.get('url'):
            proj_text += f"URL: {proj.get('url')}\n"
            
        chunks.append(SemanticChunk(
            text=proj_text,
            metadata=ChunkMetadata(
                candidate_id=candidate_id,
                chunk_type="Project",
                source="resume"
            )
        ))

    # 4. Education
    education = profile_dict.get("education", [])
    for ed in education:
        ed_text = f"Degree: {ed.get('degree', 'Unknown')}\n"
        if ed.get('institution'):
            ed_text += f"Institution: {ed.get('institution')}\n"
        if ed.get('year'):
            ed_text += f"Year: {ed.get('year')}\n"
            
        chunks.append(SemanticChunk(
            text=ed_text,
            metadata=ChunkMetadata(
                candidate_id=candidate_id,
                chunk_type="Education",
                source="resume"
            )
        ))

    # 5. Certifications
    certs = profile_dict.get("certifications", [])
    if certs:
        cert_text = "Certifications:\n"
        for cert in certs:
            cert_text += f"- {cert}\n"
            
        chunks.append(SemanticChunk(
            text=cert_text,
            metadata=ChunkMetadata(
                candidate_id=candidate_id,
                chunk_type="Certifications",
                source="resume"
            )
        ))

    # 6. GitHub Stats & Code Signals
    if github_data and not github_data.get("error"):
        # Overview chunk
        gh_overview = f"GitHub Profile: {github_data.get('username')}\n"
        top_repos = github_data.get("top_repos", [])
        if top_repos:
            gh_overview += "Top Repositories:\n"
            for r in top_repos:
                gh_overview += f"- {r.get('name')} (Language: {r.get('language')}, Stars: {r.get('stars')})\n"
        
        deps = github_data.get("verified_dependencies", [])
        if deps:
            gh_overview += f"Verified Dependencies: {', '.join(deps)}\n"
            
        chunks.append(SemanticChunk(
            text=gh_overview,
            metadata=ChunkMetadata(
                candidate_id=candidate_id,
                chunk_type="GitHub Stats",
                source="github"
            )
        ))
        
        # Code Signals (files and readmes)
        code_signals = github_data.get("code_signals", {})
        for repo_name, signals in code_signals.items():
            # README
            readme = signals.get("readme")
            if readme:
                chunks.append(SemanticChunk(
                    text=f"Repo: {repo_name} README\n\n{readme[:2000]}", # Trim to avoid massive chunks
                    metadata=ChunkMetadata(
                        candidate_id=candidate_id,
                        chunk_type="GitHub README",
                        source="github",
                        additional_metadata={"repo": repo_name}
                    )
                ))
            
            # Code files
            for f in signals.get("code_files", []):
                content = f.get("content", "")
                if content.strip():
                    chunks.append(SemanticChunk(
                        text=f"Repo: {repo_name}\nFile: {f.get('path')}\n\n{content[:4000]}",
                        metadata=ChunkMetadata(
                            candidate_id=candidate_id,
                            chunk_type="Code File",
                            source="github",
                            additional_metadata={"repo": repo_name, "path": f.get("path")}
                        )
                    ))

    # 7. Codeforces
    if codeforces_data and not codeforces_data.get("error"):
        cf_text = f"Codeforces Handle: {codeforces_data.get('handle')}\n"
        cf_text += f"Max Rating: {codeforces_data.get('max_rating')}\n"
        cf_text += f"Rank: {codeforces_data.get('rank')}\n"
        cf_text += f"Contests Participated: {codeforces_data.get('contests_participated')}\n"
        cf_text += f"Solved Problems: ~{codeforces_data.get('solved_problems_approx')}\n"
        
        chunks.append(SemanticChunk(
            text=cf_text,
            metadata=ChunkMetadata(
                candidate_id=candidate_id,
                chunk_type="Competitive Programming Stats",
                source="codeforces"
            )
        ))

    # 8. LeetCode
    if leetcode_data and not leetcode_data.get("error"):
        lc_text = f"LeetCode Username: {leetcode_data.get('username')}\n"
        solved = leetcode_data.get("solved", {})
        lc_text += f"Total Solved: {solved.get('total', 0)} (Easy: {solved.get('easy', 0)}, Medium: {solved.get('medium', 0)}, Hard: {solved.get('hard', 0)})\n"
        contest = leetcode_data.get("contest", {})
        if contest and contest.get("rating"):
            lc_text += f"Contest Rating: {contest.get('rating')}\n"
        freq = leetcode_data.get("recent_topics_frequency", {})
        if freq:
            top_topics = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:5]
            lc_text += "Top Recent Topics:\n"
            for topic, count in top_topics:
                lc_text += f"- {topic} ({count})\n"
                
        chunks.append(SemanticChunk(
            text=lc_text,
            metadata=ChunkMetadata(
                candidate_id=candidate_id,
                chunk_type="LeetCode Stats",
                source="leetcode"
            )
        ))

    return chunks
