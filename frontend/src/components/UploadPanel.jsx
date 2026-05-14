/**
 * UploadPanel.jsx — Panel 2: Upload Dataset
 * 
 * "Terminal Precision" aesthetic.
 * Centered layout with drop zone and connectors.
 */
import React, { useState, useRef, useCallback } from "react";
import { 
  Upload, FileSpreadsheet, AlertCircle, Loader2, ArrowLeft,
  Sparkles, Shield, Zap, BarChart2, Database, FileText,
  CheckCircle2, Link
} from "lucide-react";
import { uploadDataset, uploadPastedCSV } from "../services/api";
import SampleDatasetsPanel from "./SampleDatasetsPanel";
import ConnectorsPanel from "./ConnectorsPanel";

// ══════════════════════════════════════════════════════════════════════════════
// STYLES
// ══════════════════════════════════════════════════════════════════════════════

const STYLES = `
  .upload-root {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 40px 20px 60px;
    overflow-y: auto;
  }

  .upload-main {
    width: 100%;
    max-width: 500px;
    display: flex;
    flex-direction: column;
    gap: 24px;
  }

  /* Title */
  .upload-title {
    text-align: center;
    margin-bottom: 8px;
  }

  .upload-title h1 {
    font-size: 28px;
    font-weight: 700;
    color: var(--text-0);
    margin: 0 0 8px;
    letter-spacing: -0.02em;
  }

  .upload-title p {
    font-size: 14px;
    color: var(--text-2);
    margin: 0;
    line-height: 1.6;
  }

  /* Feature pills */
  .upload-features {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px;
    margin-bottom: 8px;
  }

  .upload-feature {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 99px;
    font-size: 12px;
    color: var(--text-1);
    font-weight: 500;
  }

  .upload-feature svg { color: var(--accent); }
  .upload-feature span { color: var(--accent); font-weight: 600; }

  /* Drop zone */
  .upload-drop {
    position: relative;
    padding: 48px 32px;
    background: var(--surface-1);
    border: 2px dashed var(--border-2);
    border-radius: var(--radius-xl);
    text-align: center;
    cursor: pointer;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    overflow: hidden;
  }

  .upload-drop::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, var(--accent-dim) 0%, transparent 50%);
    opacity: 0;
    transition: opacity 0.2s ease;
  }

  .upload-drop:hover {
    border-color: var(--accent);
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
  }

  .upload-drop:hover::before { opacity: 1; }

  .upload-drop--over {
    border-color: var(--accent);
    border-style: solid;
    background: var(--surface-2);
    transform: scale(1.01);
    box-shadow: 0 0 30px var(--accent-glow);
  }

  .upload-drop--over::before { opacity: 1; }

  .upload-drop--busy {
    cursor: default;
    pointer-events: none;
  }

  .upload-drop-icon {
    width: 64px;
    height: 64px;
    margin: 0 auto 16px;
    border-radius: 50%;
    background: var(--surface-2);
    border: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    z-index: 1;
    transition: all 0.2s ease;
  }

  .upload-drop:hover .upload-drop-icon {
    background: var(--accent-dim);
    border-color: var(--accent);
    transform: scale(1.05);
  }

  .upload-drop--over .upload-drop-icon {
    background: var(--accent);
    border-color: var(--accent);
    transform: scale(1.1);
  }

  .upload-drop-icon svg { color: var(--text-2); transition: color 0.2s ease; }
  .upload-drop:hover .upload-drop-icon svg { color: var(--accent); }
  .upload-drop--over .upload-drop-icon svg { color: var(--bg); }

  .upload-drop-title {
    font-size: 16px;
    font-weight: 600;
    color: var(--text-0);
    margin: 0 0 4px;
    position: relative;
    z-index: 1;
  }

  .upload-drop-hint {
    font-size: 13px;
    color: var(--text-2);
    margin: 0;
    position: relative;
    z-index: 1;
  }

  .upload-drop-link {
    color: var(--accent);
    font-weight: 600;
    cursor: pointer;
  }

  .upload-drop-link:hover { color: var(--accent-light); text-decoration: underline; }

  .upload-drop-formats {
    display: flex;
    justify-content: center;
    gap: 8px;
    margin-top: 16px;
    position: relative;
    z-index: 1;
  }

  .upload-drop-chip {
    padding: 4px 10px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 11px;
    font-weight: 700;
    color: var(--text-2);
    letter-spacing: 0.05em;
  }

  .upload-drop-limit {
    font-size: 11px;
    color: var(--text-3);
    margin-left: 8px;
  }

  /* Hidden file input */
  .upload-drop input[type="file"] {
    display: none;
  }

  /* Progress */
  .upload-progress {
    position: relative;
    z-index: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 16px;
  }

  .upload-progress-ring {
    position: relative;
    width: 80px;
    height: 80px;
  }

  .upload-progress-ring svg {
    transform: rotate(-90deg);
  }

  .upload-progress-ring circle {
    fill: none;
    stroke-width: 4;
    stroke-linecap: round;
  }

  .upload-progress-ring .bg {
    stroke: var(--surface-2);
  }

  .upload-progress-ring .progress {
    stroke: var(--accent);
    stroke-dasharray: 226;
    stroke-dashoffset: 226;
    transition: stroke-dashoffset 0.3s ease;
    filter: drop-shadow(0 0 6px var(--accent-glow));
  }

  .upload-progress-pct {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    color: var(--accent);
  }

  .upload-progress-label {
    font-size: 14px;
    color: var(--text-1);
    font-weight: 500;
  }

  .upload-progress-bar {
    width: 100%;
    max-width: 240px;
    height: 4px;
    background: var(--surface-2);
    border-radius: 2px;
    overflow: hidden;
  }

  .upload-progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--accent), var(--secondary));
    border-radius: 2px;
    transition: width 0.3s ease;
    box-shadow: 0 0 10px var(--accent-glow);
  }

  /* Paste toggle */
  .upload-paste-toggle {
    display: flex;
    justify-content: center;
  }

  .upload-paste-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    background: none;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    color: var(--text-2);
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .upload-paste-btn:hover {
    border-color: var(--border-2);
    color: var(--text-1);
    background: var(--surface-1);
  }

  .upload-paste-btn--active {
    border-color: var(--accent);
    color: var(--accent);
    background: var(--accent-dim);
  }

  /* Paste area */
  .upload-paste-area {
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .upload-paste-area textarea {
    width: 100%;
    min-height: 160px;
    padding: 12px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    color: var(--text-0);
    font-size: 12px;
    font-family: 'JetBrains Mono', monospace;
    line-height: 1.6;
    resize: vertical;
    outline: none;
    transition: border-color 0.2s ease;
  }

  .upload-paste-area textarea:focus {
    border-color: var(--accent);
  }

  .upload-paste-area textarea::placeholder {
    color: var(--text-3);
  }

  .upload-paste-submit {
    display: flex;
    justify-content: flex-end;
  }

  .upload-paste-submit button {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 10px 20px;
    background: linear-gradient(135deg, var(--accent) 0%, var(--secondary) 100%);
    border: none;
    border-radius: var(--radius-md);
    color: var(--bg);
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .upload-paste-submit button:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 4px 16px rgba(0,212,170,0.3);
  }

  .upload-paste-submit button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* Error */
  .upload-error {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
    background: rgba(239,68,68,0.1);
    border: 1px solid rgba(239,68,68,0.25);
    border-radius: var(--radius-md);
    font-size: 13px;
    color: #fca5a5;
  }

  /* Secondary cards */
  .upload-section {
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 20px;
  }

  .upload-section-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-1);
    margin: 0 0 16px;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .upload-section-title svg { color: var(--accent); }

  /* Back link */
  .upload-back {
    display: flex;
    justify-content: center;
    margin-top: 8px;
  }

  .upload-back-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: none;
    border: none;
    color: var(--text-2);
    font-size: 13px;
    cursor: pointer;
    padding: 6px 12px;
    border-radius: var(--radius-md);
    transition: all 0.2s ease;
  }

  .upload-back-btn:hover {
    color: var(--text-1);
    background: var(--surface-1);
  }
`;

