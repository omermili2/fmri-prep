#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path
from collections import OrderedDict
import re
import json
import os
import io
import shutil
import threading
import multiprocessing
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Ensure UTF-8 output on all platforms (especially Windows)
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Thread-safe print lock
print_lock = threading.Lock()

def safe_print(*args, **kwargs):
    """Thread-safe print function."""
    with print_lock:
        print(*args, **kwargs)


def find_subject_folders(input_root):
    """Scans input directory for subject folders."""
    root = Path(input_root)
    if not root.exists():
        return []
    return [d for d in root.iterdir() if d.is_dir() and not d.name.startswith('.')]


def find_sessions(subject_path):
    """
    Finds session folders within a subject directory.
    
    Expected patterns:
      - MRI1, MRI2, MRI3 ...  → ses-01, ses-02, ses-03
      - ses-01, ses-02 ...    → ses-01, ses-02 (already BIDS-like)
      - session1, session2    → ses-01, ses-02
      - T1, T2, baseline, followup → ses-01, ses-02, etc.
    
    Returns list of tuples: (session_id, session_path)
    """
    sessions = []
    
    for d in sorted(subject_path.iterdir()):
        if not d.is_dir() or d.name.startswith('.'):
            continue
        
        name = d.name.lower()
        
        # Already BIDS format (ses-01, ses-02)
        if re.match(r'^ses-\d+$', d.name):
            ses_id = d.name.replace('ses-', '')
            sessions.append((ses_id, d))
        
        # MRI1, MRI2, etc.
        elif match := re.match(r'^mri(\d+)$', name):
            ses_id = match.group(1).zfill(2)
            sessions.append((ses_id, d))
        
        # session1, session_1, session-1
        elif match := re.match(r'^session[_-]?(\d+)$', name):
            ses_id = match.group(1).zfill(2)
            sessions.append((ses_id, d))
        
        # timepoint1, tp1
        elif match := re.match(r'^(?:timepoint|tp)[_-]?(\d+)$', name):
            ses_id = match.group(1).zfill(2)
            sessions.append((ses_id, d))
        
        # baseline, followup (assign sequential numbers)
        elif name in ['baseline', 'pre', 'screening']:
            sessions.append(('01', d))
        elif name in ['followup', 'post', 'followup1']:
            sessions.append(('02', d))
        elif name in ['followup2', 'post2']:
            sessions.append(('03', d))
        
        # scans folder directly under subject (single session)
        elif name == 'scans':
            sessions.append(('01', d))
        
        # Fallback: check if this dir contains DICOM-like subdirectories
        else:
            # Check if there are subdirs that might contain DICOMs
            subdirs = [x for x in d.iterdir() if x.is_dir()]
            if subdirs or any(f.suffix.lower() in ['.dcm', '.ima', '.gz'] for f in d.rglob('*') if f.is_file()):
                # Assume it's a session, assign sequential ID
                ses_num = str(len(sessions) + 1).zfill(2)
                sessions.append((ses_num, d))
    
    return sessions if sessions else [('01', subject_path)]  # Single session fallback


def sanitize_id(raw_id):
    """Sanitize ID to be BIDS-compliant (alphanumeric only)."""
    clean = raw_id
    
    # Remove common prefixes
    for prefix in ['sub-', 'sub', 'subject-', 'subject']:
        if clean.lower().startswith(prefix):
            clean = clean[len(prefix):]
            break
    
    # Keep only alphanumeric
    clean = re.sub(r'[^a-zA-Z0-9]', '', clean)
    return clean if clean else None


def has_dicom_files(path):
    """Check if a path contains DICOM files (directly or nested)."""
    dcm_patterns = ['*.dcm', '*.DCM', '*.ima', '*.IMA', '*.dcm.gz']
    for pattern in dcm_patterns:
        if list(Path(path).rglob(pattern)):
            return True
    return False


