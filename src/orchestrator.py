#!/usr/bin/env python3
"""
Main orchestrator for fMRI preprocessing.

This module coordinates all pipeline components:
1. Subject/session discovery
2. BIDS conversion
3. fMRIPrep preprocessing  
4. Report generation
5. Cleanup

Usage:
    python -m src.orchestrator --input /path/to/dicoms --output_dir /path/to/output

    Or via GUI: python run.py
"""

import argparse
import subprocess
import sys
import os
import json
import base64
import shutil
import threading
import multiprocessing
from pathlib import Path
from datetime import datetime
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed

# Use absolute imports for compatibility when run as script
try:
    # When run as part of package
    from .core.utils import setup_encoding, safe_print, set_log_file, close_log_file
    from .core.discovery import find_subject_folders, find_sessions, sanitize_id, has_dicom_files
    from .core.progress import ProgressTracker
    from .bids.converter import run_bids_conversion, create_dataset_description
    from .bids.analyzer import count_output_files
    from .reporting.report import ExecutionReport
    from .reporting.html_report import generate as generate_html_report, generate_mriqc_report
    from .qc.checker import BIDSQualityChecker
    from .qc import motion_parser
    from .qc import connectivity_thresholds
    from .mriqc import iqm_parser
    from .mriqc import runner as mriqc_runner
except ImportError:
    # When run directly as script
    from core.utils import setup_encoding, safe_print, set_log_file, close_log_file
    from core.discovery import find_subject_folders, find_sessions, sanitize_id, has_dicom_files
    from core.progress import ProgressTracker
    from bids.converter import run_bids_conversion, create_dataset_description
    from bids.analyzer import count_output_files
    from reporting.report import ExecutionReport
    from reporting.html_report import generate as generate_html_report, generate_mriqc_report
    from qc.checker import BIDSQualityChecker
    from qc import motion_parser
    from qc import connectivity_thresholds
    from mriqc import iqm_parser
    from mriqc import runner as mriqc_runner

setup_encoding()


def _pick_mni_space(output_spaces):
    """Return the first MNI space from output_spaces, or the default.

    Strips any TemplateFlow resolution suffix (e.g. ``":res-2"``) so the
    returned name can be used in BIDS filename glob patterns.
    """
    for space in (output_spaces or []):
        if space.startswith("MNI"):
            return space.split(":")[0]
    return "MNI152NLin2009cAsym"


def _collect_coreg_plots(derivatives_dir):
    """Collect fMRIPrep coregistration overlay SVGs from the derivatives directory.

    Searches both ``derivatives/sub-*/figures/`` and ``derivatives/fmriprep/sub-*/figures/``
    for ``*_desc-coreg_bold.svg`` files.

    Returns:
        dict mapping run key (e.g. ``"sub-010_ses-02_task-rest_run-01"``) to Path.
    """
    import re
    _coreg_re = re.compile(r"_desc-coreg_bold$")
    deriv_path = Path(derivatives_dir)

    search_roots = [deriv_path, deriv_path / "fmriprep"]
    seen_paths = set()
    coreg_plots = {}

    for root in search_roots:
        if not root.exists():
            continue
        for svg in sorted(root.glob("sub-*/figures/*_desc-coreg_bold.svg")):
            resolved = svg.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            key = _coreg_re.sub("", svg.stem)
            if key not in coreg_plots:
                coreg_plots[key] = svg

    return coreg_plots


def _read_researcher_comments(output_folder):
    """Read the latest researcher comments from the comments file.

    The GUI (or CLI) writes comments to
    ``<output_folder>/execution_logs/.researcher_comments.txt`` and may
    update the file while the pipeline is running.  This helper is called
    just before each report is generated so the reports always contain the
    most recent version of the comments.
    """
    comments_path = Path(output_folder) / "execution_logs" / ".researcher_comments.txt"
    try:
        if comments_path.exists():
            return comments_path.read_text(encoding="utf-8").strip()
    except Exception:
        pass  # Best-effort
    return ""


def _write_structured_summary(
    summary_path,
    report,
    subjects_tasks,
    sessions_missing_bold,
    motion_results,
    connectivity_results,
    errors,
    pipeline_start_time,
    iqm_results=None,
    ran_fmriprep=True,
    ran_mriqc=True,
):
    """
    Write a human-readable, structured summary to its own file.

    Organised by subject > session so a reader can quickly find the outcome
    for any scan without wading through interleaved parallel output.

    Wrapped in try/except so a formatting bug can never crash the pipeline.
    """
    try:
        lines = _build_structured_summary(
            report, subjects_tasks, sessions_missing_bold,
            motion_results, connectivity_results,
            errors, pipeline_start_time, iqm_results,
            ran_fmriprep=ran_fmriprep, ran_mriqc=ran_mriqc,
        )
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        safe_print(f"Structured summary: {summary_path}", flush=True)
    except Exception as e:
        safe_print(
            f"(Could not generate structured summary: {e})",
            flush=True,
        )


