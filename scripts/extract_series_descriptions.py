#!/usr/bin/env python3
"""
Extract SeriesDescriptions from DICOM files and update dcm2bids config.

This script scans a folder containing DICOM files, extracts all unique
SeriesDescription values, and automatically updates the dcm2bids_config.json.

Usage:
    python scripts/extract_series_descriptions.py
    (A folder picker dialog will open)

Requirements:
    pip install pydicom
"""

import os
import sys
import json
import shutil
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from typing import Optional
from tkinter import Tk, filedialog

try:
    import pydicom
except ImportError:
    print("Error: pydicom is required. Install it with:")
    print("  pip install pydicom")
    sys.exit(1)


def select_folder() -> Optional[Path]:
    """Open a folder picker dialog and return the selected path."""
    root = Tk()
    root.withdraw()  # Hide the main tkinter window
    root.attributes('-topmost', True)  # Bring dialog to front
    
    folder_path = filedialog.askdirectory(
        title="Select folder containing DICOM files"
    )
    
    root.destroy()
    
    if folder_path:
        return Path(folder_path)
    return None


class SeriesInfo:
    """Container for series information."""
    def __init__(self):
        self.count: int = 0
        self.protocol_name: str = ""
        self.series_numbers: set = set()
        self.modality: str = ""
        self.example_path: str = ""


def extract_series_info(filepath: Path) -> Optional[dict]:
    """Extract relevant series information from a DICOM file."""
    try:
        ds = pydicom.dcmread(str(filepath), stop_before_pixels=True, force=True)
        
        info = {
            "SeriesDescription": getattr(ds, "SeriesDescription", None),
            "ProtocolName": getattr(ds, "ProtocolName", ""),
            "SeriesNumber": getattr(ds, "SeriesNumber", ""),
            "Modality": getattr(ds, "Modality", ""),
        }
        
        if info["SeriesDescription"] is None:
            return None
            
        return info
    except Exception:
        return None


def scan_folder(folder_path: Path) -> dict:
    """Scan a folder for DICOM files and extract unique SeriesDescriptions."""
    series_info: dict[str, SeriesInfo] = defaultdict(SeriesInfo)
    dicom_files = 0
    
    print(f"\nScanning: {folder_path}")
    print("This may take a while for large datasets...\n")
    
    for root, dirs, files in os.walk(folder_path):
        for filename in files:
            filepath = Path(root) / filename
            
            # Skip non-DICOM files
            if filepath.suffix.lower() in ['.json', '.txt', '.nii', '.gz', '.md', '.py', '.log', '.bak']:
                continue
            
            info = extract_series_info(filepath)
            if info is None:
                continue
                
            dicom_files += 1
            series_desc = info["SeriesDescription"]
            
            series_info[series_desc].count += 1
            series_info[series_desc].protocol_name = info["ProtocolName"]
            series_info[series_desc].series_numbers.add(info["SeriesNumber"])
            series_info[series_desc].modality = info["Modality"]
            if not series_info[series_desc].example_path:
                series_info[series_desc].example_path = str(filepath)
            
            if dicom_files % 100 == 0:
                print(f"  Processed {dicom_files} DICOM files...", end='\r')
    
    print(f"  Processed {dicom_files} DICOM files total.    ")
    return dict(series_info)


def categorize_series(series_desc: str) -> tuple:
    """Categorize a series and return (datatype, suffix, task_name, should_skip)."""
    desc_lower = series_desc.lower()
    
    # Skip these
    if any(x in desc_lower for x in ['localizer', 'scout', 'survey', 'loc', 'cal', 'prescan', 
                                       'asset', 'coil', 'phoenix', 'smartbrain']):
        return (None, None, None, True)
    
    # Anatomical T1w
    if any(x in desc_lower for x in ['t1', 'mprage', 'spgr', 'bravo', 'fspgr', 'ir_fspgr']):
        if 't2' not in desc_lower:
            return ("anat", "T1w", None, False)
    
    # Anatomical T2w/FLAIR
    if any(x in desc_lower for x in ['t2', 'flair', 'tse', 'fse']):
        if 'flair' in desc_lower:
            return ("anat", "FLAIR", None, False)
        return ("anat", "T2w", None, False)
    
    # Functional BOLD
    if any(x in desc_lower for x in ['fmri', 'bold', 'func']) or ('epi' in desc_lower and 'se-epi' not in desc_lower):
        task_name = series_desc
        for prefix in ['fMRI_', 'fmri_', 'FMRI_', 'bold_', 'BOLD_', 'func_', 'FUNC_']:
            task_name = task_name.replace(prefix, '')
        task_name = task_name.lower().replace(' ', '').replace('-', '').replace('_', '')
        if not task_name or task_name in ['bold', 'epi', 'fmri']:
            task_name = 'task'
        return ("func", "bold", task_name, False)
    
    # Diffusion
    if any(x in desc_lower for x in ['dwi', 'dti', 'diffusion', 'hardi']):
        return ("dwi", "dwi", None, False)
    
    # Field maps
    if 'se-epi' in desc_lower or 'seepi' in desc_lower or 'spin_echo' in desc_lower:
        return ("fmap", "epi", None, False)
    if any(x in desc_lower for x in ['fieldmap', 'field_map', 'b0map', 'phasediff', 'phase_diff']):
        return ("fmap", "phasediff", None, False)
    if ('_pa' in desc_lower or '_ap' in desc_lower) and 'epi' in desc_lower:
        return ("fmap", "epi", None, False)
    
    return (None, None, None, True)


