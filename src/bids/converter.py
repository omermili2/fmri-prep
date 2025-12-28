"""
BIDS conversion using dcm2niix.

This module handles the actual DICOM to BIDS conversion process,
using dcm2niix directly to convert ALL DICOM files and organizing
them into BIDS structure based on JSON metadata.
"""

import subprocess
import json
import re
import shutil
from pathlib import Path
from datetime import datetime

try:
    from ..core.utils import safe_print
except ImportError:
    from core.utils import safe_print


def run_bids_conversion(
    dicom_path,
    sub_id,
    ses_id,
    bids_dir,
    task_label=None,
    timeout=1800,
    anonymize=False
):
    """
    Run BIDS conversion for a single subject/session using dcm2niix.
    
    Converts ALL DICOM files and organizes them into BIDS structure
    based on JSON sidecar metadata.
    
    Args:
        dicom_path: Path to the DICOM directory
        sub_id: Subject ID (without 'sub-' prefix)
        ses_id: Session ID (without 'ses-' prefix)
        bids_dir: Output BIDS directory
        task_label: Optional label for logging (e.g., "sub-001/ses-01")
        timeout: Timeout in seconds (default: 30 minutes)
        anonymize: If True, anonymize DICOM metadata
        
    Returns:
        Tuple of (success: bool, duration: float, error_message: str or None)
    """
    if task_label is None:
        task_label = f"sub-{sub_id}/ses-{ses_id}"
    
    start_time = datetime.now()
    bids_path = Path(bids_dir)
    
    # Create temp directory for dcm2niix output
    temp_dir = bids_path / "tmp_dcm2niix" / f"sub-{sub_id}_ses-{ses_id}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # Run dcm2niix - converts EVERYTHING
    cmd = [
        "dcm2niix",
        "-z", "y",      # Compress to .nii.gz
        "-b", "y",      # Create JSON sidecar
        "-ba", "y" if anonymize else "n",  # Anonymize if requested
        "-f", "%p_%s",  # Filename pattern: protocol_series
        "-o", str(temp_dir),
        str(dicom_path)
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout
        )
        
        if result.returncode != 0:
            duration = (datetime.now() - start_time).total_seconds()
            error_msg = result.stderr[:300] if result.stderr else "dcm2niix failed"
            safe_print(f"[{task_label}] dcm2niix error: {error_msg[:100]}", flush=True)
            return False, duration, error_msg
        
        # Log dcm2niix output for debugging
        if result.stdout:
            lines = result.stdout.strip().split('\n')
            converted_count = sum(1 for line in lines if 'Convert' in line)
            safe_print(f"[{task_label}] dcm2niix converted {converted_count} series", flush=True)
        
        # Now organize converted files into BIDS structure
        organized = _organize_to_bids(temp_dir, bids_path, sub_id, ses_id)
        
        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        duration = (datetime.now() - start_time).total_seconds()
        
        if organized > 0:
            safe_print(f"[OK] {task_label} - BIDS completed ({organized} files, {duration:.1f}s)", flush=True)
            return True, duration, None
        else:
            error_msg = "No files were organized into BIDS structure"
            safe_print(f"[WARN] {task_label} - {error_msg}", flush=True)
            return False, duration, error_msg
            
    except subprocess.TimeoutExpired:
        duration = (datetime.now() - start_time).total_seconds()
        error_msg = f"Conversion timed out after {timeout // 60} minutes"
        safe_print(f"[FAIL] {task_label} - dcm2niix timed out", flush=True)
        return False, duration, error_msg
        
    except FileNotFoundError:
        duration = (datetime.now() - start_time).total_seconds()
        error_msg = "dcm2niix not found. Please ensure dcm2niix is installed and in PATH"
        safe_print(f"[FAIL] {task_label} - dcm2niix not found", flush=True)
        return False, duration, error_msg
        
    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        safe_print(f"[FAIL] {task_label} - dcm2niix conversion failed: {e}", flush=True)
        return False, duration, str(e)


def _organize_to_bids(temp_dir, bids_dir, sub_id, ses_id):
    """
    Organize dcm2niix output into BIDS structure based on JSON metadata.
    
    Reads each JSON sidecar to determine modality and organizes files accordingly.
    
    Returns:
        Number of files organized
    """
    temp_path = Path(temp_dir)
    bids_path = Path(bids_dir)
    organized_count = 0
    skipped_count = 0
    
    # Track run numbers for each task
    run_counters = {}
    
    # Find all JSON files
    json_files = sorted(temp_path.glob("*.json"))
    safe_print(f"  Found {len(json_files)} JSON sidecar files to process", flush=True)
    
    for json_file in json_files:
        nii_file = json_file.with_suffix('.nii.gz')
        if not nii_file.exists():
            nii_file = json_file.with_suffix('.nii')
            if not nii_file.exists():
                safe_print(f"  Skipping {json_file.name}: no matching NIfTI file", flush=True)
                continue
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        except Exception as e:
            safe_print(f"  Skipping {json_file.name}: failed to read JSON - {e}", flush=True)
            continue
        
        # Determine modality from metadata
        series_desc = metadata.get("SeriesDescription", "").lower()
        modality_info = _classify_scan(metadata, series_desc)
        
        if modality_info is None:
            skipped_count += 1
            safe_print(f"  Unrecognized: {metadata.get('SeriesDescription', 'NO_DESC')} ({json_file.name})", flush=True)
            continue
        
        datatype, suffix, entities = modality_info
        
        # Handle run numbering for BOLD scans
        if datatype == "func" and "task-" in entities:
            task_key = f"{datatype}_{entities}"
            run_counters[task_key] = run_counters.get(task_key, 0) + 1
            run_num = run_counters[task_key]
            entities = f"{entities}_run-{run_num:02d}"
        
        # Create output directory
        out_dir = bids_path / f"sub-{sub_id}" / f"ses-{ses_id}" / datatype
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # Create BIDS filename
        bids_name = f"sub-{sub_id}_ses-{ses_id}"
        if entities:
            bids_name += f"_{entities}"
        bids_name += f"_{suffix}"
        
        # Copy files
        out_nii = out_dir / f"{bids_name}.nii.gz"
        out_json = out_dir / f"{bids_name}.json"
        
        shutil.copy2(nii_file, out_nii)
        shutil.copy2(json_file, out_json)
        organized_count += 1
        safe_print(f"  Organized: {series_desc} -> {datatype}/{suffix}", flush=True)
    
    if skipped_count > 0:
        safe_print(f"  Warning: {skipped_count} scans were not recognized and skipped", flush=True)
    
    return organized_count


