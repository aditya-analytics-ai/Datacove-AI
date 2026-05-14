/**
 * AIInsightsPanel v3 — AI suggestions, issues, anomalies + new power features:
 *  - "Fix All" button queues all fix_action calls in one click
 *  - Outlier sparkline mini-charts in anomaly cards
 *  - Schema suggestions section (from upload inference)
 *  - Severity counts + color-coded strip
 */
import React, { useState } from "react";
import {
  Lightbulb, AlertCircle, TrendingUp, ChevronDown, ChevronRight,
  Play, Trash2, ShieldAlert, Hash, Binary, Calendar,
  Fingerprint, Zap, AlertTriangle, CheckCircle, Sparkles,
  Database, Wand2, Loader2, BarChart2,
} from "lucide-react";

const SEV_COLOR = { high:"#ef4444", medium:"#f59e0b", low:"#6b7280" };
const PRIORITY_COLOR = { high:"#ef4444", medium:"#f59e0b", low:"#6b7280" };

const DTYPE_COLOR = { float:"#6366f1", int:"#6366f1", bool:"#10b981", date:"#0891b2", category:"#f59e0b" };
const DTYPE_LABEL = { float:"Numeric", int:"Integer", bool:"Boolean", date:"Date", category:"Category" };

const ISSUE_META = {
  duplicate_rows:               { icon:Trash2,        label:"Duplicate Rows"          },
  missing_values:               { icon:Hash,          label:"Missing Values"          },
  extra_whitespace:             { icon:AlertCircle,   label:"Extra Whitespace"        },
  capitalisation_inconsistency: { icon:AlertCircle,   label:"Capitalisation Mismatch" },
  invalid_email:                { icon:ShieldAlert,   label:"Invalid Email"           },
  invalid_phone:                { icon:ShieldAlert,   label:"Invalid Phone"           },
  mixed_data_types:             { icon:Binary,        label:"Mixed Data Types"        },
  category_inconsistency:       { icon:AlertCircle,   label:"Category Inconsistency"  },
  all_null_column:              { icon:Trash2,        label:"All-Null Column"         },
  constant_column:              { icon:Zap,           label:"Constant Column"         },
  empty_string_values:          { icon:Hash,          label:"Empty String Values"     },
  negative_in_positive_col:     { icon:AlertTriangle, label:"Unexpected Negatives"    },
  encoding_garbage:             { icon:Zap,           label:"Encoding Garbage"        },
  likely_id_column:             { icon:Fingerprint,   label:"Likely ID Column"        },
  date_out_of_range:            { icon:Calendar,      label:"Date Out of Range"       },
  mixed_date_formats:           { icon:Calendar,      label:"Mixed Date Formats"      },
  unparseable_dates:            { icon:Calendar,      label:"Unparseable Dates"       },
};

function Badge({ label, color }) {
  return (
    <span style={{ fontSize:10, fontWeight:700, padding:"2px 6px", borderRadius:99,
      background:color+"22", color, letterSpacing:".04em", textTransform:"uppercase" }}>
      {label}
    </span>
  );
}

function Section({ icon:Icon, title, badge, action, children }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="aip-section">
      <div className="aip-section-header" onClick={() => setOpen(o => !o)}>
        <Icon size={14} />
        <span className="aip-section-title">{title}</span>
        {badge != null && <span className="aip-section-badge">{badge}</span>}
        {action && <span onClick={e => e.stopPropagation()}>{action}</span>}
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
      </div>
      {open && <div className="aip-section-body">{children}</div>}
    </div>
  );
}

