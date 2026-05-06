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
    from .fieldmap_intendedfor import populate_intended_for
except ImportError:
    from core.utils import safe_print
    from bids.fieldmap_intendedfor import populate_intended_for


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
            return False, duration, error_msg, []
        
        # Log dcm2niix output for debugging
        if result.stdout:
            lines = result.stdout.strip().split('\n')
            converted_count = sum(1 for line in lines if 'Convert' in line)
            safe_print(f"[{task_label}] dcm2niix converted {converted_count} series", flush=True)
        
        # Now organize converted files into BIDS structure
        organized, bold_notes = _organize_to_bids(temp_dir, bids_path, sub_id, ses_id)

        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)

        duration = (datetime.now() - start_time).total_seconds()

        if organized > 0:
            safe_print(f"[OK] {task_label} - BIDS completed ({organized} files, {duration:.1f}s)", flush=True)
            return True, duration, None, bold_notes
        else:
            error_msg = "No files were organized into BIDS structure"
            safe_print(f"[WARN] {task_label} - {error_msg}", flush=True)
            return False, duration, error_msg, bold_notes
            
    except subprocess.TimeoutExpired:
        duration = (datetime.now() - start_time).total_seconds()
        error_msg = f"Conversion timed out after {timeout // 60} minutes"
        safe_print(f"[FAIL] {task_label} - dcm2niix timed out", flush=True)
        return False, duration, error_msg, []

    except FileNotFoundError:
        duration = (datetime.now() - start_time).total_seconds()
        error_msg = "dcm2niix not found. Please ensure dcm2niix is installed and in PATH"
        safe_print(f"[FAIL] {task_label} - dcm2niix not found", flush=True)
        return False, duration, error_msg, []

    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        safe_print(f"[FAIL] {task_label} - dcm2niix conversion failed: {e}", flush=True)
        return False, duration, str(e), []


