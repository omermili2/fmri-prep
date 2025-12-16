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


def process_single_task(task, config_path, bids_dir, derivatives_dir, fmriprep_script, 
                        skip_bids, skip_fmriprep, progress_tracker, desc_created_event):
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
            "--force"
        ]
        
        try:
            result = subprocess.run(cmd_bids, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if result.returncode != 0:
                safe_print(f"[{task_label}] dcm2bids error: {result.stderr[:200]}", flush=True)
                error = f"{task_label} (BIDS failed)"
                progress_tracker.increment()
                safe_print(f"[FAIL] {task_label} - BIDS conversion failed", flush=True)
                return error
            else:
                elapsed = (datetime.now() - task_start_time).total_seconds()
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
                
        except subprocess.CalledProcessError as e:
            error = f"{task_label} (BIDS error)"
            progress_tracker.increment()
            safe_print(f"[FAIL] {task_label} - BIDS conversion failed: {e}", flush=True)
            return error
        except Exception as e:
            error = f"{task_label} ({e})"
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
                error = f"{task_label} (fMRIPrep failed)"
            else:
                safe_print(f"[OK] {task_label} - fMRIPrep completed ({fmriprep_elapsed:.1f}s)", flush=True)
        except Exception as e:
            error = f"{task_label} (fMRIPrep error: {e})"
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
    
    # Auto-detect optimal parallel workers (use CPU count, max 8 to avoid memory issues)
    default_workers = min(multiprocessing.cpu_count(), 8)
    
    parser.add_argument("--input", required=True, help="Path to root directory containing subject folders")
    parser.add_argument("--output_dir", required=True, help="Base directory for outputs")
    parser.add_argument("--config", default="dcm2bids_config.json", help="Path to dcm2bids config file")
    parser.add_argument("--subject", help="Specific subject ID (optional)")
    parser.add_argument("--session", help="Specific session ID (optional, use with --subject)")
    parser.add_argument("--skip-bids", action="store_true", help="Skip BIDS conversion step")
    parser.add_argument("--skip-fmriprep", action="store_true", help="Skip fMRIPrep preprocessing step")
    parser.add_argument("--parallel", type=int, default=default_workers, 
                        help=f"Number of parallel workers (default: {default_workers} based on CPU cores)")

    args = parser.parse_args()

    # Setup Paths
    project_root = Path(__file__).parent.parent.resolve()
    input_root = Path(args.input).resolve()
    base_output = Path(args.output_dir).resolve()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_folder = base_output / f"output_{timestamp}"
    output_folder.mkdir(parents=True, exist_ok=True)
    
    bids_dir = output_folder / "bids_output"
    derivatives_dir = output_folder / "derivatives"
    fmriprep_script = project_root / "scripts" / "run_fmriprep.py"
    
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
    
    safe_print(f"Using config: {config_path}", flush=True)

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
    max_sessions = max(len(sessions) for sessions in subjects_tasks.values())
    num_workers = min(args.parallel, max_sessions)
    
    safe_print(f"\nTotal: {len(tasks)} sessions across {num_subjects} subjects", flush=True)
    safe_print(f"Using up to {num_workers} parallel workers per subject", flush=True)
    safe_print(f"[PROGRESS:TOTAL:{len(tasks)}]", flush=True)
    
    errors = []
    progress_tracker = ProgressTracker(len(tasks))
    desc_created_event = threading.Event()

    # Process subjects one by one, with sessions in parallel within each subject
    for sub_idx, (sub_id, sub_tasks) in enumerate(subjects_tasks.items(), 1):
        safe_print(f"\n--- Subject {sub_idx}/{num_subjects}: sub-{sub_id} ({len(sub_tasks)} sessions) ---", flush=True)
        
        if len(sub_tasks) == 1:
            # Single session - just run it
            error = process_single_task(
                sub_tasks[0], config_path, bids_dir, derivatives_dir, fmriprep_script,
                args.skip_bids, args.skip_fmriprep, progress_tracker, desc_created_event
            )
            if error:
                errors.append(error)
        else:
            # Multiple sessions - run in parallel
            session_workers = min(num_workers, len(sub_tasks))
            with ThreadPoolExecutor(max_workers=session_workers) as executor:
                futures = {
                    executor.submit(
                        process_single_task,
                        task, config_path, bids_dir, derivatives_dir, fmriprep_script,
                        args.skip_bids, args.skip_fmriprep, progress_tracker, desc_created_event
                    ): task for task in sub_tasks
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
                        safe_print(f"[FAIL] Unexpected error for sub-{task['sub_id']}/ses-{task['ses_id']}: {e}", flush=True)

    # Final progress marker - always reaches 100%
    safe_print(f"[PROGRESS:COMPLETE]", flush=True)
    
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
