'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, ChevronUp, CheckCircle, AlertTriangle, Shield } from 'lucide-react';

interface DebateEntry {
  timestamp: string;
  agent: string;
  content: string;
  round_num: number;
  entry_type: string;
}

interface DebateRound {
  round: number;
  advocate: any;
  critic: any;
  fairness: any;
}

interface Props {
  rounds: DebateRound[];
  log: DebateEntry[];
  verdict: any;
}

function AgentBadge({ agent }: { agent: string }) {
  const config: Record<string, { emoji: string; color: string; label: string }> = {
    advocate: { emoji: '🟢', color: '#34d399', label: 'Advocate' },
    critic: { emoji: '🔴', color: '#f87171', label: 'Critic' },
    fairness: { emoji: '🔵', color: '#60a5fa', label: 'Fairness' },
    orchestrator: { emoji: '⚖️', color: '#a78bfa', label: 'Judge' },
  };
  const c = config[agent] || { emoji: '📝', color: '#94a3b8', label: agent };
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '2px 10px', borderRadius: 999,
      background: `${c.color}15`, border: `1px solid ${c.color}30`,
      color: c.color, fontSize: '0.75rem', fontWeight: 600,
    }}>
      {c.emoji} {c.label}
    </span>
  );
}

function ArgumentList({ items, color }: { items: string[]; color: string }) {
  if (!items || items.length === 0) return null;
  return (
    <ul style={{ listStyle: 'none', padding: 0, margin: '6px 0 0', display: 'flex', flexDirection: 'column', gap: 4 }}>
      {items.map((item, i) => (
        <li key={i} style={{
          padding: '6px 10px', borderRadius: 6,
          background: `${color}08`, borderLeft: `3px solid ${color}`,
          fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.5,
        }}>
          {item}
        </li>
      ))}
    </ul>
  );
}

