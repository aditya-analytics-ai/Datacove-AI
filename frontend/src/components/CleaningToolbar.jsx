/**
 * CleaningToolbar v7 — Excel ribbon-style with full Advanced Transform panel.
 *
 * New in v7:
 *  - "String" group: Unicode, Strip Chars, Find/Replace shortcut
 *  - "Numeric" group: Round, Clip, Scale, Extract#
 *  - "Missing" group: Fill Forward, Fill Backward, Interpolate
 *  - "Structure" group: Drop Constants, Drop Hi-Miss Cols
 *  - "Transform…" button → full Advanced panel covering all 35+ actions
 *    organised by category (String / Numeric / Missing / Structure)
 *  - TransformPanel renders a dynamic parameter form per selected action
 *  - Accepts `columns` prop (string[]) for column selectors
 */
import React, { useState, useRef, useEffect, useCallback } from "react";
import ReactDOM from "react-dom";
import {
  Trash2, WholeWord, ArrowUpDown, ListFilter,
  Wand2, Undo2, Download, Send, Loader2,
  RotateCcw, Bot, Hash, ChevronDown, CheckCircle2, Info,
  Lightbulb, Cpu, MessageSquare, Code2, GitMerge,
  CheckSquare, History, Workflow, GitCompare, ScanSearch,
  Type, Binary, Layers, Sigma, X, ChevronRight,
  CalendarDays, CalendarCheck, Scissors, Merge, RefreshCcw, Filter,
  TrendingDown, BarChart2, Percent, ToggleLeft, Columns,
  Settings2, AlertCircle,
  GitBranch, Brain, BookOpen, Globe, Package2,
} from "lucide-react";

// ── Tab icons ─────────────────────────────────────────────────────────────────
const TAB_ICONS = {
  Insights: Lightbulb, Visualize: BarChart2, Power: Settings2,
  Agent: Bot, ML: Cpu, Chat: MessageSquare,
  SQL: Code2, Fuzzy: GitMerge, Validate: CheckSquare,
  History: History, Pipelines: Workflow, Compare: GitCompare,
  Correlations: GitBranch, Intelligence: Brain, Patterns: BookOpen,
  Vocab: Globe, Batch: Package2,
};

// ── Simple one-click ribbon actions ──────────────────────────────────────────
// DATASET_WIDE actions always ignore the column selector and run on all columns.
// Column-aware actions inject the selected column from the toolbar selector bar.

const CLEAN_ACTIONS = [
  { action: "remove_duplicates",          label: "Dupes",      icon: Trash2,     params: {},                     tip: "Remove exact duplicate rows",                    datasetWide: true  },
  { action: "trim_whitespace",            label: "Trim",       icon: WholeWord,  params: {},                     tip: "Strip leading, trailing & extra whitespace"              },
  { action: "standardise_capitalisation", label: "Case",       icon: ArrowUpDown,params: {},                     tip: "Standardise capitalisation to Title Case"                },
  { action: "normalise_categories",       label: "Normalize",  icon: ListFilter, params: {},                     tip: "Normalise category variants (yes/YES/Yes → Yes)"         },
];
const STRING_ACTIONS = [
  { action: "normalize_unicode",  label: "Unicode",    icon: Type,     params: {},                            tip: "Strip accents, convert to ASCII  (café → cafe)"  },
  { action: "strip_characters",   label: "Strip",      icon: Scissors, params: { mode: "non_printable" },    tip: "Remove non-printable / garbage characters"        },
];
const NUMERIC_ACTIONS = [
  { action: "coerce_numeric",   label: "Coerce #",  icon: Binary,   params: {},                tip: "Convert ERROR/UNKNOWN/text → number (NaN if unparseable)" },
  { action: "round_numeric",    label: "Round",     icon: Sigma,    params: { decimals: 2 },   tip: "Round to 2 decimal places"                                },
  { action: "extract_numeric",  label: "Extract #", icon: Hash,     params: {},                tip: 'Pull first number from strings  ("$1,200 USD" → 1200)'    },
  { action: "clip_outliers",    label: "Clip",      icon: TrendingDown, params: { method: "iqr" }, tip: "Clamp outliers to IQR fence (removes extreme values)"  },
];
const MISSING_ACTIONS = [
  { action: "fill_missing",             label: "Fill NaN",  icon: Hash,         params: { strategy: "median" }, tip: "Fill missing values with median (numeric) or mode (text)" },
  { action: "fill_missing_ffill",       label: "Fill ↓",    icon: ChevronDown,  params: {},                     tip: "Forward-fill: carry last known value downward"             },
  { action: "fill_missing_bfill",       label: "Fill ↑",    icon: ChevronDown,  params: {},                     tip: "Backward-fill: carry next known value upward"              },
  { action: "fill_missing_interpolate", label: "Interp",    icon: TrendingDown, params: {},                     tip: "Interpolate missing numeric values (linear)"               },
];
const STRUCTURE_ACTIONS = [
  { action: "drop_constant_columns",     label: "Drop Const",  icon: Filter,   params: {},                  tip: "Drop zero-variance columns (all values identical)",  datasetWide: true },
  { action: "drop_high_missing_columns", label: "Drop Empty",  icon: Percent,  params: { threshold: 0.5 }, tip: "Drop columns with > 50% missing values",             datasetWide: true },
  { action: "cast_type",                 label: "Cast Type",   icon: ToggleLeft, params: { dtype: "float" },tip: "Convert column to int / float / string / bool / date"               },
];
const DATE_ACTIONS = [
  { action: "standardise_mixed_dates", label: "Fix Dates",   icon: CalendarDays,  params: { dayfirst: "true", output_format: "%Y-%m-%d" }, tip: "Detect & unify all mixed date formats → YYYY-MM-DD" },
  { action: "extract_date_parts",      label: "Split Date",  icon: CalendarCheck, params: { parts: ["year","month","day"] },                tip: "Extract year, month, day into separate columns"      },
];

const EXPORT_FMTS = [
  { fmt: "csv",  label: "CSV",  desc: "Comma-separated" },
  { fmt: "xlsx", label: "XLSX", desc: "Excel workbook"  },
  { fmt: "json", label: "JSON", desc: "JSON records"    },
];

const ALL_TABS = [
  "Insights", "Visualize", "Power",
  "Agent", "ML", "Chat", "SQL", "Fuzzy",
  "Correlations", "Intelligence", "Patterns",
  "Validate", "Vocab", "Batch", "History", "Pipelines", "Compare",
];

// ══════════════════════════════════════════════════════════════════════════════
// ── Advanced Transform Panel definition ──────────────────────────────────────
// ══════════════════════════════════════════════════════════════════════════════