def _organize_to_bids(temp_dir, bids_dir, sub_id, ses_id):
    """
    Organize dcm2niix output into BIDS structure based on JSON metadata.

    Reads each JSON sidecar to determine modality and organizes files accordingly.
    BOLD scans with fewer than _MIN_BOLD_VOLUMES timepoints are dropped as
    dcm2niix split artifacts.

    Returns:
        Tuple of (files_organized: int, bold_notes: list[dict])
        Each bold_note is {"action": "dropped"|"kept", "task": str,
                           "file": str, "volumes": int, "series_desc": str}
    """
    temp_path = Path(temp_dir)
    bids_path = Path(bids_dir)
    organized_count = 0
    skipped_count = 0
    bold_notes = []

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

        # Try to auto-fill missing PhaseEncodingDirection for fieldmap EPIs
        _infer_phase_encoding_direction(metadata, series_desc, json_file.name)

        modality_info = _classify_scan(metadata, series_desc)

        # Fallback: detect BOLD by NIfTI volume count when keywords fail
        if modality_info is None:
            modality_info = _classify_bold_by_volume(nii_file, metadata)

        if modality_info is None:
            skipped_count += 1
            safe_print(f"  Unrecognized: {metadata.get('SeriesDescription', 'NO_DESC')} ({json_file.name})", flush=True)
            continue

        datatype, suffix, entities = modality_info

        # Skip DWI/diffusion scans — this pipeline only processes T1w and BOLD
        if datatype == "dwi":
            skipped_count += 1
            continue

        # --- Drop BOLD fragments with too few volumes ---
        n_vols = None
        if datatype == "func":
            n_vols = _get_nifti_volumes(nii_file)
            if n_vols is not None and n_vols < _MIN_BOLD_VOLUMES:
                task_match = re.search(r'task-(\w+)', entities)
                task_name = task_match.group(1) if task_match else "unknown"
                bold_notes.append({
                    "action": "dropped",
                    "task": task_name,
                    "file": json_file.stem,
                    "volumes": n_vols,
                    "series_desc": metadata.get("SeriesDescription", ""),
                })
                safe_print(
                    f"  Dropped BOLD fragment ({n_vols} vols < {_MIN_BOLD_VOLUMES}): "
                    f"{metadata.get('SeriesDescription', 'N/A')} ({json_file.name})",
                    flush=True,
                )
                skipped_count += 1
                continue

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

        # Record kept BOLD with its BIDS output path
        if datatype == "func" and n_vols is not None:
            task_match = re.search(r'task-(\w+)', entities)
            task_name = task_match.group(1) if task_match else "unknown"
            bold_notes.append({
                "action": "kept",
                "task": task_name,
                "file": json_file.stem,
                "volumes": n_vols,
                "series_desc": metadata.get("SeriesDescription", ""),
                "bids_nii_path": str(out_nii),
                "bids_json_path": str(out_json),
            })

        shutil.copy2(nii_file, out_nii)

        # Repair NIfTI headers with sform_code/qform_code == 0.
        # dcm2niix sometimes produces fieldmap EPIs with zeroed codes, which
        # causes the BIDS validator to flag them as errors.  Setting both to 1
        # (scanner-anat) and copying the qform into the sform is the standard
        # fix and matches what most tools expect.
        if datatype == "fmap":
            try:
                import nibabel as nib
                img = nib.load(str(out_nii))
                hdr = img.header
                if int(hdr['sform_code']) == 0 or int(hdr['qform_code']) == 0:
                    hdr['qform_code'] = 1
                    hdr['sform_code'] = 1
                    hdr.set_sform(hdr.get_qform())
                    nib.save(img, str(out_nii))
                    safe_print(f"  Fixed sform/qform for {out_nii.name}", flush=True)
            except Exception as e:
                safe_print(f"  Warning: could not fix NIfTI header for {out_nii.name}: {e}", flush=True)

        # Write (possibly updated) metadata back out to BIDS JSON
        try:
            with open(out_json, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=4)
        except Exception as e:
            # Fallback to raw copy if we cannot write updated JSON
            safe_print(f"  Warning: could not write updated JSON for {json_file.name}: {e}", flush=True)
            shutil.copy2(json_file, out_json)
        organized_count += 1
        safe_print(f"  Organized: {series_desc} -> {datatype}/{suffix}", flush=True)
    
    if skipped_count > 0:
        safe_print(f"  Warning: {skipped_count} scans were not recognized and skipped", flush=True)

    # --- Post-processing: mark shorter duplicate BOLD runs for fMRIPrep exclusion ---
    # When the same task has multiple runs in a session (e.g. aborted + re-run),
    # exclude the shorter run from fMRIPrep but keep it in the BIDS directory.
    kept = [n for n in bold_notes if n["action"] == "kept"]
    from collections import Counter
    task_counts = Counter(n["task"] for n in kept)
    for task_name, count in task_counts.items():
        if count <= 1:
            continue
        task_runs = [n for n in kept if n["task"] == task_name]
        longest = max(task_runs, key=lambda n: n["volumes"])
        for run in task_runs:
            if run is not longest:
                run["action"] = "kept_excluded"
                safe_print(
                    f"  Excluding shorter duplicate from fMRIPrep: "
                    f"task-{task_name} ({run['volumes']} vols) — "
                    f"keeping {longest['volumes']} vols",
                    flush=True,
                )

    # --- Strip run numbers when only one run of a task remains ---
    # BIDS convention: run-XX is only needed when there are multiple runs
    # of the same task in a session.  If duplicates were excluded (or only
    # one run existed in the first place), rename to remove the run entity
    # so fMRIPrep and downstream tools don't show a misleading run number.
    final_kept = [n for n in bold_notes if n["action"] == "kept"]
    final_task_counts = Counter(n["task"] for n in final_kept)
    for task_name, count in final_task_counts.items():
        if count != 1:
            continue
        note = next(n for n in final_kept if n["task"] == task_name)
        nii_path = Path(note["bids_nii_path"])
        json_path = Path(note["bids_json_path"])
        new_nii_name = re.sub(r'_run-\d+', '', nii_path.name)
        new_json_name = re.sub(r'_run-\d+', '', json_path.name)
        # Only rename if the name actually changed (has a run entity)
        if new_nii_name != nii_path.name:
            new_nii = nii_path.parent / new_nii_name
            new_json = json_path.parent / new_json_name
            if nii_path.exists():
                nii_path.rename(new_nii)
            if json_path.exists():
                json_path.rename(new_json)
            note["bids_nii_path"] = str(new_nii)
            note["bids_json_path"] = str(new_json)

    # Log summary of BOLD disposition
    dropped = [n for n in bold_notes if n["action"] == "dropped"]
    excluded = [n for n in bold_notes if n["action"] == "kept_excluded"]
    final_kept = [n for n in bold_notes if n["action"] == "kept"]
    parts = [f"{len(final_kept)} run(s) kept"]
    if excluded:
        parts.append(f"{len(excluded)} duplicate(s) excluded from fMRIPrep")
    if dropped:
        parts.append(f"{len(dropped)} fragment(s) dropped")
    if excluded or dropped:
        safe_print(f"  BOLD summary: {', '.join(parts)}", flush=True)

    # Populate IntendedFor in fieldmap sidecars so fMRIPrep applies SDC
    session_dir = bids_path / f"sub-{sub_id}" / f"ses-{ses_id}"
    try:
        populate_intended_for(session_dir)
    except Exception as e:
        safe_print(f"  Warning: IntendedFor population failed: {e}", flush=True)

    return organized_count, bold_notes


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
    
    # Check for diffusion BEFORE fieldmaps — DWI series may contain "ap"/"pa"
    # in their SeriesDescription (e.g. "dwi_AP", "cmrr_mbep2d_diff_ap") and
    # must not be misclassified as fieldmap EPIs.
    _DIFFUSION_KEYS = (
        "bValue", "bValues", "bval",
        "DiffusionGradientOrientation",
        "DiffusionBValue", "DiffusionDirection",
    )
    # Substring check for full keywords
    is_diffusion = any(x in series_desc for x in ["dwi", "dti", "diffusion", "hardi"])
    # Segment check for "diff" — catches CMRR/Siemens naming (e.g.
    # "mbep2d_diff_ap") without false-positives from "phase_difference".
    if not is_diffusion:
        _desc_segments = set(re.split(r'[_\-\(\)]', series_desc))
        is_diffusion = "diff" in _desc_segments
    has_diffusion_meta = any(k in metadata for k in _DIFFUSION_KEYS)
    if is_diffusion or has_diffusion_meta:
        return ("dwi", "dwi", "")

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
    
    # Check for perfusion
    if any(x in series_desc for x in ["asl", "pcasl", "pasl"]):
        return ("perf", "asl", "")
    
    # Fallback: try to detect by ImageType or other metadata
    image_type = metadata.get("ImageType", [])
    if isinstance(image_type, list):
        if "FMRI" in image_type or "BOLD" in image_type:
            return ("func", "bold", "task-unknown")
    
    return None