// Mini sparkline bar chart for outlier visualization
// Accepts data as either:
//   float[]   — normalised heights 0–1 (what the backend sends)
//   object[]  — {bin_start, bin_end, count, height} legacy format
function Sparkline({ data, p5, p95 }) {
  if (!data?.length) return null;
  const maxH = 28;

  // Normalise: if items are plain numbers, use them directly as heights
  const bars = data.map((item, i) => {
    if (typeof item === "number") {
      return { height: item, isOutlier: false, title: `Bar ${i + 1}` };
    }
    // Legacy object format
    const isOutlier = (p5 != null && item.bin_end <= p5) || (p95 != null && item.bin_start >= p95);
    return { height: item.height ?? 0, isOutlier, title: `${item.bin_start}–${item.bin_end}: ${item.count}` };
  });

  return (
    <div className="aip-sparkline">
      {bars.map((bar, i) => (
        <div key={i} className="aip-spark-bar-wrap" title={bar.title}>
          <div className="aip-spark-bar"
            style={{
              height: Math.max(2, (bar.height || 0) * maxH),
              background: bar.isOutlier ? "#ef4444" : "var(--accent)"
            }} />
        </div>
      ))}
    </div>
  );
}

function SeveritySummary({ issues }) {
  const counts = { high:0, medium:0, low:0 };
  issues.forEach(i => { if (counts[i.severity] != null) counts[i.severity]++; });
  if (Object.values(counts).every(v => v === 0)) return null;
  return (
    <div className="aip-sev-strip">
      {Object.entries(counts).filter(([,v]) => v > 0).map(([sev, cnt]) => (
        <span key={sev} className="aip-sev-pill"
          style={{ background:SEV_COLOR[sev]+"22", color:SEV_COLOR[sev] }}>
          {cnt} {sev}
        </span>
      ))}
    </div>
  );
}

