/**
 * Dashboard v6 — all UX fixes:
 *  - Dedup feedback toast (shows "0 duplicates found" when no rows removed)
 *  - Sidebar toggle as proper visible button
 *  - Tab bar with scroll fade indicator + arrow buttons
 *  - Grid meta row with more weight
 *  - overflow:visible on toolbar-wrap so dropdowns escape
 *  - Resizable sidebar with drag handle
 *  - Ctrl+Z global undo
 */
import React, { useState, useEffect, useCallback, useRef, useMemo, Suspense, lazy } from "react";
import ReactDOM from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import {
  FileSpreadsheet, RefreshCw, GitCompare, Loader2,
  AlertCircle, X, FileDown, GripVertical,
  PanelRightClose, PanelRightOpen,
  ChevronLeft, ChevronRight,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

import SpreadsheetGrid   from "../components/SpreadsheetGrid";
import CleaningToolbar   from "../components/CleaningToolbar";
import DatasetSummary    from "../components/DatasetSummary";
import HealthScoreCard   from "../components/HealthScoreCard";
import StreamProgressBar from "../components/StreamProgressBar";
import ErrorBoundary       from "../components/ErrorBoundary";
import ExplanationToast   from "../components/ExplanationToast";
import JobPoller           from "../components/JobPoller";
import { useStreamingTransform } from "../hooks/useStreamingTransform";

const AIInsightsPanel = lazy(() => import("../components/AIInsightsPanel"));
const AIAgentPanel    = lazy(() => import("../components/AIAgentPanel"));
const AIMLPanel       = lazy(() => import("../components/AIMLPanel"));
const AIChatBox       = lazy(() => import("../components/AIChatBox"));
const ColumnQuality   = lazy(() => import("../components/ColumnQuality"));
const ProfilingCharts = lazy(() => import("../components/ProfilingCharts"));
const PipelineManager = lazy(() => import("../components/PipelineManager"));
const SQLPanel        = lazy(() => import("../components/SQLPanel"));
const FuzzyDedupPanel = lazy(() => import("../components/FuzzyDedupPanel"));
const ValidationPanel = lazy(() => import("../components/ValidationPanel"));
const VisualizationDashboard = lazy(() => import("../components/VisualizationDashboard"));
const PowerToolsPanel        = lazy(() => import("../components/PowerToolsPanel"));
const CorrelationPanel       = lazy(() => import("../components/CorrelationPanel"));
const DataIntelligencePanel  = lazy(() => import("../components/DataIntelligencePanel"));
const PatternLibraryPanel    = lazy(() => import("../components/PatternLibraryPanel"));
const SchemaApplyPanel       = lazy(() => import("../components/SchemaApplyPanel"));
const AutoCleanReport        = lazy(() => import("../components/AutoCleanReport"));
const HistoryPanel           = lazy(() => import("../components/HistoryPanel"));
const VocabMapperPanel       = lazy(() => import("../components/VocabMapperPanel"));
const BatchCleanPanel        = lazy(() => import("../components/BatchCleanPanel"));
const SharePanel             = lazy(() => import("../components/SharePanel"));
const AICommandCenter        = lazy(() => import("../components/AICommandCenter"));
const PIIDetectorPanel       = lazy(() => import("../components/PIIDetectorPanel"));
const LineagePanel           = lazy(() => import("../components/LineagePanel"));

function PanelLoader() {
  return (
    <div style={{ display:"flex", alignItems:"center", justifyContent:"center",
      padding:"40px 0", gap:8, color:"var(--text-3)", fontSize:12 }}>
      <Loader2 size={14} style={{ animation:"spin .7s linear infinite" }} />
      Loading…
    </div>
  );
}

import {
  analyzeDataset, fetchSummary, fetchProfile,
  applyTransformation, undoTransformation, resetDataset,
  sendNLCommand, downloadExport, compareDatasets, runAIAgent,
  downloadReport, editCell, fixAllIssues, applySchemasuggestions,
  rollbackToVersion, runAgentAsync, orchestrateAI,
} from "../services/api";

// Primary tabs shown to all users by default (most useful for first-timers)
const PRIMARY_TABS = ["AI Command", "Insights", "Visualize", "Power", "History"];

// Advanced tabs hidden behind the "More tools" expander
const ADVANCED_TABS = [
  "Agent", "ML", "Chat", "SQL", "Fuzzy", "Correlations",
  "Patterns", "Intelligence", "Validate", "Vocab", "Batch",
  "Pipelines", "Compare", "Share", "PII", "Lineage",
];

const ALL_TABS = [...PRIMARY_TABS, ...ADVANCED_TABS];

// Dataset-wide actions that must NOT have a column injected — defined at module
// level so it's a stable reference and doesn't recreate on every render.
const DATASET_WIDE_ACTIONS = new Set([
  "remove_duplicates", "auto_clean",
  "drop_constant_columns", "drop_high_missing_columns",
  "drop_rows_missing_threshold",
  "normalize_column_names", "rename_columns_bulk",
]);

const DEFAULT_W = 360, MIN_W = 280, MAX_W = 560;

// Session persistence helpers
const SESSION_KEY = "datacove_session";

function getPersistedSession() {
  try {
    const stored = sessionStorage.getItem(SESSION_KEY);
    if (stored) return JSON.parse(stored);
  } catch {}
  return null;
}

function persistSession(session) {
  try {
    if (session?.session_id) {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify({
        session_id: session.session_id,
        filename: session.filename || session.original_filename,
        rows: session.rows,
        columns: session.columns,
      }));
    }
  } catch {}
}

