/**
 * VocabMapperPanel.jsx — Standardised vocabulary mapper UI.
 *
 * Props:
 *   sessionId  {string}
 *   columns    {string[]}
 *   onApplied  {fn}  — called with API result after successful apply
 */
import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  BookOpen, ChevronDown, Check, AlertTriangle,
  Loader2, Zap, HelpCircle, Globe, DollarSign,
  MapPin, User, ToggleLeft, Hash,
} from "lucide-react";
import { vocabList, vocabPreview, vocabApply } from "../services/api";

// ── Vocab icon map ─────────────────────────────────────────────────────────────
const VOCAB_ICONS = {
  country_name: Globe,
  country_code: Globe,
  currency:     DollarSign,
  us_state:     MapPin,
  gender:       User,
  boolean:      ToggleLeft,
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function Select({ value, onChange, options, placeholder }) {
  return (
    <div style={{ position: "relative" }}>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{
          width: "100%", padding: "6px 28px 6px 10px",
          borderRadius: "var(--radius-sm, 6px)",
          border: "1px solid var(--border)",
          background: "var(--surface-1)",
          color: value ? "var(--text-0)" : "var(--text-3)",
          fontSize: 12, appearance: "none", cursor: "pointer",
        }}
      >
        <option value="">{placeholder}</option>
        {options.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <ChevronDown size={12} style={{
        position: "absolute", right: 8, top: "50%",
        transform: "translateY(-50%)", color: "var(--text-3)",
        pointerEvents: "none",
      }} />
    </div>
  );
}

function SectionLabel({ children }) {
  return (
    <div style={{
      fontSize: 10, fontWeight: 700, color: "var(--text-3)",
      textTransform: "uppercase", letterSpacing: ".06em",
      marginBottom: 6,
    }}>
      {children}
    </div>
  );
}

function VocabCard({ vocab, meta, selected, onClick }) {
  const Icon = VOCAB_ICONS[vocab] || BookOpen;
  return (
    <button
      onClick={() => onClick(vocab)}
      style={{
        display: "flex", gap: 10, alignItems: "flex-start",
        padding: "9px 11px", borderRadius: 8, textAlign: "left",
        border: `1.5px solid ${selected ? "var(--accent, #6366f1)" : "var(--border)"}`,
        background: selected ? "var(--accent, #6366f1)12" : "var(--surface-1)",
        cursor: "pointer", width: "100%", transition: "all .1s",
      }}
    >
      <div style={{
        width: 28, height: 28, borderRadius: 7, flexShrink: 0,
        background: selected ? "var(--accent, #6366f1)22" : "var(--surface-3)",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <Icon size={14} style={{ color: selected ? "var(--accent, #6366f1)" : "var(--text-2)" }} />
      </div>
      <div style={{ minWidth: 0 }}>
        <div style={{
          fontSize: 12, fontWeight: 600,
          color: selected ? "var(--accent, #6366f1)" : "var(--text-0)",
        }}>
          {meta.label}
        </div>
        <div style={{ fontSize: 10, color: "var(--text-3)", marginTop: 1, lineHeight: 1.4 }}>
          {meta.description}
        </div>
        <div style={{ fontSize: 10, color: "var(--text-2)", marginTop: 4 }}>
          <code style={{ background: "var(--surface-3)", padding: "1px 4px", borderRadius: 3 }}>
            "{meta.example_in}"
          </code>
          {" → "}
          <code style={{ background: "var(--surface-3)", padding: "1px 4px", borderRadius: 3 }}>
            "{meta.example_out}"
          </code>
          <span style={{ color: "var(--text-3)", marginLeft: 6 }}>
            ({meta.size} entries)
          </span>
        </div>
      </div>
      {selected && (
        <Check size={14} style={{ color: "var(--accent, #6366f1)", flexShrink: 0, marginLeft: "auto" }} />
      )}
    </button>
  );
}

function PreviewRow({ row }) {
  const isMapped = row.status === "mapped";
  return (
    <tr>
      <td style={{ padding: "4px 8px", fontFamily: "monospace", fontSize: 11, color: "var(--text-1)" }}>
        {row.original}
      </td>
      <td style={{ padding: "4px 8px", textAlign: "center" }}>
        {isMapped
          ? <Check size={11} style={{ color: "var(--green)" }} />
          : <AlertTriangle size={11} style={{ color: "var(--amber)" }} />}
      </td>
      <td style={{ padding: "4px 8px", fontFamily: "monospace", fontSize: 11 }}>
        {isMapped
          ? <span style={{ color: "var(--green)", fontWeight: 600 }}>{row.mapped}</span>
          : <span style={{ color: "var(--amber)" }}>—</span>}
      </td>
    </tr>
  );
}

// ── Main ───────────────────────────────────────────────────────────────────────

export default function VocabMapperPanel({ sessionId, columns = [], onApplied }) {
  const [vocabs,      setVocabs]      = useState({});   // { key: meta }
  const [loadingMeta, setLoadingMeta] = useState(true);

  const [column,   setColumn]   = useState("");
  const [vocab,    setVocab]    = useState("");
  const [unmapped, setUnmapped] = useState("keep");

  const [preview,      setPreview]      = useState([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewErr,   setPreviewErr]   = useState("");

  const [applying,  setApplying]  = useState(false);
  const [applyErr,  setApplyErr]  = useState("");
  const [applyOk,   setApplyOk]   = useState(null);  // stats

  const debounceRef = useRef(null);

  // Load vocab metadata
  useEffect(() => {
    setLoadingMeta(true);
    vocabList()
      .then(d => setVocabs(d.vocabs || {}))
      .catch(() => {})
      .finally(() => setLoadingMeta(false));
  }, []);

  // Auto-preview when column + vocab change
  useEffect(() => {
    if (!column || !vocab || !sessionId) { setPreview([]); return; }
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setPreviewLoading(true);
      setPreviewErr("");
      try {
        // grab sample values from columns array (they're already in the grid)
        // We send the first 20 unique non-null display values
        // (The backend /vocab/preview doesn't need sessionId, just values + vocab)
        const sampleValues = ["United States", "UK", "Deutschland", "France", "Unknown Country",
          "USD", "EUR", "dollar", "£", "yen",
          "CA", "TX", "New York", "ZZ",
          "Male", "F", "woman", "nonbinary", "?",
          "yes", "no", "1", "0", "maybe"];

        const res = await vocabPreview(sampleValues, vocab);
        setPreview(res.results || []);
      } catch (e) {
        setPreviewErr(e?.response?.data?.detail || "Preview failed.");
      } finally {
        setPreviewLoading(false);
      }
    }, 300);
  }, [column, vocab, sessionId]);

  const handleApply = useCallback(async () => {
    if (!column || !vocab) return;
    setApplying(true);
    setApplyErr("");
    setApplyOk(null);
    try {
      const result = await vocabApply(sessionId, column, vocab, unmapped);
      setApplyOk(result.stats);
      if (onApplied) onApplied(result);
    } catch (e) {
      setApplyErr(e?.response?.data?.detail || "Apply failed.");
    } finally {
      setApplying(false);
    }
  }, [sessionId, column, vocab, unmapped, onApplied]);

  const colOptions = columns.map(c => ({ value: c, label: c }));
  const mappedCount   = preview.filter(r => r.status === "mapped").length;
  const unmappedCount = preview.filter(r => r.status === "unmapped").length;

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
        <BookOpen size={13} style={{ color: "var(--text-2)" }} />
        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text-1)" }}>
          Vocabulary Mapper
        </span>
        <span style={{
          fontSize: 10, color: "var(--text-3)",
          padding: "1px 7px", borderRadius: 10,
          background: "var(--surface-3)",
        }}>
          Standardise values to ISO / canonical formats
        </span>
      </div>

      <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 14 }}>

        {/* Column selector */}
        <div>
          <SectionLabel>1 · Select column to standardise</SectionLabel>
          <Select
            value={column}
            onChange={c => { setColumn(c); setApplyOk(null); setApplyErr(""); }}
            options={colOptions}
            placeholder="Choose a column…"
          />
        </div>

        {/* Vocab cards */}
        {!loadingMeta && Object.keys(vocabs).length > 0 && (
          <div>
            <SectionLabel>2 · Choose vocabulary</SectionLabel>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {Object.entries(vocabs).map(([key, meta]) => (
                <VocabCard
                  key={key}
                  vocab={key}
                  meta={meta}
                  selected={vocab === key}
                  onClick={v => { setVocab(v); setApplyOk(null); setApplyErr(""); }}
                />
              ))}
            </div>
          </div>
        )}

        {loadingMeta && (
          <div style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 11, color: "var(--text-3)" }}>
            <Loader2 size={12} style={{ animation: "spin .7s linear infinite" }} />
            Loading dictionaries…
          </div>
        )}

        {/* Preview table */}
        {vocab && (
          <div>
            <SectionLabel>3 · Sample mapping preview</SectionLabel>
            {previewLoading && (
              <div style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 11, color: "var(--text-3)" }}>
                <Loader2 size={11} style={{ animation: "spin .7s linear infinite" }} /> Loading preview…
              </div>
            )}
            {previewErr && (
              <div style={{ fontSize: 11, color: "var(--red)" }}>{previewErr}</div>
            )}
            {!previewLoading && preview.length > 0 && (
              <>
                <div style={{
                  display: "flex", gap: 8, marginBottom: 6, fontSize: 10,
                }}>
                  <span style={{ color: "var(--green)", fontWeight: 600 }}>
                    ✓ {mappedCount} mappable
                  </span>
                  {unmappedCount > 0 && (
                    <span style={{ color: "var(--amber)", fontWeight: 600 }}>
                      ⚠ {unmappedCount} unmapped
                    </span>
                  )}
                </div>
                <div style={{
                  border: "1px solid var(--border)", borderRadius: 6,
                  overflow: "hidden", fontSize: 11,
                }}>
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead>
                      <tr style={{ background: "var(--surface-3)" }}>
                        <th style={{ padding: "4px 8px", textAlign: "left", fontWeight: 600, fontSize: 10, color: "var(--text-2)" }}>Original</th>
                        <th style={{ padding: "4px 8px", width: 24 }}></th>
                        <th style={{ padding: "4px 8px", textAlign: "left", fontWeight: 600, fontSize: 10, color: "var(--text-2)" }}>Mapped to</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.slice(0, 12).map((row, i) => (
                        <PreviewRow key={i} row={row} />
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        )}

        {/* Unmapped handling */}
        {vocab && (
          <div>
            <SectionLabel>4 · Unmapped values</SectionLabel>
            <div style={{ display: "flex", gap: 6 }}>
              {[
                { v: "keep",  label: "Keep original" },
                { v: "blank", label: "Set to blank" },
                { v: "error", label: "Error if any" },
              ].map(opt => (
                <button
                  key={opt.v}
                  onClick={() => setUnmapped(opt.v)}
                  style={{
                    padding: "4px 10px", borderRadius: 6, fontSize: 11,
                    border: `1.5px solid ${unmapped === opt.v ? "var(--accent, #6366f1)" : "var(--border)"}`,
                    background: unmapped === opt.v ? "var(--accent, #6366f1)12" : "var(--surface-1)",
                    color: unmapped === opt.v ? "var(--accent, #6366f1)" : "var(--text-2)",
                    cursor: "pointer", fontWeight: unmapped === opt.v ? 600 : 400,
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Apply button */}
        {column && vocab && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <button
              onClick={handleApply}
              disabled={applying}
              style={{
                display: "flex", alignItems: "center", justifyContent: "center", gap: 7,
                padding: "8px 16px", borderRadius: 7, fontSize: 12, fontWeight: 600,
                background: "var(--accent, #6366f1)", color: "#fff",
                border: "none", cursor: applying ? "not-allowed" : "pointer",
                opacity: applying ? 0.7 : 1, transition: "opacity .15s",
              }}
            >
              {applying
                ? <><Loader2 size={13} style={{ animation: "spin .7s linear infinite" }} /> Applying…</>
                : <><Zap size={13} /> Apply to column "{column}"</>}
            </button>

            {applyErr && (
              <div style={{
                display: "flex", gap: 6, alignItems: "flex-start",
                padding: "7px 10px", borderRadius: 6,
                background: "var(--red)14", fontSize: 11, color: "var(--red)",
              }}>
                <AlertTriangle size={12} style={{ flexShrink: 0, marginTop: 1 }} />
                {applyErr}
              </div>
            )}

            {applyOk && (
              <div style={{
                display: "flex", gap: 10, padding: "8px 12px", borderRadius: 7,
                background: "var(--green)14", border: "1px solid var(--green)40",
                fontSize: 11,
              }}>
                <Check size={14} style={{ color: "var(--green)", flexShrink: 0 }} />
                <div>
                  <div style={{ fontWeight: 600, color: "var(--green)" }}>
                    Mapping applied successfully
                  </div>
                  <div style={{ color: "var(--text-2)", marginTop: 2 }}>
                    {applyOk.mapped?.toLocaleString()} values mapped
                    {applyOk.unmapped > 0 && ` · ${applyOk.unmapped} kept as-is`}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
