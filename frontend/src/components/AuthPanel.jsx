/**
 * AuthPanel.jsx — Panel 1: Sign In / Register
 * 
 * "Terminal Precision" aesthetic with emerald teal accents.
 * Centered card layout with step indicator.
 */
import React, { useState } from "react";
import { 
  Lock, User, Loader2, AlertCircle, Mail, ArrowLeft, Eye, EyeOff 
} from "lucide-react";
import { authLogin, authRegister, authForgotPassword, setAuthToken } from "../services/api";

// ══════════════════════════════════════════════════════════════════════════════
// STYLES
// ══════════════════════════════════════════════════════════════════════════════

const STYLES = `
  .auth-root {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 40px 20px;
    min-height: calc(100vh - 88px);
  }

  .auth-card {
    width: 100%;
    max-width: 440px;
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: var(--radius-xl);
    padding: 40px;
    box-shadow: var(--shadow-lg);
  }

  .auth-logo {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    margin-bottom: 12px;
  }

  .auth-logo-icon {
    width: 40px;
    height: 40px;
    border-radius: var(--radius-md);
    background: linear-gradient(135deg, var(--accent) 0%, var(--secondary) 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 4px 16px rgba(0,212,170,0.3);
  }

  .auth-logo-text {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 800;
    font-size: 24px;
    color: var(--text-0);
    letter-spacing: -0.03em;
  }

  .auth-tagline {
    text-align: center;
    font-size: 13px;
    color: var(--text-2);
    margin-bottom: 32px;
    font-family: 'JetBrains Mono', monospace;
  }

  .auth-title {
    font-size: 22px;
    font-weight: 700;
    color: var(--text-0);
    margin: 0 0 6px;
    text-align: center;
  }

  .auth-subtitle {
    font-size: 13px;
    color: var(--text-2);
    margin: 0 0 28px;
    text-align: center;
  }

  /* Form */
  .auth-form {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .auth-field {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .auth-label {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-2);
  }

  .auth-input-wrap {
    position: relative;
    display: flex;
    align-items: center;
  }

  .auth-input-icon {
    position: absolute;
    left: 14px;
    color: var(--text-3);
    pointer-events: none;
    transition: color 0.2s ease;
  }

  .auth-input {
    width: 100%;
    padding: 12px 14px 12px 42px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    color: var(--text-0);
    font-size: 14px;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    outline: none;
  }

  .auth-input:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-dim);
  }

  .auth-input:focus + .auth-input-icon,
  .auth-input-wrap:focus-within .auth-input-icon {
    color: var(--accent);
  }

  .auth-input::placeholder { color: var(--text-3); }

  .auth-input-wrap--password .auth-input {
    padding-right: 44px;
  }

  .auth-password-toggle {
    position: absolute;
    right: 12px;
    background: none;
    border: none;
    padding: 4px;
    color: var(--text-3);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 4px;
    transition: color 0.2s ease;
  }

  .auth-password-toggle:hover { color: var(--text-1); }

  /* Error */
  .auth-error {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 12px 14px;
    background: rgba(239,68,68,0.1);
    border: 1px solid rgba(239,68,68,0.25);
    border-radius: var(--radius-md);
    font-size: 13px;
    color: #fca5a5;
  }

  .auth-error svg { flex-shrink: 0; margin-top: 1px; }

  /* Info */
  .auth-info {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 12px 14px;
    background: rgba(0,212,170,0.1);
    border: 1px solid rgba(0,212,170,0.25);
    border-radius: var(--radius-md);
    font-size: 13px;
    color: var(--accent);
  }

  /* Backend down warning */
  .auth-warning {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 14px;
    background: rgba(245,158,11,0.1);
    border: 1px solid rgba(245,158,11,0.25);
    border-radius: var(--radius-md);
    font-size: 13px;
    color: var(--amber);
    margin-bottom: 20px;
  }

  /* Submit button */
  .auth-submit {
    width: 100%;
    padding: 14px 24px;
    background: linear-gradient(135deg, var(--accent) 0%, var(--secondary) 100%);
    border: none;
    border-radius: var(--radius-md);
    color: var(--bg);
    font-size: 14px;
    font-weight: 700;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    box-shadow: 0 4px 16px rgba(0,212,170,0.25);
    margin-top: 8px;
  }

  .auth-submit:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0,212,170,0.35);
  }

  .auth-submit:active:not(:disabled) {
    transform: translateY(0);
  }

  .auth-submit:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  /* Links */
  .auth-link-row {
    display: flex;
    justify-content: flex-end;
    margin-top: -8px;
  }

  .auth-link {
    background: none;
    border: none;
    font-size: 12px;
    color: var(--text-2);
    cursor: pointer;
    padding: 4px 0;
    transition: color 0.2s ease;
  }

  .auth-link:hover { color: var(--accent); }

  /* Toggle */
  .auth-toggle {
    text-align: center;
    margin-top: 24px;
    padding-top: 24px;
    border-top: 1px solid var(--border);
    font-size: 13px;
    color: var(--text-2);
  }

  .auth-toggle-btn {
    background: none;
    border: none;
    color: var(--accent);
    font-weight: 600;
    cursor: pointer;
    font-size: 13px;
    padding: 0;
  }

  .auth-toggle-btn:hover { color: var(--accent-light); }

  /* Back button */
  .auth-back {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: none;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 10px 16px;
    color: var(--text-2);
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s ease;
    margin-bottom: 24px;
  }

  .auth-back:hover {
    border-color: var(--border-2);
    color: var(--text-1);
    background: var(--surface-2);
  }
`;

