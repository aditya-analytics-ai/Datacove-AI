/**
 * DataIntelligencePanel — two-tab panel: Referential Integrity + Column Similarity.
 */
import React, { useState, useCallback } from "react";
import { Link2, Copy, GitMerge, AlertTriangle, CheckCircle2, Loader2, ChevronDown, ChevronRight, Layers } from "lucide-react";
import { checkReferentialIntegrity, findSimilarColumns } from "../services/api";

function SevBadge({ s }) {
  const m = { high:{bg:"#ef444415",c:"#ef4444",b:"#ef444440"}, medium:{bg:"#f59e0b15",c:"#f59e0b",b:"#f59e0b40"}, low:{bg:"#6b728015",c:"#6b7280",b:"#6b728040"} }[s] ?? {bg:"#6b728015",c:"#6b7280",b:"#6b728040"};
  return <span style={{ fontSize: 9, fontWeight: 700, padding: "1px 7px", borderRadius: 99, background: m.bg, color: m.c, border: `1px solid ${m.b}`, textTransform: "uppercase", letterSpacing: ".05em" }}>{s}</span>;
}

function EmptyState({ icon: Icon, title, subtitle }) {
  return (
    <div style={{ padding: "40px 16px", textAlign: "center", color: "var(--text-3,#6b7280)",
      border: "1px dashed var(--border,#2a2a3a)", borderRadius: 8 }}>
      <Icon size={28} style={{ marginBottom: 8, opacity: 0.3 }} />
      <div style={{ fontSize: 12, fontWeight: 600 }}>{title}</div>
      <div style={{ fontSize: 10, marginTop: 4 }}>{subtitle}</div>
    </div>
  );
}