export default function Dashboard() {
  const location = useLocation();
  const navigate = useNavigate();
  
  // Get session from navigation state OR sessionStorage
  const locationSession = location.state?.session;
  const [initData, setInitData] = useState(() => {
    if (locationSession) {
      persistSession(locationSession);
      return locationSession;
    }
    // Restore from sessionStorage
    return getPersistedSession();
  });

  // Persist session when it changes
  useEffect(() => {
    if (initData?.session_id) {
      persistSession(initData);
    }
  }, [initData]);

  useEffect(() => { if (!initData) navigate("/", { replace: true }); }, [initData, navigate]);


  const [sessionId]               = useState(initData?.session_id ?? "");

  // columns + rows kept in one object so they always update atomically
  // (prevents a render where new columns exist but rows still have old keys)
  const [grid, setGrid] = useState({
    columns: initData?.columns ?? [],
    rows:    initData?.preview ?? [],
  });
  const columns = grid.columns;
  const rows    = grid.rows;

  const [totalRows,setTotalRows]  = useState(initData?.rows ?? 0);
  // Keep a ref so applyGridResult always reads the *current* row count
  // (avoids stale closure where prevRows is captured at callback creation time)
  const totalRowsRef = useRef(initData?.rows ?? 0);
  useEffect(() => { totalRowsRef.current = totalRows; }, [totalRows]);
  const [history,  setHistory]    = useState([]);

  const [summary,  setSummary]    = useState(null);
  const [analysis, setAnalysis]   = useState(null);
  const [profile,  setProfile]    = useState(null);
  const [analyzing,setAnalyzing]  = useState(false);
  const [aiInsights, setAiInsights] = useState(initData?.ai_insights ?? null);
  const [schemaSugg, setSchemaSugg] = useState(initData?.schema_suggestions ?? []);
  const [autoCleanReport, setAutoCleanReport] = useState(null);  // {steps, summary}
  const [gridLoad, setGridLoad]   = useState(false);
  const [errorMsg, setErrorMsg]   = useState("");
  const [toast,    setToast]      = useState(null);  // { msg, type }

  const [activeTab,      setActiveTab]      = useState("AI Command");
  const [sideOpen,       setSideOpen]       = useState(true);
  const [sideW,          setSideW]          = useState(DEFAULT_W);
  const [showShortcuts,  setShowShortcuts]  = useState(false);
  // Progressive disclosure: power users who click "More tools" remember that preference
  const [showAdvanced,   setShowAdvanced]   = useState(
    () => localStorage.getItem("dc_show_advanced_tabs") === "1"
  );
  const [startHereDismissed, setStartHereDismissed] = useState(
    () => localStorage.getItem("dc_start_here_dismissed") === "1"
  );
  const visibleTabs = showAdvanced ? ALL_TABS : PRIMARY_TABS;

  // Tab bar scroll ref
  const tabsRef = useRef(null);
  const scrollTabs = (dir) => {
    if (tabsRef.current) tabsRef.current.scrollLeft += dir * 120;
  };

  // Resizable sidebar
  const resizing = useRef(false);
  const startX   = useRef(0);
  const startW   = useRef(DEFAULT_W);

  useEffect(() => {
    const onMove = (e) => {
      if (!resizing.current) return;
      const delta = startX.current - e.clientX;
      setSideW(Math.min(MAX_W, Math.max(MIN_W, startW.current + delta)));
    };
    const onUp = () => {
      resizing.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup",   onUp);
    return () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
  }, []);

  // Toast helper
  const showToast = useCallback((msg, type = "info") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  }, []);

  const { runTransform, runAutoClean, progress, streaming, abort } =
    useStreamingTransform(sessionId, totalRows);

  const isBusy = gridLoad || streaming;

  useEffect(() => {
    if (!sessionId) return;

    // Fetch summary with a simple retry so transient 404s (session not yet
    // registered on the backend between upload and dashboard mount) don't
    // show as console errors.
    let summaryAttempts = 0;
    const trySummary = () => {
      fetchSummary(sessionId)
        .then(setSummary)
        .catch(() => {
          if (summaryAttempts++ < 3) setTimeout(trySummary, 600);
        });
    };
    trySummary();

    // Auto-run full analysis once on mount. Wait 800 ms so the session is
    // guaranteed to be persisted before the heavier endpoints are hit.
    if (analysis) return;
    const t = setTimeout(async () => {
      setAnalyzing(true);
      try {
        const [ar, pr] = await Promise.all([
          analyzeDataset(sessionId).catch(e => { console.warn("Auto-analyze failed:", e); return null; }),
          fetchProfile(sessionId).catch(e => { console.warn("Auto-profile failed:", e); return null; }),
        ]);
        if (ar) { setAnalysis(ar); setSummary(s => ({ ...s, health: ar.health })); }
        if (pr) setProfile(pr);
      } finally { setAnalyzing(false); }
    }, 800);
    return () => clearTimeout(t);
  }, [sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  const applyGridResult = useCallback(function applyGridResult(result, actionLabel) {
    // Use ref so we always read the latest row count — avoids stale closure crash
    const prevRows = totalRowsRef.current;
    // Update columns + rows atomically to avoid a mismatched intermediate render
    // where AG Grid has new columnDefs but old rowData (or vice-versa)
    if (result.columns || result.preview) {
      setGrid(g => ({
        columns: result.columns ?? g.columns,
        rows:    result.preview ?? g.rows,
      }));
    }
    if (result.rows != null) setTotalRows(result.rows);
    if (result.history)      setHistory(result.history);
    // Dedup feedback toast
    if (actionLabel === "remove_duplicates" && result.rows != null) {
      const removed = prevRows - result.rows;
      if (removed <= 0) {
        showToast("No duplicate rows found in this dataset", "info");
      } else {
        showToast(`✓ Removed ${removed.toLocaleString()} duplicate row${removed !== 1 ? "s" : ""}`, "success");
      }
    }
    fetchSummary(sessionId).then(setSummary).catch(() => {});
  }, [sessionId, showToast]); // removed totalRows from deps — using ref instead

  const handleTransform = useCallback(async (action, params) => {
    if (isBusy) return;
    setErrorMsg(""); setGridLoad(true);
    try {
      let ra = action, rp = params;
      if (action === "__nl__") {
        const p = await sendNLCommand(sessionId, params.command);
        if (!p?.action) throw new Error("Could not parse command.");
        ra = p.action; rp = p.params ?? {};
      }
      // __auto_clean__ sentinel from NL parser — route to auto-clean endpoint
      if (ra === "__auto_clean__") {
        await runAutoClean((r) => applyGridResult(r, "auto_clean"));
        return;
      }
      await runTransform(ra, rp, (r) => applyGridResult(r, ra));
    } catch (err) {
      setErrorMsg(err?.response?.data?.detail ?? err?.message ?? "Transform failed.");
    } finally { setGridLoad(false); }
  }, [sessionId, isBusy, runTransform, applyGridResult]);

  const handleAutoClean = useCallback(async () => {
    if (isBusy) return;
    setErrorMsg(""); setGridLoad(true);
    try {
      await runAutoClean((r) => {
        applyGridResult(r, "auto_clean");
        if (r.steps?.length) setAutoCleanReport({ steps: r.steps, summary: r.summary });
      });
    }
    catch (err) { setErrorMsg(err?.response?.data?.detail ?? err?.message ?? "Auto-clean failed."); }
    finally { setGridLoad(false); }
  }, [isBusy, runAutoClean, applyGridResult]);

  const handleUndo = useCallback(async () => {
    if (isBusy) return;
    setGridLoad(true);
    try {
      const result = await undoTransformation(sessionId);
      if (!result.success) {
        setErrorMsg(result.message ?? "Nothing to undo.");
        applyGridResult(result, "undo");
      } else {
        applyGridResult(result, "undo");
      }
    }
    catch (err) { setErrorMsg(err?.response?.data?.detail ?? "Nothing to undo."); }
    finally { setGridLoad(false); }
  }, [sessionId, isBusy, applyGridResult]);

  // Global keyboard shortcuts — placed AFTER handleUndo to avoid Temporal Dead Zone error
  useEffect(() => {
    const h = (e) => {
      const a = document.activeElement;
      const inInput = a?.tagName === "INPUT" || a?.tagName === "TEXTAREA";
      if ((e.ctrlKey || e.metaKey) && e.key === "z") {
        if (inInput) return;
        e.preventDefault(); handleUndo();
      } else if (e.key === "?" && !inInput) {
        setShowShortcuts(s => !s);
      } else if (e.key === "Escape") {
        setShowShortcuts(false);
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [handleUndo]);

  // ── Inline cell edit handler ──────────────────────────────────────────────
  const handleCellEdit = useCallback(async (rowIndex, column, newValue) => {
    try {
      const result = await editCell(sessionId, rowIndex, column, newValue);
      applyGridResult(result, "edit_cell");
      showToast(`Cell updated (${column})`, "success");
    } catch (err) {
      showToast(err?.response?.data?.detail ?? "Cell edit failed", "error");
    }
  }, [sessionId, applyGridResult, showToast]);

  // Build columnProfiles map for SpreadsheetGrid sparklines + context menu
  const columnProfiles = useMemo(() => {
    if (!profile?.columns_profile) return {};
    const map = {};
    for (const cp of profile.columns_profile) {
      map[cp.column] = cp;
    }
    return map;
  }, [profile]);

  const handleReset = useCallback(async () => {
    if (isBusy || !confirm("Reset to original uploaded dataset?")) return;
    setGridLoad(true);
    try { setHistory([]); applyGridResult(await resetDataset(sessionId)); }
    finally { setGridLoad(false); }
  }, [sessionId, isBusy, applyGridResult]);

  const handleExport = useCallback(async (fmt) => {
    setGridLoad(true);
    try {
      await downloadExport(sessionId, fmt);
    } catch (err) {
      const msg = err?.response?.data instanceof Blob
        ? "Export failed — check the browser console for details."
        : (err?.response?.data?.detail ?? err?.message ?? "Export failed.");
      setErrorMsg(msg);
    } finally {
      setGridLoad(false);
    }
  }, [sessionId]);

  const handleReport = useCallback(async () => {
    setGridLoad(true);
    try {
      await downloadReport(sessionId);
    } catch (err) {
      setErrorMsg(err?.response?.data?.detail ?? err?.message ?? "Report generation failed.");
    } finally {
      setGridLoad(false);
    }
  }, [sessionId]);
  const handleAgent = useCallback(() => {
    // Open the Agent sidebar panel — the Run button lives inside AIAgentPanel
    setActiveTab("Agent");
    setSideOpen(true);
  }, []);

  const runAnalysis = useCallback(async () => {
    setAnalyzing(true);
    setErrorMsg("");
    try {
      const [ar, pr, aiData] = await Promise.all([
        analyzeDataset(sessionId).catch(e => { console.warn("Analyze failed:", e); throw e; }),
        fetchProfile(sessionId).catch(e => { console.warn("Profile failed:", e); return null; }),
        orchestrateAI(sessionId).catch(e => { console.warn("AI orchestration failed:", e); return null; }),
      ]);
      if (ar) { setAnalysis(ar); setSummary(s => ({ ...s, health: ar.health })); }
      if (pr) setProfile(pr);
      if (aiData) setAiInsights(aiData);
    } catch(err) {
      setErrorMsg(err?.response?.data?.detail ?? err?.message ?? "Analysis failed — check backend logs.");
    } finally { setAnalyzing(false); }
  }, [sessionId]);

  const handleFixAll = useCallback(async (fixes) => {
    if (isBusy || !fixes.length) return;
    setGridLoad(true); setErrorMsg("");
    try {
      const r = await fixAllIssues(sessionId, fixes);
      applyGridResult(r, "fix_all");
      showToast(`Fixed ${fixes.length} issue${fixes.length!==1?"s":""}`, "success");
    } catch(err) {
      setErrorMsg(err?.response?.data?.detail ?? err?.message ?? "Fix All failed.");
    } finally { setGridLoad(false); }
  }, [sessionId, isBusy, applyGridResult, showToast]);

  const handleApplySchema = useCallback(async (suggestions) => {
    if (isBusy || !suggestions.length) return;
    setGridLoad(true); setErrorMsg("");
    try {
      const r = await applySchemasuggestions(sessionId, suggestions);
      applyGridResult(r, "apply_schema");
      setSchemaSugg(prev => prev.filter(s => !suggestions.find(a => a.column===s.column)));
      showToast(`Applied ${suggestions.length} type cast${suggestions.length!==1?"s":""}`, "success");
    } catch(err) {
      setErrorMsg(err?.response?.data?.detail ?? err?.message ?? "Schema apply failed.");
    } finally { setGridLoad(false); }
  }, [sessionId, isBusy, applyGridResult, showToast]);

  const handleSuggestion = useCallback((s) => {
    const params = { ...(s.params ?? {}) };
    if (s.column && !DATASET_WIDE_ACTIONS.has(s.action)) {
      params.column = s.column;
    }
    handleTransform(s.action, params);
  }, [handleTransform]);

  const [compareFile,  setCompareFile]  = useState(null);
  const [explanation,  setExplanation]  = useState(null);
  const [asyncJobId,   setAsyncJobId]   = useState(null);
  const [compareRes,   setCompareRes]   = useState(null);
  const [comparing,    setComparing]    = useState(false);

  async function handleCompareUpload(e) {
    const file = e.target.files[0]; if (!file) return;
    setCompareFile(file.name); setComparing(true); setCompareRes(null);
    try {
      const { uploadDataset } = await import("../services/api");
      setCompareRes(await compareDatasets(sessionId, (await uploadDataset(file)).session_id));
    } catch (err) {
      setCompareRes({ error: err?.response?.data?.detail ?? "Compare failed." });
    } finally { setComparing(false); }
  }

  if (!initData) return null;

  return (
    <div className="db-root">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header className="db-header">
        <div className="db-hl">
          <button className="db-back" onClick={() => navigate("/")}>
            <div className="db-logo-icon"><FileSpreadsheet size={13} color="#fff" /></div>
            <span className="db-logo-txt">datacove</span>
          </button>
          <div className="db-hdiv" />
          <DatasetSummary summary={summary} issuesCount={analysis?.issues?.length} />
        </div>
        <div className="db-hr">
          {(analyzing || isBusy) && (
            <span className="db-busy"><Loader2 size={11} className="spin" />Processing…</span>
          )}
          <button className="db-hbtn" onClick={() => setShowShortcuts(s=>!s)}
            title="Keyboard shortcuts (?)" aria-label="Toggle keyboard shortcuts">
            ⌨ Shortcuts
          </button>
          <button className="db-hbtn db-hbtn--report" onClick={handleReport}
            title="Download HTML quality report" aria-label="Download quality report">
            <FileDown size={12} aria-hidden="true" />Report
          </button>
          <button className="db-hbtn db-hbtn--cta" onClick={runAnalysis} disabled={analyzing || isBusy}
            aria-label={analyzing ? "Analysing dataset…" : "Run analysis"}>
            {analyzing ? <><Loader2 size={12} className="spin" aria-hidden="true" />Analysing…</> : <><RefreshCw size={12} aria-hidden="true" />Run Analysis</>}
          </button>
        </div>
      </header>

      {/* ── Error banner ────────────────────────────────────────────────── */}
      {errorMsg && (
        <div className="db-err">
          <AlertCircle size={12} aria-hidden="true" /><span>{errorMsg}</span>
          <button onClick={() => setErrorMsg("")} className="db-err-close"
            aria-label="Dismiss error" title="Dismiss"><X size={12} aria-hidden="true" /></button>
        </div>
      )}

      {/* ── Toolbar — overflow:visible so export dropdown escapes ────────── */}
      <div className="db-toolbar-wrap" style={{ position:"relative" }}>
        <CleaningToolbar
          sessionId={sessionId} columns={columns} onTransform={handleTransform}
          onAutoClean={handleAutoClean} onUndo={handleUndo}
          onReset={handleReset} onExport={handleExport}
          onRunAgent={handleAgent} loading={isBusy}
          activeTab={activeTab} onTabChange={setActiveTab}
        />
        {/* Toast sits below toolbar but must escape stacking context */}
        {toast && ReactDOM.createPortal(
          <div className={`db-toast db-toast--${toast.type}`}>
            {toast.type === "success" ? "✓" : "ℹ"} {toast.msg}
          </div>,
          document.body
        )}
      </div>

      {/* ── Grid meta row ───────────────────────────────────────────────── */}
      <div className="db-meta-bar">
        <span className="db-meta-count">
          <span className="db-meta-num">{totalRows.toLocaleString()}</span> rows ·
          <span className="db-meta-num"> {columns.length}</span> columns
        </span>
        {isBusy && !streaming && (
          <span className="db-meta-busy"><Loader2 size={10} className="spin" />Working…</span>
        )}
        {summary?.health && (
          <div style={{ marginLeft: "auto" }}>
            <HealthScoreCard health={analysis?.health ?? summary?.health} />
          </div>
        )}
      </div>

      {/* ── Inline panels: schema apply + auto-clean report ───────────── */}
      {(schemaSugg.length > 0 || autoCleanReport) && (
        <div style={{ padding: "0 14px 6px", display: "flex", flexDirection: "column", gap: 6 }}>
          <Suspense fallback={null}>
            {schemaSugg.length > 0 && (
              <SchemaApplyPanel
                suggestions={schemaSugg}
                onApply={handleApplySchema}
                onDismiss={() => setSchemaSugg([])}
                loading={isBusy}
              />
            )}
            {autoCleanReport && (
              <AutoCleanReport
                summary={autoCleanReport.summary}
                steps={autoCleanReport.steps}
                onDismiss={() => setAutoCleanReport(null)}
              />
            )}
          </Suspense>
        </div>
      )}

      {/* ── Body ────────────────────────────────────────────────────────── */}
      <div className="db-body" style={sideOpen ? { gridTemplateColumns:`minmax(0,1fr) auto ${sideW}px` } : { gridTemplateColumns: 'minmax(0,1fr) auto' }}>

        {/* Grid */}
        <div className="db-grid-area">
          <div className="db-grid-wrap">
          <ErrorBoundary>
            <SpreadsheetGrid
              key={columns.join(",")}
              columns={columns}
              rows={rows}
              loading={gridLoad}
              columnProfiles={columnProfiles}
              onCellEdit={handleCellEdit}
              onTransform={handleTransform}
              sessionId={sessionId}
            />
          </ErrorBoundary>
          </div>
        </div>

        {/* Resize grip */}
        {sideOpen && (
          <div className="db-grip" title="Drag to resize sidebar"
            onMouseDown={(e) => {
              resizing.current = true;
              startX.current = e.clientX;
              startW.current = sideW;
              document.body.style.cursor = "col-resize";
              document.body.style.userSelect = "none";
            }}>
            <GripVertical size={12} />
          </div>
        )}

        {/* Sidebar */}
        <AnimatePresence>
          {sideOpen && (
            <motion.aside
              className="db-side"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 50, transition: { duration: 0.2 } }}
              transition={{ type: "spring", stiffness: 300, damping: 30 }}
            >
              {/* Toggle — always visible, properly styled */}
              <button className="db-side-toggle"
                onClick={() => setSideOpen(o => !o)}
                title="Collapse sidebar"
                aria-label="Collapse sidebar"
                aria-expanded="true">
                <PanelRightClose size={14} aria-hidden="true" />
              </button>

              {/* Tab navigation row */}
              <div className="db-tabs-wrap">
                <button className="db-tabs-arrow db-tabs-arrow--left" onClick={() => scrollTabs(-1)} title="Scroll left">
                  <ChevronLeft size={12} />
                </button>
                <div className="db-tabs" ref={tabsRef}>
                  {visibleTabs.map(tab => (
                    <button key={tab}
                      className={`db-tab ${activeTab === tab ? "db-tab--on" : ""}`}
                      onClick={() => setActiveTab(tab)}>
                      {tab}
                    </button>
                  ))}
                  {/* More tools expander */}
                  <button
                    className="db-tab db-tab--more"
                    onClick={() => {
                      const next = !showAdvanced;
                      setShowAdvanced(next);
                      localStorage.setItem("dc_show_advanced_tabs", next ? "1" : "0");
                      if (!next && ADVANCED_TABS.includes(activeTab)) setActiveTab("AI Command");
                    }}
                    title={showAdvanced ? "Hide advanced tools" : "Show all tools"}
                  >
                    {showAdvanced ? "⚙ Less" : "⚙ More tools"}
                  </button>
                </div>
                <button className="db-tabs-arrow db-tabs-arrow--right" onClick={() => scrollTabs(1)} title="Scroll right">
                  <ChevronRight size={12} />
                </button>
              </div>

              {/* Start here banner — shown to first-time users */}
              {!startHereDismissed && (
                <div style={{
                  margin: "8px 12px 0", padding: "10px 14px",
                  background: "linear-gradient(135deg, rgba(99,102,241,0.12), rgba(192,38,211,0.08))",
                  border: "1px solid rgba(99,102,241,0.25)", borderRadius: "var(--radius-md)",
                  display: "flex", alignItems: "center", gap: 10, fontSize: 12,
                }}>
                  <span style={{ fontSize: 18 }}>✨</span>
                  <span style={{ flex: 1, color: "var(--text-1)", lineHeight: 1.5 }}>
                    <strong style={{ color: "var(--accent-light)" }}>Start here:</strong>{" "}
                    Click <strong>Run Analysis</strong> to get AI-powered insights, then use the toolbar to fix issues.
                  </span>
                  <button
                    onClick={() => { setStartHereDismissed(true); localStorage.setItem("dc_start_here_dismissed", "1"); }}
                    style={{ background: "none", border: "none", cursor: "pointer",
                      color: "var(--text-3)", fontSize: 14, padding: 2, lineHeight: 1 }}
                    title="Dismiss"
                  >✕</button>
                </div>
              )}

              <div className="db-tab-body">
                <ErrorBoundary>
                <Suspense fallback={<PanelLoader />}>

                  {activeTab === "AI Command" && (
                    <div className="ts">
                      <AICommandCenter
                        sessionId={sessionId}
                        initialInsights={aiInsights}
                        onActionApplied={(result) => applyGridResult(result, result?.action_id?.split("|")[0])}
                      />
                    </div>
                  )}

                  {activeTab === "Insights" && (
                    <div className="ts">
                      {analyzing && !analysis && (
                        <div className="db-empty-state db-analysing-state">
                          <div className="db-analysing-anim">
                            <Loader2 size={28} className="spin" />
                          </div>
                          <p className="db-empty-title">Analysing your dataset…</p>
                          <p className="db-empty-sub">Detecting issues, profiling columns, and generating AI suggestions.</p>
                        </div>
                      )}
                      {!analyzing && !analysis && (
                        <div className="db-empty-state">
                          <div className="db-empty-icon">✦</div>
                          <p className="db-empty-title">No analysis yet</p>
                          <p className="db-empty-sub">Run analysis to get AI insights, quality scores and column profiling.</p>
                          <button className="db-empty-cta" onClick={runAnalysis} disabled={analyzing}>
                            {analyzing ? <><Loader2 size={13} className="spin" />Analysing…</> : <><RefreshCw size={13} />Run Analysis</>}
                          </button>
                        </div>
                      )}
                      <AIInsightsPanel analysis={analysis} onApplySuggestion={handleSuggestion} onFixAll={handleFixAll} schemaSuggestions={schemaSugg} onApplySchema={handleApplySchema} />
                      {profile && <ColumnQuality profile={profile} />}
                      {profile && <ProfilingCharts profile={profile} />}
                    </div>
                  )}

                  {activeTab === "Visualize" && (
                    <div className="ts">
                      <VisualizationDashboard sessionId={sessionId} />
                    </div>
                  )}

                  {activeTab === "Power" && (
                    <div className="ts">
                      <PowerToolsPanel
                        sessionId={sessionId}
                        columns={columns}
                        columnProfiles={columnProfiles}
                        onDataChange={(r) => applyGridResult(r, "power_tool")}
                      />
                    </div>
                  )}
                  {activeTab === "Agent" && (
                    <div className="ts">
                      <Suspense fallback={<PanelLoader />}>
                        <AIAgentPanel sessionId={sessionId} onComplete={r => applyGridResult(r)} />
                      </Suspense>
                    </div>
                  )}
                  {activeTab === "ML" && (
                    <div className="ts">
                      <Suspense fallback={<PanelLoader />}>
                        <AIMLPanel sessionId={sessionId} />
                      </Suspense>
                    </div>
                  )}
                  {activeTab === "Chat" && (
                    <div className="ts">
                      <Suspense fallback={<PanelLoader />}>
                        <AIChatBox sessionId={sessionId} columns={columns} onApplied={r => applyGridResult(r)} />
                      </Suspense>
                    </div>
                  )}
                  {activeTab === "SQL" && (
                    <div className="ts">
                      <Suspense fallback={<PanelLoader />}>
                        <SQLPanel sessionId={sessionId} columns={columns} onApplied={r => applyGridResult(r)} />
                      </Suspense>
                    </div>
                  )}
                  {activeTab === "Fuzzy" && (
                    <div className="ts">
                      <Suspense fallback={<div style={{padding:20,textAlign:"center"}}><Loader2 size={16} className="spin"/></div>}>
                        <FuzzyDedupPanel sessionId={sessionId} columns={columns} onApplied={r => applyGridResult(r)} />
                      </Suspense>
                    </div>
                  )}
                  {activeTab === "Correlations" && (
                    <div className="ts">
                      <Suspense fallback={<div style={{padding:20,textAlign:"center"}}><Loader2 size={16} className="spin"/></div>}>
                        <CorrelationPanel sessionId={sessionId} columns={columns} />
                      </Suspense>
                    </div>
                  )}
                  {activeTab === "Patterns" && (
                    <div className="ts">
                      <Suspense fallback={<div style={{padding:20,textAlign:"center"}}><Loader2 size={16} className="spin"/></div>}>
                        <PatternLibraryPanel sessionId={sessionId} columns={columns} />
                      </Suspense>
                    </div>
                  )}
                  {activeTab === "Intelligence" && (
                    <div className="ts">
                      <Suspense fallback={<div style={{padding:20,textAlign:"center"}}><Loader2 size={16} className="spin"/></div>}>
                        <DataIntelligencePanel sessionId={sessionId} onTransform={handleTransform} />
                      </Suspense>
                    </div>
                  )}
                  {activeTab === "Validate" && (
                    <div className="ts">
                      <Suspense fallback={<div style={{padding:20,textAlign:"center"}}><Loader2 size={16} className="spin"/></div>}>
                        <ValidationPanel sessionId={sessionId} columns={columns} />
                      </Suspense>
                    </div>
                  )}

                  {activeTab === "History" && (
                    <div className="ts">
                      <Suspense fallback={<PanelLoader />}>
                        <HistoryPanel
                          sessionId={sessionId}
                          history={history}
                          onRollback={r => applyGridResult(r, "rollback")}
                          onUndo={handleUndo}
                        />
                      </Suspense>
                    </div>
                  )}

                  {activeTab === "Vocab" && (
                    <div className="ts">
                      <Suspense fallback={<PanelLoader />}>
                        <VocabMapperPanel
                          sessionId={sessionId}
                          columns={columns}
                          onApplied={r => applyGridResult(r, "vocab_map")}
                        />
                      </Suspense>
                    </div>
                  )}

                  {activeTab === "Batch" && (
                    <div className="ts">
                      <Suspense fallback={<PanelLoader />}>
                        <BatchCleanPanel
                          sessionId={sessionId}
                          history={history}
                        />
                      </Suspense>
                    </div>
                  )}

                  {activeTab === "Pipelines" && (
                    <Suspense fallback={<PanelLoader />}>
                      <PipelineManager sessionId={sessionId} history={history} onRan={r => applyGridResult(r)} />
                    </Suspense>
                  )}

                  {activeTab === "Share" && (
                    <div className="ts"><Suspense fallback={<PanelLoader />}><SharePanel sessionId={sessionId} /></Suspense></div>
                  )}

                  {activeTab === "PII" && (
                    <div className="ts">
                      <Suspense fallback={<PanelLoader />}>
                        <PIIDetectorPanel
                          sessionId={sessionId}
                          columns={columns}
                          onMasked={(r) => applyGridResult(r, "pii_mask")}
                        />
                      </Suspense>
                    </div>
                  )}

                  {activeTab === "Lineage" && (
                    <div className="ts">
                      <Suspense fallback={<PanelLoader />}>
                        <LineagePanel sessionId={sessionId} />
                      </Suspense>
                    </div>
                  )}
                  {activeTab === "Compare" && (
                    <div className="db-cmp">
                      <p className="db-cmp-sub">Upload a second file to diff against this dataset.</p>
                      <label className="db-cmp-btn">
                        <input type="file" accept=".csv,.xlsx,.xls" style={{display:"none"}} onChange={handleCompareUpload} />
                        {comparing ? <><Loader2 size={11} className="spin" />Comparing…</> : <><GitCompare size={11} />{compareFile ? "Re-upload" : "Upload to compare"}</>}
                      </label>
                      {compareRes?.error && <p className="db-cmp-err">{compareRes.error}</p>}
                      {compareRes && !compareRes.error && (
                        <div className="db-cmp-grid">
                          <CS label="New rows"      v={compareRes.new_rows_count}       c="var(--green)" />
                          <CS label="Removed rows"  v={compareRes.removed_rows_count}   c="var(--red)" />
                          <CS label="Changed cells" v={compareRes.changed_values?.length} c="var(--amber)" />
                          <CS label="Row Δ"         v={(compareRes.row_count_delta > 0 ? "+" : "") + compareRes.row_count_delta} />
                          {compareRes.changed_values?.length > 0 && (
                            <div style={{gridColumn:"1/-1"}}>
                              <p className="db-cmp-table-title">Sample changes</p>
                              <div className="db-cmp-table-wrap">
                                <table className="db-cmp-table">
                                  <thead><tr><th>Row</th><th>Col</th><th>Before</th><th>After</th></tr></thead>
                                  <tbody>
                                    {compareRes.changed_values.slice(0,15).map((c,i) => (
                                      <tr key={i}><td>{c.row}</td><td>{c.column}</td>
                                        <td style={{color:"var(--red)"}}>{c.value_a}</td>
                                        <td style={{color:"var(--green)"}}>{c.value_b}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                </Suspense>
                </ErrorBoundary>
              </div>
            </motion.aside>
          )}
        </AnimatePresence>
        
        {/* Toggle when closed */}
        {!sideOpen && (
           <button className="db-side-toggle--ghost"
             onClick={() => setSideOpen(true)}
             title="Expand sidebar"
             aria-label="Expand sidebar"
             aria-expanded="false">
             <PanelRightOpen size={14} aria-hidden="true" />
           </button>
        )}
      </div>

      <StreamProgressBar progress={progress} onAbort={abort} />

      {/* ── Keyboard shortcuts modal ─────────────────────────────────── */}
      {showShortcuts && (
        <div style={{position:"fixed",inset:0,zIndex:20000,background:"rgba(0,0,0,.6)",
                     display:"flex",alignItems:"center",justifyContent:"center"}}
          onClick={() => setShowShortcuts(false)}>
          <div style={{background:"var(--surface-1)",border:"1px solid var(--border-2)",
                       borderRadius:14,padding:"24px 28px",minWidth:320,
                       boxShadow:"0 24px 80px rgba(0,0,0,.7)"}}
            onClick={e => e.stopPropagation()}>
            <h3 style={{margin:"0 0 16px",fontSize:15,fontWeight:700,color:"var(--text-0)"}}>
              ⌨ Keyboard Shortcuts
            </h3>
            {[
              ["Ctrl+Z",  "Undo last transform"],
              ["Ctrl+S",  "Export as CSV"],
              ["Ctrl+R",  "Run Analysis"],
              ["?",       "Toggle this cheatsheet"],
            ].map(([key, desc]) => (
              <div key={key} style={{display:"flex",justifyContent:"space-between",
                                     padding:"6px 0",borderBottom:"1px solid var(--border)",
                                     fontSize:12}}>
                <kbd style={{background:"var(--surface-3)",border:"1px solid var(--border)",
                             borderRadius:5,padding:"2px 8px",fontSize:11,
                             fontFamily:"monospace",color:"var(--text-0)"}}>{key}</kbd>
                <span style={{color:"var(--text-2)"}}>{desc}</span>
              </div>
            ))}
            <button onClick={() => setShowShortcuts(false)}
              style={{marginTop:16,width:"100%",padding:"8px",borderRadius:8,
                      background:"var(--accent)",color:"#fff",border:"none",
                      fontSize:13,fontWeight:600,cursor:"pointer"}}>
              Close
            </button>
          </div>
        </div>
      )}

      <style>{`
        .db-root { height:100vh; display:flex; flex-direction:column; background:var(--bg); overflow:hidden;
                   background-image: var(--gradient-bg); }

        /* Header */
        .db-header { display:flex; align-items:center; justify-content:space-between;
                     padding:0 14px; height:48px; border-bottom:1px solid var(--border);
                     flex-shrink:0; gap:10px; background:var(--surface-1);
                     backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); z-index: 10; }
        .db-hl { display:flex; align-items:center; gap:12px; min-width:0; flex:1; overflow:hidden; }
        .db-hr { display:flex; align-items:center; gap:8px; flex-shrink:0; }
        .db-back { display:inline-flex; align-items:center; gap:8px; background:none; border:none; cursor:pointer; padding:0; transition: transform 0.2s; }
        .db-back:hover { transform: translateX(-2px); }
        .db-logo-icon { width:26px; height:26px; border-radius:6px; background:var(--gradient-primary);
                        display:flex; align-items:center; justify-content:center; flex-shrink:0;
                        box-shadow: var(--shadow-accent); }
        .db-logo-txt { font-size:14.5px; font-weight:800; letter-spacing:-.02em; color:var(--text-0); }
        .db-hdiv { width:1px; height:20px; background:var(--border); flex-shrink:0; }
        .db-busy { display:flex; align-items:center; gap:6px; font-size:11px; color:var(--text-3); font-weight: 500; }
        .db-hbtn { display:inline-flex; align-items:center; gap:6px; padding:6px 14px;
                   border-radius:var(--radius-sm); border:1px solid var(--border);
                   background:var(--surface-2); color:var(--text-1); font-size:12px; font-weight:600; cursor:pointer;
                   box-shadow: var(--shadow-sm); transition: all 0.2s ease; }
        .db-hbtn:hover { background:var(--surface-3); color:var(--text-0); border-color:var(--border-2); }
        .db-hbtn--report { }
        .db-hbtn--cta { background:var(--gradient-primary); color:#fff; border:none; font-weight:700;
                        box-shadow: var(--shadow-accent); }
        .db-hbtn--cta:hover:not(:disabled) { transform: translateY(-1px); box-shadow: var(--shadow-glow); }
        .db-hbtn--cta:disabled { opacity:.5; cursor:not-allowed; }

        /* Error */
        .db-err { display:flex; align-items:center; gap:8px; font-size:12.5px; color:var(--red);
                  background:var(--red-dim); border-bottom:1px solid var(--red);
                  padding:8px 16px; flex-shrink:0; font-weight: 500; backdrop-filter: blur(8px); }
        .db-err-close { margin-left:auto; background:none; border:none; cursor:pointer; color:inherit; display:flex; padding:2px; }

        /* Toolbar */
        .db-toolbar-wrap { padding:8px 14px 4px; border-bottom:1px solid var(--border);
                           flex-shrink:0; background:var(--surface-1); overflow:visible; backdrop-filter: blur(8px); }

        /* Toast */
        .db-toast { position:fixed; bottom:40px; left:50%; transform:translateX(-50%);
                    display:flex; align-items:center; gap:8px; padding:10px 20px;
                    border-radius:var(--radius-md); font-size:12.5px; font-weight:600;
                    white-space:nowrap; z-index:99999; pointer-events:none;
                    box-shadow:var(--shadow-lg); backdrop-filter: blur(8px); }
        .db-toast--success { background:var(--green-dim); border:1px solid var(--green); color:var(--green); }
        .db-toast--info    { background:var(--surface-glass); border:1px solid var(--border); color:var(--text-0); }
        .db-toast--error   { background:var(--red-dim); border:1px solid var(--red); color:var(--red); }

        /* Grid meta bar */
        .db-meta-bar { display:flex; align-items:center; gap:16px; padding:6px 16px;
                       border-bottom:1px solid var(--border); flex-shrink:0;
                       background:var(--surface-1); min-height:46px; backdrop-filter: blur(4px); }
        .db-meta-count { font-size:12.5px; color:var(--text-2); }
        .db-meta-num   { font-weight:800; color:var(--text-0); font-family: 'JetBrains Mono', monospace; }
        .db-meta-busy  { display:flex; align-items:center; gap:6px; font-size:11px; color:var(--accent-light); font-weight:600; }
        .db-meta-score { font-size:12px; font-weight:700; margin-left:auto; display:flex; align-items:center; gap:6px; }

        /* Empty state */
        .db-empty-state { display:flex; flex-direction:column; align-items:center; justify-content:center;
                          padding:40px 20px; text-align:center; gap:16px; height: 100%; }
        .db-empty-icon  { font-size:36px; line-height:1; color:var(--accent); opacity:.8;
                          filter:drop-shadow(0 0 16px var(--accent-glow)); animation: pulseGlow 4s infinite; }
        .db-empty-title { font-size:16px; font-weight:800; color:var(--text-0); margin:0; }
        .db-empty-sub   { font-size:13px; color:var(--text-2); margin:0; line-height:1.6; max-width:260px; }
        .db-empty-cta   { display:inline-flex; align-items:center; gap:8px; padding:10px 24px;
                          border-radius:var(--radius-md); background:var(--gradient-primary); color:#fff;
                          border:none; font-size:13px; font-weight:700; cursor:pointer; margin-top:8px;
                          box-shadow:var(--shadow-accent); transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1); }
        .db-empty-cta:hover:not(:disabled) { transform:translateY(-2px); box-shadow:var(--shadow-glow); }
        .db-empty-cta:disabled { opacity:.5; cursor:not-allowed; }

        /* Analysing state animation */
        .db-analysing-state { padding:60px 20px; height: 100%; display: flex; flex-direction: column; justify-content: center; align-items: center; }
        .db-analysing-anim  { color:var(--accent-light); filter:drop-shadow(0 0 20px var(--accent-glow)); }

        /* Body — column widths driven entirely by inline style on the element */
        .db-body { flex:1; display:grid; min-height:0; overflow:hidden; position: relative; }

        /* Grid area */
        .db-grid-area { display:flex; flex-direction:column; overflow:hidden; min-width:0; min-height:0; }
        .db-grid-wrap { flex:1; min-height:0; overflow:hidden; }

        /* Resize grip */
        .db-grip { width:6px; display:flex; align-items:center; justify-content:center;
                   cursor:col-resize; color:var(--text-3); background:var(--surface-1);
                   border-left:1px solid var(--border); border-right:1px solid var(--border); z-index: 5; }
        .db-grip:hover { background:var(--accent-dim); color:var(--accent); }

        /* Sidebar */
        .db-side { display:flex; flex-direction:column; overflow:hidden; min-height:0;
                   background:var(--surface-1); border-left:1px solid var(--border);
                   backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); }
        .db-side--closed { width:36px !important; }

        /* Sidebar toggle — always visible, proper button */
        .db-side-toggle { display:flex; align-items:center; justify-content:center;
                          width:100%; height:36px; background:none; border:none;
                          border-bottom:1px solid var(--border); cursor:pointer;
                          color:var(--text-2); flex-shrink:0; transition: background 0.2s; }
        .db-side-toggle:hover { background:var(--surface-2); color:var(--text-0); }
        
        .db-side-toggle--ghost {
          position: absolute; right: 0; top: 50%; transform: translateY(-50%);
          z-index: 100; display: flex; align-items: center; justify-content: center;
          width: 24px; height: 60px; background: var(--surface-glass);
          border: 1px solid var(--border); border-right: none;
          border-radius: 8px 0 0 8px; cursor: pointer; color: var(--text-2);
          box-shadow: -4px 0 16px var(--shadow-md);
          backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
          transition: all 0.2s ease;
        }
        .db-side-toggle--ghost:hover {
          background: var(--surface-2); color: var(--text-0); width: 28px;
        }

        /* Sidebar content padding */
        .db-side > * + * { } /* no extra margin */
        .db-side > .hsc-wrap,
        .db-side > .db-tabs-wrap,
        .db-side > .db-tab-body { margin:0 12px; }
        .db-side > .hsc-wrap   { margin-top:12px; }

        /* Tabs */
        .db-tabs-wrap { position:relative; display:flex; align-items:center;
                        flex-shrink:0; margin-top:8px !important; border-bottom:1px solid var(--border); }
        .db-tabs { display:flex; overflow-x:auto; scrollbar-width:none; flex:1; gap: 4px; }
        .db-tabs::-webkit-scrollbar { display:none; }
        .db-tab  { flex-shrink:0; padding:10px 14px; border:none; background:none;
                   color:var(--text-2); font-size:11.5px; font-weight:600; cursor:pointer;
                   white-space:nowrap; border-bottom:2px solid transparent;
                   margin-bottom:-1px; transition:color 0.2s; }
        .db-tab:hover { color:var(--text-0); }
        .db-tab--on { color:var(--accent-light); font-weight:700; border-bottom-color:var(--accent); }
        .db-tab--more { color:var(--text-3); font-style:italic; border-left:1px solid var(--border);
                        padding-left:10px; margin-left:4px; }
        .db-tab--more:hover { color:var(--text-1); background:var(--surface-2); }

        /* Tab scroll arrows */
        .db-tabs-arrow { flex-shrink:0; display:flex; align-items:center; justify-content:center;
                         width:24px; height:32px; background:var(--surface-1);
                         border:none; cursor:pointer; color:var(--text-2);
                         position:relative; z-index:2; backdrop-filter: blur(4px); }
        .db-tabs-arrow--left  { border-right:1px solid var(--border); box-shadow:4px 0 8px var(--shadow-sm); }
        .db-tabs-arrow--right { border-left:1px solid var(--border); box-shadow:-4px 0 8px var(--shadow-sm); }
        .db-tabs-arrow:hover { color:var(--text-0); }

        /* Tab content */
        .db-tab-body { flex:1; overflow-y:auto; overflow-x:hidden; min-height:0;
                       display:flex; flex-direction:column; gap:12px;
                       padding:12px 0; }
        .ts { display:flex; flex-direction:column; gap:12px; }

        /* History */
        .db-hist     { background:var(--surface-2); border-radius:var(--radius-md);
                       border:1px solid var(--border); overflow:hidden; }
        .db-hist-hdr { display:flex; align-items:center; justify-content:space-between;
                       padding:10px 14px; border-bottom:1px solid var(--border); background:var(--surface-1); }
        .db-hist-title { font-size:12.5px; font-weight:800; color:var(--text-0); }
        .db-hist-kbd   { font-size:9.5px; background:var(--surface-3); border:1px solid var(--border);
                         padding:3px 8px; border-radius:4px; color:var(--text-1); font-family: 'JetBrains Mono', monospace; font-weight: 600; }
        .db-hist-list  { list-style:none; margin:0; padding:8px;
                         display:flex; flex-direction:column; gap:2px; }
        .db-hist-item  { display:flex; align-items:flex-start; gap:10px; padding:6px 10px;
                         border-radius:6px; cursor:default; transition: background 0.2s; }
        .db-hist-item:hover { background:var(--surface-3); transform: translateX(2px); }
        .db-hist-n     { font-size:10px; font-weight:800; color:var(--accent);
                         min-width:18px; text-align:right; margin-top:2px; }
        .db-hist-info  { display:flex; flex-direction:column; gap:2px; min-width:0; }
        .db-hist-action { font-size:11.5px; font-weight:600; color:var(--text-0); text-transform:capitalize; }
        .db-hist-param  { font-size:10px; color:var(--text-2); font-family: 'JetBrains Mono', monospace;
                          white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }

        /* Compare */
        .db-cmp      { background:var(--surface-2); border-radius:var(--radius-md);
                       border:1px solid var(--border); padding:16px; display:flex;
                       flex-direction:column; gap:12px; }
        .db-cmp-sub  { font-size:12px; color:var(--text-2); margin:0; line-height: 1.5; }
        .db-cmp-btn  { display:inline-flex; align-items:center; gap:8px; align-self:flex-start;
                       padding:8px 14px; border-radius:var(--radius-sm); cursor:pointer;
                       background:var(--surface-3); border:1px solid var(--border);
                       font-size:11.5px; color:var(--text-0); font-weight:600; transition: all 0.2s; }
        .db-cmp-btn:hover { background:var(--surface-2); border-color:var(--border-2); }
        .db-cmp-err  { font-size:12px; color:var(--red); margin:0; font-weight: 500; }
        .db-cmp-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
        .db-cs { background:var(--surface-3); border-radius:var(--radius-sm); border: 1px solid var(--border);
                 padding:10px 12px; display:flex; flex-direction:column; gap:2px; }
        .db-cs-val { font-size:18px; font-weight:800; font-family: 'Outfit'; }
        .db-cs-lbl { font-size:9.5px; color:var(--text-3); text-transform:uppercase; letter-spacing:.05em; font-weight: 700; }
        .db-cmp-table-title { font-size:10.5px; font-weight:800; color:var(--text-2);
                              text-transform:uppercase; letter-spacing:.05em; margin:0 0 6px; }
        .db-cmp-table-wrap { overflow-x:auto; border-radius:6px; border:1px solid var(--border); }
        .db-cmp-table { width:100%; border-collapse:collapse; font-size:10.5px; font-family: 'JetBrains Mono', monospace; }
        .db-cmp-table th { padding:6px 10px; background:var(--surface-2); color:var(--text-1);
                           font-weight:700; text-align:left; border-bottom:1px solid var(--border); }
        .db-cmp-table td { padding:5px 10px; border-bottom:1px solid var(--border);
                           color:var(--text-2); max-width:80px; overflow:hidden;
                           text-overflow:ellipsis; white-space:nowrap; }

        @keyframes pulseGlow { 
          0%, 100% { filter: drop-shadow(0 0 16px var(--accent-glow)); }
          50% { filter: drop-shadow(0 0 32px var(--accent-glow)); }
        }
        @keyframes spin { to { transform:rotate(360deg); } }
        .spin { animation:spin .7s linear infinite; }
      `}</style>
    </div>
  );
}

function EmptyTab({ children }) {
  return (
    <div style={{ display:"flex", alignItems:"center", justifyContent:"center",
      padding:"40px 16px", textAlign:"center" }}>
      <span style={{ fontSize:12, color:"var(--text-3)", lineHeight:1.6 }}>{children}</span>
    </div>
  );
}

function CS({ label, v, c }) {
  return (
    <div className="db-cs">
      <span className="db-cs-val" style={{ color: c ?? "var(--text-0)" }}>{v ?? 0}</span>
      <span className="db-cs-lbl">{label}</span>
    </div>
  );
}
