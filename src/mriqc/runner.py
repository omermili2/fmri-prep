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

try:
    from ..fmriprep.runner import (
        check_docker, to_docker_path,
        is_docker_installed, is_docker_running, start_docker,
    )
except ImportError:
    from fmriprep.runner import (
        check_docker, to_docker_path,
        is_docker_installed, is_docker_running, start_docker,
    )

MRIQC_IMAGE = "nipreps/mriqc:24.0.2"

_PROJECT_PARENT = Path(__file__).parent.parent.parent.parent  # dir containing the project folder
_MRIQC_TAR_CANDIDATES = [
    "mriqc_24.0.2", "mriqc_24.0.2.tar", "mriqc-24.0.2", "mriqc-24.0.2.tar",
    "mriqc_latest", "mriqc_latest.tar", "mriqc.tar", "mriqc",
]


def _find_mriqc_tar():
    """Search the project's parent directory for a MRIQC Docker image archive."""
    for name in _MRIQC_TAR_CANDIDATES:
        p = _PROJECT_PARENT / name
        if p.exists():
            return p
    return None


def load_mriqc_from_tar(callback=None):
    """
    Load the MRIQC Docker image from a local tar archive in the project parent directory.

    Returns: (success: bool, error: str or None)
    """
    tar_path = _find_mriqc_tar()
    if tar_path is None:
        return False, f"No MRIQC tar found in {_PROJECT_PARENT}"
    if callback:
        callback(f"Loading MRIQC image from {tar_path.name}...")
    try:
        result = subprocess.run(
            ["docker", "load", "-i", str(tar_path)],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            if callback:
                callback("MRIQC image loaded successfully!")
            return True, None
        return False, f"docker load failed: {result.stderr.strip()[-500:]}"
    except subprocess.TimeoutExpired:
        return False, "docker load timed out (>5 min)"
    except Exception as e:
        return False, f"Error loading MRIQC image: {e}"


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


def mriqc_preflight(callback=None, auto_start_docker=True, auto_pull=True):
    """
    Check all prerequisites for MRIQC (Docker only, no FreeSurfer license needed).

    Mirrors the fMRIPrep preflight flow:
      1. Docker installed?
      2. Docker daemon running? (auto-start if possible)
      3. MRIQC image available? (auto-pull if missing)

    Returns: (success: bool, error: str or None)
    """
    if callback:
        callback("Checking Docker installation...")
    if not is_docker_installed():
        return False, (
            "Docker is not installed.\n\n"
            "Please install Docker Desktop:\n"
            "\u2022 macOS/Windows: https://www.docker.com/products/docker-desktop\n"
            "\u2022 Linux: https://docs.docker.com/engine/install/"
        )

    if callback:
        callback("Checking if Docker is running...")
    if not is_docker_running():
        if auto_start_docker:
            success, error = start_docker(timeout=90, callback=callback)
            if not success:
                return False, error
        else:
            return False, "Docker is not running. Please start Docker Desktop."

    if callback:
        callback("Checking MRIQC Docker image...")
    if not is_mriqc_image_available():
        if auto_pull:
            tar_path = _find_mriqc_tar()
            if tar_path is not None:
                if callback:
                    callback(f"MRIQC image not found \u2014 loading from {tar_path.name}...")
                success, err = load_mriqc_from_tar(callback=callback)
            else:
                success, err = False, "No local tar found"
            if not success:
                if callback:
                    callback(f"Tar load unavailable ({err}) \u2014 trying docker pull...")
                success, err = pull_mriqc_image(callback=callback)
            if not success:
                return False, (
                    f"MRIQC image not found and could not be loaded.\n\n"
                    f"Options:\n"
                    f"  1. Place a MRIQC tar in {_PROJECT_PARENT}\n"
                    f"  2. Run: docker pull {MRIQC_IMAGE}\n\n"
                    f"Error: {err}"
                )
        else:
            return False, (
                f"MRIQC Docker image not found.\n\n"
                f"Download it:\n  docker pull {MRIQC_IMAGE}"
            )

    if callback:
        callback("MRIQC pre-flight checks passed!")
    return True, None


def get_docker_vm_resources():
    """Return (cpus, mem_gb) available inside the Docker VM.

    Returns ``(None, None)`` if detection fails (e.g. Docker not running).
    """
    try:
        result = subprocess.run(
            ["docker", "run", "--rm", "alpine", "sh", "-c",
             "nproc && awk '/MemTotal/{printf \"%.0f\", $2/1048576}' /proc/meminfo"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if len(lines) >= 2:
                return int(lines[0]), int(lines[1])
    except Exception:
        pass
    return None, None


def run_mriqc_participant(
    bids_dir,
    mriqc_output_dir,
    participant_label: str,
    session_id: str = None,
    nprocs: int = 4,
    omp_nthreads: int = None,
    mem_gb: int = 16,
    modalities=None,
):
    """
    Run MRIQC at the participant level for one subject (optionally one session).

    Produces HTML visual reports and JSON IQM files for the scans of this
    subject/session.

    Args:
        bids_dir:          Path to BIDS dataset
        mriqc_output_dir:  MRIQC output directory (e.g. output_folder/mriqc)
        participant_label: Subject ID WITHOUT 'sub-' prefix  (e.g. '001')
        session_id:        Session ID WITHOUT 'ses-' prefix  (e.g. '01').
                           None = process all sessions for this subject.
        nprocs:            Parallel scan workflows (default: 4)
        omp_nthreads:      OpenMP threads per workflow — controls thread-level
                           parallelism within each scan's computation.
                           None = same as nprocs.
        mem_gb:            Memory limit in GB (default: 16)
        modalities:        e.g. ['T1w', 'bold'] — None means auto-detect

    Returns: (success: bool, error: str or None)
    """
    docker_ok, docker_err = check_docker()
    if not docker_ok:
        return False, docker_err

    if omp_nthreads is None:
        omp_nthreads = nprocs

    bids_dir = Path(bids_dir).resolve()
    mriqc_output_dir = Path(mriqc_output_dir).resolve()
    mriqc_output_dir.mkdir(parents=True, exist_ok=True)

    # Use per-session work dirs to avoid file collisions between parallel
    # containers writing to the same MRIQC work tree.
    if session_id:
        work_dir = mriqc_output_dir / "work" / f"sub-{participant_label}_ses-{session_id}"
    else:
        work_dir = mriqc_output_dir / "work" / f"sub-{participant_label}"
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
        "--omp-nthreads", str(omp_nthreads),
        "--mem-gb", str(mem_gb),
        "-w", "/work",
        "--no-sub",
        "--float32",
    ])

    if session_id:
        docker_cmd.extend(["--session-id", session_id])

    if modalities:
        docker_cmd.extend(["--modalities"] + modalities)

    label = f"sub-{participant_label}"
    if session_id:
        label += f"/ses-{session_id}"
    print(f"Starting MRIQC (participant) for {label}")

    try:
        result = subprocess.run(
            docker_cmd,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )

        if result.stdout:
            print(f"--- MRIQC stdout ({label}) ---")
            print(result.stdout[-3000:])
        if result.stderr:
            print(f"--- MRIQC stderr ({label}) ---")
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
          'carpet_plots':    {'sub-010_ses-01_task-memory_run-01_bold': Path, ...},
        }
    """
    mriqc_path = Path(mriqc_dir)
    out = {"subject_reports": [], "group_reports": [], "iqm_files": [],
           "carpet_plots": {}}

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

    # Use rglob to find IQM JSON files in both flat layout (older MRIQC) and
    # BIDS-derivatives layout (MRIQC ≥22.x: sub-XXX/ses-YYY/anat|func/).
    for json_file in sorted(mriqc_path.rglob("sub-*.json")):
        if "work" in json_file.parts:
            continue
        stem = json_file.stem
        # Skip non-IQM JSON files (e.g., timeseries, confounds)
        if not any(stem.endswith(s) for s in ("_T1w", "_T2w", "_bold")):
            continue
        sub_id = stem.split("_")[0].replace("sub-", "")
        modality = "bold" if "bold" in stem else "T1w" if "T1w" in stem else "other"
        out["iqm_files"].append({
            "sub_id": sub_id,
            "modality": modality,
            "filename": json_file.name,
            "path": json_file,
        })

    # Collect carpet plot SVGs for BOLD runs.
    # MRIQC writes them to {mriqc_dir}/sub-*/figures/ and fMRIPrep writes
    # similar plots to {derivatives_dir}/sub-*/figures/.  Search both locations
    # so the report can surface whichever is available.
    import re
    _carpet_re = re.compile(r"_desc-carpet(?:plot)?_")
    search_roots = [mriqc_path]
    derivatives_dir = mriqc_path.parent
    if derivatives_dir.exists() and derivatives_dir != mriqc_path:
        search_roots.append(derivatives_dir)
    for root in search_roots:
        for svg in sorted(root.glob("sub-*/figures/*_desc-carpet*_bold.svg")):
            if "work" in svg.parts:
                continue
            # Build a key that matches the IQM scan_file stem by stripping
            # the _desc-carpet(plot)_ entity from the filename stem.
            key = _carpet_re.sub("_", svg.stem)
            if key not in out["carpet_plots"]:
                out["carpet_plots"][key] = svg

    return out
