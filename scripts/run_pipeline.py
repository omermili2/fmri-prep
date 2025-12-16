#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path
import re
import json

def run_command(cmd, dry_run=False):
    """Runs a shell command and handles errors."""
    if dry_run:
        print(f"[DRY-RUN] {' '.join(cmd)}")
        return
    try:
        subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        raise e
    except FileNotFoundError:
        raise FileNotFoundError(f"Command not found: {cmd[0]}")


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


def main():
    parser = argparse.ArgumentParser(
        description="fMRI Master Pipeline: BIDS Conversion + fMRIPrep",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all subjects
  python run_pipeline.py --input /data/raw --output_dir /data/processed

  # Process single subject with specific session
  python run_pipeline.py --input /data/raw/110/MRI1 --output_dir /data/processed --subject 110 --session 01

  # Dry run to preview commands
  python run_pipeline.py --input /data/raw --output_dir /data/processed --dry-run
        """
    )
    
    parser.add_argument("--input", required=True, help="Path to root directory containing subject folders")
    parser.add_argument("--output_dir", required=True, help="Base directory for outputs")
    parser.add_argument("--config", default="dcm2bids_config.json", help="Path to dcm2bids config file")
    parser.add_argument("--subject", help="Specific subject ID (optional)")
    parser.add_argument("--session", help="Specific session ID (optional, use with --subject)")
    parser.add_argument("--skip-bids", action="store_true", help="Skip BIDS conversion step")
    parser.add_argument("--skip-fmriprep", action="store_true", help="Skip fMRIPrep preprocessing step")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing")

    args = parser.parse_args()

    # Setup Paths
    project_root = Path(__file__).parent.parent.resolve()
    input_root = Path(args.input).resolve()
    base_output = Path(args.output_dir).resolve()
    
    bids_dir = base_output / "bids_output"
    derivatives_dir = base_output / "derivatives"
    fmriprep_script = project_root / "scripts" / "run_fmriprep.sh"
    
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
        print(f"Error: Config file not found: {args.config}", flush=True)
        sys.exit(1)
    
    print(f"Using config: {config_path}", flush=True)

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
        print(f"Scanning {input_root} for subjects...", flush=True)
        
        for sub_dir in find_subject_folders(input_root):
            sub_id = sanitize_id(sub_dir.name)
            if not sub_id:
                print(f"  Skipping invalid folder name: {sub_dir.name}", flush=True)
                continue
            
            sessions = find_sessions(sub_dir)
            print(f"  Found subject {sub_id} with {len(sessions)} session(s)", flush=True)
            
            for ses_id, ses_path in sessions:
                # Verify there are actually DICOM files
                if has_dicom_files(ses_path):
                    tasks.append({
                        "sub_id": sub_id,
                        "ses_id": ses_id,
                        "dicom_path": ses_path
                    })
                else:
                    print(f"    Warning: No DICOM files found in {ses_path}", flush=True)

    if not tasks:
        print("No subjects/sessions found to process.", flush=True)
        sys.exit(0)

    print(f"\nTotal tasks: {len(tasks)} (subject-session pairs)", flush=True)
    
    errors = []

    # Processing Loop
    for task in tasks:
        sub_id = task['sub_id']
        ses_id = task['ses_id']
        dicom_path = task['dicom_path']
        
        print(f"\n{'='*60}", flush=True)
        print(f"Processing: sub-{sub_id} / ses-{ses_id}", flush=True)
        print(f"DICOM source: {dicom_path}", flush=True)
        print(f"{'='*60}", flush=True)

        # 1. BIDS Conversion
        if not args.skip_bids:
            print("  -> Converting DICOM to BIDS format...", flush=True)
            cmd_bids = [
                "dcm2bids",
                "-d", str(dicom_path),
                "-p", sub_id,
                "-s", ses_id,
                "-c", str(config_path),
                "-o", str(bids_dir),
                "--force"
            ]
            
            if args.dry_run:
                print(f"  [DRY-RUN] {' '.join(cmd_bids)}", flush=True)
            else:
                try:
                    result = subprocess.run(cmd_bids, capture_output=True, text=True)
                    if result.returncode != 0:
                        print(f"    Warning: dcm2bids output:\n{result.stderr}", flush=True)
                    else:
                        print(f"    Done.", flush=True)
                    
                    # Create dataset_description.json if missing
                    desc_path = bids_dir / "dataset_description.json"
                    if not desc_path.exists():
                        desc_content = {
                            "Name": "fMRI Pipeline Output",
                            "BIDSVersion": "1.8.0",
                            "DatasetType": "raw",
                            "Authors": ["Pipeline"]
                        }
                        with open(desc_path, 'w') as f:
                            json.dump(desc_content, f, indent=4)
                        print(f"    Created dataset_description.json", flush=True)
                        
                except subprocess.CalledProcessError as e:
                    print(f"    FAILED: {e}", flush=True)
                    errors.append(f"sub-{sub_id}_ses-{ses_id} (BIDS conversion)")
                    continue
                except Exception as e:
                    print(f"    ERROR: {e}", flush=True)
                    errors.append(f"sub-{sub_id}_ses-{ses_id} ({e})")
                    continue

        # 2. fMRIPrep (run per subject, not per session)
        if not args.skip_fmriprep:
            print("  -> Running fMRIPrep...", flush=True)
            cmd_fmriprep = [
                str(fmriprep_script),
                str(bids_dir),
                str(derivatives_dir),
                sub_id
            ]
            
            if args.dry_run:
                print(f"  [DRY-RUN] {' '.join(cmd_fmriprep)}", flush=True)
            else:
                try:
                    result = subprocess.run(cmd_fmriprep, capture_output=True, text=True)
                    if result.returncode != 0:
                        print(f"    Warning: fMRIPrep output:\n{result.stderr}", flush=True)
                    else:
                        print(f"    Done.", flush=True)
                except Exception as e:
                    print(f"    ERROR: {e}", flush=True)
                    errors.append(f"sub-{sub_id} (fMRIPrep)")

    # Summary
    print("\n" + "="*60, flush=True)
    if errors:
        print("PIPELINE COMPLETED WITH ERRORS:", flush=True)
        for err in errors:
            print(f"  [X] {err}", flush=True)
        print("="*60, flush=True)
        sys.exit(1)
    else:
        print("[OK] All tasks completed successfully.", flush=True)
        print("="*60, flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