// ══════════════════════════════════════════════════════════════════════════════
// CONSTANTS
// ══════════════════════════════════════════════════════════════════════════════

const ACCEPTED = ['.csv', '.xlsx', '.xls'];

const FEATURES = [
  { icon: Sparkles, label: '55+ transforms' },
  { icon: Zap, label: 'AI insights' },
  { icon: Shield, label: 'PII detection' },
  { icon: BarChart2, label: 'Profiling' },
  { icon: Database, label: 'SQL queries' },
];

// ══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ══════════════════════════════════════════════════════════════════════════════

export default function UploadPanel({ userRole, onUploadComplete, onBack }) {
  const [dragging,   setDragging]   = useState(false);
  const [progress,   setProgress]   = useState(0);
  const [uploading,  setUploading]  = useState(false);
  const [error,      setError]      = useState('');
  const [pasteMode,  setPasteMode]  = useState(false);
  const [pasteText,  setPasteText]  = useState('');
  const inputRef = useRef();

  const handleFile = useCallback(async (file) => {
    if (!file) return;
    
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!ACCEPTED.includes(ext)) {
      setError(`Unsupported format "${ext}". Please upload CSV, XLSX, or XLS.`);
      return;
    }

    setError('');
    setUploading(true);
    setProgress(0);

    try {
      const session = await uploadDataset(file, (pct) => setProgress(pct));
      onUploadComplete(session);
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Upload failed. Please try again.');
      setUploading(false);
    }
  }, [onUploadComplete]);

  const handlePaste = useCallback(async () => {
    const text = pasteText.trim();
    if (!text) return;

    setError('');
    setUploading(true);
    setProgress(0);

    try {
      const session = await uploadPastedCSV(text);
      onUploadComplete(session);
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Failed to parse pasted CSV. Please check the format.');
      setUploading(false);
    }
  }, [pasteText, onUploadComplete]);

  const onDragOver  = (e) => { e.preventDefault(); setDragging(true); };
  const onDragLeave = () => setDragging(false);
  const onDrop      = (e) => {
    e.preventDefault();
    setDragging(false);
    handleFile(e.dataTransfer.files[0]);
  };

  // SVG progress ring calculation
  const radius = 36;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (progress / 100) * circumference;

  return (
    <>
      <style>{STYLES}</style>
      <div className="upload-root">
        <div className="upload-main">
          
          {/* Title */}
          <div className="upload-title">
            <h1>Upload your dataset</h1>
            <p>Drop a file or connect a source to get started with AI-powered cleaning</p>
          </div>

          {/* Feature pills */}
          <div className="upload-features">
            {FEATURES.map(({ icon: Icon, label }) => (
              <div key={label} className="upload-feature">
                <Icon size={14} />
                <span>{label.split(' ')[0]}</span>
                {label.split(' ').slice(1).join(' ')}
              </div>
            ))}
          </div>

          {/* Drop zone */}
          <div
            className={`upload-drop ${dragging ? 'upload-drop--over' : ''} ${uploading ? 'upload-drop--busy' : ''}`}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            onClick={() => !uploading && inputRef.current?.click()}
          >
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPTED.join(',')}
              onChange={e => handleFile(e.target.files[0])}
            />

            {uploading ? (
              <div className="upload-progress">
                <div className="upload-progress-ring">
                  <svg width="80" height="80" viewBox="0 0 80 80">
                    <circle className="bg" cx="40" cy="40" r={radius} />
                    <circle 
                      className="progress" 
                      cx="40" 
                      cy="40" 
                      r={radius}
                      style={{ strokeDashoffset }}
                    />
                  </svg>
                  <span className="upload-progress-pct">{progress}%</span>
                </div>
                <span className="upload-progress-label">Uploading & parsing…</span>
                <div className="upload-progress-bar">
                  <div className="upload-progress-fill" style={{ width: `${progress}%` }} />
                </div>
              </div>
            ) : (
              <>
                <div className="upload-drop-icon">
                  <Upload size={28} />
                </div>
                <p className="upload-drop-title">
                  {dragging ? 'Drop to upload' : 'Drag & drop your file here'}
                </p>
                <p className="upload-drop-hint">
                  or <span className="upload-drop-link">browse files</span>
                </p>
                <div className="upload-drop-formats">
                  {['CSV', 'XLSX', 'XLS'].map(f => (
                    <span key={f} className="upload-drop-chip">{f}</span>
                  ))}
                  <span className="upload-drop-limit">· Max 50 MB</span>
                </div>
              </>
            )}
          </div>

          {/* Paste toggle */}
          <div className="upload-paste-toggle">
            <button
              className={`upload-paste-btn ${pasteMode ? 'upload-paste-btn--active' : ''}`}
              onClick={() => setPasteMode(m => !m)}
            >
              <FileText size={14} />
              {pasteMode ? 'Upload file instead' : 'Paste CSV text'}
            </button>
          </div>

          {/* Paste area */}
          {pasteMode && (
            <div className="upload-paste-area">
              <textarea
                value={pasteText}
                onChange={e => setPasteText(e.target.value)}
                placeholder={`Paste your CSV data here...

id,name,email,score
1,Alice,alice@example.com,85
2,Bob,bob@example.com,92
3,Carol,carol@example.com,78`}
              />
              <div className="upload-paste-submit">
                <button disabled={!pasteText.trim() || uploading} onClick={handlePaste}>
                  {uploading ? (
                    <Loader2 size={14} className="spin" />
                  ) : (
                    <CheckCircle2 size={14} />
                  )}
                  Load CSV data
                </button>
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="upload-error">
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          {/* Sample datasets */}
          <div className="upload-section">
            <h3 className="upload-section-title">
              <Sparkles size={16} />
              Or try a sample dataset
            </h3>
            <SampleDatasetsPanel />
          </div>

          {/* Connectors */}
          <div className="upload-section">
            <h3 className="upload-section-title">
              <Link size={16} />
              Connect a data source
            </h3>
            <ConnectorsPanel />
          </div>

          {/* Back link */}
          <div className="upload-back">
            <button className="upload-back-btn" onClick={onBack}>
              <ArrowLeft size={14} />
              Back to sign in
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