def _build_structured_summary(
    report, subjects_tasks, sessions_missing_bold,
    motion_results, connectivity_results,
    errors, pipeline_start_time, iqm_results=None,
    ran_fmriprep=True, ran_mriqc=True,
):
    """Build the structured summary as a list of lines. May raise; caller catches."""

    W = 70  # output width
    elapsed = datetime.now() - pipeline_start_time
    elapsed_min = elapsed.total_seconds() / 60
    lines = []

    def out(text=""):
        lines.append(text)

    # Index helper data by (sub, ses) for fast lookup
    success_map = {}
    for s in report.successful:
        success_map[(s['sub_id'], s['ses_id'])] = s
    fail_map = {}
    for f in report.failed:
        key = (f['sub_id'], f['ses_id'])
        fail_map.setdefault(key, []).append(f)

    motion_map = {}
    for m in (motion_results or []):
        motion_map.setdefault((m.sub_id, m.ses_id), []).append(m)
    conn_map = {}
    for c in (connectivity_results or []):
        conn_map.setdefault((c.sub_id, c.ses_id), []).append(c)
    iqm_map = {}
    for r in (iqm_results or []):
        iqm_map.setdefault((r.sub_id, r.ses_id), []).append(r)

    # ---- header ----
    out("=" * W)
    out("STRUCTURED EXECUTION SUMMARY".center(W))
    out("(ordered by subject and session for easy reading)".center(W))
    out("=" * W)
    out()
    out(f"  Generated        : {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
    out()

    total_sessions = sum(len(ts) for ts in subjects_tasks.values())
    n_success = len(report.successful)
    n_fail = len(report.failed)
    out(f"  Subjects processed : {len(subjects_tasks)}")
    out(f"  Sessions processed : {total_sessions}")
    out(f"  Successful         : {n_success}")
    if n_fail:
        out(f"  Failed / skipped   : {n_fail}")
    out(f"  Total time         : {elapsed_min:.1f} min")
    out()

    # ---- per-subject / per-session breakdown ----
    for sub_id in sorted(subjects_tasks.keys()):
        sub_tasks = subjects_tasks[sub_id]
        session_ids = sorted(set(t['ses_id'] for t in sub_tasks))

        out("-" * W)
        out(f"  Subject {sub_id}  ({len(session_ids)} session(s))")
        out("-" * W)

        for ses_id in session_ids:
            key = (sub_id, ses_id)
            out()
            out(f"    Session {ses_id}")
            out(f"    {'~' * 40}")

            # -- BIDS conversion --
            if key in success_map:
                dur = success_map[key].get('duration', 0)
                out(f"      BIDS conversion : Done ({dur:.0f}s)")
            elif key in fail_map:
                stages = [f['stage'] for f in fail_map[key]]
                if "BIDS Conversion" in stages:
                    err = next(
                        f['error'] for f in fail_map[key]
                        if f['stage'] == "BIDS Conversion"
                    )
                    out(f"      BIDS conversion : FAILED -- {err[:80]}")
            else:
                out("      BIDS conversion : (not attempted)")

            # -- BOLD availability --
            if key in sessions_missing_bold:
                out("      BOLD data       : Not found -- session has no functional scans")
            else:
                out("      BOLD data       : Present")

            # -- MRIQC --
            if ran_mriqc:
                sub_iqm = iqm_map.get(key, [])
                if sub_iqm:
                    for r in sub_iqm:
                        sev = r.worst_severity
                        if sev == "OK":
                            out(f"      MRIQC [{r.modality:5s}]    : OK")
                        else:
                            flag_strs = [
                                f"{fl.metric_label}={fl.value:.3f}"
                                for fl in r.flags
                            ]
                            out(
                                f"      MRIQC [{r.modality:5s}]    : {sev}  "
                                f"({', '.join(flag_strs)})"
                            )

            # -- fMRIPrep --
            if ran_fmriprep:
                fmriprep_fails = [
                    f for f in fail_map.get(key, []) if f['stage'] == "fMRIPrep"
                ]
                if fmriprep_fails:
                    for f in fmriprep_fails:
                        out(f"      fMRIPrep        : FAILED -- {f['error'][:80]}")
                elif key in sessions_missing_bold:
                    out("      fMRIPrep        : Skipped (no BOLD)")
                elif key in success_map:
                    if motion_map.get(key):
                        out("      fMRIPrep        : Done")
                    else:
                        out("      fMRIPrep        : Done (no confounds found)")

                # -- Motion QC --
                for m in motion_map.get(key, []):
                    label = m.run_label or ""
                    if m.flag == "OK":
                        out(
                            f"      Motion [{label:20s}] : OK  "
                            f"(mean FD {m.mean_fd:.2f} mm)"
                        )
                    elif m.flag == "WARNING":
                        out(
                            f"      Motion [{label:20s}] : WARNING  "
                            f"(mean FD {m.mean_fd:.2f} mm, "
                            f"{m.pct_high_motion:.0f}% high-motion)"
                        )
                    else:
                        out(
                            f"      Motion [{label:20s}] : RE-SCAN  "
                            f"(mean FD {m.mean_fd:.2f} mm, "
                            f"{m.pct_high_motion:.0f}% high-motion)"
                        )

                # -- Connectivity --
                for c in conn_map.get(key, []):
                    label = c.run_label or ""
                    out(
                        f"      Connectivity [{label:14s}] : {c.worst_severity}  "
                        f"(FD={c.mean_fd:.2f}mm, {c.pct_censored:.0f}% censored, {c.usable_minutes:.1f}min usable)"
                    )

    out()

    # ---- QC findings ----
    qc_all = report.qc_findings
    qc_errors = [f for f in qc_all if f.severity.value == "ERROR"]
    qc_warnings = [f for f in qc_all if f.severity.value == "WARNING"]
    if qc_errors or qc_warnings:
        out("-" * W)
        out("  Quality control findings")
        out("-" * W)
        for f in sorted(qc_errors, key=lambda x: (x.sub_id, x.ses_id)):
            out(f"    [ERROR]   sub-{f.sub_id}/ses-{f.ses_id}: {f.plain_message}")
        for f in sorted(qc_warnings, key=lambda x: (x.sub_id, x.ses_id)):
            out(f"    [WARNING] sub-{f.sub_id}/ses-{f.ses_id}: {f.plain_message}")
        out()

    # ---- errors summary ----
    if errors:
        out("-" * W)
        out("  Pipeline errors")
        out("-" * W)
        for err in errors:
            out(f"    [X] {err}")
        out()

    # ---- reading guide ----
    out("-" * W)
    out("  How to read this file")
    out("-" * W)
    out()
    out("  Each subject section shows every session and what happened at each")
    out("  pipeline stage. Here is what the stages mean:")
    out()
    out("    BIDS conversion  - Converts raw scanner files (DICOM) into the")
    out("                       standard BIDS format used by analysis tools.")
    out("    BOLD data        - Whether functional brain-activity scans were")
    out("                       found. Sessions without BOLD cannot be")
    out("                       preprocessed by fMRIPrep.")
    if ran_mriqc:
        out("    MRIQC            - Image quality metrics computed on raw data")
        out("                       before preprocessing. Flags scans with poor")
        out("                       SNR, motion, ghosting, or other artefacts.")
    if ran_fmriprep:
        out("    fMRIPrep         - Preprocessing: motion correction, spatial")
        out("                       normalisation, confound estimation.")
        out("    Motion           - Head-motion quality check. 'OK' is good;")
        out("                       'WARNING' means elevated motion; 'RE-SCAN'")
        out("                       means the data may be unusable.")
        out("    Censoring        - How many volumes were removed due to motion.")
        out("                       More usable minutes = better.")
        out("    Connectivity     - Checks whether motion corrupts brain-network")
        out("                       estimates (DM-FC split-based metric).")
    out()
    if ran_fmriprep:
        out("  For the full visual report, open full_pipeline_report.html in your browser.")
    elif ran_mriqc:
        out("  For the visual report, open the mriqc_report.html in your browser.")
    out()

    # ---- footer ----
    out("=" * W)
    out("END OF STRUCTURED SUMMARY".center(W))
    out("=" * W)
    out()

    return lines


def process_bids_task(task, bids_dir, progress_tracker,
                      desc_created_event, report, anonymize=False,
                      qc_checker=None):
    """
    Run BIDS conversion + QC for a single subject-session.

    This function is designed to run in parallel across multiple threads
    (Phase 1 of the pipeline).

    Args:
        task: Dictionary with sub_id, ses_id, dicom_path, task_num
        bids_dir: BIDS output directory
        progress_tracker: ProgressTracker instance
        desc_created_event: Threading event for dataset_description.json
        report: ExecutionReport instance
        anonymize: If True, anonymize DICOM metadata
        qc_checker: BIDSQualityChecker instance

    Returns:
        Tuple of (error_string_or_None, missing_bold: bool,
                  excluded_bold: list of (nii_path, json_path) tuples)
    """
    sub_id = task['sub_id']
    ses_id = task['ses_id']
    dicom_path = task.get('dicom_path')
    task_num = task['task_num']
    task_label = f"sub-{sub_id}/ses-{ses_id}"

    safe_print(f"[{task_label}] Starting conversion...", flush=True)

    # Signal task start for progress tracking
    progress_tracker.task_start(task_num)

    missing_bold = False
    excluded_bold = []

    success, duration, error_msg, bold_notes = run_bids_conversion(
        dicom_path, sub_id, ses_id, bids_dir, task_label, anonymize=anonymize
    )

    if success:
        report.add_success(sub_id, ses_id, duration)

        # Collect BOLD files that should be hidden from fMRIPrep
        from bids.converter import get_excluded_bold_paths
        excluded_bold = get_excluded_bold_paths(bold_notes)

        # Layer 1: Run BIDS quality checks immediately after conversion
        if qc_checker is not None:
            # Record BOLD fragment/duplicate findings from conversion
            if bold_notes:
                qc_checker.add_bold_notes(sub_id, ses_id, bold_notes)
            session_findings = qc_checker.check_session(bids_dir, sub_id, ses_id)
            n_errors = sum(1 for f in session_findings if f.severity.value == "ERROR")
            n_warnings = sum(1 for f in session_findings if f.severity.value == "WARNING")
            if n_errors > 0:
                safe_print(
                    f"[QC] {task_label} - {n_errors} error(s), {n_warnings} warning(s) found",
                    flush=True,
                )
                for finding in session_findings:
                    if finding.severity.value == "ERROR":
                        safe_print(f"  [QC-ERROR] {finding.message}", flush=True)
            elif n_warnings > 0:
                safe_print(
                    f"[QC] {task_label} - {n_warnings} warning(s) found", flush=True
                )
            else:
                safe_print(f"[QC] {task_label} - OK", flush=True)

            # Check if BOLD is missing — fMRIPrep cannot run without it
            missing_bold = any(
                f.category == "missing_scan" and "BOLD" in f.message
                for f in session_findings
            )

        # Create dataset_description.json — pybids.BIDSLayout
        # requires this file to exist at startup or it raises BIDSValidationError.
        if not desc_created_event.is_set():
            if create_dataset_description(bids_dir):
                desc_created_event.set()
    else:
        report.add_failure(sub_id, ses_id, error_msg, "BIDS Conversion")
        progress_tracker.increment()
        safe_print(f"[FAIL] {task_label} - BIDS conversion failed", flush=True)
        return f"{task_label} (BIDS failed)", missing_bold, []

    progress_tracker.increment()
    return None, missing_bold, excluded_bold


def run_fmriprep_for_subject(sub_id, session_ids, bids_dir, derivatives_dir,
                             fmriprep_script, fmriprep_opts, report,
                             debug_log_file=None):
    """
    Run fMRIPrep once for a subject, processing all of its sessions.

    fMRIPrep is invoked with ``--participant-label`` only (no session filter),
    so it processes every session present in the BIDS directory for this
    subject.  Running it once per subject is both faster and produces a
    consistent anatomical reference across sessions.

    Memory is scaled based on the number of sessions:
        base = 16 000 MB; +4 000 MB for each session beyond 2.

    Args:
        sub_id: Subject identifier (without ``sub-`` prefix)
        session_ids: List of session identifiers for this subject
        bids_dir: BIDS dataset directory
        derivatives_dir: fMRIPrep derivatives directory
        fmriprep_script: Path to fMRIPrep runner script
        fmriprep_opts: Dictionary of fMRIPrep options
        report: ExecutionReport instance
        debug_log_file: Optional path to a debug log file

    Returns:
        Error string if failed, None if successful.
    """
    sub_label = f"sub-{sub_id}"
    n_sessions = len(session_ids)

    # Scale memory for multi-session processing
    base_mem = 16000
    mem_mb = base_mem if n_sessions <= 2 else base_mem + (n_sessions - 2) * 4000

    safe_print(
        f"[{sub_label}] Running fMRIPrep ({n_sessions} session(s), mem={mem_mb}MB)...",
        flush=True,
    )

    # Build the fMRIPrep subprocess command
    cmd_fmriprep = [
        sys.executable,
        str(fmriprep_script),
        str(bids_dir),
        str(derivatives_dir),
        sub_id,
    ]

    # Inject mem_mb into opts so the runner subprocess receives it
    opts = dict(fmriprep_opts) if fmriprep_opts else {}
    opts["mem_mb"] = mem_mb

    opts_json = json.dumps(opts)
    opts_encoded = base64.b64encode(opts_json.encode("utf-8")).decode("ascii")
    cmd_fmriprep.extend(["--opts", opts_encoded])

    fmriprep_start_time = datetime.now()
    error = None

    try:
        result = subprocess.run(
            cmd_fmriprep,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        fmriprep_elapsed = (datetime.now() - fmriprep_start_time).total_seconds()

        if result.returncode != 0:
            safe_print(f"[FAIL] {sub_label} - fMRIPrep failed", flush=True)

            # Write detailed error output to debug log file
            if debug_log_file:
                try:
                    with open(debug_log_file, "a", encoding="utf-8") as f:
                        f.write(f"\n{'='*80}\n")
                        f.write(f"fMRIPrep FAILURE: {sub_label}\n")
                        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                        f.write(f"Return code: {result.returncode}\n")
                        f.write(f"{'='*80}\n\n")
                        if result.stdout:
                            f.write("--- STDOUT ---\n")
                            f.write(result.stdout)
                            f.write("\n\n")
                        if result.stderr:
                            f.write("--- STDERR ---\n")
                            f.write(result.stderr)
                            f.write("\n\n")
                except Exception as e:
                    safe_print(f"Warning: Could not write to debug log: {e}", flush=True)

            # Print detailed error output for debugging
            if result.stdout:
                safe_print("\n--- fMRIPrep stdout ---", flush=True)
                safe_print(result.stdout, flush=True)
            if result.stderr:
                safe_print("\n--- fMRIPrep stderr ---", flush=True)
                safe_print(result.stderr, flush=True)

            # Extract key error message from stderr
            error_detail = "fMRIPrep processing failed"
            if result.stderr:
                stderr_lines = result.stderr.split("\n")
                for line in reversed(stderr_lines):
                    line = line.strip()
                    if line and not line.startswith("[") and len(line) > 10:
                        error_detail = line[:200]
                        break
            if result.stdout and error_detail == "fMRIPrep processing failed":
                stdout_lines = result.stdout.split("\n")
                for line in reversed(stdout_lines):
                    line = line.strip()
                    if line and any(kw in line.lower() for kw in ["error", "failed", "exception"]):
                        error_detail = line[:200]
                        break

            # Report failure for every session of this subject
            for ses_id in session_ids:
                report.add_failure(sub_id, ses_id, error_detail, "fMRIPrep")

            error = f"{sub_label} (fMRIPrep failed: {error_detail[:100]})"

            if debug_log_file:
                safe_print(f"\n Full error details saved to: {debug_log_file}", flush=True)
        else:
            safe_print(
                f"[OK] {sub_label} - fMRIPrep completed ({fmriprep_elapsed:.1f}s)",
                flush=True,
            )
    except Exception as e:
        error = f"{sub_label} (fMRIPrep error: {e})"
        for ses_id in session_ids:
            report.add_failure(sub_id, ses_id, str(e), "fMRIPrep")
        safe_print(f"[FAIL] {sub_label} - fMRIPrep failed: {e}", flush=True)
        import traceback
        safe_print(f"Traceback:\n{traceback.format_exc()}", flush=True)

    return error


def cleanup_temp_files(bids_dir, report):
    """
    Clean up temporary files after conversion.
    
    Removes:
    - tmp_dcm2niix/ folder
    - Empty scans.tsv files
    
    Args:
        bids_dir: BIDS output directory
        report: ExecutionReport to update with cleanup info
    """
    safe_print("\nCleaning up temporary files...", flush=True)
    cleanup_count = 0
    cleanup_size = 0
    
    bids_path = Path(bids_dir)
    
    # 1. Remove tmp_dcm2niix folder
    tmp_folder = bids_path / "tmp_dcm2niix"
    if tmp_folder.exists():
        try:
            # Calculate size before deletion
            for f in tmp_folder.rglob('*'):
                if f.is_file():
                    cleanup_size += f.stat().st_size
            shutil.rmtree(tmp_folder)
            cleanup_count += 1
            safe_print(f"  Removed: tmp_dcm2niix/", flush=True)
        except Exception as e:
            warning = f"Could not remove tmp_dcm2niix folder: {e}"
            report.add_warning(warning)
            safe_print(f"  Warning: {warning}", flush=True)
    
    # 2. Remove empty scans.tsv files
    for scans_file in bids_path.rglob("*_scans.tsv"):
        try:
            content = scans_file.read_text()
            if content.count('\n') <= 1:
                scans_file.unlink()
                cleanup_count += 1
        except Exception:
            pass
    
    if cleanup_count > 0:
        size_mb = cleanup_size / (1024 * 1024)
        safe_print(f"  Cleaned up {cleanup_count} temporary items ({size_mb:.1f} MB freed)", flush=True)
        report.set_cleanup_info(cleanup_count, cleanup_size)
    else:
        safe_print("  No temporary files to clean up", flush=True)
        report.set_cleanup_info(0, 0)


def cleanup_work_dirs(output_folder, report):
    """Remove intermediate work directories from derivatives/."""
    safe_print("\nCleaning up intermediate work directories...", flush=True)
    cleanup_count = 0
    cleanup_size = 0
    output_path = Path(output_folder)

    mriqc_root = output_path / "derivatives" / "mriqc"
    targets = [
        mriqc_root / "work",       # nipype workflow cache (heaviest)
        mriqc_root / ".bids_db",   # BIDS layout SQLite index
        mriqc_root / "logs",       # MRIQC runtime logs
    ]

    for target in targets:
        if target.exists() and target.is_dir():
            try:
                for f in target.rglob('*'):
                    if f.is_file():
                        cleanup_size += f.stat().st_size
                shutil.rmtree(target)
                cleanup_count += 1
                rel = target.relative_to(output_path)
                safe_print(f"  Removed: {rel}/", flush=True)
            except Exception as e:
                safe_print(f"  Warning: Could not remove {target.name}/: {e}", flush=True)

    if cleanup_count > 0:
        size_mb = cleanup_size / (1024 * 1024)
        safe_print(f"  Freed {size_mb:.1f} MB from {cleanup_count} work dir(s)", flush=True)
    else:
        safe_print("  No work directories to clean up", flush=True)


def run_qc_only(output_folder: Path, run_mriqc: bool = False):
    """
    Run QC analysis only on an existing pipeline output folder.

    Expects the folder to contain:
      - sub-*/ses-*/ BIDS structure   (for BIDS quality checks)
      - derivatives/                  (for motion analysis)
      - derivatives/mriqc/            (for MRIQC IQM parsing, if available)

    Generates full_pipeline_report.html and prints a summary.
    """
    safe_print(f"\nRunning QC-only analysis on: {output_folder}", flush=True)
    safe_print("=" * 60, flush=True)

    if not output_folder.exists():
        safe_print(f"Error: folder does not exist: {output_folder}", flush=True)
        sys.exit(1)

    derivatives_dir = output_folder / "derivatives"

    # Discover subjects/sessions from BIDS structure
    sessions = []
    for sub_dir in sorted(output_folder.iterdir()):
        if not sub_dir.is_dir() or not sub_dir.name.startswith("sub-"):
            continue
        sub_id = sub_dir.name.replace("sub-", "")
        ses_dirs = sorted(d for d in sub_dir.iterdir() if d.is_dir() and d.name.startswith("ses-"))
        if ses_dirs:
            for ses_dir in ses_dirs:
                sessions.append((sub_id, ses_dir.name.replace("ses-", "")))
        else:
            sessions.append((sub_id, "01"))

    if not sessions:
        safe_print("No sub-*/ses-* structure found. Is this a valid BIDS output folder?", flush=True)
        sys.exit(1)

    safe_print(f"Found {len(sessions)} session(s) across {len({s[0] for s in sessions})} subject(s)", flush=True)

    # Layer 1: BIDS quality checks
    safe_print("\nRunning BIDS quality checks...", flush=True)
    qc_checker = BIDSQualityChecker()
    for sub_id, ses_id in sessions:
        findings = qc_checker.check_session(output_folder, sub_id, ses_id)
        n_err = sum(1 for f in findings if f.severity.value == "ERROR")
        n_warn = sum(1 for f in findings if f.severity.value == "WARNING")
        if n_err:
            safe_print(f"  [QC-ERROR] sub-{sub_id}/ses-{ses_id}: {n_err} error(s), {n_warn} warning(s)", flush=True)
            for f in findings:
                if f.severity.value == "ERROR":
                    safe_print(f"    - {f.message}", flush=True)
        elif n_warn:
            safe_print(f"  [QC-WARN]  sub-{sub_id}/ses-{ses_id}: {n_warn} warning(s)", flush=True)
        else:
            safe_print(f"  [QC-OK]    sub-{sub_id}/ses-{ses_id}", flush=True)

    # Layer 3: Motion analysis
    motion_results = []
    if derivatives_dir.exists():
        safe_print("\nAnalyzing motion from fMRIPrep confounds...", flush=True)
        motion_results = motion_parser.parse_all_subjects(derivatives_dir)
        if motion_results:
            rescans = [m for m in motion_results if m.flag == "RESCAN"]
            warns   = [m for m in motion_results if m.flag == "WARNING"]
            ok      = [m for m in motion_results if m.flag == "OK"]
            safe_print(
                f"  Motion: {len(ok)} OK, {len(warns)} warning(s), {len(rescans)} re-scan flag(s)",
                flush=True,
            )
            for m in rescans:
                safe_print(
                    f"  [MOTION-RESCAN] sub-{m.sub_id}/ses-{m.ses_id} [{m.run_label}]: "
                    f"mean FD={m.mean_fd:.2f}mm, {m.pct_high_motion:.0f}% high-motion frames",
                    flush=True,
                )
        else:
            safe_print("  No confounds files found in derivatives/.", flush=True)
    else:
        safe_print("\nNo derivatives/ folder found — skipping motion analysis.", flush=True)

    # Layer 4: Connectivity QC (optional)
    connectivity_results = []
    # Check if --connectivity-qc was requested
    try:
        import sys
        if '--connectivity-qc' in sys.argv and derivatives_dir.exists():
            try:
                from .qc import CONNECTIVITY_QC_AVAILABLE, connectivity_qc
            except ImportError:
                from qc import CONNECTIVITY_QC_AVAILABLE, connectivity_qc

            if CONNECTIVITY_QC_AVAILABLE:
                safe_print("\nRunning connectivity quality assessment (scrubbing strategy)...", flush=True)
                connectivity_results = connectivity_qc.analyze_all_subjects(
                    derivatives_dir,
                    output_folder,
                    atlas='schaefer_116_tian',
                    mni_space=_pick_mni_space([])
                )
                if connectivity_results:
                    failed = [r for r in connectivity_results if r.worst_severity == "ERROR"]
                    warned = [r for r in connectivity_results if r.worst_severity == "WARNING"]
                    safe_print(
                        f"    {len(connectivity_results)} runs analyzed, "
                        f"{len(failed)} failed, {len(warned)} warning(s)",
                        flush=True,
                    )
            else:
                safe_print("\nConnectivity QC skipped (Nilearn not installed)", flush=True)
    except Exception as e:
        safe_print(f"\nConnectivity QC skipped (error: {e})", flush=True)

    # MRIQC IQM parsing (if mriqc/ folder exists)
    iqm_results = []
    mriqc_reports = {}
    mriqc_dir = output_folder / "derivatives" / "mriqc"
    if mriqc_dir.exists():
        safe_print("\nParsing MRIQC IQM files...", flush=True)
        iqm_results = iqm_parser.parse_all_subjects(mriqc_dir)
        mriqc_reports = mriqc_runner.collect_mriqc_reports(mriqc_dir)
        if iqm_results:
            flagged = [r for r in iqm_results if r.worst_severity != "OK"]
            safe_print(
                f"  IQM: {len(iqm_results)} scan(s) parsed, {len(flagged)} with flag(s)",
                flush=True,
            )
            for r in flagged:
                for flag in r.flags:
                    safe_print(
                        f"  [IQM-{flag.severity}] sub-{flag.sub_id} "
                        f"{flag.modality}: {flag.metric_label} = {flag.value:.3f}",
                        flush=True,
                    )
        else:
            safe_print("  No IQM JSON files found in mriqc/.", flush=True)

    # Collect fMRIPrep coregistration figures
    coreg_plots = _collect_coreg_plots(derivatives_dir)
    if coreg_plots:
        safe_print(f"  Found {len(coreg_plots)} coregistration overlay(s)", flush=True)

    # HTML QC report
    html_path = generate_html_report(
        str(output_folder),
        qc_checker.get_all(),
        motion_results,
        [],
        [],
        iqm_results=iqm_results,
        mriqc_reports=mriqc_reports,
        connectivity_results=connectivity_results,
        coreg_plots=coreg_plots,
    )
    safe_print(f"\nQC report saved to: {html_path}", flush=True)

    # Summary
    all_errors = qc_checker.get_errors()
    all_rescans = [m for m in motion_results if m.flag == "RESCAN"]
    safe_print("\n" + "=" * 60, flush=True)
    if all_errors or all_rescans:
        safe_print(
            f"QC COMPLETE — {len(all_errors)} scan error(s), {len(all_rescans)} motion re-scan flag(s)",
            flush=True,
        )
        safe_print("Open full_pipeline_report.html for full details.", flush=True)
        sys.exit(1)
    else:
        safe_print("QC COMPLETE — No critical issues found.", flush=True)
        safe_print("Open full_pipeline_report.html for full details.", flush=True)
        sys.exit(0)


def main():
    """Main entry point for the pipeline."""
    parser = argparse.ArgumentParser(
        description="fMRI Master Pipeline: BIDS Conversion + fMRIPrep",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all subjects (parallel)
  python -m src.pipeline --input /data/raw --output_dir /data/processed

  # Process single subject
  python -m src.pipeline --input /data/raw/001/MRI1 --output_dir /data/processed --subject 001 --session 01

  # Run fMRIPrep only on existing BIDS folder
  python -m src.pipeline --bids-folder /data/processed/output_20250101_120000

  # Run QC analysis only on an existing output folder (no re-processing)
  python -m src.orchestrator --qc-only --bids-folder /data/processed/output_20250101_120000
        """
    )
    
    # Auto-detect optimal parallel workers
    cpu_count = multiprocessing.cpu_count()
    default_workers = min(max(cpu_count, 4), 12)
    
    parser.add_argument("--input", 
                        help="Path to root directory containing subject folders (required unless --bids-folder is used)")
    parser.add_argument("--output_dir", 
                        help="Base directory for outputs (required unless --bids-folder is used)")
    parser.add_argument("--bids-folder",
                        help="Path to existing BIDS folder (for running fMRIPrep only, skips BIDS conversion)")
    parser.add_argument("--subject", 
                        help="Specific subject ID (optional)")
    parser.add_argument("--session", 
                        help="Specific session ID (optional, use with --subject)")
    parser.add_argument("--skip-bids", action="store_true", 
                        help="Skip BIDS conversion step")
    parser.add_argument("--skip-fmriprep", action="store_true", 
                        help="Skip fMRIPrep preprocessing step")
    parser.add_argument("--parallel", type=int, default=default_workers, 
                        help=f"Number of parallel workers (default: {default_workers})")
    parser.add_argument("--anonymize", action="store_true", 
                        help="Enable DICOM metadata anonymization")
    parser.add_argument("--keep-temp", action="store_true",
                        help="Keep temporary files for debugging (don't cleanup)")
    parser.add_argument("--fmriprep-opts", type=str, default="",
                        help="Base64-encoded JSON fMRIPrep options (platform-agnostic)")
    parser.add_argument("--skip-mriqc", action="store_true",
                        help="Skip MRIQC image quality assessment (runs by default)")
    parser.add_argument("--connectivity-qc", action="store_true",
                        help="Run connectivity quality assessment (requires nilearn, analyzes motion-connectivity coupling)")
    parser.add_argument("--qc-only", action="store_true",
                        help="Run QC analysis only on an existing output folder (use with --bids-folder)")
    parser.add_argument("--researcher-comments", type=str, default="",
                        help="Base64-encoded researcher comments (free text)")
    parser.add_argument("--qc-thresholds", type=str, default="",
                        help="Base64-encoded JSON with QC threshold overrides")
    parser.add_argument("--mriqc-keep-work", action="store_true",
                        help="Mount MRIQC work dir on host (enables resume of failed runs; "
                             "default: work stays in container and is discarded on exit)")

    args = parser.parse_args()

    # Apply QC threshold overrides (before any QC code runs)
    if args.qc_thresholds:
        try:
            qc_overrides = json.loads(
                base64.b64decode(args.qc_thresholds).decode('utf-8')
            )
            iqm_parser.apply_overrides(qc_overrides)
            motion_parser.apply_overrides(qc_overrides)
            connectivity_thresholds.apply_overrides(qc_overrides)
            safe_print("Applied custom QC threshold overrides.", flush=True)
        except Exception as e:
            safe_print(f"Warning: Could not apply QC threshold overrides: {e}", flush=True)

    # QC-only mode: analyse an existing output folder, no re-processing
    if args.qc_only:
        if not args.bids_folder:
            safe_print("Error: --qc-only requires --bids-folder <path/to/output_folder>", flush=True)
            sys.exit(1)
        run_qc_only(Path(args.bids_folder).resolve(), run_mriqc=not getattr(args, 'skip_mriqc', False))
        return  # run_qc_only calls sys.exit(), but return as safety

    # Validate arguments
    fmriprep_only_mode = bool(args.bids_folder)
    
    if fmriprep_only_mode:
        # Using existing BIDS folder - skip BIDS conversion, run fMRIPrep only
        bids_folder_path = Path(args.bids_folder).resolve()
        if not bids_folder_path.exists():
            safe_print(f"Error: BIDS folder does not exist: {bids_folder_path}", flush=True)
            sys.exit(1)
        
        # Check for dataset_description.json (case-insensitive on Windows)
        desc_path = bids_folder_path / "dataset_description.json"
        if not desc_path.exists():
            # On Windows, check case-insensitively
            if sys.platform == 'win32':
                found = False
                try:
                    for item in bids_folder_path.iterdir():
                        if item.is_file() and item.name.lower() == "dataset_description.json":
                            found = True
                            safe_print(f"Found dataset_description.json (case variant: {item.name})", flush=True)
                            break
                except Exception as e:
                    safe_print(f"Warning: Could not check for dataset_description.json: {e}", flush=True)
                
                if not found:
                    safe_print(f"Warning: dataset_description.json not found. Will create it...", flush=True)
            else:
                safe_print(f"Warning: dataset_description.json not found. Will create it...", flush=True)
        
        # Force skip-bids in this mode
        args.skip_bids = True
    else:
        # Standard mode - require input and output_dir
        if not args.input or not args.output_dir:
            safe_print("Error: --input and --output_dir are required (unless using --bids-folder)", flush=True)
            sys.exit(1)

    # Setup Paths
    project_root = Path(__file__).parent.parent.resolve()
    
    if fmriprep_only_mode:
        # Use existing BIDS folder directly
        bids_dir = bids_folder_path
        derivatives_dir = bids_dir / "derivatives"
        output_folder = bids_dir
        input_root = bids_dir  # For report
        
        # Create dataset_description.json if missing (for incomplete conversions)
        if not (bids_dir / "dataset_description.json").exists():
            safe_print(f"Creating dataset_description.json in {bids_dir}...", flush=True)
            if create_dataset_description(bids_dir):
                safe_print("Created dataset_description.json", flush=True)
            else:
                # Check if it exists now (might have been created by another process)
                if (bids_dir / "dataset_description.json").exists():
                    safe_print("dataset_description.json now exists", flush=True)
                else:
                    safe_print(f"Warning: Could not create dataset_description.json", flush=True)
    else:
        input_root = Path(args.input).resolve()
    base_output = Path(args.output_dir).resolve()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_folder = base_output / f"output_{timestamp}"
    output_folder.mkdir(parents=True, exist_ok=True)
    
    # BIDS output goes directly in output folder
    bids_dir = output_folder
    derivatives_dir = output_folder / "derivatives"
    
    fmriprep_script = project_root / "src" / "fmriprep" / "runner.py"
    
    # Create debug log file for detailed error tracking (in derivatives/, not the BIDS root,
    # so the BIDS validator does not flag it as an unrecognised file)
    derivatives_dir.mkdir(parents=True, exist_ok=True)
    debug_log_file = None
    if not args.skip_fmriprep:
        debug_log_file = derivatives_dir / "fmriprep_debug.log"
        if debug_log_file.exists():
            debug_log_file.unlink()  # Remove old log if exists
        debug_log_file.write_text(f"fMRIPrep Debug Log\n{'='*80}\nTimestamp: {datetime.now().isoformat()}\n{'='*80}\n\n", encoding='utf-8')
        safe_print(f"Debug log: {debug_log_file}", flush=True)

    # Execution logs folder — keeps both the raw and structured logs together
    logs_folder = output_folder / "execution_logs"
    logs_folder.mkdir(parents=True, exist_ok=True)

    # Start raw execution log — mirrors all safe_print() output to disk
    execution_log = logs_folder / "raw_execution_log.log"
    set_log_file(execution_log)
    safe_print(f"Execution logs: {logs_folder}", flush=True)

    # Decode researcher comments (base64-encoded from GUI, or plain text from CLI)
    # and seed the comments file.  The GUI (or user) may update this file while
    # the pipeline runs; reports will re-read it just before generation.
    researcher_comments_initial = args.researcher_comments or ""
    if researcher_comments_initial:
        try:
            researcher_comments_initial = base64.b64decode(
                researcher_comments_initial.encode('ascii')
            ).decode('utf-8')
        except Exception:
            pass  # Not base64 — use as-is (plain text from CLI)
    # Seed the comments file so that even CLI-provided comments are stored
    comments_file = logs_folder / ".researcher_comments.txt"
    try:
        comments_file.write_text(researcher_comments_initial, encoding="utf-8")
    except Exception:
        pass

    # Initialize report
    report = ExecutionReport()
    report.input_folder = str(input_root)
    report.output_folder = str(output_folder)
    report.skip_bids = args.skip_bids
    report.skip_fmriprep = args.skip_fmriprep
    report.set_researcher_comments(researcher_comments_initial)
    
    safe_print(f"Output folder: {output_folder}", flush=True)
    
    if fmriprep_only_mode:
        safe_print("Mode: fMRIPrep only (using existing BIDS data)", flush=True)

    # Add local dcm2niix to PATH if available
    local_dcm2niix_dir = project_root / "tools" / "dcm2niix"
    if local_dcm2niix_dir.exists():
        os.environ["PATH"] = str(local_dcm2niix_dir) + os.pathsep + os.environ.get("PATH", "")
    
    # Handle anonymization
    anonymize = args.anonymize
    if anonymize:
        safe_print("Anonymization enabled - patient info will be removed from metadata", flush=True)

    # Build task list
    tasks = []
    
    if fmriprep_only_mode:
        # Discover subjects/sessions from existing BIDS folder structure
        safe_print(f"Scanning BIDS folder {bids_dir} for subjects...", flush=True)
        
        for sub_dir in sorted(bids_dir.iterdir()):
            if not sub_dir.is_dir() or not sub_dir.name.startswith("sub-"):
                continue
            
            sub_id = sub_dir.name.replace("sub-", "")
            sessions = []
            
            # Check for session folders
            for ses_dir in sorted(sub_dir.iterdir()):
                if ses_dir.is_dir() and ses_dir.name.startswith("ses-"):
                    ses_id = ses_dir.name.replace("ses-", "")
                    sessions.append(ses_id)
            
            # If no session folders, treat as single session
            if not sessions:
                sessions = ["01"]  # Default session
            
            safe_print(f"  Found subject {sub_id} with {len(sessions)} session(s)", flush=True)
            
            for ses_id in sessions:
                tasks.append({
                    "sub_id": sub_id,
                    "ses_id": ses_id,
                    "dicom_path": None  # Not needed for fMRIPrep-only mode
                })
    elif args.subject and args.session:
        tasks.append({
            "sub_id": sanitize_id(args.subject),
            "ses_id": args.session,
            "dicom_path": input_root
        })
    elif args.subject:
        sub_id = sanitize_id(args.subject)
        sessions = find_sessions(input_root)
        for ses_id, ses_path in sessions:
            tasks.append({
                "sub_id": sub_id,
                "ses_id": ses_id,
                "dicom_path": ses_path
            })
    else:
        safe_print(f"Scanning {input_root} for subjects...", flush=True)
        
        for sub_dir in find_subject_folders(input_root):
            sub_id = sanitize_id(sub_dir.name)
            if not sub_id:
                safe_print(f"  Skipping invalid folder name: {sub_dir.name}", flush=True)
                continue
            
            sessions = find_sessions(sub_dir)
            safe_print(f"  Found subject {sub_id} with {len(sessions)} session(s)", flush=True)
            
            for ses_id, ses_path in sessions:
                if has_dicom_files(ses_path):
                    tasks.append({
                        "sub_id": sub_id,
                        "ses_id": ses_id,
                        "dicom_path": ses_path
                    })
                else:
                    safe_print(f"    Warning: No DICOM files found in {ses_path}", flush=True)

    if not tasks:
        safe_print("No subjects/sessions found to process.", flush=True)
        sys.exit(0)

    # Group tasks by subject
    subjects_tasks = OrderedDict()
    for task in tasks:
        sub_id = task['sub_id']
        if sub_id not in subjects_tasks:
            subjects_tasks[sub_id] = []
        subjects_tasks[sub_id].append(task)
    
    # Add task numbers
    task_num = 0
    for sub_id in subjects_tasks:
        for task in subjects_tasks[sub_id]:
            task['task_num'] = task_num
            task_num += 1

    num_subjects = len(subjects_tasks)
    total_tasks = len(tasks)
    num_workers = min(args.parallel, total_tasks)
    
    report.total_tasks = total_tasks
    
    safe_print(f"\nTotal: {total_tasks} sessions across {num_subjects} subjects", flush=True)
    safe_print(f"Using {num_workers} parallel workers (max)", flush=True)
    safe_print(f"[PROGRESS:TOTAL:{total_tasks}]", flush=True)
    
    errors = []
    progress_tracker = ProgressTracker(total_tasks)
    desc_created_event = threading.Event()
    
    # Decode fMRIPrep options from base64 JSON (platform-agnostic)
    fmriprep_opts = {}
    if hasattr(args, 'fmriprep_opts') and args.fmriprep_opts:
        try:
            json_str = base64.b64decode(args.fmriprep_opts).decode('utf-8')
            fmriprep_opts = json.loads(json_str)
        except Exception as e:
            safe_print(f"Warning: Could not decode fMRIPrep options: {e}", flush=True)

    all_tasks = [task for sub_tasks in subjects_tasks.values() for task in sub_tasks]
    
    qc_checker = BIDSQualityChecker()
    run_mriqc = not getattr(args, 'skip_mriqc', False)
    mriqc_dir = output_folder / "derivatives" / "mriqc" if run_mriqc else None

    if run_mriqc:
        safe_print("Checking MRIQC prerequisites...", flush=True)
        ok, err = mriqc_runner.mriqc_preflight(callback=lambda m: safe_print(f"  {m}", flush=True))
        if not ok:
            safe_print(f"  MRIQC pre-flight failed: {err}", flush=True)
            safe_print("  Continuing without MRIQC.", flush=True)
            run_mriqc = False
            mriqc_dir = None

    # Track which sessions are missing BOLD data (needed for Phase 2).
    # Keyed by (sub_id, ses_id) — only sessions explicitly flagged are missing.
    sessions_missing_bold: set = set()

    # BOLD files to temporarily hide from fMRIPrep (shorter duplicates).
    # Collected during Phase 1 as a list of (nii_path, json_path) tuples.
    fmriprep_exclude_pairs: list = []

    # ------------------------------------------------------------------
    # Phase 1: BIDS conversion + QC  (parallel per session)
    # ------------------------------------------------------------------
    if not args.skip_bids:
        safe_print("\n=== Phase 1: BIDS Conversion ===", flush=True)
        report.record_phase_start("BIDS Conversion")
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = {
                executor.submit(
                    process_bids_task,
                    task, bids_dir, progress_tracker, desc_created_event,
                    report, anonymize, qc_checker
                ): task for task in all_tasks
            }

            for future in as_completed(futures):
                task = futures[future]
                sub_id = task['sub_id']
                try:
                    error, missing_bold, excluded_bold = future.result()
                    if error:
                        errors.append(error)
                    if missing_bold:
                        sessions_missing_bold.add((sub_id, task['ses_id']))
                    fmriprep_exclude_pairs.extend(excluded_bold)
                except Exception as e:
                    error_msg = f"sub-{task['sub_id']}/ses-{task['ses_id']} (Unexpected error: {e})"
                    errors.append(error_msg)
                    report.add_failure(task['sub_id'], task['ses_id'], str(e), "Unknown")
                    safe_print(
                        f"[FAIL] Unexpected error for sub-{task['sub_id']}/ses-{task['ses_id']}: {e}",
                        flush=True,
                    )

    # Hide shorter duplicate BOLD runs immediately after BIDS conversion.
    # This ensures consistency checks, MRIQC, and fMRIPrep only see the
    # final kept runs — preventing duplicate entries in reports.
    renamed_bold = []
    if fmriprep_exclude_pairs:
        from bids.converter import hide_excluded_bold
        renamed_bold = hide_excluded_bold(fmriprep_exclude_pairs)
        if renamed_bold:
            safe_print(
                f"  Hidden {len(renamed_bold)} duplicate BOLD file(s) "
                f"from further processing",
                flush=True,
            )

    # Cross-session run consistency check
    if not args.skip_bids:
        consistency_findings = qc_checker.check_run_consistency(bids_dir, subjects_tasks)
        if consistency_findings:
            safe_print(f"  Run consistency: {len(consistency_findings)} warning(s)", flush=True)
        report.record_phase_end("BIDS Conversion")

    # ------------------------------------------------------------------
    # Phase 2: MRIQC  (parallel per session — each session gets its own
    #                   Docker container so sessions run concurrently)
    # ------------------------------------------------------------------
    if run_mriqc and mriqc_dir is not None:
        report.record_phase_start("MRIQC")
        # Build (subject, session) pairs for per-session parallelism
        mriqc_tasks = []
        for sub_id, sub_tasks in subjects_tasks.items():
            seen_sessions = set()
            for t in sub_tasks:
                ses_id = t['ses_id']
                if ses_id not in seen_sessions:
                    seen_sessions.add(ses_id)
                    mriqc_tasks.append((sub_id, ses_id))

        safe_print(
            f"\n=== Phase 2: MRIQC ({len(mriqc_tasks)} session(s) across "
            f"{len(subjects_tasks)} subject(s)) ===",
            flush=True,
        )

        # Probe the Docker VM to learn its actual CPU / RAM limits.
        # On macOS Docker Desktop runs in a VM whose resources are often
        # much lower than the host — this is the #1 cause of slow MRIQC.
        docker_cpus, docker_mem_gb = mriqc_runner.get_docker_vm_resources()
        if docker_cpus is not None:
            safe_print(
                f"  Docker VM resources: {docker_cpus} CPUs, {docker_mem_gb} GB RAM",
                flush=True,
            )
            host_cpus = multiprocessing.cpu_count()
            if docker_cpus < host_cpus // 2:
                safe_print(
                    f"  WARNING: Docker only has {docker_cpus} of your {host_cpus} CPUs. "
                    f"Increase in Docker Desktop > Settings > Resources for faster runs.",
                    flush=True,
                )
            effective_cpus = docker_cpus
            effective_mem_gb = docker_mem_gb
        else:
            safe_print("  Could not detect Docker VM resources — using host values.", flush=True)
            effective_cpus = multiprocessing.cpu_count()
            # Estimate host memory (fallback to 16 GB)
            try:
                if sys.platform == "darwin":
                    import ctypes, ctypes.util
                    libc = ctypes.CDLL(ctypes.util.find_library("c"))
                    mem = ctypes.c_int64(0)
                    size = ctypes.c_size_t(ctypes.sizeof(mem))
                    libc.sysctlbyname(b"hw.memsize", ctypes.byref(mem), ctypes.byref(size), None, 0)
                    effective_mem_gb = int(mem.value / (1024 ** 3))
                else:
                    effective_mem_gb = int(
                        os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024 ** 3)
                    )
            except Exception:
                effective_mem_gb = 16

        # Dynamic resource allocation: divide Docker VM resources among
        # concurrent MRIQC containers so they don't starve each other.
        mriqc_workers = min(args.parallel, len(mriqc_tasks))

        # Reserve ~20% for OS/Docker overhead, split the rest
        usable_cpus = max(int(effective_cpus * 0.8), 1)
        usable_mem_gb = effective_mem_gb * 0.8

        cpus_per = max(usable_cpus // max(mriqc_workers, 1), 1)
        mem_per = max(int(usable_mem_gb // max(mriqc_workers, 1)), 4)

        # Split per-container CPUs into nprocs (parallel scans) and
        # omp_nthreads (threads per scan).  More omp threads speeds up
        # the heavy per-scan computation (spatial normalization, IQMs).
        if cpus_per >= 4:
            nprocs_per = max(cpus_per // 2, 1)
            omp_per = max(cpus_per // nprocs_per, 1)
        else:
            nprocs_per = cpus_per
            omp_per = 1

        safe_print(
            f"  Per container: {nprocs_per} scan workflows x {omp_per} threads, "
            f"{mem_per} GB RAM ({mriqc_workers} parallel containers)",
            flush=True,
        )

        report.record_phase_start("  Participant-level")
        with ThreadPoolExecutor(max_workers=mriqc_workers) as executor:
            futures = {
                executor.submit(
                    mriqc_runner.run_mriqc_participant,
                    bids_dir, mriqc_dir, sub_id,
                    session_id=ses_id,
                    nprocs=nprocs_per,
                    omp_nthreads=omp_per,
                    mem_gb=mem_per,
                    no_work_dir=not args.mriqc_keep_work,
                ): (sub_id, ses_id) for sub_id, ses_id in mriqc_tasks
            }
            for future in as_completed(futures):
                sub_id, ses_id = futures[future]
                label = f"sub-{sub_id}/ses-{ses_id}"
                try:
                    ok, err = future.result()
                    if ok:
                        safe_print(f"[MRIQC] {label} - done", flush=True)
                    else:
                        safe_print(f"[MRIQC] {label} - warning: {err[:120]}", flush=True)
                        report.add_warning(f"MRIQC failed for {label}: {err[:120]}")
                except Exception as e:
                    safe_print(f"[MRIQC] {label} - error: {e}", flush=True)
                    report.add_warning(f"MRIQC error for {label}: {e}")
        report.record_phase_end("  Participant-level")

    # ------------------------------------------------------------------
    # Early MRIQC report — available before fMRIPrep starts
    # ------------------------------------------------------------------
    if run_mriqc and mriqc_dir is not None:
        report.record_phase_start("  Group report")
        safe_print("Running MRIQC group-level report...", flush=True)
        grp_ok, grp_err = mriqc_runner.run_mriqc_group(
            bids_dir, mriqc_dir, no_work_dir=not args.mriqc_keep_work,
            experiment_dir=base_output,
        )
        if grp_ok:
            safe_print(
                f"  Group reports: {mriqc_dir}/group_T1w.html, group_bold.html",
                flush=True,
            )
        else:
            safe_print(f"  MRIQC group warning: {grp_err[:120]}", flush=True)

        early_iqm = iqm_parser.parse_all_subjects(mriqc_dir)
        early_reports = mriqc_runner.collect_mriqc_reports(mriqc_dir)
        if early_iqm:
            flagged = [r for r in early_iqm if r.worst_severity != "OK"]
            safe_print(
                f"  IQM: {len(early_iqm)} scan(s) analysed, {len(flagged)} with flag(s)",
                flush=True,
            )

        mriqc_report_path = generate_mriqc_report(
            str(mriqc_dir), early_iqm, early_reports,
            qc_findings=qc_checker.get_all(),
            output_folder=str(output_folder),
            researcher_comments=_read_researcher_comments(output_folder),
        )
        safe_print(f"\n  MRIQC report ready: {mriqc_report_path}", flush=True)
        safe_print("  >>> Supervisor can review this now while fMRIPrep runs <<<", flush=True)
        report.record_phase_end("  Group report")
        report.record_phase_end("MRIQC")

        # Clean MRIQC work dir to free disk space before fMRIPrep
        if not args.keep_temp:
            cleanup_work_dirs(output_folder, report)

    # ------------------------------------------------------------------
    # Create .bidsignore before fMRIPrep (defense-in-depth for BIDS validator)
    # ------------------------------------------------------------------
    bidsignore_path = Path(bids_dir) / ".bidsignore"
    if not bidsignore_path.exists():
        try:
            bidsignore_path.write_text("derivatives/\nmriqc/\nexecution_logs/\n*.log\n")
        except Exception as e:
            safe_print(f"Warning: Could not create .bidsignore: {e}", flush=True)

    # ------------------------------------------------------------------
    # Phase 3: fMRIPrep  (once per subject, parallel across subjects)
    # ------------------------------------------------------------------
    if not args.skip_fmriprep:
        # When skip_bids is set, determine BOLD availability from existing BIDS data
        if args.skip_bids:
            for sub_id, sub_tasks in subjects_tasks.items():
                for t in sub_tasks:
                    ses_id = t['ses_id']
                    ses_path = Path(bids_dir) / f"sub-{sub_id}" / f"ses-{ses_id}" / "func"
                    if not ses_path.exists() or not list(ses_path.glob("*bold.nii.gz")):
                        sessions_missing_bold.add((sub_id, ses_id))

        # Build per-subject work items, filtering out sessions without BOLD
        fmriprep_subjects = []
        for sub_id, sub_tasks in subjects_tasks.items():
            all_session_ids = [t['ses_id'] for t in sub_tasks]
            bold_session_ids = [
                ses_id for ses_id in all_session_ids
                if (sub_id, ses_id) not in sessions_missing_bold
            ]
            skipped_session_ids = [
                ses_id for ses_id in all_session_ids
                if (sub_id, ses_id) in sessions_missing_bold
            ]

            for ses_id in skipped_session_ids:
                safe_print(
                    f"[SKIP] sub-{sub_id}/ses-{ses_id} - Skipping fMRIPrep (no BOLD images found)",
                    flush=True,
                )
                report.add_failure(
                    sub_id, ses_id,
                    "No BOLD images \u2014 fMRIPrep requires BOLD data", "fMRIPrep"
                )

            if bold_session_ids:
                fmriprep_subjects.append((sub_id, bold_session_ids))

        if fmriprep_subjects:
            report.record_phase_start("fMRIPrep")
            safe_print(f"\n=== Phase 3: fMRIPrep ({len(fmriprep_subjects)} subject(s)) ===", flush=True)
            safe_print(f"[PROGRESS:TOTAL:{len(fmriprep_subjects)}]", flush=True)

            fmriprep_workers = min(args.parallel, len(fmriprep_subjects))
            with ThreadPoolExecutor(max_workers=fmriprep_workers) as executor:
                futures = {
                    executor.submit(
                        run_fmriprep_for_subject,
                        sub_id, session_ids, bids_dir, derivatives_dir,
                        fmriprep_script, fmriprep_opts, report, debug_log_file
                    ): sub_id for sub_id, session_ids in fmriprep_subjects
                }

                for future in as_completed(futures):
                    sub_id = futures[future]
                    try:
                        error = future.result()
                        if error:
                            errors.append(error)
                    except Exception as e:
                        error_msg = f"sub-{sub_id} (Unexpected fMRIPrep error: {e})"
                        errors.append(error_msg)
                        for t in subjects_tasks[sub_id]:
                            report.add_failure(sub_id, t['ses_id'], str(e), "fMRIPrep")
                        safe_print(
                            f"[FAIL] Unexpected error for sub-{sub_id}: {e}",
                            flush=True,
                        )
            report.record_phase_end("fMRIPrep")

    safe_print(f"[PROGRESS:COMPLETE]", flush=True)

    # Restore hidden duplicate BOLD files so the final BIDS directory
    # contains all original files (both kept and excluded runs).
    if renamed_bold:
        from bids.converter import restore_excluded_bold
        restore_excluded_bold(renamed_bold)
        safe_print(
            f"  Restored {len(renamed_bold)} hidden BOLD file(s)",
            flush=True,
        )

    # Cleanup (skip if --keep-temp was specified)
    if args.keep_temp:
        safe_print("\nKeeping temporary files for debugging (--keep-temp)", flush=True)
        report.set_cleanup_info(0, 0)
    else:
        cleanup_temp_files(bids_dir, report)
        cleanup_work_dirs(output_folder, report)
    
    # Analyze output
    safe_print("Analyzing output files...", flush=True)
    output_stats = count_output_files(bids_dir)
    report.set_output_stats(output_stats)
    
    if output_stats['total_nifti'] > 0:
        safe_print(f"  Found {output_stats['total_nifti']} NIfTI files:", flush=True)
        if output_stats['anat'] > 0:
            safe_print(f"    - Anatomical (anat): {output_stats['anat']}", flush=True)
        if output_stats['func'] > 0:
            safe_print(f"    - Functional (func): {output_stats['func']}", flush=True)
        if output_stats['dwi'] > 0:
            safe_print(f"    - Diffusion (dwi): {output_stats['dwi']}", flush=True)
        if output_stats['fmap'] > 0:
            safe_print(f"    - Fieldmaps (fmap): {output_stats['fmap']}", flush=True)
    
    # Layer 3: Parse fMRIPrep confounds for motion analysis
    motion_results = []
    if not args.skip_fmriprep:
        report.record_phase_start("Motion Analysis")
        safe_print("Analyzing motion from fMRIPrep confounds...", flush=True)
        motion_results = motion_parser.parse_all_subjects(derivatives_dir)
        if motion_results:
            rescans = [m for m in motion_results if m.flag == "RESCAN"]
            warns = [m for m in motion_results if m.flag == "WARNING"]
            ok = [m for m in motion_results if m.flag == "OK"]
            safe_print(
                f"  Motion: {len(ok)} OK, {len(warns)} warning(s), {len(rescans)} re-scan flag(s)",
                flush=True,
            )
            for m in rescans:
                safe_print(
                    f"  [MOTION-RESCAN] sub-{m.sub_id}/ses-{m.ses_id} [{m.run_label}]: "
                    f"mean FD={m.mean_fd:.2f}mm, {m.pct_high_motion:.0f}% high-motion frames",
                    flush=True,
                )
        else:
            safe_print("  No confounds files found (fMRIPrep may not have completed).", flush=True)
        report.record_phase_end("Motion Analysis")

    # Layer 4: Connectivity QC (runs automatically when fMRIPrep output exists)
    connectivity_results = []
    if not args.skip_fmriprep:
        try:
            from .qc import CONNECTIVITY_QC_AVAILABLE, connectivity_qc
        except ImportError:
            from qc import CONNECTIVITY_QC_AVAILABLE, connectivity_qc

        if CONNECTIVITY_QC_AVAILABLE:
            report.record_phase_start("Connectivity QC")
            safe_print("Running connectivity quality assessment (scrubbing strategy)...", flush=True)
            connectivity_results = connectivity_qc.analyze_all_subjects(
                derivatives_dir,
                bids_dir,
                atlas='schaefer_116_tian',
                mni_space=_pick_mni_space(fmriprep_opts.get("output_spaces", []))
            )
            if connectivity_results:
                failed = [r for r in connectivity_results if r.worst_severity == "ERROR"]
                warned = [r for r in connectivity_results if r.worst_severity == "WARNING"]
                ok_conn = [r for r in connectivity_results if r.worst_severity == "OK"]
                safe_print(
                    f"    Connectivity: {len(ok_conn)} OK, {len(warned)} warning(s), {len(failed)} failed",
                    flush=True,
                )
                for r in failed:
                    safe_print(
                        f"    [CONN-ERROR] sub-{r.sub_id}/ses-{r.ses_id} [{r.run_label}]: "
                        f"FD={r.mean_fd:.2f}mm, {r.pct_censored:.0f}% censored, {r.usable_minutes:.1f}min usable",
                        flush=True,
                    )
            report.record_phase_end("Connectivity QC")
        else:
            safe_print("  Connectivity QC skipped (Nilearn not installed)", flush=True)
            safe_print("  Install with: pip install nilearn nibabel", flush=True)

    # MRIQC IQM parsing (for final comprehensive report)
    # Group report already generated after early MRIQC phase —
    # just re-parse IQM files for the final comprehensive report.
    iqm_results = []
    mriqc_reports = {}
    if run_mriqc and mriqc_dir is not None:
        iqm_results = iqm_parser.parse_all_subjects(mriqc_dir)
        mriqc_reports = mriqc_runner.collect_mriqc_reports(mriqc_dir)
        if iqm_results:
            flagged = [r for r in iqm_results if r.worst_severity != "OK"]
            safe_print(
                f"  IQM: {len(iqm_results)} scan(s) analysed, "
                f"{len(flagged)} with flag(s)",
                flush=True,
            )
            for r in flagged:
                for flag in r.flags:
                    safe_print(
                        f"  [IQM-{flag.severity}] sub-{flag.sub_id} "
                        f"{flag.modality}: {flag.metric_label} = {flag.value:.3f}",
                        flush=True,
                    )

    # Attach QC + motion to the report
    report.set_qc_results(qc_checker.get_all(), motion_results)

    # Collect fMRIPrep coregistration figures
    coreg_plots = _collect_coreg_plots(derivatives_dir)
    if coreg_plots:
        safe_print(f"  Found {len(coreg_plots)} coregistration overlay(s)", flush=True)

    # Layer 5: Generate HTML QC report
    # Only generate the full pipeline report when fMRIPrep actually ran;
    # when fMRIPrep is skipped the early MRIQC report is sufficient.
    report.record_phase_start("Report Generation")

    # Re-read researcher comments right before report generation so the
    # user's latest edits (made while the pipeline was running) are included.
    researcher_comments = _read_researcher_comments(output_folder)
    report.set_researcher_comments(researcher_comments)

    if not args.skip_fmriprep:
        html_path = generate_html_report(
            str(output_folder),
            qc_checker.get_all(),
            motion_results,
            report.successful,
            report.failed,
            iqm_results=iqm_results,
            mriqc_reports=mriqc_reports,
            connectivity_results=connectivity_results,
            researcher_comments=researcher_comments,
            coreg_plots=coreg_plots,
        )
        safe_print(f"QC report: {html_path}", flush=True)

    # Save report
    report_text = report.generate_report()
    report_path = output_folder / "execution_report.txt"
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_text)
        safe_print(f"\nExecution report saved to: {report_path}", flush=True)
    except Exception as e:
        safe_print(f"Warning: Could not save report: {e}", flush=True)
    report.record_phase_end("Report Generation")
    
    # Structured summary — separate file alongside the raw log
    _write_structured_summary(
        summary_path=logs_folder / "execution_logs_summary.txt",
        report=report,
        subjects_tasks=subjects_tasks,
        sessions_missing_bold=sessions_missing_bold,
        motion_results=motion_results,
        connectivity_results=connectivity_results,
        errors=errors,
        pipeline_start_time=report.start_time,
        iqm_results=iqm_results,
        ran_fmriprep=not args.skip_fmriprep,
        ran_mriqc=run_mriqc,
    )

    # Summary
    safe_print("\n" + "=" * 60, flush=True)
    safe_print(f"Output saved to: {output_folder}", flush=True)
    if errors:
        safe_print("PIPELINE COMPLETED WITH ERRORS:", flush=True)
        for err in errors:
            safe_print(f"  [X] {err}", flush=True)
        safe_print("=" * 60, flush=True)
        close_log_file()
        sys.exit(1)
    else:
        safe_print("[OK] All tasks completed successfully.", flush=True)
        safe_print("=" * 60, flush=True)
        close_log_file()
        sys.exit(0)


if __name__ == "__main__":
    main()

