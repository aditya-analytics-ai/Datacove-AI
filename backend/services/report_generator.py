"""
report_generator.py - HTML quality report generator v2.

New in v2:
  - Accepts optional audit_entries parameter
  - Renders a full "Change Audit Trail" section when entries are present
  - XSS-safe: all dynamic values pass through html.escape()
  - Sampling notice shown when profile was computed on a sample

Sections:
  1. Dataset overview (rows, cols, health score, grade)
  2. Health score breakdown (deductions table)
  3. Issues list (severity-coloured)
  4. Column profiles (per-column stats table)
  5. Anomalies (outliers)
  6. Change Audit Trail (if audit_entries supplied)
"""
from __future__ import annotations

import html
from datetime import datetime
from typing import Any, Dict, List, Optional


def generate_html_report(
    filename:      str,
    profile:       Dict[str, Any],
    issues:        List[Dict[str, Any]],
    health:        Dict[str, Any],
    anomalies:     List[Dict[str, Any]],
    audit_entries: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Return a complete self-contained HTML string."""

    now     = datetime.now().strftime("%Y-%m-%d %H:%M")
    score   = health.get("score", 0)
    grade   = health.get("grade", "?")
    rows    = profile.get("rows", 0)
    cols    = profile.get("columns", 0)
    missing = health.get("missing_pct", 0)
    dups    = health.get("duplicate_pct", 0)

    score_color = "#22c55e" if score >= 80 else ("#f59e0b" if score >= 60 else "#ef4444")

    # ── Sampling notice ───────────────────────────────────────────────────────
    sampling = profile.get("sampling", {})
    sampling_notice = ""
    if sampling.get("was_sampled"):
        pct  = sampling.get("sample_pct", "?")
        note = html.escape(sampling.get("note", ""))
        sampling_notice = (
            f'<p style="font-size:12px;color:#f59e0b;margin-bottom:16px">'
            f'⚠ {note} ({pct}% of full dataset)</p>'
        )

    # ── Issues table ──────────────────────────────────────────────────────────
    severity_colors = {"high": "#ef4444", "medium": "#f59e0b", "low": "#6366f1"}
    issues_rows = "".join(
        f"""<tr>
          <td><span style="color:{severity_colors.get(i.get('severity','low'),'#888')};
                font-weight:700;text-transform:uppercase;font-size:11px">
            {html.escape(i.get('severity',''))}
          </span></td>
          <td>{html.escape(i.get('type','').replace('_',' '))}</td>
          <td><code>{html.escape(str(i.get('column') or '-'))}</code></td>
          <td>{html.escape(i.get('description',''))}</td>
        </tr>"""
        for i in issues
    ) or "<tr><td colspan='4' style='color:#888'>No issues detected.</td></tr>"

    # ── Column profile table ──────────────────────────────────────────────────
    col_rows = ""
    for cp in profile.get("columns_profile", []):
        ns = cp.get("numeric_stats", {})
        col_rows += f"""<tr>
          <td><code>{html.escape(cp.get('column',''))}</code></td>
          <td>{html.escape(cp.get('dtype',''))}</td>
          <td>{html.escape(cp.get('detected_type',''))}</td>
          <td>{cp.get('missing_count',0)} ({cp.get('missing_pct',0)}%)</td>
          <td>{cp.get('unique_count',0)}</td>
          <td>{ns.get('mean','-') if ns else '-'}</td>
          <td>{ns.get('min','-') if ns else '-'}</td>
          <td>{ns.get('max','-') if ns else '-'}</td>
        </tr>"""

    # ── Deductions table ──────────────────────────────────────────────────────
    ded_rows = "".join(
        f"<tr><td>{html.escape(d.get('reason',''))}</td>"
        f"<td style='color:#ef4444;font-weight:700'>{d.get('points',0):.1f}</td></tr>"
        for d in health.get("deductions", [])
    ) or "<tr><td colspan='2' style='color:#888'>No deductions.</td></tr>"

    # ── Anomalies ─────────────────────────────────────────────────────────────
    anom_rows = "".join(
        f"<tr><td><code>{html.escape(a.get('column',''))}</code></td>"
        f"<td>{a.get('outlier_count',0)}</td>"
        f"<td>{html.escape(a.get('method',''))}</td>"
        f"<td>{html.escape(a.get('description',''))}</td></tr>"
        for a in anomalies
    ) or "<tr><td colspan='4' style='color:#888'>No anomalies detected.</td></tr>"

    # ── Audit trail section ───────────────────────────────────────────────────
    audit_section = ""
    if audit_entries:
        trigger_colors = {
            "user":     "#6366f1",
            "ai":       "#7c3aed",
            "pipeline": "#0891b2",
            "auto":     "#059669",
        }

        audit_rows = ""
        for e in audit_entries:
            trigger   = html.escape(e.get("triggered_by", "user"))
            t_color   = trigger_colors.get(e.get("triggered_by", "user"), "#888")
            action    = html.escape(e.get("action", "").replace("_", " ").title())
            col       = html.escape(str(e.get("params", {}).get("column") or "-"))
            ts        = html.escape(e.get("timestamp", "")[:19].replace("T", " "))
            cells     = e.get("cells_changed", 0)
            rows_rmvd = max(0, e.get("rows_before", 0) - e.get("rows_after", 0))
            summary   = html.escape(e.get("summary", ""))
            conf      = e.get("ai_confidence")
            conf_str  = f"{conf:.0%}" if conf is not None else "-"

            audit_rows += f"""<tr>
              <td style="color:#7d85a0;font-size:11px">{ts}</td>
              <td>{action}</td>
              <td><code>{col}</code></td>
              <td>{cells:,}</td>
              <td>{rows_rmvd:,}</td>
              <td><span style="color:{t_color};font-weight:700;font-size:11px;
                    text-transform:uppercase">{trigger}</span></td>
              <td style="color:#7d85a0;font-size:11px">{conf_str}</td>
              <td style="font-size:11px;color:#a0a8c0">{summary}</td>
            </tr>"""

        total_cells = sum(e.get("cells_changed", 0) for e in audit_entries)
        total_rows  = sum(
            max(0, e.get("rows_before", 0) - e.get("rows_after", 0))
            for e in audit_entries
        )

        audit_section = f"""
<h2>Change Audit Trail ({len(audit_entries)} actions)</h2>
<p style="font-size:12px;color:#7d85a0;margin-bottom:12px">
  Total: <strong style="color:#e0e2ea">{total_cells:,} cells updated</strong>,
  <strong style="color:#e0e2ea">{total_rows:,} rows removed</strong>
  across {len(audit_entries)} operation(s).
</p>
<table>
  <thead><tr>
    <th>Timestamp</th><th>Action</th><th>Column</th>
    <th>Cells Changed</th><th>Rows Removed</th>
    <th>Source</th><th>AI Conf.</th><th>Summary</th>
  </tr></thead>
  <tbody>{audit_rows}</tbody>
</table>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Datacove Quality Report - {html.escape(filename)}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0d0f14;color:#e0e2ea;padding:32px;line-height:1.5}}
  h1{{font-size:24px;font-weight:800;margin-bottom:4px}}
  h2{{font-size:16px;font-weight:700;margin:28px 0 12px;color:#a0a8c0;text-transform:uppercase;letter-spacing:.07em}}
  .meta{{font-size:13px;color:#7d85a0;margin-bottom:32px}}
  .hero{{display:flex;gap:24px;flex-wrap:wrap;margin-bottom:8px}}
  .card{{background:#141720;border:1px solid #2a2f42;border-radius:12px;padding:20px 24px;flex:1;min-width:140px}}
  .card-label{{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:#7d85a0;margin-bottom:6px}}
  .card-value{{font-size:28px;font-weight:800}}
  table{{width:100%;border-collapse:collapse;font-size:13px;background:#141720;border-radius:10px;overflow:hidden;margin-bottom:8px}}
  th{{text-align:left;padding:10px 14px;color:#7d85a0;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid #2a2f42}}
  td{{padding:9px 14px;border-bottom:1px solid #1c2030;color:#c0c5d8}}
  tr:last-child td{{border-bottom:none}}
  code{{font-family:monospace;font-size:12px;background:#1c2030;padding:1px 5px;border-radius:4px;color:#a0c4ff}}
</style>
</head>
<body>
<h1>📊 Data Quality Report</h1>
<p class="meta">File: <strong>{html.escape(filename)}</strong> &nbsp;·&nbsp; Generated: {now}</p>
{sampling_notice}

<div class="hero">
  <div class="card">
    <div class="card-label">Health Score</div>
    <div class="card-value" style="color:{score_color}">{score} <span style="font-size:18px">/ 100</span></div>
  </div>
  <div class="card">
    <div class="card-label">Grade</div>
    <div class="card-value" style="color:{score_color}">{grade}</div>
  </div>
  <div class="card">
    <div class="card-label">Rows</div>
    <div class="card-value">{rows:,}</div>
  </div>
  <div class="card">
    <div class="card-label">Columns</div>
    <div class="card-value">{cols}</div>
  </div>
  <div class="card">
    <div class="card-label">Missing %</div>
    <div class="card-value" style="color:{'#ef4444' if missing>10 else '#f59e0b' if missing>2 else '#22c55e'}">{missing}%</div>
  </div>
  <div class="card">
    <div class="card-label">Duplicate %</div>
    <div class="card-value" style="color:{'#ef4444' if dups>5 else '#f59e0b' if dups>0 else '#22c55e'}">{dups}%</div>
  </div>
</div>

<h2>Score Breakdown</h2>
<table><thead><tr><th>Reason</th><th>Deduction</th></tr></thead><tbody>{ded_rows}</tbody></table>

<h2>Issues ({len(issues)} total)</h2>
<table><thead><tr><th>Severity</th><th>Type</th><th>Column</th><th>Description</th></tr></thead>
<tbody>{issues_rows}</tbody></table>

<h2>Column Profiles</h2>
<table><thead><tr><th>Column</th><th>Dtype</th><th>Type</th><th>Missing</th><th>Unique</th>
<th>Mean</th><th>Min</th><th>Max</th></tr></thead><tbody>{col_rows}</tbody></table>

<h2>Anomalies</h2>
<table><thead><tr><th>Column</th><th>Outliers</th><th>Method</th><th>Description</th></tr></thead>
<tbody>{anom_rows}</tbody></table>
{audit_section}

<p style="margin-top:40px;font-size:11px;color:#4a5068">Generated by Datacove v6 · {now}</p>
</body></html>"""
