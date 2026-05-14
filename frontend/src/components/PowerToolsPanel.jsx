/**
 * PowerToolsPanel.jsx — v2
 * PII Detection & Masking  +  Formula / Computed Column (fully upgraded)
 *
 * Formula upgrades in v2:
 *  ① Column type badges  (# numeric  T text  D date  @ email  ≡ category  ✓ bool)
 *  ② Cursor-aware insert — click a column chip → inserts at caret, not appended to end
 *  ③ Live preview with 600ms debounce — dry-runs on first 5 rows, shows output type
 *  ④ Smart auto-naming — column name field auto-filled from expression, clears on edit
 *  ⑤ Categorised example library (Math / String / Date / Conditional / Stats)
 *  ⑥ Column search filter — handles datasets with 100+ columns
 *  ⑦ Formula history — last 8 formulas in localStorage, one-click restore
 *  ⑧ Multi-formula mode — queue multiple formulas and apply all in one shot
 *  ⑨ Output type indicator on preview strip
 *  ⑩ Ctrl+Enter keyboard shortcut to apply
 */
import React, { useState, useRef, useEffect, useMemo, useContext, createContext } from "react";
import {
  ShieldAlert, Wand2, Plus, Loader2, CheckCircle,
  Eye, EyeOff, Hash, Shuffle, AlertTriangle, X,
  ChevronDown, ChevronRight, Clock, Search,
  Play, Layers, Trash2, Zap,
} from "lucide-react";
import { detectPII, maskPII, addFormulaColumn, previewFormula } from "../services/api";

// ─────────────────────────────────────────────────────────────────────────────
// ── Shared helpers
// ─────────────────────────────────────────────────────────────────────────────

const LS_KEY = "dc_formula_history";
function loadHistory() {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || "[]"); } catch { return []; }
}
function saveHistory(items) {
  try { localStorage.setItem(LS_KEY, JSON.stringify(items.slice(0, 8))); } catch {}
}
function pushHistory(newCol, expr) {
  const h = loadHistory().filter(h => h.expr !== expr);
  saveHistory([{ newCol, expr, ts: Date.now() }, ...h]);
}

function colTypeBadge(col, profileMap) {
  const p = profileMap?.[col];
  if (!p) return { icon: "·", color: "var(--text-3)", title: "unknown" };
  const t = p.detected_type ?? "";
  if (t === "numeric" || String(p.dtype).match(/int|float/))
    return { icon: "#", color: "#10b981", title: "numeric" };
  if (t === "date")     return { icon: "D", color: "#06b6d4", title: "date" };
  if (t === "email")    return { icon: "@", color: "#f59e0b", title: "email" };
  if (t === "phone")    return { icon: "☎", color: "#f59e0b", title: "phone" };
  if (t === "currency") return { icon: "$", color: "#10b981", title: "currency" };
  if (t === "category") return { icon: "≡", color: "#a78bfa", title: "category" };
  if (String(p.dtype).includes("bool")) return { icon: "✓", color: "#34d399", title: "boolean" };
  return { icon: "T", color: "var(--text-2)", title: "text" };
}

