/**
 * HistoryPanel.jsx — Full transformation history with diff view & rollback.
 *
 * Props:
 *   sessionId  {string}
 *   history    {Array}  — history_as_list() from backend:
 *                         [{action, params, rows_before, rows_after,
 *                           cols_before, cols_after, ts}]
 *   onRollback {fn}     — called with the API result after a rollback
 *   onUndo     {fn}     — trigger single-step undo (existing Ctrl+Z path)
 */
import React, { useState, useCallback } from "react";
import {
  RotateCcw, ChevronDown, ChevronRight, Clock, Rows,
  Columns, ArrowDownUp, Undo2, AlertTriangle, CheckCircle2,
  GitBranch, Loader2,
} from "lucide-react";
import { rollbackToVersion } from "../services/api";

// ── helpers ──────────────────────────────────────────────────────────────────

function fmt(n) {
  if (n == null) return "—";
  return Number(n).toLocaleString();
}

function delta(before, after, unit = "") {
  if (before == null || after == null) return null;
  const d = after - before;
  if (d === 0) return null;
  const sign = d > 0 ? "+" : "";
  return `${sign}${fmt(d)}${unit}`;
}

function actionLabel(action = "") {
  return action
    .replace(/_/g, " ")
    .replace(/\b\w/g, c => c.toUpperCase());
}

function paramSummary(params = {}) {
  const entries = Object.entries(params).filter(([k]) => k !== "summary");
  if (!entries.length) return null;
  return entries
    .slice(0, 3)
    .map(([k, v]) => {
      const val = typeof v === "object" ? JSON.stringify(v) : String(v);
      return `${k}: ${val.length > 40 ? val.slice(0, 37) + "…" : val}`;
    })
    .join(" · ");
}

function timeAgo(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  if (isNaN(d)) return "";
  const s = Math.floor((Date.now() - d) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// Action category → colour token
const ACTION_COLOR = {
  remove: "var(--red)",
  drop:   "var(--red)",
  fill:   "var(--amber)",
  coerce: "var(--amber)",
  cast:   "var(--amber)",
  trim:   "var(--blue)",
  strip:  "var(--blue)",
  standardise: "var(--blue)",
  normalise:   "var(--blue)",
  normalize:   "var(--blue)",
  map:    "var(--purple, #8b5cf6)",
  merge:  "var(--purple, #8b5cf6)",
  split:  "var(--purple, #8b5cf6)",
  extract:"var(--purple, #8b5cf6)",
  flag:   "var(--amber)",
  auto:   "var(--green)",
  edit:   "var(--blue)",
  sql:    "var(--blue)",
  bin:    "var(--blue)",
  clip:   "var(--blue)",
  round:  "var(--blue)",
  scale:  "var(--blue)",
  rename: "var(--blue)",
  reorder:"var(--blue)",
  find:   "var(--blue)",
  conditional: "var(--purple, #8b5cf6)",
};

function actionColor(action = "") {
  const first = action.split("_")[0].toLowerCase();
  return ACTION_COLOR[first] || "var(--text-3)";
}

// ── sub-components ───────────────────────────────────────────────────────────

function DeltaPill({ label, before, after, color }) {
  const d = delta(before, after);
  if (!d) return null;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 3,
      fontSize: 10, fontWeight: 600,
      padding: "1px 6px", borderRadius: 10,
      background: color + "22",
      color,
    }}>
      {label} {d}
    </span>
  );
}

function ParamChip({ k, v }) {
  const val = typeof v === "object" ? JSON.stringify(v) : String(v);
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      fontSize: 10, padding: "1px 6px", borderRadius: 8,
      background: "var(--surface-3)", color: "var(--text-2)",
      fontFamily: "monospace", maxWidth: 200,
      overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
    }}>
      <span style={{ color: "var(--text-3)" }}>{k}</span>
      <span style={{ color: "var(--text-1)" }}>
        {val.length > 30 ? val.slice(0, 27) + "…" : val}
      </span>
    </span>
  );
}