export default function AIInsightsPanel({ analysis, onApplySuggestion, onFixAll, schemaSuggestions, onApplySchema }) {
  const [fixingAll, setFixingAll] = useState(false);

  if (!analysis && !schemaSuggestions?.length) {
    return (
      <div className="aip-panel aip-panel--empty">
        <Lightbulb size={22} color="var(--text-3)" />
        <p>Run analysis to see AI insights.</p>
      </div>
    );
  }

  const { suggestions=[], issues=[], anomalies: anomaliesObj=[] } = analysis ?? {};
  const anomalies = Array.isArray(anomaliesObj) ? anomaliesObj : (anomaliesObj?.anomalies ?? []);

  function fixFromIssue(iss) {
    return { action:iss.fix_action, column:iss.column, params:iss.column ? { column:iss.column } : {} };
  }

  async function handleFixAll() {
    if (!onFixAll) return;
    const fixable = issues.filter(i => i.fix_action);
    if (!fixable.length) return;
    setFixingAll(true);
    try { await onFixAll(fixable.map(fixFromIssue)); }
    finally { setFixingAll(false); }
  }

  const highCount  = issues.filter(i => i.severity==="high").length;
  const issueBadge = issues.length > 0 ? `${issues.length}${highCount > 0 ? ` · ${highCount} high`:""}` : "0";
  const fixable    = issues.filter(i => i.fix_action).length;

  const FixAllBtn = onFixAll && fixable > 0 && (
    <button className="aip-fix-all-btn" disabled={fixingAll} onClick={handleFixAll}
      title={`Fix all ${fixable} issues automatically`}>
      {fixingAll ? <Loader2 size={10} className="spin"/> : <Wand2 size={10}/>}
      Fix All ({fixable})
    </button>
  );

  return (
    <div className="aip-panel">

      {/* ── Schema Suggestions (from upload inference) ────────────────── */}
      {schemaSuggestions?.length > 0 && (
        <Section icon={Database} title="Suggested Type Casts" badge={schemaSuggestions.length}
          action={onApplySchema && (
            <button className="aip-apply-all-btn" onClick={() => onApplySchema(schemaSuggestions)}>
              <Sparkles size={9}/> Apply All
            </button>
          )}>
          <p className="aip-desc" style={{marginBottom:6}}>
            Detected on upload — apply to get correct column types instantly.
          </p>
          {schemaSuggestions.map((s, i) => (
            <div key={i} className="aip-schema-row">
              <span className="aip-chip">{s.column}</span>
              <span className="aip-schema-arrow">→</span>
              <span className="aip-schema-type" style={{color: DTYPE_COLOR[s.suggested_dtype] ?? "var(--text-1)"}}>
                {DTYPE_LABEL[s.suggested_dtype] ?? s.suggested_dtype}
              </span>
              <span className="aip-schema-conf">{Math.round((s.confidence??0)*100)}%</span>
              <span className="aip-desc" style={{flex:1, minWidth:0, overflow:"hidden", textOverflow:"ellipsis",
                whiteSpace:"nowrap"}}>{s.reason}</span>
              {onApplySchema && (
                <button className="aip-fix-btn"
                  style={{borderColor:(DTYPE_COLOR[s.suggested_dtype]??"#6b7280")+"55",
                          color:DTYPE_COLOR[s.suggested_dtype]??"#6b7280"}}
                  onClick={() => onApplySchema([s])}>
                  Cast
                </button>
              )}
            </div>
          ))}
        </Section>
      )}

      {/* ── AI Suggestions ──────────────────────────────────────────────── */}
      {analysis && (
        <Section icon={Lightbulb} title="AI Suggestions" badge={suggestions.length}>
          {suggestions.length === 0
            ? <p className="aip-empty">No suggestions — dataset looks clean!</p>
            : suggestions.map((s, i) => (
              <div key={i} className="aip-sug-card">
                <div className="aip-sug-top">
                  <span className="aip-sug-title">{s.title}</span>
                  <Badge label={s.priority} color={PRIORITY_COLOR[s.priority]??"#6b7280"} />
                </div>
                <p className="aip-desc">{s.description}</p>
                {s.column && <span className="aip-chip">col: {s.column}</span>}
                {onApplySuggestion && (
                  <button className="aip-apply-btn"
                    onClick={() => onApplySuggestion({action:s.action, column:s.column, params:s.params??{}})}>
                    <Play size={9}/> Apply
                  </button>
                )}
              </div>
            ))}
        </Section>
      )}

      {/* ── Detected Issues ─────────────────────────────────────────────── */}
      {analysis && (
        <Section icon={AlertCircle} title="Detected Issues" badge={issueBadge} action={FixAllBtn}>
          {issues.length === 0
            ? <p className="aip-empty">No issues detected.</p>
            : <>
                <SeveritySummary issues={issues} />
                {issues.map((iss, i) => {
                  const meta     = ISSUE_META[iss.type] ?? { icon:AlertCircle, label:iss.type?.replace(/_/g," ") };
                  const IIcon    = meta.icon;
                  const sevColor = SEV_COLOR[iss.severity] ?? "#6b7280";
                  return (
                    <div key={i} className="aip-issue-row">
                      <div className="aip-issue-left">
                        <IIcon size={12} color={sevColor} style={{flexShrink:0, marginTop:2}}/>
                      </div>
                      <div className="aip-issue-body">
                        <div className="aip-issue-top">
                          <span className="aip-issue-type">{meta.label}</span>
                          {iss.column && <span className="aip-chip">{iss.column}</span>}
                          <Badge label={iss.severity} color={sevColor}/>
                          {iss.count != null && <span className="aip-count">{iss.count.toLocaleString()} rows</span>}
                        </div>
                        <p className="aip-desc">{iss.description}</p>
                        {iss.fix_action && onApplySuggestion && (
                          <button className="aip-fix-btn"
                            style={{borderColor:sevColor+"55", color:sevColor}}
                            onClick={() => onApplySuggestion(fixFromIssue(iss))}>
                            <CheckCircle size={9}/> Fix: {iss.fix_action.replace(/_/g," ")}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </>}
        </Section>
      )}

      {/* ── Anomalies with sparklines ────────────────────────────────────── */}
      {analysis && (
        <Section icon={TrendingUp} title="Anomalies" badge={anomalies.length}>
          {anomalies.length === 0
            ? <p className="aip-empty">No anomalies detected.</p>
            : anomalies.map((a, i) => {
                const colProfile = analysis.profile?.columns_profile?.find(c => c.column === a.column);
                const sparkData  = colProfile?.numeric_stats?.sparkline;
                const p5         = colProfile?.numeric_stats?.p5;
                const p95        = colProfile?.numeric_stats?.p95;
                return (
                  <div key={i} className="aip-issue-row">
                    <div className="aip-issue-left">
                      <TrendingUp size={12} color="#a78bfa" style={{flexShrink:0, marginTop:2}}/>
                    </div>
                    <div className="aip-issue-body">
                      <div className="aip-issue-top">
                        {a.column && <span className="aip-chip">{a.column}</span>}
                        {a.outlier_count > 0 && (
                          <span className="aip-count" style={{color:"#a78bfa"}}>
                            {a.outlier_count} outlier{a.outlier_count>1?"s":""}
                          </span>
                        )}
                      </div>
                      <p className="aip-desc">{a.description}</p>
                      {sparkData?.length > 0 && (
                        <div className="aip-sparkline-wrap">
                          <span className="aip-spark-label">Distribution</span>
                          <Sparkline data={sparkData} p5={p5} p95={p95}/>
                          {(p5!=null||p95!=null) && (
                            <span className="aip-spark-range">
                              p5:{p5?.toFixed(1)} p95:{p95?.toFixed(1)}
                            </span>
                          )}
                        </div>
                      )}
                      {a.methods?.length > 0 && (
                        <div className="aip-methods">
                          {a.methods.map(m => <span key={m} className="aip-method-badge">{m}</span>)}
                        </div>
                      )}
                      {onApplySuggestion && a.column && (
                        <button className="aip-fix-btn" style={{borderColor:"#a78bfa55",color:"#a78bfa"}}
                          onClick={() => onApplySuggestion({action:"replace_outliers",column:a.column,params:{column:a.column,strategy:"median"}})}>
                          <CheckCircle size={9}/> Replace with median
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
        </Section>
      )}

      <style>{`
        .aip-panel          { display:flex; flex-direction:column; gap:0; background:var(--surface-1); border-radius:12px; overflow:hidden; }
        .aip-panel--empty   { align-items:center; justify-content:center; padding:36px 20px; gap:10px; }
        .aip-panel--empty p { color:var(--text-2); font-size:13px; margin:0; }
        .aip-section        { border-bottom:1px solid var(--border); }
        .aip-section:last-child { border-bottom:none; }
        .aip-section-header { width:100%; display:flex; align-items:center; gap:7px; padding:10px 14px;
                              background:none; border:none; cursor:pointer; color:var(--text-1); font-size:13px; font-weight:600; }
        .aip-section-header:hover { background:var(--surface-2); }
        .aip-section-title  { flex:1; text-align:left; }
        .aip-section-badge  { background:var(--surface-3); color:var(--text-2); font-size:11px; font-weight:700; border-radius:99px; padding:1px 8px; }
        .aip-section-body   { padding:4px 14px 12px; display:flex; flex-direction:column; gap:7px; }
        .aip-empty          { color:var(--text-3); font-size:12px; margin:0; }
        .aip-sug-card       { background:var(--surface-2); border-radius:8px; padding:9px 11px; display:flex; flex-direction:column; gap:4px; }
        .aip-sug-top        { display:flex; align-items:center; gap:8px; }
        .aip-sug-title      { font-size:12px; font-weight:600; color:var(--text-0); flex:1; }
        .aip-desc           { font-size:11px; color:var(--text-2); margin:0; line-height:1.5; }
        .aip-chip           { font-size:10px; background:var(--surface-3); color:var(--text-2); padding:1px 5px; border-radius:4px; font-family:monospace; }
        .aip-count          { font-size:10px; color:var(--text-3); margin-left:auto; }
        .aip-apply-btn      { align-self:flex-start; display:inline-flex; align-items:center; gap:4px; padding:3px 9px; border-radius:5px;
                              background:var(--accent); color:#fff; border:none; font-size:11px; font-weight:600; cursor:pointer; margin-top:2px; }
        .aip-apply-btn:hover { filter:brightness(1.1); }
        .aip-apply-all-btn  { display:inline-flex; align-items:center; gap:4px; padding:2px 8px; border-radius:5px;
                              background:var(--accent); color:#fff; border:none; font-size:10px; font-weight:700; cursor:pointer; }
        .aip-apply-all-btn:hover { filter:brightness(1.1); }
        .aip-fix-all-btn    { display:inline-flex; align-items:center; gap:4px; padding:2px 8px; border-radius:5px;
                              background:#7c3aed; color:#fff; border:none; font-size:10px; font-weight:700; cursor:pointer; }
        .aip-fix-all-btn:hover { filter:brightness(1.1); }
        .aip-fix-all-btn:disabled { opacity:.5; cursor:not-allowed; }
        .aip-fix-btn        { align-self:flex-start; display:inline-flex; align-items:center; gap:4px; padding:2px 8px; border-radius:5px;
                              background:transparent; border:1px solid; font-size:10px; font-weight:600; cursor:pointer; margin-top:3px; }
        .aip-fix-btn:hover  { opacity:.75; }
        .aip-issue-row      { display:flex; gap:7px; }
        .aip-issue-left     { padding-top:1px; }
        .aip-issue-body     { flex:1; display:flex; flex-direction:column; gap:3px; }
        .aip-issue-top      { display:flex; align-items:center; gap:5px; flex-wrap:wrap; }
        .aip-issue-type     { font-size:12px; font-weight:600; color:var(--text-1); }
        .aip-sev-strip      { display:flex; gap:5px; flex-wrap:wrap; margin-bottom:4px; }
        .aip-sev-pill       { font-size:10px; font-weight:700; padding:2px 7px; border-radius:99px; text-transform:capitalize; }
        .aip-methods        { display:flex; gap:4px; flex-wrap:wrap; margin-top:2px; }
        .aip-method-badge   { font-size:9px; background:rgba(167,139,250,.15); color:#a78bfa; padding:1px 5px; border-radius:4px; font-weight:600; }
        /* Schema suggestions */
        .aip-schema-row     { display:flex; align-items:center; gap:6px; padding:4px 0; flex-wrap:wrap; }
        .aip-schema-arrow   { color:var(--text-3); font-size:11px; }
        .aip-schema-type    { font-size:11px; font-weight:700; }
        .aip-schema-conf    { font-size:10px; color:var(--text-3); background:var(--surface-3); padding:1px 5px; border-radius:4px; }
        /* Sparkline */
        .aip-sparkline-wrap { display:flex; align-items:flex-end; gap:6px; margin:3px 0; }
        .aip-spark-label    { font-size:9px; color:var(--text-3); text-transform:uppercase; letter-spacing:.06em; white-space:nowrap; }
        .aip-sparkline      { display:flex; align-items:flex-end; gap:1px; height:28px; }
        .aip-spark-bar-wrap { display:flex; align-items:flex-end; height:28px; cursor:default; }
        .aip-spark-bar      { width:7px; border-radius:2px 2px 0 0; transition:opacity .15s; }
        .aip-spark-bar-wrap:hover .aip-spark-bar { opacity:.7; }
        .aip-spark-range    { font-size:9px; color:var(--text-3); white-space:nowrap; }
        @keyframes spin { to { transform:rotate(360deg); } }
        .spin { animation:spin .7s linear infinite; }
      `}</style>
    </div>
  );
}
