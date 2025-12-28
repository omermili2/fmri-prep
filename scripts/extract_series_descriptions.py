#!/usr/bin/env python3
"""
Extract SeriesDescriptions from DICOM files and update dcm2bids config.

This script scans a folder containing DICOM files, extracts all unique
SeriesDescription values, and automatically updates the dcm2bids_config.json.

Usage:
    python extract_series_descriptions.py /path/to/dicom/folder
    python extract_series_descriptions.py /path/to/dicom/folder --config /path/to/config.json
    python extract_series_descriptions.py /path/to/dicom/folder --dry-run

Requirements:
    pip install pydicom
"""

import os
import sys
import json
import argparse
import shutil
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from typing import Optional

try:
    import pydicom
    from pydicom.errors import InvalidDicomError
except ImportError:
    print("Error: pydicom is required. Install it with:")
    print("  pip install pydicom")
    sys.exit(1)


def extract_series_info(filepath: Path) -> Optional[dict]:
    """Extract relevant series information from a DICOM file."""
    try:
        ds = pydicom.dcmread(str(filepath), stop_before_pixels=True, force=True)
        
        info = {
            "SeriesDescription": getattr(ds, "SeriesDescription", None),
            "ProtocolName": getattr(ds, "ProtocolName", ""),
            "SeriesNumber": getattr(ds, "SeriesNumber", ""),
            "Modality": getattr(ds, "Modality", ""),
            "ImageType": list(getattr(ds, "ImageType", [])) if hasattr(ds, "ImageType") else [],
        }
        
        # Skip if no SeriesDescription
        if info["SeriesDescription"] is None:
            return None
            
        return info
    except Exception:
        return None


class SeriesInfo:
    """Container for series information."""
    def __init__(self):
        self.count: int = 0
        self.protocol_name: str = ""
        self.series_numbers: set = set()
        self.modality: str = ""
        self.example_path: str = ""


def scan_folder(folder_path: Path) -> dict:
    """
    Scan a folder for DICOM files and extract unique SeriesDescriptions.
    """
    series_info: dict[str, SeriesInfo] = defaultdict(SeriesInfo)
    
    total_files = 0
    dicom_files = 0
    
    print(f"\nScanning: {folder_path}")
    print("This may take a while for large datasets...\n")
    
    for root, dirs, files in os.walk(folder_path):
        for filename in files:
            filepath = Path(root) / filename
            total_files += 1
            
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
    """
    Categorize a series and return (datatype, suffix, task_name, should_skip).
    """
    desc_lower = series_desc.lower()
    
    # Skip these
    if any(x in desc_lower for x in ['localizer', 'scout', 'survey', 'loc', 'cal', 'prescan', 'asset', 'coil', 'phoenix', 'smartbrain']):
        return (None, None, None, True)
    
    # Anatomical T1w
    if any(x in desc_lower for x in ['t1', 'mprage', 'spgr', 'bravo', 'fspgr', 'ir_fspgr']):
        if 't2' not in desc_lower:  # Make sure it's not T2
            return ("anat", "T1w", None, False)
    
    # Anatomical T2w/FLAIR
    if any(x in desc_lower for x in ['t2', 'flair', 'tse', 'fse']):
        if 'flair' in desc_lower:
            return ("anat", "FLAIR", None, False)
        return ("anat", "T2w", None, False)
    
    # Functional BOLD
    if any(x in desc_lower for x in ['fmri', 'bold', 'func']) or ('epi' in desc_lower and 'se-epi' not in desc_lower):
        # Extract task name
        task_name = series_desc
        # Remove common prefixes
        for prefix in ['fMRI_', 'fmri_', 'FMRI_', 'bold_', 'BOLD_', 'func_', 'FUNC_']:
            task_name = task_name.replace(prefix, '')
        # Clean up
        task_name = task_name.lower().replace(' ', '').replace('-', '').replace('_', '')
        if not task_name or task_name in ['bold', 'epi', 'fmri']:
            task_name = 'task'
        return ("func", "bold", task_name, False)
    
    # Diffusion
    if any(x in desc_lower for x in ['dwi', 'dti', 'diffusion', 'hardi']):
        return ("dwi", "dwi", None, False)
    
    # Field maps - SE-EPI (spin echo EPI for distortion correction)
    if 'se-epi' in desc_lower or 'seepi' in desc_lower or 'spin_echo' in desc_lower:
        return ("fmap", "epi", None, False)
    
    # Field maps - phase/magnitude
    if any(x in desc_lower for x in ['fieldmap', 'field_map', 'b0map', 'phasediff', 'phase_diff']):
        return ("fmap", "phasediff", None, False)
    
    # EPI with PA/AP might be field maps
    if ('_pa' in desc_lower or '_ap' in desc_lower) and 'epi' in desc_lower:
        return ("fmap", "epi", None, False)
    
    # Unknown - skip by default
    return (None, None, None, True)


def create_config_entry(series_desc: str) -> Optional[dict]:
    """Create a dcm2bids config entry for a SeriesDescription."""
    datatype, suffix, task_name, should_skip = categorize_series(series_desc)
    
    if should_skip or datatype is None:
        return None
    
    # Create base entry
    entry = {
        "id": series_desc.lower().replace(" ", "_").replace("-", "_"),
        "datatype": datatype,
        "suffix": suffix,
        "criteria": {
            "SeriesDescription": series_desc
        }
    }
    
    # Add task info for functional scans
    if datatype == "func" and task_name:
        entry["custom_entities"] = f"task-{task_name}"
        entry["sidecarChanges"] = {
            "TaskName": task_name
        }
    
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
        # Handle wildcard patterns - extract the core pattern
        clean_desc = series_desc.strip("*")
        existing.add(clean_desc)
        existing.add(series_desc)  # Also add the original pattern
    return existing