def create_config_entry(series_desc: str) -> Optional[dict]:
    """Create a dcm2bids config entry for a SeriesDescription."""
    datatype, suffix, task_name, should_skip = categorize_series(series_desc)
    
    if should_skip or datatype is None:
        return None
    
    entry = {
        "id": series_desc.lower().replace(" ", "_").replace("-", "_"),
        "datatype": datatype,
        "suffix": suffix,
        "criteria": {
            "SeriesDescription": series_desc
        }
    }
    
    if datatype == "func" and task_name:
        entry["custom_entities"] = f"task-{task_name}"
        entry["sidecarChanges"] = {"TaskName": task_name}
    
    return entry


def load_config(config_path: Path) -> dict:
    """Load existing config file."""
    if not config_path.exists():
        return {
            "dcm2niixOptions": "-z 1 -b y -ba n -f %p_%s",
            "descriptions": []
        }
    
    with open(config_path, 'r') as f:
        return json.load(f)


def get_existing_series_descriptions(config: dict) -> set:
    """Get set of SeriesDescriptions already in config."""
    existing = set()
    for desc in config.get("descriptions", []):
        criteria = desc.get("criteria", {})
        series_desc = criteria.get("SeriesDescription", "")
        clean_desc = series_desc.strip("*")
        existing.add(clean_desc)
        existing.add(series_desc)
    return existing


def update_config(config: dict, series_info: dict) -> tuple:
    """Update config with new SeriesDescriptions."""
    existing = get_existing_series_descriptions(config)
    new_entries = []
    skipped_entries = []
    
    for series_desc in sorted(series_info.keys()):
        already_exists = False
        for existing_pattern in existing:
            if series_desc == existing_pattern or (existing_pattern and existing_pattern in series_desc):
                already_exists = True
                break
        
        if already_exists:
            skipped_entries.append((series_desc, "already in config"))
            continue
        
        entry = create_config_entry(series_desc)
        
        if entry is None:
            _, _, _, should_skip = categorize_series(series_desc)
            if should_skip:
                skipped_entries.append((series_desc, "localizer/calibration scan"))
            else:
                skipped_entries.append((series_desc, "unknown type"))
            continue
        
        new_entries.append(entry)
        config["descriptions"].append(entry)
    
    return config, new_entries, skipped_entries


def main():
    # Get folder from command line or open picker
    if len(sys.argv) == 2:
        dicom_folder = Path(sys.argv[1])
    else:
        print("Select the folder containing DICOM files...")
        dicom_folder = select_folder()
        if dicom_folder is None:
            print("No folder selected. Exiting.")
            sys.exit(0)
    
    if not dicom_folder.exists() or not dicom_folder.is_dir():
        print(f"Error: Folder not found: {dicom_folder}")
        sys.exit(1)
    
    # Find config file
    script_dir = Path(__file__).parent
    config_path = script_dir.parent / "config" / "dcm2bids_config.json"
    
    print(f"Config file: {config_path}")
    
    # Scan DICOM folder
    series_info = scan_folder(dicom_folder)
    
    if not series_info:
        print("\nNo DICOM files with SeriesDescription found.")
        sys.exit(1)
    
    # Print found series
    print("\n" + "=" * 80)
    print("SERIES DESCRIPTIONS FOUND")
    print("=" * 80)
    print(f"\n{'SeriesDescription':<45} {'Category':<20} {'Files':>10}")
    print("-" * 80)
    
    for series_desc in sorted(series_info.keys()):
        info = series_info[series_desc]
        datatype, suffix, task, skip = categorize_series(series_desc)
        if skip:
            category = "SKIP"
        elif datatype:
            category = f"{datatype}/{suffix}"
            if task:
                category += f" ({task})"
        else:
            category = "unknown"
        print(f"{series_desc:<45} {category:<20} {info.count:>10}")
    
    # Load and update config
    config = load_config(config_path)
    updated_config, new_entries, skipped_entries = update_config(config, series_info)
    
    # Print summary
    print("\n" + "=" * 80)
    print("CONFIG UPDATE")
    print("=" * 80)
    
    if new_entries:
        print(f"\n+ ADDING {len(new_entries)} new entries:")
        for entry in new_entries:
            print(f"   {entry['datatype']}/{entry['suffix']}: {entry['criteria']['SeriesDescription']}")
    
    if skipped_entries:
        print(f"\n- SKIPPED {len(skipped_entries)} entries:")
        for series_desc, reason in skipped_entries:
            print(f"   {series_desc}: {reason}")
    
    # Save config
    if new_entries:
        # Backup
        if config_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = config_path.with_suffix(f".backup_{timestamp}.json")
            shutil.copy(config_path, backup_path)
            print(f"\nBackup: {backup_path}")
        
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(updated_config, f, indent=2)
        
        print(f"Updated: {config_path}")
        print(f"Added {len(new_entries)} new entries")
    else:
        print("\nNo changes needed - config is complete!")
    
    print("\nDone!")


if __name__ == "__main__":
    main()
