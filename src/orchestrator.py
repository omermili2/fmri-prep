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
    from .core.utils import setup_encoding, safe_print
    from .core.discovery import find_subject_folders, find_sessions, sanitize_id, has_dicom_files
    from .core.progress import ProgressTracker
    from .bids.converter import run_bids_conversion, create_dataset_description
    from .bids.analyzer import count_output_files
    from .reporting.report import ConversionReport
except ImportError:
    # When run directly as script
    from core.utils import setup_encoding, safe_print
    from core.discovery import find_subject_folders, find_sessions, sanitize_id, has_dicom_files
    from core.progress import ProgressTracker
    from bids.converter import run_bids_conversion, create_dataset_description
    from bids.analyzer import count_output_files
    from reporting.report import ConversionReport

setup_encoding()


def process_single_task(task, config_path, bids_dir, derivatives_dir, fmriprep_script, 
                        skip_bids, skip_fmriprep, fmriprep_opts, progress_tracker, 
                        desc_created_event, report):
    """
    Process a single subject-session task.
    
    This function is designed to run in parallel across multiple threads.
    
    Args:
        task: Dictionary with sub_id, ses_id, dicom_path, task_num
        config_path: Path to dcm2bids config
        bids_dir: BIDS output directory
        derivatives_dir: fMRIPrep derivatives directory
        fmriprep_script: Path to fMRIPrep runner script
        skip_bids: Skip BIDS conversion
        skip_fmriprep: Skip fMRIPrep
        fmriprep_opts: Dictionary of fMRIPrep options
        progress_tracker: ProgressTracker instance
        desc_created_event: Threading event for dataset_description.json
        report: ConversionReport instance
        
    Returns:
        Error string if failed, None if successful
    """
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
    if not skip_bids:
        success, duration, error_msg = run_bids_conversion(
            dicom_path, sub_id, ses_id, config_path, bids_dir, task_label
        )
        
        if success:
            report.add_success(sub_id, ses_id, duration)
            
            # Create dataset_description.json if missing (thread-safe)
            if not desc_created_event.is_set():
                if create_dataset_description(bids_dir):
                    desc_created_event.set()
        else:
            report.add_failure(sub_id, ses_id, error_msg, "BIDS Conversion")
            progress_tracker.increment()
            safe_print(f"[FAIL] {task_label} - BIDS conversion failed", flush=True)
            return f"{task_label} (BIDS failed)"
        
        progress_tracker.increment()

    # 2. fMRIPrep (if enabled)
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
        
        # Add fMRIPrep options if provided (as base64 JSON for platform-agnostic passing)
        if fmriprep_opts:
            opts_json = json.dumps(fmriprep_opts)
            opts_encoded = base64.b64encode(opts_json.encode('utf-8')).decode('ascii')
            cmd_fmriprep.extend(["--opts", opts_encoded])
        
        try:
            result = subprocess.run(
                cmd_fmriprep, 
                capture_output=True, 
                text=True, 
                encoding='utf-8', 
                errors='replace'
            )
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


