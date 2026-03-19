'use client';

import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { motion } from 'framer-motion';
import toast from 'react-hot-toast';
import { Upload, FileText, Github, Code, CheckCircle, Loader } from 'lucide-react';

interface Props {
  onCandidateAdded: () => void;
}

export default function UploadPanel({ onCandidateAdded }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [github, setGithub] = useState('');
  const [codeforces, setCodeforces] = useState('');
  const [loading, setLoading] = useState(false);
  const [uploadedIds, setUploadedIds] = useState<string[]>([]);

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted[0]) setFile(accepted[0]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop, accept: { 'application/pdf': ['.pdf'] }, maxFiles: 1,
  });

  const handleUpload = async () => {
    if (!file) { toast.error('Please drop a PDF resume.'); return; }

    setLoading(true);
    const formData = new FormData();
    formData.append('resume', file);
    formData.append('github_username', github.trim());
    formData.append('codeforces_handle', codeforces.trim());

    try {
      const res = await fetch('/api/upload-candidate', { method: 'POST', body: formData });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      toast.success(`✅ ${data.candidate_id} ingested! ${data.skills_found} skills found.`);
      setUploadedIds(prev => [...prev, data.candidate_id]);
      onCandidateAdded();
      setFile(null);
      setGithub('');
      setCodeforces('');
    } catch (err: any) {
      toast.error(`Upload failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass" style={{ borderRadius: 12, padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <h3 style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--text-primary)' }}>
        📄 Upload Candidate
      </h3>

      {/* Dropzone */}
      <div {...getRootProps()} style={{
        border: `2px dashed ${isDragActive ? 'var(--accent-blue)' : 'var(--border)'}`,
        borderRadius: 10, padding: '24px 16px', textAlign: 'center', cursor: 'pointer',
        background: isDragActive ? 'rgba(59,130,246,0.05)' : 'var(--bg-secondary)',
        transition: 'all 0.2s',
      }}>
        <input {...getInputProps()} />
        {file ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, justifyContent: 'center' }}>
            <FileText size={20} color="#34d399" />
            <span style={{ fontWeight: 500, color: '#34d399', fontSize: '0.9rem' }}>{file.name}</span>
          </div>
        ) : (
          <>
            <Upload size={28} style={{ color: 'var(--text-muted)', margin: '0 auto 8px' }} />
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              {isDragActive ? 'Drop it here!' : 'Drag & drop a PDF, or click to browse'}
            </p>
          </>
        )}
      </div>

      {/* GitHub */}
      <div>
        <label style={{ fontSize: '0.78rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 5, marginBottom: 5 }}>
          <Github size={12} /> GitHub Username <span style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>(optional)</span>
        </label>
        <input className="input-field" placeholder="e.g. torvalds" value={github} onChange={e => setGithub(e.target.value)} />
      </div>

      {/* Codeforces */}
      <div>
        <label style={{ fontSize: '0.78rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 5, marginBottom: 5 }}>
          <Code size={12} /> Codeforces Handle <span style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>(optional)</span>
        </label>
        <input className="input-field" placeholder="e.g. tourist" value={codeforces} onChange={e => setCodeforces(e.target.value)} />
      </div>

      <button className="btn-primary" onClick={handleUpload} disabled={loading} style={{ justifyContent: 'center' }}>
        {loading ? <><Loader size={16} className="spin" /> Processing…</> : <><Upload size={16} /> Ingest Candidate</>}
      </button>

      {/* Uploaded list */}
      {uploadedIds.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Uploaded this session:</p>
          {uploadedIds.map(id => (
            <div key={id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.8rem', color: '#34d399' }}>
              <CheckCircle size={12} /> {id}
            </div>
          ))}
        </div>
      )}

      <style>{`.spin { animation: spin 1s linear infinite; } @keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
