/**
 * LineagePanel — column-level data lineage DAG visualiser.
 *
 * Calls GET /api/lineage?session_id=... and renders the transform
 * history per column as a vertical timeline DAG.
 *
 * Each column is a node. Each transform that touches it is a step
 * in a downward chain. No heavy graph library needed — pure SVG + CSS.
 */
import React, { useState, useCallback, useEffect } from "react";
import { GitBranch, Loader2, RefreshCw, AlertCircle, ChevronDown, ChevronRight } from "lucide-react";
import { getLineage } from "../services/api";

const ACTION_COLORS = {
  drop_nulls:             "#6366f1",
  fill_nulls:             "#8b5cf6",
  remove_duplicates:      "#ef4444",
  trim_whitespace:        "#3b82f6",
  standardise_capitalisation: "#10b981",
  rename_column:          "#f59e0b",
  cast_type:              "#f97316",
  auto_clean:             "#22c55e",
  edit_cell:              "#a78bfa",
  map_to_standard:        "#06b6d4",
};

function StepNode({ step, index }) {
  const color = ACTION_COLORS[step.action] ?? "#6b7280";
  const ts = step.ts ? new Date(step.ts * 1000).toLocaleTimeString() : "";

  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 6 }}>
      {/* Connector line + dot */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0, width: 16 }}>
        {index > 0 && <div style={{ width: 1, height: 8, background: "var(--border-2)" }} />}
        <div style={{ width: 8, height: 8, borderRadius: "50%", background: color, border: `2px solid ${color}40`, flexShrink: 0 }} />
      </div>

      {/* Step detail */}
      <div style={{ flex: 1, paddingBottom: 2 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{
            display: "inline-block", padding: "1px 6px", borderRadius: 4,
            background: `${color}18`, border: `1px solid ${color}30`,
            fontSize: 10, fontWeight: 600, color, fontFamily: "monospace",
          }}>
            {step.action}
          </span>
          {ts && <span style={{ fontSize: 9, color: "var(--text-3)" }}>{ts}</span>}
        </div>
        {step.params && Object.keys(step.params).length > 0 && (
          <div style={{ fontSize: 9, color: "var(--text-3)", marginTop: 2, fontFamily: "monospace" }}>
            {JSON.stringify(step.params)}
          </div>
        )}
      </div>
    </div>
  );
}

function ColumnLineage({ column, steps }) {
  const [expanded, setExpanded] = useState(false);
  const shownSteps = expanded ? steps : steps.slice(0, 3);

  return (
    <div style={{
      background: "var(--surface-1)", border: "1px solid var(--border)",
      borderRadius: "var(--radius-sm)", marginBottom: 8, overflow: "hidden",
    }}>
      <div
        style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", cursor: "pointer" }}
        onClick={() => setExpanded(e => !e)}
      >
        <GitBranch size={11} color="var(--accent)" />
        <span style={{ flex: 1, fontWeight: 600, fontSize: 12, color: "var(--text-0)", fontFamily: "monospace" }}>
          {column}
        </span>
        <span style={{ fontSize: 10, color: "var(--text-3)", marginRight: 4 }}>
          {steps.length} step{steps.length !== 1 ? "s" : ""}
        </span>
        {expanded ? <ChevronDown size={12} color="var(--text-3)" /> : <ChevronRight size={12} color="var(--text-3)" />}
      </div>

      {expanded && (
        <div style={{ padding: "0 12px 10px 12px", borderTop: "1px solid var(--border)" }}>
          {shownSteps.map((s, i) => (
            <StepNode key={i} step={s} index={i} />
          ))}
          {steps.length > 3 && !expanded && (
            <button
              onClick={() => setExpanded(true)}
              style={{ background: "none", border: "none", color: "var(--accent)", fontSize: 11, cursor: "pointer", padding: 0 }}
            >
              +{steps.length - 3} more…
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default function LineagePanel({ sessionId }) {
  const [lineage,  setLineage]  = useState(null);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await getLineage(sessionId);
      setLineage(res.lineage ?? {});
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Lineage fetch failed.");
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  // Auto-load on mount
  useEffect(() => { load(); }, [load]);

  const css = `
    .lin-wrap { font-size: 12px; }
    .lin-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
    .lin-title { font-size: 11px; font-weight: 700; color: var(--text-2);
                 text-transform: uppercase; letter-spacing: .07em; }
    .lin-refresh { display: inline-flex; align-items: center; gap: 5px;
                   padding: 4px 10px; background: var(--surface-2); color: var(--text-1);
                   border: 1px solid var(--border); border-radius: var(--radius-sm);
                   font-size: 10px; cursor: pointer; }
    .lin-empty { text-align: center; padding: 24px 0; color: var(--text-3);
                 font-size: 12px; }
    .lin-err { color: var(--red); display: flex; align-items: center; gap: 5px;
               padding: 6px 10px; font-size: 11px; }
    .lin-cols-count { font-size: 10px; color: var(--text-3); margin-bottom: 8px; }
  `;

  const columns = lineage ? Object.keys(lineage) : [];
  const activeColumns = columns.filter(c => (lineage[c]?.length ?? 0) > 0);

  return (
    <>
      <style>{css}</style>
      <div className="lin-wrap">
        <div className="lin-header">
          <span className="lin-title">
            <GitBranch size={11} style={{ marginRight: 4, verticalAlign: "middle" }} />
            Column Lineage
          </span>
          <button className="lin-refresh" onClick={load} disabled={loading}>
            <RefreshCw size={10} style={{ animation: loading ? "spin .7s linear infinite" : "none" }} />
            Refresh
          </button>
        </div>

        {error && <div className="lin-err"><AlertCircle size={11} />{error}</div>}

        {loading && !lineage && (
          <div className="lin-empty">
            <Loader2 size={20} style={{ animation: "spin .7s linear infinite", marginBottom: 8 }} />
            <br />Loading lineage…
          </div>
        )}

        {lineage !== null && activeColumns.length === 0 && !loading && (
          <div className="lin-empty">
            <GitBranch size={20} style={{ marginBottom: 8, opacity: .3 }} />
            <br />No transform history yet. Apply some cleaning steps to see column lineage.
          </div>
        )}

        {activeColumns.length > 0 && (
          <>
            <div className="lin-cols-count">
              {activeColumns.length} column{activeColumns.length !== 1 ? "s" : ""} with recorded transforms
            </div>
            {activeColumns.map(col => (
              <ColumnLineage key={col} column={col} steps={lineage[col]} />
            ))}
          </>
        )}
      </div>
    </>
  );
}