export default function DebateTimeline({ rounds, log, verdict }: Props) {
  const [expandedRound, setExpandedRound] = useState<number | null>(1);

  if (!rounds || rounds.length === 0) {
    return (
      <div className="section-card" style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 40 }}>
        <Shield size={40} strokeWidth={1} style={{ margin: '0 auto 12px', display: 'block' }} />
        <p>No debate data available</p>
      </div>
    );
  }

  return (
    <div>
      <div className="debate-timeline">
        {rounds.map((round) => (
          <div key={round.round}>
            {/* Round header */}
            <div
              className="debate-entry"
              style={{ cursor: 'pointer', background: 'rgba(59,130,246,0.05)' }}
              onClick={() => setExpandedRound(expandedRound === round.round ? null : round.round)}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--accent-blue)' }}>
                    Round {round.round}
                  </span>
                  <AgentBadge agent="advocate" />
                  <AgentBadge agent="critic" />
                  <AgentBadge agent="fairness" />
                </div>
                {expandedRound === round.round ? <ChevronUp size={16} color="var(--text-muted)" /> : <ChevronDown size={16} color="var(--text-muted)" />}
              </div>
            </div>

            {/* Expanded content */}
            <AnimatePresence>
              {expandedRound === round.round && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.25 }}
                  style={{ overflow: 'hidden' }}
                >
                  {/* Advocate */}
                  <div className="debate-entry advocate" style={{ marginLeft: 8 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                      <AgentBadge agent="advocate" />
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>argues FOR hiring</span>
                    </div>
                    {round.advocate?.overall_assessment && (
                      <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: 8, fontStyle: 'italic' }}>
                        "{round.advocate.overall_assessment}"
                      </p>
                    )}
                    <ArgumentList items={round.advocate?.key_arguments} color="#10b981" />
                    {round.advocate?.skill_highlights?.length > 0 && (
                      <div style={{ marginTop: 8 }}>
                        <p style={{ fontSize: '0.72rem', color: '#34d399', fontWeight: 600, marginBottom: 4 }}>SKILL HIGHLIGHTS</p>
                        <ArgumentList items={round.advocate.skill_highlights} color="#10b981" />
                      </div>
                    )}
                  </div>

                  {/* Critic */}
                  <div className="debate-entry critic" style={{ marginLeft: 8 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                      <AgentBadge agent="critic" />
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>argues AGAINST hiring</span>
                    </div>
                    {round.critic?.overall_assessment && (
                      <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: 8, fontStyle: 'italic' }}>
                        "{round.critic.overall_assessment}"
                      </p>
                    )}
                    <ArgumentList items={round.critic?.key_concerns} color="#ef4444" />
                    {round.critic?.skill_gaps?.length > 0 && (
                      <div style={{ marginTop: 8 }}>
                        <p style={{ fontSize: '0.72rem', color: '#f87171', fontWeight: 600, marginBottom: 4 }}>SKILL GAPS</p>
                        <ArgumentList items={round.critic.skill_gaps} color="#ef4444" />
                      </div>
                    )}
                  </div>

                  {/* Fairness */}
                  <div className="debate-entry fairness" style={{ marginLeft: 8 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                      <AgentBadge agent="fairness" />
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>fact-checking both sides</span>
                    </div>
                    <div style={{ display: 'flex', gap: 12, marginBottom: 8, flexWrap: 'wrap' }}>
                      <span className="badge badge-green">Advocate: {round.fairness?.advocate_accuracy || 'N/A'}</span>
                      <span className="badge badge-red">Critic: {round.fairness?.critic_accuracy || 'N/A'}</span>
                    </div>
                    {round.fairness?.balanced_summary && (
                      <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                        {round.fairness.balanced_summary}
                      </p>
                    )}
                    {round.fairness?.fact_checks?.length > 0 && (
                      <div style={{ marginTop: 10 }}>
                        <p style={{ fontSize: '0.72rem', color: '#60a5fa', fontWeight: 600, marginBottom: 6 }}>FACT CHECKS</p>
                        {round.fairness.fact_checks.slice(0, 4).map((fc: any, i: number) => (
                          <div key={i} style={{
                            padding: '6px 10px', borderRadius: 6, marginBottom: 4,
                            background: fc.verdict === 'accurate' ? 'rgba(16,185,129,0.06)' : 'rgba(245,158,11,0.06)',
                            borderLeft: `3px solid ${fc.verdict === 'accurate' ? '#10b981' : '#f59e0b'}`,
                            fontSize: '0.78rem', color: 'var(--text-secondary)',
                          }}>
                            <span style={{ fontWeight: 600, textTransform: 'uppercase', fontSize: '0.68rem',
                              color: fc.verdict === 'accurate' ? '#34d399' : '#fbbf24' }}>
                              {fc.verdict}
                            </span>
                            {' · '}{fc.claimed_by}: {fc.claim}
                            {fc.correction && <span style={{ color: '#60a5fa' }}> → {fc.correction}</span>}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        ))}

        {/* Verdict */}
        {verdict && (
          <div className="debate-entry verdict" style={{ borderColor: 'rgba(139,92,246,0.4)', background: 'rgba(139,92,246,0.05)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <AgentBadge agent="orchestrator" />
              <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#a78bfa' }}>FINAL VERDICT</span>
            </div>
            <p style={{ fontSize: '0.9rem', color: 'var(--text-primary)', lineHeight: 1.65, marginBottom: 12 }}>
              {verdict.verdict_summary}
            </p>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 200 }}>
                <p style={{ fontSize: '0.72rem', color: '#34d399', fontWeight: 600, marginBottom: 6 }}>
                  <CheckCircle size={11} style={{ display: 'inline', marginRight: 4 }} />
                  STRENGTHS
                </p>
                <ArgumentList items={verdict.key_strengths} color="#10b981" />
              </div>
              <div style={{ flex: 1, minWidth: 200 }}>
                <p style={{ fontSize: '0.72rem', color: '#f87171', fontWeight: 600, marginBottom: 6 }}>
                  <AlertTriangle size={11} style={{ display: 'inline', marginRight: 4 }} />
                  CONCERNS
                </p>
                <ArgumentList items={verdict.key_concerns} color="#ef4444" />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
