/**
 * FuzzyDedupPanel — near-duplicate detection using RapidFuzz.
 * Shows duplicate groups with similarity scores and a one-click remove.
 */
import React, { useState } from "react";
import { Search, Trash2, Loader2, AlertCircle, CheckCircle, ChevronDown, ChevronRight } from "lucide-react";
import { findFuzzyDuplicates, removeFuzzyDuplicates } from "../services/api";

export default function FuzzyDedupPanel({ sessionId, columns, onApplied }) {
  const [threshold, setThreshold] = useState(85);
  const [result,    setResult]    = useState(null);
  const [loading,   setLoading]   = useState(false);
  const [removing,  setRemoving]  = useState(false);
  const [error,     setError]     = useState("");
  const [expanded,  setExpanded]  = useState({});

  async function handleFind() {
    setLoading(true); setError(""); setResult(null);
    try {
      const res = await findFuzzyDuplicates(sessionId, threshold);
      setResult(res);
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Scan failed.");
    } finally { setLoading(false); }
  }

  async function handleRemove() {
    setRemoving(true); setError("");
    try {
      const res = await removeFuzzyDuplicates(sessionId, threshold);
      onApplied?.(res);
      setResult(null);
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Remove failed.");
    } finally { setRemoving(false); }
  }

  const groups = result?.groups ?? [];

  return (
    <div className="fz-wrap">
      <div className="fz-header">
        <Search size={14} color="var(--accent)" />
        <span className="fz-title">Fuzzy Duplicate Detection</span>
      </div>

      <div className="fz-controls">
        <div className="fz-control-row">
          <label className="fz-label">
            Similarity threshold
            <span className="fz-threshold-val">{threshold}%</span>
          </label>
          <input type="range" min={50} max={100} value={threshold}
            onChange={e => setThreshold(+e.target.value)}
            className="fz-slider" />
          <div className="fz-threshold-hint">
            {threshold >= 95 ? "Very strict — exact matches only" :
             threshold >= 85 ? "Recommended — catches typos & variants" :
             threshold >= 70 ? "Loose — may flag false positives" :
                               "Very loose — many false positives likely"}
          </div>
        </div>
        <button className="fz-btn fz-btn--scan" onClick={handleFind}
          disabled={loading || removing}>
          {loading ? <Loader2 size={12} className="spin" /> : <Search size={12} />}
          Scan for duplicates
        </button>
      </div>

      {error && <div className="fz-error"><AlertCircle size={12} />{error}</div>}

      {result && (
        <div className="fz-result">
          <div className="fz-result-summary">
            {groups.length === 0 ? (
              <div className="fz-clean">
                <CheckCircle size={14} color="#22c55e" />
                No near-duplicates found at {threshold}% threshold.
              </div>
            ) : (
              <>
                <div className="fz-stats">
                  <span className="fz-stat">
                    <span className="fz-stat-val" style={{color:"#ef4444"}}>{result.total_duplicates}</span>
                    rows to remove
                  </span>
                  <span className="fz-stat">
                    <span className="fz-stat-val">{groups.length}</span>
                    duplicate groups
                  </span>
                  <span className="fz-stat">
                    <span className="fz-stat-val">{result.columns_used?.join(", ")}</span>
                    columns compared
                  </span>
                </div>
                <button className="fz-btn fz-btn--remove" onClick={handleRemove}
                  disabled={removing}>
                  {removing ? <Loader2 size={12} className="spin" /> : <Trash2 size={12} />}
                  Remove {result.total_duplicates} duplicates
                </button>
              </>
            )}
          </div>

          {groups.length > 0 && (
            <div className="fz-groups">
              <div className="fz-groups-title">Sample groups (showing up to 10)</div>
              {groups.slice(0, 10).map((g, i) => (
                <div key={i} className="fz-group">
                  <button className="fz-group-toggle"
                    onClick={() => setExpanded(e => ({ ...e, [i]: !e[i] }))}>
                    {expanded[i] ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                    <span className="fz-group-score">{g.score}% match</span>
                    <span className="fz-group-count">{g.duplicate_idxs.length} duplicate{g.duplicate_idxs.length > 1 ? "s" : ""}</span>
                  </button>
                  {expanded[i] && (
                    <div className="fz-group-detail">
                      <div className="fz-row-label">Keep (row {g.canonical_idx})</div>
                      <div className="fz-row fz-row--keep">
                        {Object.entries(g.canonical_row).slice(0, 4).map(([k, v]) => (
                          <span key={k} className="fz-cell"><span className="fz-cell-key">{k}</span>{v}</span>
                        ))}
                      </div>
                      <div className="fz-row-label">Remove (row {g.duplicate_idxs[0]})</div>
                      <div className="fz-row fz-row--remove">
                        {Object.entries(g.sample_duplicate).slice(0, 4).map(([k, v]) => (
                          <span key={k} className="fz-cell"><span className="fz-cell-key">{k}</span>{v}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <style>{`
        .fz-wrap{background:var(--surface-1);border-radius:12px;overflow:hidden;display:flex;flex-direction:column}
        .fz-header{display:flex;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid var(--border)}
        .fz-title{font-size:13px;font-weight:700;color:var(--text-0)}
        .fz-controls{padding:12px 14px;display:flex;flex-direction:column;gap:10px;border-bottom:1px solid var(--border)}
        .fz-control-row{display:flex;flex-direction:column;gap:4px}
        .fz-label{display:flex;justify-content:space-between;font-size:11px;font-weight:600;color:var(--text-2);text-transform:uppercase;letter-spacing:.06em}
        .fz-threshold-val{color:var(--accent);font-weight:700}
        .fz-slider{width:100%;accent-color:var(--accent)}
        .fz-threshold-hint{font-size:10px;color:var(--text-3);font-style:italic}
        .fz-btn{display:inline-flex;align-items:center;gap:5px;padding:6px 12px;border-radius:6px;border:none;font-size:12px;font-weight:600;cursor:pointer}
        .fz-btn:disabled{opacity:.45;cursor:not-allowed}
        .fz-btn--scan{background:var(--accent);color:#fff;align-self:flex-start}
        .fz-btn--remove{background:#ef4444;color:#fff}
        .fz-error{display:flex;align-items:center;gap:6px;font-size:11px;color:#ef4444;background:rgba(239,68,68,.1);padding:7px 14px}
        .fz-result{padding:10px 14px;display:flex;flex-direction:column;gap:10px}
        .fz-clean{display:flex;align-items:center;gap:6px;font-size:12px;color:#22c55e}
        .fz-result-summary{display:flex;flex-direction:column;gap:8px}
        .fz-stats{display:flex;gap:14px;flex-wrap:wrap}
        .fz-stat{display:flex;flex-direction:column;font-size:10px;color:var(--text-2);text-transform:uppercase;letter-spacing:.05em}
        .fz-stat-val{font-size:18px;font-weight:800;color:var(--text-0);letter-spacing:0;text-transform:none}
        .fz-groups-title{font-size:10px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:.06em}
        .fz-groups{display:flex;flex-direction:column;gap:4px}
        .fz-group{background:var(--surface-2);border-radius:8px;overflow:hidden}
        .fz-group-toggle{width:100%;display:flex;align-items:center;gap:6px;padding:7px 10px;background:none;border:none;cursor:pointer;color:var(--text-1);font-size:11px;text-align:left}
        .fz-group-score{font-weight:700;color:var(--accent)}
        .fz-group-count{color:var(--text-3);margin-left:auto}
        .fz-group-detail{padding:0 10px 8px;display:flex;flex-direction:column;gap:4px}
        .fz-row-label{font-size:9px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:.06em;margin-top:4px}
        .fz-row{display:flex;flex-wrap:wrap;gap:4px}
        .fz-row--keep{opacity:.9}
        .fz-row--remove{opacity:.6}
        .fz-cell{font-size:10px;background:var(--surface-1);border-radius:4px;padding:2px 6px;color:var(--text-1);max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .fz-cell-key{color:var(--text-3);margin-right:4px}
        @keyframes spin{to{transform:rotate(360deg)}}.spin{animation:spin .7s linear infinite}
      `}</style>
    </div>
  );
}
