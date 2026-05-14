/**
 * PIIDetectorPanel — surfaces the backend pii_detector.py service.
 *
 * Features:
 *  - Scan current dataset for columns containing PII (email, phone, SSN, etc.)
 *  - Per-column detection with type + confidence displayed
 *  - Mask actions: hash, fake, redact — applied per column
 *  - Shows rows affected + before/after column name preview
 */
import React, { useState, useCallback } from "react";
import { Shield, ShieldOff, ShieldCheck, Loader2, AlertCircle, RefreshCw } from "lucide-react";
import { detectPII, maskPII } from "../services/api";

const STRATEGY_OPTS = [
  { value: "hash",   label: "Hash (SHA-256)"   },
  { value: "fake",   label: "Replace with fake" },
  { value: "redact", label: "Redact (blank)"    },
];

const PII_COLORS = {
  email:        "#6366f1",
  phone:        "#f59e0b",
  ssn:          "#ef4444",
  credit_card:  "#ef4444",
  ip_address:   "#3b82f6",
  name:         "#8b5cf6",
  address:      "#10b981",
  date_of_birth:"#f97316",
};

function PIIBadge({ type }) {
  const color = PII_COLORS[type] ?? "#6b7280";
  return (
    <span style={{
      display: "inline-block", padding: "1px 7px", borderRadius: 99,
      background: `${color}20`, border: `1px solid ${color}40`,
      fontSize: 10, fontWeight: 600, color, textTransform: "uppercase",
      letterSpacing: ".05em",
    }}>
      {type.replace(/_/g, " ")}
    </span>
  );
}