def cleanup_temp_files(bids_dir, report):
    """
    Clean up temporary files after conversion.
    
    Removes:
    - tmp_dcm2bids/ folder
    - .bidsignore file
    - Empty scans.tsv files
    
    Args:
        bids_dir: BIDS output directory
        report: ConversionReport to update with cleanup info
    """
    safe_print("\nCleaning up temporary files...", flush=True)
    cleanup_count = 0
    cleanup_size = 0
    
    bids_path = Path(bids_dir)
    
    # 1. Remove tmp_dcm2bids folder
    tmp_folder = bids_path / "tmp_dcm2bids"
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
    bidsignore = bids_path / ".bidsignore"
    if bidsignore.exists():
        try:
            bidsignore.unlink()
            cleanup_count += 1
        except Exception:
            pass
    
    # 3. Remove empty scans.tsv files
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
        """
    )
    
    # Auto-detect optimal parallel workers
    cpu_count = multiprocessing.cpu_count()
    default_workers = min(max(cpu_count, 4), 12)
    
    parser.add_argument("--input", required=True, 
                        help="Path to root directory containing subject folders")
    parser.add_argument("--output_dir", required=True, 
                        help="Base directory for outputs")
    parser.add_argument("--config", default="dcm2bids_config.json", 
                        help="Path to dcm2bids config file")
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
    parser.add_argument("--fmriprep-opts", type=str, default="",
                        help="Base64-encoded JSON fMRIPrep options (platform-agnostic)")

    args = parser.parse_args()

    # Setup Paths
    project_root = Path(__file__).parent.parent.resolve()
    input_root = Path(args.input).resolve()
    base_output = Path(args.output_dir).resolve()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_folder = base_output / f"output_{timestamp}"
    output_folder.mkdir(parents=True, exist_ok=True)
    
    # BIDS output goes directly in output folder
    bids_dir = output_folder
    derivatives_dir = output_folder / "derivatives"
    fmriprep_script = project_root / "src" / "fmriprep" / "runner.py"
    
    # Initialize report
    report = ConversionReport()
    report.input_folder = str(input_root)
    report.output_folder = str(output_folder)
    report.skip_bids = args.skip_bids
    report.skip_fmriprep = args.skip_fmriprep
    
    safe_print(f"Output folder: {output_folder}", flush=True)

    # Add local dcm2niix to PATH if available
    local_dcm2niix_dir = project_root / "tools" / "dcm2niix"
    if local_dcm2niix_dir.exists():
        os.environ["PATH"] = str(local_dcm2niix_dir) + os.pathsep + os.environ.get("PATH", "")
    
    # Find config file
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
    
    # Handle anonymization
    if args.anonymize:
        safe_print("Anonymization enabled - patient info will be removed from metadata", flush=True)
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            current_options = config_data.get('dcm2niixOptions', '-z 1 -b y -f %p_%s')
            if '-ba n' in current_options:
                new_options = current_options.replace('-ba n', '-ba y')
            elif '-ba y' not in current_options:
                new_options = current_options + ' -ba y'
            else:
                new_options = current_options
            
            config_data['dcm2niixOptions'] = new_options
            
            modified_config_path = output_folder / "dcm2bids_config_anonymized.json"
            with open(modified_config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2)
            
            config_path = modified_config_path
            safe_print(f"Using modified config with anonymization: {config_path}", flush=True)
        except Exception as e:
            safe_print(f"Warning: Could not modify config for anonymization: {e}", flush=True)
    else:
        safe_print(f"Using config: {config_path}", flush=True)

    # Build task list
    tasks = []
    
    if args.subject and args.session:
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
    
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {
            executor.submit(
                process_single_task,
                task, config_path, bids_dir, derivatives_dir, fmriprep_script,
                args.skip_bids, args.skip_fmriprep, fmriprep_opts, 
                progress_tracker, desc_created_event, report
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
    
    # Cleanup
    cleanup_temp_files(bids_dir, report)
    
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
    
    # Save report
    report_text = report.generate_report()
    report_path = output_folder / "conversion_report.txt"
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_text)
        safe_print(f"\nConversion report saved to: {report_path}", flush=True)
    except Exception as e:
        safe_print(f"Warning: Could not save report: {e}", flush=True)
    
    # Summary
    safe_print("\n" + "=" * 60, flush=True)
    safe_print(f"Output saved to: {output_folder}", flush=True)
    if errors:
        safe_print("PIPELINE COMPLETED WITH ERRORS:", flush=True)
        for err in errors:
            safe_print(f"  [X] {err}", flush=True)
        safe_print("=" * 60, flush=True)
        sys.exit(1)
    else:
        safe_print("[OK] All tasks completed successfully.", flush=True)
        safe_print("=" * 60, flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()