// ══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ══════════════════════════════════════════════════════════════════════════════

export default function AuthPanel({ onAuthenticated, backendDown: propBackendDown }) {
  const [mode,     setMode]     = useState('login');  // login | register | forgot | forgot_done
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [email,    setEmail]    = useState('');
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState('');
  const [info,     setInfo]     = useState('');
  const [showPwd,  setShowPwd]  = useState(false);
  const [backendDown, setBackendDown] = useState(propBackendDown || false);

  function switchMode(m) {
    setMode(m);
    setError('');
    setInfo('');
    setFullName('');
    setEmail('');
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setInfo('');

    // Validation
    if (mode === 'login') {
      if (!username.trim() || !password.trim()) {
        setError('Please enter your username and password.');
        return;
      }
    } else if (mode === 'register') {
      if (!fullName.trim()) { setError('Please enter your full name.'); return; }
      if (!username.trim()) { setError('Please enter a username.'); return; }
      if (!email.trim()) { setError('Please enter your email.'); return; }
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        setError('Please enter a valid email address.');
        return;
      }
      if (!password.trim() || password.length < 6) {
        setError('Password must be at least 6 characters.');
        return;
      }
    } else if (mode === 'forgot') {
      if (!username.trim()) { setError('Please enter your username.'); return; }
    }

    setLoading(true);

    try {
      if (mode === 'forgot') {
        const res = await authForgotPassword(username);
        setInfo(res?.note || 'Reset instructions sent. Check your email.');
        setMode('forgot_done');
      } else {
        const fn = mode === 'login' ? authLogin : authRegister;
        const res = mode === 'login'
          ? await fn(username, password)
          : await fn(username, password, fullName, email);
        
        // Store token
        localStorage.setItem('dc_token', res.token);
        if (res.refresh_token) {
          localStorage.setItem('dc_refresh', res.refresh_token);
        }
        setAuthToken(res.token);
        
        // Notify parent
        onAuthenticated(res);
      }
    } catch (err) {
      if (!err?.response) {
        setBackendDown(true);
        setError('Cannot reach server. Make sure the backend is running on port 8000.');
      } else {
        setError(err.response?.data?.detail || 'Authentication failed. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <style>{STYLES}</style>
      <div className="auth-root">
        <div className="auth-card">
          
          {/* Logo */}
          <div className="auth-logo">
            <div className="auth-logo-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <rect x="3" y="3" width="7" height="7" rx="1.5" fill="white"/>
                <rect x="14" y="3" width="7" height="7" rx="1.5" fill="white" opacity="0.6"/>
                <rect x="3" y="14" width="7" height="7" rx="1.5" fill="white" opacity="0.6"/>
                <rect x="14" y="14" width="7" height="7" rx="1.5" fill="white"/>
              </svg>
            </div>
            <span className="auth-logo-text">datacove</span>
          </div>
          <p className="auth-tagline">AI-powered data cleaning</p>

          {/* Forgot Done State */}
          {mode === 'forgot_done' ? (
            <>
              <h1 className="auth-title">Check your inbox</h1>
              <p className="auth-subtitle">We've sent password reset instructions</p>
              {info && <div className="auth-info"><Mail size={16} /><span>{info}</span></div>}
              <button className="auth-back" onClick={() => switchMode('login')}>
                <ArrowLeft size={14} /> Back to sign in
              </button>
            </>
          ) : (
            <>
              <h1 className="auth-title">
                {mode === 'login' ? 'Welcome back' : mode === 'register' ? 'Create your account' : 'Reset your password'}
              </h1>
              <p className="auth-subtitle">
                {mode === 'login' ? 'Sign in to continue to Datacove' : 
                 mode === 'register' ? 'Get started with your free account' : 
                 'Enter your username to receive reset instructions'}
              </p>

              {/* Backend down warning */}
              {(backendDown || propBackendDown) && (
                <div className="auth-warning">
                  <AlertCircle size={16} />
                  <span>Cannot reach server — make sure the backend is running on port 8000.</span>
                </div>
              )}

              <form className="auth-form" onSubmit={handleSubmit} noValidate>
                
                {/* Register: Full Name */}
                {mode === 'register' && (
                  <div className="auth-field">
                    <label className="auth-label">Full Name</label>
                    <div className="auth-input-wrap">
                      <User size={16} className="auth-input-icon" />
                      <input
                        className="auth-input"
                        type="text"
                        placeholder="Jane Smith"
                        value={fullName}
                        onChange={e => setFullName(e.target.value)}
                        autoComplete="name"
                        autoFocus
                      />
                    </div>
                  </div>
                )}

                {/* Username */}
                <div className="auth-field">
                  <label className="auth-label">Username</label>
                  <div className="auth-input-wrap">
                    <User size={16} className="auth-input-icon" />
                    <input
                      className="auth-input"
                      type="text"
                      placeholder="username"
                      value={username}
                      onChange={e => setUsername(e.target.value)}
                      autoComplete="username"
                      autoFocus={mode !== 'register'}
                    />
                  </div>
                </div>

                {/* Register: Email */}
                {mode === 'register' && (
                  <div className="auth-field">
                    <label className="auth-label">Email</label>
                    <div className="auth-input-wrap">
                      <Mail size={16} className="auth-input-icon" />
                      <input
                        className="auth-input"
                        type="email"
                        placeholder="jane@company.com"
                        value={email}
                        onChange={e => setEmail(e.target.value)}
                        autoComplete="email"
                      />
                    </div>
                  </div>
                )}

                {/* Password */}
                {mode !== 'forgot' && (
                  <div className="auth-field">
                    <label className="auth-label">Password</label>
                    <div className="auth-input-wrap auth-input-wrap--password">
                      <Lock size={16} className="auth-input-icon" style={{ left: 14 }} />
                      <input
                        className="auth-input"
                        type={showPwd ? 'text' : 'password'}
                        placeholder="••••••••"
                        value={password}
                        onChange={e => setPassword(e.target.value)}
                        autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                      />
                      <button 
                        type="button" 
                        className="auth-password-toggle"
                        onClick={() => setShowPwd(s => !s)}
                        tabIndex={-1}
                      >
                        {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>
                  </div>
                )}

                {/* Error */}
                {error && (
                  <div className="auth-error">
                    <AlertCircle size={16} />
                    <span>{error}</span>
                  </div>
                )}

                {/* Forgot password link */}
                {mode === 'login' && (
                  <div className="auth-link-row">
                    <button type="button" className="auth-link" onClick={() => switchMode('forgot')}>
                      Forgot password?
                    </button>
                  </div>
                )}

                {/* Submit */}
                <button type="submit" className="auth-submit" disabled={loading}>
                  {loading ? (
                    <Loader2 size={16} className="spin" />
                  ) : null}
                  {mode === 'login' ? 'Sign in' : mode === 'register' ? 'Create account' : 'Send reset link'}
                </button>
              </form>

              {/* Toggle */}
              <div className="auth-toggle">
                {mode === 'login' ? "Don't have an account? " : "Already have an account? "}
                <button className="auth-toggle-btn" onClick={() => switchMode(mode === 'login' ? 'register' : 'login')}>
                  {mode === 'login' ? 'Create one' : 'Sign in'}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
