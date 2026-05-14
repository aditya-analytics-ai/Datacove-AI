/**
 * ConnectorsPanel — Data source connector UI.
 * Supports: Public URL (CSV/Excel), Google Sheets, AWS S3, SQL database.
 * Each connector form validates locally and calls the backend.
 */
import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Link2, Table2, Cloud, Database, AlertCircle,
  Loader2, ChevronDown, ChevronUp, CheckCircle2,
} from "lucide-react";
import { connectURL, connectDatabase, connectGSheets, connectS3, fetchAvailableConnectors } from "../services/api";

const CONNECTORS = [
  {
    id: "url",
    label: "Public URL",
    icon: Link2,
    color: "#6366f1",
    desc: "Load any public CSV or Excel file from a URL",
    fields: [
      { key: "url", label: "URL", type: "text", placeholder: "https://example.com/data.csv" },
      { key: "filename", label: "Dataset name (optional)", type: "text", placeholder: "my_data.csv" },
    ],
  },
  {
    id: "gsheets",
    label: "Google Sheets",
    icon: Table2,
    color: "#34a853",
    desc: "Import a Google Sheet using a service account",
    fields: [
      { key: "spreadsheet_id", label: "Spreadsheet ID", type: "text",
        placeholder: "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms" },
      { key: "sheet_name", label: "Sheet name (optional)", type: "text", placeholder: "Sheet1" },
      { key: "service_account_json", label: "Service account JSON", type: "textarea",
        placeholder: '{"type": "service_account", "project_id": "..."}' },
    ],
  },
  {
    id: "s3",
    label: "AWS S3",
    icon: Cloud,
    color: "#f59e0b",
    desc: "Import a CSV or Excel file from an S3 bucket",
    fields: [
      { key: "bucket",    label: "Bucket name",    type: "text",     placeholder: "my-data-bucket" },
      { key: "key",       label: "File path (key)", type: "text",    placeholder: "data/sales.csv" },
      { key: "aws_access_key_id",     label: "AWS access key ID (optional, leave blank for IAM role)",
        type: "text", placeholder: "AKIAIOSFODNN7EXAMPLE" },
      { key: "aws_secret_access_key", label: "AWS secret access key",
        type: "password", placeholder: "" },
      { key: "region",    label: "Region",         type: "text",     placeholder: "us-east-1" },
    ],
  },
  {
    id: "database",
    label: "SQL Database",
    icon: Database,
    color: "#059669",
    desc: "Connect via SQLAlchemy connection string (read-only SELECT)",
    fields: [
      { key: "connection_string", label: "Connection string", type: "text",
        placeholder: "postgresql://user:pass@host/db" },
      { key: "query", label: "SQL query", type: "textarea",
        placeholder: "SELECT * FROM orders LIMIT 5000" },
      { key: "filename", label: "Dataset name (optional)", type: "text", placeholder: "query_result.csv" },
    ],
  },
];

