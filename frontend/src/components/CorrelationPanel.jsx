/**
 * CorrelationPanel — interactive SVG heatmap with Pearson/Spearman/Cramér's V.
 */
import React, { useState, useCallback, useRef } from "react";
import { GitBranch, Loader2, AlertCircle, TrendingUp, TrendingDown, Minus, ChevronDown } from "lucide-react";
import { detectCorrelations } from "../services/api";

function corrColor(v) {
  if (v === null || v === undefined || isNaN(v)) return "#2a2a3a";
  const abs = Math.abs(v);
  if (v >= 0) return `rgb(${Math.round(30+(1-abs)*40)},${Math.round(100+(1-abs)*50)},${Math.round(220-(1-abs)*80)})`;
  return `rgb(${Math.round(220-(1-abs)*60)},${Math.round(80+(1-abs)*60)},${Math.round(80+(1-abs)*100)})`;
}
function strengthColor(s) {
  if (s === "very strong") return "#ef4444";
  if (s === "strong")      return "#f97316";
  if (s === "moderate")    return "#f59e0b";
  return "#6b7280";
}
function strLabel(r) {
  if (r >= 0.8) return "very strong"; if (r >= 0.6) return "strong";
  if (r >= 0.4) return "moderate";   if (r >= 0.2) return "weak"; return "negligible";
}

function Heatmap({ columns, matrix }) {
  const [tip, setTip] = useState(null);
  const n = columns.length;
  if (!n) return null;
  const LW   = Math.min(90, Math.max(50, 120 - n * 2));
  const CELL = Math.max(14, Math.min(36, Math.floor((560 - LW) / n)));
  const W = LW + CELL * n + 4, H = LW + CELL * n + 4;
  const FONT = Math.max(7, Math.min(11, CELL * 0.38));

  return (
    <div style={{ overflowX: "auto", position: "relative" }} onMouseLeave={() => setTip(null)}>
      <svg width={W} height={H} style={{ display: "block", cursor: "crosshair" }}>
        {columns.map((col, j) => (
          <text key={j} x={LW + CELL * j + CELL / 2} y={LW - 4} textAnchor="start" fontSize={FONT} fill="var(--text-2,#94a3b8)"
            transform={`rotate(-45,${LW + CELL * j + CELL / 2},${LW - 4})`}>
            {col.length > 14 ? col.slice(0, 13) + "…" : col}
          </text>
        ))}
        {columns.map((col, i) => (
          <text key={i} x={LW - 6} y={LW + CELL * i + CELL / 2} textAnchor="end" dominantBaseline="middle" fontSize={FONT} fill="var(--text-2,#94a3b8)">
            {col.length > 14 ? col.slice(0, 13) + "…" : col}
          </text>
        ))}
        {matrix.map((row, i) => row.map((val, j) => {
          const x = LW + CELL * j, y = LW + CELL * i;
          const show = CELL >= 18 && val !== null && !isNaN(val);
          return (
            <g key={`${i}-${j}`} onMouseEnter={e => val !== null && setTip({ x: e.clientX, y: e.clientY, a: columns[i], b: columns[j], v: val })}>
              <rect x={x+1} y={y+1} width={CELL-2} height={CELL-2} rx={2} fill={corrColor(val)} opacity={i === j ? 0.4 : 1} />
              {show && <text x={x+CELL/2} y={y+CELL/2} textAnchor="middle" dominantBaseline="middle"
                fontSize={Math.max(6,FONT-1)} fill={Math.abs(val??0)>0.5?"#fff":"var(--text-2,#94a3b8)"}
                style={{ pointerEvents: "none", fontWeight: 700 }}>{val===1.0?"1":val?.toFixed(2)}</text>}
            </g>
          );
        }))}
      </svg>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6 }}>
        <span style={{ fontSize: 9, color: "var(--text-3,#6b7280)" }}>−1</span>
        <div style={{ flex: 1, maxWidth: 160, height: 6, borderRadius: 99, background: "linear-gradient(to right,rgb(220,80,80),var(--surface-3,#2a2a3a),rgb(30,100,220))" }} />
        <span style={{ fontSize: 9, color: "var(--text-3,#6b7280)" }}>+1</span>
      </div>
      {tip && (
        <div style={{ position: "fixed", left: tip.x+12, top: tip.y-10, background: "var(--surface-1,#12121e)",
          border: "1px solid var(--border,#2a2a3a)", borderRadius: 6, padding: "6px 10px", fontSize: 11, zIndex: 9999,
          pointerEvents: "none", boxShadow: "0 4px 12px #0008" }}>
          <div style={{ fontWeight: 700, marginBottom: 2 }}>{tip.a} × {tip.b}</div>
          <div style={{ color: corrColor(tip.v), fontWeight: 800, fontSize: 14 }}>r = {tip.v?.toFixed(4)}</div>
          <div style={{ color: "var(--text-3,#6b7280)", fontSize: 9, marginTop: 2 }}>
            {tip.v >= 0 ? "positive" : "negative"} · {strLabel(Math.abs(tip.v))}
          </div>
        </div>
      )}
    </div>
  );
}

