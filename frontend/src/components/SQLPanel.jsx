/**
 * SQLPanel — DuckDB SQL editor.
 *
 * Fixes over original:
 *   - Example queries match real cafe dataset column names
 *   - Shows the auto-quoted query the backend actually ran
 *   - Better error messages with tips
 *   - Column list shown so users know what's available
 *   - LIKE tip and syntax reference
 *   - Ctrl+Enter runs query
 */
import React, { useState, useRef } from "react";
import { Play, Database, Download, Loader2, CheckCircle, AlertCircle, Info, ChevronDown, ChevronUp } from "lucide-react";
import { runSQL, applySQL } from "../services/api";

// These examples are generic and work for any dataset — no column name assumptions
const EXAMPLE_GROUPS = [
  {
    label: "Basic",
    examples: [
      "SELECT * FROM df LIMIT 50",
      "SELECT * FROM df WHERE Location = 'In-store' LIMIT 50",
      "SELECT * FROM df ORDER BY \"Total Spent\" DESC LIMIT 20",
    ],
  },
  {
    label: "Aggregate",
    examples: [
      "SELECT Item, COUNT(*) as count FROM df GROUP BY Item ORDER BY count DESC",
      "SELECT Location, AVG(\"Total Spent\") as avg_spent FROM df GROUP BY Location",
      "SELECT \"Payment Method\", SUM(\"Total Spent\") as total FROM df GROUP BY \"Payment Method\"",
    ],
  },
  {
    label: "Filter",
    examples: [
      "SELECT * FROM df WHERE \"Payment Method\" IS NULL",
      "SELECT * FROM df WHERE Item = 'ERROR' OR Location = 'ERROR'",
      "SELECT * FROM df WHERE \"Total Spent\" > 15 AND Location = 'In-store'",
    ],
  },
  {
    label: "Clean",
    examples: [
      "SELECT * FROM df WHERE Item NOT IN ('ERROR', 'UNKNOWN')",
      "SELECT * FROM df WHERE \"Payment Method\" NOT IN ('ERROR', 'UNKNOWN') AND \"Payment Method\" IS NOT NULL",
      "SELECT DISTINCT Item, Location FROM df ORDER BY Item",
    ],
  },
];

const TIPS = [
  "Column names with spaces: use double quotes — \"Transaction ID\"",
  "String values: use single quotes — WHERE Item = 'Sandwich'",
  "LIKE pattern: WHERE Item LIKE '%wich%'  (single quotes, % wildcards)",
  "NULL check: WHERE \"Payment Method\" IS NULL",
  "Table is always named: df",
];