def count_output_files(bids_dir):
    """Count NIfTI files by scan type in the output directory."""
    stats = {
        'total_nifti': 0,
        'anat': 0,
        'func': 0,
        'dwi': 0,
        'fmap': 0,
        'other': 0,
        'subjects': set(),
        'sessions': set()
    }
    
    bids_path = Path(bids_dir)
    if not bids_path.exists():
        return stats
    
    for nii in bids_path.rglob('*.nii.gz'):
        stats['total_nifti'] += 1
        
        # Determine scan type from path
        path_parts = nii.parts
        if 'anat' in path_parts:
            stats['anat'] += 1
        elif 'func' in path_parts:
            stats['func'] += 1
        elif 'dwi' in path_parts:
            stats['dwi'] += 1
        elif 'fmap' in path_parts:
            stats['fmap'] += 1
        else:
            stats['other'] += 1
        
        # Track subjects and sessions
        for part in path_parts:
            if part.startswith('sub-'):
                stats['subjects'].add(part)
            elif part.startswith('ses-'):
                stats['sessions'].add(part)
    
    # Convert sets to counts
    stats['subject_count'] = len(stats['subjects'])
    stats['session_count'] = len(stats['sessions'])
    del stats['subjects']
    del stats['sessions']
    
    return stats


class ProgressTracker:
    """Thread-safe progress tracking."""
    def __init__(self, total):
        self.total = total
        self.completed = 0
        self.lock = threading.Lock()
    
    def increment(self):
        with self.lock:
            self.completed += 1
            count = self.completed
        safe_print(f"[PROGRESS:TASK:{count}]", flush=True)
        return count
    
    def task_start(self, task_num):
        safe_print(f"[PROGRESS:TASK_START:{task_num}]", flush=True)
    
    def get_completed_count(self):
        with self.lock:
            return self.completed


