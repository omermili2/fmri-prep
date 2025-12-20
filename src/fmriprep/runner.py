"""
fMRIPrep runner using Docker.

This module provides a Python interface to run fMRIPrep via Docker,
with support for cross-platform path conversion and configurable options.
"""

import subprocess
import sys
from pathlib import Path


def to_docker_path(path):
    """
    Convert paths to Docker-compatible format.
    
    On Windows, converts 'C:\\Users\\...' to '/c/Users/...'
    On Unix systems, returns the path with forward slashes.
    
    Args:
        path: Path to convert
        
    Returns:
        Docker-compatible path string
    """
    path_str = str(path)
    if sys.platform == 'win32' and len(path_str) > 1 and path_str[1] == ':':
        # Convert C:\Users\... to /c/Users/...
        drive = path_str[0].lower()
        return '/' + drive + path_str[2:].replace('\\', '/')
    return path_str.replace('\\', '/')


def find_freesurfer_license():
    """
    Search for FreeSurfer license file in common locations.
    
    Checks:
    1. Project root directory
    2. Current working directory
    3. Home directory
    
    Returns:
        Path to license file, or None if not found
    """
    project_root = Path(__file__).parent.parent.parent.resolve()
    license_candidates = [
        project_root / ".freesurfer_license.txt",
        project_root / "freesurfer_license.txt",
        Path.cwd() / ".freesurfer_license.txt",
        Path.home() / ".freesurfer_license.txt",
    ]
    for candidate in license_candidates:
        if candidate.exists():
            return candidate
    return None


def check_docker():
    """
    Check if Docker is available and running.
    
    Returns:
        Tuple of (available: bool, error_message: str or None)
    """
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            return False, "Docker is not running. Please start Docker Desktop."
        return True, None
    except FileNotFoundError:
        return False, "Docker is not installed or not in PATH."
    except subprocess.TimeoutExpired:
        return False, "Docker is not responding. Please check Docker Desktop."


def run_fmriprep(
    bids_dir,
    output_dir,
    participant_label,
    license_path=None,
    output_spaces=None,
    fs_reconall=False,
    skip_slice_timing=False,
    use_syn_sdc=False,
    use_aroma=False,
    mem_mb=16000,
    nthreads=4
):
    """
    Run fMRIPrep preprocessing via Docker.
    
    Args:
        bids_dir: Path to BIDS dataset
        output_dir: Path to output directory
        participant_label: Participant label (without 'sub-' prefix)
        license_path: Path to FreeSurfer license file (auto-detected if None)
        output_spaces: List of output spaces (default: ['MNI152NLin2009cAsym'])
        fs_reconall: Whether to run FreeSurfer reconall (adds ~6 hours)
        skip_slice_timing: Whether to skip slice timing correction
        use_syn_sdc: Whether to use SyN-based distortion correction
        use_aroma: Whether to use ICA-AROMA denoising
        mem_mb: Memory limit in MB (default: 16000)
        nthreads: Number of CPU threads (default: 4)
        
    Returns:
        Tuple of (success: bool, error_message: str or None)
    """
    # Check Docker
    docker_ok, docker_error = check_docker()
    if not docker_ok:
        return False, docker_error
    
    # Resolve paths
    bids_dir = Path(bids_dir).resolve()
    output_dir = Path(output_dir).resolve()
    
    # Find license
    if license_path:
        license_path = Path(license_path).resolve()
    else:
        license_path = find_freesurfer_license()
        if not license_path:
            return False, "FreeSurfer license file not found. Create .freesurfer_license.txt in the project root."
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Set default output spaces
    if output_spaces is None:
        output_spaces = ['MNI152NLin2009cAsym']
    
    # Build Docker command
    bids_mount = to_docker_path(bids_dir)
    output_mount = to_docker_path(output_dir)
    license_mount = to_docker_path(license_path)
    
    docker_cmd = [
        "docker", "run", "-t", "--rm",
        "-v", f"{bids_mount}:/data:ro",
        "-v", f"{output_mount}:/out",
        "-v", f"{license_mount}:/opt/freesurfer/license.txt:ro",
        "nipreps/fmriprep:latest",
        "/data", "/out",
        "participant",
        "--participant-label", participant_label,
        "--skip-bids-validation",
    ]
    
    # Add output spaces
    docker_cmd.extend(["--output-spaces"] + output_spaces)
    
    # Add FreeSurfer option
    if not fs_reconall:
        docker_cmd.append("--fs-no-reconall")
    
    # Add slice timing option
    if skip_slice_timing:
        docker_cmd.extend(["--ignore", "slicetiming"])
    
    # Add SDC option
    if use_syn_sdc:
        docker_cmd.append("--use-syn-sdc")
    
    # Add AROMA option
    if use_aroma:
        docker_cmd.append("--use-aroma")
    
    # Add resource limits
    docker_cmd.extend(["--mem_mb", str(mem_mb)])
    docker_cmd.extend(["--nthreads", str(nthreads)])
    docker_cmd.extend(["--omp-nthreads", str(nthreads)])
    
    print(f"Starting fMRIPrep for participant: {participant_label}")
    print(f"BIDS Directory: {bids_dir}")
    print(f"Output Directory: {output_dir}")
    print(f"Options: spaces={output_spaces}, fs_reconall={fs_reconall}")
    
    # Run fMRIPrep
    try:
        result = subprocess.run(docker_cmd, check=False)
        if result.returncode == 0:
            return True, None
        else:
            return False, f"fMRIPrep exited with code {result.returncode}"
    except KeyboardInterrupt:
        return False, "Interrupted by user"
    except Exception as e:
        return False, str(e)


# Command-line interface for backward compatibility
def main():
    """
    Command-line interface for fMRIPrep runner.
    
    Usage: python -m src.fmriprep.runner <bids_dir> <output_dir> <participant_label> [options]
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="Run fMRIPrep via Docker")
    parser.add_argument("bids_dir", help="Path to BIDS dataset")
    parser.add_argument("output_dir", help="Path to output directory")
    parser.add_argument("participant_label", help="Participant label (without sub- prefix)")
    parser.add_argument("--license", help="Path to FreeSurfer license file")
    parser.add_argument("--extra-args", type=str, default="",
                        help="Comma-separated extra arguments for fMRIPrep")
    
    args = parser.parse_args()
    
    # Parse extra arguments to determine options
    extra_args = args.extra_args.split(",") if args.extra_args else []
    extra_args_str = " ".join(extra_args)
    
    # Determine options from extra args
    output_spaces = None
    for arg in extra_args:
        if arg.startswith("--output-spaces"):
            parts = arg.split(" ", 1)
            if len(parts) > 1:
                output_spaces = parts[1].split()
    
    fs_reconall = "--fs-no-reconall" not in extra_args_str
    skip_slice_timing = "slicetiming" in extra_args_str
    use_syn_sdc = "--use-syn-sdc" in extra_args_str
    use_aroma = "--use-aroma" in extra_args_str
    
    success, error = run_fmriprep(
        args.bids_dir,
        args.output_dir,
        args.participant_label,
        license_path=args.license,
        output_spaces=output_spaces,
        fs_reconall=fs_reconall,
        skip_slice_timing=skip_slice_timing,
        use_syn_sdc=use_syn_sdc,
        use_aroma=use_aroma
    )
    
    if not success:
        print(f"Error: {error}")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()

