'use client';

import { CheckCircle, XCircle, Minus, ArrowRight } from 'lucide-react';

interface SkillMatchItem {
  jd_skill: string;
  candidate_skill: string;
  similarity: number;
}

interface Props {
  matched: string[];
  missing: string[];
  extra: string[];
  verified: string[];
  unverified: string[];
  matchPercentage: number;
  skillMatches: SkillMatchItem[];
}

function SimilarityBar({ value, label }: { value: number; label: string }) {
  const pct = Math.round(value * 100);
  const color = pct >= 75 ? '#10b981' : pct >= 50 ? '#f59e0b' : '#ef4444';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
      <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', width: 140, flexShrink: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {label}
      </span>
      <div style={{ flex: 1, height: 6, background: 'var(--bg-secondary)', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 3, transition: 'width 0.8s ease' }} />
      </div>
      <span style={{ fontSize: '0.75rem', fontWeight: 600, color, width: 36, textAlign: 'right' }}>{pct}%</span>
    </div>
  );
}

export default function SkillGraph({ matched, missing, extra, verified, unverified, matchPercentage, skillMatches }: Props) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Match percentage */}
      <div style={{ textAlign: 'center', padding: '12px 0' }}>
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 8,
          padding: '8px 20px', borderRadius: 999,
          background: matchPercentage >= 70 ? 'rgba(16,185,129,0.1)' : matchPercentage >= 40 ? 'rgba(245,158,11,0.1)' : 'rgba(239,68,68,0.1)',
          border: `1px solid ${matchPercentage >= 70 ? 'rgba(16,185,129,0.3)' : matchPercentage >= 40 ? 'rgba(245,158,11,0.3)' : 'rgba(239,68,68,0.3)'}`,
        }}>
          <span style={{
            fontSize: '1.4rem', fontWeight: 800,
            color: matchPercentage >= 70 ? '#34d399' : matchPercentage >= 40 ? '#fbbf24' : '#f87171',
          }}>
            {Math.round(matchPercentage)}%
          </span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Skill Match</span>
        </div>
      </div>

      {/* Skill categories */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
        {/* Matched */}
        <div>
          <p style={{ fontSize: '0.72rem', color: '#34d399', fontWeight: 600, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 4 }}>
            <CheckCircle size={11} /> MATCHED ({matched.length})
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
            {matched.map(s => <span key={s} className="skill-matched">{s}</span>)}
            {matched.length === 0 && <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>None</span>}
          </div>
        </div>

        {/* Missing */}
        <div>
          <p style={{ fontSize: '0.72rem', color: '#f87171', fontWeight: 600, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 4 }}>
            <XCircle size={11} /> MISSING ({missing.length})
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
            {missing.map(s => <span key={s} className="skill-missing">{s}</span>)}
            {missing.length === 0 && <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>None — all matched!</span>}
          </div>
        </div>

        {/* Extra */}
        <div>
          <p style={{ fontSize: '0.72rem', color: '#fbbf24', fontWeight: 600, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 4 }}>
            <Minus size={11} /> EXTRA ({extra.length})
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
            {extra.map(s => <span key={s} className="skill-extra">{s}</span>)}
            {extra.length === 0 && <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>None</span>}
          </div>
        </div>
      </div>

      {/* Verification status */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div>
          <p style={{ fontSize: '0.72rem', color: '#34d399', fontWeight: 600, marginBottom: 6 }}>
            ✓ GITHUB VERIFIED ({verified.length})
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
            {verified.slice(0, 15).map(s => <span key={s} className="skill-verified">{s}</span>)}
          </div>
        </div>
        <div>
          <p style={{ fontSize: '0.72rem', color: '#fbbf24', fontWeight: 600, marginBottom: 6 }}>
            ⚠ UNVERIFIED ({unverified.length})
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
            {unverified.slice(0, 10).map(s => <span key={s} className="skill-unverified">{s}</span>)}
            {unverified.length === 0 && <span style={{ fontSize: '0.78rem', color: '#34d399' }}>All verified! 🎉</span>}
          </div>
        </div>
      </div>

      {/* Per-skill similarity bars */}
      {skillMatches && skillMatches.length > 0 && (
        <div>
          <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 600, marginBottom: 8 }}>
            PER-SKILL SIMILARITY (JD → Candidate)
          </p>
          {skillMatches.slice(0, 8).map((m, i) => (
            <SimilarityBar
              key={i}
              value={m.similarity}
              label={m.jd_skill === m.candidate_skill ? m.jd_skill : `${m.jd_skill} → ${m.candidate_skill}`}
            />
          ))}
        </div>
      )}
    </div>
  );
}
