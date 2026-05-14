/**
 * SharePanel — Workspace sharing & collaboration panel.
 * Create share links (view / fork), list active links, revoke them.
 * Designed to be used as a tab or modal inside the Dashboard.
 */
import React, { useState, useEffect, useCallback } from "react";
import {
  Link2, Copy, Trash2, RefreshCw, Eye, GitFork,
  Clock, AlertCircle, CheckCircle2, Loader2, Plus,
} from "lucide-react";
import { createShare, listShares, revokeShare } from "../services/api";

function timeAgo(ts) {
  if (!ts) return "—";
  const diff = Date.now() / 1000 - ts;
  if (diff < 60)    return "just now";
  if (diff < 3600)  return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function SharePanel({ sessionId }) {
  const [shares, setShares]       = useState([]);
  const [loading, setLoading]     = useState(true);
  const [creating, setCreating]   = useState(false);
  const [revoking, setRevoking]   = useState(null);
  const [copied, setCopied]       = useState(null);
  const [error, setError]         = useState("");
  const [perm, setPerm]           = useState("view");
  const [expiry, setExpiry]       = useState("7d");

  const load = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const res = await listShares(sessionId);
      setShares(res.links || []);
    } catch {
      setError("Could not load share links.");
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    setCreating(true);
    setError("");
    try {
      const expiryMap = { "1d": 86400, "7d": 604800, "30d": 2592000, never: null };
      const res = await createShare(sessionId, {
        permission: perm,
        expires_in: expiryMap[expiry],
      });
      setShares(s => [res, ...s]);
    } catch {
      setError("Failed to create share link.");
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (token) => {
    setRevoking(token);
    try {
      await revokeShare(token);
      setShares(s => s.filter(x => x.token !== token));
    } catch {
      setError("Failed to revoke link.");
    } finally {
      setRevoking(null);
    }
  };

  const handleCopy = (token) => {
    const url = `${window.location.origin}/share/${token}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopied(token);
      setTimeout(() => setCopied(null), 2000);
    });
  };

  const css = `
    .sh-wrap { padding: 16px; }
    .sh-create { display: flex; align-items: flex-end; gap: 8px;
      background: var(--surface-2); border-radius: var(--radius-md);
      padding: 14px; margin-bottom: 16px; flex-wrap: wrap; }
    .sh-field { display: flex; flex-direction: column; gap: 4px; }
    .sh-label { font-size: 10px; font-weight: 600; color: var(--text-2);
      text-transform: uppercase; letter-spacing: .06em; }
    .sh-select { background: var(--surface-3); border: 1px solid var(--border);
      border-radius: var(--radius-sm); color: var(--text-0); padding: 6px 10px;
      font-size: 12px; cursor: pointer; outline: none; }
    .sh-select:focus { border-color: var(--accent); }
    .sh-btn { display: inline-flex; align-items: center; gap: 6px;
      padding: 7px 14px; background: var(--accent); color: #fff;
      border: none; border-radius: var(--radius-sm); font-size: 12px;
      font-weight: 500; cursor: pointer; white-space: nowrap; }
    .sh-btn:hover { opacity: .9; }
    .sh-btn:disabled { opacity: .4; cursor: default; }
    .sh-list { display: grid; gap: 8px; }
    .sh-card { background: var(--surface-1); border: 1px solid var(--border);
      border-radius: var(--radius-md); padding: 12px 14px;
      display: flex; align-items: center; gap: 10px; }
    .sh-card-icon { flex-shrink: 0; }
    .sh-card-info { flex: 1; min-width: 0; }
    .sh-token { font-size: 12px; font-weight: 500; color: var(--accent-light);
      font-family: 'JetBrains Mono', monospace; white-space: nowrap;
      overflow: hidden; text-overflow: ellipsis; }
    .sh-meta { display: flex; gap: 10px; margin-top: 4px; flex-wrap: wrap; }
    .sh-badge { font-size: 10px; font-weight: 600; padding: 1px 7px;
      border-radius: 99px; border: 1px solid; }
    .sh-badge-view { color: #0891b2; border-color: rgba(8,145,178,.3);
      background: rgba(8,145,178,.08); }
    .sh-badge-fork { color: #7c3aed; border-color: rgba(124,58,237,.3);
      background: rgba(124,58,237,.08); }
    .sh-stat { font-size: 10px; color: var(--text-2);
      display: flex; align-items: center; gap: 3px; }
    .sh-actions { display: flex; gap: 4px; }
    .sh-ico-btn { padding: 5px; border-radius: var(--radius-sm);
      border: none; background: transparent; cursor: pointer;
      display: flex; align-items: center; color: var(--text-2); }
    .sh-ico-btn:hover { background: var(--surface-3); color: var(--text-0); }
    .sh-ico-btn-danger:hover { background: rgba(239,68,68,.1); color: #ef4444; }
    .sh-err { display: flex; align-items: center; gap: 6px; font-size: 12px;
      color: var(--red); margin-bottom: 12px; }
    .sh-empty { text-align: center; padding: 32px; color: var(--text-3); font-size: 13px; }
  `;

  return (
    <>
      <style>{css}</style>
      <div className="sh-wrap">
        <div className="sh-create">
          <div className="sh-field">
            <span className="sh-label">Permission</span>
            <select className="sh-select" value={perm} onChange={e => setPerm(e.target.value)}>
              <option value="view">View only</option>
              <option value="fork">Fork (copy)</option>
            </select>
          </div>
          <div className="sh-field">
            <span className="sh-label">Expires</span>
            <select className="sh-select" value={expiry} onChange={e => setExpiry(e.target.value)}>
              <option value="1d">1 day</option>
              <option value="7d">7 days</option>
              <option value="30d">30 days</option>
              <option value="never">Never</option>
            </select>
          </div>
          <button className="sh-btn" onClick={handleCreate} disabled={creating}>
            {creating
              ? <Loader2 size={13} style={{ animation: "spin .7s linear infinite" }} />
              : <Plus size={13} />}
            Create link
          </button>
        </div>

        {error && (
          <div className="sh-err"><AlertCircle size={12} /> {error}</div>
        )}

        {loading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: 24 }}>
            <Loader2 size={16} style={{ animation: "spin .7s linear infinite", color: "var(--text-3)" }} />
          </div>
        ) : shares.length === 0 ? (
          <div className="sh-empty">No active share links</div>
        ) : (
          <div className="sh-list">
            {shares.map(s => (
              <div key={s.token} className="sh-card">
                <div className="sh-card-icon">
                  {s.permission === "fork"
                    ? <GitFork size={14} color="var(--text-2)" />
                    : <Eye size={14} color="var(--text-2)" />}
                </div>
                <div className="sh-card-info">
                  <div className="sh-token">{s.token}</div>
                  <div className="sh-meta">
                    <span className={`sh-badge sh-badge-${s.permission}`}>{s.permission}</span>
                    <span className="sh-stat"><Link2 size={9} /> {s.access_count || 0} uses</span>
                    <span className="sh-stat"><Clock size={9} /> created {timeAgo(s.created_at)}</span>
                    {s.expires_at && (
                      <span className="sh-stat">expires {timeAgo(s.expires_at - Date.now() / 1000 + Date.now() / 1000)}</span>
                    )}
                  </div>
                </div>
                <div className="sh-actions">
                  <button
                    className="sh-ico-btn"
                    title="Copy link"
                    onClick={() => handleCopy(s.token)}
                  >
                    {copied === s.token
                      ? <CheckCircle2 size={14} color="#22c55e" />
                      : <Copy size={14} />}
                  </button>
                  <button
                    className="sh-ico-btn sh-ico-btn-danger"
                    title="Revoke link"
                    onClick={() => handleRevoke(s.token)}
                    disabled={revoking === s.token}
                  >
                    {revoking === s.token
                      ? <Loader2 size={14} style={{ animation: "spin .7s linear infinite" }} />
                      : <Trash2 size={14} />}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </>
  );
}