class ConversionReport:
    """Tracks conversion results for generating human-readable report."""
    def __init__(self):
        self.lock = threading.Lock()
        self.start_time = datetime.now()
        self.end_time = None
        self.successful = []  # List of {sub_id, ses_id, duration, details, output_files}
        self.failed = []      # List of {sub_id, ses_id, error, stage}
        self.warnings = []    # List of warning messages
        self.skipped = []     # List of skipped items with reasons
        self.total_tasks = 0
        self.config_file = None
        self.input_folder = None
        self.output_folder = None
        self.skip_bids = False
        self.skip_fmriprep = False
        self.output_stats = {}  # Scan type counts
        self.cleanup_info = {}  # Info about cleanup
    
    def add_success(self, sub_id, ses_id, duration, details="", output_files=None):
        with self.lock:
            self.successful.append({
                'sub_id': sub_id, 
                'ses_id': ses_id, 
                'duration': duration,
                'details': details,
                'output_files': output_files or []
            })
    
    def add_failure(self, sub_id, ses_id, error, stage="BIDS"):
        with self.lock:
            self.failed.append({
                'sub_id': sub_id, 
                'ses_id': ses_id, 
                'error': str(error),
                'stage': stage
            })
    
    def add_skipped(self, sub_id, ses_id, reason):
        with self.lock:
            self.skipped.append({
                'sub_id': sub_id,
                'ses_id': ses_id,
                'reason': reason
            })
    
    def add_warning(self, message):
        with self.lock:
            self.warnings.append(message)
    
    def set_output_stats(self, stats):
        """Set scan type statistics after scanning output."""
        with self.lock:
            self.output_stats = stats
    
    def set_cleanup_info(self, count, size_bytes):
        """Set information about cleanup."""
        with self.lock:
            self.cleanup_info = {'count': count, 'size': size_bytes}
    
    def finalize(self):
        self.end_time = datetime.now()
    
    def _simplify_error(self, error):
        """Convert technical errors to user-friendly messages."""
        error_lower = error.lower()
        
        if 'no such file' in error_lower or 'not found' in error_lower:
            return "The input files could not be found. Please check if the DICOM folder exists."
        elif 'permission denied' in error_lower:
            return "The program doesn't have permission to access these files. Check folder permissions."
        elif 'timeout' in error_lower:
            return "The conversion took too long (over 30 minutes). The data might be very large or there may be an issue."
        elif 'no dicom' in error_lower or 'no valid' in error_lower:
            return "No valid DICOM files were found in this folder."
        elif 'disk' in error_lower or 'space' in error_lower:
            return "Not enough disk space to complete the conversion."
        elif 'memory' in error_lower:
            return "Not enough computer memory (RAM) available."
        elif 'dcm2niix' in error_lower:
            return "The DICOM to NIfTI converter encountered an issue. The scan may be incomplete or corrupted."
        elif len(error) > 100:
            return error[:100] + "... (see detailed error below)"
        else:
            return error
    
    def generate_report(self):
        """Generate a comprehensive human-readable report for non-technical users."""
        self.finalize()
        total_duration = (self.end_time - self.start_time).total_seconds()
        
        lines = []
        
        # Header with visual appeal
        lines.append("")
        lines.append("+" + "=" * 68 + "+")
        lines.append("|" + " " * 68 + "|")
        lines.append("|" + "BIDS CONVERSION REPORT".center(68) + "|")
        lines.append("|" + "fMRI Preprocessing Assistant".center(68) + "|")
        lines.append("|" + " " * 68 + "|")
        lines.append("+" + "=" * 68 + "+")
        lines.append("")
        
        # Date and time
        lines.append(f"  Generated: {self.end_time.strftime('%B %d, %Y at %I:%M %p')}")
        lines.append("")
        
        # ===== SUMMARY SECTION =====
        lines.append("-" * 70)
        lines.append("  SUMMARY")
        lines.append("-" * 70)
        lines.append("")
        
        success_count = len(self.successful)
        fail_count = len(self.failed)
        skip_count = len(self.skipped)
        
        # Big status box
        if fail_count == 0 and success_count > 0:
            lines.append("  +---------------------------------------------------------+")
            lines.append("  |                                                         |")
            lines.append("  |     SUCCESS! All your data was converted correctly.     |")
            lines.append("  |                                                         |")
            lines.append("  +---------------------------------------------------------+")
        elif fail_count > 0 and success_count > 0:
            lines.append("  +---------------------------------------------------------+")
            lines.append("  |                                                         |")
            lines.append("  |   PARTIAL SUCCESS - Some sessions had problems.         |")
            lines.append("  |   Please review the errors below.                       |")
            lines.append("  |                                                         |")
            lines.append("  +---------------------------------------------------------+")
        elif fail_count > 0 and success_count == 0:
            lines.append("  +---------------------------------------------------------+")
            lines.append("  |                                                         |")
            lines.append("  |   CONVERSION FAILED - No data was converted.            |")
            lines.append("  |   Please review the errors below for guidance.          |")
            lines.append("  |                                                         |")
            lines.append("  +---------------------------------------------------------+")
        else:
            lines.append("  +---------------------------------------------------------+")
            lines.append("  |                                                         |")
            lines.append("  |   NO DATA PROCESSED - Nothing was found to convert.     |")
            lines.append("  |                                                         |")
            lines.append("  +---------------------------------------------------------+")
        
        lines.append("")
        lines.append(f"  Scanning sessions processed:  {self.total_tasks}")
        lines.append(f"  Successfully converted:       {success_count}")
        if fail_count > 0:
            lines.append(f"  Failed (needs attention):     {fail_count}")
        if skip_count > 0:
            lines.append(f"  Skipped:                      {skip_count}")
        lines.append(f"  Total time:                   {self._format_duration(total_duration)}")
        
        if self.total_tasks > 0:
            success_rate = (success_count / self.total_tasks) * 100
            lines.append(f"  Success rate:                 {success_rate:.0f}%")
        lines.append("")
        
        # ===== WHAT WAS CREATED =====
        if success_count > 0:
            lines.append("-" * 70)
            lines.append("  YOUR CONVERTED DATA")
            lines.append("-" * 70)
            lines.append("")
            lines.append(f"  Output location:")
            lines.append(f"  {self.output_folder}")
            lines.append("")
            
            # Output statistics
            if self.output_stats and self.output_stats.get('total_nifti', 0) > 0:
                lines.append("  What was created:")
                lines.append("")
                lines.append(f"    {self.output_stats['total_nifti']} brain scan files (.nii.gz format)")
                if self.output_stats.get('anat', 0) > 0:
                    lines.append(f"      - {self.output_stats['anat']} anatomical scans (brain structure images)")
                if self.output_stats.get('func', 0) > 0:
                    lines.append(f"      - {self.output_stats['func']} functional scans (brain activity recordings)")
                if self.output_stats.get('dwi', 0) > 0:
                    lines.append(f"      - {self.output_stats['dwi']} diffusion scans (white matter imaging)")
                if self.output_stats.get('fmap', 0) > 0:
                    lines.append(f"      - {self.output_stats['fmap']} fieldmaps (distortion correction images)")
                lines.append("")
            
            # List successful conversions
            lines.append("  Sessions that were converted:")
            lines.append("")
            sorted_success = sorted(self.successful, key=lambda x: (x['sub_id'], x['ses_id']))
            for item in sorted_success:
                dur = self._format_duration(item['duration'])
                lines.append(f"    [OK] Subject {item['sub_id']}, Session {item['ses_id']} ({dur})")
            lines.append("")
        
        # ===== PROBLEMS / ERRORS =====
        if self.failed:
            lines.append("-" * 70)
            lines.append("  PROBLEMS THAT NEED ATTENTION")
            lines.append("-" * 70)
            lines.append("")
            lines.append("  The following sessions could NOT be converted:")
            lines.append("")
            
            sorted_failed = sorted(self.failed, key=lambda x: (x['sub_id'], x['ses_id']))
            for item in sorted_failed:
                lines.append(f"    [FAILED] Subject {item['sub_id']}, Session {item['ses_id']}")
                lines.append(f"             What went wrong: {self._simplify_error(item['error'])}")
                lines.append("")
            
            lines.append("  HOW TO FIX THESE PROBLEMS:")
            lines.append("")
            lines.append("    1. Check that DICOM files exist in the source folder")
            lines.append("    2. Make sure the files aren't corrupted (try opening one in a DICOM viewer)")
            lines.append("    3. Verify you have enough disk space (at least 2x the raw data size)")
            lines.append("    4. If problems persist, contact your lab's technical support")
            lines.append("")
        
        # ===== WARNINGS =====
        if self.warnings:
            lines.append("-" * 70)
            lines.append("  NOTES AND WARNINGS")
            lines.append("-" * 70)
            lines.append("")
            for warning in self.warnings:
                lines.append(f"    - {warning}")
            lines.append("")
        
        # ===== DATA FORMAT EXPLANATION =====
        if success_count > 0:
            lines.append("-" * 70)
            lines.append("  UNDERSTANDING YOUR OUTPUT FOLDER")
            lines.append("-" * 70)
            lines.append("")
            lines.append("  Your data is now in 'BIDS format' - a standard way to organize brain")
            lines.append("  imaging data. Here's what you'll find:")
            lines.append("")
            lines.append("    dataset_description.json")
            lines.append("        A file describing your dataset (required by BIDS)")
            lines.append("")
            lines.append("    sub-001/                    <- One folder per participant")
            lines.append("      ses-01/                   <- One folder per scanning session")
            lines.append("        anat/                   <- Structural brain images (T1, T2)")
            lines.append("          sub-001_ses-01_T1w.nii.gz     <- Compressed brain image")
            lines.append("          sub-001_ses-01_T1w.json       <- Scan parameters")
            lines.append("        func/                   <- Functional brain images (BOLD)")
            lines.append("          sub-001_ses-01_task-rest_bold.nii.gz")
            lines.append("          sub-001_ses-01_task-rest_bold.json")
            lines.append("")
            lines.append("    conversion_report.txt       <- This report file")
            lines.append("")
            lines.append("  File naming explained:")
            lines.append("    - sub-XXX: participant/subject ID")
            lines.append("    - ses-YY: session number (01, 02, etc.)")
            lines.append("    - T1w, T2w: type of anatomical scan")
            lines.append("    - bold: functional MRI data")
            lines.append("    - .nii.gz: compressed brain image format")
            lines.append("    - .json: metadata about the scan")
            lines.append("")
        
        # ===== NEXT STEPS =====
        lines.append("-" * 70)
        lines.append("  WHAT TO DO NEXT")
        lines.append("-" * 70)
        lines.append("")
        
        step = 1
        if fail_count > 0:
            lines.append(f"  {step}. FIX THE FAILED CONVERSIONS (see problems section above)")
            step += 1
        
        if success_count > 0:
            lines.append(f"  {step}. VERIFY YOUR DATA")
            lines.append("     Open a few .nii.gz files in a viewer like FSLeyes or ITK-SNAP")
            lines.append("     to make sure the brain images look correct.")
            lines.append("")
            step += 1
            
            lines.append(f"  {step}. QUALITY CHECK")
            lines.append("     Run MRIQC on your data to check image quality before preprocessing.")
            lines.append("     Website: https://mriqc.readthedocs.io/")
            lines.append("")
            step += 1
            
            lines.append(f"  {step}. PREPROCESS YOUR DATA")
            lines.append("     Use the 'Run Full Pipeline' button in the fMRI Preprocessing")
            lines.append("     Assistant to run fMRIPrep on your converted data.")
            lines.append("")
        
        # ===== TECHNICAL DETAILS =====
        lines.append("-" * 70)
        lines.append("  TECHNICAL DETAILS (for troubleshooting)")
        lines.append("-" * 70)
        lines.append("")
        lines.append(f"    Source folder:     {self.input_folder}")
        lines.append(f"    Output folder:     {self.output_folder}")
        lines.append(f"    Config file:       {self.config_file}")
        lines.append(f"    Started:           {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"    Finished:          {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"    Duration:          {self._format_duration(total_duration)}")
        
        if self.cleanup_info:
            size_mb = self.cleanup_info.get('size', 0) / (1024 * 1024)
            lines.append(f"    Temp files cleaned: {self.cleanup_info.get('count', 0)} ({size_mb:.1f} MB)")
        lines.append("")
        
        # Footer
        lines.append("+" + "=" * 68 + "+")
        lines.append("|" + "Report generated by fMRI Preprocessing Assistant".center(68) + "|")
        lines.append("|" + "For help, contact your lab's technical support".center(68) + "|")
        lines.append("+" + "=" * 68 + "+")
        lines.append("")
        
        return "\n".join(lines)
    
    def _format_duration(self, seconds):
        """Format duration in human-readable format."""
        if seconds < 60:
            return f"{seconds:.1f} seconds"
        elif seconds < 3600:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins} min {secs} sec"
        else:
            hours = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            return f"{hours} hr {mins} min"


