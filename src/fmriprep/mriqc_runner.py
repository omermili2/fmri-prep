"""
MRIQC runner using Docker - Layer 2

Runs MRIQC (MRI Quality Control) for automated image quality assessment.
Docker image: nipreps/mriqc:latest  (~4-6 GB, one-time download)

Key differences from fMRIPrep:
  - NO FreeSurfer license required
  - Two-step: participant level (per-subject) then group level (all subjects)
  - Faster: ~10 min for T1w, ~30-45 min for BOLD per subject

MRIQC outputs (written to <output_folder>/mriqc/):
  sub-001/anat/sub-001_T1w.html           visual T1w report + brain thumbnails
  sub-001/func/sub-001_task-rest_bold.html visual BOLD report + motion plots
  group_T1w.html                           group anatomical report + outlier flags
  group_bold.html                          group functional report + outlier flags
  sub-001_T1w.json                         raw Image Quality Metrics (IQMs)
  sub-001_task-rest_bold.json              raw BOLD IQMs
"""

import subprocess
import sys
from pathlib import Path

from .runner import check_docker, to_docker_path

MRIQC_IMAGE = "nipreps/mriqc:latest"


def is_mriqc_image_available() -> bool:
    """Check if the MRIQC Docker image is already downloaded."""
    try:
        result = subprocess.run(
            ["docker", "images", "-q", MRIQC_IMAGE],
            capture_output=True, text=True, timeout=30,
        )
        return bool(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def pull_mriqc_image(callback=None):
    """
    Pull the MRIQC Docker image (~4-6 GB).

    Returns: (success: bool, error: str or None)
    """
    if callback:
        callback(f"Downloading MRIQC image ({MRIQC_IMAGE})...")
        callback("First-time download: ~4-6 GB, may take 10-30 minutes...")
    try:
        process = subprocess.Popen(
            ["docker", "pull", MRIQC_IMAGE],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        for line in process.stdout:
            line = line.strip()
            if line and callback:
                if any(k in line for k in ("Pulling", "Downloading", "Extracting")):
                    callback(f"  {line[:80]}")
        process.wait()
        if process.returncode == 0:
            if callback:
                callback("MRIQC image downloaded successfully!")
            return True, None
        return False, "Failed to download MRIQC image."
    except Exception as e:
        return False, f"Error pulling MRIQC image: {e}"


def mriqc_preflight(callback=None, auto_pull=True):
    """
    Check all prerequisites for MRIQC (Docker only, no FreeSurfer license needed).

    Returns: (success: bool, error: str or None)
    """
    if callback:
        callback("Checking Docker for MRIQC...")
    docker_ok, docker_err = check_docker()
    if not docker_ok:
        return False, docker_err

    if not is_mriqc_image_available():
        if auto_pull:
            if callback:
                callback("MRIQC image not found — downloading automatically...")
            success, err = pull_mriqc_image(callback=callback)
            if not success:
                return False, (
                    f"MRIQC image not found and auto-pull failed.\n\n"
                    f"Run manually to download:\n  docker pull {MRIQC_IMAGE}\n\n"
                    f"Pull error: {err}"
                )
        else:
            return False, (
                f"MRIQC Docker image not found.\n\n"
                f"Download it (one-time, ~4-6 GB):\n  docker pull {MRIQC_IMAGE}"
            )

    if callback:
        callback("MRIQC pre-flight checks passed!")
    return True, None


def run_mriqc_participant(
    bids_dir,
    mriqc_output_dir,
    participant_label: str,
    nprocs: int = 4,
    mem_gb: int = 16,
    modalities=None,
):
    """
    Run MRIQC at the participant level for one subject.

    Produces HTML visual reports and JSON IQM files for all scans of this subject.

    Args:
        bids_dir:          Path to BIDS dataset
        mriqc_output_dir:  MRIQC output directory (e.g. output_folder/mriqc)
        participant_label: Subject ID WITHOUT 'sub-' prefix  (e.g. '001')
        nprocs:            CPU cores (default: 4)
        mem_gb:            Memory limit in GB (default: 16)
        modalities:        e.g. ['T1w', 'bold'] — None means auto-detect

    Returns: (success: bool, error: str or None)
    """
    docker_ok, docker_err = check_docker()
    if not docker_ok:
        return False, docker_err

    bids_dir = Path(bids_dir).resolve()
    mriqc_output_dir = Path(mriqc_output_dir).resolve()
    mriqc_output_dir.mkdir(parents=True, exist_ok=True)
    work_dir = mriqc_output_dir / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    bids_mount = to_docker_path(bids_dir)
    out_mount  = to_docker_path(mriqc_output_dir)
    work_mount = to_docker_path(work_dir)

    docker_cmd = [
        "docker", "run", "-t", "--rm",
        "-v", f"{bids_mount}:/data:ro",
        "-v", f"{out_mount}:/out",
        "-v", f"{work_mount}:/work",
    ]

    if sys.platform == "win32":
        docker_cmd.extend([
            "-e", "MPLCONFIGDIR=/tmp/mpl",
            "-e", "PYTHONUNBUFFERED=1",
            "--tmpfs", "/tmp:exec,mode=1777,size=2g",
        ])

    docker_cmd.extend([
        MRIQC_IMAGE,
        "/data", "/out",
        "participant",
        "--participant-label", participant_label,
        "--nprocs", str(nprocs),
        "--mem-gb", str(mem_gb),
        "-w", "/work",
        "--no-sub",
        "--float32",
    ])

    if modalities:
        docker_cmd.extend(["--modalities"] + modalities)

    print(f"Starting MRIQC (participant) for sub-{participant_label}")

    try:
        result = subprocess.run(
            docker_cmd,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )

        if result.stdout:
            print("--- MRIQC stdout ---")
            print(result.stdout[-3000:])
        if result.stderr:
            print("--- MRIQC stderr ---")
            print(result.stderr[-2000:])

        if result.returncode == 0:
            return True, None

        combined = (result.stdout or "") + (result.stderr or "")
        error_lines = [
            ln for ln in combined.split("\n")
            if any(k in ln.lower() for k in ("error", "failed", "exception", "traceback"))
        ]
        msg = f"MRIQC exited with code {result.returncode}\n"
        msg += "\n".join(error_lines[-15:]) if error_lines else combined[-1000:]
        return False, msg

    except KeyboardInterrupt:
        return False, "Interrupted by user"
    except FileNotFoundError:
        return False, "Docker not found. Is Docker installed and running?"
    except Exception as e:
        return False, f"Exception running MRIQC: {e}"


def run_mriqc_group(bids_dir, mriqc_output_dir, modalities=None):
    """
    Run MRIQC group-level report across all subjects.

    Generates group_T1w.html and group_bold.html containing:
    - IQM distributions across your entire cohort
    - Automatic outlier flagging (subjects who deviate from the group)
    - Interactive scatter plots per metric

    Must be called AFTER all participant-level runs have completed.

    Returns: (success: bool, error: str or None)
    """
    docker_ok, docker_err = check_docker()
    if not docker_ok:
        return False, docker_err

    bids_dir = Path(bids_dir).resolve()
    mriqc_output_dir = Path(mriqc_output_dir).resolve()
    work_dir = mriqc_output_dir / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    bids_mount = to_docker_path(bids_dir)
    out_mount  = to_docker_path(mriqc_output_dir)
    work_mount = to_docker_path(work_dir)

    docker_cmd = [
        "docker", "run", "-t", "--rm",
        "-v", f"{bids_mount}:/data:ro",
        "-v", f"{out_mount}:/out",
        "-v", f"{work_mount}:/work",
        MRIQC_IMAGE,
        "/data", "/out",
        "group",
        "-w", "/work",
        "--no-sub",
    ]

    if modalities:
        docker_cmd.extend(["--modalities"] + modalities)

    print("Running MRIQC group-level report...")

    try:
        result = subprocess.run(
            docker_cmd,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        if result.returncode == 0:
            return True, None
        combined = (result.stdout or "") + (result.stderr or "")
        return False, f"MRIQC group failed (code {result.returncode}):\n{combined[-1000:]}"
    except Exception as e:
        return False, f"Exception running MRIQC group: {e}"


def collect_mriqc_reports(mriqc_dir) -> dict:
    """
    Collect paths to all MRIQC HTML reports and IQM JSON files.

    Returns:
        {
          'subject_reports': [{'sub_id': '001', 'scan_type': 'anat'/'func',
                               'filename': '...', 'path': Path}],
          'group_reports':   [{'scan_type': 'T1w'/'bold', 'path': Path}],
          'iqm_files':       [{'sub_id': '001', 'modality': 'T1w', 'path': Path}],
        }
    """
    mriqc_path = Path(mriqc_dir)
    out = {"subject_reports": [], "group_reports": [], "iqm_files": []}

    if not mriqc_path.exists():
        return out

    for html in sorted(mriqc_path.glob("group_*.html")):
        out["group_reports"].append({
            "scan_type": html.stem.replace("group_", ""),
            "path": html,
        })

    for sub_dir in sorted(mriqc_path.glob("sub-*")):
        if not sub_dir.is_dir():
            continue
        sub_id = sub_dir.name.replace("sub-", "")
        for html in sorted(sub_dir.rglob("*.html")):
            out["subject_reports"].append({
                "sub_id": sub_id,
                "scan_type": html.parent.name,
                "filename": html.name,
                "path": html,
            })

    for json_file in sorted(mriqc_path.glob("sub-*.json")):
        stem = json_file.stem
        sub_id = stem.split("_")[0].replace("sub-", "")
        modality = "bold" if "bold" in stem else "T1w" if "T1w" in stem else "other"
        out["iqm_files"].append({
            "sub_id": sub_id,
            "modality": modality,
            "filename": json_file.name,
            "path": json_file,
        })

    return out
