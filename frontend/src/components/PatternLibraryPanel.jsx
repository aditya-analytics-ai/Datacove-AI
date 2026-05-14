/**
 * PatternLibraryPanel — browse 50+ named patterns, validate columns, test values.
 *
 * Three sub-views:
 *   Browse  — searchable pattern catalogue grouped by category
 *   Validate — pick a column + pattern → see match %, sample hits/misses
 *   Test    — type a value, pick a pattern → instant match result
 */
import React, { useState, useEffect, useCallback, useMemo } from "react";
import { Search, CheckCircle2, XCircle, Loader2, AlertCircle, BookOpen, ChevronRight, ChevronDown } from "lucide-react";
import { listPatterns, validatePattern, testPattern } from "../services/api";

const CAT_COLORS = {
  Financial:  "#22c55e", Identity:  "#6366f1", Network:   "#0891b2",
  Telecom:    "#f59e0b", Vehicle:   "#f97316", Retail:    "#a855f7",
  Geographic: "#06b6d4", Dates:     "#ec4899", Healthcare:"#ef4444",
  Codes:      "#64748b",
};

function CatBadge({ cat }) {
  const c = CAT_COLORS[cat] ?? "#6b7280";
  return (
    <span style={{ fontSize: 9, fontWeight: 700, padding: "1px 6px", borderRadius: 4,
      background: `${c}18`, color: c, border: `1px solid ${c}35`, whiteSpace: "nowrap" }}>
      {cat}
    </span>
  );
}

