"""
fMRIPrep runner using Docker.

This module provides a Python interface to run fMRIPrep via Docker,
with support for cross-platform path conversion and configurable options.
"""

import subprocess
import sys
import json
import base64
import time
import shutil
from pathlib import Path

# Default fMRIPrep Docker image
FMRIPREP_IMAGE = "nipreps/fmriprep:latest"


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


def is_docker_installed():
    """Check if Docker is installed on the system."""
    return shutil.which("docker") is not None


def is_docker_running():
    """Check if Docker daemon is running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def start_docker(timeout=60, callback=None):
    """
    Attempt to start Docker Desktop.
    
    Args:
        timeout: Maximum seconds to wait for Docker to start
        callback: Optional callback function for progress updates (receives message string)
        
    Returns:
        Tuple of (success: bool, error_message: str or None)
    """
    if is_docker_running():
        return True, None
    
    if callback:
        callback("Starting Docker Desktop...")
    
    # Try to start Docker based on platform
    if sys.platform == "darwin":
        # macOS - open Docker Desktop app
        try:
            subprocess.run(["open", "-a", "Docker"], check=True)
        except subprocess.CalledProcessError:
            return False, "Could not start Docker Desktop. Please start it manually."
    elif sys.platform == "win32":
        # Windows - try to start Docker Desktop
        docker_paths = [
            Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe"),
            Path.home() / "AppData" / "Local" / "Docker" / "Docker Desktop.exe",
        ]
        started = False
        for docker_path in docker_paths:
            if docker_path.exists():
                try:
                    subprocess.Popen([str(docker_path)])
                    started = True
                    break
                except Exception:
                    continue
        if not started:
            return False, "Could not find Docker Desktop. Please start it manually."
    else:
        # Linux - try systemctl
        try:
            subprocess.run(["sudo", "systemctl", "start", "docker"], check=True, timeout=30)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False, "Could not start Docker service. Try: sudo systemctl start docker"
    
    # Wait for Docker to be ready
    start_time = time.time()
    while time.time() - start_time < timeout:
        if callback:
            elapsed = int(time.time() - start_time)
            callback(f"Waiting for Docker to start... ({elapsed}s)")
        
        if is_docker_running():
            if callback:
                callback("Docker is ready!")
            return True, None
        time.sleep(2)
    
    return False, f"Docker did not start within {timeout} seconds. Please start it manually."


def is_fmriprep_image_available():
    """Check if the fMRIPrep Docker image is downloaded."""
    try:
        result = subprocess.run(
            ["docker", "images", "-q", FMRIPREP_IMAGE],
            capture_output=True,
            text=True,
            timeout=30
        )
        return bool(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def pull_fmriprep_image(callback=None):
    """
    Pull the fMRIPrep Docker image.
    
    Args:
        callback: Optional callback function for progress updates
        
    Returns:
        Tuple of (success: bool, error_message: str or None)
    """
    if callback:
        callback(f"Downloading fMRIPrep image ({FMRIPREP_IMAGE})...")
        callback("This may take 10-30 minutes on first run...")
    
    try:
        # Use Popen to stream output
        process = subprocess.Popen(
            ["docker", "pull", FMRIPREP_IMAGE],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        for line in process.stdout:
            line = line.strip()
            if line and callback:
                # Simplify Docker pull progress messages
                if "Pulling" in line or "Downloading" in line or "Extracting" in line:
                    callback(f"  {line[:80]}")
        
        process.wait()
        
        if process.returncode == 0:
            if callback:
                callback("fMRIPrep image downloaded successfully!")
            return True, None
        else:
            return False, "Failed to download fMRIPrep image."
    except Exception as e:
        return False, f"Error pulling fMRIPrep image: {e}"


def check_docker():
    """
    Check if Docker is available and running.
    
    Returns:
        Tuple of (available: bool, error_message: str or None)
    """
    if not is_docker_installed():
        return False, "Docker is not installed. Please install Docker Desktop from https://docker.com"
    
    if not is_docker_running():
        return False, "Docker is not running. Please start Docker Desktop."
    
    return True, None


def preflight_check(callback=None, auto_start_docker=True, auto_pull_image=True):
    """
    Perform all pre-flight checks for fMRIPrep.
    
    This function checks and optionally fixes all prerequisites:
    1. Docker installation
    2. Docker daemon running (auto-start if possible)
    3. fMRIPrep image available (auto-pull if missing)
    4. FreeSurfer license file
    
    Args:
        callback: Optional callback for progress messages
        auto_start_docker: Attempt to start Docker if not running
        auto_pull_image: Attempt to pull fMRIPrep image if missing
        
    Returns:
        Tuple of (success: bool, error_message: str or None)
    """
    # Check Docker installation
    if callback:
        callback("Checking Docker installation...")
    
    if not is_docker_installed():
        return False, (
            "Docker is not installed.\n\n"
            "Please install Docker Desktop:\n"
            "• macOS/Windows: https://www.docker.com/products/docker-desktop\n"
            "• Linux: https://docs.docker.com/engine/install/"
        )
    
    # Check if Docker is running (auto-start if needed)
    if callback:
        callback("Checking if Docker is running...")
    
    if not is_docker_running():
        if auto_start_docker:
            success, error = start_docker(timeout=90, callback=callback)
            if not success:
                return False, error
        else:
            return False, "Docker is not running. Please start Docker Desktop."
    
    # Check if fMRIPrep image is available
    if callback:
        callback("Checking fMRIPrep Docker image...")
    
    if not is_fmriprep_image_available():
        if auto_pull_image:
            success, error = pull_fmriprep_image(callback=callback)
            if not success:
                return False, error
        else:
            return False, (
                f"fMRIPrep Docker image not found.\n\n"
                f"Run this command to download it:\n"
                f"  docker pull {FMRIPREP_IMAGE}"
            )
    
    # Check FreeSurfer license
    if callback:
        callback("Checking FreeSurfer license...")
    
    license_path = find_freesurfer_license()
    if not license_path:
        return False, (
            "FreeSurfer license file not found.\n\n"
            "To get a free license:\n"
            "1. Register at https://surfer.nmr.mgh.harvard.edu/registration.html\n"
            "2. You'll receive an email with the license\n"
            "3. Save it as '.freesurfer_license.txt' in the project folder"
        )
    
    if callback:
        callback("All pre-flight checks passed!")
    
    return True, None


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
    
    # Detect Windows/WSL 2 for special handling
    is_windows = sys.platform == 'win32'
    
    docker_cmd = [
        "docker", "run", "-t", "--rm",
        "-v", f"{bids_mount}:/data:ro",
        "-v", f"{output_mount}:/out",
        "-v", f"{license_mount}:/opt/freesurfer/license.txt:ro",
    ]
    
    # Fix for Windows Docker Desktop multiprocessing issues
    # Docker Desktop on Windows (with or without WSL 2) can have issues with
    # Unix sockets used by Python's multiprocessing module
    if is_windows:
        # Set environment variables to help with multiprocessing
        # Use 'spawn' method which works better in containers
        docker_cmd.extend([
            "-e", "MPLCONFIGDIR=/tmp/mpl",
            "-e", "PYTHONUNBUFFERED=1",
            "-e", "MP_START_METHOD=spawn",
            "-e", "TMPDIR=/tmp",
        ])
        
        # Use a tmpfs for /tmp to avoid Windows file sharing issues
        # This creates an in-memory filesystem for temp files and sockets
        # Size of 2GB should be enough for multiprocessing sockets
        # This helps with Unix socket creation in Docker containers on Windows
        # The 'exec' flag allows execution, 'mode=1777' gives proper permissions
        docker_cmd.extend([
            "--tmpfs", "/tmp:exec,mode=1777,size=2g",
        ])
    
    docker_cmd.extend([
        FMRIPREP_IMAGE,
        "/data", "/out",
        "participant",
        "--participant-label", participant_label,
        "--skip-bids-validation",
    ])
    
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
    print(f"Docker command: {' '.join(docker_cmd[:10])}...")  # Show first part of command
    
    # Run fMRIPrep with output capture
    try:
        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        # Print stdout/stderr for debugging
        if result.stdout:
            print("--- fMRIPrep stdout ---")
            print(result.stdout)
        
        if result.stderr:
            print("--- fMRIPrep stderr ---")
            print(result.stderr)
        
        if result.returncode == 0:
            return True, None
        else:
            # Build detailed error message
            error_msg = f"fMRIPrep exited with code {result.returncode}\n\n"
            
            # Check for specific WSL 2 multiprocessing error
            combined_output = (result.stdout or "") + (result.stderr or "")
            is_multiproc_error = (
                "FileNotFoundError" in combined_output and 
                "multiprocessing" in combined_output.lower() and
                ("No such file or directory" in combined_output or "socket" in combined_output.lower())
            )
            
            if is_multiproc_error and is_windows:
                error_msg += "⚠️  WINDOWS DOCKER MULTIPROCESSING ERROR DETECTED\n\n"
                error_msg += "This is a known issue with Docker Desktop on Windows.\n"
                error_msg += "The container cannot create Unix sockets for multiprocessing.\n\n"
                error_msg += "SOLUTIONS TO TRY:\n"
                error_msg += "1. Restart Docker Desktop completely:\n"
                error_msg += "   - Right-click Docker Desktop icon > Quit Docker Desktop\n"
                error_msg += "   - Wait a few seconds, then start it again\n"
                error_msg += "   - Try running fMRIPrep again\n"
                error_msg += "2. Try running with fewer threads:\n"
                error_msg += "   - In fMRIPrep options, reduce nthreads to 2 or 1\n"
                error_msg += "   - This reduces multiprocessing overhead\n"
                error_msg += "3. If you have WSL 2 installed:\n"
                error_msg += "   - Go to Docker Desktop Settings > Resources > WSL Integration\n"
                error_msg += "   - Enable integration with your WSL distro\n"
                error_msg += "   - Move data to WSL filesystem (e.g., /mnt/d/data)\n"
                error_msg += "4. Check Docker Desktop logs:\n"
                error_msg += "   - Docker Desktop > Troubleshoot > View logs\n"
                error_msg += "   - Look for any errors related to file access\n\n"
                error_msg += "Full error details:\n"
            
            # Extract key error information from stderr
            if result.stderr:
                # Look for common error patterns
                stderr_lines = result.stderr.split('\n')
                error_lines = []
                for line in stderr_lines:
                    line_lower = line.lower()
                    if any(keyword in line_lower for keyword in ['error', 'failed', 'exception', 'traceback', 'cannot', 'unable']):
                        error_lines.append(line)
                
                if error_lines:
                    error_msg += "Key error messages:\n"
                    error_msg += "\n".join(error_lines[-20:])  # Last 20 error lines
                else:
                    # If no obvious errors, show last part of stderr
                    error_msg += "Last stderr output:\n"
                    error_msg += "\n".join(stderr_lines[-30:])
            
            # Also check stdout for errors
            if result.stdout:
                stdout_lines = result.stdout.split('\n')
                error_lines = []
                for line in stdout_lines:
                    line_lower = line.lower()
                    if any(keyword in line_lower for keyword in ['error', 'failed', 'exception', 'traceback']):
                        error_lines.append(line)
                
                if error_lines:
                    error_msg += "\n\nKey stdout errors:\n"
                    error_msg += "\n".join(error_lines[-20:])
            
            return False, error_msg
            
    except KeyboardInterrupt:
        return False, "Interrupted by user"
    except FileNotFoundError:
        return False, "Docker command not found. Is Docker installed?"
    except Exception as e:
        return False, f"Exception running fMRIPrep: {str(e)}\n\nTraceback:\n{type(e).__name__}: {e}"


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
    parser.add_argument("--opts", type=str, default="",
                        help="Base64-encoded JSON options (platform-agnostic)")
    
    args = parser.parse_args()
    
    # Decode options from base64 JSON (platform-agnostic)
    opts = {}
    if args.opts:
        try:
            json_str = base64.b64decode(args.opts).decode('utf-8')
            opts = json.loads(json_str)
        except Exception as e:
            print(f"Warning: Could not decode options: {e}")
    
    # Extract options from decoded dict
    output_spaces = opts.get("output_spaces", None)
    fs_reconall = opts.get("fs_reconall", True)
    skip_slice_timing = opts.get("skip_slice_timing", False)
    use_syn_sdc = opts.get("use_syn_sdc", False)
    use_aroma = opts.get("use_aroma", False)
    
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

