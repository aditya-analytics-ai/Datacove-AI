/**
 * PipelineManager — list saved pipelines, create new ones, and run them.
 * Supports building a pipeline from the current transformation history.
 */
import React, { useState, useEffect } from "react";
import { Play, Plus, Loader2, GitBranch, ChevronDown, ChevronRight, Trash2 } from "lucide-react";
import { listPipelines, createPipeline, runPipeline } from "../services/api";

const ACTION_LABELS = {
  remove_duplicates:          "Remove Duplicates",
  trim_whitespace:            "Trim Whitespace",
  standardise_capitalisation: "Standardise Capitalisation",
  normalise_categories:       "Normalise Categories",
  fill_missing:               "Fill Missing Values",
  coerce_numeric:             "Coerce to Numeric",
  standardise_dates:          "Standardise Dates",
  flag_invalid_emails:        "Flag Invalid Emails",
  drop_column:                "Drop Column",
  auto_clean:                 "Auto-Clean Suite",
};

function PipelineRow({ pipeline, sessionId, onRan }) {
  const [open, setOpen]       = useState(false);
  const [running, setRunning] = useState(false);
  const [msg, setMsg]         = useState("");

  async function handleRun() {
    setRunning(true);
    setMsg("");
    try {
      const result = await runPipeline(sessionId, pipeline.pipeline_id);
      setMsg(`✓ Applied — ${result.rows} rows`);
      onRan?.(result);
    } catch (err) {
      setMsg("✗ " + (err?.response?.data?.detail ?? "Run failed."));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="pl-row">
      <div className="pl-row-header">
        <button className="pl-expand" onClick={() => setOpen((o) => !o)}>
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <GitBranch size={14} color="var(--accent)" />
        <span className="pl-name">{pipeline.name}</span>
        <span className="pl-step-count">{pipeline.steps.length} steps</span>
        <button className="pl-run-btn" onClick={handleRun} disabled={running || !sessionId}>
          {running ? <Loader2 size={12} className="spin" /> : <Play size={12} />}
          Run
        </button>
      </div>
      {msg && <p className="pl-msg" style={{ color: msg.startsWith("✓") ? "#22c55e" : "#ef4444" }}>{msg}</p>}
      {open && (
        <ol className="pl-steps">
          {pipeline.steps.map((s, i) => (
            <li key={i} className="pl-step">
              <span className="pl-step-num">{i + 1}</span>
              <span className="pl-step-label">{ACTION_LABELS[s.action] ?? s.action}</span>
              {Object.keys(s.params ?? {}).length > 0 && (
                <code className="pl-step-params">{JSON.stringify(s.params)}</code>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export default function PipelineManager({ sessionId, history = [], onRan }) {
  const [pipelines, setPipelines] = useState([]);
  const [loading, setLoading]     = useState(false);
  const [creating, setCreating]   = useState(false);
  const [newName, setNewName]     = useState("");
  const [saveMsg, setSaveMsg]     = useState("");

  useEffect(() => {
    listPipelines().then(setPipelines).catch(() => {});
  }, []);

  async function handleCreate() {
    if (!newName.trim()) return;
    // Build steps from history (history entries carry {action, params})
    const steps = history.map((h) => ({ action: h.action, params: h.params ?? {} }));
    if (steps.length === 0) {
      setSaveMsg("No transformation history to save as pipeline.");
      return;
    }
    setCreating(true);
    setSaveMsg("");
    try {
      const p = await createPipeline(newName.trim(), steps);
      setPipelines((prev) => [...prev, p]);
      setNewName("");
      setSaveMsg(`✓ Pipeline "${p.name}" saved.`);
    } catch (err) {
      setSaveMsg("✗ " + (err?.response?.data?.detail ?? "Save failed."));
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="pm-wrap">
      <h3 className="pm-title">Pipelines</h3>

      {/* Saved pipelines */}
      {loading && <p className="pm-empty">Loading…</p>}
      {!loading && pipelines.length === 0 && (
        <p className="pm-empty">No pipelines yet. Save your current history as a pipeline below.</p>
      )}
      <div className="pm-list">
        {pipelines.map((p) => (
          <PipelineRow
            key={p.pipeline_id}
            pipeline={p}
            sessionId={sessionId}
            onRan={onRan}
          />
        ))}
      </div>

      {/* Create from history */}
      <div className="pm-create">
        <p className="pm-create-label">
          Save current history as pipeline
          {history.length > 0 && ` (${history.length} steps)`}
        </p>
        <div className="pm-create-row">
          <input
            className="pm-input"
            placeholder="Pipeline name…"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
          />
          <button className="pm-save-btn" onClick={handleCreate} disabled={creating || !newName.trim()}>
            {creating ? <Loader2 size={13} className="spin" /> : <Plus size={13} />}
            Save
          </button>
        </div>
        {saveMsg && (
          <p className="pm-save-msg" style={{ color: saveMsg.startsWith("✓") ? "#22c55e" : "#ef4444" }}>
            {saveMsg}
          </p>
        )}
      </div>

      <style>{`
        .pm-wrap      { display:flex; flex-direction:column; gap:12px;
                        background:var(--surface-1); border-radius:12px; padding:16px; }
        .pm-title     { font-size:13px; font-weight:700; color:var(--text-2);
                        text-transform:uppercase; letter-spacing:.06em; margin:0; }
        .pm-empty     { font-size:12px; color:var(--text-3); margin:0; }
        .pm-list      { display:flex; flex-direction:column; gap:6px; }
        .pl-row       { border:1px solid var(--border); border-radius:8px; overflow:hidden; }
        .pl-row-header { display:flex; align-items:center; gap:7px; padding:9px 12px;
                         background:var(--surface-2); }
        .pl-expand    { background:none; border:none; cursor:pointer; color:var(--text-2);
                        padding:0; display:flex; align-items:center; }
        .pl-name      { flex:1; font-size:13px; font-weight:600; color:var(--text-0); }
        .pl-step-count { font-size:11px; color:var(--text-3); }
        .pl-run-btn   { display:inline-flex; align-items:center; gap:4px;
                        padding:4px 10px; border-radius:5px;
                        background:var(--accent); color:#fff; border:none;
                        font-size:11px; font-weight:600; cursor:pointer; }
        .pl-run-btn:disabled { opacity:.45; cursor:not-allowed; }
        .pl-msg       { font-size:11px; margin:0; padding:4px 12px; }
        .pl-steps     { margin:0; padding:8px 12px 8px 28px;
                        display:flex; flex-direction:column; gap:4px;
                        background:var(--surface-1); }
        .pl-step      { display:flex; align-items:baseline; gap:6px; font-size:12px; }
        .pl-step-num  { font-weight:700; color:var(--accent); min-width:16px; }
        .pl-step-label { color:var(--text-1); }
        .pl-step-params { font-size:10px; color:var(--text-3); background:var(--surface-3);
                          padding:1px 5px; border-radius:4px; }
        .pm-create    { border-top:1px solid var(--border); padding-top:12px;
                        display:flex; flex-direction:column; gap:8px; }
        .pm-create-label { font-size:12px; color:var(--text-2); margin:0; }
        .pm-create-row { display:flex; gap:8px; }
        .pm-input     { flex:1; padding:6px 10px; border-radius:6px;
                        border:1px solid var(--border); background:var(--surface-2);
                        color:var(--text-0); font-size:12px; outline:none; }
        .pm-input:focus { border-color:var(--accent); }
        .pm-save-btn  { display:inline-flex; align-items:center; gap:4px;
                        padding:6px 12px; border-radius:6px;
                        background:var(--surface-3); color:var(--text-1);
                        border:1px solid var(--border); font-size:12px;
                        font-weight:600; cursor:pointer; }
        .pm-save-btn:disabled { opacity:.45; cursor:not-allowed; }
        .pm-save-msg  { font-size:12px; margin:0; }
        @keyframes spin { to { transform:rotate(360deg); } }
        .spin { animation:spin .7s linear infinite; }
      `}</style>
    </div>
  );
}
