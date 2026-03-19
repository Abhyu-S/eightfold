'use client';

import { Users, FileCheck, Brain } from 'lucide-react';

interface Props {
  candidateCount: number;
  matchCount: number;
}

export default function StatsBar({ candidateCount, matchCount }: Props) {
  const stats = [
    { icon: <Users size={16} />, label: 'Candidates Uploaded', value: candidateCount, color: '#3b82f6' },
    { icon: <FileCheck size={16} />, label: 'Candidates Ranked', value: matchCount, color: '#10b981' },
    { icon: <Brain size={16} />, label: 'AI Agents Active', value: 3, color: '#8b5cf6' },
  ];

  return (
    <div style={{ display: 'flex', gap: 0, justifyContent: 'center', padding: '0 32px 24px', maxWidth: 1400, margin: '0 auto' }}>
      {stats.map((s, i) => (
        <div key={s.label} style={{
          flex: 1, maxWidth: 240,
          display: 'flex', alignItems: 'center', gap: 12,
          padding: '12px 20px',
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderLeft: i === 0 ? '1px solid var(--border)' : 'none',
          borderRadius: i === 0 ? '10px 0 0 10px' : i === stats.length - 1 ? '0 10px 10px 0' : 0,
        }}>
          <div style={{ color: s.color }}>{s.icon}</div>
          <div>
            <div style={{ fontSize: '1.2rem', fontWeight: 700, color: s.color }}>{s.value}</div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{s.label}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