// ── Browse tab ────────────────────────────────────────────────────────────────
function BrowseTab({ patterns, onSelect }) {
  const [search, setSearch] = useState("");
  const [openCats, setOpenCats] = useState({});

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return q ? patterns.filter(p =>
      p.name.includes(q) || p.description.toLowerCase().includes(q) || p.category.toLowerCase().includes(q)
    ) : patterns;
  }, [patterns, search]);

  const grouped = useMemo(() => {
    const g = {};
    filtered.forEach(p => { (g[p.category] = g[p.category] || []).push(p); });
    return g;
  }, [filtered]);

  const toggleCat = cat => setOpenCats(o => ({...o, [cat]: !o[cat]}));
  const allCats   = Object.keys(grouped);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ position: "relative" }}>
        <Search size={12} style={{ position: "absolute", left: 9, top: "50%", transform: "translateY(-50%)", color: "var(--text-3,#6b7280)" }} />
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Search patterns…"
          style={{ width: "100%", paddingLeft: 28, paddingRight: 10, paddingTop: 6, paddingBottom: 6,
            background: "var(--surface-3,#2a2a3a)", border: "1px solid var(--border,#2a2a3a)",
            borderRadius: 6, color: "var(--text-1,#e2e8f0)", fontSize: 11, outline: "none", boxSizing: "border-box" }} />
      </div>
      <div style={{ fontSize: 10, color: "var(--text-3,#6b7280)" }}>
        {filtered.length} pattern{filtered.length !== 1 ? "s" : ""} · {allCats.length} categor{allCats.length !== 1 ? "ies" : "y"}
      </div>
      {allCats.map(cat => {
        const open = openCats[cat] !== false; // default open
        const c    = CAT_COLORS[cat] ?? "#6b7280";
        return (
          <div key={cat} style={{ border: "1px solid var(--border,#2a2a3a)", borderRadius: 7, overflow: "hidden", background: "var(--surface-2,#1a1a2e)" }}>
            <div onClick={() => toggleCat(cat)} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", cursor: "pointer", borderLeft: `3px solid ${c}` }}>
              <span style={{ flex: 1, fontSize: 11, fontWeight: 700, color: "var(--text-1,#e2e8f0)" }}>{cat}</span>
              <span style={{ fontSize: 9, color: "var(--text-3,#6b7280)" }}>{grouped[cat].length} patterns</span>
              {open ? <ChevronDown size={12} color="var(--text-3)" /> : <ChevronRight size={12} color="var(--text-3)" />}
            </div>
            {open && (
              <div style={{ display: "flex", flexDirection: "column" }}>
                {grouped[cat].map(p => (
                  <div key={p.name} onClick={() => onSelect(p)}
                    style={{ display: "grid", gridTemplateColumns: "140px 1fr auto", gap: 8, alignItems: "center",
                      padding: "5px 10px", cursor: "pointer", borderTop: "1px solid var(--border,#1e1e2e)",
                      transition: "background .12s" }}
                    onMouseEnter={e => e.currentTarget.style.background = "var(--surface-3,#2a2a3a)"}
                    onMouseLeave={e => e.currentTarget.style.background = ""}>
                    <span style={{ fontSize: 10, fontWeight: 700, color: c, fontFamily: "monospace" }}>{p.name}</span>
                    <span style={{ fontSize: 10, color: "var(--text-2,#94a3b8)" }}>{p.description}</span>
                    <code style={{ fontSize: 9, color: "var(--text-3,#6b7280)", background: "var(--surface-3,#2a2a3a)", padding: "1px 5px", borderRadius: 3 }}>{p.example}</code>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Validate tab ──────────────────────────────────────────────────────────────
function ValidateTab({ patterns, columns, sessionId }) {
  const [col,     setCol]     = useState(columns[0] ?? "");
  const [pat,     setPat]     = useState("");
  const [result,  setResult]  = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  const run = useCallback(async () => {
    if (!col || !pat) return;
    setLoading(true); setError(""); setResult(null);
    try { setResult(await validatePattern(sessionId, col, pat)); }
    catch (e) { setError(e?.response?.data?.detail ?? e?.message ?? "Validation failed."); }
    finally { setLoading(false); }
  }, [sessionId, col, pat]);

  const matchColor = result ? (result.match_pct >= 80 ? "#22c55e" : result.match_pct >= 40 ? "#f59e0b" : "#ef4444") : "#6b7280";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: 8, alignItems: "flex-end" }}>
        <div>
          <div style={{ fontSize: 9, color: "var(--text-3,#6b7280)", marginBottom: 3, textTransform: "uppercase", letterSpacing: ".05em" }}>Column</div>
          <select value={col} onChange={e => setCol(e.target.value)}
            style={{ width: "100%", background: "var(--surface-3,#2a2a3a)", border: "1px solid var(--border,#2a2a3a)", color: "var(--text-1,#e2e8f0)", borderRadius: 6, padding: "5px 8px", fontSize: 11 }}>
            {columns.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div>
          <div style={{ fontSize: 9, color: "var(--text-3,#6b7280)", marginBottom: 3, textTransform: "uppercase", letterSpacing: ".05em" }}>Pattern</div>
          <select value={pat} onChange={e => setPat(e.target.value)}
            style={{ width: "100%", background: "var(--surface-3,#2a2a3a)", border: "1px solid var(--border,#2a2a3a)", color: "var(--text-1,#e2e8f0)", borderRadius: 6, padding: "5px 8px", fontSize: 11 }}>
            <option value="">Select pattern…</option>
            {patterns.map(p => <option key={p.name} value={p.name}>{p.name} — {p.description}</option>)}
          </select>
        </div>
        <button onClick={run} disabled={loading || !col || !pat}
          style={{ background: "#6366f1", color: "#fff", border: "none", borderRadius: 6, padding: "6px 14px", fontSize: 11, fontWeight: 700,
            cursor: (!col || !pat || loading) ? "not-allowed" : "pointer", display: "flex", alignItems: "center", gap: 5,
            opacity: (!col || !pat) ? 0.5 : 1 }}>
          {loading ? <Loader2 size={12} style={{ animation: "spin 1s linear infinite" }} /> : <BookOpen size={12} />}
          Validate
        </button>
      </div>

      {error && <div style={{ display: "flex", gap: 8, padding: "7px 10px", background: "#ef444415", border: "1px solid #ef444440", borderRadius: 6, color: "#ef4444", fontSize: 11 }}><AlertCircle size={13}/>{error}</div>}

      {result && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {/* Big match % */}
          <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "12px 14px",
            background: "var(--surface-2,#1a1a2e)", border: `1px solid ${matchColor}40`, borderRadius: 8 }}>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 28, fontWeight: 900, color: matchColor, lineHeight: 1 }}>{result.match_pct}%</div>
              <div style={{ fontSize: 9, color: "var(--text-3,#6b7280)", textTransform: "uppercase", marginTop: 2 }}>match</div>
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ height: 6, background: "var(--surface-3,#2a2a3a)", borderRadius: 99, overflow: "hidden", marginBottom: 6 }}>
                <div style={{ height: "100%", width: `${result.match_pct}%`, background: matchColor, borderRadius: 99, transition: "width .5s ease" }} />
              </div>
              <div style={{ fontSize: 11, color: "var(--text-2,#94a3b8)" }}>
                <strong style={{ color: matchColor }}>{result.matches.toLocaleString()}</strong> of{" "}
                <strong>{result.total.toLocaleString()}</strong> cells match <code style={{ fontSize: 10 }}>{result.pattern_name}</code>
              </div>
            </div>
          </div>

          {/* Sample hits and misses */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {[["✓ Matches", result.sample_matches, "#22c55e", "#22c55e15"], ["✗ Non-matches", result.sample_fails, "#ef4444", "#ef444415"]].map(([label, vals, c, bg]) => (
              <div key={label} style={{ background: bg, border: `1px solid ${c}30`, borderRadius: 7, padding: "8px 10px" }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: c, marginBottom: 5 }}>{label}</div>
                {vals?.length === 0
                  ? <div style={{ fontSize: 10, color: "var(--text-3,#6b7280)", fontStyle: "italic" }}>None</div>
                  : vals.slice(0, 5).map((v, i) => (
                    <div key={i} style={{ fontSize: 10, fontFamily: "monospace", color: "var(--text-2,#94a3b8)",
                      overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", marginBottom: 2 }}>{v}</div>
                  ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Test tab ──────────────────────────────────────────────────────────────────
function TestTab({ patterns }) {
  const [value,  setValue]  = useState("");
  const [pat,    setPat]    = useState("");
  const [result, setResult] = useState(null);
  const [loading,setLoading]= useState(false);

  const run = useCallback(async () => {
    if (!value || !pat) return;
    setLoading(true);
    try { setResult(await testPattern(value, pat)); }
    catch { setResult(null); }
    finally { setLoading(false); }
  }, [value, pat]);

  // Auto-run on change
  useEffect(() => { if (value && pat) run(); }, [value, pat]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <div>
          <div style={{ fontSize: 9, color: "var(--text-3,#6b7280)", marginBottom: 3, textTransform: "uppercase", letterSpacing: ".05em" }}>Value to test</div>
          <input value={value} onChange={e => setValue(e.target.value)}
            placeholder="e.g. GB82WEST12345698765432"
            style={{ width: "100%", background: "var(--surface-3,#2a2a3a)", border: "1px solid var(--border,#2a2a3a)",
              color: "var(--text-1,#e2e8f0)", borderRadius: 6, padding: "6px 10px", fontSize: 11, outline: "none", boxSizing: "border-box" }} />
        </div>
        <div>
          <div style={{ fontSize: 9, color: "var(--text-3,#6b7280)", marginBottom: 3, textTransform: "uppercase", letterSpacing: ".05em" }}>Pattern</div>
          <select value={pat} onChange={e => setPat(e.target.value)}
            style={{ width: "100%", background: "var(--surface-3,#2a2a3a)", border: "1px solid var(--border,#2a2a3a)", color: "var(--text-1,#e2e8f0)", borderRadius: 6, padding: "5px 8px", fontSize: 11 }}>
            <option value="">Select pattern…</option>
            {patterns.map(p => <option key={p.name} value={p.name}>{p.name} — {p.description}</option>)}
          </select>
        </div>
      </div>

      {result !== null && value && pat && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6, padding: "12px 14px",
          background: result.matched ? "#22c55e10" : "#ef444410",
          border: `1px solid ${result.matched ? "#22c55e" : "#ef4444"}40`, borderRadius: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {result.matched
              ? <CheckCircle2 size={18} color="#22c55e" />
              : <XCircle size={18} color="#ef4444" />}
            <span style={{ fontSize: 13, fontWeight: 800, color: result.matched ? "#22c55e" : "#ef4444" }}>
              {result.matched ? "Match" : "No match"}
            </span>
          </div>
          {result.match_text && (
            <div style={{ fontSize: 10, color: "var(--text-2,#94a3b8)" }}>
              Matched: <code style={{ background: "#22c55e20", color: "#22c55e", padding: "1px 6px", borderRadius: 3 }}>{result.match_text}</code>
            </div>
          )}
        </div>
      )}

      {!value && (
        <div style={{ padding: "20px 16px", textAlign: "center", color: "var(--text-3,#6b7280)", fontSize: 11,
          border: "1px dashed var(--border,#2a2a3a)", borderRadius: 8 }}>
          Type a value and select a pattern to test instantly
        </div>
      )}
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────
const TABS = ["Browse", "Validate", "Test"];

export default function PatternLibraryPanel({ sessionId, columns = [] }) {
  const [tab,      setTab]      = useState("Browse");
  const [patterns, setPatterns] = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    listPatterns().then(d => { setPatterns(d.patterns ?? []); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  const handleSelect = (p) => { setSelected(p); setTab("Validate"); };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
      {/* Tab bar */}
      <div style={{ display: "flex", borderBottom: "1px solid var(--border,#2a2a3a)", marginBottom: 12 }}>
        {TABS.map(t => (
          <button key={t} onClick={() => setTab(t)}
            style={{ padding: "6px 12px", fontSize: 11, fontWeight: t === tab ? 700 : 500,
              background: "none", border: "none", borderBottom: t === tab ? "2px solid #6366f1" : "2px solid transparent",
              color: t === tab ? "#6366f1" : "var(--text-3,#6b7280)", cursor: "pointer" }}>
            {t}
          </button>
        ))}
        {loading && <Loader2 size={12} style={{ margin: "auto 8px", animation: "spin 1s linear infinite", color: "var(--text-3,#6b7280)" }} />}
        {!loading && <span style={{ marginLeft: "auto", fontSize: 9, color: "var(--text-3,#6b7280)", alignSelf: "center", paddingRight: 10 }}>{patterns.length} patterns</span>}
      </div>

      {tab === "Browse"   && <BrowseTab   patterns={patterns} onSelect={handleSelect} />}
      {tab === "Validate" && <ValidateTab patterns={patterns} columns={columns} sessionId={sessionId} />}
      {tab === "Test"     && <TestTab     patterns={patterns} />}

      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}
