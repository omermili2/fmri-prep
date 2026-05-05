"""
HTML QC Report Generator - Layer 5

Generates a self-contained full_pipeline_report.html file in the output folder.
Designed for non-technical research students — color-coded, scannable,
requires no external CSS or JS libraries (everything inline).

Sections:
  1. Overall status banner (green / yellow / red)
  2. Per-subject summary table
  3. BIDS quality findings (Layer 1)
  4. MRIQC Image Quality Metrics (Layer 2, optional)
  5. Motion analysis results (Layer 3)
  6. Connectivity QC results (optional)
"""

import base64
from datetime import datetime
from pathlib import Path
from typing import List

try:
    from ..qc import motion_parser as _mp
    from ..qc import connectivity_thresholds as _ct
    from ..mriqc import iqm_parser as _iqm
except ImportError:
    from qc import motion_parser as _mp
    from qc import connectivity_thresholds as _ct
    from mriqc import iqm_parser as _iqm


def generate(
    output_folder: str,
    qc_findings,
    motion_results,
    conversion_successes: List[dict],
    conversion_failures: List[dict],
    iqm_results=None,
    mriqc_reports=None,
    connectivity_results=None,
    researcher_comments: str = "",
    coreg_plots=None,
) -> str:
    """
    Write full_pipeline_report.html to output_folder.

    Args:
        output_folder:          Pipeline output directory path
        qc_findings:            List[QCFinding] from BIDSQualityChecker
        motion_results:         List[MotionResult] from motion_parser
        conversion_successes:   Report.successful list (dicts with sub_id/ses_id)
        conversion_failures:    Report.failed list (dicts with sub_id/ses_id/error)
        iqm_results:            List[IQMResult] from iqm_parser (optional)
        mriqc_reports:          Dict from mriqc_runner.collect_mriqc_reports (optional)
        connectivity_results:   List[ConnectivityQCResult] from connectivity_qc (optional)
        researcher_comments:    Free-text notes from the researcher (optional)
        coreg_plots:            Dict mapping run keys to SVG file paths (optional)

    Returns:
        Path to the generated HTML file as a string.
    """
    html = _build_html(
        output_folder, qc_findings, motion_results,
        conversion_successes, conversion_failures,
        iqm_results or [], mriqc_reports or {},
        connectivity_results or [],
        researcher_comments=researcher_comments,
        coreg_plots=coreg_plots or {},
    )
    out_path = Path(output_folder) / "full_pipeline_report.html"
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception:
        pass
    return str(out_path)


def generate_mriqc_report(mriqc_dir: str, iqm_results, mriqc_reports,
                          qc_findings=None, output_folder: str = None,
                          researcher_comments: str = "") -> str:
    """
    Write a standalone MRIQC-only HTML report.

    Designed for early feedback — the supervisor can open this as soon as
    MRIQC finishes, without waiting for the full pipeline to complete.
    Includes BIDS scan quality findings (if available) so the researcher
    gets maximum information at the earliest stage.

    Args:
        mriqc_dir:              Path to MRIQC derivatives directory.
        iqm_results:            List of IQMResult from iqm_parser.
        mriqc_reports:          Dict from mriqc_runner.collect_mriqc_reports.
        qc_findings:            List of QCFinding from BIDSQualityChecker (optional).
        output_folder:          Top-level output directory for the report file.
                                If None, falls back to mriqc_dir.
        researcher_comments:    Free-text notes from the researcher (optional).
    """
    iqm_results = iqm_results or []
    mriqc_reports = mriqc_reports or {}
    qc_findings = qc_findings or []

    bids_errors = [f for f in qc_findings if f.severity.value == "ERROR"]
    bids_warnings = [f for f in qc_findings if f.severity.value == "WARNING"]

    iqm_errors = [r for r in iqm_results if r.worst_severity == "ERROR"]
    iqm_warns  = [r for r in iqm_results if r.worst_severity == "WARNING"]

    n_critical = len(iqm_errors) + len(bids_errors)
    n_warnings = len(iqm_warns) + len(bids_warnings)

    if n_critical > 0:
        accent_color = "#c0392b"
    elif n_warnings > 0:
        accent_color = "#d68910"
    else:
        accent_color = "#1e8449"

    now = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    parts = [
        _html_head(accent_color, title="MRIQC - Image Quality Report"),
        "<body>",
        _section_header_mriqc(now, mriqc_dir),
    ]

    if bids_errors or bids_warnings:
        parts.append(_section_bids_findings(bids_errors, bids_warnings))

    parts.extend([
        _section_mriqc(iqm_results, mriqc_reports),
        _section_researcher_comments(researcher_comments),
        _html_footer(),
        "</body></html>",
    ])

    html = "\n".join(parts)
    report_dir = output_folder if output_folder else mriqc_dir
    out_path = Path(report_dir) / "mriqc_report.html"
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception:
        pass
    return str(out_path)


def _section_header_mriqc(now: str, mriqc_dir: str) -> str:
    return f"""<div class="container">
<div style="margin-bottom:24px;">
  <div style="font-size:1.5rem;font-weight:800;color:#2c3e50;">
    MRIQC - Image Quality Report
  </div>
  <div class="meta">Generated: {now} &nbsp;|&nbsp; MRIQC output: {mriqc_dir}</div>
  <div class="meta" style="margin-top:4px;">
    This report was generated immediately after MRIQC completed, before fMRIPrep.
    A comprehensive QC report will be available after the full pipeline finishes.
  </div>
</div>"""


# ---------------------------------------------------------------------------
# HTML construction
# ---------------------------------------------------------------------------