# Minimum number of timepoints required to consider a 4-D NIfTI as BOLD.
# Typical BOLD runs have 100-1500 volumes.  Diffusion scans have 60-130.
# Multi-echo anatomicals have < 10.  A threshold of 50 avoids all non-BOLD
# 4-D data while catching even short BOLD runs.
_MIN_BOLD_VOLUMES = 50


def _get_nifti_volumes(nii_path):
    """Return number of volumes (4th dimension) from a NIfTI file, or None."""
    try:
        import nibabel as nib
        shape = nib.load(str(nii_path)).shape
        return shape[3] if len(shape) >= 4 else 1
    except Exception:
        return None


def _classify_bold_by_volume(nii_path, metadata):
    """
    Fallback BOLD classification using NIfTI header properties.

    Called only when keyword-based ``_classify_scan`` returned ``None``.
    Detects BOLD scans whose SeriesDescription is non-standard (e.g.
    "10m", "24m") by checking:

    1. The NIfTI is 4-D with >= 50 timepoints.
    2. RepetitionTime (if present) is in the typical BOLD range (0.2-5.0 s).
    3. No diffusion gradient metadata (to exclude DTI/DWI).
    4. Not a known non-functional modality (localiser, scout, SBRef, etc.).

    Returns:
        Tuple ``(datatype, suffix, entities)`` or ``None``.
    """
    try:
        import nibabel as nib
        img = nib.load(str(nii_path))
        shape = img.shape

        # Must be 4-D with enough timepoints
        if len(shape) < 4 or shape[3] < _MIN_BOLD_VOLUMES:
            return None

        n_volumes = shape[3]

        # ---- Exclusion checks ----

        # Diffusion scans are also 4-D but carry gradient metadata
        _DIFFUSION_KEYS = (
            "bValue", "bValues", "bval",
            "DiffusionGradientOrientation",
            "DiffusionBValue", "DiffusionDirection",
        )
        if any(k in metadata for k in _DIFFUSION_KEYS):
            return None

        # RepetitionTime sanity (only reject if present AND out of range)
        tr = metadata.get("RepetitionTime")
        if tr is not None and (tr < 0.2 or tr > 5.0):
            return None

        # Skip derived / secondary images (SBRef, phase maps, scout composites)
        series_desc = metadata.get("SeriesDescription", "").lower()
        _NON_BOLD_HINTS = (
            "sbref", "phase", "scout", "localizer", "localiser",
            "setter", "noise", "phoenix", "moco", "adc",
        )
        if any(h in series_desc for h in _NON_BOLD_HINTS):
            return None

        image_type = metadata.get("ImageType", [])
        if isinstance(image_type, list):
            if "DERIVED" in image_type or "SECONDARY" in image_type:
                return None

        # ---- Looks like BOLD: extract task name ----
        task = _extract_task_from_description(series_desc)

        tr_str = f"TR={tr:.2f}s" if tr is not None else "TR=unknown"
        safe_print(
            f"  Detected BOLD by volume count "
            f"({n_volumes} vols, {tr_str}): "
            f"{metadata.get('SeriesDescription', 'N/A')}",
            flush=True,
        )

        return ("func", "bold", f"task-{task}")

    except ImportError:
        # nibabel not installed — cannot inspect NIfTI header
        return None
    except Exception:
        # Never let a fallback heuristic crash the pipeline
        return None


