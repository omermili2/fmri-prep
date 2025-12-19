#!/usr/bin/env python3
"""
fMRIPrep Runner Script (Cross-platform Python version)
Usage: python run_fmriprep.py <bids_dir> <output_dir> <participant_label> [freesurfer_license_path]
"""

import subprocess
import sys
import os
from pathlib import Path


def main():
    # Parse arguments
    if len(sys.argv) < 4:
        print("Usage: python run_fmriprep.py <bids_dir> <output_dir> <participant_label> [freesurfer_license_path]")
        sys.exit(1)
    
    bids_dir = Path(sys.argv[1]).resolve()
    output_dir = Path(sys.argv[2]).resolve()
    participant_label = sys.argv[3]
    
    # License path (default to project root)
    if len(sys.argv) > 4:
        license_path = Path(sys.argv[4]).resolve()
    else:
        # Look for license in common locations
        project_root = Path(__file__).parent.parent.resolve()
        license_candidates = [
            project_root / ".freesurfer_license.txt",
            project_root / "freesurfer_license.txt",
            Path.cwd() / ".freesurfer_license.txt",
        ]
        license_path = None
        for candidate in license_candidates:
            if candidate.exists():
                license_path = candidate
                break
        
        if not license_path:
            print("Warning: FreeSurfer license file not found. fMRIPrep may fail.")
            license_path = project_root / ".freesurfer_license.txt"
    
    # Check if Docker is available
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            print("Error: Docker is not running. Please start Docker Desktop.")
            sys.exit(1)
    except FileNotFoundError:
        print("Error: Docker is not installed or not in PATH.")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("Error: Docker is not responding. Please check Docker Desktop.")
        sys.exit(1)
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Starting fMRIPrep for participant: {participant_label}")
    print(f"BIDS Directory: {bids_dir}")
    print(f"Output Directory: {output_dir}")
    
    # Build Docker command
    # On Windows, paths need to be converted for Docker
    if sys.platform == 'win32':
        # Convert Windows paths to Docker-compatible format
        # Docker Desktop on Windows uses /c/Users/... format
        def to_docker_path(path):
            path_str = str(path)
            if len(path_str) > 1 and path_str[1] == ':':
                # Convert C:\Users\... to /c/Users/...
                drive = path_str[0].lower()
                return '/' + drive + path_str[2:].replace('\\', '/')
            return path_str.replace('\\', '/')
        
        bids_mount = to_docker_path(bids_dir)
        output_mount = to_docker_path(output_dir)
        license_mount = to_docker_path(license_path)
    else:
        bids_mount = str(bids_dir)
        output_mount = str(output_dir)
        license_mount = str(license_path)
    
    docker_cmd = [
        "docker", "run", "-t", "--rm",
        "-v", f"{bids_mount}:/data:ro",
        "-v", f"{output_mount}:/out",
        "-v", f"{license_mount}:/opt/freesurfer/license.txt:ro",
        "nipreps/fmriprep:latest",
        "/data", "/out",
        "participant",
        "--participant-label", participant_label,
        "--fs-no-reconall",
        "--skip-bids-validation",
        "--nthreads", "4",
        "--omp-nthreads", "4",
        "--mem_mb", "8000"
    ]
    
    print(f"\nRunning Docker command...")
    
    # Run fMRIPrep
    try:
        result = subprocess.run(docker_cmd, check=False)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Error running fMRIPrep: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

