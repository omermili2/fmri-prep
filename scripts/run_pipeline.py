#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path
import shutil
import re

def run_command(cmd, dry_run=False):
    """Runs a shell command and handles errors."""
    if dry_run:
        print(f"[DRY-RUN] {' '.join(cmd)}")
        return

    try:
        # Capture output to suppress verbose logs unless error
        subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        # Re-raise to be caught by caller
        raise e
    except FileNotFoundError:
        raise FileNotFoundError(f"Command not found: {cmd[0]}")

def find_subject_folders(input_root):
    """Scans input directory for subject folders."""
    root = Path(input_root)
    if not root.exists():
        return []
    
    # Return directories only
    return [d for d in root.iterdir() if d.is_dir() and not d.name.startswith('.')]

def find_dicom_dir(subject_path):
    """Recursively finds the directory containing .dcm files."""
    # Strategy: Walk through the directory. If we find .dcm files, that's our target.
    # If multiple directories have .dcm files, this simple version returns the first one found
    # or we could rely on dcm2bids searching recursively (which it does if we point to top level).
    
    # dcm2bids -d <path> handles recursive search, but sometimes it's safer to be specific.
    # However, for this nested structure: 
    # 110/MRI1/scans/Study.../Series.../MR001.dcm
    # Pointing dcm2bids to '110' usually works.
    
    return subject_path

def main():
    parser = argparse.ArgumentParser(description="fMRI Master Pipeline: BIDS Conversion + fMRIPrep")
    
    parser.add_argument("--input", required=True, help="Path to root directory containing subject folders")
    parser.add_argument("--output_dir", required=True, help="Base directory for outputs")
    parser.add_argument("--config", default="dcm2bids_config.json", help="Path to dcm2bids config file")
    parser.add_argument("--subject", help="Specific subject ID (optional)")
    parser.add_argument("--session", default="01", help="Session ID (default: 01)")
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
    config_path = Path(args.config).resolve()
    fmriprep_script = project_root / "scripts" / "run_fmriprep.sh"

    # Determine subjects
    subjects_to_process = []
    if args.subject:
        subjects_to_process.append({
            "id": args.subject,
            "path": input_root, 
            "session": args.session
        })
    else:
        print(f"Scanning {input_root} for subjects...", flush=True)
        sub_dirs = find_subject_folders(input_root)
        for d in sub_dirs:
            # Use folder name as ID, but remove 'sub-' prefix if present
            clean_id = d.name
            if clean_id.startswith('sub-'):
                clean_id = clean_id[4:]
            elif clean_id.startswith('sub'): # Handle cases like 'sub01' without dash
                clean_id = clean_id[3:]
            
            # Sanitize to alphanumeric only to be safe for BIDS
            clean_id = re.sub(r'[^a-zA-Z0-9]', '', clean_id)
            
            if not clean_id: continue

            subjects_to_process.append({
                "id": clean_id,
                "path": d, # Pass the subject root folder directly (e.g. '110'). dcm2bids handles recursion.
                "session": args.session
            })

    if not subjects_to_process:
        print("No subject directories found.", flush=True)
        sys.exit(0)

    print(f"Found {len(subjects_to_process)} subjects to process.", flush=True)

    errors = []

    # Processing Loop
    for sub in subjects_to_process:
        sub_id = sub['id']
        sub_path = sub['path']
        ses_id = sub['session']
        
        print(f"\n--- Processing Subject: {sub_id} ---", flush=True)

        # 1. BIDS Conversion
        if not args.skip_bids:
            print(f"  • Converting DICOM to BIDS format...", end="", flush=True)
            cmd_bids = [
                "dcm2bids",
                "-d", str(sub_path),
                "-p", sub_id,
                "-s", ses_id,
                "-c", str(config_path),
                "-o", str(bids_dir),
                "--force"
            ]
            try:
                run_command(cmd_bids, args.dry_run)
                
                # Create dataset_description.json if missing (Required for BIDS validity)
                desc_path = bids_dir / "dataset_description.json"
                if not args.dry_run and not desc_path.exists():
                    # Simple minimal JSON content
                    import json
                    desc_content = {
                        "Name": "fMRI Pipeline Output",
                        "BIDSVersion": "1.8.0",
                        "DatasetType": "raw",
                        "Authors": ["Pipeline"]
                    }
                    with open(desc_path, 'w') as f:
                        json.dump(desc_content, f, indent=4)
                    print("  • Created dataset_description.json", flush=True)

                print(" Done.", flush=True)
            except subprocess.CalledProcessError as e:
                print(f" Failed!", flush=True)
                error_msg = e.output.decode('utf-8').strip() if e.output else str(e)
                print(f"    Error Details: {error_msg}", flush=True)
                errors.append(f"Subject {sub_id} (BIDS Failed)")
                continue
            except Exception as e:
                print(f" Failed! ({e})", flush=True)
                errors.append(f"Subject {sub_id} (BIDS Error: {e})")
                continue

        # 2. fMRIPrep
        if not args.skip_fmriprep:
            print(f"  • Running fMRIPrep preprocessing...", end="", flush=True)
            cmd_fmriprep = [
                str(fmriprep_script),
                str(bids_dir),
                str(derivatives_dir),
                sub_id
            ]
            if args.dry_run:
                cmd_fmriprep.append("--dry-run")
            
            try:
                run_command(cmd_fmriprep, args.dry_run)
                print(" Done.", flush=True)
            except subprocess.CalledProcessError as e:
                print(f" Failed!", flush=True)
                error_msg = e.output.decode('utf-8').strip() if e.output else str(e)
                print(f"    Error Details: {error_msg}", flush=True)
                errors.append(f"Subject {sub_id} (fMRIPrep Failed)")
            except Exception as e:
                print(f" Failed! ({e})", flush=True)
                errors.append(f"Subject {sub_id} (fMRIPrep Error: {e})")

    print("\n" + "="*50)
    if errors:
        print("PIPELINE COMPLETED WITH ERRORS:")
        for err in errors:
            print(f" - {err}")
        print("="*50)
        sys.exit(1)
    else:
        print("All tasks completed successfully.")
        print("="*50)
        sys.exit(0)

if __name__ == "__main__":
    main()
