/**
 * DatasetSummary v5 — cleaner chips with icons, color-coded issues badge.
 */
import React from "react";
import { Rows3, Columns3, AlertTriangle, Clock, GitBranch } from "lucide-react";

function Chip({ icon: Icon, value, label, color }) {
  return (
    <div className="ds-chip">
      <Icon size={11} color={color ?? "var(--text-3)"} />
      <span className="ds-chip-val" style={color ? { color } : {}}>
        {value ?? "—"}
      </span>
      <span className="ds-chip-lbl">{label}</span>
    </div>
  );
}

export default function DatasetSummary({ summary, issuesCount }) {
  if (!summary) return null;
  const issues = issuesCount ?? (summary.top_issues?.length ?? 0);
  return (
    <div className="ds-wrap">
      <span className="ds-filename" title={summary.filename}>
        {summary.filename}
      </span>
      <div className="ds-chips">
        <Chip icon={Rows3}         value={summary.rows?.toLocaleString()} label="Rows" />
        <Chip icon={Columns3}      value={summary.columns}               label="Cols" />
        <Chip icon={AlertTriangle} value={issues} label="Issues"
          color={issues > 0 ? "var(--amber)" : "var(--green)"} />
        <Chip icon={Clock}         value={summary.history_len ?? 0}      label="Edits" />
        {(summary.versions ?? 0) > 0 && (
          <Chip icon={GitBranch} value={summary.versions} label="Versions"
            color="var(--accent-light)" />
        )}
      </div>
      <style>{`
        .ds-wrap   { display:flex; align-items:center; gap:8px; min-width:0; flex:1; overflow:hidden; }
        .ds-filename { font-size:12px; font-weight:600; color:var(--text-1);
                       white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
                       max-width:160px; flex-shrink:0; }
        .ds-chips  { display:flex; gap:3px; flex-wrap:wrap; }
        .ds-chip   { display:inline-flex; align-items:center; gap:3px; padding:3px 7px;
                     border-radius:5px; background:var(--surface-2); border:1px solid var(--border); }
        .ds-chip-val { font-size:11px; font-weight:700; color:var(--text-0); }
        .ds-chip-lbl { font-size:10px; color:var(--text-3); }
      `}</style>
    </div>
  );
}