// ── Referential Integrity ─────────────────────────────────────────────────────
function ReferentialTab({ sessionId }) {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [open, setOpen] = useState({});

  const run = useCallback(async () => {
    setLoading(true); setError("");
    try { setResult(await checkReferentialIntegrity(sessionId)); }
    catch (e) { setError(e?.response?.data?.detail ?? e?.message ?? "Check failed."); }
    finally { setLoading(false); }
  }, [sessionId]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <button onClick={run} disabled={loading} style={{ background: "#6366f1", color: "#fff", border: "none", borderRadius: 6, padding: "5px 14px", fontSize: 11, fontWeight: 700, cursor: loading ? "not-allowed" : "pointer", display: "flex", alignItems: "center", gap: 6, opacity: loading ? 0.6 : 1 }}>
          {loading ? <><Loader2 size={12} style={{ animation: "spin 1s linear infinite" }} />Running…</> : <><Link2 size={12} />Run Integrity Check</>}
        </button>
        {result && <span style={{ fontSize: 11, color: "var(--text-3,#6b7280)" }}>{result.summary.total_violations === 0 ? "✓ No issues found" : `${result.summary.total_violations} issue(s)`}</span>}
      </div>

      {error && <div style={{ display: "flex", gap: 8, padding: "7px 10px", background: "#ef444415", border: "1px solid #ef444440", borderRadius: 6, color: "#ef4444", fontSize: 11 }}><AlertTriangle size={13} />{error}</div>}

      {result && (
        <>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {[["PK cols",result.summary.pk_columns_found,"#6366f1"],["FK cols",result.summary.fk_columns_found,"#0891b2"],
              ["Dup PKs",result.summary.duplicate_pk_values,"#ef4444"],["Orphaned",result.summary.orphaned_fk_values,"#f97316"],
              ["Null FKs",result.summary.null_fk_values,"#f59e0b"]].map(([l,v,c]) => (
              <div key={l} style={{ background: "var(--surface-2,#1a1a2e)", border: `1px solid ${c}30`, borderRadius: 7, padding: "4px 10px" }}>
                <div style={{ fontSize: 14, fontWeight: 800, color: c }}>{v}</div>
                <div style={{ fontSize: 9, color: "var(--text-3,#6b7280)", textTransform: "uppercase" }}>{l}</div>
              </div>
            ))}
          </div>

          {result.violations.length === 0
            ? <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 12px", background: "#22c55e10", border: "1px solid #22c55e30", borderRadius: 7, color: "#22c55e", fontSize: 12 }}><CheckCircle2 size={14} />No violations detected.</div>
            : result.violations.map((v, i) => (
              <div key={i} style={{ background: "var(--surface-2,#1a1a2e)", border: "1px solid var(--border,#2a2a3a)", borderLeft: `3px solid ${v.severity==="high"?"#ef4444":"#f59e0b"}`, borderRadius: 7, overflow: "hidden" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 10px", cursor: "pointer" }} onClick={() => setOpen(o => ({...o,[i]:!o[i]}))}>
                  <SevBadge s={v.severity} />
                  <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-1,#e2e8f0)", flex: 1 }}>
                    {v.type==="duplicate_pk"?`Duplicate PK: ${v.column}`:v.type==="null_fk"?`Null FK: ${v.column}`:`Orphaned FK: ${v.column} → ${v.ref_column}`}
                  </span>
                  <span style={{ fontSize: 10, color: "var(--text-3,#6b7280)" }}>{v.count.toLocaleString()} rows</span>
                  {open[i]?<ChevronDown size={12}/>:<ChevronRight size={12}/>}
                </div>
                {open[i] && (
                  <div style={{ padding: "6px 10px 10px", borderTop: "1px solid var(--border,#2a2a3a)" }}>
                    <p style={{ fontSize: 11, color: "var(--text-2,#94a3b8)", margin: "0 0 6px" }}>{v.description}</p>
                    {v.sample_values?.length > 0 && (
                      <div style={{ fontSize: 10, color: "var(--text-3,#6b7280)" }}>
                        Samples: {v.sample_values.slice(0,5).map(s => <code key={s} style={{ background:"var(--surface-3,#2a2a3a)",padding:"1px 5px",borderRadius:3,marginRight:4 }}>{s}</code>)}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
        </>
      )}
      {!result && !loading && <EmptyState icon={Link2} title="Referential Integrity Checker" subtitle="Auto-detects PK/FK columns and flags orphaned values, duplicate PKs, null FKs" />}
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}

// ── Column Similarity ─────────────────────────────────────────────────────────
const SUG_META = {
  drop_duplicate:{color:"#ef4444",icon:Copy,label:"Likely duplicate"},
  merge:{color:"#6366f1",icon:GitMerge,label:"Suggest merge"},
  review:{color:"#f59e0b",icon:Layers,label:"Review"},
};

function SimilarityTab({ sessionId, onTransform }) {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [open, setOpen] = useState({});

  const run = useCallback(async () => {
    setLoading(true); setError("");
    try { setResult(await findSimilarColumns(sessionId)); }
    catch (e) { setError(e?.response?.data?.detail ?? e?.message ?? "Analysis failed."); }
    finally { setLoading(false); }
  }, [sessionId]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <button onClick={run} disabled={loading} style={{ background: "#6366f1", color: "#fff", border: "none", borderRadius: 6, padding: "5px 14px", fontSize: 11, fontWeight: 700, cursor: loading?"not-allowed":"pointer", display: "flex", alignItems: "center", gap: 6, opacity: loading?0.6:1 }}>
          {loading?<><Loader2 size={12} style={{animation:"spin 1s linear infinite"}}/>Running…</>:<><GitMerge size={12}/>Find Similar Columns</>}
        </button>
        {result && <span style={{ fontSize: 11, color: "var(--text-3,#6b7280)" }}>{result.similar_pairs_found===0?"✓ All distinct":`${result.similar_pairs_found} group(s)`}</span>}
      </div>

      {error && <div style={{ display: "flex", gap: 8, padding: "7px 10px", background: "#ef444415", border: "1px solid #ef444440", borderRadius: 6, color: "#ef4444", fontSize: 11 }}><AlertTriangle size={13}/>{error}</div>}

      {result?.groups?.length === 0 && <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 12px", background: "#22c55e10", border: "1px solid #22c55e30", borderRadius: 7, color: "#22c55e", fontSize: 12 }}><CheckCircle2 size={14}/>All column names appear distinct.</div>}

      {result?.groups?.map((g, i) => {
        const meta = SUG_META[g.suggestion] ?? SUG_META.review;
        const Icon = meta.icon;
        return (
          <div key={i} style={{ background: "var(--surface-2,#1a1a2e)", border: "1px solid var(--border,#2a2a3a)", borderLeft: `3px solid ${meta.color}`, borderRadius: 7, overflow: "hidden" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 10px", cursor: "pointer" }} onClick={() => setOpen(o => ({...o,[i]:!o[i]}))}>
              <span style={{ display:"flex",alignItems:"center",justifyContent:"center",width:20,height:20,borderRadius:4,background:`${meta.color}20`,flexShrink:0 }}><Icon size={11} color={meta.color}/></span>
              <span style={{ fontSize:11,fontWeight:700,color:"var(--text-1,#e2e8f0)",flex:1 }}>{g.columns.join(" · ")}</span>
              <span style={{ fontSize:9,background:`${meta.color}15`,color:meta.color,border:`1px solid ${meta.color}30`,borderRadius:99,padding:"1px 7px",fontWeight:700 }}>{meta.label}</span>
              <span style={{ fontSize:10,color:"var(--text-3,#6b7280)" }}>{g.combined_score.toFixed(0)}/100</span>
              {open[i]?<ChevronDown size={12}/>:<ChevronRight size={12}/>}
            </div>
            {open[i] && (
              <div style={{ padding:"8px 10px 10px",borderTop:"1px solid var(--border,#2a2a3a)" }}>
                <p style={{ fontSize:11,color:"var(--text-2,#94a3b8)",margin:"0 0 8px" }}>{g.reason}</p>
                <div style={{ display:"flex",gap:12,marginBottom:8 }}>
                  {[["Name sim",g.name_score.toFixed(0)+"/100","#6366f1"],["Value overlap",(g.value_overlap*100).toFixed(0)+"%","#0891b2"]].map(([l,v,c])=>(
                    <div key={l}><div style={{fontSize:9,color:"var(--text-3,#6b7280)",textTransform:"uppercase"}}>{l}</div><div style={{fontSize:13,fontWeight:800,color:c}}>{v}</div></div>
                  ))}
                </div>
                {g.columns.map(col => g.sample?.[col]?.length>0 && (
                  <div key={col} style={{fontSize:10,marginBottom:3}}>
                    <strong style={{color:"var(--text-2,#94a3b8)"}}>{col}:</strong>{" "}
                    {g.sample[col].map(v=><code key={v} style={{background:"var(--surface-3,#2a2a3a)",padding:"1px 5px",borderRadius:3,marginRight:3}}>{v}</code>)}
                  </div>
                ))}
                {g.suggestion==="drop_duplicate" && onTransform && g.columns.length>=2 && (
                  <div style={{marginTop:8,display:"flex",gap:6}}>
                    {g.columns.slice(1).map(col=>(
                      <button key={col} onClick={()=>onTransform("drop_column",{column:col})} style={{ background:"#ef444415",color:"#ef4444",border:"1px solid #ef444440",borderRadius:5,padding:"3px 9px",fontSize:10,fontWeight:700,cursor:"pointer" }}>Drop '{col}'</button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}

      {!result && !loading && <EmptyState icon={GitMerge} title="Column Similarity Detector" subtitle="Finds first_name / FirstName / fname — suggests merges or drops" />}
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────
const TABS = [
  { id: "integrity",  label: "Referential Integrity", icon: Link2 },
  { id: "similarity", label: "Column Similarity",     icon: GitMerge },
];

export default function DataIntelligencePanel({ sessionId, onTransform }) {
  const [tab, setTab] = useState("integrity");
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", borderBottom: "1px solid var(--border,#2a2a3a)", marginBottom: 12 }}>
        {TABS.map(t => {
          const Icon = t.icon; const active = tab === t.id;
          return (
            <button key={t.id} onClick={() => setTab(t.id)} style={{ display:"flex",alignItems:"center",gap:5,padding:"6px 12px",fontSize:11,fontWeight:active?700:500,background:"none",border:"none",borderBottom:active?"2px solid #6366f1":"2px solid transparent",color:active?"#6366f1":"var(--text-3,#6b7280)",cursor:"pointer" }}>
              <Icon size={12}/>{t.label}
            </button>
          );
        })}
      </div>
      {tab === "integrity"  && <ReferentialTab sessionId={sessionId} />}
      {tab === "similarity" && <SimilarityTab  sessionId={sessionId} onTransform={onTransform} />}
    </div>
  );
}
