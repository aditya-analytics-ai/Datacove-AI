/**
 * App.jsx — v6 with dark/light theme support
 */
import React, { useState, useEffect, lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import UploadPage from "./pages/UploadPage";
import Dashboard  from "./pages/Dashboard";
import AuthModal     from "./components/AuthModal";
import DatasetsPage  from "./pages/DatasetsPage";
import BillingPage   from "./pages/BillingPage";
import AdminPage    from "./pages/AdminPage";
import { PageLoader } from "./components/Skeleton";

import ErrorBoundary from "./components/ErrorBoundary";
import { ThemeProvider } from "./context/ThemeContext";
import { authMe, setAuthToken } from "./services/api";

const GLOBAL_CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');
  
  *, *::before, *::after { box-sizing: border-box; }

  /* Dark theme (default) */
  [data-theme="dark"] {
    --bg:        #0a0a12;
    --surface-1: #12121c;
    --surface-2: #1a1a28;
    --surface-3: #222236;
    --surface-glass: rgba(30, 30, 50, 0.6);
    
    --border:    #2a2a42;
    --border-2:  #3d3d5c;
    --border-glass: rgba(139, 92, 246, 0.15);
    --border-accent: rgba(139, 92, 246, 0.4);

    --text-0: #f1f1f5;
    --text-1: #c4c4d4;
    --text-2: #8888a0;
    --text-3: #5a5a72;

    --accent:       #8b5cf6;
    --accent-light: #a78bfa;
    --accent-hover: #7c3aed;
    --accent-dim:   rgba(139, 92, 246, 0.15);
    --accent-glow:  rgba(139, 92, 246, 0.4);
    
    --gradient-primary: linear-gradient(135deg, #8b5cf6 0%, #c026d3 50%, #f43f5e 100%);
    --gradient-primary-hover: linear-gradient(135deg, #7c3aed 0%, #d946ef 50%, #e11d48 100%);
    --gradient-accent: linear-gradient(135deg, #06b6d4 0%, #8b5cf6 100%);
    --gradient-surface: linear-gradient(180deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0) 100%);
    --gradient-bg: radial-gradient(ellipse at 50% 0%, rgba(139,92,246,0.15) 0%, transparent 50%),
                   radial-gradient(ellipse at 100% 100%, rgba(192,38,211,0.08) 0%, transparent 50%);
    
    --green:  #10b981;
    --green-dim: rgba(16, 185, 129, 0.15);
    --amber:  #f59e0b;
    --amber-dim: rgba(245, 158, 11, 0.15);
    --red:    #ef4444;
    --red-dim: rgba(239, 68, 68, 0.15);
    --cyan:   #06b6d4;
    --pink:   #ec4899;

    --radius-sm: 6px;
    --radius-md: 10px;
    --radius-lg: 16px;
    --radius-xl: 24px;
    --radius-full: 9999px;
    
    --shadow-sm: 0 2px 8px rgba(0,0,0,0.3);
    --shadow-md: 0 4px 16px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.03);
    --shadow-lg: 0 8px 32px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.04);
    --shadow-glow: 0 0 30px var(--accent-glow);
    --shadow-accent: 0 4px 20px rgba(139,92,246,0.3);
  }

  /* Light theme — Clean & Professional */
  [data-theme="light"] {
    --bg:        #f8f9fc;
    --surface-1: #ffffff;
    --surface-2: #f1f3f8;
    --surface-3: #e8ecf4;
    --surface-glass: rgba(255, 255, 255, 0.95);
    
    --border:    #d1d7e4;
    --border-2:  #b8c3d6;
    --border-glass: rgba(124, 58, 237, 0.25);
    --border-accent: #7c3aed;

    --text-0: #111827;
    --text-1: #374151;
    --text-2: #6b7280;
    --text-3: #9ca3af;

    --accent:       #7c3aed;
    --accent-light: #6d28d9;
    --accent-hover: #5b21b6;
    --accent-dim:   rgba(124, 58, 237, 0.1);
    --accent-glow:  rgba(124, 58, 237, 0.4);
    
    --gradient-primary: linear-gradient(135deg, #7c3aed 0%, #8b5cf6 100%);
    --gradient-primary-hover: linear-gradient(135deg, #6d28d9 0%, #7c3aed 100%);
    --gradient-accent: linear-gradient(135deg, #0891b2 0%, #7c3aed 100%);
    --gradient-surface: linear-gradient(180deg, rgba(0,0,0,0.02) 0%, rgba(0,0,0,0) 100%);
    --gradient-bg: linear-gradient(180deg, rgba(124,58,237,0.03) 0%, transparent 50%);
    
    --green:  #059669;
    --green-dim: rgba(5, 150, 105, 0.12);
    --amber:  #d97706;
    --amber-dim: rgba(217, 119, 6, 0.12);
    --red:    #dc2626;
    --red-dim: rgba(220, 38, 38, 0.12);
    --cyan:   #0891b2;
    --pink:   #db2777;

    --shadow-sm: 0 1px 3px rgba(0,0,0,0.08);
    --shadow-md: 0 4px 12px rgba(0,0,0,0.1), 0 2px 4px rgba(0,0,0,0.06);
    --shadow-lg: 0 8px 24px rgba(0,0,0,0.12), 0 4px 8px rgba(0,0,0,0.08);
    --shadow-glow: 0 0 24px var(--accent-glow);
    --shadow-accent: 0 4px 16px rgba(124,58,237,0.25);
  }

  html, body, #root { height: 100%; margin: 0; padding: 0; }

  body {
    font-family: 'Outfit', system-ui, sans-serif;
    background: var(--bg);
    background-image: var(--gradient-bg);
    color: var(--text-0);
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    font-size: 14px;
    letter-spacing: 0.01em;
    line-height: 1.5;
  }

  ::-webkit-scrollbar        { width: 8px; height: 8px; }
  ::-webkit-scrollbar-track  { background: transparent; }
  ::-webkit-scrollbar-thumb  { background: var(--border-2); border-radius: var(--radius-full); }
  ::-webkit-scrollbar-thumb:hover { background: var(--accent); }

  :focus-visible { 
    outline: 2px solid var(--accent); 
    outline-offset: 2px; 
    border-radius: var(--radius-sm); 
  }

  ::selection { background: var(--accent-dim); color: var(--text-0); }

  button, a, input, select, textarea,
  .btn-gradient, .glass-panel, .card-hover { 
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1); 
  }
  
  button, a { cursor: pointer; }
  
  .btn-gradient {
    background: var(--gradient-primary);
    border: none;
    color: white;
    box-shadow: var(--shadow-accent), inset 0 1px 1px rgba(255,255,255,0.2);
  }
  .btn-gradient:hover:not(:disabled) {
    background: var(--gradient-primary-hover);
    transform: translateY(-2px);
  }
  .btn-gradient:active:not(:disabled) {
    transform: translateY(0) scale(0.98);
  }
  
  .glass-panel {
    background: var(--surface-glass);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid var(--border-glass);
    box-shadow: var(--shadow-lg);
  }

  .card-hover {
    transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
  }
  .card-hover:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-glow);
    border-color: var(--border-accent);
  }

  @media (max-width: 768px) {
    .hide-mobile { display: none !important; }
  }
  @media (min-width: 769px) {
    .hide-desktop { display: none !important; }
  }
`;

const LearningPage = lazy(() => import("./pages/LearningPage"));

function AppContent() {
  const [authReady,   setAuthReady]   = useState(false);
  const [needsAuth,   setNeedsAuth]   = useState(true);
  const [userRole,    setUserRole]    = useState("user");
  const [backendDown, setBackendDown] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("dc_token");
    if (saved) setAuthToken(saved);
    
    authMe()
      .then(u => {
        setAuthReady(true);
        setNeedsAuth(false);
        setUserRole(u?.role || "user");
      })
      .catch(err => {
        const status = err?.response?.status;
        if (!status) {
          localStorage.removeItem("dc_token");
          setAuthToken(null);
          setBackendDown(true);
          setNeedsAuth(true);
        } else {
          setNeedsAuth(true);
        }
        setAuthReady(true);
      });
  }, []);

  function handleLogout() {
    localStorage.removeItem("dc_token");
    localStorage.removeItem("dc_refresh");
    setAuthToken(null);
    setNeedsAuth(true);
  }

  function handleAuthenticated(res) {
    setNeedsAuth(false);
    setBackendDown(false);
    if (res?.role) setUserRole(res.role);
  }

  if (!authReady) return null;

  return (
    <>
      <style>{GLOBAL_CSS}</style>
      
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        {needsAuth && <AuthModal onAuthenticated={handleAuthenticated} backendDown={backendDown} />}
        <ErrorBoundary>
          <Routes>
            <Route path="/"          element={<UploadPage userRole={userRole} onLogout={handleLogout} />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/datasets"  element={<DatasetsPage />} />
            <Route path="/billing"   element={<BillingPage />} />
            <Route path="/admin"     element={<AdminPage userRole={userRole} />} />
            <Route path="/learning"  element={
              <Suspense fallback={<PageLoader title="Learning" />}>
                <LearningPage />
              </Suspense>
            } />
            <Route path="*"          element={<Navigate to="/" replace />} />
          </Routes>
        </ErrorBoundary>
      </BrowserRouter>
    </>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AppContent />
    </ThemeProvider>
  );
}