def _classify_scan(metadata, series_desc):
    """
    Classify a scan based on its metadata.
    
    Returns:
        Tuple of (datatype, suffix, custom_entities) or None if unrecognized
    """
    # Check for BOLD/functional scans
    # Match: bold, fmri, epi, mbepi, or series starting with "func"
    is_functional = any(x in series_desc for x in ["bold", "fmri", "mbepi"])
    is_functional = is_functional or series_desc.startswith("func")
    # Also check for "epi" but not "se_epi" or "seepi" (those are fieldmaps)
    if "epi" in series_desc and "se_epi" not in series_desc and "seepi" not in series_desc and "spinecho" not in series_desc:
        is_functional = True
    
    if is_functional:
        # Try to extract task name from series description
        # Look for patterns like: task-story, task-rest, _story_, -story-, etc.
        task = None
        
        # Pattern 1: explicit task-<name> format
        task_match = re.search(r'task[_-]([a-zA-Z]+)', series_desc)
        if task_match:
            task = task_match.group(1).lower()
        # Pattern 2: common task names anywhere in description
        elif "rest" in series_desc:
            task = "rest"
        elif "memory" in series_desc:
            task = "memory"
        elif "movie" in series_desc:
            task = "movie"
        elif "music" in series_desc:
            task = "music"
        elif "story" in series_desc:
            task = "story"
        elif "sound" in series_desc:
            task = "sound"
        elif "faces" in series_desc:
            task = "faces"
        elif "motor" in series_desc:
            task = "motor"
        elif "nf" in series_desc or "neurofeedback" in series_desc:
            task = "nf"
        elif "word" in series_desc:
            task = "wordpairs"
        else:
            # Default: try to extract from end of description
            match = re.search(r'[-_]([a-zA-Z]+)\d*$', series_desc)
            if match:
                task = match.group(1).lower()
            else:
                task = "unknown"
        
        return ("func", "bold", f"task-{task}")
    
    # Check for anatomical scans
    if any(x in series_desc for x in ["t1w", "t1_", "mprage", "spgr", "bravo", "tfl"]):
        return ("anat", "T1w", "")
    if any(x in series_desc for x in ["t2w", "t2_", "t2space", "tse", "fse"]):
        return ("anat", "T2w", "")
    if "flair" in series_desc or "dark_fluid" in series_desc:
        return ("anat", "FLAIR", "")
    
    # Check for fieldmaps
    phase_dir = metadata.get("PhaseEncodingDirection", "")
    if any(x in series_desc for x in ["ap", "pa", "se_epi", "spinecho", "topup", "distortion"]):
        if "j-" in phase_dir or "ap" in series_desc:
            return ("fmap", "epi", "dir-AP")
        elif "j" in phase_dir or "pa" in series_desc:
            return ("fmap", "epi", "dir-PA")
        return ("fmap", "epi", "")
    if "fieldmap" in series_desc or "gre_field" in series_desc:
        return ("fmap", "phasediff", "")
    
    # Check for diffusion
    if any(x in series_desc for x in ["dwi", "dti", "diffusion", "hardi"]):
        return ("dwi", "dwi", "")
    
    # Check for perfusion
    if any(x in series_desc for x in ["asl", "pcasl", "pasl"]):
        return ("perf", "asl", "")
    
    # Fallback: try to detect by ImageType or other metadata
    image_type = metadata.get("ImageType", [])
    if isinstance(image_type, list):
        if "FMRI" in image_type or "BOLD" in image_type:
            return ("func", "bold", "task-unknown")
    
    return None


def create_dataset_description(bids_dir, name="fMRI Pipeline Output"):
    """
    Create the required dataset_description.json file for BIDS.
    
    Args:
        bids_dir: Path to the BIDS output directory
        name: Name of the dataset
        
    Returns:
        True if created, False if already exists or error
    """
    bids_path = Path(bids_dir)
    desc_path = bids_path / "dataset_description.json"
    
    if desc_path.exists():
        return False
    
    bids_path.mkdir(parents=True, exist_ok=True)
    
    desc_content = {
        "Name": name,
        "BIDSVersion": "1.8.0",
        "DatasetType": "raw",
        "Authors": ["Pipeline"]
    }
    
    try:
        with open(desc_path, 'w', encoding='utf-8') as f:
            json.dump(desc_content, f, indent=4)
        return True
    except Exception:
        return False