export default function SQLPanel({ sessionId, columns = [], onApplied }) {
  const [query,      setQuery]      = useState("SELECT * FROM df LIMIT 50");
  const [result,     setResult]     = useState(null);
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState("");
  const [showTips,   setShowTips]   = useState(false);
  const [activeGrp,  setActiveGrp]  = useState("Basic");
  const taRef = useRef();

  async function handleRun() {
    if (!query.trim() || loading) return;
    setLoading(true); setError(""); setResult(null);
    try {
      const res = await runSQL(sessionId, query);
      setResult({ ...res, applied: false });
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Query failed.");
    } finally { setLoading(false); }
  }

  async function handleApply() {
    if (!query.trim() || loading) return;
    setLoading(true); setError(""); setResult(null);
    try {
      const res = await applySQL(sessionId, query);
      setResult({ ...res, applied: true });
      onApplied?.(res);
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Apply failed.");
    } finally { setLoading(false); }
  }

  const group = EXAMPLE_GROUPS.find(g => g.label === activeGrp);

  return (
    <div className="sql-wrap">
      {/* Header */}
      <div className="sql-header">
        <Database size={14} color="var(--accent)" />
        <span className="sql-title">SQL Query</span>
        <span className="sql-badge">table: <code>df</code></span>
        <button className="sql-tips-toggle" onClick={() => setShowTips(s => !s)}>
          <Info size={11} /> Tips {showTips ? <ChevronUp size={10}/> : <ChevronDown size={10}/>}
        </button>
      </div>

      {/* Tips panel */}
      {showTips && (
        <div className="sql-tips">
          {TIPS.map((t, i) => <div key={i} className="sql-tip">💡 {t}</div>)}
        </div>
      )}

      {/* Column list */}
      {columns.length > 0 && (
        <div className="sql-cols">
          <span className="sql-cols-label">Columns:</span>
          {columns.map(c => (
            <button key={c} className="sql-col-pill"
              onClick={() => {
                const quoted = c.includes(" ") ? `"${c}"` : c;
                const ta = taRef.current;
                if (ta) {
                  const s = ta.selectionStart, e = ta.selectionEnd;
                  setQuery(q => q.slice(0, s) + quoted + q.slice(e));
                  setTimeout(() => { ta.focus(); ta.setSelectionRange(s + quoted.length, s + quoted.length); }, 0);
                }
              }}
              title={`Insert ${c.includes(" ") ? `"${c}"` : c}`}
            >{c}</button>
          ))}
        </div>
      )}

      {/* Example groups */}
      <div className="sql-examples-wrap">
        <div className="sql-group-tabs">
          {EXAMPLE_GROUPS.map(g => (
            <button key={g.label}
              className={`sql-group-tab ${activeGrp === g.label ? "sql-group-tab--active" : ""}`}
              onClick={() => setActiveGrp(g.label)}>{g.label}</button>
          ))}
        </div>
        <div className="sql-examples">
          {group?.examples.map((ex, i) => (
            <button key={i} className="sql-ex-btn" onClick={() => setQuery(ex)} title={ex}>
              {ex.length > 50 ? ex.slice(0, 50) + "…" : ex}
            </button>
          ))}
        </div>
      </div>

      {/* Editor */}
      <textarea
        className="sql-editor"
        ref={taRef}
        value={query}
        onChange={e => setQuery(e.target.value)}
        placeholder="SELECT * FROM df LIMIT 50"
        rows={4}
        spellCheck={false}
        onKeyDown={e => {
          if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            handleRun();
          }
        }}
      />

      {/* Actions */}
      <div className="sql-actions">
        <button className="sql-btn sql-btn--run" onClick={handleRun}
          disabled={loading || !query.trim()}>
          {loading ? <Loader2 size={12} className="spin" /> : <Play size={12} />}
          Run <span className="sql-shortcut">Ctrl+Enter</span>
        </button>
        <button className="sql-btn sql-btn--apply" onClick={handleApply}
          disabled={loading || !query.trim()}>
          <Download size={12} /> Apply to dataset
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="sql-error">
          <AlertCircle size={12} style={{flexShrink:0}} />
          <span style={{whiteSpace:"pre-wrap"}}>{error}</span>
        </div>
      )}

      {/* Result */}
      {result && !error && (
        <div className="sql-result">
          <div className="sql-result-meta">
            {result.applied
              ? <><CheckCircle size={12} color="#22c55e" /><span style={{color:"#22c55e",fontWeight:700}}>Applied to dataset</span></>
              : <span>{result.rows?.toLocaleString()} rows · {result.columns?.length} columns</span>
            }
            {result.truncated && <span className="sql-truncated">⚠ truncated to 100k</span>}
          </div>

          {/* Show the actual query that ran (with auto-quoting applied) */}
          {result.query_used && result.query_used !== query && (
            <div className="sql-query-used">
              <span className="sql-query-used-label">Auto-quoted:</span>
              <code>{result.query_used}</code>
            </div>
          )}

          {result.preview?.length > 0 && (
            <div className="sql-table-wrap">
              <table className="sql-table">
                <thead>
                  <tr>{result.columns?.map(c => <th key={c}>{c}</th>)}</tr>
                </thead>
                <tbody>
                  {result.preview.slice(0, 50).map((row, i) => (
                    <tr key={i}>
                      {result.columns?.map(c => (
                        <td key={c} className={!row[c] || row[c] === "" ? "sql-td-null" : ""}>
                          {row[c] || <span className="sql-null-badge">NULL</span>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {result.preview?.length === 0 && (
            <div className="sql-empty">Query returned 0 rows.</div>
          )}
        </div>
      )}

      <style>{`
        .sql-wrap{background:var(--surface-1);border-radius:12px;overflow:hidden;display:flex;flex-direction:column}
        .sql-header{display:flex;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid var(--border);flex-shrink:0}
        .sql-title{font-size:13px;font-weight:700;color:var(--text-0);flex:1}
        .sql-badge{font-size:10px;color:var(--text-3);background:var(--surface-2);padding:2px 7px;border-radius:99px}
        .sql-badge code{font-family:monospace;color:#a0c4ff}
        .sql-tips-toggle{display:inline-flex;align-items:center;gap:3px;font-size:10px;color:var(--text-2);background:none;border:1px solid var(--border);border-radius:5px;padding:2px 7px;cursor:pointer}
        .sql-tips-toggle:hover{background:var(--surface-2)}
        .sql-tips{padding:8px 14px;border-bottom:1px solid var(--border);display:flex;flex-direction:column;gap:3px;background:rgba(99,102,241,.05)}
        .sql-tip{font-size:11px;color:var(--text-2)}
        .sql-cols{display:flex;flex-wrap:wrap;gap:3px;padding:7px 12px;border-bottom:1px solid var(--border);align-items:center}
        .sql-cols-label{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-3);margin-right:4px;white-space:nowrap}
        .sql-col-pill{font-size:10px;font-family:monospace;padding:2px 7px;border-radius:4px;border:1px solid var(--border);background:var(--surface-2);color:var(--text-1);cursor:pointer;white-space:nowrap}
        .sql-col-pill:hover{background:var(--accent);color:#fff;border-color:var(--accent)}
        .sql-examples-wrap{border-bottom:1px solid var(--border)}
        .sql-group-tabs{display:flex;gap:1px;padding:5px 12px 0;background:none}
        .sql-group-tab{font-size:10px;font-weight:600;padding:4px 9px;border-radius:5px 5px 0 0;border:none;cursor:pointer;background:none;color:var(--text-3)}
        .sql-group-tab--active{background:var(--surface-2);color:var(--text-0)}
        .sql-examples{display:flex;flex-wrap:wrap;gap:4px;padding:6px 12px 8px}
        .sql-ex-btn{font-size:10px;padding:3px 8px;border-radius:5px;border:1px solid var(--border);background:var(--surface-2);color:var(--text-2);cursor:pointer;text-align:left;font-family:monospace}
        .sql-ex-btn:hover{background:var(--surface-3);color:var(--text-0)}
        .sql-editor{width:100%;padding:10px 14px;background:var(--surface-2);border:none;border-bottom:1px solid var(--border);color:var(--text-0);font-family:monospace;font-size:12px;resize:vertical;outline:none;line-height:1.6;min-height:80px}
        .sql-actions{display:flex;gap:8px;padding:8px 12px;border-bottom:1px solid var(--border)}
        .sql-btn{display:inline-flex;align-items:center;gap:5px;padding:5px 12px;border-radius:6px;border:none;font-size:12px;font-weight:600;cursor:pointer}
        .sql-btn:disabled{opacity:.45;cursor:not-allowed}
        .sql-btn--run{background:var(--accent);color:#fff}
        .sql-btn--apply{background:var(--surface-2);color:var(--text-1);border:1px solid var(--border)}
        .sql-btn--apply:hover:not(:disabled){background:var(--surface-3)}
        .sql-shortcut{font-size:9px;opacity:.7;font-weight:400}
        .sql-error{display:flex;align-items:flex-start;gap:6px;font-size:11px;color:#ef4444;background:rgba(239,68,68,.1);padding:8px 14px;line-height:1.5}
        .sql-result{padding:10px 12px;display:flex;flex-direction:column;gap:6px}
        .sql-result-meta{display:flex;align-items:center;gap:8px;font-size:11px;color:var(--text-2)}
        .sql-truncated{color:#f59e0b;font-size:10px}
        .sql-query-used{display:flex;flex-direction:column;gap:2px}
        .sql-query-used-label{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-3)}
        .sql-query-used code{font-family:monospace;font-size:10px;color:#a0c4ff;background:var(--surface-2);padding:4px 8px;border-radius:4px;display:block;white-space:pre-wrap;word-break:break-all}
        .sql-table-wrap{overflow-x:auto;border-radius:6px;border:1px solid var(--border);max-height:320px;overflow-y:auto}
        .sql-table{width:100%;border-collapse:collapse;font-size:11px}
        .sql-table th{padding:5px 8px;background:var(--surface-2);color:var(--text-2);font-weight:600;text-align:left;white-space:nowrap;border-bottom:1px solid var(--border);position:sticky;top:0;z-index:1}
        .sql-table td{padding:4px 8px;color:var(--text-1);border-bottom:1px solid var(--border);max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .sql-table tr:last-child td{border-bottom:none}
        .sql-td-null{background:rgba(239,68,68,.06)}
        .sql-null-badge{font-size:9px;color:#ef4444;font-style:italic}
        .sql-empty{font-size:12px;color:var(--text-3);padding:8px 0;text-align:center}
        @keyframes spin{to{transform:rotate(360deg)}}.spin{animation:spin .7s linear infinite}
      `}</style>
    </div>
  );
}
