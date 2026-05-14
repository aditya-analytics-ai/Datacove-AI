/**
 * ProfilingCharts — Recharts-based charts for dataset profile.
 * Shows: missing value bar chart, column type distribution, value distribution.
 */
import React, { useState } from "react";
import { TrendingUp, ChevronDown, ChevronRight } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";

const TYPE_COLORS = {
  numeric:     "#6366f1",
  categorical: "#22c55e",
  text:        "#f59e0b",
  email:       "#0891b2",
  phone:       "#a78bfa",
  date:        "#f43f5e",
  country:     "#14b8a6",
  city:        "#fb923c",
  currency:    "#fbbf24",
};

export default function ProfilingCharts({ profile }) {
  const [open, setOpen] = useState(true);

  if (!profile?.columns_profile?.length) return null;

  const cols = profile.columns_profile;

  // Missing values chart data (only cols with missing)
  const missingData = cols
    .filter(c => c.missing_pct > 0)
    .sort((a, b) => b.missing_pct - a.missing_pct)
    .slice(0, 12)
    .map(c => ({ name: c.column, pct: c.missing_pct }));

  // Type distribution pie
  const typeCounts = {};
  cols.forEach(c => {
    typeCounts[c.detected_type] = (typeCounts[c.detected_type] ?? 0) + 1;
  });
  const typeData = Object.entries(typeCounts).map(([name, value]) => ({ name, value }));

  return (
    <div className="pc-wrap">
      <button className="pc-header" onClick={() => setOpen(o => !o)}>
        <TrendingUp size={14} color="var(--accent)" />
        <span className="pc-title">Profiling Charts</span>
        {open ? <ChevronDown size={13}/> : <ChevronRight size={13}/>}
      </button>

      {open && (
        <div className="pc-body">
          {/* Missing values bar */}
          {missingData.length > 0 && (
            <div className="pc-section">
              <p className="pc-section-title">Missing Values by Column (%)</p>
              <ResponsiveContainer width="100%" height={missingData.length * 22 + 30}>
                <BarChart
                  data={missingData}
                  layout="vertical"
                  margin={{ top: 0, right: 30, bottom: 0, left: 4 }}
                >
                  <XAxis
                    type="number" domain={[0, 100]}
                    tick={{ fontSize: 10, fill: "var(--text-2)" }}
                    axisLine={false} tickLine={false}
                    tickFormatter={v => v + "%"}
                  />
                  <YAxis
                    type="category" dataKey="name"
                    width={80} tick={{ fontSize: 10, fill: "var(--text-1)" }}
                    axisLine={false} tickLine={false}
                  />
                  <Tooltip
                    contentStyle={{ background: "var(--surface-2)", border: "1px solid var(--border)", fontSize: 11 }}
                    formatter={v => [v + "%", "Missing"]}
                  />
                  <Bar dataKey="pct" radius={[0, 4, 4, 0]} fill="#ef4444" opacity={0.8} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Column type pie */}
          {typeData.length > 0 && (
            <div className="pc-section">
              <p className="pc-section-title">Column Type Distribution</p>
              <ResponsiveContainer width="100%" height={160}>
                <PieChart>
                  <Pie
                    data={typeData}
                    cx="50%" cy="50%"
                    outerRadius={60}
                    dataKey="value"
                    label={({ name, percent }) =>
                      percent > 0.08 ? `${name} ${(percent * 100).toFixed(0)}%` : ""
                    }
                    labelLine={false}
                  >
                    {typeData.map((entry, i) => (
                      <Cell
                        key={i}
                        fill={TYPE_COLORS[entry.name] ?? `hsl(${i * 40},60%,55%)`}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: "var(--surface-2)", border: "1px solid var(--border)", fontSize: 11 }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      <style>{`
        .pc-wrap         { background:var(--surface-1); border-radius:12px; overflow:hidden; }
        .pc-header       { width:100%; display:flex; align-items:center; gap:8px; padding:12px 14px;
                           background:none; border:none; cursor:pointer; color:var(--text-1); }
        .pc-header:hover { background:var(--surface-2); }
        .pc-title        { flex:1; font-size:13px; font-weight:700; color:var(--text-0); text-align:left; }
        .pc-body         { padding:4px 14px 14px; display:flex; flex-direction:column; gap:16px; }
        .pc-section      { display:flex; flex-direction:column; gap:6px; }
        .pc-section-title { font-size:11px; font-weight:700; color:var(--text-2);
                            text-transform:uppercase; letter-spacing:.05em; margin:0; }
      `}</style>
    </div>
  );
}
