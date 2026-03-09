"""
HTML QC Report Generator - Layer 4

Generates a self-contained qc_report.html file in the output folder.
Designed for non-technical research students — color-coded, scannable,
requires no external CSS or JS libraries (everything inline).

Sections:
  1. Overall status banner (green / yellow / red)
  2. Per-subject summary table
  3. BIDS quality findings (Layer 1)
  4. Motion analysis results (Layer 3)
"""

from datetime import datetime
from pathlib import Path
from typing import List


def generate(
    output_folder: str,
    qc_findings,
    motion_results,
    conversion_successes: List[dict],
    conversion_failures: List[dict],
) -> str:
    """
    Write qc_report.html to output_folder.

    Args:
        output_folder:          Pipeline output directory path
        qc_findings:            List[QCFinding] from BIDSQualityChecker
        motion_results:         List[MotionResult] from motion_parser
        conversion_successes:   Report.successful list (dicts with sub_id/ses_id)
        conversion_failures:    Report.failed list (dicts with sub_id/ses_id/error)

    Returns:
        Path to the generated HTML file as a string.
    """
    html = _build_html(
        output_folder, qc_findings, motion_results,
        conversion_successes, conversion_failures
    )
    out_path = Path(output_folder) / "qc_report.html"
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception:
        pass
    return str(out_path)


# ---------------------------------------------------------------------------
# HTML construction
# ---------------------------------------------------------------------------

def _build_html(output_folder, qc_findings, motion_results,
                conversion_successes, conversion_failures) -> str:
    errors = [f for f in qc_findings if f.severity.value == "ERROR"]
    warnings = [f for f in qc_findings if f.severity.value == "WARNING"]
    rescans = [m for m in motion_results if m.flag == "RESCAN"]
    motion_warns = [m for m in motion_results if m.flag == "WARNING"]

    n_critical = len(errors) + len(rescans)
    n_warnings = len(warnings) + len(motion_warns)

    if n_critical > 0:
        banner_color = "#c0392b"
        banner_bg = "#fdf0ef"
        banner_icon = "&#x26A0;"
        banner_title = f"{n_critical} error(s) detected"
        banner_sub = f"{n_critical} error(s) and {n_warnings} warning(s) found. See details below."
    elif n_warnings > 0:
        banner_color = "#d68910"
        banner_bg = "#fef9e7"
        banner_icon = "&#x26A0;"
        banner_title = f"{n_warnings} warning(s) detected"
        banner_sub = "No errors found. See warning details below."
    else:
        banner_color = "#1e8449"
        banner_bg = "#eafaf1"
        banner_icon = "&#x2714;"
        banner_title = "NO ISSUES DETECTED"
        banner_sub = "All checks passed with no errors or warnings."

    subjects = _collect_subjects(
        conversion_successes, conversion_failures, qc_findings, motion_results
    )

    now = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    parts = [
        _html_head(banner_color),
        "<body>",
        _section_header(now, output_folder),
        _banner(banner_color, banner_bg, banner_icon, banner_title, banner_sub),
        _section_summary_table(subjects, qc_findings, motion_results),
    ]

    if errors or warnings:
        parts.append(_section_bids_findings(errors, warnings))

    if motion_results:
        parts.append(_section_motion(motion_results))

    if conversion_failures:
        parts.append(_section_pipeline_failures(conversion_failures))

    parts.append(_html_footer())
    parts.append("</body></html>")

    return "\n".join(parts)


def _collect_subjects(successes, failures, qc_findings, motion_results):
    """Build a unified list of subject/session keys seen in any source."""
    seen = {}
    for item in successes:
        key = (item["sub_id"], item["ses_id"])
        seen[key] = {"status": "converted"}
    for item in failures:
        key = (item["sub_id"], item["ses_id"])
        seen[key] = {"status": "failed", "error": item.get("error", "")}
    for f in qc_findings:
        key = (f.sub_id, f.ses_id)
        if key not in seen:
            seen[key] = {"status": "converted"}
    for m in motion_results:
        key = (m.sub_id, m.ses_id)
        if key not in seen:
            seen[key] = {"status": "converted"}
    return seen


# ---------------------------------------------------------------------------
# HTML blocks
# ---------------------------------------------------------------------------

