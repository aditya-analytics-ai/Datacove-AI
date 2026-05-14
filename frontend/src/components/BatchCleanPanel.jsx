/**
 * BatchCleanPanel.jsx — Multi-file batch cleaning pipeline UI.
 *
 * Flow:
 *   1. Drag & drop / select multiple CSV / XLSX files
 *   2. Build a pipeline from a curated set of "safe" one-click transforms
 *      (or import the current session's history as a pipeline)
 *   3. Run → per-file status + row counts
 *   4. Download ZIP of all cleaned files
 *
 * Props:
 *   sessionId {string}   — used to seed the pipeline from session history
 *   history   {Array}    — current session history (for "import pipeline")
 */
import React, { useState, useCallback, useRef } from "react";
import {
  UploadCloud, Play, Download, Trash2, Plus, X,
  Loader2, CheckCircle2, AlertTriangle, FileText,
  GripVertical, ChevronDown, Package,
} from "lucide-react";
import { batchUpload, batchRun, batchDownload } from "../services/api";

// ── Preset pipeline steps ─────────────────────────────────────────────────────

const PRESET_STEPS = [
  { label: "Trim whitespace",            action: "trim_whitespace",            params: {} },
  { label: "Standardise capitalisation", action: "standardise_capitalisation",  params: {} },
  { label: "Remove duplicates",          action: "remove_duplicates",           params: {} },
  { label: "Normalise categories",       action: "normalise_categories",        params: {} },
  { label: "Normalise Unicode",          action: "normalize_unicode",           params: {} },
  { label: "Drop constant columns",      action: "drop_constant_columns",       params: {} },
  { label: "Drop high-missing columns",  action: "drop_high_missing_columns",   params: { threshold: 0.9 } },
  { label: "Fill missing (mean)",        action: "fill_missing",                params: { strategy: "mean" } },
  { label: "Fill missing (mode)",        action: "fill_missing",                params: { strategy: "mode" } },
  { label: "Coerce numeric columns",     action: "coerce_numeric",              params: {} },
  { label: "Standardise dates",          action: "standardise_dates",           params: {} },
];

// ── Helpers ────────────────────────────────────────────────────────────────────

function FileStatusBadge({ status }) {
  const map = {
    ready:           { color: "var(--text-3)", label: "ready" },
    done:            { color: "var(--green)",   label: "cleaned" },
    done_with_errors:{ color: "var(--amber)",   label: "done (errors)" },
    error:           { color: "var(--red)",     label: "error" },
    running:         { color: "var(--blue, #3b82f6)", label: "running…" },
  };
  const s = map[status] || map.ready;
  return (
    <span style={{
      fontSize: 10, fontWeight: 600, padding: "1px 7px", borderRadius: 10,
      background: s.color + "18", color: s.color,
    }}>
      {s.label}
    </span>
  );
}

function SectionLabel({ children }) {
  return (
    <div style={{
      fontSize: 10, fontWeight: 700, color: "var(--text-3)",
      textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 6,
    }}>
      {children}
    </div>
  );
}

function StepPill({ step, onRemove }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 6,
      padding: "5px 8px 5px 10px", borderRadius: 8,
      background: "var(--surface-1)", border: "1px solid var(--border)",
      fontSize: 11, color: "var(--text-1)",
    }}>
      <GripVertical size={11} style={{ color: "var(--text-3)", flexShrink: 0 }} />
      <span style={{ flex: 1 }}>{step.label}</span>
      {Object.keys(step.params).length > 0 && (
        <span style={{ fontSize: 10, color: "var(--text-3)", fontFamily: "monospace" }}>
          {Object.entries(step.params).map(([k, v]) => `${k}=${v}`).join(", ")}
        </span>
      )}
      <button
        onClick={onRemove}
        style={{
          background: "none", border: "none", cursor: "pointer",
          color: "var(--text-3)", padding: 2, display: "flex",
        }}
      >
        <X size={11} />
      </button>
    </div>
  );
}

