/**
 * ExplanationToast — shows the AI explanation for the last applied action.
 *
 * Rendered inside the Dashboard after any cleaning action that returns
 * an `explanation` field. Auto-dismisses after 8 seconds.
 *
 * Props:
 *   explanation  {object}  — ExplainedAction.to_dict() from the backend
 *   onDismiss    {fn}
 */
import React, { useEffect } from "react";
import { X, Info, CheckCircle2, AlertTriangle } from "lucide-react";

const CONFIDENCE_COLOR = {
  high:   { text: "#22c55e", bg: "rgba(34,197,94,0.10)",   border: "rgba(34,197,94,0.2)" },
  medium: { text: "#f59e0b", bg: "rgba(245,158,11,0.10)",  border: "rgba(245,158,11,0.2)" },
  low:    { text: "#ef4444", bg: "rgba(239,68,68,0.10)",   border: "rgba(239,68,68,0.2)" },
};

export default function ExplanationToast({ explanation, onDismiss }) {
  useEffect(() => {
    if (!explanation) return;
    const t = setTimeout(onDismiss, 8000);
    return () => clearTimeout(t);
  }, [explanation, onDismiss]);

  if (!explanation) return null;

  const { what, why, confidence, confidence_label, rows_affected, action } = explanation;
  const conf  = CONFIDENCE_COLOR[confidence_label] ?? CONFIDENCE_COLOR.medium;
  const pct   = Math.round((confidence ?? 0) * 100);

  const css = `
    .et-wrap { position: fixed; bottom: 24px; left: 24px; z-index: 9998;
      width: 340px; background: var(--surface-2); border: 1px solid var(--border);
      border-radius: var(--radius-lg); padding: 14px 16px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.35);
      animation: et-in 0.25s cubic-bezier(0.16,1,0.3,1); }
    @keyframes et-in {
      from { opacity: 0; transform: translateY(12px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    .et-header { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 8px; }
    .et-title  { flex: 1; font-size: 12px; font-weight: 600; color: var(--text-0);
      line-height: 1.4; }
    .et-close  { border: none; background: none; color: var(--text-3);
      cursor: pointer; padding: 0; flex-shrink: 0; display: flex; }
    .et-close:hover { color: var(--text-1); }
    .et-what   { font-size: 12px; color: var(--text-1); margin-bottom: 6px; line-height: 1.5; }
    .et-why    { font-size: 11px; color: var(--text-2); line-height: 1.5;
      padding: 7px 10px; background: var(--surface-3); border-radius: var(--radius-sm);
      border-left: 2px solid var(--border-2); margin-bottom: 8px; }
    .et-footer { display: flex; align-items: center; gap: 8px; }
    .et-conf   { display: inline-flex; align-items: center; gap: 4px;
      font-size: 10px; font-weight: 700; padding: 2px 8px;
      border-radius: 99px; letter-spacing: .03em; }
    .et-rows   { font-size: 10px; color: var(--text-3); }
  `;

  return (
    <>
      <style>{css}</style>
      <div className="et-wrap">
        <div className="et-header">
          <CheckCircle2 size={14} color="#22c55e" style={{ marginTop: 1, flexShrink: 0 }} />
          <div className="et-title">
            {action?.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}
          </div>
          <button className="et-close" onClick={onDismiss}><X size={12} /></button>
        </div>

        <div className="et-what">{what}</div>

        <div className="et-why">
          <span style={{ color: "var(--text-3)", fontWeight: 600, fontSize: 10,
            textTransform: "uppercase", letterSpacing: ".06em" }}>Why</span>
          <br />
          {why}
        </div>

        <div className="et-footer">
          <span className="et-conf" style={{
            color: conf.text, background: conf.bg, border: `1px solid ${conf.border}`,
          }}>
            {confidence_label?.toUpperCase()} CONFIDENCE · {pct}%
          </span>
          {rows_affected > 0 && (
            <span className="et-rows">{rows_affected.toLocaleString()} rows affected</span>
          )}
        </div>
      </div>
    </>
  );
}
