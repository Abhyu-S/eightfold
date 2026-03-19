'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import toast from 'react-hot-toast';
import { Cpu, Users, Search, Zap, ChevronDown, Trash2 } from 'lucide-react';
import UploadPanel from '@/components/UploadPanel';
import JDPanel from '@/components/JDPanel';
import CandidateCard from '@/components/CandidateCard';
import StatsBar from '@/components/StatsBar';

export interface MatchResult {
  candidate_id: string;
  rank: number;
  match_score: number;
  final_score: number;
  verified_skills: string[];
  unverified_claims: string[];
  verification_rate: number;
  trajectory_score: number;
  explanation: string;
  top_language: string;
  cf_rank: string | null;
  cf_max_rating: number | null;
}

export default function Home() {
  const [candidates, setCandidates] = useState<MatchResult[]>([]);
  const [isMatching, setIsMatching] = useState(false);
  const [jdText, setJdText] = useState('');
  const [activeTab, setActiveTab] = useState<'upload' | 'jd'>('upload');
  const [candidateCount, setCandidateCount] = useState(0);

  const handleMatch = async () => {
    if (!jdText.trim()) {
      toast.error('Please enter a Job Description first.');
      return;
    }
    if (candidateCount === 0) {
      toast.error('Upload at least one candidate before matching.');
      return;
    }

    setIsMatching(true);
    setCandidates([]);
    try {
      const res = await fetch('/api/match', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jd_text: jdText, top_k: 10 }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data: MatchResult[] = await res.json();
      setCandidates(data);
      toast.success(`Ranked ${data.length} candidates successfully!`);
    } catch (err: any) {
      toast.error(`Matching failed: ${err.message}`);
    } finally {
      setIsMatching(false);
    }
  };

  const handleReset = async () => {
    try {
      await fetch('/api/reset', { method: 'DELETE' });
      setCandidates([]);
      setCandidateCount(0);
      toast.success('Pipeline reset successfully.');
    } catch {
      toast.error('Reset failed.');
    }
  };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>
      {/* ── Navbar ── */}
      <nav style={{
        position: 'sticky', top: 0, zIndex: 50,
        borderBottom: '1px solid var(--border)',
        background: 'rgba(2, 9, 23, 0.85)',
        backdropFilter: 'blur(20px)',
        padding: '0 32px',
        height: '64px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{
            width: 36, height: 36, borderRadius: '10px',
            background: 'var(--gradient-accent)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Cpu size={18} color="white" />
          </div>
          <span style={{ fontWeight: 700, fontSize: '1.1rem', background: 'var(--gradient-accent)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
            Eightfold AI
          </span>
          <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginLeft: 4 }}>Talent Intelligence</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span className="badge badge-green">
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#34d399', display: 'inline-block' }} />
            API Online
          </span>
          <button className="btn-secondary" style={{ padding: '6px 14px', fontSize: '0.8rem' }} onClick={handleReset}>
            <Trash2 size={14} /> Reset
          </button>
        </div>
      </nav>

      {/* ── Hero ── */}
      <div style={{
        textAlign: 'center', padding: '64px 32px 40px',
        background: 'radial-gradient(ellipse 80% 40% at 50% 0%, rgba(59,130,246,0.08) 0%, transparent 70%)',
      }}>
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
          <div className="badge badge-blue" style={{ marginBottom: 16, fontSize: '0.8rem' }}>
            <Zap size={12} /> Multi-Agent AI System · Skills-Verified · Bias-Free
          </div>
          <h1 style={{ fontSize: 'clamp(2rem, 5vw, 3.2rem)', fontWeight: 800, lineHeight: 1.15, marginBottom: 16 }}>
            Find the{' '}
            <span style={{ background: 'var(--gradient-accent)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              Right Talent
            </span>
            , Verified.
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '1.05rem', maxWidth: 560, margin: '0 auto' }}>
            Upload resumes, paste your JD, and let our AI agents verify real skills via GitHub, rank candidates intelligently, and explain every decision.
          </p>
        </motion.div>
      </div>

      {/* ── Stats Bar ── */}
      <StatsBar candidateCount={candidateCount} matchCount={candidates.length} />

      {/* ── Main Layout ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', gap: '24px', padding: '24px 32px', maxWidth: 1400, margin: '0 auto' }}>
        
        {/* ── Left Panel ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Tab switcher */}
          <div style={{ display: 'flex', background: 'var(--bg-card)', borderRadius: 10, padding: 4, border: '1px solid var(--border)' }}>
            {(['upload', 'jd'] as const).map((tab) => (
              <button key={tab} onClick={() => setActiveTab(tab)} style={{
                flex: 1, padding: '8px 0', borderRadius: 7, border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: '0.85rem', transition: 'all 0.2s',
                background: activeTab === tab ? 'var(--gradient-accent)' : 'transparent',
                color: activeTab === tab ? 'white' : 'var(--text-secondary)',
              }}>
                {tab === 'upload' ? '📄 Upload' : '💼 Job Description'}
              </button>
            ))}
          </div>

          <AnimatePresence mode="wait">
            {activeTab === 'upload' ? (
              <motion.div key="upload" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -10 }}>
                <UploadPanel onCandidateAdded={() => setCandidateCount(c => c + 1)} />
              </motion.div>
            ) : (
              <motion.div key="jd" initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 10 }}>
                <JDPanel jdText={jdText} setJdText={setJdText} />
              </motion.div>
            )}
          </AnimatePresence>

          {/* Match Button */}
          <motion.button
            className="btn-primary"
            style={{ width: '100%', justifyContent: 'center', padding: '14px', fontSize: '1rem' }}
            onClick={handleMatch}
            disabled={isMatching}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            {isMatching ? (
              <>
                <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}>
                  <Cpu size={18} />
                </motion.div>
                Agents Working…
              </>
            ) : (
              <><Search size={18} /> Match Candidates</>
            )}
          </motion.button>
        </div>

        {/* ── Right Panel: Results ── */}
        <div>
          {candidates.length === 0 && !isMatching && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                minHeight: 400, gap: 16, color: 'var(--text-muted)', textAlign: 'center',
              }}
            >
              <Users size={56} strokeWidth={1} />
              <p style={{ fontSize: '1.1rem', fontWeight: 500 }}>No candidates ranked yet</p>
              <p style={{ fontSize: '0.9rem' }}>Upload resumes, enter a JD, then click Match Candidates</p>
            </motion.div>
          )}

          {isMatching && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {[1, 2, 3].map(i => (
                <div key={i} className="skeleton" style={{ height: 140, borderRadius: 12 }} />
              ))}
            </div>
          )}

          <AnimatePresence>
            {candidates.map((c, i) => (
              <motion.div
                key={c.candidate_id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.08 }}
              >
                <CandidateCard candidate={c} />
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