const ADVANCED_CATEGORIES = [
  {
    id: "string", label: "String", icon: Type, color: "#6366f1",
    actions: [
      { id: "find_replace",       label: "Find & Replace",     desc: "Replace text (exact or regex) in a column" },
      { id: "map_values",         label: "Map Values",          desc: "Replace values using a lookup dictionary" },
      { id: "split_column",       label: "Split Column",        desc: "Split one column into two on a delimiter" },
      { id: "merge_columns",      label: "Merge Columns",       desc: "Concatenate two columns into one" },
      { id: "normalize_phone",    label: "Normalise Phone",     desc: "Standardise phone numbers (strip non-digits)" },
      { id: "strip_characters",   label: "Strip Characters",    desc: "Remove HTML, special chars, or garbage bytes" },
      { id: "normalize_unicode",  label: "Normalise Unicode",   desc: "Strip accents / convert to ASCII" },
    ],
  },
  {
    id: "numeric", label: "Numeric", icon: Sigma, color: "#10b981",
    actions: [
      { id: "extract_numeric",    label: "Extract Number",      desc: 'Pull first number from strings ("$1,200" → 1200)' },
      { id: "clip_outliers",      label: "Clip Outliers",       desc: "Clamp values to IQR or manual [min, max] bounds" },
      { id: "replace_outliers",   label: "Replace Outliers",    desc: "Replace outliers with mean / median / NaN" },
      { id: "round_numeric",      label: "Round",               desc: "Round to N decimal places" },
      { id: "scale_numeric",      label: "Scale / Normalise",   desc: "Min-max [0,1] or Z-score standardisation" },
      { id: "bin_numeric",        label: "Bin into Buckets",    desc: "Convert continuous values into N discrete bins" },
    ],
  },
  {
    id: "missing", label: "Missing Values", icon: Hash, color: "#f59e0b",
    actions: [
      { id: "fill_missing",             label: "Fill Missing",      desc: "Fill with mean / median / mode / constant" },
      { id: "fill_missing_ffill",       label: "Forward Fill",      desc: "Propagate last valid value forward" },
      { id: "fill_missing_bfill",       label: "Backward Fill",     desc: "Propagate next valid value backward" },
      { id: "fill_missing_interpolate", label: "Interpolate",       desc: "Linear (or polynomial) interpolation" },
      { id: "drop_rows_missing_threshold", label: "Drop Sparse Rows", desc: "Remove rows missing more than X% of values" },
    ],
  },
  {
    id: "date", label: "Date", icon: CalendarDays, color: "#06b6d4",
    actions: [
      { id: "standardise_mixed_dates", label: "Fix Mixed Formats",     desc: "Detect & unify mixed date formats (DD-MM-YYYY, M/D/YYYY, etc.) → ISO 8601" },
      { id: "standardise_dates",       label: "Standardise Dates",     desc: "Parse dates and reformat to a consistent format (default: YYYY-MM-DD)" },
      { id: "extract_date_parts",      label: "Extract Date Parts",    desc: "Split a date into year, month, day, weekday, quarter columns" },
      { id: "calculate_date_diff",     label: "Date Difference",       desc: "Calculate days/weeks/months/years between two dates or vs a reference" },
      { id: "flag_future_dates",       label: "Flag Future Dates",     desc: "Add a boolean column marking dates in the future" },
      { id: "flag_weekend_dates",      label: "Flag Weekend Dates",    desc: "Add a boolean column marking Saturday/Sunday dates" },
      { id: "age_from_date",           label: "Age from Date",         desc: "Calculate age in years/months/days from a date-of-birth column" },
    ],
  },
  {
    id: "structure", label: "Structure", icon: Layers, color: "#a78bfa",
    actions: [
      { id: "cast_type",                 label: "Cast Type",          desc: "Convert column to int / float / bool / category" },
      { id: "conditional_column",        label: "Conditional Column", desc: "Add a new column derived from a condition" },
      { id: "drop_constant_columns",     label: "Drop Constant Cols", desc: "Remove zero-variance (all-same-value) columns", datasetWide: true },
      { id: "drop_high_missing_columns", label: "Drop Hi-Miss Cols",  desc: "Remove columns with > X% missing values", datasetWide: true },
      { id: "drop_rows_missing_threshold", label: "Drop Sparse Rows", desc: "Remove rows missing more than X% of values", datasetWide: true },
      { id: "reorder_columns",           label: "Reorder Columns",    desc: "Drag columns into a new order", datasetWide: true },
      { id: "rename_columns_bulk",       label: "Bulk Rename",        desc: "Rename multiple columns at once", datasetWide: true },
      { id: "normalize_column_names",    label: "Normalize Col Names",desc: "Convert all column names to snake_case / camelCase", datasetWide: true },
    ],
  },
  {
    id: "filter", label: "Filter / Drop", icon: Filter, color: "#f43f5e",
    actions: [
      { id: "drop_rows_where",   label: "Drop Rows (Exact)",   desc: "Remove rows where column exactly equals a value" },
      { id: "drop_rows_matching",label: "Drop Rows (Regex)",   desc: "Remove rows where column matches a regex pattern" },
    ],
  },
];

