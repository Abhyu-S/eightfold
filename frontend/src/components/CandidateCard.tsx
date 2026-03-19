'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, ChevronUp, CheckCircle, XCircle, Star, Trophy, Github, Code } from 'lucide-react';
import type { MatchResult } from '@/app/page';

interface Props {
  candidate: MatchResult;
}

function ScoreRing({ score, size = 56 }: { score: number; size?: number }) {
  const pct = Math.min(100, Math.max(0, score * 100));
  const color = pct >= 70 ? '#34d399' : pct >= 45 ? '#fbbf24' : '#f87171';
  const stroke = size * 0.12;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const dash = (pct / 100) * circ;

  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--bg-secondary)" strokeWidth={stroke} />
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={stroke}
          strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
          style={{ transition: 'stroke-dasharray 0.8s ease' }} />
      </svg>
      <span style={{
        position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: size * 0.22, fontWeight: 700, color,
      }}>
        {Math.round(pct)}
      </span>
    </div>
  );
}

function TrajectoryStars({ score }: { score: number }) {
  return (
    <div style={{ display: 'flex', gap: 2 }}>
      {[1,2,3,4,5].map(i => (
        <Star key={i} size={12} fill={i <= score ? '#fbbf24' : 'none'} color={i <= score ? '#fbbf24' : 'var(--border-light)'} />
      ))}
    </div>
  );
}

export default function CandidateCard({ candidate }: Props) {
  const [expanded, setExpanded] = useState(false);
  const {
    candidate_id, rank, match_score, final_score,
    verified_skills, unverified_claims, verification_rate,
    trajectory_score, explanation,
    top_language, cf_rank, cf_max_rating,
  } = candidate;

  const pct = Math.round(final_score * 100);
  const verPct = Math.round(verification_rate * 100);

  return (
    <div className="glass glow-blue" style={{
      borderRadius: 14, marginBottom: 14, overflow: 'hidden',
      transition: 'border-color 0.2s',
      borderColor: rank === 1 ? 'rgba(59,130,246,0.4)' : undefined,
    }}>
      {/* Header row */}
      <div style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 16, cursor: 'pointer' }}
        onClick={() => setExpanded(!expanded)}>

        {/* Rank badge */}
        <div style={{
          width: 32, height: 32, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: rank === 1 ? 'var(--gradient-accent)' : rank === 2 ? 'rgba(139,92,246,0.2)' : 'var(--bg-secondary)',
          fontSize: '0.85rem', fontWeight: 700, flexShrink: 0,
          border: rank <= 2 ? '1px solid var(--accent-purple)' : '1px solid var(--border)',
          color: rank <= 2 ? '#a78bfa' : 'var(--text-secondary)',
        }}>
          #{rank}
        </div>

        {/* Score ring */}
        <ScoreRing score={final_score} size={54} />

        {/* Info */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 5 }}>
            <span style={{ fontWeight: 600, fontSize: '0.95rem', color: 'var(--text-primary)' }}>
              {candidate_id}
            </span>
            {rank === 1 && <span className="badge badge-blue"><Trophy size={10} /> Top Match</span>}
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <span className="badge badge-green">✓ {verPct}% verified</span>
            <span className="badge badge-purple">
              <TrajectoryStars score={trajectory_score} /> Trajectory
            </span>
            {top_language && <span className="badge badge-blue"><Github size={9} /> {top_language}</span>}
            {cf_rank && <span className="badge badge-amber"><Code size={9} /> {cf_rank} {cf_max_rating ? `(${cf_max_rating})` : ''}</span>}
          </div>
        </div>

        {/* Vector match */}
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div style={{ fontSize: '1.1rem', fontWeight: 800, color: '#60a5fa' }}>
            {Math.round(match_score * 100)}%
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>vector match</div>
        </div>

        {expanded ? <ChevronUp size={16} color="var(--text-muted)" /> : <ChevronDown size={16} color="var(--text-muted)" />}
      </div>

      {/* Expanded detail */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{ padding: '0 20px 20px', borderTop: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 16 }}>

              {/* AI Explanation */}
              <div style={{ background: 'rgba(59,130,246,0.05)', border: '1px solid rgba(59,130,246,0.15)', borderRadius: 10, padding: 14, marginTop: 16 }}>
                <p style={{ fontSize: '0.75rem', color: 'var(--accent-blue)', fontWeight: 600, marginBottom: 6, letterSpacing: '0.04em' }}>
                  🤖 AI EXPLAINABILITY
                </p>
                <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', lineHeight: 1.65 }}>{explanation}</p>
              </div>

              {/* Skills grid */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                {/* Verified */}
                <div>
                  <p style={{ fontSize: '0.75rem', color: '#34d399', fontWeight: 600, marginBottom: 8 }}>
                    <CheckCircle size={11} style={{ display: 'inline', marginRight: 4 }} />
                    GITHUB VERIFIED ({verified_skills.length})
                  </p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                    {verified_skills.slice(0, 12).map(s => (
                      <span key={s} className="badge badge-green" style={{ fontSize: '0.7rem' }}>{s}</span>
                    ))}
                  </div>
                </div>
                {/* Unverified */}
                <div>
                  <p style={{ fontSize: '0.75rem', color: '#f87171', fontWeight: 600, marginBottom: 8 }}>
                    <XCircle size={11} style={{ display: 'inline', marginRight: 4 }} />
                    UNVERIFIED CLAIMS ({unverified_claims.length})
                  </p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                    {unverified_claims.slice(0, 8).map(s => (
                      <span key={s} className="badge badge-red" style={{ fontSize: '0.7rem' }}>{s}</span>
                    ))}
                    {unverified_claims.length === 0 && (
                      <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>All claims verified 🎉</span>
                    )}
                  </div>
                </div>
              </div>

              {/* Score breakdown bar */}
              <div>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600, marginBottom: 8 }}>COMPOSITE SCORE BREAKDOWN</p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {[
                    { label: 'Vector Similarity', value: match_score, color: '#3b82f6', weight: '40%' },
                    { label: 'Skill Verification', value: verification_rate, color: '#10b981', weight: '30%' },
                    { label: 'Trajectory', value: trajectory_score / 5, color: '#f59e0b', weight: '30%' },
                  ].map(item => (
                    <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', width: 120, flexShrink: 0 }}>{item.label}</span>
                      <div style={{ flex: 1, height: 6, background: 'var(--bg-secondary)', borderRadius: 3, overflow: 'hidden' }}>
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${item.value * 100}%` }}
                          transition={{ duration: 0.6, ease: 'easeOut' }}
                          style={{ height: '100%', background: item.color, borderRadius: 3 }}
                        />
                      </div>
                      <span style={{ fontSize: '0.75rem', color: item.color, fontWeight: 600, width: 36, textAlign: 'right' }}>
                        {Math.round(item.value * 100)}%
                      </span>
                      <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', width: 28 }}>{item.weight}</span>
                    </div>
                  ))}
                </div>
              </div>

            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
