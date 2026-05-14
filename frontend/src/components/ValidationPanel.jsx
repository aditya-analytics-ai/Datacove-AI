/**
 * ValidationPanel — custom data validation rule builder.
 * Supports: not_null, positive, range, enum, regex, unique, max_length
 */
import React, { useState, useEffect } from "react";
import { Plus, Trash2, Play, Save, Loader2, CheckCircle, AlertCircle, ShieldCheck } from "lucide-react";
import { runValidation, saveRuleset, listRulesets } from "../services/api";

const RULE_TYPES = [
  { value: "not_null",   label: "Not null",    fields: [] },
  { value: "positive",   label: "Positive",    fields: [] },
  { value: "range",      label: "Range",       fields: ["min","max"] },
  { value: "enum",       label: "Enum values", fields: ["values"] },
  { value: "regex",      label: "Regex",       fields: ["pattern"] },
  { value: "unique",     label: "Unique",      fields: [] },
  { value: "max_length", label: "Max length",  fields: ["max"] },
];

function emptyRule() {
  return { column: "", type: "not_null", min: "", max: "", values: "", pattern: "" };
}

export default function ValidationPanel({ sessionId, columns }) {
  const [rules,      setRules]      = useState([emptyRule()]);
  const [result,     setResult]     = useState(null);
  const [loading,    setLoading]    = useState(false);
  const [saveModal,  setSaveModal]  = useState(false);
  const [saveName,   setSaveName]   = useState("");
  const [rulesets,   setRulesets]   = useState({});
  const [error,      setError]      = useState("");

  useEffect(() => {
    listRulesets(sessionId).then(r => setRulesets(r.rulesets ?? {})).catch(() => {});
  }, [sessionId]);

  function updateRule(i, key, val) {
    setRules(rs => rs.map((r, idx) => idx === i ? { ...r, [key]: val } : r));
  }
  function addRule()    { setRules(rs => [...rs, emptyRule()]); }
  function removeRule(i){ setRules(rs => rs.filter((_, idx) => idx !== i)); }

  function buildRulePayload() {
    return rules
      .filter(r => r.column && r.type)
      .map(r => {
        const base = { column: r.column, type: r.type };
        if (r.type === "range")  { if (r.min !== "") base.min = +r.min; if (r.max !== "") base.max = +r.max; }
        if (r.type === "enum")   base.values = r.values.split(",").map(v => v.trim());
        if (r.type === "regex")  base.pattern = r.pattern;
        if (r.type === "max_length") base.max = +r.max || 255;
        return base;
      });
  }

  async function handleRun() {
    const payload = buildRulePayload();
    if (!payload.length) { setError("Add at least one rule with a column selected."); return; }
    setLoading(true); setError(""); setResult(null);
    try {
      const res = await runValidation(sessionId, payload);
      setResult(res);
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Validation failed.");
    } finally { setLoading(false); }
  }

  async function handleSave() {
    const payload = buildRulePayload();
    if (!saveName.trim() || !payload.length) return;
    await saveRuleset(sessionId, saveName, payload);
    const updated = await listRulesets(sessionId);
    setRulesets(updated.rulesets ?? {});
    setSaveModal(false); setSaveName("");
  }

  function loadRuleset(name) {
    const loaded = (rulesets[name] ?? []).map(r => ({
      column: r.column ?? "", type: r.type ?? "not_null",
      min: r.min ?? "", max: r.max ?? "",
      values: Array.isArray(r.values) ? r.values.join(", ") : "",
      pattern: r.pattern ?? "",
    }));
    setRules(loaded.length ? loaded : [emptyRule()]);
    setResult(null);
  }

  return (
    <div className="vp-wrap">
      <div className="vp-header">
        <ShieldCheck size={14} color="var(--accent)" />
        <span className="vp-title">Validation Rules</span>
        {Object.keys(rulesets).length > 0 && (
          <select className="vp-ruleset-sel" onChange={e => e.target.value && loadRuleset(e.target.value)}
            defaultValue="">
            <option value="" disabled>Load saved ruleset…</option>
            {Object.keys(rulesets).map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        )}
      </div>

      <div className="vp-rules">
        {rules.map((rule, i) => {
          const rt = RULE_TYPES.find(t => t.value === rule.type);
          return (
            <div key={i} className="vp-rule">
              <select className="vp-sel vp-col-sel" value={rule.column}
                onChange={e => updateRule(i, "column", e.target.value)}>
                <option value="">Column…</option>
                {(columns ?? []).map(c => <option key={c} value={c}>{c}</option>)}
              </select>

              <select className="vp-sel" value={rule.type}
                onChange={e => updateRule(i, "type", e.target.value)}>
                {RULE_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>

              {rule.type === "range" && (
                <>
                  <input className="vp-input vp-input--sm" placeholder="min"
                    value={rule.min} onChange={e => updateRule(i, "min", e.target.value)} />
                  <input className="vp-input vp-input--sm" placeholder="max"
                    value={rule.max} onChange={e => updateRule(i, "max", e.target.value)} />
                </>
              )}
              {rule.type === "enum" && (
                <input className="vp-input" placeholder="val1, val2, val3"
                  value={rule.values} onChange={e => updateRule(i, "values", e.target.value)} />
              )}
              {rule.type === "regex" && (
                <input className="vp-input" placeholder="^[A-Z].*"
                  value={rule.pattern} onChange={e => updateRule(i, "pattern", e.target.value)} />
              )}
              {rule.type === "max_length" && (
                <input className="vp-input vp-input--sm" placeholder="255"
                  value={rule.max} onChange={e => updateRule(i, "max", e.target.value)} />
              )}

              <button className="vp-remove" onClick={() => removeRule(i)} title="Remove rule">
                <Trash2 size={11} />
              </button>
            </div>
          );
        })}

        <button className="vp-add-btn" onClick={addRule}>
          <Plus size={12} /> Add rule
        </button>
      </div>

      {error && <div className="vp-error"><AlertCircle size={12} />{error}</div>}

      <div className="vp-actions">
        <button className="vp-btn vp-btn--run" onClick={handleRun} disabled={loading}>
          {loading ? <Loader2 size={12} className="spin" /> : <Play size={12} />}
          Run validation
        </button>
        <button className="vp-btn vp-btn--save" onClick={() => setSaveModal(true)}>
          <Save size={12} /> Save ruleset
        </button>
      </div>

      {saveModal && (
        <div className="vp-save-modal">
          <input className="vp-input" placeholder="Ruleset name…"
            value={saveName} onChange={e => setSaveName(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleSave()} autoFocus />
          <button className="vp-btn vp-btn--run" onClick={handleSave}>Save</button>
          <button className="vp-btn vp-btn--save" onClick={() => setSaveModal(false)}>Cancel</button>
        </div>
      )}

      {result && (
        <div className="vp-results">
          <div className={`vp-summary ${result.passed ? "vp-summary--pass" : "vp-summary--fail"}`}>
            {result.passed
              ? <><CheckCircle size={13} /> All {result.results.length} rules passed</>
              : <><AlertCircle size={13} /> {result.total_violations} total violations across {result.results.filter(r => !r.passed).length} rules</>}
          </div>
          {(result.results ?? []).map((r, i) => (
            <div key={i} className={`vp-rule-result ${r.passed ? "vp-rule-result--pass" : "vp-rule-result--fail"}`}>
              <div className="vp-rule-result-header">
                {r.passed ? <CheckCircle size={11} color="#22c55e" /> : <AlertCircle size={11} color="#ef4444" />}
                <code>{r.rule?.column}</code>
                <span className="vp-rule-type">{r.rule?.type?.replace(/_/g," ")}</span>
                {!r.passed && <span className="vp-violations">{r.violations} violations ({r.violation_pct}%)</span>}
                {r.note && <span className="vp-note">{r.note}</span>}
              </div>
              {!r.passed && r.sample_rows?.length > 0 && (
                <div className="vp-samples">
                  {r.sample_rows.slice(0, 3).map((row, j) => (
                    <span key={j} className="vp-sample-row">
                      {Object.entries(row).slice(0, 3).map(([k, v]) => `${k}: ${v}`).join(" · ")}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <style>{`
        .vp-wrap{background:var(--surface-1);border-radius:12px;overflow:hidden;display:flex;flex-direction:column;gap:0}
        .vp-header{display:flex;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid var(--border)}
        .vp-title{font-size:13px;font-weight:700;color:var(--text-0);flex:1}
        .vp-ruleset-sel{font-size:11px;padding:3px 6px;border-radius:5px;border:1px solid var(--border);background:var(--surface-2);color:var(--text-1);cursor:pointer}
        .vp-rules{padding:10px 14px;display:flex;flex-direction:column;gap:6px;border-bottom:1px solid var(--border)}
        .vp-rule{display:flex;align-items:center;gap:5px;flex-wrap:wrap}
        .vp-sel{padding:4px 6px;border-radius:5px;border:1px solid var(--border);background:var(--surface-2);color:var(--text-0);font-size:11px;cursor:pointer}
        .vp-col-sel{min-width:100px}
        .vp-input{padding:4px 8px;border-radius:5px;border:1px solid var(--border);background:var(--surface-2);color:var(--text-0);font-size:11px;outline:none;min-width:80px}
        .vp-input--sm{width:60px;min-width:unset}
        .vp-input:focus{border-color:var(--accent)}
        .vp-remove{background:none;border:none;cursor:pointer;color:var(--text-3);padding:3px;border-radius:4px;display:flex}
        .vp-remove:hover{color:#ef4444}
        .vp-add-btn{display:inline-flex;align-items:center;gap:4px;font-size:11px;color:var(--accent);background:none;border:1px dashed var(--accent);border-radius:5px;padding:4px 10px;cursor:pointer;align-self:flex-start}
        .vp-error{display:flex;align-items:center;gap:6px;font-size:11px;color:#ef4444;background:rgba(239,68,68,.1);padding:7px 14px}
        .vp-actions{display:flex;gap:8px;padding:10px 14px}
        .vp-btn{display:inline-flex;align-items:center;gap:5px;padding:5px 12px;border-radius:6px;border:none;font-size:12px;font-weight:600;cursor:pointer}
        .vp-btn:disabled{opacity:.45;cursor:not-allowed}
        .vp-btn--run{background:var(--accent);color:#fff}
        .vp-btn--save{background:var(--surface-2);color:var(--text-1);border:1px solid var(--border)}
        .vp-btn--save:hover{background:var(--surface-3)}
        .vp-save-modal{display:flex;gap:6px;padding:0 14px 10px;align-items:center}
        .vp-results{padding:10px 14px;display:flex;flex-direction:column;gap:6px}
        .vp-summary{display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600;padding:8px 12px;border-radius:8px}
        .vp-summary--pass{color:#22c55e;background:rgba(34,197,94,.1)}
        .vp-summary--fail{color:#ef4444;background:rgba(239,68,68,.1)}
        .vp-rule-result{background:var(--surface-2);border-radius:8px;padding:8px 10px;display:flex;flex-direction:column;gap:4px}
        .vp-rule-result--pass{border-left:2px solid #22c55e}
        .vp-rule-result--fail{border-left:2px solid #ef4444}
        .vp-rule-result-header{display:flex;align-items:center;gap:6px;font-size:11px;flex-wrap:wrap}
        .vp-rule-result-header code{font-family:monospace;background:var(--surface-1);padding:1px 5px;border-radius:3px;color:#a0c4ff}
        .vp-rule-type{color:var(--text-2);text-transform:capitalize}
        .vp-violations{color:#ef4444;font-weight:700;margin-left:auto}
        .vp-note{color:var(--text-3);font-style:italic}
        .vp-samples{display:flex;flex-direction:column;gap:3px}
        .vp-sample-row{font-size:10px;color:var(--text-2);font-family:monospace;background:var(--surface-1);padding:2px 6px;border-radius:4px}
        @keyframes spin{to{transform:rotate(360deg)}}.spin{animation:spin .7s linear infinite}
      `}</style>
    </div>
  );
}
