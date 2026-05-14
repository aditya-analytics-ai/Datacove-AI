/**
 * SampleDatasetsPanel — Onboarding panel for loading sample datasets.
 * Shown on UploadPage so new users can explore without uploading anything.
 */
import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Database, AlertCircle, Loader2, ChevronRight, Users, ShoppingCart, Briefcase } from "lucide-react";
import { fetchSamples, loadSample } from "../services/api";

const ICONS = {
  messy_customers: Users,
  sales_data: ShoppingCart,
  hr_data: Briefcase,
};

const COLORS = {
  messy_customers: "var(--accent)",
  sales_data: "var(--cyan)",
  hr_data: "var(--green)",
};

export default function SampleDatasetsPanel() {
  const navigate = useNavigate();
  const [samples, setSamples] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingId, setLoadingId] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchSamples()
      .then(d => setSamples(d.samples || []))
      .catch(() => setError("Could not load sample datasets."))
      .finally(() => setLoading(false));
  }, []);

  const handleLoad = async (sampleId) => {
    setLoadingId(sampleId);
    try {
      const result = await loadSample(sampleId);
      navigate("/dashboard", {
        state: {
          session: {
            session_id: result.session_id,
            columns:    result.columns || [],
            preview:    result.preview || [],
            filename:   result.filename,
            rows:       result.rows,
          },
        },
      });
    } catch {
      setError("Failed to load sample. Please try again.");
      setLoadingId(null);
    }
  };

  const css = `
    .sp-wrap { width: 100%; max-width: 480px; }
    .sp-title { font-size: 12px; font-weight: 600; color: var(--text-1);
      text-transform: uppercase; letter-spacing: .07em; margin-bottom: 12px; }
    .sp-grid { display: grid; gap: 8px; }
    .sp-card { display: flex; align-items: center; gap: 12px;
      background: var(--surface-1); border: 1px solid var(--border);
      border-radius: var(--radius-md); padding: 14px 16px; cursor: pointer;
      transition: all .15s; }
    .sp-card:hover { border-color: var(--accent); background: var(--accent-dim); }
    .sp-card:disabled { opacity: 0.5; cursor: default; }
    .sp-icon { width: 42px; height: 42px; border-radius: var(--radius-md);
      display: flex; align-items: center; justify-content: center; flex-shrink: 0;
      background: var(--accent-dim); border: 1px solid var(--border-glass); }
    .sp-info { flex: 1; min-width: 0; }
    .sp-name { font-size: 14px; font-weight: 600; color: var(--text-0); }
    .sp-desc { font-size: 12px; color: var(--text-2); margin-top: 2px; }
    .sp-issues { display: flex; gap: 4px; margin-top: 5px; flex-wrap: wrap; }
    .sp-tag { font-size: 10px; font-weight: 600; padding: 2px 8px;
      border-radius: 99px; background: var(--accent-dim); color: var(--accent);
      border: 1px solid var(--border-glass); letter-spacing: .03em; }
    .sp-err { display: flex; align-items: center; gap: 6px; font-size: 12px;
      color: var(--red); margin-top: 8px; }
  `;

  if (loading) return (
    <div style={{ display: "flex", justifyContent: "center", padding: 32 }}>
      <Loader2 size={18} style={{ animation: "spin .7s linear infinite", color: "var(--text-3)" }} />
    </div>
  );

  return (
    <>
      <style>{css}</style>
      <div className="sp-wrap">
        <div className="sp-title">Or try a sample dataset</div>
        {error && (
          <div className="sp-err"><AlertCircle size={12} /> {error}</div>
        )}
        <div className="sp-grid">
          {samples.map(s => {
            const Icon = ICONS[s.id] || Database;
            const color = COLORS[s.id] || "#6366f1";
            const busy = loadingId === s.id;
            return (
              <button
                key={s.id}
                className="sp-card"
                onClick={() => handleLoad(s.id)}
                disabled={!!loadingId}
                style={{ border: "none", textAlign: "left", width: "100%", background: "var(--surface-1)" }}
              >
                <div className="sp-icon">
                  {busy
                    ? <Loader2 size={18} color="var(--accent)" style={{ animation: "spin .7s linear infinite" }} />
                    : <Icon size={18} color="var(--accent)" />}
                </div>
                <div className="sp-info">
                  <div className="sp-name">{s.name}</div>
                  <div className="sp-desc">{s.description}</div>
                  {s.issues && s.issues.length > 0 && (
                    <div className="sp-issues">
                      {s.issues.slice(0, 4).map(iss => (
                        <span key={iss} className="sp-tag">{iss}</span>
                      ))}
                    </div>
                  )}
                </div>
                <ChevronRight size={16} color="var(--text-2)" />
              </button>
            );
          })}
        </div>
      </div>
    </>
  );
}
