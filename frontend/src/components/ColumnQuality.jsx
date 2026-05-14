/**
 * ColumnQuality — per-column quality bars with stats.
 * Derived from the profile response from /api/profile.
 */
import React, { useState } from "react";
import { BarChart2, ChevronDown, ChevronRight } from "lucide-react";

function qualityScore(col) {
  let s = 100;
  s -= (col.missing_pct ?? 0) * 0.6;
  if (col.mixed_types)         s -= 15;
  if (col.whitespace_count > 0) s -= 5;
  if (col.invalid_format_count > 0) s -= 10;
  return Math.max(0, Math.round(s));
}

function scoreColor(s) {
  if (s >= 80) return "#22c55e";
  if (s >= 50) return "#f59e0b";
  return "#ef4444";
}

export default function ColumnQuality({ profile }) {
  const [open, setOpen] = useState(true);

  if (!profile?.columns_profile?.length) return null;

  const cols = profile.columns_profile;

  return (
    <div className="cq-wrap">
      <button className="cq-header" onClick={() => setOpen(o => !o)}>
        <BarChart2 size={14} color="var(--accent)" />
        <span className="cq-title">Column Quality</span>
        <span className="cq-count">{cols.length}</span>
        {open ? <ChevronDown size={13}/> : <ChevronRight size={13}/>}
      </button>

      {open && (
        <div className="cq-list">
          {cols.map((col, i) => {
            const score = qualityScore(col);
            const color = scoreColor(score);
            return (
              <div key={i} className="cq-row">
                <div className="cq-row-top">
                  <span className="cq-name">{col.column}</span>
                  <span className="cq-type">{col.detected_type}</span>
                  <span className="cq-score" style={{ color }}>{score}</span>
                </div>
                <div className="cq-bar-track">
                  <div
                    className="cq-bar-fill"
                    style={{ width: `${score}%`, background: color }}
                  />
                </div>
                <div className="cq-row-stats">
                  {col.missing_pct > 0 && (
                    <span className="cq-stat cq-stat--warn">
                      {col.missing_pct}% missing
                    </span>
                  )}
                  {col.mixed_types && (
                    <span className="cq-stat cq-stat--err">mixed types</span>
                  )}
                  {col.whitespace_count > 0 && (
                    <span className="cq-stat">
                      {col.whitespace_count} whitespace
                    </span>
                  )}
                  {col.invalid_format_count > 0 && (
                    <span className="cq-stat cq-stat--err">
                      {col.invalid_format_count} invalid
                    </span>
                  )}
                  {col.numeric_stats?.mean != null && (
                    <span className="cq-stat">
                      μ {col.numeric_stats.mean}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <style>{`
        .cq-wrap      { background:var(--surface-1); border-radius:12px; overflow:hidden; }
        .cq-header    { width:100%; display:flex; align-items:center; gap:8px; padding:12px 14px;
                        background:none; border:none; cursor:pointer; color:var(--text-1); }
        .cq-header:hover { background:var(--surface-2); }
        .cq-title     { flex:1; font-size:13px; font-weight:700; color:var(--text-0); text-align:left; }
        .cq-count     { background:var(--surface-3); color:var(--text-2); font-size:11px;
                        font-weight:700; border-radius:99px; padding:1px 7px; }
        .cq-list      { padding:4px 14px 12px; display:flex; flex-direction:column; gap:8px; }
        .cq-row       { display:flex; flex-direction:column; gap:3px; }
        .cq-row-top   { display:flex; align-items:center; gap:6px; }
        .cq-name      { flex:1; font-size:12px; font-weight:600; color:var(--text-0);
                        white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .cq-type      { font-size:10px; color:var(--text-3); background:var(--surface-3);
                        padding:1px 5px; border-radius:4px; font-family:monospace; }
        .cq-score     { font-size:12px; font-weight:700; min-width:24px; text-align:right; }
        .cq-bar-track { height:4px; background:var(--surface-3); border-radius:99px; overflow:hidden; }
        .cq-bar-fill  { height:100%; border-radius:99px; transition:width .4s ease; }
        .cq-row-stats { display:flex; flex-wrap:wrap; gap:4px; }
        .cq-stat      { font-size:10px; color:var(--text-3); background:var(--surface-2);
                        padding:1px 5px; border-radius:4px; }
        .cq-stat--warn { color:#f59e0b; background:rgba(245,158,11,.1); }
        .cq-stat--err  { color:#ef4444; background:rgba(239,68,68,.1); }
      `}</style>
    </div>
  );
}