function HistoryItem({
  entry, index, total, isCurrent, isRollingBack, onRollback
}) {
  const [expanded, setExpanded] = useState(false);
  const stepNum   = index + 1;
  const color     = actionColor(entry.action);
  const rowDelta  = delta(entry.rows_before, entry.rows_after);
  const colDelta  = delta(entry.cols_before, entry.cols_after);
  const hasParams = entry.params && Object.keys(entry.params).filter(k => k !== "summary").length > 0;

  return (
    <li style={{
      display: "flex", gap: 10, padding: "6px 8px 6px 4px",
      borderRadius: 6, cursor: "default",
      background: isCurrent ? "var(--surface-3)" : "transparent",
      transition: "background .12s",
      position: "relative",
      opacity: isCurrent ? 1 : 0.72,
    }}
      onMouseEnter={e => e.currentTarget.style.opacity = "1"}
      onMouseLeave={e => e.currentTarget.style.opacity = isCurrent ? "1" : "0.72"}
    >
      {/* Timeline spine */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 24, flexShrink: 0 }}>
        <div style={{
          width: 20, height: 20, borderRadius: "50%",
          background: isCurrent ? color : "var(--surface-3)",
          border: `2px solid ${color}`,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 9, fontWeight: 700, color: isCurrent ? "#fff" : color,
          flexShrink: 0,
        }}>
          {stepNum}
        </div>
        {index < total - 1 && (
          <div style={{ width: 2, flex: 1, minHeight: 8, background: "var(--border)", marginTop: 3 }} />
        )}
      </div>

      {/* Main content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Header row */}
        <div style={{ display: "flex", alignItems: "flex-start", gap: 6, justifyContent: "space-between" }}>
          <div style={{ minWidth: 0 }}>
            <span style={{
              fontSize: 12, fontWeight: 600, color: "var(--text-0)",
              display: "block", textTransform: "capitalize",
            }}>
              {actionLabel(entry.action)}
            </span>

            {/* Deltas */}
            <div style={{ display: "flex", gap: 4, marginTop: 3, flexWrap: "wrap" }}>
              {rowDelta && (
                <DeltaPill
                  label="rows"
                  before={entry.rows_before} after={entry.rows_after}
                  color={entry.rows_after < entry.rows_before ? "var(--red)" : "var(--green)"}
                />
              )}
              {colDelta && (
                <DeltaPill
                  label="cols"
                  before={entry.cols_before} after={entry.cols_after}
                  color={entry.cols_after < entry.cols_before ? "var(--red)" : "var(--green)"}
                />
              )}
              {entry.ts && (
                <span style={{ fontSize: 10, color: "var(--text-3)", marginTop: 1 }}>
                  <Clock size={9} style={{ marginRight: 2, verticalAlign: "middle" }} />
                  {timeAgo(entry.ts)}
                </span>
              )}
            </div>
          </div>

          {/* Actions */}
          <div style={{ display: "flex", gap: 4, alignItems: "center", flexShrink: 0 }}>
            {hasParams && (
              <button
                onClick={() => setExpanded(x => !x)}
                title="Show params"
                style={{
                  background: "none", border: "none", cursor: "pointer",
                  color: "var(--text-3)", padding: 2, display: "flex",
                }}
              >
                {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              </button>
            )}
            {!isCurrent && (
              <button
                onClick={() => onRollback(index)}
                disabled={isRollingBack}
                title={`Rollback to after step ${stepNum}`}
                style={{
                  display: "flex", alignItems: "center", gap: 4,
                  fontSize: 10, fontWeight: 500,
                  padding: "3px 7px", borderRadius: 5,
                  background: "var(--surface-1)",
                  border: "1px solid var(--border)",
                  color: "var(--text-2)", cursor: "pointer",
                }}
              >
                {isRollingBack
                  ? <Loader2 size={10} style={{ animation: "spin .7s linear infinite" }} />
                  : <RotateCcw size={10} />}
                Restore
              </button>
            )}
            {isCurrent && (
              <span style={{
                fontSize: 10, color: "var(--green)", fontWeight: 600,
                display: "flex", alignItems: "center", gap: 3,
              }}>
                <CheckCircle2 size={10} /> current
              </span>
            )}
          </div>
        </div>

        {/* Expanded params */}
        {expanded && hasParams && (
          <div style={{
            marginTop: 6, display: "flex", flexWrap: "wrap", gap: 4,
          }}>
            {Object.entries(entry.params)
              .filter(([k]) => k !== "summary")
              .map(([k, v]) => <ParamChip key={k} k={k} v={v} />)
            }
          </div>
        )}

        {/* Auto-clean summary if present */}
        {entry.params?.summary && (
          <div style={{
            marginTop: 4, fontSize: 10, color: "var(--text-2)",
            lineHeight: 1.4,
          }}>
            {entry.params.summary}
          </div>
        )}
      </div>
    </li>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function HistoryPanel({ sessionId, history = [], onRollback, onUndo }) {
  const [rollingBackIdx, setRollingBackIdx] = useState(null);
  const [error, setError] = useState("");

  const handleRollback = useCallback(async (versionIndex) => {
    setError("");
    setRollingBackIdx(versionIndex);
    try {
      const result = await rollbackToVersion(sessionId, versionIndex);
      if (onRollback) onRollback(result);
    } catch (e) {
      setError(e?.response?.data?.detail || "Rollback failed.");
    } finally {
      setRollingBackIdx(null);
    }
  }, [sessionId, onRollback]);

  const currentIdx = history.length - 1;

  return (
    <div style={{
      background: "var(--surface-2)", borderRadius: "var(--radius-md)",
      border: "1px solid var(--border)", overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "9px 12px", borderBottom: "1px solid var(--border)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <GitBranch size={13} style={{ color: "var(--text-2)" }} />
          <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text-1)" }}>
            Version History
          </span>
          {history.length > 0 && (
            <span style={{
              fontSize: 10, padding: "1px 7px", borderRadius: 10,
              background: "var(--surface-3)", color: "var(--text-2)", fontWeight: 600,
            }}>
              {history.length} step{history.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {history.length > 0 && onUndo && (
            <button
              onClick={onUndo}
              title="Undo last step (Ctrl+Z)"
              style={{
                display: "flex", alignItems: "center", gap: 5,
                fontSize: 10, fontWeight: 500,
                padding: "3px 8px", borderRadius: 5,
                background: "var(--surface-1)",
                border: "1px solid var(--border)",
                color: "var(--text-2)", cursor: "pointer",
              }}
            >
              <Undo2 size={10} /> Undo last
            </button>
          )}
          <kbd style={{
            fontSize: 9, background: "var(--surface-1)",
            border: "1px solid var(--border)",
            padding: "2px 6px", borderRadius: 4,
            color: "var(--text-3)", fontFamily: "monospace",
          }}>
            Ctrl+Z
          </kbd>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div style={{
          display: "flex", gap: 7, alignItems: "center",
          padding: "7px 12px", background: "var(--red)18",
          borderBottom: "1px solid var(--border)",
          fontSize: 11, color: "var(--red)",
        }}>
          <AlertTriangle size={12} /> {error}
        </div>
      )}

      {/* Empty state */}
      {history.length === 0 ? (
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          gap: 8, padding: "32px 16px", color: "var(--text-3)",
        }}>
          <ArrowDownUp size={28} strokeWidth={1.5} />
          <span style={{ fontSize: 12 }}>No transformations yet.</span>
          <span style={{ fontSize: 11 }}>
            Apply cleaning operations to build a version history.
          </span>
        </div>
      ) : (
        <ol style={{
          listStyle: "none", margin: 0, padding: "8px 8px 8px 6px",
          display: "flex", flexDirection: "column", gap: 0,
          maxHeight: 520, overflowY: "auto",
        }}>
          {history.map((entry, i) => (
            <HistoryItem
              key={i}
              entry={entry}
              index={i}
              total={history.length}
              isCurrent={i === currentIdx}
              isRollingBack={rollingBackIdx === i}
              onRollback={handleRollback}
            />
          ))}
        </ol>
      )}

      {/* Stats footer */}
      {history.length > 0 && (
        <div style={{
          display: "flex", gap: 12, padding: "7px 12px",
          borderTop: "1px solid var(--border)",
          fontSize: 10, color: "var(--text-3)",
        }}>
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <Rows size={10} />
            {fmt(history[history.length - 1]?.rows_after)} rows now
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <Columns size={10} />
            {fmt(history[history.length - 1]?.cols_after)} cols now
          </span>
          <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 4 }}>
            <RotateCcw size={10} /> Click <strong>Restore</strong> on any step to roll back
          </span>
        </div>
      )}

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
