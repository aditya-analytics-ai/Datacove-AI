/**
 * AdminPage — platform management console (admin role only).
 *
 * Sections:
 *   - Platform stats cards
 *   - User management table (activate/deactivate, role change)
 *   - Audit log (paginated, filterable)
 */
import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  Users, ShieldCheck, Activity, ArrowLeft,
  RefreshCw, CheckCircle2, XCircle, Loader2,
  AlertCircle, ChevronLeft, ChevronRight, ShieldAlert,
} from "lucide-react";
import {
  fetchAdminStats, fetchAdminUsers, setUserRole,
  setUserActive, fetchAuditLog,
} from "../services/api";
import { SkeletonStats, SkeletonTable } from "../components/Skeleton";

// ── Stat card ─────────────────────────────────────────────────────────────────
function StatCard({ label, value, icon: Icon, color }) {
  return (
    <div style={{ background: "var(--surface-1)", border: "1px solid var(--border)",
      borderRadius: "var(--radius-lg)", padding: "18px 20px",
      display: "flex", alignItems: "center", gap: 14 }}>
      <div style={{ width: 40, height: 40, borderRadius: "var(--radius-md)",
        background: `${color}1a`, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Icon size={18} color={color} />
      </div>
      <div>
        <div style={{ fontSize: 22, fontWeight: 800, color: "var(--text-0)" }}>{value ?? "—"}</div>
        <div style={{ fontSize: 11, color: "var(--text-2)", marginTop: 1 }}>{label}</div>
      </div>
    </div>
  );
}

// ── Role badge ────────────────────────────────────────────────────────────────
function RoleBadge({ role }) {
  const isAdmin = role === "admin";
  return (
    <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 8px",
      borderRadius: 99, letterSpacing: ".04em",
      background: isAdmin ? "rgba(99,102,241,.12)" : "var(--surface-3)",
      color: isAdmin ? "var(--accent-light)" : "var(--text-2)",
      border: `1px solid ${isAdmin ? "rgba(99,102,241,.25)" : "var(--border)"}` }}>
      {role?.toUpperCase()}
    </span>
  );
}

