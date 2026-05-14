/**
 * AICommandCenter — The unified AI interface.
 * 
 * Replaces the scattered experience of:
 *   - AIInsightsPanel
 *   - AIAgentPanel  
 *   - AIChatBox
 * 
 * Shows everything the AI knows about your data in one place:
 *   1. Health score & summary
 *   2. Auto-executable actions (one-click apply)
 *   3. Manual review actions
 *   4. Visualizations
 *   5. Chat interface for questions
 */
import React, { useState, useEffect } from "react";
import { 
  Sparkles, Play, CheckCircle2, AlertCircle, 
  TrendingUp, BarChart3, MessageSquare, Loader2,
  ChevronDown, ChevronRight, Info
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip,
  LineChart, Line, CartesianGrid, Legend,
} from "recharts";
import { orchestrateAI, executeAction } from "../services/api";

export default function AICommandCenter({ sessionId, initialInsights = null, onActionApplied = null }) {
  const [loading, setLoading] = useState(initialInsights === null);
  const [insights, setInsights] = useState(initialInsights);
  const [executing, setExecuting] = useState(new Set());
  const [completed, setCompleted] = useState(new Set());
  const [failed, setFailed] = useState(new Set());
  const [expandedActions, setExpandedActions] = useState(new Set());
  const [activeView, setActiveView] = useState("actions");

  useEffect(() => {
    if (initialInsights) {
      setInsights(initialInsights);
      setLoading(false);
      // Auto-expand first 3 auto-executable actions
      const autoActions = initialInsights.actions
        ?.filter(a => a.auto_executable)
        .slice(0, 3)
        .map(a => a.id) || [];
      setExpandedActions(new Set(autoActions));
    } else {
      loadInsights();
    }
  }, [sessionId, initialInsights]);

  async function loadInsights() {
    try {
      setLoading(true);
      const data = await orchestrateAI(sessionId);
      setInsights(data);
      
      // Auto-expand first 3 auto-executable actions
      const autoActions = data.actions
        ?.filter(a => a.auto_executable)
        .slice(0, 3)
        .map(a => a.id) || [];
      setExpandedActions(new Set(autoActions));
    } catch (err) {
      console.error("Failed to load AI insights:", err);
    } finally {
      setLoading(false);
    }
  }

  async function handleExecuteAction(actionId) {
    try {
      setExecuting(prev => new Set(prev).add(actionId));
      setFailed(prev => { const n = new Set(prev); n.delete(actionId); return n; });
      const result = await executeAction(sessionId, actionId);
      setCompleted(prev => new Set(prev).add(actionId));
      // Notify Dashboard to refresh grid with updated data
      if (onActionApplied) onActionApplied(result);
      // Refresh insights panel after a short delay
      setTimeout(() => loadInsights(), 1200);
    } catch (err) {
      console.error("Failed to execute action:", err);
      setFailed(prev => new Set(prev).add(actionId));
    } finally {
      setExecuting(prev => {
        const next = new Set(prev);
        next.delete(actionId);
        return next;
      });
    }
  }

  function toggleAction(actionId) {
    setExpandedActions(prev => {
      const next = new Set(prev);
      if (next.has(actionId)) {
        next.delete(actionId);
      } else {
        next.add(actionId);
      }
      return next;
    });
  }

  if (loading) {
    return (
      <div className="acc-loading">
        <Loader2 size={20} className="spin" />
        <span>Analyzing your data...</span>
      </div>
    );
  }

  if (!insights) {
    return (
      <div className="acc-error">
        <AlertCircle size={18} />
        <span>Failed to load AI insights</span>
      </div>
    );
  }

  const autoActions = insights.actions?.filter(a => a.auto_executable) || [];
  const manualActions = insights.actions?.filter(a => !a.auto_executable) || [];
  const healthScore = insights.health_score || {};

  return (
    <div className="acc-root">
      {/* ═══════════════════════════════════════════════════════════ */}
      {/* HEADER - Health Score & Summary */}
      {/* ═══════════════════════════════════════════════════════════ */}
      <div className="acc-header">
        <div className="acc-health">
          <div className="acc-health-badge" data-grade={healthScore.grade}>
            <div className="acc-health-score">{healthScore.score || 0}</div>
            <div className="acc-health-label">Quality Score</div>
          </div>
          <div className="acc-health-details">
            <div className="acc-health-grade">Grade: {healthScore.grade || 'F'}</div>
            <div className="acc-health-issues">
              {insights.issues?.length || 0} issues detected
            </div>
          </div>
        </div>
        
        <div className="acc-summary">
          <Sparkles size={16} />
          <p>{insights.summary}</p>
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* TABS - Actions / Visualizations / Chat */}
      {/* ═══════════════════════════════════════════════════════════ */}
      <div className="acc-tabs">
        <button
          className={`acc-tab ${activeView === "actions" ? "active" : ""}`}
          onClick={() => setActiveView("actions")}
        >
          <CheckCircle2 size={14} />
          Actions ({insights.actions?.length || 0})
        </button>
        <button
          className={`acc-tab ${activeView === "visualizations" ? "active" : ""}`}
          onClick={() => setActiveView("visualizations")}
        >
          <BarChart3 size={14} />
          Insights ({insights.visualizations?.length || 0})
        </button>
        <button
          className={`acc-tab ${activeView === "chat" ? "active" : ""}`}
          onClick={() => setActiveView("chat")}
        >
          <MessageSquare size={14} />
          Chat
        </button>
      </div>

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* CONTENT AREA */}
      {/* ═══════════════════════════════════════════════════════════ */}
      <div className="acc-content">
        {activeView === "actions" && (
          <div className="acc-actions">
            {/* AUTO-EXECUTABLE ACTIONS */}
            {autoActions.length > 0 && (
              <div className="acc-action-section">
                <div className="acc-section-header">
                  <Sparkles size={14} />
                  <h3>One-Click Fixes</h3>
                  <span className="acc-badge">{autoActions.length}</span>
                </div>
                <div className="acc-action-list">
                  {autoActions.map(action => (
                    <ActionCard
                      key={action.id}
                      action={action}
                      expanded={expandedActions.has(action.id)}
                      executing={executing.has(action.id)}
                      completed={completed.has(action.id)}
                      failed={failed.has(action.id)}
                      onToggle={() => toggleAction(action.id)}
                      onExecute={() => handleExecuteAction(action.id)}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* MANUAL REVIEW ACTIONS */}
            {manualActions.length > 0 && (
              <div className="acc-action-section">
                <div className="acc-section-header">
                  <Info size={14} />
                  <h3>Review & Apply</h3>
                  <span className="acc-badge">{manualActions.length}</span>
                </div>
                <div className="acc-action-list">
                  {manualActions.map(action => (
                    <ActionCard
                      key={action.id}
                      action={action}
                      expanded={expandedActions.has(action.id)}
                      executing={executing.has(action.id)}
                      completed={completed.has(action.id)}
                      failed={failed.has(action.id)}
                      onToggle={() => toggleAction(action.id)}
                      onExecute={() => handleExecuteAction(action.id)}
                    />
                  ))}
                </div>
              </div>
            )}

            {insights.actions?.length === 0 && (
              <div className="acc-empty">
                <CheckCircle2 size={24} />
                <p>No actions needed — your data looks great!</p>
              </div>
            )}
          </div>
        )}

        {activeView === "visualizations" && (
          <div className="acc-visualizations">
            {insights.visualizations?.length > 0 ? (
              <div className="acc-viz-grid">
                {insights.visualizations.map((viz, idx) => (
                  <VizCard key={idx} viz={viz} />
                ))}
              </div>
            ) : (
              <div className="acc-empty">
                <BarChart3 size={24} />
                <p>No visualizations available for this dataset</p>
              </div>
            )}
          </div>
        )}

        {activeView === "chat" && (
          <div className="acc-chat">
            <div className="acc-chat-placeholder">
              <MessageSquare size={32} />
              <p>Chat interface coming soon</p>
              <p className="acc-chat-hint">Ask questions about your data, get recommendations, and explore insights</p>
            </div>
          </div>
        )}
      </div>

      <style>{`
        .acc-root {
          display: flex;
          flex-direction: column;
          height: 100%;
          background: var(--surface-0);
          border-radius: 12px;
          overflow: hidden;
        }

        .acc-loading, .acc-error {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          padding: 48px 20px;
          color: var(--text-2);
          font-size: 13px;
        }

        /* ═══ HEADER ═══ */
        .acc-header {
          padding: 20px;
          background: linear-gradient(135deg, rgba(99,102,241,0.1) 0%, rgba(168,85,247,0.1) 100%);
          border-bottom: 1px solid var(--border);
        }

        .acc-health {
          display: flex;
          align-items: center;
          gap: 16px;
          margin-bottom: 16px;
        }

        .acc-health-badge {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          width: 88px;
          height: 88px;
          border-radius: 50%;
          background: var(--surface-1);
          border: 3px solid var(--green);
          flex-shrink: 0;
          gap: 2px;
        }

        .acc-health-badge[data-grade="A"], .acc-health-badge[data-grade="B"] {
          border-color: var(--green);
        }

        .acc-health-badge[data-grade="C"] {
          border-color: var(--amber);
        }

        .acc-health-badge[data-grade="D"], .acc-health-badge[data-grade="F"] {
          border-color: var(--red);
        }

        .acc-health-score {
          font-size: 22px;
          font-weight: 800;
          color: var(--text-0);
          line-height: 1;
        }

        .acc-health-label {
          font-size: 8px;
          text-transform: uppercase;
          color: var(--text-3);
          font-weight: 600;
          letter-spacing: 0.4px;
          text-align: center;
          max-width: 70px;
        }

        .acc-health-details {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .acc-health-grade {
          font-size: 14px;
          font-weight: 700;
          color: var(--text-0);
        }

        .acc-health-issues {
          font-size: 12px;
          color: var(--text-2);
        }

        .acc-summary {
          display: flex;
          align-items: flex-start;
          gap: 10px;
          padding: 12px;
          background: var(--surface-1);
          border-radius: 8px;
          border: 1px solid var(--border);
        }

        .acc-summary svg {
          flex-shrink: 0;
          margin-top: 2px;
          color: var(--accent);
        }

        .acc-summary p {
          margin: 0;
          font-size: 13px;
          line-height: 1.5;
          color: var(--text-1);
        }

        /* ═══ TABS ═══ */
        .acc-tabs {
          display: flex;
          gap: 4px;
          padding: 12px 20px 0;
          background: var(--surface-0);
          border-bottom: 1px solid var(--border);
        }

        .acc-tab {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 8px 16px;
          background: none;
          border: none;
          border-radius: 8px 8px 0 0;
          font-size: 13px;
          font-weight: 600;
          color: var(--text-2);
          cursor: pointer;
          transition: all 0.2s;
        }

        .acc-tab:hover {
          background: var(--surface-1);
          color: var(--text-0);
        }

        .acc-tab.active {
          background: var(--surface-1);
          color: var(--accent);
          border-bottom: 2px solid var(--accent);
        }

        /* ═══ CONTENT ═══ */
        .acc-content {
          flex: 1;
          overflow-y: auto;
          padding: 20px;
        }

        .acc-action-section {
          margin-bottom: 24px;
        }

        .acc-section-header {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 12px;
          color: var(--text-1);
        }

        .acc-section-header h3 {
          margin: 0;
          font-size: 14px;
          font-weight: 700;
        }

        .acc-badge {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          padding: 2px 8px;
          background: var(--surface-2);
          border-radius: 12px;
          font-size: 11px;
          font-weight: 700;
          color: var(--text-2);
        }

        .acc-action-list {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .acc-empty {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 12px;
          padding: 48px 20px;
          color: var(--text-3);
          text-align: center;
        }

        .acc-empty p {
          margin: 0;
          font-size: 13px;
        }

        /* ═══ VISUALIZATIONS ═══ */
        .acc-viz-grid {
          display: grid;
          grid-template-columns: 1fr;
          gap: 16px;
        }

        .acc-viz-card {
          padding: 16px;
          background: var(--surface-1);
          border: 1px solid var(--border);
          border-radius: 8px;
        }

        .acc-viz-card h4 {
          margin: 0 0 4px;
          font-size: 13px;
          font-weight: 700;
          color: var(--text-0);
        }

        .acc-viz-type {
          font-size: 10px;
          color: var(--text-3);
          text-transform: uppercase;
          letter-spacing: 0.5px;
          margin-bottom: 12px;
        }

        /* ═══ CHAT ═══ */
        .acc-chat {
          height: 100%;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .acc-chat-placeholder {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 12px;
          color: var(--text-3);
          text-align: center;
        }

        .acc-chat-hint {
          font-size: 12px;
          max-width: 320px;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }

        .spin {
          animation: spin 1s linear infinite;
        }
      `}</style>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════ */
/* ACTION CARD COMPONENT */
/* ═══════════════════════════════════════════════════════════════════ */
function ActionCard({ action, expanded, executing, completed, failed, onToggle, onExecute }) {
  const severityColor = {
    critical: "var(--red)",
    high: "var(--amber)",
    medium: "var(--blue)",
    low: "var(--text-3)",
  }[action.impact?.severity] || "var(--text-3)";

  return (
    <div className={`action-card ${expanded ? "expanded" : ""}`}>
      <div className="action-card-header" onClick={onToggle}>
        <div className="action-card-icon">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </div>
        
        <div className="action-card-title">
          <div className="action-card-problem">{action.problem}</div>
          <div className="action-card-meta">
            <span className="action-card-category">{action.category}</span>
            <span className="action-card-confidence">
              {Math.round(action.confidence * 100)}% confidence
            </span>
          </div>
        </div>

        {completed && (
          <CheckCircle2 size={16} className="action-card-check" />
        )}
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="action-card-body"
          >
            <div className="action-card-solution">
              <strong>Solution:</strong> {action.solution}
            </div>

            <div className="action-card-impact">
              <div className="action-card-impact-item">
                <span>Rows affected:</span>
                <span>{action.impact?.rows_affected || 0}</span>
              </div>
              <div className="action-card-impact-item">
                <span>Severity:</span>
                <span style={{ color: severityColor }}>
                  {action.impact?.severity || "unknown"}
                </span>
              </div>
            </div>

            <button
              className={`action-card-btn${failed ? " action-card-btn--error" : ""}`}
              onClick={(e) => {
                e.stopPropagation();
                onExecute();
              }}
              disabled={executing || completed}
            >
              {executing ? (
                <>
                  <Loader2 size={14} className="spin" />
                  Applying...
                </>
              ) : completed ? (
                <>
                  <CheckCircle2 size={14} />
                  Applied
                </>
              ) : failed ? (
                <>
                  <AlertCircle size={14} />
                  Retry Fix
                </>
              ) : (
                <>
                  <Play size={14} />
                  Apply Fix
                </>
              )}
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <style>{`
        .action-card {
          background: var(--surface-1);
          border: 1px solid var(--border);
          border-radius: 8px;
          overflow: hidden;
          transition: all 0.2s;
        }

        .action-card:hover {
          border-color: var(--border-2);
        }

        .action-card-header {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px;
          cursor: pointer;
          user-select: none;
        }

        .action-card-icon {
          flex-shrink: 0;
          color: var(--text-2);
        }

        .action-card-title {
          flex: 1;
          min-width: 0;
        }

        .action-card-problem {
          font-size: 13px;
          font-weight: 600;
          color: var(--text-0);
          margin-bottom: 4px;
        }

        .action-card-meta {
          display: flex;
          align-items: center;
          gap: 12px;
          font-size: 11px;
          color: var(--text-3);
        }

        .action-card-category {
          text-transform: uppercase;
          font-weight: 600;
        }

        .action-card-check {
          flex-shrink: 0;
          color: var(--green);
        }

        .action-card-body {
          padding: 0 12px 12px;
          overflow: hidden;
        }

        .action-card-solution {
          padding: 12px;
          background: var(--surface-0);
          border-radius: 6px;
          font-size: 12px;
          color: var(--text-1);
          margin-bottom: 12px;
        }

        .action-card-solution strong {
          color: var(--text-0);
        }

        .action-card-impact {
          display: flex;
          gap: 16px;
          margin-bottom: 12px;
          font-size: 12px;
        }

        .action-card-impact-item {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .action-card-impact-item span:first-child {
          color: var(--text-3);
          font-size: 10px;
          text-transform: uppercase;
        }

        .action-card-impact-item span:last-child {
          color: var(--text-0);
          font-weight: 600;
        }

        .action-card-btn {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 8px 16px;
          background: var(--accent);
          color: #fff;
          border: none;
          border-radius: 6px;
          font-size: 12px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
        }

        .action-card-btn:hover:not(:disabled) {
          transform: translateY(-1px);
          box-shadow: 0 4px 12px rgba(99,102,241,0.3);
        }

        .action-card-btn--error {
          background: var(--red, #ef4444);
        }

        .action-card-btn--error:hover:not(:disabled) {
          box-shadow: 0 4px 12px rgba(239,68,68,0.3);
        }

        .action-card-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
      `}</style>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════ */
/* VIZ CARD COMPONENT — renders real Recharts charts from backend spec */
/* ═══════════════════════════════════════════════════════════════════ */
function VizCard({ viz }) {
  const { type, title, data, x_key, y_keys = [], colors = [], color } = viz;

  const COLORS = [
    color || "#6366f1", "#10b981", "#f59e0b", "#ef4444", "#3b82f6", "#8b5cf6",
  ];

  function renderChart() {
    if (!data || data.length === 0) {
      return (
        <div className="viz-empty">
          <BarChart3 size={24} />
          <span>No data</span>
        </div>
      );
    }

    if (type === "histogram" || type === "bar") {
      return (
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={data} margin={{ top: 4, right: 8, left: -20, bottom: 40 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis
              dataKey={x_key}
              tick={{ fontSize: 10, fill: "var(--text-3)" }}
              angle={-35}
              textAnchor="end"
              interval="preserveStartEnd"
            />
            <YAxis tick={{ fontSize: 10, fill: "var(--text-3)" }} />
            <Tooltip
              contentStyle={{
                background: "var(--surface-2, #1e1e2e)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                fontSize: 12,
              }}
            />
            {y_keys.map((key, i) => (
              <Bar key={key} dataKey={key} fill={COLORS[i % COLORS.length]} radius={[3, 3, 0, 0]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      );
    }

    if (type === "timeseries") {
      return (
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={data} margin={{ top: 4, right: 8, left: -20, bottom: 40 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis
              dataKey={x_key}
              tick={{ fontSize: 10, fill: "var(--text-3)" }}
              angle={-35}
              textAnchor="end"
              interval="preserveStartEnd"
            />
            <YAxis tick={{ fontSize: 10, fill: "var(--text-3)" }} />
            <Tooltip
              contentStyle={{
                background: "var(--surface-2, #1e1e2e)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                fontSize: 12,
              }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {y_keys.map((key, i) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                stroke={COLORS[i % COLORS.length]}
                dot={false}
                strokeWidth={2}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      );
    }

    if (type === "heatmap") {
      // Render as a compact table-style heatmap
      const cols = viz.columns || [];
      const maxVal = Math.max(...(data || []).map(d => Math.abs(d.value || 0)));
      return (
        <div className="viz-heatmap">
          <div className="viz-heatmap-grid" style={{ gridTemplateColumns: `60px repeat(${cols.length}, 1fr)` }}>
            <div className="viz-heatmap-cell viz-heatmap-header" />
            {cols.map(c => (
              <div key={c} className="viz-heatmap-cell viz-heatmap-header" title={c}>
                {c.length > 6 ? c.slice(0, 6) + "…" : c}
              </div>
            ))}
            {cols.map(row => (
              <React.Fragment key={row}>
                <div className="viz-heatmap-cell viz-heatmap-label" title={row}>
                  {row.length > 6 ? row.slice(0, 6) + "…" : row}
                </div>
                {cols.map(col => {
                  const cell = data?.find(d => d.row === row && d.col === col);
                  const val = cell?.value ?? 0;
                  const intensity = maxVal > 0 ? Math.abs(val) / maxVal : 0;
                  const bg = val >= 0
                    ? `rgba(99,102,241,${intensity * 0.8})`
                    : `rgba(239,68,68,${intensity * 0.8})`;
                  return (
                    <div
                      key={col}
                      className="viz-heatmap-cell"
                      style={{ background: bg }}
                      title={`${row} × ${col}: ${val.toFixed(2)}`}
                    >
                      {val.toFixed(1)}
                    </div>
                  );
                })}
              </React.Fragment>
            ))}
          </div>
        </div>
      );
    }

    // Fallback for unknown types
    return (
      <div className="viz-empty">
        <BarChart3 size={24} />
        <span>{type}</span>
      </div>
    );
  }

  return (
    <div className="acc-viz-card">
      <h4>{title}</h4>
      <div className="acc-viz-type">{type}</div>
      {renderChart()}
      <style>{`
        .viz-empty {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 8px;
          padding: 32px;
          color: var(--text-3);
          font-size: 12px;
        }
        .viz-heatmap {
          overflow-x: auto;
          margin-top: 8px;
        }
        .viz-heatmap-grid {
          display: grid;
          gap: 2px;
          font-size: 10px;
        }
        .viz-heatmap-cell {
          padding: 4px 3px;
          text-align: center;
          border-radius: 3px;
          color: var(--text-1);
          min-width: 0;
          overflow: hidden;
          white-space: nowrap;
        }
        .viz-heatmap-header {
          font-weight: 700;
          color: var(--text-3);
          font-size: 9px;
          text-transform: uppercase;
        }
        .viz-heatmap-label {
          font-weight: 600;
          color: var(--text-2);
          text-align: right;
          padding-right: 6px;
        }
      `}</style>
    </div>
  );
}
