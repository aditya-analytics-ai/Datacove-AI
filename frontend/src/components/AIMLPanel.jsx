/**
 * AIMLPanel — AI Data Scientist mode.
 * Auto-detects target, trains RandomForest, shows metrics + feature importance.
 */
import React, { useState, useEffect } from "react";
import { Brain, Loader2, ChevronDown, ChevronRight, Target } from "lucide-react";
import { trainModel, suggestTargets } from "../services/api";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";

const ACCENT = "#6366f1";

export default function AIMLPanel({ sessionId }) {
  const [open,       setOpen]       = useState(true);
  const [targets,    setTargets]    = useState([]);
  const [selected,   setSelected]   = useState("");
  const [training,   setTraining]   = useState(false);
  const [result,     setResult]     = useState(null);
  const [error,      setError]      = useState("");

  // Load candidate target columns
  useEffect(() => {
    if (!sessionId) return;
    suggestTargets(sessionId)
      .then(r => {
        setTargets(r.candidates ?? []);
        if (r.candidates?.length > 0) setSelected(r.candidates[0].column);
      })
      .catch(() => {});
  }, [sessionId]);

  async function handleTrain() {
    setTraining(true);
    setError("");
    setResult(null);
    try {
      const res = await trainModel(sessionId, selected || null);
      setResult(res);
    } catch (err) {
      setError(err?.response?.data?.detail ?? "Training failed.");
    } finally {
      setTraining(false);
    }
  }

  return (
    <div className="ml-wrap">
      <div className="ml-header">
        <Brain size={15} color="#a78bfa" />
        <span className="ml-title">AI Data Scientist</span>
        <button className="ml-expand" onClick={() => setOpen(o => !o)}>
          {open ? <ChevronDown size={14}/> : <ChevronRight size={14}/>}
        </button>
      </div>

      {open && (
        <div className="ml-body">
          <p className="ml-desc">
            Auto-detect target, train a RandomForest model, and get accuracy metrics + feature importance.
          </p>

          {/* Target selector */}
          <div className="ml-target-row">
            <Target size={13} color="var(--text-2)" />
            <select
              className="ml-select"
              value={selected}
              onChange={e => setSelected(e.target.value)}
              disabled={training}
            >
              <option value="">Auto-detect target</option>
              {targets.map(t => (
                <option key={t.column} value={t.column}>
                  {t.column} ({t.n_unique} unique)
                </option>
              ))}
            </select>
          </div>

          <button className="ml-train-btn" onClick={handleTrain} disabled={training || !sessionId}>
            {training
              ? <><Loader2 size={14} className="spin" /> Training…</>
              : <><Brain size={14} /> Train Model</>}
          </button>

          {error && <p className="ml-error">{error}</p>}

          {result && <MLResult result={result} />}
        </div>
      )}

      <style>{`
        .ml-wrap    { background:var(--surface-1); border-radius:12px; overflow:hidden; }
        .ml-header  { display:flex; align-items:center; gap:8px; padding:12px 14px;
                      border-bottom:1px solid var(--border); }
        .ml-title   { flex:1; font-size:13px; font-weight:700; color:var(--text-0); }
        .ml-expand  { background:none; border:none; cursor:pointer; color:var(--text-2); padding:0; }
        .ml-body    { padding:14px; display:flex; flex-direction:column; gap:10px; }
        .ml-desc    { font-size:12px; color:var(--text-2); margin:0; }
        .ml-target-row { display:flex; align-items:center; gap:8px; }
        .ml-select  { flex:1; padding:6px 10px; border-radius:6px; border:1px solid var(--border);
                      background:var(--surface-2); color:var(--text-0); font-size:12px; outline:none; }
        .ml-select:focus { border-color:var(--accent); }
        .ml-train-btn { display:inline-flex; align-items:center; gap:6px;
                        padding:8px 16px; border-radius:8px; border:none; cursor:pointer;
                        background:#7c3aed; color:#fff; font-size:13px; font-weight:600; }
        .ml-train-btn:disabled { opacity:.5; cursor:not-allowed; }
        .ml-error   { font-size:12px; color:#ef4444; margin:0; }
        @keyframes spin { to { transform:rotate(360deg); } }
        .spin { animation:spin .7s linear infinite; }
      `}</style>
    </div>
  );
}