def process_single_task(task, config_path, bids_dir, derivatives_dir, fmriprep_script, 
                        skip_bids, skip_fmriprep, progress_tracker, desc_created_event, report):
    """Process a single subject-session task. Returns error string or None."""
    sub_id = task['sub_id']
    ses_id = task['ses_id']
    dicom_path = task['dicom_path']
    task_num = task['task_num']
    task_label = f"sub-{sub_id}/ses-{ses_id}"
    
    safe_print(f"[{task_label}] Starting conversion...", flush=True)
    
    # Signal task start for progress tracking
    progress_tracker.task_start(task_num)
    
    error = None
    
    # 1. BIDS Conversion
    task_start_time = datetime.now()
    if not skip_bids:
        cmd_bids = [
            "dcm2bids",
            "-d", str(dicom_path),
            "-p", sub_id,
            "-s", ses_id,
            "-c", str(config_path),
            "-o", str(bids_dir),
            "--force_dcm2bids",  # Overwrite existing dcm2bids output
            "--clobber"  # Overwrite existing NIfTI files without prompting
        ]
        
        try:
            # Use subprocess.run with minimal output for speed
            result = subprocess.run(
                cmd_bids, 
                capture_output=True, 
                text=True, 
                encoding='utf-8', 
                errors='replace',
                timeout=1800  # 30 minute timeout per session
            )
            if result.returncode != 0:
                error_msg = result.stderr[:300] if result.stderr else "Unknown error"
                safe_print(f"[{task_label}] dcm2bids error: {error_msg[:100]}", flush=True)
                error = f"{task_label} (BIDS failed)"
                report.add_failure(sub_id, ses_id, error_msg, "BIDS Conversion")
                progress_tracker.increment()
                safe_print(f"[FAIL] {task_label} - BIDS conversion failed", flush=True)
                return error
            else:
                elapsed = (datetime.now() - task_start_time).total_seconds()
                report.add_success(sub_id, ses_id, elapsed)
                progress_tracker.increment()
                safe_print(f"[OK] {task_label} - BIDS completed ({elapsed:.1f}s)", flush=True)
            
            # Create dataset_description.json if missing (thread-safe)
            if not desc_created_event.is_set():
                desc_path = bids_dir / "dataset_description.json"
                with print_lock:
                    if not desc_path.exists() and not desc_created_event.is_set():
                        bids_dir.mkdir(parents=True, exist_ok=True)
                        desc_content = {
                            "Name": "fMRI Pipeline Output",
                            "BIDSVersion": "1.8.0",
                            "DatasetType": "raw",
                            "Authors": ["Pipeline"]
                        }
                        with open(desc_path, 'w', encoding='utf-8') as f:
                            json.dump(desc_content, f, indent=4)
                        desc_created_event.set()
                
        except subprocess.TimeoutExpired:
            error = f"{task_label} (Timeout - took longer than 30 minutes)"
            report.add_failure(sub_id, ses_id, "Conversion timed out after 30 minutes", "BIDS Conversion")
            progress_tracker.increment()
            safe_print(f"[FAIL] {task_label} - BIDS conversion timed out", flush=True)
            return error
        except subprocess.CalledProcessError as e:
            error = f"{task_label} (BIDS error)"
            report.add_failure(sub_id, ses_id, str(e), "BIDS Conversion")
            progress_tracker.increment()
            safe_print(f"[FAIL] {task_label} - BIDS conversion failed: {e}", flush=True)
            return error
        except Exception as e:
            error = f"{task_label} ({e})"
            report.add_failure(sub_id, ses_id, str(e), "BIDS Conversion")
            progress_tracker.increment()
            safe_print(f"[FAIL] {task_label} - BIDS conversion failed: {e}", flush=True)
            return error

    # 2. fMRIPrep (run per subject, not per session)
    if not skip_fmriprep:
        fmriprep_start_time = datetime.now()
        safe_print(f"[{task_label}] Running fMRIPrep...", flush=True)
        cmd_fmriprep = [
            sys.executable,
            str(fmriprep_script),
            str(bids_dir),
            str(derivatives_dir),
            sub_id
        ]
        
        try:
            result = subprocess.run(cmd_fmriprep, capture_output=True, text=True, encoding='utf-8', errors='replace')
            fmriprep_elapsed = (datetime.now() - fmriprep_start_time).total_seconds()
            if result.returncode != 0:
                safe_print(f"[FAIL] {task_label} - fMRIPrep failed", flush=True)
                report.add_failure(sub_id, ses_id, "fMRIPrep processing failed", "fMRIPrep")
                error = f"{task_label} (fMRIPrep failed)"
            else:
                safe_print(f"[OK] {task_label} - fMRIPrep completed ({fmriprep_elapsed:.1f}s)", flush=True)
        except Exception as e:
            error = f"{task_label} (fMRIPrep error: {e})"
            report.add_failure(sub_id, ses_id, str(e), "fMRIPrep")
            safe_print(f"[FAIL] {task_label} - fMRIPrep failed: {e}", flush=True)
    
    return error