def _html_head(accent_color: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>fMRI Pipeline QC Report</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #f5f6fa; color: #2c3e50; font-size: 15px; line-height: 1.6; }}
  .container {{ max-width: 960px; margin: 0 auto; padding: 24px 20px 60px; }}
  h2 {{ font-size: 1.15rem; font-weight: 700; color: #2c3e50;
        margin: 32px 0 12px; border-left: 4px solid {accent_color};
        padding-left: 10px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px;
           background: #fff; border-radius: 8px; overflow: hidden;
           box-shadow: 0 1px 4px rgba(0,0,0,.08); margin-bottom: 24px; }}
  th {{ background: #f0f2f5; text-align: left; padding: 10px 14px;
        font-weight: 600; color: #555; }}
  td {{ padding: 9px 14px; border-top: 1px solid #eee; vertical-align: top; }}
  tr:hover td {{ background: #fafafa; }}
  .badge {{ display: inline-block; padding: 2px 9px; border-radius: 12px;
             font-size: 12px; font-weight: 700; white-space: nowrap; }}
  .badge-error   {{ background: #fdecea; color: #c0392b; }}
  .badge-warning {{ background: #fef3cd; color: #856404; }}
  .badge-ok      {{ background: #d4edda; color: #155724; }}
  .badge-rescan  {{ background: #fdecea; color: #c0392b; }}
  .badge-failed  {{ background: #fdecea; color: #c0392b; }}
  .action-box {{ background: #fff8e1; border-left: 3px solid #f39c12;
                  padding: 6px 10px; border-radius: 4px; margin-top: 4px;
                  font-size: 13px; color: #7d6608; }}
  .plain-msg {{ color: #444; }}
  .meta {{ color: #888; font-size: 12px; }}
  .sep {{ border: none; border-top: 1px solid #e8eaed; margin: 28px 0; }}
</style>
</head>"""


def _section_header(now: str, output_folder: str) -> str:
    return f"""<div class="container">
<div style="margin-bottom:24px;">
  <div style="font-size:1.5rem;font-weight:800;color:#2c3e50;">fMRI Pipeline QC Report</div>
  <div class="meta">Generated: {now} &nbsp;|&nbsp; Output: {output_folder}</div>
</div>"""


def _banner(color, bg, icon, title, subtitle) -> str:
    return f"""<div style="background:{bg};border:2px solid {color};border-radius:10px;
padding:18px 22px;margin-bottom:28px;display:flex;align-items:flex-start;gap:14px;">
  <div style="font-size:2rem;color:{color};line-height:1;">{icon}</div>
  <div>
    <div style="font-size:1.1rem;font-weight:700;color:{color};">{title}</div>
    <div style="color:#555;margin-top:3px;">{subtitle}</div>
  </div>
</div>"""


def _section_summary_table(subjects, qc_findings, motion_results) -> str:
    findings_by_sub = {}
    for f in qc_findings:
        findings_by_sub.setdefault((f.sub_id, f.ses_id), []).append(f)

    motion_by_sub = {}
    for m in motion_results:
        motion_by_sub.setdefault((m.sub_id, m.ses_id), []).append(m)

    rows = []
    for (sub_id, ses_id), info in sorted(subjects.items()):
        conv_badge = (
            '<span class="badge badge-ok">Converted</span>'
            if info["status"] == "converted"
            else '<span class="badge badge-failed">Failed</span>'
        )

        sub_findings = findings_by_sub.get((sub_id, ses_id), [])
        if any(f.severity.value == "ERROR" for f in sub_findings):
            qc_badge = '<span class="badge badge-error">Issues found</span>'
        elif any(f.severity.value == "WARNING" for f in sub_findings):
            qc_badge = '<span class="badge badge-warning">Warnings</span>'
        else:
            qc_badge = '<span class="badge badge-ok">OK</span>'

        sub_motion = motion_by_sub.get((sub_id, ses_id), [])
        if any(m.flag == "RESCAN" for m in sub_motion):
            motion_badge = '<span class="badge badge-rescan">High motion</span>'
        elif any(m.flag == "WARNING" for m in sub_motion):
            motion_badge = '<span class="badge badge-warning">Elevated motion</span>'
        elif sub_motion:
            motion_badge = '<span class="badge badge-ok">OK</span>'
        else:
            motion_badge = '<span class="meta">—</span>'

        rows.append(
            f"<tr><td><b>sub-{sub_id}</b></td><td>ses-{ses_id}</td>"
            f"<td>{conv_badge}</td><td>{qc_badge}</td><td>{motion_badge}</td></tr>"
        )

    rows_html = "\n".join(rows) if rows else "<tr><td colspan='5'>No subjects found.</td></tr>"

    return f"""<h2>Subject Overview</h2>
<table>
  <thead><tr>
    <th>Subject</th><th>Session</th>
    <th>Conversion</th><th>Scan QC</th><th>Motion</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>"""


def _section_bids_findings(errors, warnings) -> str:
    all_findings = errors + warnings
    rows = []
    for f in sorted(all_findings, key=lambda x: (x.sub_id, x.ses_id)):
        sev_class = "badge-error" if f.severity.value == "ERROR" else "badge-warning"
        badge = f'<span class="badge {sev_class}">{f.severity.value}</span>'
        rows.append(
            f"<tr>"
            f"<td><b>sub-{f.sub_id}</b><br><span class='meta'>ses-{f.ses_id}</span></td>"
            f"<td>{badge}</td>"
            f"<td><span class='meta'>{f.category.replace('_', ' ').title()}</span></td>"
            f"<td><span class='plain-msg'>{f.plain_message}</span></td>"
            f"</tr>"
        )
    rows_html = "\n".join(rows)

    return f"""<hr class="sep">
<h2>Scan Quality Findings</h2>
<table>
  <thead><tr>
    <th>Subject</th><th>Severity</th><th>Category</th><th>Details</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>"""


def _section_motion(motion_results) -> str:
    rows = []
    for m in sorted(motion_results, key=lambda x: (x.sub_id, x.ses_id)):
        if m.flag == "RESCAN":
            badge = '<span class="badge badge-rescan">RE-SCAN</span>'
        elif m.flag == "WARNING":
            badge = '<span class="badge badge-warning">WARNING</span>'
        else:
            badge = '<span class="badge badge-ok">OK</span>'

        fd_bar = _fd_bar(m.pct_high_motion)
        rows.append(
            f"<tr>"
            f"<td><b>sub-{m.sub_id}</b><br><span class='meta'>ses-{m.ses_id}</span></td>"
            f"<td><span class='meta'>{m.run_label}</span></td>"
            f"<td>{badge}</td>"
            f"<td style='text-align:center'>{m.mean_fd:.2f} mm</td>"
            f"<td>{fd_bar}<br><span class='meta'>{m.pct_high_motion:.0f}% "
            f"({m.n_high_motion}/{m.n_frames} frames)</span></td>"
            f"<td><span class='plain-msg'>{m.plain_message}</span></td>"
            f"</tr>"
        )
    rows_html = "\n".join(rows)

    return f"""<hr class="sep">
<h2>Motion Analysis (fMRIPrep Confounds)</h2>
<p style="color:#555;font-size:13px;margin-bottom:12px;">
  FD threshold: {0.5} mm. 
  RESCAN flag: &ge;20% of frames above threshold or mean FD &ge;1.0 mm.
  WARNING flag: &ge;10% of frames above threshold or mean FD &ge;0.5 mm.
</p>
<table>
  <thead><tr>
    <th>Subject</th><th>Run</th><th>Status</th>
    <th>Mean FD</th><th>High-motion frames</th><th>Details</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>"""


def _section_pipeline_failures(failures) -> str:
    rows = []
    for item in sorted(failures, key=lambda x: (x["sub_id"], x["ses_id"])):
        rows.append(
            f"<tr>"
            f"<td><b>sub-{item['sub_id']}</b></td><td>ses-{item['ses_id']}</td>"
            f"<td>{item.get('stage','?')}</td>"
            f"<td><span class='meta'>{item.get('error','')[:200]}</span></td>"
            f"</tr>"
        )
    rows_html = "\n".join(rows)

    return f"""<hr class="sep">
<h2>Pipeline Failures</h2>
<table>
  <thead><tr>
    <th>Subject</th><th>Session</th><th>Stage</th><th>Error</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>"""


def _fd_bar(pct: float) -> str:
    """Render a small inline progress bar for the motion percentage."""
    clamped = min(pct, 100.0)
    color = "#c0392b" if pct >= 20 else ("#e67e22" if pct >= 10 else "#27ae60")
    return (
        f'<div style="background:#eee;border-radius:4px;height:8px;width:120px;display:inline-block;vertical-align:middle;">'
        f'<div style="background:{color};width:{clamped:.0f}%;height:100%;border-radius:4px;"></div>'
        f'</div>'
    )


def _html_footer() -> str:
    return """<hr class="sep">
<div style="text-align:center;color:#aaa;font-size:12px;padding-top:12px;">
  Generated by fMRI Preprocessing Assistant &nbsp;|&nbsp;
  For help, contact your lab's technical support
</div>
</div>"""
