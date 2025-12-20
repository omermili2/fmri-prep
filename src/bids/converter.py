"""
BIDS conversion using dcm2bids.

This module handles the actual DICOM to BIDS conversion process,
wrapping the dcm2bids command-line tool.
"""

import subprocess
import json
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
    config_path,
    bids_dir,
    task_label=None,
    timeout=1800
):
    """
    Run BIDS conversion for a single subject/session.
    
    Uses dcm2bids to convert DICOM files to BIDS format.
    
    Args:
        dicom_path: Path to the DICOM directory
        sub_id: Subject ID (without 'sub-' prefix)
        ses_id: Session ID (without 'ses-' prefix)
        config_path: Path to dcm2bids config file
        bids_dir: Output BIDS directory
        task_label: Optional label for logging (e.g., "sub-001/ses-01")
        timeout: Timeout in seconds (default: 30 minutes)
        
    Returns:
        Tuple of (success: bool, duration: float, error_message: str or None)
    """
    if task_label is None:
        task_label = f"sub-{sub_id}/ses-{ses_id}"
    
    start_time = datetime.now()
    
    cmd = [
        "dcm2bids",
        "-d", str(dicom_path),
        "-p", sub_id,
        "-s", ses_id,
        "-c", str(config_path),
        "-o", str(bids_dir),
        "--force_dcm2bids",  # Overwrite existing dcm2bids output
        "--clobber"          # Overwrite existing NIfTI files without prompting
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
        
        duration = (datetime.now() - start_time).total_seconds()
        
        if result.returncode != 0:
            error_msg = result.stderr[:300] if result.stderr else "Unknown error"
            safe_print(f"[{task_label}] dcm2bids error: {error_msg[:100]}", flush=True)
            return False, duration, error_msg
        
        safe_print(f"[OK] {task_label} - BIDS completed ({duration:.1f}s)", flush=True)
        return True, duration, None
        
    except subprocess.TimeoutExpired:
        duration = (datetime.now() - start_time).total_seconds()
        error_msg = f"Conversion timed out after {timeout // 60} minutes"
        safe_print(f"[FAIL] {task_label} - BIDS conversion timed out", flush=True)
        return False, duration, error_msg
        
    except FileNotFoundError:
        duration = (datetime.now() - start_time).total_seconds()
        error_msg = "dcm2bids not found. Please install dcm2bids: pip install dcm2bids"
        safe_print(f"[FAIL] {task_label} - dcm2bids not found", flush=True)
        return False, duration, error_msg
        
    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        safe_print(f"[FAIL] {task_label} - BIDS conversion failed: {e}", flush=True)
        return False, duration, str(e)


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

