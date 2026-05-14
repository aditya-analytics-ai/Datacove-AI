/**
 * StreamProgressBar — floating progress overlay during streaming transforms.
 * Self-hides when progress is null.
 */
import React from "react";
import { X } from "lucide-react";

export default function StreamProgressBar({ progress, onAbort }) {
  if (!progress) return null;
  const { pct, rowsDone, totalRows, message } = progress;

  return (
    <div style={{
      position: "fixed", bottom: 24, left: "50%", transform: "translateX(-50%)",
      background: "var(--surface-1)", border: "1px solid var(--border)",
      borderRadius: 12, padding: "12px 16px", width: 360, zIndex: 9999,
      display: "flex", flexDirection: "column", gap: 8,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text-0)" }}>
          Processing large dataset
        </span>
        {onAbort && (
          <button onClick={onAbort} style={{
            background: "none", border: "none", cursor: "pointer",
            color: "var(--text-3)", padding: 2, borderRadius: 4,
          }}>
            <X size={13} />
          </button>
        )}
      </div>
      <div style={{ height: 6, background: "var(--surface-2)", borderRadius: 4, overflow: "hidden" }}>
        <div style={{
          height: "100%", borderRadius: 4, background: "var(--accent)",
          width: `${pct}%`, transition: "width 0.25s ease",
        }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-2)" }}>
        <span>{message ?? "Processing…"}</span>
        <span style={{ fontVariantNumeric: "tabular-nums" }}>
          {rowsDone?.toLocaleString()} / {totalRows?.toLocaleString()} · {pct}%
        </span>
      </div>
    </div>
  );
}