def _build_html(output_folder, qc_findings, motion_results,
                conversion_successes, conversion_failures,
                iqm_results=None, mriqc_reports=None,
                connectivity_results=None,
                researcher_comments: str = "",
                coreg_plots=None) -> str:
    iqm_results = iqm_results or []
    mriqc_reports = mriqc_reports or {}
    connectivity_results = connectivity_results or []
    coreg_plots = coreg_plots or {}

    errors = [f for f in qc_findings if f.severity.value == "ERROR"]
    warnings = [f for f in qc_findings if f.severity.value == "WARNING"]
    rescans = [m for m in motion_results if m.flag == "RESCAN"]
    motion_warns = [m for m in motion_results if m.flag == "WARNING"]
    iqm_errors = [r for r in iqm_results if r.worst_severity == "ERROR"]
    iqm_warns  = [r for r in iqm_results if r.worst_severity == "WARNING"]
    conn_errors = [c for c in connectivity_results if c.worst_severity == "ERROR"]
    conn_warns = [c for c in connectivity_results if c.worst_severity == "WARNING"]

    n_critical = len(errors) + len(rescans) + len(iqm_errors) + len(conn_errors)
    n_warnings = len(warnings) + len(motion_warns) + len(iqm_warns) + len(conn_warns)

    if n_critical > 0:
        accent_color = "#c0392b"
    elif n_warnings > 0:
        accent_color = "#d68910"
    else:
        accent_color = "#1e8449"

    subjects = _collect_subjects(
        conversion_successes, conversion_failures, qc_findings, motion_results,
        connectivity_results,
    )

    now = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    parts = [
        _html_head(accent_color),
        "<body>",
        _section_header(now, output_folder),
        _section_summary_table(subjects, qc_findings, motion_results, iqm_results,
                                connectivity_results),
    ]

    if errors or warnings:
        parts.append(_section_bids_findings(errors, warnings))

    if iqm_results or mriqc_reports:
        parts.append(_section_mriqc(iqm_results, mriqc_reports))

    if motion_results:
        parts.append(_section_motion(motion_results))

    if coreg_plots:
        parts.append(_section_fmriprep_registration(coreg_plots))

    if connectivity_results:
        parts.append(_section_connectivity_qc(connectivity_results))

    if conversion_failures:
        parts.append(_section_pipeline_failures(conversion_failures))

    parts.append(_section_researcher_comments(researcher_comments))

    parts.append(_html_footer())
    parts.append("</body></html>")

    return "\n".join(parts)


def _collect_subjects(successes, failures, qc_findings, motion_results,
                      connectivity_results=None):
    """Build a unified list of subject/session keys seen in any source."""
    connectivity_results = connectivity_results or []

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
    for c in connectivity_results:
        key = (c.sub_id, c.ses_id)
        if key not in seen:
            seen[key] = {"status": "converted"}
    return seen


# ---------------------------------------------------------------------------
# HTML blocks
# ---------------------------------------------------------------------------

