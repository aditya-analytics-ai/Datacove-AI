/**
 * UploadPage v6 — Excel-ribbon inspired layout.
 * Top nav bar like Excel's "File" menu area, then a ribbon of features,
 * then the central drop zone, then a status bar at the bottom.
 */
import React, { useState, useRef, useCallback } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  Upload, FileSpreadsheet, AlertCircle, Loader2,
  Sparkles, ShieldCheck, Zap, Database, BarChart2,
  GitBranch, Search, Table2, Wand2, Bot, FileDown,
} from "lucide-react";
import { uploadDataset, uploadPastedCSV } from "../services/api";
import { useTheme } from "../context/ThemeContext";
import SampleDatasetsPanel from "../components/SampleDatasetsPanel";
import ConnectorsPanel     from "../components/ConnectorsPanel";

const ACCEPTED = [".csv", ".xlsx", ".xls"];

const RIBBON_TABS = [
  {
    name: "Clean",
    icon: Wand2,
    color: "var(--accent)",
    items: [
      { icon: Trash2_,    label: "Remove Dupes",    desc: "Exact & fuzzy dedup" },
      { icon: Whitespace_, label: "Trim Whitespace", desc: "Strip extra spaces" },
      { icon: Fill_,       label: "Fill Missing",    desc: "Mean/median/mode fill" },
      { icon: Normalise_,  label: "Normalise Cats",  desc: "Fix category variants" },
    ],
  },
  {
    name: "Analyse",
    icon: BarChart2,
    color: "var(--cyan)",
    items: [
      { icon: BarChart2,   label: "Health Score",    desc: "0–100 quality rating" },
      { icon: Search,      label: "Issue Detector",  desc: "Find data problems" },
      { icon: BarChart2,   label: "Profiling",       desc: "Column-level stats" },
      { icon: ShieldCheck, label: "Validate Rules",  desc: "Custom constraints" },
    ],
  },
  {
    name: "AI",
    icon: Bot,
    color: "var(--accent)",
    items: [
      { icon: Bot,         label: "AI Agent",        desc: "Auto end-to-end clean" },
      { icon: Sparkles,    label: "AI Insights",     desc: "Smart suggestions" },
      { icon: Database,    label: "SQL Query",       desc: "DuckDB on your data" },
      { icon: Zap,         label: "NL Commands",     desc: "Plain English ops" },
    ],
  },
  {
    name: "Export",
    icon: FileDown,
    color: "var(--green)",
    items: [
      { icon: Table2,      label: "CSV",             desc: "Comma-separated" },
      { icon: FileSpreadsheet, label: "Excel XLSX",  desc: "Excel workbook" },
      { icon: Database,    label: "JSON",            desc: "JSON records" },
      { icon: GitBranch,   label: "Version History", desc: "Snapshots & rollback" },
    ],
  },
];

// Placeholder icon components (using lucide aliases)
function Trash2_({ size, style }) { return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={style}><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/></svg>; }
function Whitespace_({ size, style }) { return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={style}><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="2"/></svg>; }
function Fill_({ size, style }) { return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={style}><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>; }
function Normalise_({ size, style }) { return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={style}><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>; }

