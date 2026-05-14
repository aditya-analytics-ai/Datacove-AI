/**
 * AutoCleanReport — plain-English step-by-step report from auto_clean_explained().
 */
import React, { useState } from "react";
import { CheckCircle2, ChevronDown, ChevronRight, X, Trash2, AlignLeft, Type, Tag, ArrowRight } from "lucide-react";

const ACTION_META = {
  remove_duplicates:          { icon: Trash2,    color: "#ef4444" },
  trim_whitespace:            { icon: AlignLeft, color: "#0891b2" },
  standardise_capitalisation: { icon: Type,      color: "#f59e0b" },
  normalise_categories:       { icon: Tag,       color: "#7c3aed" },
};

function SampleDiff({ changes }) {
  if (!changes?.length) return null;
  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-3,#6b7280)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 4 }}>Sample changes</div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border,#2a2a3a)" }}>
            {["Column", "Before", "", "After"].map((h, i) => (
              <th key={i} style={{ padding: "2px 6px", textAlign: "left", color: "var(--text-3,#6b7280)", fontWeight: 600, width: i === 2 ? 20 : "auto" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {changes.map((c, i) => (
            <tr key={i} style={{ borderBottom: "1px solid var(--border,#1e1e2e)" }}>
              <td style={{ padding: "3px 6px", color: "var(--text-3,#6b7280)", fontStyle: "italic", maxWidth: 100, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.column}</td>
              <td style={{ padding: "3px 6px", fontFamily: "monospace", background: "#ef444415", color: "#fca5a5", borderRadius: 3, maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.before}</td>
              <td style={{ padding: "3px 4px", color: "var(--text-3,#6b7280)" }}><ArrowRight size={10} /></td>
              <td style={{ padding: "3px 6px", fontFamily: "monospace", background: "#22c55e15", color: "#86efac", borderRadius: 3, maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.after}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StepCard({ step, index }) {
  const [open, setOpen] = useState(index === 0);
  const meta = ACTION_META[step.action] ?? { icon: CheckCircle2, color: "#6b7280" };
  const Icon = meta.icon;

  return (
    <div style={{ border: "1px solid var(--border,#2a2a3a)", borderLeft: `3px solid ${meta.color}`, borderRadius: 6, overflow: "hidden", background: "var(--surface-2,#1a1a2e)" }}>
      <div onClick={() => setOpen(o => !o)} style={{ display: "flex", alignItems: "center", gap: 9, padding: "8px 12px", cursor: "pointer" }}>
        <span style={{ display: "flex", alignItems: "center", justifyContent: "center", width: 22, height: 22, borderRadius: 5, background: `${meta.color}20`, flexShrink: 0 }}>
          <Icon size={12} color={meta.color} />
        </span>
        <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-1,#e2e8f0)", flex: 1 }}>{step.label}</span>
        <span style={{ fontSize: 9, fontWeight: 700, padding: "1px 7px", borderRadius: 99,
          background: step.delta !== 0 ? "#ef444415" : (step.sample_changes?.length ? "#f59e0b15" : "#22c55e15"),
          color: step.delta !== 0 ? "#ef4444" : (step.sample_changes?.length ? "#f59e0b" : "#22c55e"),
          border: "1px solid currentColor" }}>
          {step.delta !== 0 ? `${step.before_count}→${step.after_count} rows` : step.sample_changes?.length ? `${step.sample_changes.length} changes` : "no change"}
        </span>
        {open ? <ChevronDown size={12} color="var(--text-3,#6b7280)" /> : <ChevronRight size={12} color="var(--text-3,#6b7280)" />}
      </div>
      {open && (
        <div style={{ padding: "8px 12px 10px", borderTop: "1px solid var(--border,#2a2a3a)" }}>
          <p style={{ fontSize: 11, color: "var(--text-2,#94a3b8)", margin: "0 0 6px" }}>{step.description}</p>
          {step.affected_cols?.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 4 }}>
              {step.affected_cols.slice(0, 8).map(col => (
                <span key={col} style={{ fontSize: 9, padding: "1px 6px", borderRadius: 4,
                  background: `${meta.color}15`, color: meta.color, border: `1px solid ${meta.color}30`, fontWeight: 600 }}>{col}</span>
              ))}
              {step.affected_cols.length > 8 && <span style={{ fontSize: 9, color: "var(--text-3,#6b7280)" }}>+{step.affected_cols.length - 8} more</span>}
            </div>
          )}
          <SampleDiff changes={step.sample_changes} />
        </div>
      )}
    </div>
  );
}

export default function AutoCleanReport({ summary, steps = [], onDismiss }) {
  const [collapsed, setCollapsed] = useState(false);
  if (!summary && !steps.length) return null;

  const hasChanges  = steps.some(s => s.delta !== 0 || s.sample_changes?.length > 0);
  const accentColor = hasChanges ? "#22c55e" : "#6366f1";

  return (
    <div style={{ background: "var(--surface-2,#1a1a2e)", border: `1px solid ${accentColor}40`,
      borderLeft: `3px solid ${accentColor}`, borderRadius: 8, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 12px",
        background: `${accentColor}10`, borderBottom: collapsed ? "none" : `1px solid ${accentColor}25` }}>
        <CheckCircle2 size={15} color={accentColor} style={{ flexShrink: 0 }} />
        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text-1,#e2e8f0)", flex: 1 }}>{summary}</span>
        <button onClick={() => setCollapsed(c => !c)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-3,#6b7280)", padding: 3 }}>
          {collapsed ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
        </button>
        {onDismiss && (
          <button onClick={onDismiss} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-3,#6b7280)", padding: 3 }}>
            <X size={13} />
          </button>
        )}
      </div>
      {!collapsed && steps.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6, padding: "10px 12px" }}>
          {steps.map((step, i) => <StepCard key={step.action} step={step} index={i} />)}
        </div>
      )}
    </div>
  );
}