def main():
    parser = argparse.ArgumentParser(
        description="fMRI Master Pipeline: BIDS Conversion + fMRIPrep",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all subjects (sequential)
  python run_pipeline.py --input /data/raw --output_dir /data/processed

  # Process all subjects with 4 parallel workers
  python run_pipeline.py --input /data/raw --output_dir /data/processed --parallel 4

  # Process single subject with specific session
  python run_pipeline.py --input /data/raw/110/MRI1 --output_dir /data/processed --subject 110 --session 01
        """
    )
    
    # Auto-detect optimal parallel workers
    # Use more aggressive parallelism: CPU count, max 12, min 4 (if available)
    cpu_count = multiprocessing.cpu_count()
    default_workers = min(max(cpu_count, 4), 12)
    
    parser.add_argument("--input", required=True, help="Path to root directory containing subject folders")
    parser.add_argument("--output_dir", required=True, help="Base directory for outputs")
    parser.add_argument("--config", default="dcm2bids_config.json", help="Path to dcm2bids config file")
    parser.add_argument("--subject", help="Specific subject ID (optional)")
    parser.add_argument("--session", help="Specific session ID (optional, use with --subject)")
    parser.add_argument("--skip-bids", action="store_true", help="Skip BIDS conversion step")
    parser.add_argument("--skip-fmriprep", action="store_true", help="Skip fMRIPrep preprocessing step")
    parser.add_argument("--parallel", type=int, default=default_workers, 
                        help=f"Number of parallel workers (default: {default_workers} based on CPU cores)")
    parser.add_argument("--anonymize", action="store_true", 
                        help="Enable DICOM metadata anonymization (removes patient info from JSON sidecars)")

    args = parser.parse_args()

    # Setup Paths
    project_root = Path(__file__).parent.parent.resolve()
    input_root = Path(args.input).resolve()
    base_output = Path(args.output_dir).resolve()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_folder = base_output / f"output_{timestamp}"
    output_folder.mkdir(parents=True, exist_ok=True)
    
    # BIDS output goes directly in output folder (no bids_output subfolder)
    bids_dir = output_folder
    derivatives_dir = output_folder / "derivatives"
    fmriprep_script = project_root / "src" / "run_fmriprep.py"
    
    # Initialize report
    report = ConversionReport()
    report.input_folder = str(input_root)
    report.output_folder = str(output_folder)
    report.skip_bids = args.skip_bids
    report.skip_fmriprep = args.skip_fmriprep
    
    safe_print(f"Output folder: {output_folder}", flush=True)

    local_dcm2niix_dir = project_root / "tools" / "dcm2niix"
    if local_dcm2niix_dir.exists():
        os.environ["PATH"] = str(local_dcm2niix_dir) + os.pathsep + os.environ.get("PATH", "")
    
    # Find config file (check multiple locations)
    config_path = None
    for candidate in [
        Path(args.config),
        project_root / args.config,
        project_root / "config" / args.config,
    ]:
        if candidate.exists():
            config_path = candidate.resolve()
            break
    
    if not config_path:
        safe_print(f"Error: Config file not found: {args.config}", flush=True)
        sys.exit(1)
    
    report.config_file = str(config_path)
    
    # Handle anonymization option
    if args.anonymize:
        safe_print("Anonymization enabled - patient info will be removed from metadata", flush=True)
        # Load config and modify dcm2niixOptions to enable anonymization
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Get current options or set default
            current_options = config_data.get('dcm2niixOptions', '-z 1 -b y -f %p_%s')
            
            # Replace -ba n with -ba y (enable anonymization)
            if '-ba n' in current_options:
                new_options = current_options.replace('-ba n', '-ba y')
            elif '-ba y' not in current_options:
                # Add anonymization flag if not present
                new_options = current_options + ' -ba y'
            else:
                new_options = current_options
            
            config_data['dcm2niixOptions'] = new_options
            
            # Write modified config to output folder
            modified_config_path = output_folder / "dcm2bids_config_anonymized.json"
            with open(modified_config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2)
            
            config_path = modified_config_path
            safe_print(f"Using modified config with anonymization: {config_path}", flush=True)
        except Exception as e:
            safe_print(f"Warning: Could not modify config for anonymization: {e}", flush=True)
            safe_print("Continuing with original config (no anonymization)", flush=True)
    else:
        safe_print(f"Using config: {config_path}", flush=True)
        safe_print("Anonymization disabled (default) - full metadata preserved", flush=True)

    # Build list of (subject_id, session_id, dicom_path)
    tasks = []
    
    if args.subject and args.session:
        # Single subject + session mode
        tasks.append({
            "sub_id": sanitize_id(args.subject),
            "ses_id": args.session,
            "dicom_path": input_root
        })
    elif args.subject:
        # Single subject, auto-detect sessions
        sub_id = sanitize_id(args.subject)
        sessions = find_sessions(input_root)
        for ses_id, ses_path in sessions:
            tasks.append({
                "sub_id": sub_id,
                "ses_id": ses_id,
                "dicom_path": ses_path
            })
    else:
        # Auto-detect everything
        safe_print(f"Scanning {input_root} for subjects...", flush=True)
        
        for sub_dir in find_subject_folders(input_root):
            sub_id = sanitize_id(sub_dir.name)
            if not sub_id:
                safe_print(f"  Skipping invalid folder name: {sub_dir.name}", flush=True)
                continue
            
            sessions = find_sessions(sub_dir)
            safe_print(f"  Found subject {sub_id} with {len(sessions)} session(s)", flush=True)
            
            for ses_id, ses_path in sessions:
                # Verify there are actually DICOM files
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

    # Group tasks by subject (sessions of same subject will run in parallel first)
    subjects_tasks = OrderedDict()
    for task in tasks:
        sub_id = task['sub_id']
        if sub_id not in subjects_tasks:
            subjects_tasks[sub_id] = []
        subjects_tasks[sub_id].append(task)
    
    # Add task numbers for progress tracking (global across all tasks)
    task_num = 0
    for sub_id in subjects_tasks:
        for task in subjects_tasks[sub_id]:
            task['task_num'] = task_num
            task_num += 1

    num_subjects = len(subjects_tasks)
    total_tasks = len(tasks)
    # Use aggressive parallelism: process all tasks in parallel
    num_workers = min(args.parallel, total_tasks)
    
    report.total_tasks = total_tasks
    
    safe_print(f"\nTotal: {total_tasks} sessions across {num_subjects} subjects", flush=True)
    safe_print(f"Using {num_workers} parallel workers (max)", flush=True)
    safe_print(f"[PROGRESS:TOTAL:{total_tasks}]", flush=True)
    
    errors = []
    progress_tracker = ProgressTracker(total_tasks)
    desc_created_event = threading.Event()

    all_tasks = [task for sub_tasks in subjects_tasks.values() for task in sub_tasks]
    
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {
            executor.submit(
                process_single_task,
                task, config_path, bids_dir, derivatives_dir, fmriprep_script,
                args.skip_bids, args.skip_fmriprep, progress_tracker, desc_created_event, report
            ): task for task in all_tasks
        }
        
        for future in as_completed(futures):
            task = futures[future]
            try:
                error = future.result()
                if error:
                    errors.append(error)
            except Exception as e:
                error_msg = f"sub-{task['sub_id']}/ses-{task['ses_id']} (Unexpected error: {e})"
                errors.append(error_msg)
                report.add_failure(task['sub_id'], task['ses_id'], str(e), "Unknown")
                safe_print(f"[FAIL] Unexpected error for sub-{task['sub_id']}/ses-{task['ses_id']}: {e}", flush=True)

    safe_print(f"[PROGRESS:COMPLETE]", flush=True)
    
    safe_print("\nCleaning up temporary files...", flush=True)
    cleanup_count = 0
    cleanup_size = 0
    
    # 1. Remove tmp_dcm2bids folder
    tmp_folder = bids_dir / "tmp_dcm2bids"
    if tmp_folder.exists():
        try:
            # Calculate size before deletion
            for f in tmp_folder.rglob('*'):
                if f.is_file():
                    cleanup_size += f.stat().st_size
            shutil.rmtree(tmp_folder)
            cleanup_count += 1
            safe_print(f"  Removed: tmp_dcm2bids/", flush=True)
        except Exception as e:
            warning = f"Could not remove tmp_dcm2bids folder: {e}"
            report.add_warning(warning)
            safe_print(f"  Warning: {warning}", flush=True)
    
    # 2. Remove .bidsignore if it only contains default entries
    bidsignore = bids_dir / ".bidsignore"
    if bidsignore.exists():
        try:
            bidsignore.unlink()
            cleanup_count += 1
        except Exception:
            pass
    
    # 3. Log files are preserved in the output folder for debugging    
    # 4. Remove scans.tsv files if they're empty or just headers
    for scans_file in bids_dir.rglob("*_scans.tsv"):
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
    
    # Count output files
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
    
    # Generate and save report
    report_text = report.generate_report()
    report_path = output_folder / "conversion_report.txt"
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_text)
        safe_print(f"\nConversion report saved to: {report_path}", flush=True)
    except Exception as e:
        safe_print(f"Warning: Could not save report: {e}", flush=True)
    
    # Summary
    safe_print("\n" + "="*60, flush=True)
    safe_print(f"Output saved to: {output_folder}", flush=True)
    if errors:
        safe_print("PIPELINE COMPLETED WITH ERRORS:", flush=True)
        for err in errors:
            safe_print(f"  [X] {err}", flush=True)
        safe_print("="*60, flush=True)
        sys.exit(1)
    else:
        safe_print("[OK] All tasks completed successfully.", flush=True)
        safe_print("="*60, flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
