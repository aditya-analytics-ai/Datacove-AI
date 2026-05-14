/**
 * DatasetsPage — "My Datasets" listing.
 * Shows all sessions belonging to the current user with stats,
 * health score, and options to reopen or delete.
 */
import React, { useState, useEffect, useCallback } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  FileSpreadsheet, Trash2, RefreshCw, Upload,
  AlertCircle, Loader2, Clock, Database, BarChart2,
} from "lucide-react";
import { fetchMySessions, deleteSession } from "../services/api";
import { SkeletonCard } from "../components/Skeleton";

function timeAgo(ts) {
  if (!ts) return "—";
  const diff = Date.now() / 1000 - ts;
  if (diff < 60)   return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function HealthBadge({ score }) {
  if (score == null) return <span style={{ color: "var(--text-2)", fontSize: 11 }}>not analysed</span>;
  const color = score >= 80 ? "#22c55e" : score >= 60 ? "#f59e0b" : "#ef4444";
  const grade = score >= 90 ? "A" : score >= 80 ? "B" : score >= 70 ? "C" : score >= 60 ? "D" : "F";
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      fontSize: 11, fontWeight: 600, color,
    }}>
      <span style={{
        width: 6, height: 6, borderRadius: "50%", background: color,
      }} />
      {score} ({grade})
    </span>
  );
}

export default function DatasetsPage() {
  const navigate = useNavigate();
  const [sessions, setSessions]   = useState([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState("");
  const [deleting, setDeleting]   = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetchMySessions();
      setSessions(res.sessions || []);
    } catch {
      setError("Could not load your datasets. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleOpen = (session) => {
    navigate("/dashboard", {
      state: {
        session: {
          session_id: session.id,
          columns:    [],
          preview:    [],
          filename:   session.filename,
          rows:       session.rows,
        },
      },
    });
  };

  const handleDelete = async (e, sessionId) => {
    e.stopPropagation();
    if (!window.confirm("Delete this dataset? This cannot be undone.")) return;
    setDeleting(sessionId);
    try {
      await deleteSession(sessionId);
      setSessions(s => s.filter(x => x.id !== sessionId));
    } catch (err) {
      const msg = err?.response?.data?.detail || err?.message || "Failed to delete.";
      setError(msg);
    } finally {
      setDeleting(null);
    }
  };

  const css = `
    .ds-page { min-height: 100vh; background: var(--bg); padding: 40px 32px; }
    .ds-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 28px; }
    .ds-title { font-size: 20px; font-weight: 600; color: var(--text-0); }
    .ds-subtitle { font-size: 13px; color: var(--text-2); margin-top: 2px; }
    .ds-btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px;
      background: var(--accent); color: #fff; border: none; border-radius: var(--radius-md);
      font-size: 13px; font-weight: 500; cursor: pointer; }
    .ds-btn:hover { opacity: 0.9; }
    .ds-btn-ghost { background: var(--surface-2); color: var(--text-1); border: 1px solid var(--border); }
    .ds-btn-ghost:hover { background: var(--surface-3); }
    .ds-grid { display: grid; gap: 10px; }
    .ds-card { background: var(--surface-1); border: 1px solid var(--border);
      border-radius: var(--radius-lg); padding: 16px 20px;
      display: flex; align-items: center; gap: 16px; cursor: pointer;
      transition: border-color 0.15s; }
    .ds-card:hover { border-color: var(--accent); }
    .ds-icon { width: 40px; height: 40px; border-radius: var(--radius-md);
      background: var(--accent-dim); display: flex; align-items: center;
      justify-content: center; flex-shrink: 0; }
    .ds-info { flex: 1; min-width: 0; }
    .ds-name { font-size: 14px; font-weight: 500; color: var(--text-0);
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .ds-meta { display: flex; gap: 14px; margin-top: 5px; flex-wrap: wrap; }
    .ds-stat { display: flex; align-items: center; gap: 4px;
      font-size: 11px; color: var(--text-2); }
    .ds-del { padding: 6px; border-radius: var(--radius-sm); border: none;
      background: transparent; color: var(--text-3); cursor: pointer;
      display: flex; align-items: center; }
    .ds-del:hover { background: rgba(239,68,68,0.12); color: #ef4444; }
    .ds-empty { text-align: center; padding: 80px 20px; color: var(--text-2); }
    .ds-empty-icon { margin: 0 auto 16px; opacity: 0.3; }
    .ds-error { display: flex; align-items: center; gap: 8px; color: #ef4444;
      font-size: 13px; padding: 12px 16px; background: rgba(239,68,68,0.08);
      border-radius: var(--radius-md); margin-bottom: 20px; }
  `;

  return (
    <>
      <style>{css}</style>
      <div className="ds-page">
        <div className="ds-header">
          <div>
            <div className="ds-title">My Datasets</div>
            <div className="ds-subtitle">{sessions.length} dataset{sessions.length !== 1 ? "s" : ""}</div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="ds-btn ds-btn-ghost" onClick={load} disabled={loading}>
              <RefreshCw size={14} style={loading ? { animation: "spin .7s linear infinite" } : {}} />
              Refresh
            </button>
            <Link to="/billing" style={{ display:"inline-flex", alignItems:"center",
              gap:6, padding:"8px 14px", background:"var(--surface-2)", color:"var(--text-1)",
              border:"1px solid var(--border)", borderRadius:"var(--radius-md)",
              fontSize:13, fontWeight:500, textDecoration:"none" }}>
              Billing
            </Link>
            <button className="ds-btn" onClick={() => navigate("/")}>
              <Upload size={14} /> Upload new
            </button>
          </div>
        </div>

        {error && (
          <div className="ds-error">
            <AlertCircle size={14} /> {error}
          </div>
        )}

        {loading ? (
          <div className="ds-grid">
            {Array.from({ length: 4 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        ) : sessions.length === 0 ? (
          <div className="ds-empty">
            <Database size={48} className="ds-empty-icon" />
            <div style={{ fontSize: 15, fontWeight: 500, color: "var(--text-1)", marginBottom: 8 }}>
              No datasets yet
            </div>
            <div style={{ fontSize: 13, marginBottom: 20 }}>
              Upload a CSV or Excel file to get started
            </div>
            <button className="ds-btn" onClick={() => navigate("/")}>
              <Upload size={14} /> Upload your first dataset
            </button>
          </div>
        ) : (
          <div className="ds-grid">
            {sessions.map(s => (
              <div key={s.id} className="ds-card" onClick={() => handleOpen(s)}>
                <div className="ds-icon">
                  <FileSpreadsheet size={18} color="var(--accent-light)" />
                </div>
                <div className="ds-info">
                  <div className="ds-name">{s.filename}</div>
                  <div className="ds-meta">
                    <span className="ds-stat">
                      <Database size={10} />
                      {(s.rows || 0).toLocaleString()} rows · {s.columns || 0} cols
                    </span>
                    <span className="ds-stat">
                      <BarChart2 size={10} />
                      <HealthBadge score={s.health_score} />
                    </span>
                    <span className="ds-stat">
                      <Clock size={10} />
                      {timeAgo(s.last_accessed)}
                    </span>
                  </div>
                </div>
                <button
                  className="ds-del"
                  onClick={e => handleDelete(e, s.id)}
                  disabled={deleting === s.id}
                  title="Delete dataset"
                >
                  {deleting === s.id
                    ? <Loader2 size={14} style={{ animation: "spin .7s linear infinite" }} />
                    : <Trash2 size={14} />}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </>
  );
}