export default function AdminPage({ userRole }) {
  const navigate = useNavigate();

  // ── Role guard — non-admins see an access-denied screen ──────────────────
  if (userRole !== "admin") {
    return (
      <div style={{ minHeight: "100vh", background: "var(--bg)", display: "flex",
        alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 16 }}>
        <ShieldAlert size={48} color="var(--red)" style={{ opacity: 0.7 }} />
        <div style={{ fontSize: 18, fontWeight: 700, color: "var(--text-0)" }}>Access Denied</div>
        <div style={{ fontSize: 13, color: "var(--text-2)" }}>Admin role required to view this page.</div>
        <button onClick={() => navigate("/")}
          style={{ marginTop: 8, padding: "8px 18px", background: "var(--surface-2)",
            border: "1px solid var(--border)", borderRadius: "var(--radius-md)",
            color: "var(--text-1)", cursor: "pointer", fontSize: 13 }}>
          Go Home
        </button>
      </div>
    );
  }

  const [tab, setTab]         = useState("users");
  const [stats, setStats]     = useState(null);
  const [users, setUsers]     = useState([]);
  const [userTotal, setUserTotal] = useState(0);
  const [userPage, setUserPage]   = useState(1);
  const [auditLog, setAuditLog]   = useState([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditPage, setAuditPage]   = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState("");
  const [busy, setBusy]       = useState({});

  const PAGE_SIZE = 20;

  const loadStats = useCallback(async () => {
    try { setStats(await fetchAdminStats()); } catch { /* non-fatal */ }
  }, []);

  const loadUsers = useCallback(async (page = 1) => {
    setLoading(true);
    try {
      const res = await fetchAdminUsers(page, PAGE_SIZE);
      setUsers(res.users || []);
      setUserTotal(res.total || 0);
      setUserPage(page);
    } catch (e) {
      setError("Failed to load users.");
    } finally { setLoading(false); }
  }, []);

  const loadAudit = useCallback(async (page = 1) => {
    setLoading(true);
    try {
      const res = await fetchAuditLog(page, PAGE_SIZE);
      setAuditLog(res.events || []);
      setAuditTotal(res.total || 0);
      setAuditPage(page);
    } catch (e) {
      setError("Failed to load audit log.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    loadStats();
    loadUsers(1);
  }, [loadStats, loadUsers]);

  useEffect(() => {
    if (tab === "audit") loadAudit(1);
  }, [tab, loadAudit]);

  const toggleActive = async (user) => {
    setBusy(b => ({ ...b, [user.id]: true }));
    try {
      await setUserActive(user.id, !user.is_active);
      setUsers(us => us.map(u => u.id === user.id ? { ...u, is_active: !u.is_active } : u));
      loadStats();
    } catch { setError("Action failed."); }
    finally { setBusy(b => ({ ...b, [user.id]: false })); }
  };

  const toggleRole = async (user) => {
    const newRole = user.role === "admin" ? "user" : "admin";
    if (!window.confirm(`Change ${user.username} to ${newRole}?`)) return;
    setBusy(b => ({ ...b, [`role-${user.id}`]: true }));
    try {
      await setUserRole(user.id, newRole);
      setUsers(us => us.map(u => u.id === user.id ? { ...u, role: newRole } : u));
    } catch { setError("Role change failed."); }
    finally { setBusy(b => ({ ...b, [`role-${user.id}`]: false })); }
  };

  const totalUserPages  = Math.ceil(userTotal / PAGE_SIZE);
  const totalAuditPages = Math.ceil(auditTotal / PAGE_SIZE);

  const css = `
    .adm-page  { min-height:100vh; background:var(--bg); padding:32px; }
    .adm-back  { display:inline-flex; align-items:center; gap:6px; font-size:12px;
      color:var(--text-2); cursor:pointer; border:none; background:none; margin-bottom:24px; padding:0; }
    .adm-back:hover { color:var(--text-0); }
    .adm-title { font-size:20px; font-weight:700; color:var(--text-0); margin-bottom:4px; }
    .adm-sub   { font-size:13px; color:var(--text-2); margin-bottom:28px; }
    .adm-stats { display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr));
      gap:12px; margin-bottom:28px; }
    .adm-tabs  { display:flex; gap:0; border-bottom:1px solid var(--border); margin-bottom:20px; }
    .adm-tab   { padding:9px 18px; font-size:12px; font-weight:600; cursor:pointer;
      border:none; background:none; color:var(--text-2); border-bottom:2px solid transparent; margin-bottom:-1px; }
    .adm-tab:hover { color:var(--text-0); }
    .adm-tab--on { color:var(--accent); border-bottom-color:var(--accent); }
    .adm-table { width:100%; border-collapse:collapse; font-size:12px; }
    .adm-table th { text-align:left; font-size:10px; font-weight:700; color:var(--text-3);
      text-transform:uppercase; letter-spacing:.06em; padding:8px 12px;
      border-bottom:1px solid var(--border); }
    .adm-table td { padding:10px 12px; border-bottom:1px solid var(--border);
      color:var(--text-1); }
    .adm-table tr:hover td { background:var(--surface-2); }
    .adm-btn   { display:inline-flex; align-items:center; gap:4px; padding:4px 10px;
      border-radius:var(--radius-sm); border:1px solid var(--border); background:var(--surface-3);
      color:var(--text-1); font-size:11px; cursor:pointer; }
    .adm-btn:hover { background:var(--surface-2); color:var(--text-0); }
    .adm-btn-danger:hover { border-color:var(--red); color:var(--red);
      background:var(--red-dim); }
    .adm-pager { display:flex; align-items:center; gap:8px; margin-top:16px;
      font-size:12px; color:var(--text-2); }
    .adm-pager button { padding:4px 10px; border-radius:var(--radius-sm);
      border:1px solid var(--border); background:var(--surface-2);
      color:var(--text-1); cursor:pointer; }
    .adm-pager button:disabled { opacity:.3; cursor:default; }
    .adm-err  { display:flex; align-items:center; gap:6px; font-size:12px; color:var(--red);
      margin-bottom:16px; }
    .adm-time { font-family:'JetBrains Mono',monospace; font-size:10px; color:var(--text-3); }
  `;

  return (
    <>
      <style>{css}</style>
      <div className="adm-page">
        <button className="adm-back" onClick={() => navigate(-1)}>
          <ArrowLeft size={13} /> Back
        </button>
        <div className="adm-title">Admin Console</div>
        <div className="adm-sub">Platform management — visible to admins only</div>

        {error && <div className="adm-err"><AlertCircle size={12} />{error}</div>}

        {/* Stats */}
        {stats ? (
          <div className="adm-stats">
            <StatCard label="Total users"       value={stats.users?.total}        icon={Users}      color="#6366f1" />
            <StatCard label="Active users"      value={stats.users?.active}       icon={CheckCircle2} color="#22c55e" />
            <StatCard label="Admins"            value={stats.users?.admins}       icon={ShieldCheck} color="#f59e0b" />
            <StatCard label="Logins (24h)"      value={stats.activity?.logins_last_24h} icon={Activity} color="#0891b2" />
            <StatCard label="Active sessions"   value={stats.sessions?.active_in_memory} icon={Activity} color="#7c3aed" />
          </div>
        ) : (
          <SkeletonStats count={5} />
        )}

        {/* Tabs */}
        <div className="adm-tabs">
          {["users", "audit"].map(t => (
            <button key={t} className={`adm-tab${tab === t ? " adm-tab--on" : ""}`}
              onClick={() => setTab(t)}>
              {t === "users" ? "Users" : "Audit Log"}
            </button>
          ))}
          <button className="adm-tab" style={{ marginLeft: "auto" }}
            onClick={() => { loadStats(); tab === "users" ? loadUsers(userPage) : loadAudit(auditPage); }}>
            <RefreshCw size={11} style={{ marginRight: 4 }} />Refresh
          </button>
        </div>

        {loading && (
          <SkeletonTable rows={5} cols={7} />
        )}

        {/* Users table */}
        {!loading && tab === "users" && (
          <>
            <table className="adm-table">
              <thead>
                <tr>
                  <th>Username</th><th>Full Name</th><th>Email</th><th>Role</th><th>Status</th>
                  <th>Created</th><th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.id}>
                    <td style={{ color: "var(--text-0)", fontWeight: 500 }}>{u.username}</td>
                    <td style={{ color: "var(--text-1)" }}>{u.full_name || <span style={{ color: "var(--text-3)" }}>—</span>}</td>
                    <td style={{ color: "var(--text-2)", fontSize: 11 }}>{u.email || <span style={{ color: "var(--text-3)" }}>—</span>}</td>
                    <td><RoleBadge role={u.role} /></td>
                    <td>
                      {u.is_active
                        ? <span style={{ color: "var(--green)", fontSize: 11 }}>● Active</span>
                        : <span style={{ color: "var(--red)", fontSize: 11 }}>● Inactive</span>}
                    </td>
                    <td className="adm-time">
                      {u.created_at ? new Date(u.created_at * 1000).toLocaleDateString() : "—"}
                    </td>
                    <td style={{ display: "flex", gap: 6 }}>
                      <button className={`adm-btn${u.is_active ? " adm-btn-danger" : ""}`}
                        disabled={busy[u.id]}
                        onClick={() => toggleActive(u)}>
                        {busy[u.id]
                          ? <Loader2 size={10} style={{ animation: "spin .7s linear infinite" }} />
                          : u.is_active ? <XCircle size={10} /> : <CheckCircle2 size={10} />}
                        {u.is_active ? "Deactivate" : "Activate"}
                      </button>
                      <button className="adm-btn" disabled={busy[`role-${u.id}`]}
                        onClick={() => toggleRole(u)}>
                        {busy[`role-${u.id}`]
                          ? <Loader2 size={10} style={{ animation: "spin .7s linear infinite" }} />
                          : <ShieldCheck size={10} />}
                        {u.role === "admin" ? "→ User" : "→ Admin"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="adm-pager">
              <button disabled={userPage <= 1} onClick={() => loadUsers(userPage - 1)}>
                <ChevronLeft size={12} />
              </button>
              <span>Page {userPage} of {totalUserPages || 1}</span>
              <button disabled={userPage >= totalUserPages} onClick={() => loadUsers(userPage + 1)}>
                <ChevronRight size={12} />
              </button>
              <span style={{ marginLeft: "auto" }}>{userTotal} total</span>
            </div>
          </>
        )}

        {/* Audit log */}
        {!loading && tab === "audit" && (
          <>
            <table className="adm-table">
              <thead>
                <tr><th>Time</th><th>User</th><th>Action</th><th>Resource</th><th>Detail</th><th>IP</th></tr>
              </thead>
              <tbody>
                {auditLog.map(e => (
                  <tr key={e.id}>
                    <td className="adm-time">
                      {new Date(e.ts * 1000).toLocaleString()}
                    </td>
                    <td style={{ fontWeight: 500 }}>{e.username}</td>
                    <td><code style={{ fontSize: 10, color: "var(--accent-light)" }}>{e.action}</code></td>
                    <td style={{ fontSize: 11, maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis" }}>
                      {e.resource || "—"}
                    </td>
                    <td style={{ fontSize: 11, color: "var(--text-3)" }}>{e.detail || "—"}</td>
                    <td className="adm-time">{e.ip_address || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="adm-pager">
              <button disabled={auditPage <= 1} onClick={() => loadAudit(auditPage - 1)}>
                <ChevronLeft size={12} />
              </button>
              <span>Page {auditPage} of {totalAuditPages || 1}</span>
              <button disabled={auditPage >= totalAuditPages} onClick={() => loadAudit(auditPage + 1)}>
                <ChevronRight size={12} />
              </button>
              <span style={{ marginLeft: "auto" }}>{auditTotal} total events</span>
            </div>
          </>
        )}
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </>
  );
}
