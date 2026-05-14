/**
 * AIAgentPanel — runs the full AI cleaning agent and displays the report.
 * Shows score before/after, actions applied, and agent suggestions.
 */
import React, { useState } from "react";
import { Bot, Loader2, ChevronDown, ChevronRight, CheckCircle2, XCircle, Zap } from "lucide-react";
import { runAIAgent } from "../services/api";

export default function AIAgentPanel({ sessionId, onComplete }) {
  const [running, setRunning]   = useState(false);
  const [report,  setReport]    = useState(null);
  const [error,   setError]     = useState("");
  const [open,    setOpen]      = useState(true);

  async function handleRun() {
    setRunning(true);
    setError("");
    setReport(null);
    try {
      const result = await runAIAgent(sessionId);
      setReport(result.report);
      onComplete?.(result);
    } catch (err) {
      setError(err?.response?.data?.detail ?? "Agent run failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="agent-wrap">
      <div className="agent-header">
        <Bot size={15} color="var(--accent)" />
        <span className="agent-title">AI Cleaning Agent</span>
        <button className="agent-expand" onClick={() => setOpen(o => !o)}>
          {open ? <ChevronDown size={14}/> : <ChevronRight size={14}/>}
        </button>
      </div>

      {open && (
        <div className="agent-body">
          <p className="agent-desc">
            Automatically profiles, detects issues, applies fixes, and scores your dataset end-to-end.
          </p>

          <button className="agent-run-btn" onClick={handleRun} disabled={running || !sessionId}>
            {running
              ? <><Loader2 size={14} className="spin" /> Running Agent…</>
              : <><Zap size={14} /> Run AI Agent</>}
          </button>

          {error && <p className="agent-error">{error}</p>}

          {report && (
            <div className="agent-report">
              {/* Score improvement */}
              <div className="score-delta">
                <div className="score-box">
                  <span className="score-num" style={{ color: "#ef4444" }}>{report.score_before}</span>
                  <span className="score-lbl">Before</span>
                </div>
                <span className="score-arrow">→</span>
                <div className="score-box">
                  <span className="score-num" style={{ color: "#22c55e" }}>{report.score_after}</span>
                  <span className="score-lbl">After</span>
                </div>
                <div className="score-box">
                  <span className="score-num" style={{ color: "var(--accent)" }}>{report.grade_after}</span>
                  <span className="score-lbl">Grade</span>
                </div>
              </div>

              {/* Stats row */}
              <div className="agent-stats">
                <Kv label="Rows before" value={report.rows_before} />
                <Kv label="Rows after"  value={report.rows_after} />
                <Kv label="Issues fixed" value={report.issues_before - report.issues_after} color="#22c55e" />
                <Kv label="Issues left" value={report.issues_after} color={report.issues_after > 0 ? "#f59e0b" : "#22c55e"} />
              </div>

              {/* Actions applied */}
              <div className="agent-actions">
                <p className="agent-section-title">Actions Applied ({report.actions_applied?.length ?? 0})</p>
                {report.actions_applied?.map((a, i) => (
                  <div key={i} className="action-row">
                    {a.status === "applied"
                      ? <CheckCircle2 size={12} color="#22c55e" />
                      : <XCircle size={12} color="#ef4444" />}
                    <span className="action-name">{a.action?.replace(/_/g, " ")}</span>
                    {a.column && <span className="col-chip">{a.column}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <style>{`
        .agent-wrap   { background:var(--surface-1); border-radius:12px; overflow:hidden; }
        .agent-header { display:flex; align-items:center; gap:8px; padding:12px 14px;
                        border-bottom:1px solid var(--border); }
        .agent-title  { flex:1; font-size:13px; font-weight:700; color:var(--text-0); }
        .agent-expand { background:none; border:none; cursor:pointer; color:var(--text-2); padding:0; }
        .agent-body   { padding:14px; display:flex; flex-direction:column; gap:10px; }
        .agent-desc   { font-size:12px; color:var(--text-2); margin:0; }
        .agent-run-btn { display:inline-flex; align-items:center; gap:6px;
                         padding:8px 16px; border-radius:8px; border:none; cursor:pointer;
                         background:var(--accent); color:#fff; font-size:13px; font-weight:600; }
        .agent-run-btn:disabled { opacity:.5; cursor:not-allowed; }
        .agent-error  { font-size:12px; color:#ef4444; margin:0; }
        .agent-report { display:flex; flex-direction:column; gap:10px; }
        .score-delta  { display:flex; align-items:center; justify-content:center; gap:12px;
                        padding:12px; background:var(--surface-2); border-radius:10px; }
        .score-box    { display:flex; flex-direction:column; align-items:center; gap:2px; }
        .score-num    { font-size:22px; font-weight:800; }
        .score-lbl    { font-size:10px; color:var(--text-2); text-transform:uppercase; letter-spacing:.05em; }
        .score-arrow  { font-size:20px; color:var(--text-3); }
        .agent-stats  { display:grid; grid-template-columns:1fr 1fr; gap:6px; }
        .kv           { display:flex; flex-direction:column; gap:2px; background:var(--surface-2);
                        border-radius:8px; padding:8px 10px; }
        .kv-label     { font-size:10px; color:var(--text-2); text-transform:uppercase; letter-spacing:.05em; }
        .kv-value     { font-size:16px; font-weight:700; }
        .agent-actions { display:flex; flex-direction:column; gap:4px; }
        .agent-section-title { font-size:11px; font-weight:700; color:var(--text-2);
                               text-transform:uppercase; letter-spacing:.05em; margin:0 0 4px; }
        .action-row   { display:flex; align-items:center; gap:6px; font-size:12px; color:var(--text-1); }
        .action-name  { text-transform:capitalize; }
        .col-chip     { font-size:10px; background:var(--surface-3); color:var(--text-2);
                        padding:1px 6px; border-radius:4px; font-family:monospace; }
        @keyframes spin { to { transform:rotate(360deg); } }
        .spin { animation:spin .7s linear infinite; }
      `}</style>
    </div>
  );
}

function Kv({ label, value, color }) {
  return (
    <div className="kv">
      <span className="kv-label">{label}</span>
      <span className="kv-value" style={{ color: color ?? "var(--text-0)" }}>{value ?? 0}</span>
    </div>
  );
}
