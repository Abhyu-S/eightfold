'use client';

import toast from 'react-hot-toast';
import { BriefcaseBusiness, Save } from 'lucide-react';

interface Props {
  jdText: string;
  setJdText: (v: string) => void;
}

const SAMPLE_JD = `We are looking for a Senior Python Backend Engineer with 4+ years of experience.

Required Skills:
- Python, FastAPI, PostgreSQL, Redis
- Docker, Kubernetes, AWS
- Experience with ML pipelines (scikit-learn, pandas)
- Strong computer science fundamentals

Bonus:
- Competitive programming background
- Open source contributions`;

export default function JDPanel({ jdText, setJdText }: Props) {
  const handleSaveJD = async () => {
    if (!jdText.trim()) { toast.error('Enter a job description first.'); return; }
    try {
      const res = await fetch('/api/add-jd', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jd_text: jdText, jd_id: 'active_jd' }),
      });
      if (!res.ok) throw new Error(await res.text());
      toast.success('JD stored in vector DB ✅');
    } catch (err: any) {
      toast.error(`Failed: ${err.message}`);
    }
  };

  return (
    <div className="glass" style={{ borderRadius: 12, padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h3 style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 7 }}>
          <BriefcaseBusiness size={16} /> Job Description
        </h3>
        <button
          style={{ fontSize: '0.75rem', color: 'var(--accent-blue)', background: 'none', border: 'none', cursor: 'pointer' }}
          onClick={() => setJdText(SAMPLE_JD)}
        >
          Use Sample
        </button>
      </div>

      <textarea
        className="input-field"
        rows={12}
        placeholder="Paste your job description here…"
        value={jdText}
        onChange={e => setJdText(e.target.value)}
        style={{ resize: 'vertical', lineHeight: 1.6 }}
      />

      <button className="btn-secondary" onClick={handleSaveJD} style={{ justifyContent: 'center' }}>
        <Save size={15} /> Save to Vector DB
      </button>

      <p style={{ fontSize: '0.73rem', color: 'var(--text-muted)', textAlign: 'center' }}>
        The JD is automatically used when you click "Match Candidates"
      </p>
    </div>
  );
}
