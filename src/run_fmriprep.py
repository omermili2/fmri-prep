#!/usr/bin/env python3
"""
fMRIPrep Runner Script (Cross-platform Python version)
Usage: python run_fmriprep.py <bids_dir> <output_dir> <participant_label> [options]
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path


def to_docker_path(path):
    """Convert Windows paths to Docker-compatible format."""
    path_str = str(path)
    if sys.platform == 'win32' and len(path_str) > 1 and path_str[1] == ':':
        # Convert C:\Users\... to /c/Users/...
        drive = path_str[0].lower()
        return '/' + drive + path_str[2:].replace('\\', '/')
    return path_str.replace('\\', '/')


def find_license():
    """Find FreeSurfer license file."""
    project_root = Path(__file__).parent.parent.resolve()
    license_candidates = [
        project_root / ".freesurfer_license.txt",
        project_root / "freesurfer_license.txt",
        Path.cwd() / ".freesurfer_license.txt",
    ]
    for candidate in license_candidates:
        if candidate.exists():
            return candidate
    return None


def main():
    parser = argparse.ArgumentParser(description="Run fMRIPrep via Docker")
    parser.add_argument("bids_dir", help="Path to BIDS dataset")
    parser.add_argument("output_dir", help="Path to output directory")
    parser.add_argument("participant_label", help="Participant label (without sub- prefix)")
    parser.add_argument("--license", help="Path to FreeSurfer license file")
    parser.add_argument("--extra-args", type=str, default="",
                        help="Comma-separated extra arguments for fMRIPrep")
    
    args = parser.parse_args()
    
    bids_dir = Path(args.bids_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    participant_label = args.participant_label
    
    # Find license
    if args.license:
        license_path = Path(args.license).resolve()
    else:
        license_path = find_license()
        if not license_path:
            print("Warning: FreeSurfer license file not found. fMRIPrep may fail.")
            license_path = Path(__file__).parent.parent / ".freesurfer_license.txt"
    
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
    
    # Parse extra arguments
    extra_args = []
    if args.extra_args:
        # Split by comma and process each argument
        for arg in args.extra_args.split(","):
            arg = arg.strip()
            if arg:
                extra_args.append(arg)
    
    # Build Docker command with defaults
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
    
    # Add default options if not overridden by extra_args
    extra_args_str = " ".join(extra_args)
    
    # Output spaces - use provided or default to MNI
    if "--output-spaces" not in extra_args_str:
        docker_cmd.extend(["--output-spaces", "MNI152NLin2009cAsym"])
    
    # FreeSurfer - skip by default unless enabled
    if "--fs-no-reconall" not in extra_args_str and "freesurfer" not in extra_args_str.lower():
        docker_cmd.append("--fs-no-reconall")
    
    # Memory - use provided or default
    if "--mem-mb" not in extra_args_str and "--mem_mb" not in extra_args_str:
        docker_cmd.extend(["--mem_mb", "16000"])
    
    # Threads - use provided or default
    if "--nthreads" not in extra_args_str:
        docker_cmd.extend(["--nthreads", "4"])
    
    if "--omp-nthreads" not in extra_args_str:
        docker_cmd.extend(["--omp-nthreads", "4"])
    
    # Add extra arguments from GUI
    for arg in extra_args:
        # Handle space-separated key-value pairs
        parts = arg.split(" ", 1)
        docker_cmd.append(parts[0])
        if len(parts) > 1:
            docker_cmd.append(parts[1])
    
    print(f"\nfMRIPrep options: {' '.join(docker_cmd[docker_cmd.index('participant'):])}")
    print(f"Running Docker command...")
    
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
