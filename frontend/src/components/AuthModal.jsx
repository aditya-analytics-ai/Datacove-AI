/**
 * AuthModal — login / register / forgot-password modal.
 * Only shown when AUTH_ENABLED=True on the backend.
 * Token is stored in localStorage and injected into axios via setAuthToken().
 */
import React, { useState } from "react";
import { Lock, User, Loader2, AlertCircle, FileSpreadsheet, Mail, ArrowLeft } from "lucide-react";
import { authLogin, authRegister, authForgotPassword, setAuthToken } from "../services/api";

export default function AuthModal({ onAuthenticated, backendDown = false }) {
  // mode: "login" | "register" | "forgot" | "forgot_done"
  const [mode,     setMode]     = useState("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [email,    setEmail]    = useState("");
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");
  const [info,     setInfo]     = useState("");

  function switchMode(m) { setMode(m); setError(""); setInfo(""); setFullName(""); setEmail(""); }

  function getErrorMessage(err) {
    const detail = err?.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (typeof detail?.msg === "string") return detail.msg;
    if (Array.isArray(detail)) return detail.map(e => e.msg || JSON.stringify(e)).join(", ");
    return "Authentication failed.";
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(""); setInfo("");

    if (mode === "forgot") {
      if (!username.trim()) { setError("Enter your username."); return; }
      setLoading(true);
      try {
        const res = await authForgotPassword(username);
        setInfo(res?.note ?? "Reset instructions issued. Check your email (or dev_token in API response).");
        setMode("forgot_done");
      } catch (err) {
        setError(getErrorMessage(err));
      } finally { setLoading(false); }
      return;
    }

    if (!username.trim() || !password.trim()) return;
    if (mode === "register") {
      if (!fullName.trim()) { setError("Please enter your full name."); return; }
      if (!email.trim())    { setError("Please enter your email address."); return; }
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { setError("Please enter a valid email address."); return; }
    }
    setLoading(true);
    try {
      const fn  = mode === "login" ? authLogin : authRegister;
      const res = mode === "login"
        ? await fn(username, password)
        : await fn(username, password, fullName, email);
      localStorage.setItem("dc_token", res.token);
      setAuthToken(res.token);
      onAuthenticated(res);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally { setLoading(false); }
  }

  return (
    <div className="am-overlay" role="dialog" aria-modal="true" aria-label={
      mode === "login" ? "Sign in" : mode === "register" ? "Create account" : "Password reset"
    }>
      <div className="am-modal">
        <div className="am-logo">
          <FileSpreadsheet size={24} color="var(--accent)" />
          <span className="am-logo-text">datacove</span>
        </div>

        {mode === "forgot_done" ? (
          <>
            <h2 className="am-title">Check your inbox</h2>
            {info && <div className="am-info"><Mail size={12} />{info}</div>}
            <button className="am-back" onClick={() => switchMode("login")}>
              <ArrowLeft size={12} /> Back to sign in
            </button>
          </>
        ) : (
          <>
            <h2 className="am-title">
              {mode === "login" ? "Sign in" : mode === "register" ? "Create account" : "Reset password"}
            </h2>

            {backendDown && (
              <div style={{
                background: "rgba(245,158,11,0.12)", border: "1px solid rgba(245,158,11,0.3)",
                borderRadius: 8, padding: "8px 12px", marginBottom: 12,
                color: "#f59e0b", fontSize: 12, display: "flex", alignItems: "center", gap: 7
              }} role="alert">
                <span>⚠</span>
                <span>Cannot reach server — make sure the backend is running on port 8000.</span>
              </div>
            )}

            <form className="am-form" onSubmit={handleSubmit} noValidate>
              {mode === "register" && (
                <div className="am-field">
                  <User size={13} className="am-icon" aria-hidden="true" />
                  <input
                    className="am-input"
                    type="text"
                    placeholder="Full name"
                    aria-label="Full name"
                    value={fullName}
                    onChange={e => setFullName(e.target.value)}
                    autoComplete="name"
                  />
                </div>
              )}

              <div className="am-field">
                <User size={13} className="am-icon" aria-hidden="true" />
                <input
                  id="am-username"
                  className="am-input"
                  type="text"
                  placeholder="Username"
                  aria-label="Username"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  autoFocus
                  autoComplete="username"
                />
              </div>

              {mode === "register" && (
                <div className="am-field">
                  <Mail size={13} className="am-icon" aria-hidden="true" />
                  <input
                    className="am-input"
                    type="email"
                    placeholder="Email address"
                    aria-label="Email address"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    autoComplete="email"
                  />
                </div>
              )}

              {mode !== "forgot" && (
                <div className="am-field">
                  <Lock size={13} className="am-icon" aria-hidden="true" />
                  <input
                    id="am-password"
                    className="am-input"
                    type="password"
                    placeholder="Password"
                    aria-label="Password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    autoComplete={mode === "login" ? "current-password" : "new-password"}
                  />
                </div>
              )}

              {error && (
                <div className="am-error" role="alert">
                  <AlertCircle size={12} aria-hidden="true" />{error}
                </div>
              )}

              <button className="am-submit" type="submit" disabled={loading}
                aria-label={mode === "login" ? "Sign in" : mode === "register" ? "Create account" : "Send reset link"}>
                {loading ? <Loader2 size={14} className="spin" aria-hidden="true" /> : null}
                {mode === "login" ? "Sign in" : mode === "register" ? "Create account" : "Send reset link"}
              </button>
            </form>

            {mode === "login" && (
              <button className="am-switch-btn" style={{ alignSelf: "flex-end", fontSize: 11 }}
                onClick={() => switchMode("forgot")}>
                Forgot password?
              </button>
            )}

            <p className="am-switch">
              {mode === "login" ? "No account? " : mode === "register" ? "Already have one? " : "Remember it? "}
              <button className="am-switch-btn"
                onClick={() => switchMode(mode === "login" ? "register" : "login")}>
                {mode === "login" ? "Register" : "Sign in"}
              </button>
            </p>
          </>
        )}
      </div>

      <style>{`
        .am-overlay{position:fixed;inset:0;background:rgba(0,0,0,.7);display:flex;align-items:center;justify-content:center;z-index:10000}
        .am-modal{background:var(--surface-1);border:1px solid var(--border);border-radius:16px;padding:32px;width:360px;display:flex;flex-direction:column;gap:20px}
        .am-logo{display:flex;align-items:center;gap:8px}
        .am-logo-text{font-size:20px;font-weight:800;letter-spacing:-.02em;color:var(--text-0)}
        .am-title{font-size:18px;font-weight:700;color:var(--text-0);margin:0}
        .am-form{display:flex;flex-direction:column;gap:12px}
        .am-field{position:relative;display:flex;align-items:center}
        .am-icon{position:absolute;left:12px;color:var(--text-3);pointer-events:none}
        .am-input{width:100%;padding:9px 12px 9px 32px;border-radius:8px;border:1px solid var(--border);background:var(--surface-2);color:var(--text-0);font-size:13px;outline:none}
        .am-input:focus{border-color:var(--accent)}
        .am-error{display:flex;align-items:center;gap:6px;font-size:12px;color:#ef4444;background:rgba(239,68,68,.1);padding:7px 10px;border-radius:6px}
        .am-info{display:flex;align-items:flex-start;gap:6px;font-size:12px;color:var(--green);background:rgba(34,197,94,.1);padding:10px 12px;border-radius:6px;line-height:1.5}
        .am-submit{padding:10px;border-radius:8px;border:none;background:var(--accent);color:#fff;font-size:13px;font-weight:700;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:6px;transition:background 0.15s}
        .am-submit:hover:not(:disabled){background:var(--accent-hover)}
        .am-submit:disabled{opacity:.55;cursor:not-allowed}
        .am-switch{font-size:12px;color:var(--text-2);text-align:center;margin:0}
        .am-switch-btn{background:none;border:none;color:var(--accent);cursor:pointer;font-size:12px;font-weight:600;padding:0}
        .am-back{display:inline-flex;align-items:center;gap:5px;background:none;border:1px solid var(--border);border-radius:6px;padding:7px 12px;color:var(--text-2);font-size:12px;cursor:pointer}
        .am-back:hover{color:var(--text-0);border-color:var(--border-2)}
        @keyframes spin{to{transform:rotate(360deg)}}.spin{animation:spin .7s linear infinite}
      `}</style>
    </div>
  );
}