def backup_config(config_path: Path) -> Optional[Path]:
    """Create a backup of the config file."""
    if not config_path.exists():
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = config_path.with_suffix(f".backup_{timestamp}.json")
    shutil.copy(config_path, backup_path)
    return backup_path


def update_config(config: dict, series_info: dict) -> tuple:
    """
    Update config with new SeriesDescriptions.
    Returns (updated_config, new_entries, skipped_entries).
    """
    existing = get_existing_series_descriptions(config)
    new_entries = []
    skipped_entries = []
    
    for series_desc in sorted(series_info.keys()):
        # Check if already exists (exact or as part of wildcard)
        already_exists = False
        for existing_pattern in existing:
            if series_desc == existing_pattern:
                already_exists = True
                break
            # Check if existing wildcard matches this series
            if existing_pattern and existing_pattern in series_desc:
                already_exists = True
                break
        
        if already_exists:
            skipped_entries.append((series_desc, "already in config"))
            continue
        
        # Create new entry
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


def save_config(config: dict, config_path: Path):
    """Save config to file with nice formatting."""
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Extract SeriesDescriptions from DICOM files and update dcm2bids config."
    )
    parser.add_argument("dicom_folder", help="Path to folder containing DICOM files")
    parser.add_argument(
        "--config", "-c",
        default=None,
        help="Path to dcm2bids_config.json (default: auto-detect in project)"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Don't create backup of config file"
    )
    
    args = parser.parse_args()
    
    # Validate DICOM folder
    dicom_folder = Path(args.dicom_folder)
    if not dicom_folder.exists():
        print(f"Error: Folder not found: {dicom_folder}")
        sys.exit(1)
    
    # Find config file
    if args.config:
        config_path = Path(args.config)
    else:
        # Try to find config in common locations
        script_dir = Path(__file__).parent
        possible_paths = [
            script_dir.parent / "config" / "dcm2bids_config.json",
            script_dir / "dcm2bids_config.json",
            Path.cwd() / "config" / "dcm2bids_config.json",
            Path.cwd() / "dcm2bids_config.json",
        ]
        config_path = None
        for path in possible_paths:
            if path.exists():
                config_path = path
                break
        
        if config_path is None:
            config_path = script_dir.parent / "config" / "dcm2bids_config.json"
            print(f"Config file not found, will create: {config_path}")
    
    print(f"Config file: {config_path}")
    
    # Scan DICOM folder
    series_info = scan_folder(dicom_folder)
    
    if not series_info:
        print("\nNo DICOM files with SeriesDescription found.")
        sys.exit(1)
    
    # Print found series
    print("\n" + "=" * 80)
    print("SERIES DESCRIPTIONS FOUND IN DICOM FILES")
    print("=" * 80)
    print(f"\n{'SeriesDescription':<45} {'Category':<20} {'Files':>10}")
    print("-" * 80)
    
    for series_desc in sorted(series_info.keys()):
        info = series_info[series_desc]
        datatype, suffix, task, skip = categorize_series(series_desc)
        if skip:
            category = "SKIP (localizer/cal)"
        elif datatype:
            category = f"{datatype}/{suffix}"
            if task:
                category += f" (task-{task})"
        else:
            category = "unknown"
        print(f"{series_desc:<45} {category:<20} {info.count:>10}")
    
    # Load existing config
    config = load_config(config_path)
    
    # Update config
    updated_config, new_entries, skipped_entries = update_config(config, series_info)
    
    # Print results
    print("\n" + "=" * 80)
    print("CONFIG UPDATE SUMMARY")
    print("=" * 80)
    
    if new_entries:
        print(f"\n✅ NEW ENTRIES TO ADD ({len(new_entries)}):")
        for entry in new_entries:
            series_desc = entry["criteria"]["SeriesDescription"]
            print(f"   + {entry['datatype']}/{entry['suffix']}: {series_desc}")
    else:
        print("\n✅ No new entries needed - config is already complete!")
    
    if skipped_entries:
        print(f"\n⏭️  SKIPPED ({len(skipped_entries)}):")
        for series_desc, reason in skipped_entries:
            print(f"   - {series_desc}: {reason}")
    
    # Apply changes
    if args.dry_run:
        print("\n" + "=" * 80)
        print("DRY RUN - No changes made")
        print("=" * 80)
        if new_entries:
            print("\nNew entries that WOULD be added:\n")
            print(json.dumps(new_entries, indent=2))
    else:
        if new_entries:
            # Create backup
            if not args.no_backup and config_path.exists():
                backup_path = backup_config(config_path)
                print(f"\n📁 Backup created: {backup_path}")
            
            # Ensure parent directory exists
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save updated config
            save_config(updated_config, config_path)
            print(f"\n✅ Config updated: {config_path}")
            print(f"   Added {len(new_entries)} new entries")
        else:
            print("\n✅ Config file unchanged - no updates needed")
    
    print("\n" + "=" * 80)
    print("DONE")
    print("=" * 80)


if __name__ == "__main__":
    main()