def _html_head(accent_color: str, title: str = "fMRI-Prep Full Pipeline Report") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
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
  th {{ background: #f0f2f5; text-align: center; padding: 10px 14px;
        font-weight: 600; color: #555; }}
  td {{ padding: 9px 14px; border-top: 1px solid #eee; vertical-align: middle;
       text-align: center; }}
  td:first-child, th:first-child {{ text-align: left; }}
  .details-left {{ text-align: left; }}
  tr:hover td {{ background: #fafafa; }}
  .badge {{ display: inline-block; padding: 2px 9px; border-radius: 12px;
             font-size: 12px; font-weight: 700; white-space: nowrap; }}
  .badge-error   {{ background: #fdecea; color: #c0392b; }}
  .badge-warning {{ background: #fef3cd; color: #856404; }}
  .badge-ok      {{ background: #d4edda; color: #155724; }}
  .badge-rescan  {{ background: #fdecea; color: #c0392b; }}
  .badge-failed  {{ background: #fdecea; color: #c0392b; }}
  .badge-check {{ background: #d4edda; color: #155724; display: inline-block;
                   padding: 2px 9px; border-radius: 12px; font-size: 14px;
                   font-weight: 700; white-space: nowrap; }}
  .th-hint {{ font-size: 10px; font-weight: 400; color: #999; letter-spacing: .01em; }}
  .plain-msg {{ color: #444; }}
  .meta {{ color: #888; font-size: 12px; }}
  .sep {{ border: none; border-top: 1px solid #e8eaed; margin: 28px 0; }}
  .section-explainer {{ background: #f8f9fa; border-left: 3px solid #b0bec5;
                          padding: 10px 14px; border-radius: 4px; margin-bottom: 16px;
                          font-size: 13px; color: #555; line-height: 1.65; }}
  /* Collapsible heatmaps toggle */
  .heatmap-toggle {{ background: none; border: 1px solid #b0bec5; border-radius: 6px;
                      padding: 6px 14px; font-size: 13px; font-weight: 600;
                      color: #555; cursor: pointer; margin: 12px 0 8px; }}
  .heatmap-toggle:hover {{ background: #f0f2f5; }}
  .heatmap-content {{ overflow: hidden; transition: max-height 0.3s ease; }}
  .heatmap-content.collapsed {{ max-height: 0; }}
  .metric-ok    {{ font-weight: 700; color: #155724; }}
  .metric-warn  {{ font-weight: 700; color: #856404; }}
  .metric-error {{ font-weight: 700; color: #c0392b; }}
  .metric-unknown {{ color: #888; }}
  .metric-bubble {{ display: inline-block; padding: 2px 9px; border-radius: 12px;
                    font-size: 12px; font-weight: 700; white-space: nowrap; }}
  /* Carpet plot styling */
  .carpet-row td {{ padding: 0; background: #fafbfc; }}
  .carpet-container {{ padding: 10px 16px 14px; }}
  .carpet-header {{
    font-size: 12px; font-weight: 600; color: #666;
    margin-bottom: 6px; display: flex; align-items: center; gap: 6px;
  }}
  .carpet-header .carpet-icon {{
    display: inline-block; width: 14px; height: 14px;
    background: linear-gradient(180deg, #3498db 0%, #2c3e50 30%, #95a5a6 60%, #ecf0f1 100%);
    border-radius: 2px; flex-shrink: 0;
  }}
  .carpet-img {{ width: 100%; border: 1px solid #e0e0e0; border-radius: 6px; background: #fff; }}
  .coreg-svg-container {{ width: 100%; border: 1px solid #e0e0e0; border-radius: 6px; background: #fff; overflow: hidden; }}
  .coreg-svg-container svg {{ width: 100%; height: auto; display: block; }}
  .carpet-caption {{ font-size: 11px; color: #999; margin-top: 4px; line-height: 1.5; }}
  details.carpet-details {{ margin: 0; }}
  details.carpet-details summary {{
    cursor: pointer; font-size: 12px; color: #5c6bc0;
    font-weight: 600; padding: 6px 16px; user-select: none; list-style: none;
  }}
  details.carpet-details summary::-webkit-details-marker {{ display: none; }}
  details.carpet-details summary::before {{
    content: "\\25B6\\FE0E"; display: inline-block; margin-right: 6px;
    font-size: 10px; transition: transform 0.15s;
  }}
  details.carpet-details[open] summary::before {{ transform: rotate(90deg); }}
</style>
</head>"""


def _section_header(now: str, output_folder: str) -> str:
    return f"""<div class="container">
<div style="margin-bottom:24px;">
  <div style="font-size:1.5rem;font-weight:800;color:#2c3e50;">fMRI-Prep Full Pipeline Report</div>
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


def _section_summary_table(subjects, qc_findings, motion_results, iqm_results=None,
                            connectivity_results=None) -> str:
    findings_by_sub = {}
    for f in qc_findings:
        findings_by_sub.setdefault((f.sub_id, f.ses_id), []).append(f)

    motion_by_sub = {}
    for m in motion_results:
        motion_by_sub.setdefault((m.sub_id, m.ses_id), []).append(m)

    iqm_by_sub = {}
    for r in (iqm_results or []):
        iqm_by_sub.setdefault((r.sub_id, r.ses_id), []).append(r)

    connectivity_by_sub = {}
    for c in (connectivity_results or []):
        connectivity_by_sub.setdefault((c.sub_id, c.ses_id), []).append(c)

    has_connectivity = bool(connectivity_results)

    _check = '<span class="badge-check">&#10003;</span>'

    rows = []
    for (sub_id, ses_id), info in sorted(subjects.items()):
        sub_findings = findings_by_sub.get((sub_id, ses_id), [])
        if info["status"] != "converted":
            qc_badge = '<span class="badge badge-failed">Failed</span>'
        elif any(f.severity.value == "ERROR" for f in sub_findings):
            qc_badge = '<span class="badge badge-error">Error</span>'
        elif any(f.severity.value == "WARNING" for f in sub_findings):
            qc_badge = '<span class="badge badge-warning">Warning</span>'
        else:
            qc_badge = _check

        sub_iqm = iqm_by_sub.get((sub_id, ses_id), [])
        if any(r.worst_severity == "ERROR" for r in sub_iqm):
            iqm_badge = '<span class="badge badge-error">Error</span>'
        elif any(r.worst_severity == "WARNING" for r in sub_iqm):
            iqm_badge = '<span class="badge badge-warning">Warning</span>'
        else:
            iqm_badge = _check

        sub_motion = motion_by_sub.get((sub_id, ses_id), [])
        if any(m.flag == "RESCAN" for m in sub_motion):
            motion_badge = '<span class="badge badge-rescan">Error</span>'
        elif any(m.flag == "WARNING" for m in sub_motion):
            motion_badge = '<span class="badge badge-warning">Warning</span>'
        elif sub_motion:
            motion_badge = _check
        else:
            motion_badge = '<span class="meta">-</span>'

        conn_badge = '<span class="meta">-</span>'
        if has_connectivity:
            sub_conn = connectivity_by_sub.get((sub_id, ses_id), [])
            error_conn = any(c.worst_severity == "ERROR" for c in sub_conn)
            warn_conn = any(c.worst_severity == "WARNING" for c in sub_conn)

            if error_conn:
                conn_badge = '<span class="badge badge-error">Error</span>'
            elif warn_conn:
                conn_badge = '<span class="badge badge-warning">Warning</span>'
            elif sub_conn:
                conn_badge = _check

        row_content = (
            f"<tr><td><b>sub-{sub_id}</b><br><span class='meta'>ses-{ses_id}</span></td>"
            f"<td>{qc_badge}</td>"
            f"<td>{iqm_badge}</td><td>{motion_badge}</td>"
        )

        if has_connectivity:
            row_content += f"<td>{conn_badge}</td>"

        row_content += "</tr>"
        rows.append(row_content)

    colspan = 5 if has_connectivity else 4
    rows_html = "\n".join(rows) if rows else f"<tr><td colspan='{colspan}'>No subjects found.</td></tr>"

    conn_header = "<th>Connectivity</th>" if has_connectivity else ""

    return f"""<h2>Overview</h2>
<table>
  <thead><tr>
    <th>Run</th>
    <th>Scan Quality</th><th>MRIQC</th><th>Motion Analysis</th>{conn_header}
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>"""


def _section_bids_findings(errors, warnings) -> str:
    all_findings = errors + warnings
    rows = []
    for f in sorted(all_findings, key=lambda x: (x.sub_id, x.ses_id)):
        sev_class = "badge-error" if f.severity.value == "ERROR" else "badge-warning"
        sev_label = "Error" if f.severity.value == "ERROR" else "Warning"
        badge = f'<span class="badge {sev_class}">{sev_label}</span>'
        rows.append(
            f"<tr>"
            f"<td><b>sub-{f.sub_id}</b><br><span class='meta'>ses-{f.ses_id}</span></td>"
            f"<td>{badge}</td>"
            f"<td><span class='meta'>{f.category.replace('_', ' ').title()}</span></td>"
            f"<td class='details-left'><span class='plain-msg'>{f.plain_message}</span></td>"
            f"</tr>"
        )
    rows_html = "\n".join(rows)

    return f"""<hr class="sep">
<h2>Scan Quality</h2>
<div class="section-explainer">
  Checks performed immediately after DICOM-to-BIDS conversion, before any preprocessing.
  They verify that the expected scan types are present (T1w anatomical, BOLD functional),
  that files are not suspiciously small or truncated, and that key acquisition parameters
  (TR, field strength) are consistent across subjects.
  Issues flagged here may indicate an aborted scan, a missing sequence, or a protocol change
  mid-study.
</div>
<table>
  <thead><tr>
    <th>Run</th><th>Status</th><th>Category</th><th>Details</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>"""


def _section_motion(motion_results) -> str:
    _check = '<span class="badge-check">&#10003;</span>'
    rows = []
    for m in sorted(motion_results, key=lambda x: (x.sub_id, x.ses_id)):
        if m.flag == "RESCAN":
            badge = '<span class="badge badge-rescan">Error</span>'
        elif m.flag == "WARNING":
            badge = '<span class="badge badge-warning">Warning</span>'
        else:
            badge = _check

        fd_bar = _fd_bar(m.pct_high_motion)
        rows.append(
            f"<tr>"
            f"<td><b>sub-{m.sub_id}</b><br>"
            f"<span class='meta'>ses-{m.ses_id}</span><br>"
            f"<span class='meta'>{m.run_label}</span></td>"
            f"<td>{badge}</td>"
            f"<td>{m.mean_fd:.2f} mm</td>"
            f"<td>{fd_bar}<br><span class='meta'>{m.pct_high_motion:.0f}% "
            f"({m.n_high_motion}/{m.n_frames} frames)</span></td>"
            f"</tr>"
        )
    rows_html = "\n".join(rows)

    fd_thr = _mp.FD_THRESHOLD
    warn_fd = _mp.WARN_MEAN_FD
    rescan_fd = _mp.RESCAN_MEAN_FD
    warn_pct = _mp.WARN_MOTION_PERCENT
    rescan_pct = _mp.RESCAN_MOTION_PERCENT

    return f"""<hr class="sep">
<h2>Motion Analysis</h2>
<div class="section-explainer">
  After preprocessing, <a href="https://fmriprep.org/" target="_blank"
  style="color:#5c6bc0;">fMRIPrep</a> outputs a confounds time-series file for every
  BOLD run. This section reads the <b>framewise displacement (FD)</b> column from those
  files to quantify head motion.
  <br><br>
  <b>Framewise displacement</b> (Power et al., 2012) summarizes volume-to-volume head
  movement by combining translational and rotational displacement into a single number
  (in mm). A frame with FD &gt; {fd_thr}&nbsp;mm is considered a <i>high-motion frame</i>.
  Runs with many high-motion frames yield unreliable activation maps and inflated
  functional-connectivity estimates.
  <br><br>
  <b>Thresholds used here:</b>&ensp;
  Error: &ge;{rescan_pct:g}% high-motion frames <i>or</i> mean&nbsp;FD &ge; {rescan_fd}&nbsp;mm &nbsp;|&nbsp;
  Warning: &ge;{warn_pct:g}% high-motion frames <i>or</i> mean&nbsp;FD &ge; {warn_fd}&nbsp;mm.
</div>
<table>
  <thead><tr>
    <th>Run</th><th>Status</th>
    <th>Mean FD<br><span class="th-hint">&#9888; &ge;{warn_fd}mm &nbsp; &#10007; &ge;{rescan_fd}mm</span></th><th>High-motion frames<br><span class="th-hint">FD &gt;{fd_thr}mm &nbsp;|&nbsp; &#9888; &ge;{warn_pct:g}% &nbsp; &#10007; &ge;{rescan_pct:g}%</span></th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>"""


def _section_fmriprep_registration(coreg_plots) -> str:
    """Generate the fMRIPrep coregistration quality section with per-run SVG overlays."""
    import re

    if not coreg_plots:
        return ""

    # Group coreg plots by (sub_id, ses_id)
    grouped = {}
    for key, svg_path in sorted(coreg_plots.items()):
        # Key format: sub-010_ses-02_task-rest_run-01
        sub_match = re.search(r"sub-([^_]+)", key)
        ses_match = re.search(r"ses-([^_]+)", key)
        sub_id = sub_match.group(1) if sub_match else "unknown"
        ses_id = ses_match.group(1) if ses_match else "unknown"
        # Build a readable run label from the remaining BIDS entities
        run_label = key
        for prefix in [f"sub-{sub_id}_", f"ses-{ses_id}_"]:
            run_label = run_label.replace(prefix, "")
        grouped.setdefault((sub_id, ses_id), []).append((run_label, svg_path))

    # Build collapsible blocks per subject/session
    blocks = []
    for (sub_id, ses_id), runs in sorted(grouped.items()):
        run_items = []
        for run_label, svg_path in runs:
            svg_file = Path(svg_path)
            if not svg_file.is_file():
                continue
            try:
                svg_content = svg_file.read_text(encoding="utf-8", errors="replace")
                run_items.append(
                    f'<div style="margin-bottom:12px;">'
                    f'<div class="carpet-header">'
                    f'<span style="display:inline-block;width:14px;height:14px;'
                    f'background:linear-gradient(135deg,#e74c3c 0%,#95a5a6 50%,#ecf0f1 100%);'
                    f'border-radius:2px;flex-shrink:0;"></span> {run_label}'
                    f'</div>'
                    f'<div class="coreg-svg-container">'
                    f'{svg_content}'
                    f'</div>'
                    f'</div>'
                )
            except Exception:
                pass

        if not run_items:
            continue

        label = f"sub-{sub_id}/ses-{ses_id}"
        n_runs = len(run_items)
        runs_html = "\n".join(run_items)
        blocks.append(
            f'<details class="carpet-details">'
            f'<summary>{label} -{n_runs} run{"s" if n_runs != 1 else ""}</summary>'
            f'<div class="carpet-container">'
            f'{runs_html}'
            f'<div class="carpet-caption">'
            f'The BOLD reference image (warm/red tones) is overlaid on the T1-weighted '
            f'anatomical scan (grayscale). Cortical boundaries in the BOLD should align '
            f'with the T1w edges. Misalignment (shifted, rotated, or distorted outlines) '
            f'indicates a registration failure.'
            f'</div></div></details>'
        )

    if not blocks:
        return ""

    blocks_html = "\n".join(blocks)

    return f"""<hr class="sep">
<h2>fMRIPrep Registration Quality</h2>
<div class="section-explainer">
  After preprocessing, <a href="https://fmriprep.org/" target="_blank"
  style="color:#5c6bc0;">fMRIPrep</a> aligns each BOLD run's reference volume
  to the subject's T1-weighted anatomical scan (<b>coregistration</b>).
  This is a critical step -if the functional and anatomical images are
  misaligned, all downstream analyses (activation maps, connectivity, etc.)
  will be unreliable.
  <br><br>
  Each overlay below shows the BOLD reference superimposed on the T1w.
  <b>What to check:</b> the cortical surface outline from the BOLD should
  closely follow the gray/white matter boundaries visible in the T1w.
  If you see a clear shift, rotation, or distortion between the two, that
  run's coregistration failed and the data should be reviewed.
  <br><br>
  <b>Note:</b> fMRIPrep also generates additional diagnostic figures
  (confound correlation matrices, component-variance plots, tissue
  segmentation overlays). These are available in fMRIPrep's own per-subject
  HTML reports under <code>derivatives/sub-*/figures/</code> but are not
  included here because they address preprocessing strategy decisions rather
  than the scan-quality question this report targets.
</div>
{blocks_html}"""


def _section_pipeline_failures(failures) -> str:
    rows = []
    for item in sorted(failures, key=lambda x: (x["sub_id"], x["ses_id"])):
        rows.append(
            f"<tr>"
            f"<td><b>sub-{item['sub_id']}</b><br><span class='meta'>ses-{item['ses_id']}</span></td>"
            f"<td>{item.get('stage','?')}</td>"
            f"<td><span class='meta'>{item.get('error','')[:200]}</span></td>"
            f"</tr>"
        )
    rows_html = "\n".join(rows)

    return f"""<hr class="sep">
<h2>Pipeline Failures</h2>
<div class="section-explainer">
  Sessions listed here could not be fully processed. The <b>Stage</b> column indicates
  where the failure occurred (BIDS conversion or fMRIPrep preprocessing) and the
  <b>Error</b> column shows the reason. Common causes include missing scan types,
  Docker container issues, or insufficient disk space.
</div>
<table>
  <thead><tr>
    <th>Run</th><th>Stage</th><th>Error</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>"""


def _section_mriqc(iqm_results, mriqc_reports) -> str:
    try:
        from mriqc.iqm_parser import METRIC_DISPLAY
    except ImportError:
        from ..mriqc.iqm_parser import METRIC_DISPLAY

    _check = '<span class="badge-check">&#10003;</span>'

    carpet_plots = mriqc_reports.get("carpet_plots", {})

    rows = []
    sorted_results = sorted(
        iqm_results,
        key=lambda x: (x.sub_id, x.ses_id, 0 if x.modality == "T1w" else 1, x.scan_file),
    )
    for r in sorted_results:
        sev = r.worst_severity
        if sev == "ERROR":
            badge = '<span class="badge badge-error">Error</span>'
        elif sev == "WARNING":
            badge = '<span class="badge badge-warning">Warning</span>'
        else:
            badge = _check

        # --- Metrics column: colored bubbles, one per line ---
        flag_sev = {fl.metric: fl.severity for fl in r.flags}
        metric_lines = []
        for k, v in r.metrics.items():
            display_name = METRIC_DISPLAY.get(k, k)
            severity = flag_sev.get(k, "OK")
            css = {"OK": "badge-ok", "WARNING": "badge-warning",
                   "ERROR": "badge-error"}.get(severity, "badge-ok")
            metric_lines.append(
                f'<span class="metric-bubble {css}">{display_name}: {v:.2f}</span>'
            )
        metrics_html = "<br>".join(metric_lines)

        # --- Run column: subject bold, session meta, scan label meta ---
        scan_label = r.scan_label if hasattr(r, 'scan_label') else r.modality
        ses_part = f"<br><span class='meta'>ses-{r.ses_id}</span>" if r.ses_id else ""
        rows.append(
            f"<tr>"
            f"<td><b>sub-{r.sub_id}</b>{ses_part}<br>"
            f"<span class='meta'>{scan_label}</span></td>"
            f"<td>{badge}</td>"
            f"<td>{metrics_html}</td>"
            f"</tr>"
        )

        # --- Carpet plot row (BOLD runs only) ---
        carpet_key = Path(r.scan_file).stem
        carpet_path = carpet_plots.get(carpet_key)
        if carpet_path and Path(carpet_path).is_file():
            try:
                svg_data = Path(carpet_path).read_bytes()
                b64 = base64.b64encode(svg_data).decode("ascii")
                rows.append(
                    f'<tr class="carpet-row"><td colspan="3">'
                    f'<details class="carpet-details">'
                    f'<summary>Carpet plot -{scan_label}</summary>'
                    f'<div class="carpet-container">'
                    f'<div class="carpet-header">'
                    f'<span class="carpet-icon"></span> Carpet plot'
                    f'</div>'
                    f'<img class="carpet-img" '
                    f'src="data:image/svg+xml;base64,{b64}" '
                    f'alt="Carpet plot for {carpet_key}">'
                    f'<div class="carpet-caption">'
                    f'Each row is one brain voxel; each column is one time-point (TR). '
                    f'Vertical stripes indicate signal changes affecting many voxels '
                    f'simultaneously (often head motion). The traces above the carpet '
                    f'show framewise displacement and DVARS.'
                    f'</div></div></details></td></tr>'
                )
            except Exception:
                pass  # Graceful fallback — skip if SVG cannot be read

    rows_html = "\n".join(rows)

    if rows_html:
        table_html = f"""<table>
  <thead><tr>
    <th>Run</th><th>Status</th><th>Metrics</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>"""
    else:
        table_html = (
            '<div class="section-explainer" style="color:#999;font-style:italic;">'
            'MRIQC ran but no IQM metrics were parsed. '
            'Check the MRIQC logs and derivatives/mriqc/ folder for details.</div>'
        )

    return f"""<hr class="sep">
<h2>MRIQC - Image Quality Metrics</h2>
<div class="section-explainer">
  <b>Structural (T1w) metrics:</b>
  <ul style="margin:4px 0 8px 18px;">
    <li><b>SNR</b> - signal-to-noise ratio in gray matter; quantifies overall image clarity</li>
    <li><b>CNR</b> - contrast-to-noise ratio; ability to distinguish gray from white matter</li>
    <li><b>CJV</b> - coefficient of joint variation; detects tissue-intensity overlap from motion or B1-field inhomogeneity</li>
    <li><b>INU range</b> - intensity non-uniformity (bias field) severity</li>
    <li><b>QI1</b> - proportion of artifact-contaminated voxels in the air background</li>
  </ul>
  <b>Functional (BOLD) metrics:</b>
  <ul style="margin:4px 0 8px 18px;">
    <li><b>tSNR</b> - temporal signal-to-noise ratio; stability of the BOLD signal over time</li>
    <li><b>FD mean</b> - mean framewise displacement; average head movement per volume</li>
    <li><b>GSR X / Y</b> - ghost-to-signal ratio; detects EPI ghosting artifacts per phase-encode direction</li>
    <li><b>AOR</b> - AFNI outlier ratio; fraction of volumes flagged as outliers</li>
  </ul>
  <b>Carpet plots</b> (BOLD runs only): The carpet plot shows signal intensity across all brain
  voxels (rows) over time (columns). Vertical stripes indicate whole-brain signal shifts - usually
  from head motion or scanner artifacts. The traces above the carpet show framewise displacement
  and DVARS. Click the toggle below each BOLD row to expand.
  <br><br>
  <b>Metric colors:</b>
  <span class="badge badge-ok" style="font-size:11px;">Normal</span>
  <span class="badge badge-warning" style="font-size:11px;">Borderline</span>
  <span class="badge badge-error" style="font-size:11px;">Out of range</span>
  <br><br>
  <b>How metrics are evaluated (two layers):</b>
  <ol style="margin:6px 0 8px 22px;line-height:1.8;">
    <li><b>Primary -within-study comparison (IQR-based).</b>
      Each scan&rsquo;s metrics are compared to all other scans of the same type
      in this dataset using the Interquartile Range (IQR) method.
      A metric that falls <b>&gt;1.5&times;&nbsp;IQR</b> beyond the study&rsquo;s
      &ldquo;worse&rdquo; quartile is flagged as
      <span class="badge badge-warning" style="font-size:10px;">Borderline</span>;
      <b>&gt;3&times;&nbsp;IQR</b> is flagged as
      <span class="badge badge-error" style="font-size:10px;">Out of range</span>.
      This adapts automatically to any acquisition protocol -no manual
      threshold tuning required. Requires &ge;3 scans of the same type.</li>
    <li><b>Safety net -absolute thresholds for extreme values.</b>
      Protocol-independent ERROR thresholds catch values so extreme they indicate
      a definite problem regardless of protocol (e.g.&nbsp;tSNR&nbsp;&lt;&nbsp;{_iqm.THRESHOLDS_BOLD['tsnr'][1]:g},
      mean&nbsp;FD&nbsp;&gt;&nbsp;{_iqm.THRESHOLDS_BOLD['fd_mean'][1]:g}&nbsp;mm).
      When fewer than 3 scans of the same type are available (IQR cannot run),
      moderate absolute thresholds are applied as a WARNING-level fallback.</li>
  </ol>
  {_iqm_threshold_text()}
</div>
{table_html}"""


def _iqm_threshold_text() -> str:
    """Build the IQM threshold summary from the current iqm_parser globals."""
    # Display names for metrics
    _anat_labels = {
        "snr_gm": "SNR", "cnr": "CNR", "cjv": "CJV",
        "inu_range": "INU", "qi_1": "QI1",
    }
    _bold_labels = {
        "tsnr": "tSNR", "fd_mean": "FD", "gsr_x": "GSR",
        "gsr_y": "GSR Y", "aor": "AOR",
    }
    # Metrics with units
    _units = {"fd_mean": "&nbsp;mm"}

    def _fmt(thresholds, labels, level):
        """level: 0 = fallback_warn, 1 = safety_net_error"""
        parts = []
        for metric, label in labels.items():
            if metric not in thresholds:
                continue
            warn, error, direction = thresholds[metric]
            val = error if level == 1 else warn
            op = "&gt;" if direction == "high" else "&lt;"
            unit = _units.get(metric, "")
            parts.append(f"{label}&nbsp;{op}&nbsp;{val:g}{unit}")
        return " &nbsp;|&nbsp;\n  ".join(parts)

    anat = _iqm.THRESHOLDS_ANAT
    bold = _iqm.THRESHOLDS_BOLD

    return (
        '<b>Absolute safety-net thresholds (ERROR -always applied):</b><br>\n'
        f'  <b>T1w:</b>&ensp;\n  {_fmt(anat, _anat_labels, 1)}<br>\n'
        f'  <b>BOLD:</b>&ensp;\n  {_fmt(bold, _bold_labels, 1)}<br>\n'
        '  <b>Fallback WARNING thresholds (used when &lt;3 scans):</b><br>\n'
        f'  <b>T1w:</b>&ensp;\n  {_fmt(anat, _anat_labels, 0)}<br>\n'
        f'  <b>BOLD:</b>&ensp;\n  {_fmt(bold, _bold_labels, 0)}'
    )


def _fd_bar(pct: float, warn_pct: float = None, error_pct: float = None) -> str:
    """Render a small inline progress bar for the motion percentage."""
    if warn_pct is None:
        warn_pct = _mp.WARN_MOTION_PERCENT
    if error_pct is None:
        error_pct = _mp.RESCAN_MOTION_PERCENT
    clamped = min(pct, 100.0)
    color = "#c0392b" if pct >= error_pct else ("#e67e22" if pct >= warn_pct else "#27ae60")
    return (
        f'<div style="background:#eee;border-radius:4px;height:8px;width:120px;display:inline-block;vertical-align:middle;">'
        f'<div style="background:{color};width:{clamped:.0f}%;height:100%;border-radius:4px;"></div>'
        f'</div>'
    )


def _metric_span(value: str, severity: str) -> str:
    """Wrap a metric value in a severity-colored span."""
    css = {"OK": "metric-ok", "WARNING": "metric-warn",
           "ERROR": "metric-error"}.get(severity, "metric-unknown")
    return f'<span class="{css}">{value}</span>'


def _section_connectivity_qc(connectivity_results) -> str:
    """Generate the Nilearn connectivity QC section with distinctive styling."""

    if not connectivity_results:
        return ""

    fd_warn = _ct.CONNECTIVITY_MEAN_FD_WARN
    fd_fail = _ct.CONNECTIVITY_MEAN_FD_FAIL
    cens_warn = _ct.MAX_CENSORED_PCT_WARN
    cens_fail = _ct.MAX_CENSORED_PCT_FAIL
    usable_fail = _ct.MIN_USABLE_MINUTES_FAIL
    dof_warn = _ct.LOSS_DOF_WARN
    dof_warn_pct = dof_warn * 100

    intro = f"""<hr class="sep">
<h2>Functional Connectivity Quality Assessment</h2>
<div class="section-explainer">
  This section evaluates whether each BOLD run has sufficient data quality for
  <b>functional connectivity analysis</b> (e.g., seed-based correlation, network parcellation,
  or graph-theoretic measures).
  Connectivity estimates are especially sensitive to head motion because even small movements
  can introduce spurious short-range correlations and inflate or distort network structure
  (Power et al., 2012; Satterthwaite et al., 2013).
  <br><br>
  The analyses below use Nilearn&rsquo;s
  <a href="https://nilearn.github.io/stable/modules/generated/nilearn.interfaces.fmriprep.load_confounds_strategy.html"
     target="_blank" style="color:#5c6bc0;"><code>load_confounds_strategy</code></a>
  with the <b>&ldquo;scrubbing&rdquo;</b> preset, which automatically selects confound
  regressors and identifies volumes to censor. Time-series extraction and connectivity
  matrices are computed on the <b>scrubbed (cleaned) data only</b>, so the heatmaps below
  reflect denoised connectivity.
  Thresholds follow recommendations from
  <a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC10977879/" target="_blank"
     style="color:#5c6bc0;">Parkes et al.</a>
  <br><br>
  <b>Metrics at a glance:</b><br>
  &#9679; <b>Mean FD</b> -
  Average framewise displacement across all volumes.
  <span class="metric-ok">&lt;{fd_warn}&nbsp;mm</span>,
  <span class="metric-warn">{fd_warn}-{fd_fail}&nbsp;mm</span>,
  <span class="metric-error">&gt;{fd_fail}&nbsp;mm</span>.<br>
  &#9679; <b>Censored Volumes</b> -
  Volumes flagged by the scrubbing strategy and removed before time-series extraction.
  <span class="metric-error">&gt;{cens_fail:g}% censored = not suitable</span>.<br>
  &#9679; <b>Usable Time</b> -
  Clean scan duration remaining after censoring (in minutes).
  <span class="metric-error">&lt;{usable_fail:g}&nbsp;min = not suitable</span>.<br>
  &#9679; <b># Regressors</b> -
  Number of confound columns selected by the scrubbing strategy.<br>
  &#9679; <b>Loss of DoF</b> -
  Total temporal degrees of freedom consumed (regressors + censored volumes).
  High values reduce statistical power and can inflate connectivity estimates.
  <span class="metric-warn">&gt;{dof_warn_pct:g}% = caution</span>.
</div>"""

    sections = [intro]

    # Metrics table
    rows = []
    for c in sorted(connectivity_results, key=lambda x: (x.sub_id, x.ses_id, x.run_label)):
        if c.worst_severity == "OK":
            badge = '<span class="badge-check">&#10003;</span>'
        elif c.worst_severity == "WARNING":
            badge = '<span class="badge badge-warning">Warning</span>'
        elif c.worst_severity == "ERROR":
            badge = '<span class="badge badge-error">Error</span>'
        else:
            badge = '<span class="metric-unknown">UNKNOWN</span>'

        # Mean FD
        fd_cls = ("metric-error" if c.mean_fd > fd_fail
                  else "metric-warn" if c.mean_fd > fd_warn
                  else "metric-ok")

        # Censored volumes
        censor_bar = _fd_bar(c.pct_censored, warn_pct=cens_warn, error_pct=cens_fail)
        pct_cls = ("metric-error" if c.pct_censored > cens_fail
                   else "metric-warn" if c.pct_censored > cens_warn
                   else "metric-ok")

        # DoF loss
        dof_cls = ("metric-warn" if c.loss_of_dof_pct > dof_warn_pct else "metric-ok")

        rows.append(
            f"<tr>"
            f"<td><b>sub-{c.sub_id}</b><br>"
            f"<span class='meta'>ses-{c.ses_id}</span><br>"
            f"<span class='meta'>{c.run_label}</span></td>"
            f"<td>{badge}</td>"
            f"<td><span class='{fd_cls}'>{c.mean_fd:.2f}&nbsp;mm</span></td>"
            f"<td><span class='{pct_cls}'>{c.pct_censored:.0f}%</span> {censor_bar}<br>"
            f"<span class='meta'>({c.censored_volumes}/{c.total_volumes} vols)</span></td>"
            f"<td>{c.usable_minutes:.1f}&nbsp;min</td>"
            f"<td>{c.n_regressors}</td>"
            f"<td><span class='{dof_cls}'>{c.loss_of_dof}</span><br>"
            f"<span class='meta'>({c.loss_of_dof_pct:.0f}% of {c.total_volumes})</span></td>"
            f"</tr>"
        )

    rows_html = "\n".join(rows) if rows else "<tr><td colspan='7'>No results</td></tr>"
    sections.append(f"""<h3>Quality Metrics</h3>
<table>
  <thead><tr>
    <th>Run</th>
    <th>Status</th>
    <th>Mean FD<br><span class="th-hint">&#9888; &ge;{fd_warn}mm &#10007; &ge;{fd_fail}mm</span></th>
    <th>Censored<br><span class="th-hint">&#10007; &gt;{cens_fail:g}%</span></th>
    <th>Usable Time<br><span class="th-hint">&#10007; &lt;{usable_fail:g} min</span></th>
    <th># Regressors</th>
    <th>Loss of DoF<br><span class="th-hint">&#9888; &gt;{dof_warn_pct:g}%</span></th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>""")

    # Connectivity Heatmaps (collapsible)
    heatmap_runs = [c for c in connectivity_results
                    if getattr(c, 'heatmap_base64', None)]
    if heatmap_runs:
        heatmap_parts = [
            '<h3>Connectivity Heatmaps (scrubbed data)</h3>',
            '<button class="heatmap-toggle" onclick="'
            "var c=this.nextElementSibling;"
            "if(c.classList.contains('collapsed')){"
            "c.classList.remove('collapsed');c.style.maxHeight=c.scrollHeight+'px';"
            "this.textContent='Hide heatmaps'}"
            "else{c.classList.add('collapsed');c.style.maxHeight='0';"
            "this.textContent='Show heatmaps'}"
            '">Show heatmaps</button>',
            '<div class="heatmap-content collapsed">',
        ]
        for c in sorted(heatmap_runs, key=lambda x: (x.sub_id, x.ses_id, x.run_label)):
            label = f"sub-{c.sub_id}/ses-{c.ses_id} - {c.run_label}"
            heatmap_parts.append(
                f'<p style="font-weight:700;margin:12px 0 6px;">{label}</p>'
                f'<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px;">'
            )
            if c.heatmap_base64:
                heatmap_parts.append(
                    f'<img src="data:image/png;base64,{c.heatmap_base64}" '
                    f'style="max-width:460px;border:1px solid #ccc;border-radius:6px;" '
                    f'alt="Full connectivity matrix">'
                )
            if getattr(c, 'network_summary_base64', None):
                heatmap_parts.append(
                    f'<img src="data:image/png;base64,{c.network_summary_base64}" '
                    f'style="max-width:380px;border:1px solid #ccc;border-radius:6px;" '
                    f'alt="Network summary">'
                )
            heatmap_parts.append('</div>')
        heatmap_parts.append('</div>')  # close .heatmap-content
        sections.append("\n".join(heatmap_parts))

    return "\n".join(sections)


def _section_researcher_comments(comments: str = "") -> str:
    """Generate the Researcher Comments section for HTML reports."""
    comments = (comments or "").strip()
    if comments:
        # Escape HTML special characters
        safe = (
            comments
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )
        # Convert newlines to <br> for display
        safe = safe.replace("\n", "<br>")
        body_html = safe
    else:
        body_html = (
            '<span style="color:#999;font-style:italic;">'
            'No comments were entered by the researcher.</span>'
        )

    return (
        '<hr class="sep">\n'
        '<h2 style="border-left-color:#5c6bc0;">Researcher Comments</h2>\n'
        '<div dir="auto" style="background:#f8f9fa;border:1px solid #e0e0e0;border-left:4px solid #5c6bc0;'
        'border-radius:6px;padding:16px 20px;margin-bottom:24px;'
        f'font-size:14px;line-height:1.7;color:#333;white-space:pre-wrap;">{body_html}</div>'
    )


def _html_footer() -> str:
    return """<hr class="sep">
<div style="text-align:center;color:#aaa;font-size:12px;padding-top:12px;">
  Generated by fMRI Preprocessing Assistant &nbsp;|&nbsp;
  For help, contact your lab's technical support
</div>
</div>"""
