/**
 * HealthScoreCard v7 — upgraded for health_score v3 backend.
 * Shows breakdown category bar chart + detail subtitles on deductions.
 */
import React, { useState } from "react";
import { ChevronDown, ChevronRight, AlertTriangle } from "lucide-react";

const RADIUS = 16;
const CIRC   = 2 * Math.PI * RADIUS;

const CAT_COLORS = {
  Completeness: "#ef4444", Duplicates: "#f97316", Structural: "#f59e0b",
  Format: "#eab308", Type: "#6366f1", Date: "#0891b2", Anomalies: "#7c3aed",
};

function scoreColor(s) {
  if (s >= 80) return "#22c55e";
  if (s >= 50) return "#f59e0b";
  return "#ef4444";
}
function scoreLabel(s) {
  if (s >= 80) return "Healthy";
  if (s >= 50) return "Needs Work";
  return "Critical";
}

export default function HealthScoreCard({ health }) {
  const [expanded, setExpanded] = useState(false);
  if (!health) return null;

  const score     = Math.round(health.score ?? 0);
  const color     = scoreColor(score);
  const dash      = (score / 100) * CIRC;
  const deds      = health.deductions ?? [];
  const grade     = health.grade ?? "";
  const breakdown = health.breakdown ?? null;
  const maxPen    = breakdown ? Math.max(...Object.values(breakdown), 1) : 1;

  return (
    <div className="hsc-wrap">
      <div className="hsc-strip">
        <svg viewBox="0 0 40 40" width={34} height={34} style={{ flexShrink: 0 }}>
          <circle cx={20} cy={20} r={RADIUS} fill="none" stroke="var(--surface-3)" strokeWidth={4} />
          <circle cx={20} cy={20} r={RADIUS} fill="none" stroke={color} strokeWidth={4}
            strokeDasharray={`${dash} ${CIRC}`} strokeLinecap="round" transform="rotate(-90 20 20)"
            style={{ transition: "stroke-dasharray .6s ease" }} />
          <text x={20} y={21} textAnchor="middle" dominantBaseline="middle"
            style={{ fontSize: 9, fontWeight: 800, fill: color, fontFamily: "inherit" }}>{score}</text>
        </svg>
        <span className="hsc-label" style={{ color }}>{scoreLabel(score)}</span>
        <span className="hsc-grade" style={{ color }}>{grade}</span>
        <div className="hsc-divider" />
        <StatPill label="Missing"  value={`${health.missing_pct ?? 0}%`}    bad={(health.missing_pct ?? 0) > 5} />
        <StatPill label="Dupes"    value={`${health.duplicate_pct ?? 0}%`}  bad={(health.duplicate_pct ?? 0) > 1} />
        <StatPill label="Issues"   value={health.total_issues ?? 0}          bad={(health.total_issues ?? 0) > 0} warn />
        <div className="hsc-bar-track" title={`Score: ${score}/100`}>
          <div className="hsc-bar-fill" style={{ width: `${score}%`, background: color }} />
        </div>
        {deds.length > 0 && (
          <button className="hsc-expand" onClick={() => setExpanded(e => !e)} title="Show breakdown">
            {expanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
          </button>
        )}
      </div>

      {expanded && deds.length > 0 && (
        <div className="hsc-expanded">
          {breakdown && Object.keys(breakdown).length > 0 && (
            <div className="hsc-breakdown">
              <div className="hsc-section-label">Penalty by category</div>
              {Object.entries(breakdown).sort((a, b) => b[1] - a[1]).map(([cat, pts]) => {
                const bc = CAT_COLORS[cat] ?? "#6b7280";
                return (
                  <div key={cat} className="hsc-cat-row">
                    <span className="hsc-cat-name">{cat}</span>
                    <div className="hsc-cat-track">
                      <div className="hsc-cat-fill" style={{ width: `${Math.round((pts / maxPen) * 100)}%`, background: bc }} />
                    </div>
                    <span className="hsc-cat-pts" style={{ color: bc }}>−{pts.toFixed(1)}</span>
                  </div>
                );
              })}
            </div>
          )}
          <div className="hsc-section-label" style={{ marginTop: breakdown ? 8 : 0 }}>All deductions</div>
          <ul className="hsc-deds">
            {deds.map((d, i) => (
              <li key={i} className="hsc-ded-row">
                <AlertTriangle size={9} color="#ef4444" style={{ flexShrink: 0, marginTop: 1 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <span className="hsc-ded-reason">{d.reason}</span>
                  {d.detail && <div className="hsc-ded-detail">{d.detail}</div>}
                </div>
                <span className="hsc-ded-pts">−{Math.abs(typeof d.points === "number" ? d.points.toFixed(1) : d.points)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <style>{`
        .hsc-wrap{background:var(--surface-2);border-radius:var(--radius-md);border:1px solid var(--border);overflow:hidden;flex-shrink:0}
        .hsc-strip{display:flex;align-items:center;gap:7px;padding:5px 10px}
        .hsc-label{font-size:11px;font-weight:700;white-space:nowrap}
        .hsc-grade{font-size:10px;font-weight:600;opacity:.7}
        .hsc-divider{width:1px;height:16px;background:var(--border);flex-shrink:0;margin:0 2px}
        .hsc-stat{display:flex;flex-direction:column;align-items:center;min-width:36px}
        .hsc-stat-val{font-size:11px;font-weight:700;line-height:1.1}
        .hsc-stat-lbl{font-size:8px;color:var(--text-3);text-transform:uppercase;letter-spacing:.05em}
        .hsc-bar-track{flex:1;height:3px;background:var(--surface-3);border-radius:99px;overflow:hidden;min-width:30px}
        .hsc-bar-fill{height:100%;border-radius:99px;transition:width .6s ease}
        .hsc-expand{background:none;border:none;cursor:pointer;color:var(--text-3);padding:3px;border-radius:4px;display:flex;flex-shrink:0}
        .hsc-expand:hover{background:var(--surface-3);color:var(--text-1)}
        .hsc-expanded{border-top:1px solid var(--border);padding:8px 10px 10px}
        .hsc-section-label{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-3);margin-bottom:4px}
        .hsc-breakdown{display:flex;flex-direction:column;gap:3px;margin-bottom:4px}
        .hsc-cat-row{display:grid;grid-template-columns:80px 1fr 32px;align-items:center;gap:6px}
        .hsc-cat-name{font-size:10px;color:var(--text-2);text-align:right}
        .hsc-cat-track{height:4px;background:var(--surface-3);border-radius:99px;overflow:hidden}
        .hsc-cat-fill{height:100%;border-radius:99px;transition:width .5s ease}
        .hsc-cat-pts{font-size:9px;font-weight:700;text-align:right}
        .hsc-deds{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:3px}
        .hsc-ded-row{display:flex;align-items:flex-start;gap:5px;font-size:10px}
        .hsc-ded-reason{color:var(--text-2)}
        .hsc-ded-detail{font-size:9px;color:var(--text-3);margin-top:1px}
        .hsc-ded-pts{font-weight:700;color:#ef4444;white-space:nowrap;margin-left:auto;padding-left:8px}
      `}</style>
    </div>
  );
}

function StatPill({ label, value, bad, warn }) {
  const color = bad ? (warn ? "#f59e0b" : "#ef4444") : "#22c55e";
  return (
    <div className="hsc-stat">
      <span className="hsc-stat-val" style={{ color }}>{value}</span>
      <span className="hsc-stat-lbl">{label}</span>
    </div>
  );
}