function PairRow({ pair }) {
  const DirIcon = pair.direction === "positive" ? TrendingUp : pair.direction === "negative" ? TrendingDown : Minus;
  const dc = pair.direction === "positive" ? "#22c55e" : pair.direction === "negative" ? "#ef4444" : "#6b7280";
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 60px 80px 90px", gap: 8,
      padding: "5px 10px", fontSize: 11, borderBottom: "1px solid var(--border,#1e1e2e)", alignItems: "center" }}>
      <span style={{ color: "var(--text-1,#e2e8f0)", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{pair.col_a}</span>
      <span style={{ color: "var(--text-1,#e2e8f0)", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{pair.col_b}</span>
      <span style={{ display: "flex", alignItems: "center", gap: 3, color: dc }}>
        <DirIcon size={11} /><span style={{ fontWeight: 800 }}>{pair.correlation.toFixed(3)}</span>
      </span>
      <div style={{ height: 4, background: "var(--surface-3,#2a2a3a)", borderRadius: 99, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${pair.abs_correlation * 100}%`, background: corrColor(pair.correlation), borderRadius: 99 }} />
      </div>
      <span style={{ fontSize: 9, fontWeight: 700, color: strengthColor(pair.strength),
        background: `${strengthColor(pair.strength)}15`, border: `1px solid ${strengthColor(pair.strength)}40`,
        borderRadius: 99, padding: "1px 7px", textAlign: "center" }}>{pair.strength}</span>
    </div>
  );
}

const METHODS = [
  { value: "auto", label: "Auto" }, { value: "pearson", label: "Pearson" },
  { value: "spearman", label: "Spearman" }, { value: "cramers_v", label: "Cramér's V" },
];

export default function CorrelationPanel({ sessionId }) {
  const [method,    setMethod]    = useState("auto");
  const [threshold, setThreshold] = useState(0.3);
  const [result,    setResult]    = useState(null);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState("");
  const [showPairs, setShowPairs] = useState(true);

  const run = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true); setError("");
    try { setResult(await detectCorrelations(sessionId, method, threshold)); }
    catch (e) { setError(e?.response?.data?.detail ?? e?.message ?? "Analysis failed."); }
    finally { setLoading(false); }
  }, [sessionId, method, threshold]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: "12px 0" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end",
        padding: "10px 14px", background: "var(--surface-2,#1a1a2e)", border: "1px solid var(--border,#2a2a3a)", borderRadius: 8 }}>
        <div>
          <div style={{ fontSize: 9, color: "var(--text-3,#6b7280)", marginBottom: 4, textTransform: "uppercase", letterSpacing: ".06em" }}>Method</div>
          <div style={{ display: "flex", gap: 4 }}>
            {METHODS.map(m => (
              <button key={m.value} onClick={() => setMethod(m.value)} style={{
                background: method === m.value ? "#6366f1" : "var(--surface-3,#2a2a3a)",
                color: method === m.value ? "#fff" : "var(--text-2,#94a3b8)",
                border: "1px solid " + (method === m.value ? "#6366f1" : "var(--border,#2a2a3a)"),
                borderRadius: 5, padding: "3px 9px", fontSize: 11, fontWeight: 600, cursor: "pointer" }}>{m.label}</button>
            ))}
          </div>
        </div>
        <div style={{ flex: 1, minWidth: 160 }}>
          <div style={{ fontSize: 9, color: "var(--text-3,#6b7280)", marginBottom: 4, textTransform: "uppercase", letterSpacing: ".06em" }}>
            Min |r|: <strong style={{ color: "var(--text-1,#e2e8f0)" }}>{threshold.toFixed(2)}</strong>
          </div>
          <input type="range" min={0.1} max={0.9} step={0.05} value={threshold}
            onChange={e => setThreshold(parseFloat(e.target.value))} style={{ width: "100%", accentColor: "#6366f1" }} />
        </div>
        <button onClick={run} disabled={loading || !sessionId} style={{
          background: "#6366f1", color: "#fff", border: "none", borderRadius: 6,
          padding: "6px 16px", fontSize: 12, fontWeight: 700, cursor: loading ? "not-allowed" : "pointer",
          display: "flex", alignItems: "center", gap: 6, opacity: loading ? 0.6 : 1 }}>
          {loading ? <><Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} />Analysing…</>
                   : <><GitBranch size={13} />Run Correlation</>}
        </button>
      </div>

      {error && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px",
          background: "#ef444415", border: "1px solid #ef444440", borderRadius: 6, color: "#ef4444", fontSize: 12 }}>
          <AlertCircle size={14} /> {error}
        </div>
      )}

      {result && (
        <>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", padding: "8px 14px",
            background: "var(--surface-2,#1a1a2e)", border: "1px solid var(--border,#2a2a3a)", borderRadius: 8 }}>
            {[{l:"Method",v:result.method},{l:"Columns",v:result.summary?.columns_analysed},
              {l:"Pairs",v:result.summary?.total_pairs},
              {l:`Strong (≥${threshold.toFixed(2)})`,v:result.summary?.strong_pairs_count,a:"#f59e0b"},
              {l:"Max |r|",v:result.summary?.max_correlation?.toFixed(3),a:"#6366f1"},
            ].map(({l,v,a}) => (
              <div key={l}>
                <div style={{ fontSize: 9, color: "var(--text-3,#6b7280)", textTransform: "uppercase", letterSpacing: ".05em" }}>{l}</div>
                <div style={{ fontSize: 14, fontWeight: 800, color: a ?? "var(--text-1,#e2e8f0)" }}>{v}</div>
              </div>
            ))}
          </div>

          {result.matrix?.length > 0 && (
            <div style={{ background: "var(--surface-2,#1a1a2e)", border: "1px solid var(--border,#2a2a3a)", borderRadius: 8, padding: "12px 14px" }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-2,#94a3b8)", marginBottom: 8 }}>Correlation Heatmap</div>
              <Heatmap columns={result.columns} matrix={result.matrix} />
            </div>
          )}

          {result.strong_pairs?.length > 0 && (
            <div style={{ background: "var(--surface-2,#1a1a2e)", border: "1px solid var(--border,#2a2a3a)", borderRadius: 8, overflow: "hidden" }}>
              <div onClick={() => setShowPairs(p => !p)} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", cursor: "pointer", borderBottom: showPairs ? "1px solid var(--border,#2a2a3a)" : "none" }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-2,#94a3b8)", flex: 1 }}>Strong Pairs ({result.strong_pairs.length})</span>
                <ChevronDown size={13} color="var(--text-3)" style={{ transform: showPairs ? "none" : "rotate(-90deg)", transition: "transform .2s" }} />
              </div>
              {showPairs && (
                <>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 60px 80px 90px", gap: 8, padding: "4px 10px",
                    background: "var(--surface-1,#12121e)", borderBottom: "1px solid var(--border,#2a2a3a)" }}>
                    {["Column A","Column B","r","Strength",""].map((h,i) => (
                      <span key={i} style={{ fontSize: 9, fontWeight: 700, color: "var(--text-3,#6b7280)", textTransform: "uppercase", letterSpacing: ".05em" }}>{h}</span>
                    ))}
                  </div>
                  <div style={{ maxHeight: 320, overflowY: "auto" }}>
                    {result.strong_pairs.map((p, i) => <PairRow key={i} pair={p} />)}
                  </div>
                </>
              )}
            </div>
          )}
        </>
      )}

      {!result && !loading && (
        <div style={{ padding: "32px 16px", textAlign: "center", color: "var(--text-3,#6b7280)", fontSize: 12,
          background: "var(--surface-2,#1a1a2e)", border: "1px dashed var(--border,#2a2a3a)", borderRadius: 8 }}>
          <GitBranch size={28} style={{ marginBottom: 8, opacity: 0.4 }} />
          <div>Select a method and click <strong>Run Correlation</strong></div>
          <div style={{ fontSize: 10, marginTop: 4 }}>Pearson & Spearman for numeric · Cramér's V for categorical</div>
        </div>
      )}
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}