// ── Portal dropdown (uses ReactDOM.createPortal to escape overflow/backdrop-filter) ──
function PortalDropdown({ anchorRef, open, onClose, children }) {
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const dropdownRef = useRef(null);

  useEffect(() => {
    if (!open || !anchorRef.current) return;
    const r = anchorRef.current.getBoundingClientRect();
    const top = r.bottom + 4;
    const left = Math.min(r.left, window.innerWidth - 200);
    setPos({ top, left });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const h = (e) => {
      const inAnchor   = anchorRef.current?.contains(e.target);
      const inDropdown = dropdownRef.current?.contains(e.target);
      if (!inAnchor && !inDropdown) onClose();
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [open, onClose]);

  if (!open) return null;

  return ReactDOM.createPortal(
    <div ref={dropdownRef} style={{
      position:"fixed", top:pos.top, left:pos.left, zIndex:99999, minWidth:180,
      background:"var(--surface-2)", border:"1px solid var(--border-2)",
      borderRadius:"var(--radius-md)", padding:5,
      boxShadow:"0 8px 32px rgba(0,0,0,.6), 0 0 0 1px rgba(99,102,241,.1)",
    }}>
      {children}
    </div>,
    document.body
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// ── Advanced Transform Panel ──────────────────────────────────────────────────
// ══════════════════════════════════════════════════════════════════════════════

function ColSelect({ value, onChange, columns, required, placeholder = "All columns" }) {
  // Auto-select first column when required and nothing selected yet
  // NOTE: onChange excluded from deps intentionally — it's a new fn each render (would loop)
  useEffect(() => {
    if (required && !value && columns.length > 0) {
      onChange(columns[0]);
    }
  }, [required, value, columns.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  // Controlled value: fall back to first column for required selects during the
  // first render before the useEffect above fires asynchronously.
  const effectiveValue = value ?? (required && columns.length > 0 ? columns[0] : "");

  return (
    <select className="tp-input" value={effectiveValue} onChange={e => onChange(e.target.value || null)}>
      {!required && <option value="">{placeholder}</option>}
      {columns.map(c => <option key={c} value={c}>{c}</option>)}
    </select>
  );
}

function ParamForm({ actionId, params, setParam, columns }) {
  const num = (key, label, def, min, max, step = 1) => (
    <label className="tp-field">
      <span>{label}</span>
      <input className="tp-input tp-input--sm" type="number"
        min={min} max={max} step={step}
        value={params[key] ?? def}
        onChange={e => setParam(key, parseFloat(e.target.value))} />
    </label>
  );
  const txt = (key, label, placeholder = "", req = false, defaultVal = "") => {
    // Write defaultVal into params immediately if key is not yet set
    // so Apply always sends a real value, not undefined
    if (params[key] === undefined && defaultVal !== "") {
      // Use setTimeout to avoid setState-during-render warning
      setTimeout(() => setParam(key, defaultVal), 0);
    }
    return (
      <label className="tp-field">
        <span>{label}{req && <em style={{color:"var(--red)"}}>*</em>}</span>
        <input className="tp-input" type="text" placeholder={placeholder}
          value={params[key] ?? defaultVal}
          onChange={e => setParam(key, e.target.value)} />
      </label>
    );
  };
  const sel = (key, label, options) => {
    const defVal = options[0]?.value;
    if (params[key] === undefined && defVal !== undefined) {
      setTimeout(() => setParam(key, defVal), 0);
    }
    return (
      <label className="tp-field">
        <span>{label}</span>
        <select className="tp-input" value={params[key] ?? defVal}
          onChange={e => setParam(key, e.target.value)}>
          {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </label>
    );
  };
  const chk = (key, label) => (
    <label className="tp-field tp-field--row">
      <input type="checkbox" checked={!!params[key]}
        onChange={e => setParam(key, e.target.checked)} />
      <span>{label}</span>
    </label>
  );
  const colSel = (key = "column", label = "Column", req = false) => (
    <label className="tp-field">
      <span>{label}{req && <em style={{color:"var(--red)"}}>*</em>}</span>
      <ColSelect value={params[key]} onChange={v => setParam(key, v)}
        columns={columns} required={req} />
    </label>
  );

  switch (actionId) {
    // ── String ──────────────────────────────────────────────────────────────
    case "find_replace":
      return (<>
        {colSel("column", "Column", true)}
        {txt("find",    "Find",    "text to find", true)}
        {txt("replace", "Replace", "replacement (blank = delete)")}
        {chk("regex",          "Treat 'Find' as regex pattern")}
        {chk("case_sensitive", "Case sensitive")}
      </>);

    case "map_values":
      return (<>
        {colSel("column", "Column", true)}
        <MapValuesEditor params={params} setParam={setParam} />
      </>);

    case "split_column": {
      const base = params.column || "col";
      return (<>
        {colSel("column", "Column", true)}
        {txt("delimiter", "Delimiter", "e.g. space, comma, |", false, " ")}
        {txt("new_col_1", "Left part column name",  `${base}_1`, false, `${base}_1`)}
        {txt("new_col_2", "Right part column name", `${base}_2`, false, `${base}_2`)}
        {chk("keep_original", "Keep source column")}
      </>);
    }

    case "merge_columns": {
      const defaultNewCol = `${params.col1 || "col1"}_${params.col2 || "col2"}`;
      return (<>
        {colSel("col1", "First column",  true)}
        <label className="tp-field">
          <span>Second column<em style={{color:"var(--red)"}}>*</em></span>
          <select className="tp-input" value={params.col2 || ""}
            onChange={e => setParam("col2", e.target.value || null)}>
            <option value="">Select column…</option>
            {columns.filter(c => c !== params.col1).map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        {txt("separator", "Separator", " ", false, " ")}
        {txt("new_col", "New column name", defaultNewCol, false, defaultNewCol)}
        {chk("keep_originals", "Keep source columns")}
      </>);
    }

    case "normalize_phone":
      return (<>
        {colSel("column", "Column", true)}
        {txt("country_code", "Country code prefix (optional)", "+91")}
      </>);

    case "strip_characters":
      return (<>
        {colSel("column", "Column (blank = all string cols)")}
        {sel("mode", "Mode", [
          { value: "non_printable", label: "Non-printable / garbage bytes" },
          { value: "html",          label: "HTML / XML tags" },
          { value: "special",       label: "Special chars (keep alphanumeric + spaces)" },
          { value: "custom",        label: "Custom character list" },
        ])}
        {params.mode === "custom" && txt("chars", "Characters to remove", "#@!$")}
      </>);

    case "normalize_unicode":
      return (<>
        {colSel("column", "Column (blank = all string cols)")}
        <p className="tp-hint">Strips diacritic accents: café → cafe, naïve → naive</p>
      </>);

    // ── Numeric ─────────────────────────────────────────────────────────────
    case "extract_numeric":
      return (<>
        {colSel("column", "Column", true)}
        <p className="tp-hint">Extracts the first number found in each cell.<br/>e.g. "$1,200 USD" → 1200, "Age: 25 yrs" → 25</p>
      </>);

    case "clip_outliers":
      return (<>
        {colSel("column", "Column", true)}
        {sel("method", "Detection method", [
          { value: "iqr",    label: "IQR (auto-detect bounds)" },
          { value: "manual", label: "Manual bounds" },
        ])}
        {params.method === "iqr" && num("iqr_factor", "IQR multiplier", 1.5, 0.5, 5, 0.1)}
        {params.method === "manual" && <>
          {num("lower", "Lower bound", 0, -1e9, 1e9, 0.01)}
          {num("upper", "Upper bound", 100, -1e9, 1e9, 0.01)}
        </>}
      </>);

    case "replace_outliers":
      return (<>
        {colSel("column", "Column", true)}
        {sel("method", "Detection method", [
          { value: "iqr",    label: "IQR (1.5×)" },
          { value: "zscore", label: "Z-score" },
        ])}
        {params.method === "zscore" && num("z_threshold", "Z threshold", 3.0, 1, 10, 0.1)}
        {sel("strategy", "Replace with", [
          { value: "median", label: "Median of non-outliers" },
          { value: "mean",   label: "Mean of non-outliers"   },
          { value: "nan",    label: "NaN (null)"             },
        ])}
      </>);

    case "round_numeric":
      return (<>
        {colSel("column", "Column (blank = all numeric)")}
        {num("decimals", "Decimal places", 2, 0, 10)}
      </>);

    case "scale_numeric":
      return (<>
        {colSel("column", "Column (blank = all numeric)")}
        {sel("method", "Method", [
          { value: "min_max", label: "Min-Max → [0, 1]"     },
          { value: "z_score", label: "Z-score (μ=0, σ=1)"   },
        ])}
      </>);

    case "bin_numeric":
      return (<>
        {colSel("column", "Column", true)}
        {num("bins", "Number of bins", 5, 2, 50)}
        {sel("strategy", "Bin strategy", [
          { value: "equal_width", label: "Equal width (cut)"  },
          { value: "quantile",    label: "Equal frequency (qcut)" },
        ])}
        {txt("new_col", "Result column name", `${params.column || "col"}_bin`, false, `${params.column || "col"}_bin`)}
      </>);

    // ── Missing ─────────────────────────────────────────────────────────────
    case "fill_missing":
      return (<>
        {colSel("column", "Column (blank = all)")}
        {sel("strategy", "Strategy", [
          { value: "mode",   label: "Mode (most frequent)"  },
          { value: "median", label: "Median (numeric)"      },
          { value: "mean",   label: "Mean (numeric)"        },
          { value: "value",  label: "Constant value"        },
          { value: "drop",   label: "Drop rows with nulls"  },
        ])}
        {params.strategy === "value" && txt("value", "Fill value", "e.g. 0 or Unknown")}
      </>);

    case "fill_missing_ffill":
    case "fill_missing_bfill":
    case "fill_missing_interpolate":
      return (<>
        {colSel("column", "Column (blank = all)")}
        {actionId === "fill_missing_interpolate" &&
          sel("method", "Interpolation method", [
            { value: "linear",      label: "Linear"      },
            { value: "polynomial",  label: "Polynomial"  },
            { value: "nearest",     label: "Nearest"     },
          ])}
        <p className="tp-hint">
          {actionId === "fill_missing_ffill"       && "Carries last valid value forward (good for time-series)."}
          {actionId === "fill_missing_bfill"       && "Carries next valid value backward."}
          {actionId === "fill_missing_interpolate" && "Fills gaps by interpolating between adjacent numeric values."}
        </p>
      </>);

    case "drop_rows_missing_threshold":
      return (<>
        {num("threshold", "Drop rows missing more than (fraction)", 0.5, 0, 1, 0.05)}
        <p className="tp-hint">e.g. 0.5 drops rows where more than 50% of columns are missing.</p>
      </>);

    // ── Structure ────────────────────────────────────────────────────────────
    case "cast_type":
      return (<>
        {colSel("column", "Column", true)}
        {sel("dtype", "Target type", [
          { value: "float",    label: "Float (decimal)"          },
          { value: "int",      label: "Integer (nullable)"       },
          { value: "string",   label: "String / text"            },
          { value: "bool",     label: "Boolean (true/false)"     },
          { value: "category", label: "Category (low-cardinality)" },
          { value: "date",     label: "Date → ISO 8601"          },
        ])}
      </>);

    case "conditional_column":
      return (<>
        {colSel("column", "Source column", true)}
        {sel("condition", "Condition", [
          { value: "gt",          label: "Greater than (>)"       },
          { value: "gte",         label: "Greater or equal (≥)"   },
          { value: "lt",          label: "Less than (<)"          },
          { value: "lte",         label: "Less or equal (≤)"      },
          { value: "eq",          label: "Equals (=)"             },
          { value: "neq",         label: "Not equals (≠)"         },
          { value: "contains",    label: "Contains (text)"        },
          { value: "starts_with", label: "Starts with (text)"     },
          { value: "ends_with",   label: "Ends with (text)"       },
          { value: "not_null",    label: "Is not null"            },
        ])}
        {params.condition !== "not_null" && txt("value", "Comparison value", "e.g. 0 or Active", true)}
        {txt("true_label",  "Value when TRUE",  "yes")}
        {txt("false_label", "Value when FALSE", "no")}
        {txt("new_col",     "New column name",  `${params.column || "col"}_flag`, false, `${params.column || "col"}_flag`)}
      </>);

    case "drop_constant_columns":
      return <p className="tp-hint">Drops all columns where every non-null value is identical. No configuration needed.</p>;

    case "drop_high_missing_columns":
      return (<>
        {num("threshold", "Drop columns missing more than (fraction)", 0.5, 0, 1, 0.05)}
        <p className="tp-hint">e.g. 0.5 drops columns where more than 50% of rows are missing.</p>
      </>);

    // ── Date ────────────────────────────────────────────────────────────────
    case "standardise_mixed_dates":
    case "standardise_dates":
      return (<>
        {colSel("column", "Column", true)}
        {actionId === "standardise_mixed_dates" && (
          <>
            {sel("dayfirst", "Ambiguous dates (e.g. 05-06-2020)", [
              { value: "true",  label: "Day first → 5th June (DD-MM-YYYY)" },
              { value: "false", label: "Month first → May 6th (MM-DD-YYYY)" },
            ])}
            <p className="tp-hint">Handles all mixed formats automatically: DD-MM-YYYY, M/D/YYYY, YYYY/MM/DD, "Jan 15 2020", etc.</p>
          </>
        )}
        {sel("output_format", "Output format", [
          { value: "%Y-%m-%d", label: "YYYY-MM-DD (ISO 8601) — recommended" },
          { value: "%d/%m/%Y", label: "DD/MM/YYYY" },
          { value: "%m/%d/%Y", label: "MM/DD/YYYY" },
          { value: "%d-%m-%Y", label: "DD-MM-YYYY" },
          { value: "%d %b %Y", label: "15 Jan 2020" },
          { value: "%B %d, %Y",label: "January 15, 2020" },
        ])}
      </>);

    case "extract_date_parts":
      return (<>
        {colSel("column", "Date column", true)}
        <label className="tp-field">
          <span>Parts to extract</span>
          <div style={{display:"flex", flexWrap:"wrap", gap:6, marginTop:4}}>
            {["year","month","day","weekday","quarter","week","hour","minute"].map(part => (
              <label key={part} className="tp-field tp-field--row" style={{minWidth:90}}>
                <input type="checkbox"
                  checked={!!(params.parts || ["year","month","day"]).includes(part)}
                  onChange={e => {
                    const cur = params.parts || ["year","month","day"];
                    setParam("parts", e.target.checked ? [...cur, part] : cur.filter(p => p !== part));
                  }} />
                <span>{part}</span>
              </label>
            ))}
          </div>
        </label>
        {txt("prefix", "Column name prefix", `${params.column || "date"}_`, false, `${params.column || "date"}_`)}
        {sel("dayfirst", "Parse ambiguous dates", [
          { value: "true",  label: "Day first (DD-MM)" },
          { value: "false", label: "Month first (MM-DD)" },
        ])}
      </>);

    case "calculate_date_diff":
      return (<>
        {colSel("column", "Start date column", true)}
        <label className="tp-field">
          <span>Compare against</span>
          <select className="tp-input" value={params._diff_mode || "column"}
            onChange={e => setParam("_diff_mode", e.target.value)}>
            <option value="column">Another column</option>
            <option value="fixed">Fixed reference date</option>
          </select>
        </label>
        {(!params._diff_mode || params._diff_mode === "column") && (
          <label className="tp-field">
            <span>End date column<em style={{color:"var(--red)"}}>*</em></span>
            <select className="tp-input" value={params.column2 || ""}
              onChange={e => setParam("column2", e.target.value || null)}>
              <option value="">Select column…</option>
              {columns.filter(c => c !== params.column).map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
        )}
        {params._diff_mode === "fixed" && txt("reference_date", "Reference date", "e.g. 2024-01-01", false, new Date().toISOString().slice(0,10))}
        {sel("unit", "Unit", [
          { value: "days",   label: "Days" },
          { value: "weeks",  label: "Weeks" },
          { value: "months", label: "Months" },
          { value: "years",  label: "Years" },
        ])}
        {txt("new_col", "Result column name", `${params.column || "date"}_diff`, false, `${params.column || "date"}_diff`)}
        <label className="tp-field tp-field--row">
          <input type="checkbox" checked={params.absolute !== false}
            onChange={e => setParam("absolute", e.target.checked)} />
          <span>Always positive (absolute difference)</span>
        </label>
      </>);

    case "flag_future_dates":
      return (<>
        {colSel("column", "Date column", true)}
        {txt("cutoff_date", "Cutoff date (blank = today)", "e.g. 2024-12-31")}
        {txt("flag_col", "Flag column name", `${params.column || "date"}_is_future`, false, `${params.column || "date"}_is_future`)}
        <p className="tp-hint">Adds a True/False column. Dates after the cutoff are flagged as True.</p>
      </>);

    case "flag_weekend_dates":
      return (<>
        {colSel("column", "Date column", true)}
        {txt("flag_col", "Flag column name", `${params.column || "date"}_is_weekend`, false, `${params.column || "date"}_is_weekend`)}
        <p className="tp-hint">Adds a True/False column. Saturday and Sunday are flagged as True.</p>
      </>);

    case "age_from_date":
      return (<>
        {colSel("column", "Date-of-birth column", true)}
        {txt("reference_date", "Age as of date (blank = today)", "e.g. 2024-01-01")}
        {sel("unit", "Unit", [
          { value: "years",  label: "Years (integer)" },
          { value: "months", label: "Months (decimal)" },
          { value: "days",   label: "Days (integer)" },
        ])}
        {txt("new_col", "Result column name", `${params.column || "dob"}_age`, false, `${params.column || "dob"}_age`)}
        <p className="tp-hint">Calculates age from the date column to today (or a custom reference date).</p>
      </>);

    // ── Filter / Drop ────────────────────────────────────────────────────
    case "drop_rows_matching":
      return (<>
        {colSel("column", "Column", true)}
        {txt("pattern", "Regex pattern", "e.g. ^test|unknown|N/A", true)}
        {sel("flags", "Case", [
          { value: "",  label: "Case sensitive" },
          { value: "i", label: "Case insensitive" },
        ])}
        <label className="tp-field tp-field--row">
          <input type="checkbox" checked={!!params.keep}
            onChange={e => setParam("keep", e.target.checked)} />
          <span>Keep matching rows (instead of dropping)</span>
        </label>
        <p className="tp-hint">Supports full regex: <code>^</code> start, <code>$</code> end, <code>|</code> OR, <code>.*</code> wildcard</p>
      </>);

    // ── Structure ────────────────────────────────────────────────────────────
    case "reorder_columns": {
      const [dragIdx, setDragIdx] = useState(null);
      const order = params.order || columns;
      return (<>
        <p className="tp-hint">Drag rows to reorder columns. Click Apply when done.</p>
        <div style={{display:"flex",flexDirection:"column",gap:2,marginTop:4}}>
          {order.map((col, i) => (
            <div key={col}
              draggable
              onDragStart={() => setDragIdx(i)}
              onDragOver={e => { e.preventDefault(); }}
              onDrop={() => {
                if (dragIdx === null || dragIdx === i) return;
                const newOrder = [...order];
                const [moved] = newOrder.splice(dragIdx, 1);
                newOrder.splice(i, 0, moved);
                setParam("order", newOrder);
                setDragIdx(null);
              }}
              style={{display:"flex",alignItems:"center",gap:8,padding:"5px 8px",
                      background:"var(--surface-3)",borderRadius:5,cursor:"grab",
                      border:"1px solid var(--border)",fontSize:12,userSelect:"none"}}>
              <span style={{color:"var(--text-3)",fontSize:10}}>⠿</span>
              <span style={{flex:1}}>{col}</span>
              <span style={{fontSize:10,color:"var(--text-3)"}}>{i+1}</span>
            </div>
          ))}
        </div>
      </>);
    }

    case "rename_columns_bulk": {
      const mapping = params.mapping || {};
      return (<>
        <p className="tp-hint">Edit column names inline. Leave blank to keep original.</p>
        <div style={{display:"flex",flexDirection:"column",gap:4,marginTop:4}}>
          {columns.map(col => (
            <label key={col} className="tp-field" style={{flexDirection:"row",alignItems:"center",gap:8}}>
              <span style={{fontSize:11,color:"var(--text-2)",minWidth:120,overflow:"hidden",
                            textOverflow:"ellipsis",whiteSpace:"nowrap"}} title={col}>{col}</span>
              <span style={{color:"var(--text-3)",fontSize:11}}>→</span>
              <input className="tp-input" style={{flex:1}} placeholder={col}
                value={mapping[col] ?? ""}
                onChange={e => {
                  const v = e.target.value;
                  const m = {...mapping};
                  if (v && v !== col) m[col] = v; else delete m[col];
                  setParam("mapping", m);
                }} />
            </label>
          ))}
        </div>
      </>);
    }

    case "normalize_column_names":
      return (<>
        {sel("style", "Name style", [
          { value: "snake_case",  label: "snake_case  (transaction_id)" },
          { value: "camel_case",  label: "camelCase   (transactionId)" },
          { value: "lower",       label: "lowercase   (transactionid)" },
          { value: "upper",       label: "UPPER_CASE  (TRANSACTION_ID)" },
        ])}
        <p className="tp-hint">Removes special characters, normalises spaces. Applied to ALL column names.</p>
      </>);

    default:
      return <p className="tp-hint" style={{color:"var(--text-3)"}}>No parameters needed for this action.</p>;
  }
}

// Map values editor — table of old → new pairs
function MapValuesEditor({ params, setParam }) {
  const mapping = params.mapping || {};
  const entries = Object.entries(mapping);

  function setEntry(idx, key, value) {
    const arr = [...entries];
    arr[idx]  = [idx === 0 ? key : arr[idx][0], idx === 1 ? value : arr[idx][1]];
    // rebuild as object
    const m = {};
    arr.forEach(([k, v]) => { if (k !== "") m[k] = v; });
    setParam("mapping", m);
  }
  function addRow()       { setParam("mapping", { ...mapping, "": "" }); }
  function removeRow(idx) {
    const m = {};
    entries.forEach(([k, v], i) => { if (i !== idx) m[k] = v; });
    setParam("mapping", m);
  }
  function updateKey(idx, newKey) {
    const m = {};
    entries.forEach(([k, v], i) => { m[i === idx ? newKey : k] = v; });
    setParam("mapping", m);
  }
  function updateVal(idx, newVal) {
    const m = {};
    entries.forEach(([k, v], i) => { m[k] = i === idx ? newVal : v; });
    setParam("mapping", m);
  }

  return (
    <div>
      <span className="tp-field-label">Mapping (old → new)</span>
      <div style={{display:"flex", flexDirection:"column", gap:3, marginTop:4}}>
        {entries.map(([k, v], i) => (
          <div key={i} style={{display:"flex", gap:4, alignItems:"center"}}>
            <input className="tp-input" style={{flex:1}} placeholder="Find value"
              value={k} onChange={e => updateKey(i, e.target.value)} />
            <span style={{color:"var(--text-3)", fontSize:11}}>→</span>
            <input className="tp-input" style={{flex:1}} placeholder="Replace with"
              value={v} onChange={e => updateVal(i, e.target.value)} />
            <button className="tp-icon-btn" onClick={() => removeRow(i)} title="Remove"><X size={10}/></button>
          </div>
        ))}
        <button className="tp-ghost-btn" onClick={addRow}>+ Add row</button>
      </div>
    </div>
  );
}

// ── Full Advanced Transform Panel ─────────────────────────────────────────────
function TransformPanel({ columns, onApply, onClose }) {
  const [activeCat,    setActiveCat]    = useState(ADVANCED_CATEGORIES[0].id);
  const [activeAction, setActiveAction] = useState(ADVANCED_CATEGORIES[0].actions[0].id);
  const [params,       setParams]       = useState({});
  const [applying,     setApplying]     = useState(false);
  const [error,        setError]        = useState(null);

  function setParam(key, value) {
    setParams(p => ({ ...p, [key]: value }));
  }

  // Default params per action — ensures conditional fields render correctly on first load
  const ACTION_DEFAULTS = {
    clip_outliers:        { method: "iqr", iqr_factor: 1.5 },
    replace_outliers:     { method: "iqr", strategy: "median" },
    fill_missing:         { strategy: "mode" },
    fill_missing_interpolate: { method: "linear" },
    conditional_column:   { condition: "gt", true_label: "yes", false_label: "no" },
    cast_type:            { dtype: "float" },
    scale_numeric:        { method: "min_max" },
    bin_numeric:          { bins: 5, strategy: "equal_width" },
    round_numeric:        { decimals: 2 },
    strip_characters:     { mode: "non_printable" },
    drop_rows_missing_threshold: { threshold: 0.5 },
    drop_high_missing_columns:   { threshold: 0.5 },
    find_replace:         { regex: false, case_sensitive: true },
    merge_columns:        { separator: " ", keep_originals: false },
    standardise_mixed_dates: { dayfirst: "true", output_format: "%Y-%m-%d" },
    standardise_dates:       { output_format: "%Y-%m-%d" },
    extract_date_parts:      { parts: ["year","month","day"], dayfirst: "true" },
    calculate_date_diff:     { unit: "days", absolute: true, _diff_mode: "column" },
    flag_future_dates:       {},
    flag_weekend_dates:      {},
    age_from_date:           { unit: "years" },
    split_column:         { delimiter: " ", keep_original: false },
    normalize_phone:      {},
    drop_rows_matching:   { flags: "", keep: false },
    normalize_column_names: { style: "snake_case" },
    rename_columns_bulk:  { mapping: {} },
    map_values:           { mapping: {} },
  };

  function selectAction(catId, actionId) {
    setParams(ACTION_DEFAULTS[actionId] ?? {});
    setError(null);
    setActiveCat(catId);
    setActiveAction(actionId);
  }

  // Actions that require a column to be explicitly set
  const REQUIRES_COLUMN = [
    "find_replace","map_values","split_column","normalize_phone",
    "extract_numeric","clip_outliers","replace_outliers","bin_numeric","cast_type","conditional_column",
  ];
  const REQUIRES_COL1_COL2 = ["merge_columns"];

  // Strip empty string values from params — backend uses "" as a missing value guard
  function cleanParams(rawParams) {
    const cleaned = {};
    for (const [k, v] of Object.entries(rawParams)) {
      // Keep booleans/numbers as-is; replace "" strings with undefined (omit)
      if (v === "" || v === null) continue;
      cleaned[k] = v;
    }
    return cleaned;
  }

  async function handleApply() {
    setError(null);
    // Validate required fields
    if (REQUIRES_COLUMN.includes(activeAction) && !params.column) {
      setError("Please select a column.");
      return;
    }
    if (REQUIRES_COL1_COL2.includes(activeAction) && (!params.col1 || !params.col2)) {
      setError("Please select both columns.");
      return;
    }
    if (activeAction === "find_replace" && !params.find) {
      setError("Please enter a 'Find' value.");
      return;
    }
    setApplying(true);
    const finalParams = cleanParams(params);
    try {
      await onApply(activeAction, finalParams);
      onClose();
    } catch (err) {
      setError(err?.response?.data?.detail ?? err?.message ?? "Transform failed. Check the browser console for details.");
    } finally {
      setApplying(false);
    }
  }

  const cat    = ADVANCED_CATEGORIES.find(c => c.id === activeCat);
  const action = ADVANCED_CATEGORIES.flatMap(c => c.actions).find(a => a.id === activeAction);

  return ReactDOM.createPortal(
    <div className="tp-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="tp-panel">
        {/* Header */}
        <div className="tp-header">
          <Settings2 size={15} style={{color:"var(--accent)"}} />
          <span className="tp-title">Advanced Transform</span>
          <button className="tp-close" onClick={onClose}><X size={14}/></button>
        </div>

        <div className="tp-body">
          {/* Category + action sidebar */}
          <div className="tp-sidebar">
            {ADVANCED_CATEGORIES.map(c => {
              const CIcon = c.icon;
              return (
                <div key={c.id} className={`tp-cat ${activeCat === c.id ? "tp-cat--on" : ""}`}>
                  <button className="tp-cat-header" onClick={() => { setActiveCat(c.id); selectAction(c.id, c.actions[0].id); }}>
                    <CIcon size={12} style={{color: c.color}}/>
                    <span>{c.label}</span>
                  </button>
                  {activeCat === c.id && (
                    <div className="tp-actions-list">
                      {c.actions.map(a => (
                        <button key={a.id}
                          className={`tp-action-item ${activeAction === a.id ? "tp-action-item--on" : ""}`}
                          onClick={() => selectAction(c.id, a.id)}>
                          <ChevronRight size={9} />
                          {a.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Param form */}
          <div className="tp-form">
            {action && (
              <>
                <div className="tp-form-header">
                  <span className="tp-form-title">{action.label}</span>
                  <span className="tp-form-desc">{action.desc}</span>
                </div>
                <div className="tp-form-fields">
                  <ParamForm actionId={activeAction} params={params}
                    setParam={setParam} columns={columns} />
                </div>
              </>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="tp-footer">
          {error && (
            <div className="tp-error">
              <AlertCircle size={12} /> {error}
            </div>
          )}
          <button className="tp-btn" onClick={onClose}>Cancel</button>
          <button className="tp-btn tp-btn--primary" disabled={applying} onClick={handleApply}>
            {applying ? <Loader2 size={12} className="spin" /> : null}
            Apply Transform
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}


// ══════════════════════════════════════════════════════════════════════════════
// ── Main CleaningToolbar ──────────────────────────────────────────────────────
// ══════════════════════════════════════════════════════════════════════════════

export default function CleaningToolbar({
  sessionId, columns = [], onTransform, onAutoClean, onUndo,
  onReset, onExport, onRunAgent, loading,
  activeTab, onTabChange,
}) {
  const [nlText,       setNlText]       = useState("");
  const [nlLoading,    setNlLoading]    = useState(false);
  const [exportOpen,   setExportOpen]   = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [toast,        setToast]        = useState(null);
  const [selectedCol,  setSelectedCol]  = useState("");   // "" = all columns
  const [castDtype,    setCastDtype]    = useState("float"); // inline cast type picker
  const exportBtnRef = useRef(null);
  const toastTimer   = useRef(null);

  // Reset selected column whenever the column list changes (new dataset uploaded)
  useEffect(() => { setSelectedCol(""); }, [columns.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  const isBusy = loading || nlLoading;

  // Per-action dataset-wide flag — these always ignore the column selector
  const DATASET_WIDE = new Set([
     "remove_duplicates", "auto_clean",
     "drop_constant_columns", "drop_high_missing_columns",
     "drop_rows_missing_threshold",
     "normalize_column_names", "rename_columns_bulk",
  ]);

  function showToast(msg, type = "info") {
    clearTimeout(toastTimer.current);
    setToast({ msg, type });
    toastTimer.current = setTimeout(() => setToast(null), 3000);
  }

  const handleTransform = useCallback(async (action, params) => {
    try { await onTransform(action, params); }
    catch (err) { showToast(err?.message ?? "Transform failed", "error"); }
  }, [onTransform]);

  // NL command history stored in localStorage
  const NL_HISTORY_KEY = "datacove_nl_history";
  const [nlHistory, setNlHistory] = useState(() => {
    try { return JSON.parse(localStorage.getItem(NL_HISTORY_KEY) ?? "[]"); }
    catch { return []; }
  });
  const [nlHistOpen, setNlHistOpen] = useState(false);

  async function handleNL(e) {
    e.preventDefault();
    if (!nlText.trim()) return;
    setNlLoading(true);
    try {
      await onTransform("__nl__", { command: nlText });
      // Save to history (deduplicate, max 10)
      const updated = [nlText, ...nlHistory.filter(h => h !== nlText)].slice(0, 10);
      setNlHistory(updated);
      try { localStorage.setItem(NL_HISTORY_KEY, JSON.stringify(updated)); } catch {}
      setNlText("");
    }
    catch (err) { showToast(err?.message ?? "Command failed", "error"); }
    finally { setNlLoading(false); }
  }

  function rerunNL(cmd) {
    setNlText(cmd);
    setNlHistOpen(false);
  }

  // Build params for a ribbon action, injecting the selected column if applicable
  function buildParams(action, baseParams, actionDef) {
    // Dataset-wide actions never get a column injected
    if (DATASET_WIDE.has(action) || actionDef?.datasetWide) return baseParams;
    // cast_type needs the inline dtype selector value
    if (action === "cast_type") {
      return { ...baseParams, dtype: castDtype, ...(selectedCol ? { column: selectedCol } : {}) };
    }
    if (!selectedCol) return baseParams;
    return { ...baseParams, column: selectedCol };
  }

  // Tooltip: describe what will happen given current column selection
  function buildTip(action, tip, actionDef) {
    if (DATASET_WIDE.has(action) || actionDef?.datasetWide) return tip;
    if (selectedCol) return `${tip}\n→ Column: "${selectedCol}"`;
    return `${tip}\n→ All eligible columns`;
  }

  // Helper to render a ribbon group of flat buttons
  function RibbonGroup({ label, actions, extra }) {
    return (
      <div className="tbv7-group">
        <div className="tbv7-group-btns">
          {actions.map((def) => {
            const { action, label: lbl, icon: Icon, params, tip } = def;
            const isDatasetWide = DATASET_WIDE.has(action) || def.datasetWide;
            return (
              <button key={action}
                className={`tbv7-btn ${isDatasetWide ? "tbv7-btn--dataset" : ""}`}
                disabled={isBusy}
                onClick={() => handleTransform(action, buildParams(action, params, def))}
                title={buildTip(action, tip, def)}>
                <Icon size={12} />
                <span>{lbl}</span>
              </button>
            );
          })}
          {extra}
        </div>
        <div className="tbv7-group-label">{label}</div>
      </div>
    );
  }

  return (
    <div className="tbv7-wrap" style={{ position: "relative" }}>

      {/* ── Column selector bar ──────────────────────────────────────────── */}
      <div className="tbv7-colbar">
        <span className="tbv7-colbar-label">
          <Columns size={11} />
          Target column:
        </span>
        <div className="tbv7-colbar-pills">
          <button
            className={`tbv7-colpill ${!selectedCol ? "tbv7-colpill--on" : ""}`}
            onClick={() => setSelectedCol("")}
            title="Apply ribbon actions to all eligible columns">
            All columns
          </button>
          {columns.map(col => (
            <button
              key={col}
              className={`tbv7-colpill ${selectedCol === col ? "tbv7-colpill--on" : ""}`}
              onClick={() => setSelectedCol(c => c === col ? "" : col)}
              title={`Target "${col}" — ribbon buttons will only affect this column`}>
              {col}
            </button>
          ))}
        </div>
        {selectedCol && (
          <span className="tbv7-colbar-active">
            <CheckCircle2 size={10} />
            Targeting: <strong>{selectedCol}</strong>
            <button className="tbv7-colbar-clear" onClick={() => setSelectedCol("")} title="Clear selection">
              <X size={10} />
            </button>
          </span>
        )}
        {!selectedCol && (
          <span className="tbv7-colbar-hint">
            Pick a column to target ribbon actions, or leave on All columns
          </span>
        )}
      </div>

      {/* ── Ribbon ───────────────────────────────────────────────────────── */}
      <div className="tbv7-ribbon">

        <RibbonGroup label="Clean"     actions={CLEAN_ACTIONS}     />
        <RibbonGroup label="String"    actions={STRING_ACTIONS}    />
        <RibbonGroup label="Numeric"   actions={NUMERIC_ACTIONS}   />
        <RibbonGroup label="Missing"   actions={MISSING_ACTIONS}   />
        <RibbonGroup label="Structure" actions={STRUCTURE_ACTIONS}
          extra={
            /* Inline dtype picker for Cast Type button */
            <select
              className="tbv7-cast-sel"
              value={castDtype}
              onChange={e => setCastDtype(e.target.value)}
              title="Data type to cast to when using Cast Type button"
              onClick={e => e.stopPropagation()}>
              <option value="float">float</option>
              <option value="int">int</option>
              <option value="string">string</option>
              <option value="bool">bool</option>
              <option value="date">date</option>
              <option value="category">category</option>
            </select>
          }
        />
        <RibbonGroup label="Date"      actions={DATE_ACTIONS}      />

        {/* Advanced Transform */}
        <div className="tbv7-group">
          <div className="tbv7-group-btns">
            <button
              className={`tbv7-btn tbv7-btn--lg tbv7-btn--accent ${showAdvanced ? "tbv7-btn--active" : ""}`}
              disabled={isBusy}
              onClick={() => setShowAdvanced(o => !o)}
              title="Open full advanced transform panel (35+ operations)">
              <Settings2 size={13} />
              <span>Transform…</span>
            </button>
          </div>
          <div className="tbv7-group-label">Advanced</div>
        </div>

        {/* AI */}
        <div className="tbv7-group">
          <div className="tbv7-group-btns">
            <button className="tbv7-btn tbv7-btn--primary tbv7-btn--lg" disabled={isBusy}
              onClick={onAutoClean} title="Run full auto-clean suite">
              {isBusy && !nlLoading
                ? <Loader2 size={13} className="spin" />
                : <Wand2 size={13} />}
              <span>Auto-Clean</span>
            </button>
            {onRunAgent && (
              <button className="tbv7-btn tbv7-btn--ai tbv7-btn--lg" disabled={isBusy}
                onClick={onRunAgent} title="Run full AI cleaning pipeline">
                <Bot size={13} /><span>AI Agent</span>
              </button>
            )}
          </div>
          <div className="tbv7-group-label">AI</div>
        </div>

        {/* History */}
        <div className="tbv7-group">
          <div className="tbv7-group-btns">
            <button className="tbv7-btn" disabled={isBusy} onClick={onUndo}
              title="Undo last action (Ctrl+Z)">
              <Undo2 size={12} /><span>Undo</span>
            </button>
            {onReset && (
              <button className="tbv7-btn tbv7-btn--danger" disabled={isBusy}
                onClick={onReset} title="Reset to original dataset">
                <RotateCcw size={12} /><span>Reset</span>
              </button>
            )}
          </div>
          <div className="tbv7-group-label">History</div>
        </div>

        {/* Export */}
        <div className="tbv7-group">
          <div className="tbv7-group-btns">
            <button ref={exportBtnRef}
              className={`tbv7-btn tbv7-btn--export ${exportOpen ? "tbv7-btn--active" : ""}`}
              onClick={() => setExportOpen(o => !o)}
              title="Download cleaned dataset">
              <Download size={12} /><span>Export</span>
              <ChevronDown size={9} style={{ marginLeft:1, opacity:.6 }} />
            </button>
            <PortalDropdown anchorRef={exportBtnRef} open={exportOpen}
              onClose={() => setExportOpen(false)}>
              {EXPORT_FMTS.map(({ fmt, label, desc }) => (
                <button key={fmt} className="tbv7-export-item"
                  onClick={() => { onExport(fmt); setExportOpen(false); }}>
                  <Download size={10} />
                  <span className="tbv7-export-label">{label}</span>
                  <span className="tbv7-export-desc">{desc}</span>
                </button>
              ))}
            </PortalDropdown>
          </div>
          <div className="tbv7-group-label">Export</div>
        </div>

        {/* Panels */}
        {onTabChange && (
          <div className="tbv7-group tbv7-group--panels">
            <div className="tbv7-group-btns">
              {ALL_TABS.map((id) => {
                const Icon = TAB_ICONS[id];
                return (
                  <button key={id}
                    className={`tbv7-btn tbv7-tab-btn ${activeTab === id ? "tbv7-tab-btn--on" : ""}`}
                    onClick={() => onTabChange(id)} title={id}>
                    {Icon && <Icon size={11} />}<span>{id}</span>
                  </button>
                );
              })}
            </div>
            <div className="tbv7-group-label">Panels</div>
          </div>
        )}
      </div>

      {/* ── NL bar ───────────────────────────────────────────────────────── */}
      <form className="tbv7-nl" onSubmit={handleNL}>
        <div style={{position:"relative",flex:1}}>
          <input className="tbv7-nl-input" value={nlText}
            onChange={e => setNlText(e.target.value)}
            placeholder='e.g. "find replace $0 with 0 in revenue", "clip outliers in age", "bin price into 5 buckets"…'
            disabled={nlLoading}
            onFocus={() => nlHistory.length && setNlHistOpen(true)}
            onBlur={() => setTimeout(() => setNlHistOpen(false), 200)}
          />
          {nlHistOpen && nlHistory.length > 0 && (
            <div style={{position:"absolute",top:"calc(100% + 4px)",left:0,right:0,zIndex:9999,
                         background:"var(--surface-2)",border:"1px solid var(--border)",
                         borderRadius:8,boxShadow:"0 8px 32px rgba(0,0,0,.5)",overflow:"hidden"}}>
              <div style={{padding:"4px 10px 2px",fontSize:9,color:"var(--text-3)",
                           textTransform:"uppercase",letterSpacing:".08em"}}>Recent commands</div>
              {nlHistory.map((cmd,i) => (
                <button key={i} type="button"
                  style={{width:"100%",textAlign:"left",padding:"6px 10px",background:"none",
                          border:"none",color:"var(--text-1)",fontSize:11,cursor:"pointer",
                          borderTop:"1px solid var(--border)"}}
                  onMouseDown={() => rerunNL(cmd)}
                  onMouseEnter={e => e.target.style.background="var(--surface-3)"}
                  onMouseLeave={e => e.target.style.background="none"}>
                  {cmd}
                </button>
              ))}
            </div>
          )}
        </div>
        <button className="tbv7-btn tbv7-btn--primary tbv7-nl-btn" type="submit"
          disabled={nlLoading || !nlText.trim()}>
          {nlLoading ? <Loader2 size={12} className="spin" /> : <Send size={12} />}
          <span>Run</span>
        </button>
      </form>

      {/* Toast */}
      {toast && ReactDOM.createPortal(
        <div className={`tbv7-toast tbv7-toast--${toast.type}`}>
          {toast.type === "error" ? <Info size={11} /> : <CheckCircle2 size={11} />}
          {toast.msg}
        </div>,
        document.body
      )}

      {/* ── Advanced Transform Panel (modal) ─────────────────────────────── */}
      {showAdvanced && (
        <TransformPanel
          columns={columns}
          onApply={handleTransform}
          onClose={() => setShowAdvanced(false)}
        />
      )}

      {/* ── Styles ────────────────────────────────────────────────────────── */}
      <style>{`
        /* ── Wrapper ───────────────────────────────────────────────────── */
        .tbv7-wrap  { display:flex; flex-direction:column; gap:0; }

        /* ── Column selector bar ─────────────────────────────────────── */
        .tbv7-colbar {
          display:flex; align-items:center; gap:6px;
          padding:4px 10px 4px 12px;
          background:var(--surface-glass);
          border-bottom:1px solid var(--border-glass);
          overflow-x:auto; scrollbar-width:none; flex-shrink:0;
          min-height:28px;
          backdrop-filter: blur(12px);
          -webkit-backdrop-filter: blur(12px);
        }
        .tbv7-colbar-hint {
          margin-left:6px; font-size:9px; color:var(--text-3);
          font-style:italic; white-space:nowrap; flex-shrink:0;
        }

        /* Dataset-wide buttons get a subtle different tint to signal they ignore the column */
        .tbv7-btn--dataset { opacity:.85; }
        .tbv7-btn--dataset:hover:not(:disabled) {
          background:rgba(239,68,68,.06);
          border-color:rgba(239,68,68,.15);
          color:var(--text-0);
        }

        /* Inline cast type selector inside Structure group */
        .tbv7-cast-sel {
          padding:3px 5px; border-radius:5px; font-size:9px; font-weight:600;
          border:1px solid rgba(99,102,241,.25); background:rgba(99,102,241,.08);
          color:var(--accent-light); cursor:pointer; outline:none;
          align-self:center; margin-left:2px;
          max-width:68px;
        }
        .tbv7-cast-sel:hover { border-color:rgba(99,102,241,.45); background:rgba(99,102,241,.14); }
        .tbv7-cast-sel:focus { border-color:var(--accent); }

        .tbv7-colbar-label {
          display:flex; align-items:center; gap:4px;
          font-size:9px; font-weight:700; text-transform:uppercase;
          letter-spacing:.08em; color:var(--text-3);
          white-space:nowrap; flex-shrink:0;
        }

        .tbv7-colbar-pills {
          display:flex; align-items:center; gap:3px; flex-shrink:0;
        }

        .tbv7-colpill {
          display:inline-flex; align-items:center;
          padding:2px 8px; border-radius:99px;
          font-size:10px; font-weight:500;
          border:1px solid var(--border);
          background:var(--surface-2); color:var(--text-2);
          cursor:pointer; white-space:nowrap;
          transition:all .12s;
        }
        .tbv7-colpill:hover {
          background:var(--accent-dim);
          border-color:var(--accent);
          color:var(--accent);
        }
        .tbv7-colpill--on {
          background:var(--accent-dim);
          border-color:var(--accent);
          color:var(--accent); font-weight:700;
          box-shadow:0 0 8px var(--accent-glow);
        }

        .tbv7-colbar-active {
          display:inline-flex; align-items:center; gap:4px;
          margin-left:4px; padding:2px 8px 2px 6px;
          border-radius:99px; flex-shrink:0;
          font-size:10px; color:var(--green);
          background:var(--green-dim);
          border:1px solid var(--green);
          white-space:nowrap;
        }
        .tbv7-colbar-active strong { font-weight:700; }
        .tbv7-colbar-clear {
          display:inline-flex; align-items:center;
          background:none; border:none; cursor:pointer;
          color:var(--green); padding:0; margin-left:2px;
        }
        .tbv7-colbar-clear:hover { color:var(--accent); }


        .tbv7-ribbon { display:flex; align-items:flex-end; gap:0;
                       flex-wrap:nowrap; overflow-x:auto; scrollbar-width:none; }
        .tbv7-ribbon::-webkit-scrollbar { display:none; }

        .tbv7-group { display:flex; flex-direction:column; align-items:flex-start; gap:3px;
                      padding:5px 8px 0; flex-shrink:0;
                      background:var(--surface-2);
                      border-radius:8px;
                      border:1px solid var(--border);
                      margin-right:5px;
                      backdrop-filter:blur(8px);
                      box-shadow:var(--shadow-sm); }
        .tbv7-group-btns  { display:flex; align-items:center; gap:2px; }
        .tbv7-group-label { font-size:9px; font-weight:700; color:var(--text-1);
                            text-transform:uppercase; letter-spacing:.1em;
                            width:100%; text-align:center; padding:3px 0 5px; }

        /* ── Buttons ────────────────────────────────────────────────────── */
        .tbv7-btn { display:inline-flex; flex-direction:column; align-items:center;
                    justify-content:center; gap:2px; padding:6px 8px; min-width:42px;
                    border-radius:6px; border:1px solid transparent;
                    background:none; color:var(--text-1); font-size:10px; font-weight:500;
                    cursor:pointer; white-space:nowrap; line-height:1;
                    transition:all .15s ease; }
        .tbv7-btn:hover:not(:disabled) { background:var(--accent-dim); border-color:var(--border-glass); color:var(--accent); }
        .tbv7-btn:disabled { opacity:.35; cursor:not-allowed; }
        .tbv7-btn--active  { background:var(--accent-dim); border-color:var(--accent); color:var(--accent); }
        .tbv7-btn--lg      { flex-direction:row !important; gap:5px !important;
                             padding:7px 13px !important; font-size:11px !important;
                             min-width:unset !important; align-items:center !important;
                             font-weight:600 !important; }
        .tbv7-btn--primary { background:var(--gradient-primary); color:#fff;
                             border:none; font-weight:600;
                             box-shadow:var(--shadow-accent); }
        .tbv7-btn--primary:hover:not(:disabled) { filter:brightness(1.1); box-shadow:var(--shadow-glow); transform:translateY(-1px); }
        .tbv7-btn--ai      { background:var(--gradient-accent); color:#fff;
                             border:none; font-weight:600;
                             box-shadow:var(--shadow-accent); }
        .tbv7-btn--ai:hover:not(:disabled) { filter:brightness(1.1); box-shadow:var(--shadow-glow); transform:translateY(-1px); }
        .tbv7-btn--accent  { background:var(--accent-dim); border:1px solid var(--accent); color:var(--accent); font-weight:600;
                             box-shadow:0 0 12px var(--accent-glow); }
        .tbv7-btn--accent:hover:not(:disabled) { background:var(--accent); color:#fff; }
        .tbv7-btn--danger  { color:var(--red); }
        .tbv7-btn--danger:hover:not(:disabled) { background:var(--red-dim); border-color:var(--red); }
        .tbv7-btn--export  { flex-direction:row !important; gap:4px !important;
                             font-size:11px !important; padding:6px 10px !important;
                             min-width:unset !important; align-items:center !important; }

        /* Export item */
        .tbv7-export-item { width:100%; display:flex; align-items:center; gap:7px;
                            padding:7px 10px; border-radius:5px; border:none;
                            background:none; color:var(--text-0); font-size:12px;
                            font-weight:500; cursor:pointer; text-align:left; }
        .tbv7-export-item:hover { background:var(--accent-dim); color:var(--accent); }
        .tbv7-export-label { font-weight:600; min-width:36px; }
        .tbv7-export-desc  { margin-left:auto; font-size:10px; color:var(--text-2); }

        /* Panels group */
        .tbv7-group--panels { flex-shrink:0; }
        .tbv7-tab-btn { flex-direction:row !important; gap:4px !important;
                        padding:5px 8px !important; min-width:unset !important;
                        font-size:10px !important; border:1px solid transparent;
                        border-radius:6px !important; }
        .tbv7-tab-btn:hover:not(:disabled) { background:var(--accent-dim); border-color:var(--border-glass); color:var(--accent); }
        .tbv7-tab-btn--on { background:var(--accent-dim) !important; border-color:var(--accent) !important;
                            color:var(--accent) !important; font-weight:600 !important; }

        /* ── NL row ─────────────────────────────────────────────────────── */
        .tbv7-nl       { display:flex; gap:6px; }
        .tbv7-nl-input { flex:1; padding:7px 14px; border-radius:8px;
                         border:1px solid var(--border); background:var(--surface-2);
                         color:var(--text-0); font-size:12px; outline:none; font-family:inherit;
                         backdrop-filter:blur(4px); }
        .tbv7-nl-input::placeholder { color:var(--text-2); font-size:11px; }
        .tbv7-nl-input:focus        { border-color:var(--accent); box-shadow:var(--shadow-accent); }
        .tbv7-nl-btn   { flex-direction:row !important; gap:5px !important;
                         padding:6px 14px !important; min-width:unset !important; }

        /* ── Toast ──────────────────────────────────────────────────────── */
        .tbv7-toast      { position:fixed; bottom:40px; left:50%;
                           transform:translateX(-50%); display:flex; align-items:center;
                           gap:6px; padding:8px 16px; border-radius:var(--radius-md);
                           font-size:12px; font-weight:600; white-space:nowrap;
                           z-index:99999; pointer-events:none; box-shadow:var(--shadow-lg); backdrop-filter: blur(8px); }
        .tbv7-toast--info  { background:var(--surface-glass); border:1px solid var(--border); color:var(--text-0); }
        .tbv7-toast--error { background:var(--red-dim); border:1px solid var(--red); color:var(--red); }

        /* ─────────────────────────────────────────────────────────────────
           Advanced Transform Panel
        ───────────────────────────────────────────────────────────────── */
        .tp-overlay { position:fixed; inset:0; z-index:10000;
                      background:rgba(0,0,0,.5); display:flex;
                      align-items:center; justify-content:center;
                      backdrop-filter:blur(4px); }

        .tp-panel  { width:720px; max-width:96vw; max-height:88vh;
                     display:flex; flex-direction:column;
                     background:var(--surface-1); border-radius:16px;
                     border:1px solid var(--border-2);
                     box-shadow:var(--shadow-lg); overflow:hidden; }

        .tp-header { display:flex; align-items:center; gap:8px;
                     padding:14px 18px; border-bottom:1px solid var(--border);
                     background:linear-gradient(180deg, var(--surface-2) 0%, var(--surface-1) 100%); }
        .tp-title  { flex:1; font-size:13px; font-weight:700; color:var(--text-0); }
        .tp-close  { display:flex; align-items:center; justify-content:center;
                     width:26px; height:26px; border-radius:6px;
                     border:1px solid var(--border); background:none;
                     color:var(--text-2); cursor:pointer; }
        .tp-close:hover { background:var(--surface-3); color:var(--text-0); }

        .tp-body   { display:flex; flex:1; overflow:hidden; }

        /* Sidebar */
        .tp-sidebar { width:190px; flex-shrink:0; border-right:1px solid var(--border);
                      overflow-y:auto; padding:6px 0; background:var(--surface-2); }
        .tp-cat         { border-bottom:1px solid var(--border); }
        .tp-cat:last-child { border-bottom:none; }
        .tp-cat-header  { width:100%; display:flex; align-items:center; gap:7px;
                          padding:8px 14px; border:none; background:none;
                          color:var(--text-1); font-size:11px; font-weight:600;
                          cursor:pointer; text-align:left; }
        .tp-cat-header:hover  { background:var(--surface-3); }
        .tp-cat--on .tp-cat-header { color:var(--text-0); background:var(--surface-3); }
        .tp-actions-list { padding:2px 0 6px; }
        .tp-action-item  { width:100%; display:flex; align-items:center; gap:5px;
                           padding:5px 14px 5px 22px; border:none; background:none;
                           color:var(--text-2); font-size:11px; cursor:pointer; text-align:left; }
        .tp-action-item:hover     { background:var(--accent-dim); color:var(--text-0); }
        .tp-action-item--on       { background:var(--accent-dim); color:var(--accent-light);
                                    font-weight:600; }

        /* Form area */
        .tp-form        { flex:1; overflow-y:auto; display:flex; flex-direction:column; }
        .tp-form-header { padding:16px 20px 10px; border-bottom:1px solid var(--border); }
        .tp-form-title  { display:block; font-size:13px; font-weight:700; color:var(--text-0); }
        .tp-form-desc   { display:block; font-size:11px; color:var(--text-2); margin-top:3px; }
        .tp-form-fields { padding:14px 20px; display:flex; flex-direction:column; gap:10px; }

        /* Form controls */
        .tp-field       { display:flex; flex-direction:column; gap:4px; }
        .tp-field--row  { flex-direction:row !important; align-items:center; gap:8px; }
        .tp-field span, .tp-field-label { font-size:11px; font-weight:600; color:var(--text-1); }
        .tp-input       { padding:6px 9px; border-radius:var(--radius-sm);
                          border:1px solid var(--border); background:var(--surface-2);
                          color:var(--text-0); font-size:12px; outline:none; width:100%;
                          font-family:inherit; }
        .tp-input--sm   { max-width:100px; }
        .tp-input:focus { border-color:var(--accent); box-shadow:var(--shadow-accent); }
        select.tp-input { appearance:auto; }
        .tp-hint        { font-size:11px; color:var(--text-2); margin:0; line-height:1.5; }
        .tp-icon-btn    { display:flex; align-items:center; justify-content:center;
                          width:20px; height:20px; border-radius:4px; border:1px solid var(--border);
                          background:none; color:var(--text-2); cursor:pointer; flex-shrink:0; }
        .tp-icon-btn:hover { background:var(--red-dim); color:var(--red); border-color:var(--red); }
        .tp-ghost-btn   { background:none; border:1px dashed var(--border); border-radius:5px;
                          color:var(--accent); font-size:11px; padding:4px 10px;
                          cursor:pointer; margin-top:2px; }
        .tp-ghost-btn:hover { background:var(--accent-dim); }

        /* Footer */
        .tp-footer { display:flex; justify-content:flex-end; align-items:center; gap:8px;
                     padding:12px 18px; border-top:1px solid var(--border);
                     background:var(--surface-2); }
        .tp-error  { flex:1; display:flex; align-items:center; gap:5px;
                     font-size:11px; color:var(--red); font-weight:500; }
        .tp-btn    { padding:7px 16px; border-radius:var(--radius-sm);
                     border:1px solid var(--border); background:var(--surface-3);
                     color:var(--text-1); font-size:12px; font-weight:600; cursor:pointer; }
        .tp-btn:hover { background:var(--accent-dim); color:var(--accent); border-color:var(--accent); }
        .tp-btn--primary { background:var(--gradient-primary); color:#fff; border:none;
                           box-shadow:var(--shadow-accent); }
        .tp-btn--primary:hover:not(:disabled) { filter:brightness(1.1); box-shadow:var(--shadow-glow); }
        .tp-btn--primary:disabled { opacity:.5; cursor:not-allowed; }

        @keyframes spin { to { transform:rotate(360deg); } }
        .spin { animation:spin .7s linear infinite; }
      `}</style>
    </div>
  );
}