// ── Main ───────────────────────────────────────────────────────────────────────

export default function BatchCleanPanel({ sessionId, history = [] }) {
  const [files,     setFiles]     = useState([]);   // {filename, rows, columns, status, errors}
  const [batchId,   setBatchId]   = useState(null);
  const [pipeline,  setPipeline]  = useState([
    { ...PRESET_STEPS[0] },
    { ...PRESET_STEPS[2] },
  ]);
  const [results,   setResults]   = useState([]);
  const [uploading, setUploading] = useState(false);
  const [running,   setRunning]   = useState(false);
  const [error,     setError]     = useState("");
  const [showAdd,   setShowAdd]   = useState(false);
  const [dragging,  setDragging]  = useState(false);
  const inputRef = useRef();

  // ── File handling ──────────────────────────────────────────────────────────

  const handleFiles = useCallback(async (rawFiles) => {
    const accepted = [...rawFiles].filter(f =>
      f.name.match(/\.(csv|xlsx|xls)$/i)
    );
    if (!accepted.length) return;

    setUploading(true);
    setError("");
    setResults([]);
    setBatchId(null);

    try {
      const res = await batchUpload(accepted);
      setBatchId(res.batch_id);
      setFiles(res.files || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Upload failed.");
    } finally {
      setUploading(false);
    }
  }, []);

  const onDrop = useCallback((e) => {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  }, [handleFiles]);

  const onInputChange = useCallback((e) => {
    handleFiles(e.target.files);
    e.target.value = "";
  }, [handleFiles]);

  // ── Pipeline management ────────────────────────────────────────────────────

  const addStep = useCallback((preset) => {
    setPipeline(p => [...p, { ...preset }]);
    setShowAdd(false);
  }, []);

  const removeStep = useCallback((idx) => {
    setPipeline(p => p.filter((_, i) => i !== idx));
  }, []);

  const importFromHistory = useCallback(() => {
    if (!history.length) return;
    const steps = history.map(h => ({
      label:  h.action.replace(/_/g, " "),
      action: h.action,
      params: h.params || {},
    }));
    setPipeline(steps);
  }, [history]);

  // ── Run ────────────────────────────────────────────────────────────────────

  const handleRun = useCallback(async () => {
    if (!batchId || !pipeline.length) return;
    setRunning(true);
    setError("");
    setResults([]);
    try {
      const res = await batchRun(batchId, pipeline.map(s => ({
        action: s.action,
        params: s.params,
      })));
      setResults(res.results || []);
      // Update file statuses
      setFiles(prev => prev.map(f => {
        const r = (res.results || []).find(r => r.filename === f.filename);
        return r ? { ...f, ...r } : f;
      }));
    } catch (e) {
      setError(e?.response?.data?.detail || "Run failed.");
    } finally {
      setRunning(false);
    }
  }, [batchId, pipeline]);

  // ── Download ───────────────────────────────────────────────────────────────

  const handleDownload = useCallback(async () => {
    if (!batchId) return;
    try {
      await batchDownload(batchId);
    } catch (e) {
      setError(e?.response?.data?.detail || "Download failed.");
    }
  }, [batchId]);

  const canRun      = batchId && pipeline.length > 0 && !running;
  const canDownload = results.length > 0;
  const doneCount   = results.filter(r => r.status?.startsWith("done")).length;

  return (
    <div style={{
      background: "var(--surface-2)", borderRadius: "var(--radius-md)",
      border: "1px solid var(--border)", overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        padding: "9px 12px", borderBottom: "1px solid var(--border)",
      }}>
        <Package size={13} style={{ color: "var(--text-2)" }} />
        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text-1)" }}>
          Batch Cleaning
        </span>
        <span style={{
          fontSize: 10, color: "var(--text-3)", padding: "1px 7px",
          borderRadius: 10, background: "var(--surface-3)",
        }}>
          Apply a pipeline to multiple files at once
        </span>
      </div>

      <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 14 }}>

        {/* Error */}
        {error && (
          <div style={{
            display: "flex", gap: 7, alignItems: "flex-start",
            padding: "7px 10px", borderRadius: 6,
            background: "var(--red)14", fontSize: 11, color: "var(--red)",
          }}>
            <AlertTriangle size={12} style={{ flexShrink: 0, marginTop: 1 }} />
            {error}
          </div>
        )}

        {/* Drop zone */}
        <div>
          <SectionLabel>1 · Upload files (CSV / XLSX)</SectionLabel>
          <div
            onDragOver={e => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            style={{
              border: `2px dashed ${dragging ? "var(--accent, #6366f1)" : "var(--border)"}`,
              borderRadius: 10, padding: "20px 16px",
              display: "flex", flexDirection: "column", alignItems: "center", gap: 8,
              cursor: "pointer", transition: "all .15s",
              background: dragging ? "var(--accent, #6366f1)08" : "var(--surface-1)",
            }}
          >
            <input
              ref={inputRef}
              type="file"
              multiple
              accept=".csv,.xlsx,.xls"
              style={{ display: "none" }}
              onChange={onInputChange}
            />
            {uploading
              ? <Loader2 size={22} style={{ color: "var(--text-3)", animation: "spin .7s linear infinite" }} />
              : <UploadCloud size={22} style={{ color: dragging ? "var(--accent, #6366f1)" : "var(--text-3)" }} />}
            <span style={{ fontSize: 12, color: "var(--text-2)", fontWeight: 500 }}>
              {uploading ? "Uploading…" : "Drop CSV / XLSX files here, or click to browse"}
            </span>
            <span style={{ fontSize: 10, color: "var(--text-3)" }}>
              Multiple files supported
            </span>
          </div>
        </div>

        {/* File manifest */}
        {files.length > 0 && (
          <div>
            <SectionLabel>Files ({files.length})</SectionLabel>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {files.map((f, i) => {
                const result = results.find(r => r.filename === f.filename);
                return (
                  <div key={i} style={{
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "6px 10px", borderRadius: 7,
                    background: "var(--surface-1)", border: "1px solid var(--border)",
                  }}>
                    <FileText size={12} style={{ color: "var(--text-3)", flexShrink: 0 }} />
                    <span style={{ fontSize: 11, color: "var(--text-1)", flex: 1, minWidth: 0,
                      overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {f.filename}
                    </span>
                    <span style={{ fontSize: 10, color: "var(--text-3)", flexShrink: 0 }}>
                      {f.rows?.toLocaleString()} rows
                    </span>
                    {result && (
                      <span style={{ fontSize: 10, color: "var(--green)", flexShrink: 0 }}>
                        → {result.rows?.toLocaleString()} rows
                      </span>
                    )}
                    <FileStatusBadge status={result?.status || f.status || "ready"} />
                    {result?.errors?.length > 0 && (
                      <span title={result.errors.map(e => e.error).join("; ")}>
                        <AlertTriangle size={11} style={{ color: "var(--amber)" }} />
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Pipeline builder */}
        <div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
            <SectionLabel>2 · Cleaning pipeline</SectionLabel>
            {history.length > 0 && (
              <button
                onClick={importFromHistory}
                style={{
                  fontSize: 10, padding: "2px 8px", borderRadius: 5,
                  border: "1px solid var(--border)", background: "var(--surface-1)",
                  color: "var(--text-2)", cursor: "pointer", marginBottom: 6,
                }}
              >
                Import from session history
              </button>
            )}
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 5, marginBottom: 8 }}>
            {pipeline.length === 0 && (
              <div style={{
                fontSize: 11, color: "var(--text-3)", padding: "10px",
                textAlign: "center", border: "1px dashed var(--border)", borderRadius: 7,
              }}>
                No steps yet — add transforms below
              </div>
            )}
            {pipeline.map((step, i) => (
              <StepPill key={i} step={step} onRemove={() => removeStep(i)} />
            ))}
          </div>

          {/* Add step dropdown */}
          <div style={{ position: "relative" }}>
            <button
              onClick={() => setShowAdd(x => !x)}
              style={{
                display: "flex", alignItems: "center", gap: 5,
                fontSize: 11, padding: "5px 10px", borderRadius: 6,
                border: "1px dashed var(--border)", background: "var(--surface-1)",
                color: "var(--text-2)", cursor: "pointer", width: "100%",
                justifyContent: "center",
              }}
            >
              <Plus size={11} /> Add step
              <ChevronDown size={11} style={{ marginLeft: "auto" }} />
            </button>
            {showAdd && (
              <div style={{
                position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0,
                background: "var(--surface-1)", border: "1px solid var(--border)",
                borderRadius: 8, zIndex: 10, overflow: "hidden", boxShadow: "0 4px 16px rgba(0,0,0,.12)",
                maxHeight: 240, overflowY: "auto",
              }}>
                {PRESET_STEPS.map((preset, i) => (
                  <button
                    key={i}
                    onClick={() => addStep(preset)}
                    style={{
                      display: "block", width: "100%", textAlign: "left",
                      padding: "7px 12px", fontSize: 11, color: "var(--text-1)",
                      background: "none", border: "none", cursor: "pointer",
                      borderBottom: i < PRESET_STEPS.length - 1 ? "1px solid var(--border)" : "none",
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = "var(--surface-2)"}
                    onMouseLeave={e => e.currentTarget.style.background = "none"}
                  >
                    {preset.label}
                    {Object.keys(preset.params).length > 0 && (
                      <span style={{ fontSize: 10, color: "var(--text-3)", marginLeft: 8, fontFamily: "monospace" }}>
                        {Object.entries(preset.params).map(([k,v]) => `${k}=${v}`).join(", ")}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Run + Download buttons */}
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={handleRun}
            disabled={!canRun}
            style={{
              flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 7,
              padding: "8px 14px", borderRadius: 7, fontSize: 12, fontWeight: 600,
              background: canRun ? "var(--accent, #6366f1)" : "var(--surface-3)",
              color: canRun ? "#fff" : "var(--text-3)",
              border: "none", cursor: canRun ? "pointer" : "not-allowed",
              transition: "all .15s",
            }}
          >
            {running
              ? <><Loader2 size={13} style={{ animation: "spin .7s linear infinite" }} /> Running…</>
              : <><Play size={13} /> Run pipeline</>}
          </button>

          <button
            onClick={handleDownload}
            disabled={!canDownload}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "8px 14px", borderRadius: 7, fontSize: 12, fontWeight: 600,
              background: canDownload ? "var(--green)" : "var(--surface-3)",
              color: canDownload ? "#fff" : "var(--text-3)",
              border: "none", cursor: canDownload ? "pointer" : "not-allowed",
              transition: "all .15s",
            }}
          >
            <Download size={13} />
            ZIP
          </button>
        </div>

        {/* Results summary */}
        {results.length > 0 && (
          <div style={{
            display: "flex", gap: 7, alignItems: "flex-start",
            padding: "9px 12px", borderRadius: 7,
            background: "var(--green)12", border: "1px solid var(--green)30",
            fontSize: 11,
          }}>
            <CheckCircle2 size={14} style={{ color: "var(--green)", flexShrink: 0 }} />
            <div>
              <div style={{ fontWeight: 600, color: "var(--green)" }}>
                Pipeline complete — {doneCount}/{results.length} files cleaned
              </div>
              <div style={{ color: "var(--text-2)", marginTop: 2 }}>
                Click ZIP to download all cleaned files as an archive.
              </div>
            </div>
          </div>
        )}
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
