/**
 * VisualizationDashboard.jsx
 * Auto-generated charts from the dataset using Recharts (already installed).
 * Renders histograms, bar charts, time series, correlation heatmaps and missing-value bars.
 */
import React, { useState, useCallback } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  LineChart, Line, ResponsiveContainer, Cell, Legend,
} from "recharts";
import { BarChart2, RefreshCw, Loader2, TrendingUp, Grid, AlertTriangle } from "lucide-react";
import { fetchVisualizations } from "../services/api";

const COLORS = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#0891b2", "#a78bfa"];

// ── Tooltip formatters ─────────────────────────────────────────────────────
const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)",
      borderRadius: 8, padding: "8px 12px", fontSize: 12 }}>
      <p style={{ margin: 0, fontWeight: 700, color: "var(--text-1)", marginBottom: 4 }}>{label}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ margin: "2px 0", color: p.color || "var(--text-2)" }}>
          {p.name}: <strong>{typeof p.value === "number" ? p.value.toLocaleString() : p.value}</strong>
        </p>
      ))}
    </div>
  );
};

// ── Individual chart renderers ─────────────────────────────────────────────
function HistogramChart({ chart }) {
  return (
    <div className="viz-card">
      <div className="viz-card-header">
        <BarChart2 size={13} color="#6366f1" />
        <span className="viz-card-title">{chart.title}</span>
      </div>
      {chart.stats && (
        <div className="viz-stats-row">
          {["mean", "median", "std"].map(k => (
            <span key={k} className="viz-stat">
              <span className="viz-stat-label">{k}</span>
              <span className="viz-stat-val">{chart.stats[k]?.toLocaleString()}</span>
            </span>
          ))}
        </div>
      )}
      <ResponsiveContainer width="100%" height={160}>
        <BarChart data={chart.data} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="bin" tick={false} axisLine={false} />
          <YAxis tick={{ fontSize: 9, fill: "var(--text-3)" }} />
          <Tooltip content={<CustomTooltip />} />
          <Bar dataKey="count" fill={chart.color || "#6366f1"} radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function BarChartCard({ chart }) {
  const maxItems = 12;
  const data = chart.data.slice(0, maxItems);
  return (
    <div className="viz-card">
      <div className="viz-card-header">
        <BarChart2 size={13} color={chart.color || "#10b981"} />
        <span className="viz-card-title">{chart.title}</span>
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 8, left: 4, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
          <XAxis type="number" tick={{ fontSize: 9, fill: "var(--text-3)" }} />
          <YAxis dataKey={chart.x_key} type="category" width={80}
            tick={{ fontSize: 9, fill: "var(--text-2)" }} />
          <Tooltip content={<CustomTooltip />} />
          <Bar dataKey={chart.y_keys?.[0] || "count"} fill={chart.color || "#10b981"} radius={[0, 2, 2, 0]}>
            {data.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function TimeSeriesChart({ chart }) {
  return (
    <div className="viz-card viz-card--wide">
      <div className="viz-card-header">
        <TrendingUp size={13} color="#f59e0b" />
        <span className="viz-card-title">{chart.title}</span>
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={chart.data} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey={chart.x_key} tick={{ fontSize: 9, fill: "var(--text-3)" }} interval="preserveStartEnd" />
          <YAxis tick={{ fontSize: 9, fill: "var(--text-3)" }} />
          <Tooltip content={<CustomTooltip />} />
          <Legend iconSize={8} wrapperStyle={{ fontSize: 10 }} />
          {chart.y_keys?.map((key, i) => (
            <Line key={key} type="monotone" dataKey={key}
              stroke={chart.colors?.[i] || COLORS[i % COLORS.length]}
              strokeWidth={2} dot={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function HeatmapChart({ chart }) {
  const cols = chart.columns || [];
  const valueMap = {};
  (chart.data || []).forEach(({ row, col, value }) => {
    valueMap[`${row}::${col}`] = value;
  });
  const colorFor = v => {
    if (v === null || v === undefined) return "var(--surface-3)";
    const abs = Math.abs(v);
    if (v > 0) return `rgba(99,102,241,${abs.toFixed(2)})`;
    return `rgba(239,68,68,${abs.toFixed(2)})`;
  };
  return (
    <div className="viz-card viz-card--wide">
      <div className="viz-card-header">
        <Grid size={13} color="#0891b2" />
        <span className="viz-card-title">{chart.title}</span>
      </div>
      <div style={{ overflowX: "auto", marginTop: 8 }}>
        <table style={{ borderSpacing: 2, borderCollapse: "separate" }}>
          <thead>
            <tr>
              <td style={{ width: 60 }} />
              {cols.map(c => (
                <td key={c} style={{ fontSize: 9, color: "var(--text-3)", maxWidth: 48,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  transform: "rotate(-45deg)", height: 36, verticalAlign: "bottom",
                  paddingBottom: 4 }}>{c}</td>
              ))}
            </tr>
          </thead>
          <tbody>
            {cols.map(row => (
              <tr key={row}>
                <td style={{ fontSize: 9, color: "var(--text-3)", paddingRight: 4,
                  textAlign: "right", maxWidth: 60, overflow: "hidden",
                  textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row}</td>
                {cols.map(col => {
                  const v = valueMap[`${row}::${col}`];
                  return (
                    <td key={col} title={`${row} × ${col} = ${v?.toFixed(2)}`}
                      style={{ width: 24, height: 24, background: colorFor(v),
                        borderRadius: 3, textAlign: "center", fontSize: 7,
                        color: Math.abs(v || 0) > 0.5 ? "#fff" : "var(--text-3)" }}>
                      {v != null ? v.toFixed(1) : ""}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ display: "flex", gap: 8, marginTop: 6, fontSize: 9, color: "var(--text-3)" }}>
          <span style={{ color: "#ef4444" }}>■ Negative correlation</span>
          <span style={{ color: "#6366f1" }}>■ Positive correlation</span>
        </div>
      </div>
    </div>
  );
}


// ── Main component ─────────────────────────────────────────────────────────
export default function VisualizationDashboard({ sessionId }) {
  const [vizData, setVizData]   = useState(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");

  const load = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError("");
    try {
      const result = await fetchVisualizations(sessionId);
      setVizData(result);
    } catch (e) {
      setError(e?.response?.data?.detail || "Failed to generate charts.");
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  function renderChart(chart, i) {
    switch (chart.type) {
      case "histogram":  return <HistogramChart  key={i} chart={chart} />;
      case "timeseries": return <TimeSeriesChart key={i} chart={chart} />;
      case "heatmap":    return <HeatmapChart    key={i} chart={chart} />;
      case "bar":
      default:           return <BarChartCard    key={i} chart={chart} />;
    }
  }

  return (
    <div className="viz-root">
      <div className="viz-header">
        <BarChart2 size={16} />
        <span className="viz-header-title">Auto Visualization</span>
        <button className="viz-run-btn" onClick={load} disabled={loading || !sessionId}>
          {loading ? <Loader2 size={12} className="spin" /> : <RefreshCw size={12} />}
          {vizData ? "Refresh" : "Generate Charts"}
        </button>
      </div>

      {error && (
        <div className="viz-error">
          <AlertTriangle size={13} /> {error}
        </div>
      )}

      {!vizData && !loading && (
        <div className="viz-empty">
          <BarChart2 size={28} color="var(--text-3)" />
          <p>Click <strong>Generate Charts</strong> to auto-visualize your dataset.</p>
          <p style={{ fontSize: 11 }}>Generates histograms, bar charts, trends and correlation matrices.</p>
        </div>
      )}

      {vizData && (
        <>
          <div className="viz-meta">
            {vizData.total_charts} charts · {vizData.numeric_cols?.length} numeric ·
            {" "}{vizData.object_cols?.length} categorical ·
            {" "}{vizData.date_cols?.length} date columns
          </div>
          <div className="viz-grid">
            {vizData.charts.map((chart, i) => renderChart(chart, i))}
          </div>
        </>
      )}

      <style>{`
        .viz-root          { display:flex; flex-direction:column; gap:12px; padding:14px; }
        .viz-header        { display:flex; align-items:center; gap:8px; }
        .viz-header-title  { font-size:14px; font-weight:700; color:var(--text-0); flex:1; }
        .viz-run-btn       { display:inline-flex; align-items:center; gap:6px; padding:6px 14px;
                             background:var(--accent); color:#fff; border:none; border-radius:8px;
                             font-size:12px; font-weight:600; cursor:pointer; }
        .viz-run-btn:disabled { opacity:.5; cursor:not-allowed; }
        .viz-run-btn:hover:not(:disabled) { filter:brightness(1.1); }
        .viz-empty         { display:flex; flex-direction:column; align-items:center; justify-content:center;
                             gap:8px; padding:48px 24px; color:var(--text-2); text-align:center; }
        .viz-empty p       { margin:0; font-size:13px; }
        .viz-error         { display:flex; align-items:center; gap:6px; padding:8px 12px;
                             background:#ef444422; color:#ef4444; border-radius:8px; font-size:12px; }
        .viz-meta          { font-size:11px; color:var(--text-3); }
        .viz-grid          { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:14px; }
        .viz-card          { background:var(--surface-1); border:1px solid var(--border);
                             border-radius:12px; padding:14px; }
        .viz-card--wide    { grid-column:span 2; }
        .viz-card-header   { display:flex; align-items:center; gap:6px; margin-bottom:8px; }
        .viz-card-title    { font-size:12px; font-weight:600; color:var(--text-1);
                             flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .viz-stats-row     { display:flex; gap:10px; margin-bottom:6px; }
        .viz-stat          { display:flex; flex-direction:column; gap:1px; }
        .viz-stat-label    { font-size:9px; color:var(--text-3); text-transform:uppercase; letter-spacing:.05em; }
        .viz-stat-val      { font-size:11px; font-weight:700; color:var(--text-1); font-variant-numeric:tabular-nums; }
        @keyframes spin    { to { transform:rotate(360deg); } }
        .spin              { animation:spin .8s linear infinite; }
        @media (max-width: 600px) { .viz-card--wide { grid-column:span 1; } }
      `}</style>
    </div>
  );
}
