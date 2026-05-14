/**
 * ErrorBoundary — catches React render errors
 * Styled for "Terminal Precision" theme
 */
import React from "react";

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error("[ErrorBoundary]", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          justifyContent: "center", height: "100vh", gap: 16,
          background: "var(--bg)", color: "var(--text-0)",
          fontFamily: "'Outfit', sans-serif", padding: 32,
        }}>
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" style={{ opacity: 0.5 }}>
            <circle cx="12" cy="12" r="10" stroke="var(--red)" strokeWidth="1.5" fill="none"/>
            <path d="M12 7v6M12 16v1" stroke="var(--red)" strokeWidth="2" strokeLinecap="round"/>
          </svg>
          
          <div style={{ fontSize: 20, fontWeight: 700, color: "var(--text-0)" }}>
            Something went wrong
          </div>
          
          <div style={{
            fontSize: 12, color: "var(--text-2)",
            maxWidth: 480, textAlign: "center", lineHeight: 1.6,
            background: "var(--surface-1)", padding: "16px 24px",
            borderRadius: "var(--radius-lg)", 
            border: "1px solid var(--border)",
            fontFamily: "'JetBrains Mono', monospace",
            wordBreak: "break-word",
          }}>
            {this.state.error?.message ?? "An unexpected render error occurred."}
          </div>
          
          <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              style={{
                padding: "10px 24px", borderRadius: "var(--radius-md)", border: "none",
                background: "var(--gradient-primary)",
                color: "#fff", fontSize: 13, fontWeight: 600,
                cursor: "pointer", boxShadow: "var(--shadow-accent)",
              }}
            >
              Try to recover
            </button>
            <button
              onClick={() => window.location.reload()}
              style={{
                padding: "10px 24px", borderRadius: "var(--radius-md)",
                border: "1px solid var(--border)",
                background: "var(--surface-2)", color: "var(--text-1)",
                fontSize: 13, cursor: "pointer",
              }}
            >
              Reload page
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