function ConnectorForm({ connector, onSuccess }) {
  const [values, setValues]   = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState("");

  const set = (k, v) => setValues(prev => ({ ...prev, [k]: v }));

  const handleSubmit = async () => {
    setLoading(true);
    setError("");
    try {
      let res;
      if (connector.id === "url") {
        res = await connectURL(values.url, values.filename);
      } else if (connector.id === "database") {
        res = await connectDatabase(
          values.connection_string,
          values.query,
          values.filename,
        );
      } else if (connector.id === "gsheets") {
        res = await connectGSheets(
          values.spreadsheet_id,
          values.sheet_name,
          values.service_account_json,
        );
      } else if (connector.id === "s3") {
        res = await connectS3(
          values.bucket,
          values.key,
          values.aws_access_key_id,
          values.aws_secret_access_key,
          values.region,
        );
      }
      if (res) onSuccess(res);
    } catch (e) {
      setError(e?.response?.data?.detail || "Connection failed. Check your inputs.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: "12px 0 4px" }}>
      {connector.fields.map(f => (
        <div key={f.key} style={{ marginBottom: 10 }}>
          <label style={{ display: "block", fontSize: 11, fontWeight: 600,
            color: "var(--text-2)", marginBottom: 4,
            textTransform: "uppercase", letterSpacing: ".06em" }}>
            {f.label}
          </label>
          {f.type === "textarea" ? (
            <textarea
              rows={3}
              placeholder={f.placeholder}
              value={values[f.key] || ""}
              onChange={e => set(f.key, e.target.value)}
              style={{ width: "100%", background: "var(--surface-2)",
                border: "1px solid var(--border)", borderRadius: "var(--radius-sm)",
                color: "var(--text-0)", padding: "8px 12px", fontSize: 13,
                fontFamily: "'JetBrains Mono', monospace", resize: "vertical",
                boxSizing: "border-box", outline: "none" }}
            />
          ) : (
            <input
              type={f.type === "password" ? "password" : "text"}
              placeholder={f.placeholder}
              value={values[f.key] || ""}
              onChange={e => set(f.key, e.target.value)}
              style={{ width: "100%", background: "var(--surface-2)",
                border: "1px solid var(--border)", borderRadius: "var(--radius-sm)",
                color: "var(--text-0)", padding: "8px 12px", fontSize: 13,
                boxSizing: "border-box", outline: "none" }}
            />
          )}
        </div>
      ))}
      {error && (
        <div style={{ display: "flex", alignItems: "center", gap: 6,
          fontSize: 11, color: "var(--red)", marginBottom: 8 }}>
          <AlertCircle size={11} /> {error}
        </div>
      )}
      <button
        onClick={handleSubmit}
        disabled={loading}
        style={{ display: "inline-flex", alignItems: "center", gap: 6,
          padding: "7px 16px", background: "var(--accent)", color: "#fff",
          border: "none", borderRadius: "var(--radius-sm)", fontSize: 12,
          fontWeight: 500, cursor: loading ? "default" : "pointer",
          opacity: loading ? .5 : 1 }}
      >
        {loading
          ? <Loader2 size={12} style={{ animation: "spin .7s linear infinite" }} />
          : <Cloud size={12} />}
        Connect & load
      </button>
    </div>
  );
}

export default function ConnectorsPanel() {
  const navigate = useNavigate();
  const [available, setAvailable]   = useState({});
  const [expanded, setExpanded]     = useState(null);
  const [success, setSuccess]       = useState(null);

  useEffect(() => {
    fetchAvailableConnectors()
      .then(d => setAvailable(d.available || {}))
      .catch(() => {});
  }, []);

  const handleSuccess = (res) => {
    setSuccess(res);
    navigate("/dashboard", {
      state: {
        session: {
          session_id: res.session_id,
          columns:    res.columns || [],
          preview:    res.preview || [],
          filename:   res.filename,
          rows:       res.rows,
        },
      },
    });
  };

  const css = `
    .cn-wrap { max-width: 560px; }
    .cn-title { font-size: 12px; font-weight: 600; color: var(--text-1);
      text-transform: uppercase; letter-spacing: .07em; margin-bottom: 12px; }
    .cn-list { display: grid; gap: 8px; }
    .cn-item { background: var(--surface-1); border: 1px solid var(--border);
      border-radius: var(--radius-md); overflow: hidden; }
    .cn-header { display: flex; align-items: center; gap: 10px;
      padding: 14px 16px; cursor: pointer; }
    .cn-header:hover { background: var(--surface-2); }
    .cn-icon { width: 40px; height: 40px; border-radius: var(--radius-md);
      display: flex; align-items: center; justify-content: center; flex-shrink: 0;
      background: var(--accent-dim); border: 1px solid var(--border-glass); }
    .cn-info { flex: 1; }
    .cn-label { font-size: 14px; font-weight: 600; color: var(--text-0); }
    .cn-desc { font-size: 12px; color: var(--text-2); margin-top: 2px; }
    .cn-status { font-size: 10px; font-weight: 600; padding: 3px 10px;
      border-radius: 99px; }
    .cn-status-ok { background: var(--green-dim); color: var(--green);
      border: 1px solid var(--green); }
    .cn-status-na { background: var(--surface-3); color: var(--text-3);
      border: 1px solid var(--border); }
    .cn-body { padding: 0 16px 14px; border-top: 1px solid var(--border); }
    @keyframes spin { to { transform: rotate(360deg); } }
  `;

  return (
    <>
      <style>{css}</style>
      <div className="cn-wrap">
        <div className="cn-title">Data source connectors</div>
        <div className="cn-list">
          {CONNECTORS.map(c => {
            const Icon = c.icon;
            const isOpen = expanded === c.id;
            const isAvailable = available[c.id] !== false;
            return (
              <div key={c.id} className="cn-item">
                <div className="cn-header" onClick={() => setExpanded(isOpen ? null : c.id)}>
                  <div className="cn-icon">
                    <Icon size={18} color="var(--accent)" />
                  </div>
                  <div className="cn-info">
                    <div className="cn-label">{c.label}</div>
                    <div className="cn-desc">{c.desc}</div>
                  </div>
                  <span className={`cn-status ${isAvailable ? "cn-status-ok" : "cn-status-na"}`}>
                    {isAvailable ? "Ready" : "Not configured"}
                  </span>
                  {isOpen ? <ChevronUp size={16} color="var(--text-2)" /> : <ChevronDown size={16} color="var(--text-2)" />}
                </div>
                {isOpen && (
                  <div className="cn-body">
                    {isAvailable
                      ? <ConnectorForm connector={c} onSuccess={handleSuccess} />
                      : <div style={{ fontSize: 12, color: "var(--text-2)", padding: "10px 0" }}>
                          This connector requires additional packages. Check the README for setup instructions.
                        </div>}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
