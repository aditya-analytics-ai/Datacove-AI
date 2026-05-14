/**
 * SchemaApplyPanel — collapsible banner shown after upload.
 * Lets users pick which schema inference suggestions to apply before committing.
 */
import React, { useState, useMemo } from "react";
import { Wand2, ChevronDown, ChevronUp, CheckSquare, Square, X, Loader2, CheckCircle2, Info } from "lucide-react";

const DTYPE_META = {
  int:      { label: "Integer",  color: "#6366f1", bg: "#6366f115" },
  float:    { label: "Float",    color: "#0891b2", bg: "#0891b215" },
  bool:     { label: "Boolean",  color: "#059669", bg: "#05966915" },
  date:     { label: "Date",     color: "#d97706", bg: "#d9770615" },
  category: { label: "Category", color: "#7c3aed", bg: "#7c3aed15" },
};

function DtypeBadge({ dtype }) {
  const m = DTYPE_META[dtype] ?? { label: dtype, color: "#6b7280", bg: "#6b728015" };
  return (
    <span style={{ background: m.bg, color: m.color, border: `1px solid ${m.color}40`,
      borderRadius: 4, padding: "1px 6px", fontSize: 10, fontWeight: 700, whiteSpace: "nowrap" }}>
      {m.label}
    </span>
  );
}

function ConfBar({ value }) {
  const pct = Math.round(value * 100);
  const color = pct >= 95 ? "#22c55e" : pct >= 80 ? "#f59e0b" : "#ef4444";
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 4, minWidth: 60 }}>
      <span style={{ flex: 1, height: 4, background: "var(--surface-3,#2a2a3a)", borderRadius: 99, overflow: "hidden" }}>
        <span style={{ display: "block", height: "100%", width: `${pct}%`, background: color, borderRadius: 99, transition: "width .4s ease" }} />
      </span>
      <span style={{ fontSize: 9, color: "var(--text-3,#6b7280)", width: 24 }}>{pct}%</span>
    </span>
  );
}

export default function SchemaApplyPanel({ suggestions = [], onApply, onDismiss, loading = false }) {
  const [checked,  setChecked]  = useState(() => new Set(suggestions.map(s => s.column)));
  const [expanded, setExpanded] = useState(true);
  const [applied,  setApplied]  = useState(false);

  const allChecked = checked.size === suggestions.length;
  if (!suggestions.length || applied) return null;

  const toggle    = col => setChecked(p => { const n = new Set(p); n.has(col) ? n.delete(col) : n.add(col); return n; });
  const toggleAll = () => setChecked(allChecked ? new Set() : new Set(suggestions.map(s => s.column)));
  const handleApply = async () => {
    const accepted = suggestions.filter(s => checked.has(s.column));
    if (!accepted.length) return;
    await onApply(accepted);
    setApplied(true);
  };

  const highConf = suggestions.filter(s => s.confidence >= 0.9);

  return (
    <div style={{ background: "var(--surface-2,#1a1a2e)", border: "1px solid #6366f140",
      borderLeft: "3px solid #6366f1", borderRadius: 8, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", cursor: "pointer",
        borderBottom: expanded ? "1px solid var(--border,#2a2a3a)" : "none" }}
        onClick={() => setExpanded(e => !e)}>
        <Wand2 size={14} color="#6366f1" style={{ flexShrink: 0 }} />
        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text-1,#e2e8f0)", flex: 1 }}>Smart Schema Detected</span>
        <span style={{ background: "#6366f120", color: "#6366f1", borderRadius: 99, padding: "1px 7px", fontSize: 10, fontWeight: 700 }}>
          {suggestions.length} column{suggestions.length !== 1 ? "s" : ""}
        </span>
        {highConf.length > 0 && (
          <span style={{ background: "#22c55e15", color: "#22c55e", borderRadius: 99, padding: "1px 7px", fontSize: 10, fontWeight: 600 }}>
            {highConf.length} high-confidence
          </span>
        )}
        {expanded ? <ChevronUp size={13} color="var(--text-3,#6b7280)" /> : <ChevronDown size={13} color="var(--text-3,#6b7280)" />}
      </div>

      {expanded && (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 12px",
            background: "var(--surface-1,#12121e)", borderBottom: "1px solid var(--border,#2a2a3a)" }}>
            <Info size={11} color="#6b7280" />
            <span style={{ fontSize: 10, color: "var(--text-3,#6b7280)", flex: 1 }}>
              These columns look like typed data but were read as strings. Select casts to apply.
            </span>
            <button onClick={toggleAll} style={{ background: "none", border: "none", cursor: "pointer",
              color: "var(--text-2,#94a3b8)", fontSize: 10, display: "flex", alignItems: "center", gap: 3, padding: "2px 4px" }}>
              {allChecked ? <CheckSquare size={11} /> : <Square size={11} />}
              {allChecked ? "Deselect all" : "Select all"}
            </button>
          </div>

          <div style={{ maxHeight: 280, overflowY: "auto" }}>
            {suggestions.map(s => {
              const isC = checked.has(s.column);
              return (
                <div key={s.column} onClick={() => toggle(s.column)}
                  style={{ display: "grid", gridTemplateColumns: "20px 1fr auto auto", alignItems: "center",
                    gap: 10, padding: "6px 12px", cursor: "pointer",
                    background: isC ? "#6366f106" : "transparent",
                    borderBottom: "1px solid var(--border,#1e1e2e)", transition: "background .15s" }}>
                  <span style={{ color: isC ? "#6366f1" : "var(--text-3,#4b5563)" }}>
                    {isC ? <CheckSquare size={13} /> : <Square size={13} />}
                  </span>
                  <div>
                    <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-1,#e2e8f0)" }}>{s.column}</span>
                    <span style={{ fontSize: 9, color: "var(--text-3,#6b7280)", marginLeft: 6 }}>{s.reason}</span>
                    {s.sample_values?.length > 0 && (
                      <div style={{ fontSize: 9, color: "var(--text-3,#6b7280)", marginTop: 1 }}>
                        Sample: {s.sample_values.slice(0, 3).join(", ")}
                      </div>
                    )}
                  </div>
                  <DtypeBadge dtype={s.suggested_dtype} />
                  <ConfBar value={s.confidence} />
                </div>
              );
            })}
          </div>

          <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 8,
            padding: "8px 12px", borderTop: "1px solid var(--border,#2a2a3a)" }}>
            <span style={{ fontSize: 10, color: "var(--text-3,#6b7280)", flex: 1 }}>
              {checked.size} of {suggestions.length} selected
            </span>
            <button onClick={onDismiss} disabled={loading}
              style={{ background: "none", border: "1px solid var(--border,#2a2a3a)",
                color: "var(--text-3,#6b7280)", borderRadius: 5, padding: "4px 10px",
                fontSize: 11, cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
              <X size={11} /> Dismiss
            </button>
            <button onClick={handleApply} disabled={loading || checked.size === 0}
              style={{ background: checked.size === 0 ? "#6366f140" : "#6366f1", color: "#fff",
                border: "none", borderRadius: 5, padding: "4px 12px", fontSize: 11, fontWeight: 700,
                cursor: checked.size === 0 ? "not-allowed" : "pointer",
                display: "flex", alignItems: "center", gap: 5,
                opacity: checked.size === 0 ? 0.5 : 1, transition: "all .15s" }}>
              {loading
                ? <><Loader2 size={11} style={{ animation: "spin 1s linear infinite" }} /> Applying…</>
                : <><CheckCircle2 size={11} /> Apply {checked.size} cast{checked.size !== 1 ? "s" : ""}</>}
            </button>
          </div>
        </>
      )}
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}