function MLResult({ result }) {
  const metrics  = result.metrics ?? {};
  const fi       = (result.feature_importance ?? []).slice(0, 10);
  const isClass  = result.problem_type === "classification";

  return (
    <div className="mlr-wrap">
      {/* Header */}
      <div className="mlr-pill-row">
        <Pill label={result.model} color="#7c3aed" />
        <Pill label={result.problem_type} color={isClass ? "#0891b2" : "#0d9488"} />
        <Pill label={`Target: ${result.target}`} color="var(--accent)" />
      </div>

      {/* Metrics */}
      <div className="mlr-metrics">
        {isClass && metrics.accuracy != null && (
          <MetricBox label="Accuracy" value={(metrics.accuracy * 100).toFixed(1) + "%"} color="#22c55e" />
        )}
        {!isClass && metrics.r2 != null && (
          <MetricBox label="R²" value={metrics.r2.toFixed(3)} color="#22c55e" />
        )}
        {!isClass && metrics.mae != null && (
          <MetricBox label="MAE" value={metrics.mae.toFixed(3)} color="#f59e0b" />
        )}
        {!isClass && metrics.rmse != null && (
          <MetricBox label="RMSE" value={metrics.rmse.toFixed(3)} color="#ef4444" />
        )}
        <MetricBox label="Train rows" value={result.train_rows} />
        <MetricBox label="Test rows"  value={result.test_rows} />
      </div>

      {/* Feature importance chart */}
      {fi.length > 0 && (
        <div className="mlr-fi">
          <p className="mlr-fi-title">Feature Importance</p>
          <ResponsiveContainer width="100%" height={fi.length * 22 + 20}>
            <BarChart
              data={fi}
              layout="vertical"
              margin={{ top: 0, right: 8, bottom: 0, left: 4 }}
            >
              <XAxis type="number" tick={{ fontSize: 10, fill: "var(--text-2)" }} axisLine={false} tickLine={false} />
              <YAxis
                type="category" dataKey="feature"
                width={90}
                tick={{ fontSize: 10, fill: "var(--text-1)" }}
                axisLine={false} tickLine={false}
              />
              <Tooltip
                contentStyle={{ background: "var(--surface-2)", border: "1px solid var(--border)", fontSize: 11 }}
                labelStyle={{ color: "var(--text-0)" }}
                formatter={v => [v.toFixed(4), "Importance"]}
              />
              <Bar dataKey="importance" radius={[0, 4, 4, 0]}>
                {fi.map((_, i) => (
                  <Cell key={i} fill={`hsl(${240 - i * 15},70%,55%)`} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <style>{`
        .mlr-wrap       { display:flex; flex-direction:column; gap:10px;
                          background:var(--surface-2); border-radius:10px; padding:12px; }
        .mlr-pill-row   { display:flex; flex-wrap:wrap; gap:5px; }
        .mlr-pill       { font-size:10px; font-weight:700; padding:2px 8px; border-radius:99px;
                          letter-spacing:.04em; text-transform:uppercase; }
        .mlr-metrics    { display:grid; grid-template-columns:1fr 1fr; gap:6px; }
        .metric-box     { background:var(--surface-1); border-radius:8px; padding:8px 10px;
                          display:flex; flex-direction:column; gap:2px; }
        .metric-label   { font-size:10px; color:var(--text-2); text-transform:uppercase; letter-spacing:.05em; }
        .metric-value   { font-size:16px; font-weight:700; }
        .mlr-fi         { display:flex; flex-direction:column; gap:5px; }
        .mlr-fi-title   { font-size:11px; font-weight:700; color:var(--text-2);
                          text-transform:uppercase; letter-spacing:.05em; margin:0; }
      `}</style>
    </div>
  );
}

function Pill({ label, color }) {
  return (
    <span className="mlr-pill" style={{ background: color + "22", color }}>
      {label}
    </span>
  );
}

function MetricBox({ label, value, color }) {
  return (
    <div className="metric-box">
      <span className="metric-label">{label}</span>
      <span className="metric-value" style={{ color: color ?? "var(--text-0)" }}>{value}</span>
    </div>
  );
}