def _extract_task_from_description(series_desc):
    """
    Best-effort task-name extraction from a (lowered) SeriesDescription.

    Re-uses the same heuristics as the main classifier but returns
    ``"unknown"`` instead of ``None`` when nothing matches.
    """
    # Explicit task-<name>
    m = re.search(r'task[_-]([a-zA-Z]+)', series_desc)
    if m:
        return m.group(1).lower()

    _KNOWN_TASKS = [
        "rest", "memory", "movie", "music", "story",
        "sound", "faces", "motor", "nf", "neurofeedback",
        "word", "wordpairs",
    ]
    for t in _KNOWN_TASKS:
        if t in series_desc:
            return t

    # Trailing word after a separator (e.g. "bold-rest")
    m = re.search(r'[-_]([a-zA-Z]+)\d*$', series_desc)
    if m and m.group(1).lower() not in ("m",):  # exclude bare "m" from e.g. "10m"
        return m.group(1).lower()

    return "unknown"


def _infer_phase_encoding_direction(metadata, series_desc, json_name=""):
    """
    Best-effort inference of PhaseEncodingDirection for fieldmap EPIs.

    Some scanners / dcm2niix combinations do not populate the BIDS
    PhaseEncodingDirection field, which causes fMRIPrep to fail on
    EPI fieldmaps. Here we try to infer a reasonable value when:

    - The series looks like an EPI fieldmap (AP/PA, se_epi, spinecho, topup)
    - PhaseEncodingDirection is missing or empty

    Heuristics (conservative):
    - If JSON already has PhaseEncodingDirection -> keep it
    - Else, if "ap" in SeriesDescription and not "pa" -> assume dir-AP, use "j-"
    - Else, if "pa" in SeriesDescription and not "ap" -> assume dir-PA, use "j"

    Notes:
    - The sign (j vs j-) is a heuristic based on common AP/PA conventions
      with dcm2niix, but users should verify for their scanner if possible.
    - We log a warning the first time we infer a direction so users are aware.
    """
    try:
        phase_dir = metadata.get("PhaseEncodingDirection", "")
        if phase_dir:
            return  # Nothing to do

        # Only consider likely fieldmap EPIs
        is_fmap_candidate = any(
            x in series_desc for x in ["ap", "pa", "se_epi", "spinecho", "topup", "distortion"]
        )
        if not is_fmap_candidate:
            return

        inferred = None
        if "ap" in series_desc and "pa" not in series_desc:
            inferred = "j-"
        elif "pa" in series_desc and "ap" not in series_desc:
            inferred = "j"

        if inferred:
            metadata["PhaseEncodingDirection"] = inferred
            safe_print(
                f"  Inferred PhaseEncodingDirection='{inferred}' for {json_name} "
                f"(SeriesDescription='{series_desc}')",
                flush=True,
            )
    except Exception:
        # Never let inference failure break conversion
        return


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


# -- fMRIPrep BOLD exclusion helpers ------------------------------------------

_EXCLUDE_SUFFIX = "._excluded_from_fmriprep"


def get_excluded_bold_paths(bold_notes):
    """Extract BIDS NIfTI+JSON paths that should be hidden from fMRIPrep.

    Args:
        bold_notes: List of bold_note dicts from ``_organize_to_bids()``.

    Returns:
        List of (nii_path, json_path) tuples.
    """
    pairs = []
    for n in bold_notes:
        if n.get("action") == "kept_excluded":
            nii = n.get("bids_nii_path")
            jsn = n.get("bids_json_path")
            if nii:
                pairs.append((nii, jsn))
    return pairs


def hide_excluded_bold(pairs):
    """Temporarily rename excluded BOLD files so pybids/fMRIPrep won't see them.

    Renames each file by appending ``._excluded_from_fmriprep``.
    Returns the list of (original, renamed) tuples for later restoration.
    """
    renamed = []
    for nii, jsn in pairs:
        for p in (nii, jsn):
            if p is None:
                continue
            src = Path(p)
            if src.exists():
                dst = src.with_name(src.name + _EXCLUDE_SUFFIX)
                src.rename(dst)
                renamed.append((str(dst), str(src)))
    return renamed


def restore_excluded_bold(renamed):
    """Restore files hidden by :func:`hide_excluded_bold`.

    ``renamed`` is the list returned by ``hide_excluded_bold``.
    """
    for hidden, original in renamed:
        src = Path(hidden)
        if src.exists():
            src.rename(Path(original))
