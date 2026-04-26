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

from datetime import datetime
from pathlib import Path
from typing import List


def generate(
    output_folder: str,
    qc_findings,
    motion_results,
    conversion_successes: List[dict],
    conversion_failures: List[dict],
    iqm_results=None,
    mriqc_reports=None,
    censoring_results=None,
    connectivity_results=None,
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
        censoring_results:      List[CensoringResult] from volume_censoring (optional)
        connectivity_results:   List[ConnectivityQCResult] from connectivity_qc (optional)

    Returns:
        Path to the generated HTML file as a string.
    """
    html = _build_html(
        output_folder, qc_findings, motion_results,
        conversion_successes, conversion_failures,
        iqm_results or [], mriqc_reports or {},
        censoring_results or [], connectivity_results or []
    )
    out_path = Path(output_folder) / "full_pipeline_report.html"
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception:
        pass
    return str(out_path)


def generate_mriqc_report(mriqc_dir: str, iqm_results, mriqc_reports,
                          qc_findings=None, output_folder: str = None) -> str:
    """
    Write a standalone MRIQC-only HTML report.

    Designed for early feedback — the supervisor can open this as soon as
    MRIQC finishes, without waiting for the full pipeline to complete.
    Includes BIDS scan quality findings (if available) so the researcher
    gets maximum information at the earliest stage.

    Args:
        mriqc_dir:      Path to MRIQC derivatives directory.
        iqm_results:    List of IQMResult from iqm_parser.
        mriqc_reports:  Dict from mriqc_runner.collect_mriqc_reports.
        qc_findings:    List of QCFinding from BIDSQualityChecker (optional).
        output_folder:  Top-level output directory for the report file.
                        If None, falls back to mriqc_dir.
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
        banner_color, banner_bg = "#c0392b", "#fdf0ef"
        banner_icon = "&#x26A0;"
        banner_title = f"{n_critical} critical issue(s) detected"
        banner_sub = "One or more scans have metrics outside acceptable ranges. Review details below."
    elif n_warnings > 0:
        banner_color, banner_bg = "#d68910", "#fef9e7"
        banner_icon = "&#x26A0;"
        banner_title = f"{n_warnings} warning(s) detected"
        banner_sub = "Some metrics are borderline. Review the details below."
    else:
        banner_color, banner_bg = "#1e8449", "#eafaf1"
        banner_icon = "&#x2714;"
        banner_title = "ALL SCANS PASSED"
        banner_sub = "No image quality issues detected across all scans."

    now = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    parts = [
        _html_head(banner_color),
        "<body>",
        _section_header_mriqc(now, mriqc_dir),
        _banner(banner_color, banner_bg, banner_icon, banner_title, banner_sub),
    ]

    if bids_errors or bids_warnings:
        parts.append(_section_bids_findings(bids_errors, bids_warnings))

    parts.extend([
        _section_mriqc(iqm_results, mriqc_reports),
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
    MRIQC &#x2014; Early Image Quality Report
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
                censoring_results=None, connectivity_results=None) -> str:
    iqm_results = iqm_results or []
    mriqc_reports = mriqc_reports or {}
    censoring_results = censoring_results or []
    connectivity_results = connectivity_results or []

    errors = [f for f in qc_findings if f.severity.value == "ERROR"]
    warnings = [f for f in qc_findings if f.severity.value == "WARNING"]
    rescans = [m for m in motion_results if m.flag == "RESCAN"]
    motion_warns = [m for m in motion_results if m.flag == "WARNING"]
    iqm_errors = [r for r in iqm_results if r.worst_severity == "ERROR"]
    iqm_warns  = [r for r in iqm_results if r.worst_severity == "WARNING"]
    censor_errors = [c for c in censoring_results if c.severity == "ERROR"]
    censor_warns = [c for c in censoring_results if c.severity == "WARNING"]
    conn_errors = [c for c in connectivity_results if c.worst_severity == "ERROR"]
    conn_warns = [c for c in connectivity_results if c.worst_severity == "WARNING"]

    n_critical = len(errors) + len(rescans) + len(iqm_errors) + len(censor_errors) + len(conn_errors)
    n_warnings = len(warnings) + len(motion_warns) + len(iqm_warns) + len(censor_warns) + len(conn_warns)

    if n_critical > 0:
        accent_color = "#c0392b"
    elif n_warnings > 0:
        accent_color = "#d68910"
    else:
        accent_color = "#1e8449"

    subjects = _collect_subjects(
        conversion_successes, conversion_failures, qc_findings, motion_results,
        censoring_results, connectivity_results
    )

    now = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    parts = [
        _html_head(accent_color),
        "<body>",
        _section_header(now, output_folder),
        _section_summary_table(subjects, qc_findings, motion_results, iqm_results,
                                censoring_results, connectivity_results),
    ]

    if errors or warnings:
        parts.append(_section_bids_findings(errors, warnings))

    if iqm_results:
        parts.append(_section_mriqc(iqm_results, mriqc_reports))

    if motion_results:
        parts.append(_section_motion(motion_results))

    if censoring_results or connectivity_results:
        parts.append(_section_connectivity_qc(censoring_results, connectivity_results))

    if conversion_failures:
        parts.append(_section_pipeline_failures(conversion_failures))

    parts.append(_html_footer())
    parts.append("</body></html>")

    return "\n".join(parts)


def _collect_subjects(successes, failures, qc_findings, motion_results,
                      censoring_results=None, connectivity_results=None):
    """Build a unified list of subject/session keys seen in any source."""
    censoring_results = censoring_results or []
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
    for c in censoring_results:
        key = (c.sub_id, c.ses_id)
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

def _html_head(accent_color: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>fMRI-Prep Full Pipeline Report</title>
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
  .action-box {{ background: #fff8e1; border-left: 3px solid #f39c12;
                  padding: 6px 10px; border-radius: 4px; margin-top: 4px;
                  font-size: 13px; color: #7d6608; }}
  .plain-msg {{ color: #444; }}
  .meta {{ color: #888; font-size: 12px; }}
  .sep {{ border: none; border-top: 1px solid #e8eaed; margin: 28px 0; }}
  .section-explainer {{ background: #f8f9fa; border-left: 3px solid #b0bec5;
                          padding: 10px 14px; border-radius: 4px; margin-bottom: 16px;
                          font-size: 13px; color: #555; line-height: 1.65; }}
  /* Nilearn / Connectivity QC section */
  .nilearn-section {{ background: #f0f4ff; border: 1.5px solid #7c83d6;
                       border-radius: 10px; padding: 20px 24px 12px;
                       margin: 32px 0 24px; }}
  .nilearn-header {{ display: flex; align-items: center; gap: 10px;
                      margin-bottom: 10px; }}
  .nilearn-tag {{ background: #5c6bc0; color: #fff; font-size: 11px;
                   font-weight: 800; letter-spacing: .06em; padding: 3px 9px;
                   border-radius: 20px; text-transform: uppercase; }}
  .nilearn-title {{ font-size: 1.15rem; font-weight: 700; color: #1a237e; }}
  .nilearn-legend {{ background: #e8eaf6; border-left: 3px solid #5c6bc0;
                      padding: 8px 14px; border-radius: 4px; margin: 10px 0 14px;
                      font-size: 12px; color: #3949ab; line-height: 1.7; }}
  .nilearn-section h3 {{ font-size: .95rem; font-weight: 700; color: #283593;
                          margin: 18px 0 8px; border-left: 3px solid #7986cb;
                          padding-left: 8px; }}
  .nilearn-section table {{ box-shadow: 0 1px 6px rgba(92,107,192,.15); }}
  .nilearn-section th {{ background: #e8eaf6; color: #3949ab; text-align: center; }}
  .nilearn-section .th-hint {{ color: #7986cb; }}
  .metric-ok    {{ font-weight: 700; color: #155724; }}
  .metric-warn  {{ font-weight: 700; color: #856404; }}
  .metric-error {{ font-weight: 700; color: #c0392b; }}
  .metric-unknown {{ color: #888; }}
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
                            censoring_results=None, connectivity_results=None) -> str:
    findings_by_sub = {}
    for f in qc_findings:
        findings_by_sub.setdefault((f.sub_id, f.ses_id), []).append(f)

    motion_by_sub = {}
    for m in motion_results:
        motion_by_sub.setdefault((m.sub_id, m.ses_id), []).append(m)

    iqm_by_sub = {}
    for r in (iqm_results or []):
        iqm_by_sub.setdefault(r.sub_id, []).append(r)

    censoring_by_sub = {}
    for c in (censoring_results or []):
        censoring_by_sub.setdefault((c.sub_id, c.ses_id), []).append(c)

    connectivity_by_sub = {}
    for c in (connectivity_results or []):
        connectivity_by_sub.setdefault((c.sub_id, c.ses_id), []).append(c)

    # Determine if connectivity QC was run
    has_connectivity = bool(censoring_results or connectivity_results)

    _check = '<span class="badge-check">&#10003;</span>'

    rows = []
    for (sub_id, ses_id), info in sorted(subjects.items()):
        conv_badge = (
            _check
            if info["status"] == "converted"
            else '<span class="badge badge-failed">Failed</span>'
        )

        sub_findings = findings_by_sub.get((sub_id, ses_id), [])
        if any(f.severity.value == "ERROR" for f in sub_findings):
            qc_badge = '<span class="badge badge-error">Issues found</span>'
        elif any(f.severity.value == "WARNING" for f in sub_findings):
            qc_badge = '<span class="badge badge-warning">Warnings</span>'
        else:
            qc_badge = _check

        sub_iqm = iqm_by_sub.get(sub_id, [])
        if any(r.worst_severity == "ERROR" for r in sub_iqm):
            iqm_badge = '<span class="badge badge-error">Issues found</span>'
        elif any(r.worst_severity == "WARNING" for r in sub_iqm):
            iqm_badge = '<span class="badge badge-warning">Warnings</span>'
        else:
            iqm_badge = _check

        sub_motion = motion_by_sub.get((sub_id, ses_id), [])
        if any(m.flag == "RESCAN" for m in sub_motion):
            motion_badge = '<span class="badge badge-rescan">Issues found</span>'
        elif any(m.flag == "WARNING" for m in sub_motion):
            motion_badge = '<span class="badge badge-warning">Warnings</span>'
        elif sub_motion:
            motion_badge = _check
        else:
            motion_badge = '<span class="meta">—</span>'

        # Connectivity badge (if enabled)
        conn_badge = '<span class="meta">—</span>'
        if has_connectivity:
            sub_censor = censoring_by_sub.get((sub_id, ses_id), [])
            sub_conn = connectivity_by_sub.get((sub_id, ses_id), [])

            # Check censoring first (more critical)
            unsuitable_censor = any(not c.connectivity_ready for c in sub_censor)
            warn_censor = any(c.severity == "WARNING" for c in sub_censor)

            # Check connectivity metrics
            error_conn = any(c.worst_severity == "ERROR" for c in sub_conn)
            warn_conn = any(c.worst_severity == "WARNING" for c in sub_conn)

            if unsuitable_censor or error_conn:
                conn_badge = '<span class="badge badge-error">Issues found</span>'
            elif warn_censor or warn_conn:
                conn_badge = '<span class="badge badge-warning">Warnings</span>'
            elif sub_censor or sub_conn:
                conn_badge = _check

        row_content = (
            f"<tr><td><b>sub-{sub_id}</b><br><span class='meta'>ses-{ses_id}</span></td>"
            f"<td>{conv_badge}</td><td>{qc_badge}</td>"
            f"<td>{iqm_badge}</td><td>{motion_badge}</td>"
        )

        if has_connectivity:
            row_content += f"<td>{conn_badge}</td>"

        row_content += "</tr>"
        rows.append(row_content)

    colspan = 6 if has_connectivity else 5
    rows_html = "\n".join(rows) if rows else f"<tr><td colspan='{colspan}'>No subjects found.</td></tr>"

    conn_header = "<th>Connectivity</th>" if has_connectivity else ""

    return f"""<h2>Overview</h2>
<table>
  <thead><tr>
    <th>Run</th>
    <th>BIDS Conversion</th><th>Scan QC</th><th>MRIQC</th><th>Motion Analysis</th>{conn_header}
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
    <th>Subject</th><th>Status</th><th>Category</th><th>Details</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>"""


def _section_motion(motion_results) -> str:
    _check = '<span class="badge-check">&#10003;</span>'
    rows = []
    for m in sorted(motion_results, key=lambda x: (x.sub_id, x.ses_id)):
        if m.flag == "RESCAN":
            badge = '<span class="badge badge-rescan">RE-SCAN</span>'
        elif m.flag == "WARNING":
            badge = '<span class="badge badge-warning">WARNING</span>'
        else:
            badge = _check

        fd_bar = _fd_bar(m.pct_high_motion)
        rows.append(
            f"<tr>"
            f"<td><b>sub-{m.sub_id}</b><br>"
            f"<span class='meta'>ses-{m.ses_id} / {m.run_label}</span></td>"
            f"<td>{badge}</td>"
            f"<td>{m.mean_fd:.2f} mm</td>"
            f"<td>{fd_bar}<br><span class='meta'>{m.pct_high_motion:.0f}% "
            f"({m.n_high_motion}/{m.n_frames} frames)</span></td>"
            f"</tr>"
        )
    rows_html = "\n".join(rows)

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
  (in mm). A frame with FD &gt; {0.5}&nbsp;mm is considered a <i>high-motion frame</i>.
  Runs with many high-motion frames yield unreliable activation maps and inflated
  functional-connectivity estimates.
  <br><br>
  <b>Thresholds used here:</b>&ensp;
  RE-SCAN: &ge;20% high-motion frames <i>or</i> mean&nbsp;FD &ge; 1.0&nbsp;mm &nbsp;|&nbsp;
  WARNING: &ge;10% high-motion frames <i>or</i> mean&nbsp;FD &ge; 0.5&nbsp;mm.
</div>
<table>
  <thead><tr>
    <th>Run</th><th>Status</th>
    <th>Mean FD<br><span class="th-hint">&#9888; &ge;0.5mm &nbsp; &#10007; &ge;1.0mm</span></th><th>High-motion frames<br><span class="th-hint">FD &gt;0.5mm &nbsp;|&nbsp; &#9888; &ge;10% &nbsp; &#10007; &ge;20%</span></th>
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
<div class="section-explainer">
  Sessions listed here could not be fully processed. The <b>Stage</b> column indicates
  where the failure occurred (BIDS conversion or fMRIPrep preprocessing) and the
  <b>Error</b> column shows the reason. Common causes include missing scan types,
  Docker container issues, or insufficient disk space.
</div>
<table>
  <thead><tr>
    <th>Subject</th><th>Session</th><th>Stage</th><th>Error</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>"""


def _section_mriqc(iqm_results, mriqc_reports) -> str:
    group_reports = mriqc_reports.get("group_reports", [])
    subject_reports = mriqc_reports.get("subject_reports", [])

    group_links = ""
    if group_reports:
        links = " &nbsp;|&nbsp; ".join(
            f'<a href="mriqc/{r["path"].name}" target="_blank">group_{r["scan_type"]}.html</a>'
            for r in group_reports
        )
        group_links = f'<p style="margin-bottom:12px;">Group reports (open for outlier detection): {links}</p>'

    rows = []
    sorted_results = sorted(
        iqm_results,
        key=lambda x: (x.sub_id, x.ses_id, 0 if x.modality == "T1w" else 1, x.scan_file),
    )
    for r in sorted_results:
        sev = r.worst_severity
        if sev == "ERROR":
            badge = '<span class="badge badge-error">ERROR</span>'
        elif sev == "WARNING":
            badge = '<span class="badge badge-warning">WARNING</span>'
        else:
            badge = '<span class="badge badge-ok">OK</span>'

        # --- Visual report link: match by filename stem ---
        iqm_stem = Path(r.scan_file).stem  # e.g. "sub-010_ses-01_T1w"
        sub_html = next(
            (
                f'<a href="mriqc/sub-{r.sub_id}/{s["scan_type"]}/{s["filename"]}" '
                f'target="_blank">{s["filename"]}</a>'
                for s in subject_reports
                if Path(s["filename"]).stem == iqm_stem
            ),
            r.scan_file,
        )

        # --- Flags column ---
        flag_lines = (
            "<br>".join(
                f'<span class="badge {"badge-error" if fl.severity == "ERROR" else "badge-warning"}">'
                f'{fl.severity}</span> {fl.metric_label}: {fl.value:.3f}'
                for fl in r.flags
            )
            if r.flags else "<span class='meta'>No flags</span>"
        )

        # --- Color-coded metrics: show ALL, colored by severity ---
        flag_sev = {fl.metric: fl.severity for fl in r.flags}
        metrics_str = " &nbsp; ".join(
            _metric_span(f"{k}={v:.2f}", flag_sev.get(k, "OK"))
            for k, v in r.metrics.items()
        )

        # --- Scan column: subject, session, scan label ---
        scan_label = r.scan_label if hasattr(r, 'scan_label') else r.modality
        ses_line = f"<br><span class='meta'>ses-{r.ses_id}</span>" if r.ses_id else ""
        rows.append(
            f"<tr>"
            f"<td><b>sub-{r.sub_id}</b>{ses_line}<br>"
            f"<span class='meta'>{scan_label}</span></td>"
            f"<td>{badge}</td>"
            f"<td>{flag_lines}</td>"
            f"<td style='font-size:12px'>{metrics_str}</td>"
            f"<td style='font-size:12px'>{sub_html}</td>"
            f"</tr>"
        )
    rows_html = "\n".join(rows)

    return f"""<hr class="sep">
<h2>MRIQC &#x2014; Image Quality Metrics</h2>
<div class="section-explainer">
  <a href="https://mriqc.readthedocs.io/" target="_blank" style="color:#5c6bc0;">MRIQC</a>
  (MRI Quality Control) is a tool developed by the
  <a href="https://www.nipreps.org/" target="_blank" style="color:#5c6bc0;">NiPreps</a>
  community that computes <b>Image Quality Metrics (IQMs)</b> on unprocessed MRI data.
  It produces per-scan visual reports and a set of numerical measures that help identify
  problematic acquisitions <i>before</i> investing time in preprocessing.
  <br><br>
  <b>Structural (T1w) metrics:</b>
  <b>SNR</b> (signal-to-noise ratio in gray matter) quantifies overall image clarity;
  <b>CNR</b> (contrast-to-noise ratio) measures the ability to distinguish gray from white matter;
  <b>CJV</b> (coefficient of joint variation) detects tissue-intensity overlap caused by motion or
  B1-field inhomogeneity;
  <b>INU range</b> captures the severity of intensity non-uniformity (bias field);
  <b>QI1</b> estimates the proportion of artifact-contaminated voxels in the air background.
  <br><br>
  <b>Functional (BOLD) metrics:</b>
  <b>tSNR</b> (temporal signal-to-noise ratio) reflects the stability of the BOLD signal over time
  &mdash; low tSNR means noisy time-series that reduce statistical power;
  <b>FD mean</b> (mean framewise displacement) summarizes average head movement per volume;
  <b>GSR</b> (ghost-to-signal ratio, X and Y) detects EPI ghosting artifacts along each
  phase-encode direction;
  <b>AOR</b> (AFNI outlier ratio) reports the fraction of volumes flagged as outliers.
  <br><br>
  Thresholds shown here are indicative &mdash; always open the MRIQC visual HTML reports
  for the full picture (carpet plots, tissue segmentation overlays, and mosaic views).
  <br><br>
  <b>Metric colors:</b>
  <span class="metric-ok">green = within normal range</span>,
  <span class="metric-warn">yellow = borderline</span>,
  <span class="metric-error">red = outside acceptable range</span>.
</div>
{group_links}
<table>
  <thead><tr>
    <th>Scan</th><th>Status</th><th>Flags</th><th>Metrics</th><th>Visual Report</th>
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


def _metric_span(value: str, severity: str) -> str:
    """Wrap a metric value in a severity-colored span."""
    css = {"OK": "metric-ok", "WARNING": "metric-warn",
           "ERROR": "metric-error"}.get(severity, "metric-unknown")
    return f'<span class="{css}">{value}</span>'


def _section_connectivity_qc(censoring_results, connectivity_results) -> str:
    """Generate the Nilearn connectivity QC section with distinctive styling."""

    if not censoring_results and not connectivity_results:
        return ""

    intro = """<hr class="sep">
<div class="nilearn-section">
<div class="nilearn-header">
  <span class="nilearn-tag">Nilearn</span>
  <span class="nilearn-title">Functional Connectivity Quality Assessment</span>
</div>
<div class="section-explainer" style="background:#e8eaf6;border-color:#5c6bc0;color:#3949ab;">
  This section evaluates whether each BOLD run has sufficient data quality for
  <b>functional connectivity analysis</b> (e.g., seed-based correlation, network parcellation,
  or graph-theoretic measures).
  Connectivity estimates are especially sensitive to head motion because even small movements
  can introduce spurious short-range correlations and inflate or distort network structure
  (Power et al., 2012; Satterthwaite et al., 2013).
  <br><br>
  The analyses below are computed with
  <a href="https://nilearn.github.io/" target="_blank" style="color:#5c6bc0;">Nilearn</a>,
  an open-source Python library for statistical learning on neuroimaging data.
  Nilearn extracts regional time-series from a brain atlas (here, Schaefer 100-parcel),
  computes a connectivity matrix (Pearson correlation), and then derives the QC metrics below.
  Thresholds follow recommendations from
  <a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC10977879/" target="_blank" style="color:#5c6bc0;">Parkes et al.</a>
</div>
<div class="nilearn-legend">
  <b>Metrics at a glance:</b><br>
  &#9679; <b>Volume Censoring</b> &mdash;
  Identifies BOLD volumes where framewise displacement exceeds 0.2&nbsp;mm (a strict threshold
  appropriate for connectivity work) and reports the proportion of volumes that would be
  removed ("scrubbed"). If more than 80% of volumes are censored or less than 1&nbsp;minute of
  clean data remains, the run is <span class="metric-error">not suitable</span> for
  connectivity analysis.<br>
  &#9679; <b>DM-FC</b> (Distance-dependent Motion &ndash; Functional Connectivity, split-based) &mdash;
  Splits each run&rsquo;s timepoints into high-FD (&gt;0.2&nbsp;mm) and low-FD groups,
  computes separate connectivity matrices for each, and correlates the difference
  (high&minus;low) with inter-ROI Euclidean distance.
  A strong negative correlation means motion inflates short-range connections (bad);
  near-zero means denoising worked (good).
  If either split has too few frames (&lt;20), the metric is skipped &mdash; this is treated
  as OK since it indicates a low-motion scan.
  <span class="metric-ok">|r|&lt;0.10 = acceptable</span>,
  <span class="metric-warn">0.10&ndash;0.20 = caution</span>,
  <span class="metric-error">&gt;0.20 = likely biased</span>.
</div>"""

    sections = [intro]

    # Section 4a: Volume Censoring
    if censoring_results:
        rows = []
        for c in sorted(censoring_results, key=lambda x: (x.sub_id, x.ses_id, x.run_label)):
            if c.connectivity_ready and c.severity == "OK":
                badge = '<span class="badge badge-ok">Ready</span>'
            elif c.connectivity_ready and c.severity == "WARNING":
                badge = '<span class="badge badge-warning">Marginal</span>'
            else:
                badge = '<span class="badge badge-error">Not Suitable</span>'

            censor_bar = _fd_bar(c.pct_censored_02mm)
            pct_cls = ("metric-error" if c.pct_censored_02mm > 80
                       else "metric-warn" if c.pct_censored_02mm > 40
                       else "metric-ok")

            rows.append(
                f"<tr>"
                f"<td><b>sub-{c.sub_id}</b> / ses-{c.ses_id}<br>"
                f"<span class='meta'>{c.run_label}</span></td>"
                f"<td>{badge}</td>"
                f"<td>{c.mean_fd:.2f} mm</td>"
                f"<td><span class='{pct_cls}'>{c.pct_censored_02mm:.0f}%</span> {censor_bar}<br>"
                f"<span class='meta'>({c.n_censored_02mm}/{c.n_volumes} vols @ 0.2mm)</span></td>"
                f"<td>{c.usable_minutes_02mm:.1f} min<br>"
                f"<span class='meta'>({c.usable_volumes_02mm} volumes)</span></td>"
                f"<td class='details-left' style='font-size:12px'>{c.plain_message}</td>"
                f"</tr>"
            )

        rows_html = "\n".join(rows) if rows else "<tr><td colspan='6'>No results</td></tr>"
        sections.append(f"""<h3>Volume Censoring</h3>
<table>
  <thead><tr>
    <th>Subject / Run</th><th>Status</th><th>Mean FD</th>
    <th>Censored @ 0.2mm<br><span class="th-hint">&#10007; &gt;80% censored</span></th><th>Usable Time<br><span class="th-hint">&#10007; &lt;1 min remaining</span></th><th>Notes</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>""")

    # Section 4b: DM-FC metrics
    if connectivity_results:
        rows = []
        for c in sorted(connectivity_results, key=lambda x: (x.sub_id, x.ses_id, x.run_label)):
            if c.worst_severity == "OK":
                badge = '<span class="badge badge-ok">OK</span>'
            elif c.worst_severity == "WARNING":
                badge = '<span class="badge badge-warning">WARNING</span>'
            elif c.worst_severity == "ERROR":
                badge = '<span class="badge badge-error">EXCLUDE</span>'
            else:
                badge = '<span class="metric-unknown">UNKNOWN</span>'

            if c.dm_fc_value is not None:
                dm_fc_str = _metric_span(f"{c.dm_fc_value:.3f}", c.dm_fc_severity)
            elif getattr(c, 'dm_fc_note', ''):
                dm_fc_str = f'<span class="metric-ok">{c.dm_fc_note}</span>'
            else:
                dm_fc_str = '<span class="metric-unknown">&mdash;</span>'
            mod_str   = (_metric_span(f"{c.modularity_q:.3f}", c.modularity_severity)
                         if c.modularity_q is not None
                         else '<span class="metric-unknown">&mdash;</span>')

            error_msg = ""
            if c.error_message:
                error_msg = (f"<br><span class='meta' style='color:#c0392b;'>"
                             f"Error: {c.error_message[:100]}</span>")

            action_box = ""
            if c.action:
                action_box = (f"<div class='action-box' style='border-color:#5c6bc0;"
                              f"background:#e8eaf6;color:#283593;'>{c.action}</div>")

            rows.append(
                f"<tr>"
                f"<td><b>sub-{c.sub_id}</b> / ses-{c.ses_id}<br>"
                f"<span class='meta'>{c.run_label} &bull; {c.atlas_name} &bull; {c.n_rois} ROIs</span></td>"
                f"<td>{badge}</td>"
                f"<td>{dm_fc_str}<br><span class='meta'>({c.dm_fc_severity})</span></td>"
                f"<td>{mod_str}<br><span class='meta'>({c.modularity_severity})</span></td>"
                f"<td style='font-size:12px'>{c.plain_message}{error_msg}{action_box}</td>"
                f"</tr>"
            )

        rows_html = "\n".join(rows) if rows else "<tr><td colspan='5'>No results</td></tr>"
        sections.append(f"""<h3>Motion-Connectivity Metrics (DM-FC)</h3>
<table>
  <thead><tr>
    <th>Subject / Run</th><th>Status</th><th>DM-FC</th><th>Modularity Q</th><th>Recommendation</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>""")

    # Section 4c: Connectivity Heatmaps
    heatmap_runs = [c for c in connectivity_results
                    if getattr(c, 'heatmap_base64', None)]
    if heatmap_runs:
        heatmap_parts = ['<h3>Connectivity Heatmaps</h3>']
        for c in sorted(heatmap_runs, key=lambda x: (x.sub_id, x.ses_id, x.run_label)):
            label = f"sub-{c.sub_id} / ses-{c.ses_id} / {c.run_label}"
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
        sections.append("\n".join(heatmap_parts))

    sections.append("</div>")  # close .nilearn-section
    return "\n".join(sections)


def _html_footer() -> str:
    return """<hr class="sep">
<div style="text-align:center;color:#aaa;font-size:12px;padding-top:12px;">
  Generated by fMRI Preprocessing Assistant &nbsp;|&nbsp;
  For help, contact your lab's technical support
</div>
</div>"""