export default function PIIDetectorPanel({ sessionId, columns, onMasked }) {
  const [detections, setDetections]   = useState(null);   // [{column, pii_type, confidence, sample_count}]
  const [scanning,   setScanning]     = useState(false);
  const [strategies, setStrategies]   = useState({});     // column → strategy
  const [selected,   setSelected]     = useState(new Set()); // columns selected for masking
  const [masking,    setMasking]      = useState(false);
  const [error,      setError]        = useState("");
  const [masked,     setMasked]       = useState(null);   // result from maskPII

  const scan = useCallback(async () => {
    setScanning(true);
    setError("");
    setDetections(null);
    setMasked(null);
    try {
      const res = await detectPII(sessionId);
      setDetections(res.detections ?? []);
    } catch (e) {
      setError(e?.response?.data?.detail ?? "PII scan failed.");
    } finally {
      setScanning(false);
    }
  }, [sessionId]);

  const toggleColumn = (col) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(col) ? next.delete(col) : next.add(col);
      return next;
    });
  };

  const applyMask = useCallback(async () => {
    if (!selected.size) return;
    setMasking(true);
    setError("");
    try {
      const cols = [...selected].map(col => ({
        column:   col,
        pii_type: detections.find(d => d.column === col)?.pii_type ?? "unknown",
        strategy: strategies[col] ?? "hash",
      }));
      const res = await maskPII(sessionId, cols);
      setMasked(res);
      if (onMasked) onMasked(res);
      setSelected(new Set());
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Masking failed.");
    } finally {
      setMasking(false);
    }
  }, [sessionId, selected, strategies, detections, onMasked]);

  const css = `
    .pii-wrap { font-size: 12px; }
    .pii-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
    .pii-title { font-size: 11px; font-weight: 700; color: var(--text-2);
                 text-transform: uppercase; letter-spacing: .07em; }
    .pii-scan-btn { display: inline-flex; align-items: center; gap: 5px;
                    padding: 6px 13px; background: var(--accent); color: #fff;
                    border: none; border-radius: var(--radius-sm); font-size: 11px;
                    font-weight: 600; cursor: pointer; }
    .pii-scan-btn:disabled { opacity: .5; cursor: default; }
    .pii-empty { text-align: center; padding: 24px 0; color: var(--text-3); font-size: 12px; }
    .pii-success { display: flex; align-items: center; gap: 6px; padding: 8px 10px;
                   background: rgba(34,197,94,.08); border: 1px solid rgba(34,197,94,.2);
                   border-radius: var(--radius-sm); color: #22c55e; margin-bottom: 10px; font-size: 11px; }
    .pii-err { color: var(--red); display: flex; align-items: center; gap: 5px;
               padding: 6px 10px; font-size: 11px; }
    .pii-item { background: var(--surface-1); border: 1px solid var(--border);
                border-radius: var(--radius-sm); padding: 10px 12px; margin-bottom: 8px; }
    .pii-item-row { display: flex; align-items: center; gap: 8px; }
    .pii-item-col { font-weight: 600; color: var(--text-0); flex: 1; }
    .pii-conf { font-size: 10px; color: var(--text-3); }
    .pii-strategy { margin-top: 8px; display: flex; align-items: center; gap: 6px; }
    .pii-sel { background: none; border: 1px solid var(--border); border-radius: 4px;
               padding: 3px 6px; font-size: 11px; color: var(--text-1); cursor: pointer; }
    .pii-mask-bar { margin-top: 12px; display: flex; align-items: center; gap: 8px; }
    .pii-mask-btn { padding: 7px 14px; background: #ef4444; color: #fff;
                    border: none; border-radius: var(--radius-sm); font-size: 11px;
                    font-weight: 600; cursor: pointer; }
    .pii-mask-btn:disabled { opacity: .5; cursor: default; }
  `;

  return (
    <>
      <style>{css}</style>
      <div className="pii-wrap">
        <div className="pii-header">
          <span className="pii-title">
            <Shield size={11} style={{ marginRight: 4, verticalAlign: "middle" }} />
            PII Detector
          </span>
          <button className="pii-scan-btn" onClick={scan} disabled={scanning || masking}>
            {scanning
              ? <><Loader2 size={11} style={{ animation: "spin .7s linear infinite" }} />Scanning…</>
              : <><RefreshCw size={11} />Scan for PII</>}
          </button>
        </div>

        {error && (
          <div className="pii-err"><AlertCircle size={11} />{error}</div>
        )}

        {masked && (
          <div className="pii-success">
            <ShieldCheck size={13} />
            Masked {masked.masked_columns?.length ?? 0} column(s) successfully.
          </div>
        )}

        {detections === null && !scanning && (
          <div className="pii-empty">
            <ShieldOff size={20} style={{ marginBottom: 8, opacity: .4 }} />
            <br />Click "Scan for PII" to check your dataset for sensitive data.
          </div>
        )}

        {detections !== null && detections.length === 0 && (
          <div className="pii-empty">
            <ShieldCheck size={20} style={{ marginBottom: 8, color: "#22c55e" }} />
            <br />No PII detected in this dataset.
          </div>
        )}

        {detections?.map(d => (
          <div key={d.column} className="pii-item">
            <div className="pii-item-row">
              <input
                type="checkbox"
                checked={selected.has(d.column)}
                onChange={() => toggleColumn(d.column)}
                style={{ accentColor: "var(--accent)" }}
              />
              <span className="pii-item-col">{d.column}</span>
              <PIIBadge type={d.pii_type} />
              <span className="pii-conf">{Math.round((d.confidence ?? 0) * 100)}% conf.</span>
            </div>
            {selected.has(d.column) && (
              <div className="pii-strategy">
                <span style={{ color: "var(--text-3)", fontSize: 10 }}>Strategy:</span>
                <select
                  className="pii-sel"
                  value={strategies[d.column] ?? "hash"}
                  onChange={e => setStrategies(s => ({ ...s, [d.column]: e.target.value }))}
                >
                  {STRATEGY_OPTS.map(o => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
            )}
          </div>
        ))}

        {detections?.length > 0 && (
          <div className="pii-mask-bar">
            <button
              className="pii-mask-btn"
              onClick={applyMask}
              disabled={!selected.size || masking}
            >
              {masking
                ? <><Loader2 size={11} style={{ animation: "spin .7s linear infinite" }} /> Masking…</>
                : `Mask ${selected.size} column${selected.size !== 1 ? "s" : ""}`}
            </button>
            {selected.size === 0 && (
              <span style={{ color: "var(--text-3)", fontSize: 11 }}>Select columns above to mask</span>
            )}
          </div>
        )}
      </div>
    </>
  );
}
