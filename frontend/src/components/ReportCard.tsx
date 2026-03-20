'use client';

import { motion } from 'framer-motion';
import { Github, Code, Briefcase, Award, ExternalLink } from 'lucide-react';

interface Props {
  data: any;
}

function ScoreRing({ score, size = 110 }: { score: number; size?: number }) {
  const pct = Math.min(100, Math.max(0, score));
  const color = pct >= 70 ? '#34d399' : pct >= 45 ? '#fbbf24' : '#f87171';
  const stroke = size * 0.1;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const dash = (pct / 100) * circ;

  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--bg-secondary)" strokeWidth={stroke} />
        <motion.circle
          cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={stroke}
          strokeLinecap="round"
          initial={{ strokeDasharray: `0 ${circ}` }}
          animate={{ strokeDasharray: `${dash} ${circ}` }}
          transition={{ duration: 1.2, ease: 'easeOut' }}
        />
      </svg>
      <div style={{
        position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
      }}>
        <span style={{ fontSize: size * 0.28, fontWeight: 800, color, lineHeight: 1 }}>
          {Math.round(pct)}
        </span>
        <span style={{ fontSize: size * 0.1, color: 'var(--text-muted)', fontWeight: 500 }}>/ 100</span>
      </div>
    </div>
  );
}

export default function ReportCard({ data }: Props) {
  if (!data) return null;

  const recColors: Record<string, string> = {
    strongly_recommend: '#10b981',
    recommend: '#34d399',
    neutral: '#f59e0b',
    not_recommend: '#ef4444',
    strongly_not_recommend: '#dc2626',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Hero score area */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 24, justifyContent: 'center',
        padding: '24px', borderRadius: 16,
        background: 'linear-gradient(145deg, rgba(59,130,246,0.08), rgba(139,92,246,0.08))',
        border: '1px solid rgba(59,130,246,0.2)',
      }}>
        <motion.div
          initial={{ scale: 0, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.5, type: 'spring' }}
        >
          <ScoreRing score={data.final_score_pct || 0} />
        </motion.div>

        <div>
          {/* Verdict badge */}
          <motion.div
            initial={{ y: 10, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.3 }}
          >
            <span className="verdict-badge" style={{
              background: `${recColors[data.recommendation] || '#f59e0b'}20`,
              border: `1px solid ${recColors[data.recommendation] || '#f59e0b'}40`,
              color: recColors[data.recommendation] || '#f59e0b',
            }}>
              {data.recommendation_emoji} {data.recommendation_label || 'Neutral'}
            </span>
          </motion.div>

          <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginTop: 8, maxWidth: 320, lineHeight: 1.6 }}>
            {data.verdict_summary || 'Score computed successfully.'}
          </p>

          <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
            <span className="badge badge-blue">Confidence: {data.confidence || 'N/A'}</span>
            {data.bias_check?.is_bias_free && <span className="badge badge-green">✓ Bias Free</span>}
            {data.bias_check && !data.bias_check.is_bias_free && (
              <span className="badge badge-red">⚠ Bias Δ={data.bias_check.delta?.toFixed(4)}</span>
            )}
          </div>
        </div>
      </div>

      {/* Score breakdown */}
      <div>
        <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 600, marginBottom: 8, letterSpacing: '0.05em' }}>
          SCORE BREAKDOWN
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
          {[
            { label: 'Semantic\nMatch', key: 'semantic_match', emoji: '🧠', color: '#3b82f6' },
            { label: 'Evidence\nMatch', key: 'evidence_match', emoji: '🔍', color: '#8b5cf6' },
            { label: 'Verification\nRatio', key: 'verification_ratio', emoji: '✅', color: '#10b981' },
            { label: 'Experience\nSignal', key: 'experience_signal', emoji: '💼', color: '#f59e0b' },
          ].map(({ label, key, emoji, color }) => {
            const comp = data.score_breakdown?.[key] || {};
            const value = comp.value || 0;
            const weight = comp.weight || 0;
            return (
              <div key={key} style={{
                textAlign: 'center', padding: '12px 8px',
                background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)',
                borderRadius: 10,
              }}>
                <div style={{ fontSize: '1.2rem', marginBottom: 4 }}>{emoji}</div>
                <div style={{ fontSize: '1.1rem', fontWeight: 700, color }}>{(value * 100).toFixed(0)}%</div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', whiteSpace: 'pre-line', marginTop: 2 }}>{label}</div>
                <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)', marginTop: 2 }}>
                  weight: {(weight * 100).toFixed(0)}%
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* GitHub & Codeforces */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        {/* GitHub */}
        <div style={{
          padding: 14, borderRadius: 10,
          background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)',
        }}>
          <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 600, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 5 }}>
            <Github size={12} /> GITHUB
          </p>
          {data.github_summary?.username ? (
            <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              <p><strong style={{ color: 'var(--text-primary)' }}>@{data.github_summary.username}</strong></p>
              <p>{data.github_summary.repos_analyzed} repos analyzed</p>
              {data.github_summary.top_repos?.slice(0, 3).map((r: any) => (
                <p key={r.name} style={{ fontSize: '0.78rem' }}>
                  ⭐ {r.name} ({r.language}) — {r.stars} stars
                </p>
              ))}
            </div>
          ) : (
            <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>No GitHub profile found</p>
          )}
        </div>

        {/* Codeforces */}
        <div style={{
          padding: 14, borderRadius: 10,
          background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)',
        }}>
          <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 600, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 5 }}>
            <Code size={12} /> CODEFORCES
          </p>
          {data.codeforces_summary?.max_rating ? (
            <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              <p><strong style={{ color: 'var(--text-primary)' }}>{data.codeforces_summary.handle}</strong> — {data.codeforces_summary.rank}</p>
              <p>Max Rating: {data.codeforces_summary.max_rating}</p>
              <p>Contests: {data.codeforces_summary.contests} · Solved: ~{data.codeforces_summary.solved_approx}</p>
            </div>
          ) : (
            <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>No Codeforces profile found</p>
          )}
        </div>
      </div>

      {/* Explanation */}
      {data.explanation && (
        <div>
          <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 600, marginBottom: 8, letterSpacing: '0.05em' }}>
            AI EXPLANATION
          </p>
          {data.explanation.summary && (
            <p style={{
              fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.65,
              padding: 12, borderRadius: 8,
              background: 'rgba(59,130,246,0.04)', border: '1px solid rgba(59,130,246,0.12)',
              marginBottom: 10,
            }}>
              {data.explanation.summary}
            </p>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <p style={{ fontSize: '0.72rem', color: '#34d399', fontWeight: 600, marginBottom: 4 }}>STRENGTHS</p>
              {data.explanation.pros?.map((p: string, i: number) => (
                <p key={i} style={{
                  padding: '5px 8px', borderRadius: 5, marginBottom: 3,
                  background: 'rgba(16,185,129,0.06)', borderLeft: '3px solid #10b981',
                  fontSize: '0.78rem', color: 'var(--text-secondary)',
                }}>✅ {p}</p>
              ))}
            </div>
            <div>
              <p style={{ fontSize: '0.72rem', color: '#f87171', fontWeight: 600, marginBottom: 4 }}>WEAKNESSES</p>
              {data.explanation.cons?.map((c: string, i: number) => (
                <p key={i} style={{
                  padding: '5px 8px', borderRadius: 5, marginBottom: 3,
                  background: 'rgba(239,68,68,0.06)', borderLeft: '3px solid #ef4444',
                  fontSize: '0.78rem', color: 'var(--text-secondary)',
                }}>❌ {c}</p>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
