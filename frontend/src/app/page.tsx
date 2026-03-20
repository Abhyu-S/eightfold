'use client';

import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import toast from 'react-hot-toast';
import { useDropzone } from 'react-dropzone';
import {
  Cpu, Upload, FileText, Search, Zap, BriefcaseBusiness,
  ChevronDown, ChevronUp, Shield, BarChart3, MessageSquare,
  GitGraph, Github, Loader,
} from 'lucide-react';
import DebateTimeline from '@/components/DebateTimeline';
import SkillGraph from '@/components/SkillGraph';
import ReportCard from '@/components/ReportCard';

const SAMPLE_JD = `We are looking for a Senior Python Backend Engineer with 4+ years of experience.

Required Skills:
- Python, FastAPI, PostgreSQL, Redis
- Docker, Kubernetes, AWS
- Experience with ML pipelines (scikit-learn, pandas)
- Strong computer science fundamentals

Bonus:
- Competitive programming background
- Open source contributions`;

export default function Home() {
  const [result, setResult] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [jdText, setJdText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [activeSection, setActiveSection] = useState<string>('report');

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted[0]) setFile(accepted[0]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop, accept: { 'application/pdf': ['.pdf'] }, maxFiles: 1,
  });

  const handleEvaluate = async () => {
    if (!jdText.trim()) { toast.error('Please enter a Job Description.'); return; }
    if (!file) { toast.error('Please upload a resume PDF.'); return; }

    setIsLoading(true);
    setResult(null);

    const formData = new FormData();
    formData.append('resume_pdf', file);
    formData.append('job_description', jdText);

    try {
      const res = await fetch('/api/evaluate', { method: 'POST', body: formData, signal: AbortSignal.timeout(180000) });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setResult(data);
      toast.success(`Evaluation complete! Score: ${data.final_score_pct}%`);
    } catch (err: any) {
      toast.error(`Evaluation failed: ${err.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleReset = () => {
    setResult(null);
    setFile(null);
    setJdText('');
    setActiveSection('report');
    toast.success('Reset complete.');
  };

  const sections = [
    { id: 'report', label: 'Report', icon: <BarChart3 size={14} /> },
    { id: 'skills', label: 'Skills', icon: <GitGraph size={14} /> },
    { id: 'debate', label: 'Debate', icon: <MessageSquare size={14} /> },
  ];

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
          {result && (
            <button className="btn-secondary" style={{ padding: '6px 14px', fontSize: '0.8rem' }} onClick={handleReset}>
              Reset
            </button>
          )}
        </div>
      </nav>

      {/* ── Hero ── */}
      {!result && !isLoading && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          style={{
            textAlign: 'center', padding: '52px 32px 32px',
            background: 'radial-gradient(ellipse 80% 40% at 50% 0%, rgba(59,130,246,0.08) 0%, transparent 70%)',
          }}
        >
          <div className="badge badge-blue" style={{ marginBottom: 16, fontSize: '0.8rem' }}>
            <Zap size={12} /> Multi-Agent System · FAISS · Skill Graphs · Bias-Free
          </div>
          <h1 style={{ fontSize: 'clamp(2rem, 5vw, 3rem)', fontWeight: 800, lineHeight: 1.15, marginBottom: 12 }}>
            AI Resume{' '}
            <span style={{ background: 'var(--gradient-accent)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              Screener
            </span>
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '1rem', maxWidth: 560, margin: '0 auto' }}>
            Upload a resume, paste a job description, and let our AI agents evaluate, debate, and explain every decision with full transparency.
          </p>
        </motion.div>
      )}

      {/* ── Input Section ── */}
      {!result && (
        <div style={{ maxWidth: 900, margin: '0 auto', padding: '16px 32px 48px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
            {/* Resume Upload */}
            <div className="glass" style={{ borderRadius: 14, padding: 20 }}>
              <h3 style={{ fontWeight: 700, fontSize: '0.95rem', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 7 }}>
                <FileText size={16} /> Resume Upload
              </h3>
              <div {...getRootProps()} style={{
                border: `2px dashed ${isDragActive ? 'var(--accent-blue)' : 'var(--border)'}`,
                borderRadius: 10, padding: '32px 16px', textAlign: 'center', cursor: 'pointer',
                background: isDragActive ? 'rgba(59,130,246,0.05)' : 'var(--bg-secondary)',
                transition: 'all 0.2s', minHeight: 120,
                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              }}>
                <input {...getInputProps()} />
                {file ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <FileText size={22} color="#34d399" />
                    <span style={{ fontWeight: 500, color: '#34d399', fontSize: '0.9rem' }}>{file.name}</span>
                  </div>
                ) : (
                  <>
                    <Upload size={32} style={{ color: 'var(--text-muted)', marginBottom: 8 }} />
                    <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                      {isDragActive ? 'Drop it here!' : 'Drag & drop PDF, or click'}
                    </p>
                  </>
                )}
              </div>
            </div>

            {/* Job Description */}
            <div className="glass" style={{ borderRadius: 14, padding: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
                <h3 style={{ fontWeight: 700, fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: 7 }}>
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
                rows={6}
                placeholder="Paste your job description here…"
                value={jdText}
                onChange={e => setJdText(e.target.value)}
                style={{ resize: 'vertical', lineHeight: 1.6 }}
              />
            </div>
          </div>

          {/* Evaluate Button */}
          <motion.button
            className="btn-primary"
            style={{
              width: '100%', justifyContent: 'center', padding: '16px',
              fontSize: '1rem', marginTop: 20, borderRadius: 12,
            }}
            onClick={handleEvaluate}
            disabled={isLoading}
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.99 }}
          >
            {isLoading ? (
              <>
                <Loader size={18} className="spin" />
                AI Agents Working… (this may take 30-90s)
              </>
            ) : (
              <><Search size={18} /> Evaluate Candidate</>
            )}
          </motion.button>

          {/* Loading skeleton */}
          {isLoading && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              style={{ marginTop: 24, display: 'flex', flexDirection: 'column', gap: 12 }}
            >
              {['Extracting PDF text...', 'Redacting PII...', 'Scraping GitHub...', 'Computing scores...', 'Running debate...'].map((step, i) => (
                <motion.div
                  key={step}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 4 }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '10px 16px', borderRadius: 8,
                    background: 'rgba(59,130,246,0.05)', border: '1px solid rgba(59,130,246,0.12)',
                    fontSize: '0.82rem', color: 'var(--text-secondary)',
                  }}
                >
                  <div className="spin" style={{ width: 14, height: 14 }}>
                    <Cpu size={14} color="#3b82f6" />
                  </div>
                  {step}
                </motion.div>
              ))}
            </motion.div>
          )}
        </div>
      )}

      {/* ── Results Section ── */}
      {result && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          style={{ maxWidth: 1100, margin: '0 auto', padding: '24px 32px 48px' }}
        >
          {/* Section tabs */}
          <div style={{
            display: 'flex', gap: 4, marginBottom: 20, padding: 4,
            background: 'var(--bg-card)', borderRadius: 10, border: '1px solid var(--border)',
            maxWidth: 400,
          }}>
            {sections.map(s => (
              <button
                key={s.id}
                onClick={() => setActiveSection(s.id)}
                style={{
                  flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                  padding: '8px 0', borderRadius: 7, border: 'none', cursor: 'pointer',
                  fontWeight: 600, fontSize: '0.85rem', transition: 'all 0.2s',
                  background: activeSection === s.id ? 'var(--gradient-accent)' : 'transparent',
                  color: activeSection === s.id ? 'white' : 'var(--text-secondary)',
                }}
              >
                {s.icon} {s.label}
              </button>
            ))}
          </div>

          {/* Content */}
          <AnimatePresence mode="wait">
            {activeSection === 'report' && (
              <motion.div key="report" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -10 }}>
                <div className="section-card">
                  <div className="section-header">
                    <BarChart3 size={18} color="var(--accent-blue)" /> Evaluation Report
                  </div>
                  <ReportCard data={result} />
                </div>
              </motion.div>
            )}

            {activeSection === 'skills' && (
              <motion.div key="skills" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -10 }}>
                <div className="section-card">
                  <div className="section-header">
                    <GitGraph size={18} color="var(--accent-green)" /> Skill Analysis
                  </div>
                  <SkillGraph
                    matched={result.skills?.matched || []}
                    missing={result.skills?.missing || []}
                    extra={result.skills?.extra || []}
                    verified={result.skills?.verified || []}
                    unverified={result.skills?.unverified || []}
                    matchPercentage={result.skills?.match_percentage || 0}
                    skillMatches={result.skill_matches || []}
                  />
                </div>
              </motion.div>
            )}

            {activeSection === 'debate' && (
              <motion.div key="debate" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -10 }}>
                <div className="section-card">
                  <div className="section-header">
                    <MessageSquare size={18} color="var(--accent-purple)" /> Multi-Agent Debate
                    <span className="badge badge-purple" style={{ marginLeft: 8 }}>
                      {result.debate?.num_rounds || 0} rounds
                    </span>
                  </div>
                  <DebateTimeline
                    rounds={result.debate?.rounds || []}
                    log={result.debate?.log || []}
                    verdict={result.debate?.verdict || null}
                  />
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Raw JSON toggle */}
          <details style={{ marginTop: 16 }}>
            <summary style={{
              cursor: 'pointer', color: 'var(--text-muted)', fontSize: '0.82rem',
              padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border)',
              background: 'var(--bg-card)',
            }}>
              🔧 Raw API Response
            </summary>
            <pre style={{
              background: 'var(--bg-secondary)', border: '1px solid var(--border)',
              borderRadius: '0 0 8px 8px', padding: 16,
              fontSize: '0.72rem', color: 'var(--text-secondary)',
              overflow: 'auto', maxHeight: 400,
            }}>
              {JSON.stringify(result, null, 2)}
            </pre>
          </details>
        </motion.div>
      )}
    </div>
  );
}