export default function UploadPage({ userRole, onLogout }) {
  const { theme, toggleTheme } = useTheme();
  const [dragging,   setDragging]   = useState(false);
  const [progress,   setProgress]   = useState(0);
  const [uploading,  setUploading]  = useState(false);
  const [error,      setError]      = useState("");
  const [activeTab,  setActiveTab]  = useState("Clean");
  const [pasteMode,  setPasteMode]  = useState(false);
  const [pasteText,  setPasteText]  = useState("");
  const inputRef  = useRef();
  const navigate  = useNavigate();

  const handleFile = useCallback(async (file) => {
    if (!file) return;
    const ext = "." + file.name.split(".").pop().toLowerCase();
    if (!ACCEPTED.includes(ext)) {
      setError(`Unsupported format "${ext}". Please upload CSV, XLSX, or XLS.`);
      return;
    }
    setError(""); setUploading(true); setProgress(0);
    try {
      navigate("/dashboard", { state: { session: await uploadDataset(file, setProgress) } });
    } catch (err) {
      setError(err?.response?.data?.detail ?? "Upload failed. Please try again.");
    } finally { setUploading(false); }
  }, [navigate]);

  // Handle pasted CSV text — posts JSON directly to /upload/paste endpoint
  const handlePaste = useCallback(async () => {
    const text = pasteText.trim();
    if (!text) return;
    setError(""); setUploading(true); setProgress(0);
    try {
      navigate("/dashboard", { state: { session: await uploadPastedCSV(text) } });
    } catch (err) {
      setError(err?.response?.data?.detail ?? "Failed to parse pasted CSV. Please check the format.");
    } finally { setUploading(false); }
  }, [pasteText, navigate]);

  const onDragOver  = e => { e.preventDefault(); setDragging(true); };
  const onDragLeave = () => setDragging(false);
  const onDrop      = e => { e.preventDefault(); setDragging(false); handleFile(e.dataTransfer.files[0]); };

  const currentTab = RIBBON_TABS.find(t => t.name === activeTab) ?? RIBBON_TABS[0];

  return (
    <div className="up-root">

      {/* ── Quick Access Toolbar (top-left Excel-style) ─────────────────── */}
      <div className="up-qat">
        <div className="up-brand">
          <div className="up-brand-icon"><FileSpreadsheet size={15} color="#fff" /></div>
          <span className="up-brand-name">datacove</span>
          <span className="up-brand-sep">|</span>
          <span className="up-brand-sub">AI Data Cleaning</span>
        </div>
        <div className="up-qat-right" style={{ display:"flex", alignItems:"center", gap:12 }}>
          <button
            onClick={toggleTheme}
            className="up-theme-toggle"
            title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          >
            {theme === "dark" ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="5"/>
                <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
              </svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
              </svg>
            )}
          </button>
          <Link to="/datasets" style={{ fontSize:11, color:"var(--text-2)",
            textDecoration:"none", fontWeight:500 }}>
            My Datasets
          </Link>
          <Link to="/billing" style={{ fontSize:11, color:"var(--text-2)",
            textDecoration:"none", fontWeight:500 }}>
            Billing
          </Link>
          {userRole === "admin" && (
            <Link to="/admin" style={{ fontSize:11, color:"#f59e0b",
              textDecoration:"none", fontWeight:700,
              display:"inline-flex", alignItems:"center", gap:4 }}>
              <ShieldCheck size={11} />
              Admin
            </Link>
          )}
          <span className="up-version-badge">v4.0</span>
          
          {/* User menu */}
          <button
            onClick={() => {
              if (window.confirm("Sign out?")) {
                onLogout?.();
              }
            }}
            style={{
              padding: "4px 12px",
              background: "var(--surface-2)", border: "1px solid var(--border)",
              borderRadius: "var(--radius-md)", color: "var(--text-2)",
              fontSize: 11, cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
            }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
            Sign Out
          </button>
        </div>
      </div>

      {/* ── Ribbon tabs ─────────────────────────────────────────────────── */}
      <div className="up-ribbon-tabs">
        {RIBBON_TABS.map(t => (
          <button key={t.name}
            className={`up-ribbon-tab ${activeTab === t.name ? "up-ribbon-tab--on" : ""}`}
            onClick={() => setActiveTab(t.name)}>
            <t.icon size={11} />{t.name}
          </button>
        ))}
      </div>

      {/* ── Ribbon content ──────────────────────────────────────────────── */}
      <div className="up-ribbon">
        {currentTab.items.map(({ icon: Icon, label, desc }) => (
          <div key={label} className="up-ribbon-item"
            title={`Upload a file first to use: ${label}`}
            aria-disabled="true"
            role="button"
            tabIndex={-1}>
            <div className="up-ribbon-icon">
              <Icon size={20} style={{ color: currentTab.color }} />
            </div>
            <span className="up-ribbon-label">{label}</span>
            <span className="up-ribbon-desc">{desc}</span>
          </div>
        ))}
        <div className="up-ribbon-divider" />
        <div className="up-ribbon-cta">
          <div className="up-ribbon-cta-icon">
            <Upload size={20} color="#fff" />
          </div>
          <span className="up-ribbon-label">Open File</span>
          <span className="up-ribbon-desc">CSV, XLSX, XLS</span>
        </div>
      </div>

      {/* ── Main content ────────────────────────────────────────────────── */}
      <main className="up-main">
        <div className="up-hero-text">
          <h1 className="up-headline">
            Clean your data,{" "}
            <span className="up-accent">intelligently.</span>
          </h1>
          <p className="up-sub">
            Upload a CSV or Excel file to get started. Datacove profiles,
            scores, and fixes your dataset with AI-powered suggestions.
          </p>
        </div>

        {/* Drop zone */}
        <div
          className={`up-drop${dragging ? " up-drop--over" : ""}${uploading ? " up-drop--busy" : ""}`}
          onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}
          onClick={() => !uploading && inputRef.current?.click()}
          role="button" tabIndex={0}
          onKeyDown={e => e.key === "Enter" && inputRef.current?.click()}>
          <input ref={inputRef} type="file" accept={ACCEPTED.join(",")}
            style={{ display:"none" }} onChange={e => handleFile(e.target.files[0])} />

          {uploading ? (
            <div className="up-uploading">
              <div className="up-uploading-ring">
                <Loader2 size={32} color="var(--accent)" style={{ animation:"spin .7s linear infinite" }} />
                <span className="up-uploading-pct">{progress}%</span>
              </div>
              <p className="up-uploading-label">Uploading & parsing…</p>
              <div className="up-progress-track">
                <div className="up-progress-fill" style={{ width:`${progress}%` }} />
              </div>
            </div>
          ) : (
            <div className="up-drop-inner">
              <div className={`up-drop-icon${dragging ? " up-drop-icon--over" : ""}`}>
                <Upload size={28} color={dragging ? "var(--accent)" : "var(--text-2)"} />
              </div>
              <p className="up-drop-title">{dragging ? "Drop to upload" : "Drag & drop your file here"}</p>
              <p className="up-drop-hint">or <span className="up-drop-link">click to browse</span></p>
              <div className="up-drop-chips">
                {["CSV", "XLSX", "XLS"].map(f => (
                  <span key={f} className="up-drop-chip">{f}</span>
                ))}
                <span className="up-drop-limit">· up to 50 MB</span>
              </div>
            </div>
          )}
        </div>

        {/* ── Paste CSV toggle ──────────────────────────────────── */}
        <div style={{display:"flex", gap:8, alignItems:"center", marginTop:-8}}>
          <button
            style={{background:"none",border:"1px solid var(--border)",borderRadius:6,
                    padding:"4px 12px",fontSize:11,color:"var(--text-2)",cursor:"pointer",
                    ...(pasteMode?{borderColor:"var(--accent)",color:"var(--accent-light)"}:{})}}
            onClick={() => setPasteMode(m => !m)}>
            {pasteMode ? "⬆ Upload file instead" : "Paste CSV text"}
          </button>
        </div>
        {pasteMode && (
          <div style={{width:"100%",maxWidth:480,display:"flex",flexDirection:"column",gap:8}}>
            <textarea
              value={pasteText}
              onChange={e => setPasteText(e.target.value)}
              placeholder={`Paste CSV data here...
id,name,email
1,Alice,alice@example.com
2,Bob,bob@example.com`}
              rows={8}
              style={{width:"100%",padding:"10px 12px",borderRadius:8,border:"1px solid var(--border)",
                      background:"var(--surface-2)",color:"var(--text-0)",fontSize:12,
                      fontFamily:"monospace",resize:"vertical",outline:"none"}}
            />
            <button
              disabled={!pasteText.trim() || uploading}
              onClick={handlePaste}
              style={{padding:"8px 20px",borderRadius:8,background:"var(--accent)",color:"#fff",
                      border:"none",fontSize:13,fontWeight:700,cursor:"pointer",
                      opacity:!pasteText.trim()||uploading?0.5:1}}>
              {uploading ? "Parsing…" : "Load CSV Data"}
            </button>
          </div>
        )}

                {error && (
          <div className="up-error">
            <AlertCircle size={13} /><span>{error}</span>
          </div>
        )}
      </main>

      {/* ── Sample datasets + connectors ──────────────────────────────── */}
      <div style={{ display:"flex", flexDirection:"column", alignItems:"center",
        gap:32, padding:"32px 24px 0", width:"100%" }}>
        <SampleDatasetsPanel />
        <div style={{ width:"100%", maxWidth:480 }}>
          <ConnectorsPanel />
        </div>
      </div>

      {/* ── Status bar (Excel-style bottom bar) ─────────────────────────── */}
      <div className="up-statusbar">
        <span>Ready</span>
        <span className="up-status-sep">|</span>
        <span>Supported formats: CSV, XLSX, XLS</span>
        <span className="up-status-sep">|</span>
        <span>Max file size: 50 MB</span>
        <span className="up-status-right">Datacove AI v4.0</span>
      </div>

      <style>{`
        @keyframes spin { to { transform:rotate(360deg); } }
        @keyframes pulseGlow { 
          0%, 100% { box-shadow: var(--shadow-md); }
          50% { box-shadow: var(--shadow-glow); }
        }

        .up-root { min-height:100vh; display:flex; flex-direction:column;
                   background:var(--bg); }

        /* QAT */
        .up-qat  { display:flex; align-items:center; justify-content:space-between;
                   padding:0 14px; height:40px; background:var(--surface-1);
                   border-bottom:1px solid var(--border); flex-shrink:0; }
        .up-brand { display:flex; align-items:center; gap:8px; }
        .up-brand-icon { width:24px; height:24px; border-radius:6px; background:var(--gradient-primary);
                         display:flex; align-items:center; justify-content:center;
                         box-shadow: var(--shadow-accent); }
        .up-brand-name { font-size:14px; font-weight:800; letter-spacing:-.02em; color:var(--text-0); }
        .up-brand-sep  { color:var(--border); margin:0 4px; }
        .up-brand-sub  { font-size:11.5px; color:var(--text-2); font-weight:500; }
        .up-theme-toggle { background:var(--surface-2); border:1px solid var(--border); border-radius:var(--radius-md);
                           cursor:pointer; color:var(--text-2); padding:4px 8px; display:flex;
                           align-items:center; justify-content:center; transition:all 0.2s; }
        .up-theme-toggle:hover { border-color:var(--accent); color:var(--accent); background:var(--accent-dim); }
        .up-version-badge { font-size:9.5px; background:var(--accent-dim);
                            border:1px solid var(--border-accent); color:var(--accent);
                            padding:2px 8px; border-radius:99px; font-weight:700; }

        /* Ribbon tabs */
        .up-ribbon-tabs { display:flex; background:var(--surface-1);
                          border-bottom:1px solid var(--border); flex-shrink:0; padding:0 12px; }
        .up-ribbon-tab  { display:inline-flex; align-items:center; gap:6px; padding:10px 16px;
                          border:none; background:none; color:var(--text-2); font-size:11.5px;
                          font-weight:600; cursor:pointer; border-bottom:2px solid transparent;
                          margin-bottom:-1px; transition: all 0.2s ease; }
        .up-ribbon-tab:hover { color:var(--text-0); background: var(--surface-2); }
        .up-ribbon-tab--on { color:var(--accent); border-bottom-color:var(--accent); font-weight:700; }
        .up-ribbon-tab--on .up-ribbon-tab-icon { color:var(--accent); }

        /* Ribbon */
        .up-ribbon { display:flex; align-items:center; gap:0; padding:12px 20px;
                     background:var(--surface-1); border-bottom:1px solid var(--border);
                     flex-shrink:0; overflow-x:auto; scrollbar-width:none; }
        .up-ribbon::-webkit-scrollbar { display:none; }
        .up-ribbon-item { display:flex; flex-direction:column; align-items:center; gap:6px;
                          padding:10px 16px; cursor:not-allowed; min-width:90px;
                          transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
                          border-radius: var(--radius-md); border: 1px solid transparent;
                          position: relative; }
        .up-ribbon-item:hover { background:var(--surface-2); border-color: var(--border); }
        .up-ribbon-item:hover::after { content:"↑ Upload first"; position:absolute; bottom:-22px;
                          left:50%; transform:translateX(-50%); white-space:nowrap; font-size:9px;
                          color:var(--text-2); background:var(--surface-3); padding:2px 6px;
                          border-radius:4px; pointer-events:none; border:1px solid var(--border);
                          z-index:10; }
        .up-ribbon-icon { width:44px; height:44px; border-radius:var(--radius-md);
                          display:flex; align-items:center; justify-content:center;
                          background:var(--accent-dim); border: 1px solid var(--border-glass); }
        .up-ribbon-label { font-size:11px; font-weight:700; color:var(--text-1);
                           text-align:center; white-space:nowrap; margin-top:4px; }
        .up-ribbon-desc  { font-size:10px; color:var(--text-2); text-align:center;
                           white-space:nowrap; margin-top:2px; }
        .up-ribbon-divider { width:1px; height:56px; background:var(--border); margin:0 12px; flex-shrink:0; }
        .up-ribbon-cta { display:flex; flex-direction:column; align-items:center; gap:6px;
                          padding:10px 16px; cursor:pointer; min-width:90px; border-radius:var(--radius-md);
                          border:1px dashed var(--accent); background:var(--accent-dim);
                          transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1); }
        .up-ribbon-cta:hover { background:var(--accent); border-color: var(--accent);
                               transform: translateY(-2px); box-shadow: var(--shadow-accent); }
        .up-ribbon-cta:hover .up-ribbon-label { color:#fff; }
        .up-ribbon-cta:hover .up-ribbon-desc { color:rgba(255,255,255,0.8); }
        .up-ribbon-cta-icon { width:44px; height:44px; border-radius:var(--radius-md);
                               background:var(--gradient-primary); display:flex;
                               align-items:center; justify-content:center;
                               box-shadow: var(--shadow-accent); }

        /* Main */
        .up-main { flex:1; display:flex; flex-direction:column; align-items:center;
                   justify-content:center; padding:50px 24px; gap:32px; }

        .up-hero-text { text-align:center; display:flex; flex-direction:column;
                        align-items:center; gap:16px; }
        .up-headline { font-size:clamp(32px, 5vw, 48px); font-weight:800;
                       letter-spacing:-.03em; margin:0; line-height:1.15; color:var(--text-0); }
        .up-accent   { background: var(--gradient-primary); -webkit-background-clip: text;
                       -webkit-text-fill-color: transparent; }
        .up-sub      { font-size:14.5px; color:var(--text-2); margin:0; line-height:1.7;
                       max-width:480px; }

        /* Drop zone */
        .up-drop { width:100%; max-width:520px; border:2px dashed var(--border);
                   border-radius:var(--radius-xl); padding:40px; text-align:center;
                   cursor:pointer; background:var(--surface-1);
                   box-shadow: var(--shadow-md); animation: pulseGlow 6s infinite;
                   transition:all .3s cubic-bezier(0.16, 1, 0.3, 1) !important; }
        .up-drop:hover { border-color:var(--accent); background:var(--surface-2);
                         transform: translateY(-4px); box-shadow: var(--shadow-lg); }
        .up-drop--over { border-color:var(--accent); background:var(--accent-dim); transform: scale(1.02); }
        .up-drop--busy { cursor:default; pointer-events:none; animation: none; transform: scale(0.98); }

        .up-drop-inner { display:flex; flex-direction:column; align-items:center; gap:12px; }
        .up-drop-icon  { width:56px; height:56px; border-radius:50%; background:var(--surface-2);
                         border:2px dashed var(--border); display:flex; align-items:center;
                         justify-content:center; transition: all 0.3s ease; }
        .up-drop:hover .up-drop-icon { background:var(--accent-dim); border-color:var(--accent); }
        .up-drop-icon--over { background:var(--accent-dim) !important; border-color:var(--accent) !important; scale: 1.1; }
        
        .up-drop-title { font-size:16px; font-weight:700; color:var(--text-0); margin:0; }
        .up-drop-hint  { font-size:13px; color:var(--text-2); margin:0; }
        .up-drop-link  { color:var(--accent); font-weight:600; text-decoration: underline; text-underline-offset: 2px; }
        .up-drop-chips { display:flex; align-items:center; gap:6px; flex-wrap:wrap; justify-content:center; margin-top: 4px; }
        .up-drop-chip  { font-size:10px; font-weight:800; letter-spacing:.05em; color:var(--text-2);
                         background:var(--surface-2); border:1px solid var(--border);
                         padding:3px 8px; border-radius:6px; }
        .up-drop-limit { font-size:11px; color:var(--text-3); font-weight: 500; }

        .up-uploading { display:flex; flex-direction:column; align-items:center; gap:12px; }
        .up-uploading-ring { position:relative; width:64px; height:64px; display:flex;
                             align-items:center; justify-content:center; }
        .up-uploading-pct { position:absolute; font-size:11px; font-weight:800;
                             color:var(--accent); }
        .up-uploading-label { font-size:13px; color:var(--text-1); font-weight: 500; margin:0; }
        .up-progress-track { width:220px; height:4px; background:var(--surface-3);
                              border-radius:99px; overflow:hidden; }
        .up-progress-fill  { height:100%; background:var(--gradient-primary); border-radius:99px;
                               transition:width .3s ease !important; }

        .up-error { display:flex; align-items:center; gap:10px; font-size:12.5px; color:var(--red);
                    background:var(--red-dim); border:1px solid var(--red);
                    border-radius:var(--radius-md); padding:12px 16px;
                    max-width:520px; width:100%; font-weight: 500; }

        /* Status bar */
        .up-statusbar { display:flex; align-items:center; gap:0; height:26px; flex-shrink:0;
                        background:var(--surface-1); border-top:1px solid var(--border);
                        padding:0 16px; font-size:10.5px; color:var(--text-3); gap:10px; }
        .up-status-sep  { opacity:0.5; }
        .up-status-right { margin-left:auto; color:var(--accent); font-weight:600; }
      `}</style>
    </div>
  );
}