function suggestColName(expr) {
  if (!expr.trim()) return "";
  return expr.trim()
    .replace(/['"()[\]{}]/g, "")
    .replace(/[^a-zA-Z0-9_\s]/g, "_")
    .replace(/\s+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "")
    .slice(0, 40) || "";
}

function insertAtCaret(textarea, text) {
  const start = textarea.selectionStart ?? textarea.value.length;
  const end   = textarea.selectionEnd   ?? textarea.value.length;
  const before = textarea.value.slice(0, start);
  const after  = textarea.value.slice(end);
  const needSpaceBefore = before.length > 0 && !/[\s(+\-*/,]$/.test(before);
  const needSpaceAfter  = after.length  > 0 && !/^[\s)+\-*/,]/.test(after);
  const insert = (needSpaceBefore ? " " : "") + text + (needSpaceAfter ? " " : "");
  return { value: before + insert + after, caretPos: start + insert.length };
}

// Context so PIISection and FormulaSection share the onSuccess callback
const PTCtx = createContext({});

// ─────────────────────────────────────────────────────────────────────────────
// ── PII Section
// ─────────────────────────────────────────────────────────────────────────────
function PIISection({ sessionId }) {
  const { onDataChange } = useContext(PTCtx);
  const [piiData,  setPiiData]  = useState(null);
  const [scanning, setScanning] = useState(false);
  const [masking,  setMasking]  = useState(false);
  const [selected, setSelected] = useState({});
  const [error,    setError]    = useState("");
  const [done,     setDone]     = useState(false);

  async function scan() {
    setScanning(true); setError(""); setDone(false);
    try {
      const result = await detectPII(sessionId);
      setPiiData(result);
      const sel = {};
      result.pii_columns.forEach(c => { sel[c.column] = { strategy: "redact", pii_type: c.pii_type }; });
      setSelected(sel);
    } catch (e) { setError(e?.response?.data?.detail || "Scan failed."); }
    finally     { setScanning(false); }
  }

  async function applyMasking() {
    const cols = Object.entries(selected).map(([column, { strategy, pii_type }]) => ({ column, pii_type, strategy }));
    if (!cols.length) return;
    setMasking(true); setError("");
    try { const r = await maskPII(sessionId, cols); setDone(true); onDataChange?.(r); }
    catch (e) { setError(e?.response?.data?.detail || "Masking failed."); }
    finally   { setMasking(false); }
  }

  const STRATEGY_LABELS = { redact: "Redact", hash: "Hash", fake: "Fake" };

  return (
    <div className="pt-section">
      <div className="pt-section-header">
        <ShieldAlert size={13} color="#ef4444" />
        <span className="pt-section-title">PII Detection & Masking</span>
      </div>
      <p className="pt-desc">Auto-detect emails, phones, SSNs, names and other personal data.</p>
      <button className="pt-btn pt-btn--primary" onClick={scan} disabled={scanning || !sessionId}>
        {scanning ? <Loader2 size={11} className="spin" /> : <Eye size={11} />} Scan for PII
      </button>
      {error && <div className="pt-msg pt-msg--err"><AlertTriangle size={11} /> {error}</div>}
      {piiData?.pii_columns?.length === 0 && (
        <div className="pt-msg pt-msg--ok"><CheckCircle size={11} /> No PII detected.</div>
      )}
      {piiData?.pii_columns?.length > 0 && !done && (
        <>
          <div className="pt-pii-list">
            {piiData.pii_columns.map(col => {
              const sel = selected[col.column];
              return (
                <div key={col.column} className={`pt-pii-row ${sel ? "pt-pii-row--on" : ""}`}>
                  <input type="checkbox" checked={!!sel} onChange={e => {
                    if (e.target.checked) setSelected(s => ({ ...s, [col.column]: { strategy:"redact", pii_type: col.pii_type } }));
                    else setSelected(s => { const n={...s}; delete n[col.column]; return n; });
                  }} />
                  <div style={{flex:1, minWidth:0}}>
                    <div className="pt-pii-name">{col.column}</div>
                    <div className="pt-pii-type">{col.pii_type} · {Math.round(col.confidence*100)}%</div>
                  </div>
                  {sel && (
                    <select className="pt-sel" value={sel.strategy}
                      onChange={e => setSelected(s => ({...s, [col.column]: {...s[col.column], strategy: e.target.value}}))}>
                      {Object.entries(STRATEGY_LABELS).map(([k,v]) => <option key={k} value={k}>{v}</option>)}
                    </select>
                  )}
                </div>
              );
            })}
          </div>
          <button className="pt-btn pt-btn--danger" disabled={masking || !Object.keys(selected).length} onClick={applyMasking}>
            {masking ? <Loader2 size={11} className="spin" /> : <EyeOff size={11} />}
            Mask {Object.keys(selected).length} Column{Object.keys(selected).length !== 1 ? "s" : ""}
          </button>
        </>
      )}
      {done && (
        <div className="pt-msg pt-msg--ok">
          <CheckCircle size={11} /> PII masked!
          <button className="pt-link" onClick={() => { setPiiData(null); setDone(false); }}>Run again</button>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ── Example data
// ─────────────────────────────────────────────────────────────────────────────
const EXAMPLE_CATS = [
  {
    label: "Math", color: "#10b981",
    items: [
      { label: "Price × Qty",    expr: "Price * Quantity",                              desc: "Multiply two columns" },
      { label: "Profit %",       expr: "(Revenue - Cost) / Revenue * 100",              desc: "Profit margin %" },
      { label: "Log Revenue",    expr: "np.log1p(Revenue)",                             desc: "Log transform (handles 0)" },
      { label: "Z-Score",        expr: "(Score - Score.mean()) / Score.std()",          desc: "Standardise" },
      { label: "Clamp 0–100",    expr: "np.clip(Score, 0, 100)",                        desc: "Cap to range" },
      { label: "Running Total",  expr: "Amount.cumsum()",                               desc: "Cumulative sum" },
      { label: "Pct of Total",   expr: "Amount / Amount.sum() * 100",                  desc: "Row as % of total" },
      { label: "Abs Diff",       expr: "np.abs(Expected - Actual)",                    desc: "Absolute error" },
    ],
  },
  {
    label: "String", color: "#6366f1",
    items: [
      { label: "Full Name",      expr: "FirstName + ' ' + LastName",                   desc: "Concatenate" },
      { label: "Uppercase",      expr: "Name.str.upper()",                             desc: "UPPERCASE" },
      { label: "Email Domain",   expr: "Email.str.split('@').str[1]",                  desc: "Domain from email" },
      { label: "Trim + Lower",   expr: "Name.str.strip().str.lower()",                 desc: "Clean whitespace & case" },
      { label: "Title Case",     expr: "Name.str.title()",                             desc: "Title Case" },
      { label: "String Length",  expr: "Description.str.len()",                        desc: "Character count" },
      { label: "Starts With A",  expr: "Name.str.startswith('A')",                     desc: "Boolean flag" },
      { label: "Replace Text",   expr: "Status.str.replace('old', 'new')",             desc: "Find & replace" },
    ],
  },
  {
    label: "Date", color: "#06b6d4",
    items: [
      { label: "Year",           expr: "pd.to_datetime(Date).dt.year",                 desc: "Extract year" },
      { label: "Month",          expr: "pd.to_datetime(Date).dt.month",                desc: "Extract month" },
      { label: "Day of Week",    expr: "pd.to_datetime(Date).dt.day_name()",           desc: "Monday, Tuesday…" },
      { label: "Days Since",     expr: "(pd.Timestamp.now() - pd.to_datetime(Date)).dt.days", desc: "Age in days" },
      { label: "Is Weekend",     expr: "pd.to_datetime(Date).dt.dayofweek >= 5",       desc: "True/False" },
      { label: "Quarter",        expr: "pd.to_datetime(Date).dt.quarter",              desc: "Q1–Q4" },
      { label: "Date Diff",      expr: "(pd.to_datetime(EndDate) - pd.to_datetime(StartDate)).dt.days", desc: "Days between two dates" },
    ],
  },
  {
    label: "Conditional", color: "#f59e0b",
    items: [
      { label: "Pass / Fail",    expr: "np.where(Score > 50, 'Pass', 'Fail')",          desc: "If / else" },
      { label: "3-way label",    expr: "np.where(Score>=80,'High', np.where(Score>=50,'Mid','Low'))", desc: "Nested conditions" },
      { label: "Age Bucket",     expr: "pd.cut(Age, bins=[0,18,35,60,100], labels=['Teen','Adult','Middle','Senior'])", desc: "Named bins" },
      { label: "Null flag",      expr: "Column.isna().astype(int)",                     desc: "1 where null" },
      { label: "Fill nulls",     expr: "Column.fillna(0)",                              desc: "Replace NaN with 0" },
      { label: "Dense Rank",     expr: "Score.rank(ascending=False, method='dense')",   desc: "Ranking" },
      { label: "Quartile",       expr: "pd.qcut(Revenue, q=4, labels=['Q1','Q2','Q3','Q4'])", desc: "Equal-freq bins" },
    ],
  },
  {
    label: "Stats", color: "#a78bfa",
    items: [
      { label: "Rolling Avg",    expr: "Value.rolling(3).mean()",                      desc: "3-period MA" },
      { label: "Rolling Std",    expr: "Value.rolling(5).std()",                       desc: "Rolling std dev" },
      { label: "Pct Change",     expr: "Value.pct_change() * 100",                     desc: "Period-over-period %" },
      { label: "Lag (prev row)", expr: "Value.shift(1)",                               desc: "Previous row value" },
      { label: "Min-Max Scale",  expr: "(Value - Value.min()) / (Value.max() - Value.min())", desc: "Normalise [0,1]" },
      { label: "Outlier flag",   expr: "np.abs(Value - Value.mean()) > 2 * Value.std()", desc: "True = outlier (2σ)" },
    ],
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// ── Sub-components
// ─────────────────────────────────────────────────────────────────────────────
function PreviewStrip({ vals, outType, rows }) {
  const TYPE_COLOR = { numeric:"#10b981", boolean:"#34d399", datetime:"#06b6d4", text:"var(--text-2)", unknown:"var(--text-3)" };
  return (
    <div className="fp-strip">
      <div className="fp-header">
        <Play size={9} style={{color:"#10b981"}} />
        <span>Preview ({rows} row{rows!==1?"s":""})</span>
        <span className="fp-type" style={{color: TYPE_COLOR[outType] ?? "var(--text-3)"}}>{outType}</span>
      </div>
      <div className="fp-vals">
        {vals.slice(0,5).map((v,i) => (
          <span key={i} className="fp-val">
            {v === "NaN" ? <em style={{opacity:.4}}>NaN</em> : v}
          </span>
        ))}
      </div>
    </div>
  );
}

function QueueItem({ item, idx, onRemove }) {
  return (
    <div className="fq-item">
      <span className="fq-num">{idx+1}</span>
      <div className="fq-body">
        <span className="fq-col">{item.newCol}</span>
        <span className="fq-expr">{item.expr}</span>
      </div>
      <button className="fq-rm" onClick={() => onRemove(idx)}><X size={10}/></button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ── Formula Section
// ─────────────────────────────────────────────────────────────────────────────
function FormulaSection({ sessionId, columns, columnProfiles }) {
  const { onDataChange } = useContext(PTCtx);

  const [newCol,      setNewCol]      = useState("");
  const [expr,        setExpr]        = useState("");
  const [autoNamed,   setAutoNamed]   = useState(false);
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState("");
  const [success,     setSuccess]     = useState("");
  const [colSearch,   setColSearch]   = useState("");
  const [openCat,     setOpenCat]     = useState(null);
  const [preview,     setPreview]     = useState(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [history,     setHistory]     = useState(loadHistory);
  const [showHist,    setShowHist]    = useState(false);
  const [multiMode,   setMultiMode]   = useState(false);
  const [queue,       setQueue]       = useState([]);
  const [applying,    setApplying]    = useState(false);

  const textareaRef  = useRef(null);
  const previewTimer = useRef(null);

  // Column profile map
  const profileMap = useMemo(() => columnProfiles ?? {}, [columnProfiles]);

  // Filtered columns for picker
  const filteredCols = useMemo(() =>
    columns.filter(c => c.toLowerCase().includes(colSearch.toLowerCase())),
    [columns, colSearch]
  );

  // ① Auto-name from expression
  useEffect(() => {
    if (!expr) { if (autoNamed) { setNewCol(""); setAutoNamed(false); } return; }
    if (!newCol || autoNamed) {
      const sug = suggestColName(expr);
      if (sug) { setNewCol(sug); setAutoNamed(true); }
    }
  }, [expr]); // eslint-disable-line

  // ③ Live preview (600ms debounce)
  useEffect(() => {
    clearTimeout(previewTimer.current);
    setPreview(null);
    if (!expr.trim() || !sessionId) return;
    previewTimer.current = setTimeout(async () => {
      setPreviewBusy(true);
      try {
        const res = await previewFormula(sessionId, expr.trim(), 5);
        if (res.ok) { setPreview(res); setError(""); }
        else        { setPreview(null); setError(res.error ?? "Invalid expression."); }
      } catch { /* silent */ }
      finally { setPreviewBusy(false); }
    }, 600);
    return () => clearTimeout(previewTimer.current);
  }, [expr, sessionId]); // eslint-disable-line

  // ② Cursor-aware column insert
  function insertCol(col) {
    const ta = textareaRef.current;
    if (!ta) { setExpr(e => e ? `${e} ${col}` : col); return; }
    const { value, caretPos } = insertAtCaret(ta, col);
    setExpr(value);
    requestAnimationFrame(() => { ta.focus(); ta.setSelectionRange(caretPos, caretPos); });
  }

  // Example insert
  function applyExample(ex) {
    setExpr(ex.expr);
    setAutoNamed(false);
    setNewCol(suggestColName(ex.expr));
    textareaRef.current?.focus();
  }

  // Apply single
  async function apply() {
    if (!newCol.trim() || !expr.trim()) return;
    setLoading(true); setError(""); setSuccess("");
    try {
      const result = await addFormulaColumn(sessionId, newCol.trim(), expr.trim());
      pushHistory(newCol.trim(), expr.trim());
      setHistory(loadHistory());
      setSuccess(`Column "${result.new_column}" added!`);
      setNewCol(""); setExpr(""); setPreview(null); setAutoNamed(false);
      onDataChange?.(result);
    } catch (e) { setError(e?.response?.data?.detail || "Formula error."); }
    finally     { setLoading(false); }
  }

  // Queue add
  function addToQueue() {
    if (!newCol.trim() || !expr.trim()) return;
    setQueue(q => [...q, { newCol: newCol.trim(), expr: expr.trim() }]);
    setNewCol(""); setExpr(""); setPreview(null); setAutoNamed(false); setError(""); setSuccess("");
  }

  // Apply all queued
  async function applyAll() {
    if (!queue.length) return;
    setApplying(true); setError(""); setSuccess("");
    try {
      let last = null;
      for (const item of queue) {
        const r = await addFormulaColumn(sessionId, item.newCol, item.expr);
        pushHistory(item.newCol, item.expr); last = r;
      }
      setHistory(loadHistory());
      setSuccess(`${queue.length} column${queue.length>1?"s":""} added!`);
      setQueue([]);
      if (last) onDataChange?.(last);
    } catch (e) { setError(e?.response?.data?.detail || "Formula error."); }
    finally     { setApplying(false); }
  }

  const canApply = !!(newCol.trim() && expr.trim() && !loading && sessionId);

  return (
    <div className="pt-section">

      {/* Header */}
      <div className="pt-section-header">
        <Wand2 size={13} color="#a78bfa" />
        <span className="pt-section-title">Formula / Computed Column</span>
        <button
          className={`fm-toggle ${multiMode ? "fm-toggle--on" : ""}`}
          onClick={() => setMultiMode(m => !m)}
          title={multiMode ? "Single mode" : "Multi-column mode — queue multiple formulas"}>
          <Layers size={10}/> {multiMode ? "Multi" : "Single"}
        </button>
      </div>
      <p className="pt-desc">Create a new column using any pandas expression. Reference columns by name.</p>

      {/* ⑤ Categorised examples */}
      <div className="fm-cats">
        {EXAMPLE_CATS.map(cat => (
          <div key={cat.label}>
            <button
              className={`fm-cat-btn ${openCat===cat.label ? "fm-cat-btn--on" : ""}`}
              style={openCat===cat.label ? {borderColor:cat.color, color:cat.color} : {}}
              onClick={() => setOpenCat(o => o===cat.label ? null : cat.label)}>
              {openCat===cat.label ? <ChevronDown size={9}/> : <ChevronRight size={9}/>}
              {cat.label}
            </button>
            {openCat===cat.label && (
              <div className="fm-cat-body">
                {cat.items.map(ex => (
                  <button key={ex.label} className="fm-ex-row" onClick={() => applyExample(ex)} title={ex.desc}>
                    <span className="fm-ex-label">{ex.label}</span>
                    <span className="fm-ex-expr">{ex.expr}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* ① ② Column picker with type badges + search + cursor insert */}
      <div className="fm-picker">
        <div className="fm-picker-top">
          <span className="fm-picker-lbl">Columns — click to insert at cursor</span>
          <div className="fm-search-box">
            <Search size={9} color="var(--text-3)"/>
            <input className="fm-search" placeholder="filter…" value={colSearch}
              onChange={e => setColSearch(e.target.value)} />
          </div>
        </div>
        <div className="fm-chips">
          {filteredCols.map(col => {
            const b = colTypeBadge(col, profileMap);
            return (
              <button key={col} className="fm-chip" onClick={() => insertCol(col)}
                title={`${col} (${b.title}) — click to insert at cursor`}>
                <span className="fm-chip-badge" style={{color:b.color}}>{b.icon}</span>
                {col}
              </button>
            );
          })}
          {filteredCols.length === 0 && <span style={{fontSize:10,color:"var(--text-3)"}}>No match.</span>}
        </div>
      </div>

      {/* ④ Column name with auto-badge */}
      <label className="pt-label">
        New column name
        {autoNamed && <span className="fm-auto">auto</span>}
      </label>
      <input className="pt-input" placeholder="e.g. total_revenue"
        value={newCol}
        onChange={e => { setNewCol(e.target.value); setAutoNamed(false); }} />

      {/* Expression */}
      <label className="pt-label" style={{marginTop:8}}>Expression</label>
      <div style={{position:"relative"}}>
        <textarea
          ref={textareaRef}
          className={`pt-textarea ${error ? "fm-ta--err" : preview && !error ? "fm-ta--ok" : ""}`}
          rows={3}
          placeholder={"e.g. Price * Quantity\nor: FirstName + ' ' + LastName\nor: np.log1p(Revenue)"}
          value={expr}
          onChange={e => { setExpr(e.target.value); setError(""); setSuccess(""); }}
          onKeyDown={e => {
            if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
              e.preventDefault();
              if (multiMode) addToQueue(); else if (canApply) apply();
            }
          }}
        />
        {previewBusy && (
          <div style={{position:"absolute",bottom:7,right:7,color:"var(--text-3)"}}>
            <Loader2 size={11} className="spin"/>
          </div>
        )}
      </div>
      <p className="fm-hint">Click column above to insert at cursor · Ctrl+Enter to {multiMode ? "queue" : "apply"}</p>

      {/* ③ ⑨ Live preview */}
      {preview && !error && (
        <PreviewStrip vals={preview.preview_vals} outType={preview.out_type} rows={preview.row_count} />
      )}

      {error   && <div className="pt-msg pt-msg--err"><AlertTriangle size={11}/> {error}</div>}
      {success && <div className="pt-msg pt-msg--ok"><CheckCircle size={11}/> {success}</div>}

      {/* ⑦ Formula history */}
      {history.length > 0 && (
        <div className="fm-hist">
          <button className="fm-hist-toggle" onClick={() => setShowHist(h => !h)}>
            <Clock size={10}/> History ({history.length})
            {showHist ? <ChevronDown size={9}/> : <ChevronRight size={9}/>}
          </button>
          {showHist && (
            <div className="fm-hist-body">
              {history.map((h, i) => (
                <button key={i} className="fm-hist-row"
                  onClick={() => { setExpr(h.expr); setNewCol(h.newCol); setAutoNamed(false); }}
                  title={`${h.newCol} = ${h.expr}`}>
                  <span className="fm-hist-col">{h.newCol}</span>
                  <span className="fm-hist-expr">{h.expr}</span>
                </button>
              ))}
              <button className="fm-hist-clear"
                onClick={() => { saveHistory([]); setHistory([]); setShowHist(false); }}>
                <Trash2 size={9}/> Clear history
              </button>
            </div>
          )}
        </div>
      )}

      {/* ⑧ Actions */}
      <div className="fm-actions">
        {!multiMode ? (
          <button className="pt-btn pt-btn--primary" onClick={apply} disabled={!canApply}>
            {loading ? <Loader2 size={11} className="spin"/> : <Plus size={11}/>} Add Column
          </button>
        ) : (
          <>
            <button className="pt-btn pt-btn--outline" onClick={addToQueue} disabled={!canApply}>
              <Plus size={11}/> Queue
            </button>
            {queue.length > 0 && (
              <button className="pt-btn pt-btn--primary" onClick={applyAll} disabled={applying}>
                {applying ? <Loader2 size={11} className="spin"/> : <Zap size={11}/>}
                Apply {queue.length} Column{queue.length!==1?"s":""}
              </button>
            )}
          </>
        )}
      </div>

      {/* Queue list */}
      {multiMode && queue.length > 0 && (
        <div className="fm-queue">
          <div className="fm-queue-hdr"><Layers size={10}/> Queued ({queue.length})</div>
          {queue.map((item, i) => (
            <QueueItem key={i} item={item} idx={i}
              onRemove={idx => setQueue(q => q.filter((_,j)=>j!==idx))} />
          ))}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ── Main export
// ─────────────────────────────────────────────────────────────────────────────
export default function PowerToolsPanel({ sessionId, columns, columnProfiles, onDataChange }) {
  return (
    <PTCtx.Provider value={{ onDataChange }}>
      <div className="pt-root">
        <PIISection sessionId={sessionId} />
        <FormulaSection sessionId={sessionId} columns={columns} columnProfiles={columnProfiles} />

        <style>{`
          .pt-root { display:flex; flex-direction:column; }
          .pt-section { padding:14px; border-bottom:1px solid var(--border); }
          .pt-section:last-child { border-bottom:none; }
          .pt-section-header { display:flex; align-items:center; gap:7px; margin-bottom:6px; }
          .pt-section-title { font-size:13px; font-weight:700; color:var(--text-0); flex:1; }
          .pt-desc { font-size:11px; color:var(--text-2); margin:0 0 10px; line-height:1.5; }
          .pt-label { font-size:11px; font-weight:600; color:var(--text-2);
                      display:flex; align-items:center; gap:6px; margin-bottom:4px; }
          .pt-input { width:100%; box-sizing:border-box; padding:7px 10px; font-size:12px;
                      background:var(--surface-2); border:1px solid var(--border);
                      border-radius:7px; color:var(--text-0); outline:none; }
          .pt-input:focus { border-color:var(--accent); }
          .pt-textarea { width:100%; box-sizing:border-box; padding:8px 10px; font-size:12px;
                         background:var(--surface-2); border:1px solid var(--border);
                         border-radius:7px; color:var(--text-0); outline:none;
                         font-family:monospace; resize:vertical; line-height:1.5; }
          .pt-textarea:focus { border-color:var(--accent); }
          .fm-ta--err { border-color:#ef4444 !important; }
          .fm-ta--ok  { border-color:#10b981 !important; }

          .pt-btn { display:inline-flex; align-items:center; gap:6px; padding:7px 14px;
                    border:none; border-radius:8px; font-size:12px; font-weight:600; cursor:pointer; }
          .pt-btn--primary { background:var(--accent); color:#fff; }
          .pt-btn--danger  { background:#ef4444; color:#fff; }
          .pt-btn--outline { background:transparent; border:1px solid var(--accent);
                             color:var(--accent-light); }
          .pt-btn:disabled { opacity:.4; cursor:not-allowed; }
          .pt-btn:hover:not(:disabled) { filter:brightness(1.1); }

          .pt-msg { display:flex; align-items:center; gap:6px; padding:6px 10px;
                    border-radius:7px; font-size:11px; margin-top:6px; }
          .pt-msg--err { background:#ef444418; color:#ef4444; }
          .pt-msg--ok  { background:#10b98118; color:#10b981; }
          .pt-link { background:none; border:none; color:inherit; text-decoration:underline;
                     cursor:pointer; font-size:11px; margin-left:6px; padding:0; }

          /* PII */
          .pt-pii-list { display:flex; flex-direction:column; gap:5px; margin:8px 0; }
          .pt-pii-row  { display:flex; align-items:center; gap:8px; padding:7px 9px;
                         background:var(--surface-2); border-radius:8px;
                         border:1px solid var(--border); }
          .pt-pii-row--on { border-color:#ef4444; }
          .pt-pii-name { font-size:12px; font-weight:600; color:var(--text-1); font-family:monospace; }
          .pt-pii-type { font-size:10px; color:var(--text-3); }
          .pt-sel { font-size:11px; background:var(--surface-3); border:1px solid var(--border);
                    border-radius:5px; padding:2px 6px; color:var(--text-1); cursor:pointer; }

          /* Mode toggle */
          .fm-toggle { display:inline-flex; align-items:center; gap:4px; padding:3px 9px;
                       border-radius:99px; font-size:10px; font-weight:600;
                       border:1px solid var(--border); background:none;
                       color:var(--text-3); cursor:pointer; }
          .fm-toggle--on { border-color:var(--accent); color:var(--accent-light); background:var(--accent-dim); }
          .fm-toggle:hover { border-color:var(--accent); color:var(--accent-light); }

          /* Example categories */
          .fm-cats { display:flex; flex-direction:column; gap:3px; margin-bottom:10px; }
          .fm-cat-btn { display:inline-flex; align-items:center; gap:5px; padding:4px 10px;
                        border-radius:99px; font-size:10px; font-weight:600;
                        border:1px solid var(--border); background:var(--surface-2);
                        color:var(--text-2); cursor:pointer; width:100%; text-align:left; }
          .fm-cat-btn:hover { border-color:var(--border-2); color:var(--text-1); }
          .fm-cat-btn--on { background:var(--surface-3); }
          .fm-cat-body { margin-top:4px; background:var(--surface-2); border-radius:8px;
                         border:1px solid var(--border); overflow:hidden; }
          .fm-ex-row { display:flex; align-items:baseline; gap:8px; padding:6px 10px;
                       border:none; background:none; cursor:pointer; text-align:left;
                       width:100%; border-bottom:1px solid var(--border); }
          .fm-ex-row:last-child { border-bottom:none; }
          .fm-ex-row:hover { background:var(--surface-3); }
          .fm-ex-label { font-size:11px; font-weight:600; color:var(--text-1);
                         white-space:nowrap; min-width:92px; flex-shrink:0; }
          .fm-ex-expr  { font-size:10px; color:var(--text-3); font-family:monospace;
                         overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }

          /* Column picker */
          .fm-picker     { background:var(--surface-2); border:1px solid var(--border);
                           border-radius:8px; padding:8px; margin-bottom:10px; }
          .fm-picker-top { display:flex; align-items:center; justify-content:space-between;
                           margin-bottom:6px; }
          .fm-picker-lbl { font-size:9px; font-weight:700; color:var(--text-3);
                           text-transform:uppercase; letter-spacing:.06em; }
          .fm-search-box { display:flex; align-items:center; gap:4px; background:var(--surface-3);
                           border-radius:5px; padding:3px 7px; border:1px solid var(--border); }
          .fm-search     { background:none; border:none; outline:none; font-size:10px;
                           color:var(--text-1); width:72px; }
          .fm-chips      { display:flex; flex-wrap:wrap; gap:4px; max-height:84px;
                           overflow-y:auto; scrollbar-width:thin; }
          .fm-chip       { display:inline-flex; align-items:center; gap:4px; padding:3px 8px;
                           background:var(--surface-3); border:1px solid var(--border);
                           border-radius:6px; font-size:10px; color:var(--text-1);
                           font-family:monospace; cursor:pointer; white-space:nowrap; }
          .fm-chip:hover { border-color:var(--accent); background:var(--accent-dim);
                           color:var(--accent-light); }
          .fm-chip-badge { font-size:9px; font-weight:800; min-width:10px; text-align:center; }

          /* Auto badge */
          .fm-auto { font-size:9px; font-weight:600; padding:1px 6px; border-radius:99px;
                     background:rgba(99,102,241,.15); color:var(--accent-light);
                     border:1px solid rgba(99,102,241,.25); }

          .fm-hint { font-size:10px; color:var(--text-3); margin:3px 0 0; line-height:1.4; }

          /* Preview strip */
          .fp-strip  { background:rgba(16,185,129,.08); border:1px solid rgba(16,185,129,.22);
                       border-radius:8px; padding:8px 10px; margin-top:6px; }
          .fp-header { display:flex; align-items:center; gap:5px; margin-bottom:5px;
                       font-size:10px; font-weight:600; color:#10b981; }
          .fp-type   { margin-left:auto; font-size:9px; font-weight:700;
                       text-transform:uppercase; letter-spacing:.05em; }
          .fp-vals   { display:flex; gap:5px; flex-wrap:wrap; }
          .fp-val    { padding:2px 7px; background:rgba(255,255,255,.05); border-radius:5px;
                       font-size:10px; font-family:monospace; color:var(--text-1);
                       border:1px solid var(--border); }

          /* History */
          .fm-hist        { margin-top:8px; }
          .fm-hist-toggle { display:inline-flex; align-items:center; gap:5px; background:none;
                            border:none; color:var(--text-3); font-size:10px; cursor:pointer; padding:0; }
          .fm-hist-toggle:hover { color:var(--text-1); }
          .fm-hist-body   { margin-top:4px; background:var(--surface-2); border:1px solid var(--border);
                            border-radius:8px; overflow:hidden; }
          .fm-hist-row    { display:flex; align-items:baseline; gap:6px; padding:6px 9px;
                            border:none; background:none; cursor:pointer; text-align:left;
                            width:100%; border-bottom:1px solid var(--border); }
          .fm-hist-row:last-of-type { border-bottom:none; }
          .fm-hist-row:hover { background:var(--surface-3); }
          .fm-hist-col    { font-size:11px; font-weight:600; color:var(--accent-light);
                            min-width:80px; white-space:nowrap; flex-shrink:0; }
          .fm-hist-expr   { font-size:10px; color:var(--text-3); font-family:monospace;
                            overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
          .fm-hist-clear  { display:inline-flex; align-items:center; gap:4px; margin:4px;
                            padding:4px 8px; border:none; background:none;
                            color:var(--text-3); font-size:10px; cursor:pointer;
                            border-radius:5px; }
          .fm-hist-clear:hover { color:#ef4444; background:rgba(239,68,68,.08); }

          /* Actions */
          .fm-actions { display:flex; gap:6px; flex-wrap:wrap; margin-top:6px; }

          /* Queue */
          .fm-queue     { margin-top:8px; background:var(--surface-2); border:1px solid var(--border);
                          border-radius:8px; padding:6px; }
          .fm-queue-hdr { display:flex; align-items:center; gap:5px; font-size:10px; font-weight:700;
                          color:var(--text-3); text-transform:uppercase; letter-spacing:.06em;
                          margin-bottom:5px; padding:0 2px; }
          .fq-item  { display:flex; align-items:center; gap:6px; padding:5px 7px;
                      background:var(--surface-3); border-radius:6px; margin-bottom:3px; }
          .fq-num   { font-size:9px; font-weight:700; color:var(--text-3); min-width:14px; text-align:center; }
          .fq-body  { flex:1; min-width:0; display:flex; flex-direction:column; gap:1px; }
          .fq-col   { font-size:11px; font-weight:600; color:var(--accent-light); }
          .fq-expr  { font-size:10px; color:var(--text-3); font-family:monospace;
                      overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
          .fq-rm    { display:flex; align-items:center; background:none; border:none;
                      color:var(--text-3); cursor:pointer; padding:2px; border-radius:4px; }
          .fq-rm:hover { color:#ef4444; background:rgba(239,68,68,.1); }

          @keyframes spin { to { transform:rotate(360deg); } }
          .spin { animation:spin .8s linear infinite; }
        `}</style>
      </div>
    </PTCtx.Provider>
  );
}
