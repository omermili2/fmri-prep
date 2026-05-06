#!/usr/bin/env python3
"""
fMRI Preprocessing Assistant - Entry Point

Usage:
    # GUI mode (if display available)
    python run.py
    
    # CLI mode (automatically used if no display, or with arguments)
    python run.py --help                    # Show CLI help
    python run.py --input ... --output_dir ...  # Run pipeline
    python run.py --bids-folder ...         # Run fMRIPrep only
    
    # Force CLI mode
    python run.py --cli --help
"""

import sys
import os
import subprocess
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))


def ensure_dependencies():
    """Check that required packages are installed; install them if missing."""
    requirements_file = Path(__file__).parent / "requirements.txt"
    if not requirements_file.exists():
        return

    missing = []
    for line in requirements_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Extract the bare package name (strip version specifiers)
        pkg = line.split(">=")[0].split("<=")[0].split("==")[0].split("!=")[0].split("<")[0].split(">")[0].strip()
        # importlib.metadata handles name normalisation (e.g. scikit-learn -> scikit_learn)
        try:
            from importlib.metadata import distribution  # Python 3.8+
            distribution(pkg)
        except Exception:
            missing.append(pkg)

    if missing:
        print(f"Installing missing dependencies: {', '.join(missing)} ...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)],
                stdout=sys.stdout,
                stderr=sys.stderr,
            )
            print("Dependencies installed successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Warning: Failed to install dependencies (exit code {e.returncode}).")
            print("Please run manually:  pip install -r requirements.txt")
            sys.exit(1)


def has_display():
    """Check if a display is available for GUI."""
    # On Linux, require the DISPLAY variable (X11)
    if sys.platform == 'linux' and 'DISPLAY' not in os.environ:
        return False
    # On macOS/Windows just check tkinter is importable — don't instantiate
    # Tk() here as it can segfault on non-framework Python builds on macOS.
    # Any real display failure will be caught when App() is created.
    try:
        import tkinter  # noqa: F401
        return True
    except Exception:
        return False


def print_x11_help():
    """Print helpful information about running GUI over SSH."""
    print("\n" + "=" * 60)
    print("To run the GUI over SSH, enable X11 forwarding:")
    print("=" * 60)
    print("\n1. Connect with X11 forwarding:")
    print("   ssh -X user@host")
    print("   # or")
    print("   ssh -Y user@host  (trusted forwarding)")
    print("\n2. On Windows, install an X server first:")
    print("   - VcXsrv (free): https://sourceforge.net/projects/vcxsrv/")
    print("   - Xming: https://sourceforge.net/projects/xming/")
    print("   Then connect: ssh -X user@host")
    print("\n3. Verify X11 forwarding is working:")
    print("   echo $DISPLAY  # Should show something like localhost:10.0")
    print("   xeyes  # Test with a simple X11 app (if available)")
    print("\n4. If X11 forwarding still doesn't work:")
    print("   - Check SSH server config: X11Forwarding yes")
    print("   - Check /etc/ssh/sshd_config on the server")
    print("   - Restart SSH server: sudo systemctl restart sshd")
    print("\n5. Alternative: Use CLI mode (no display needed):")
    print("   python run.py --help")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    ensure_dependencies()

    # Check if --cli flag is present
    if '--cli' in sys.argv:
        # Remove --cli flag and pass rest to orchestrator
        sys.argv.remove('--cli')
        from orchestrator import main
        main()
    # Check if any CLI arguments are provided (not just --help)
    elif len(sys.argv) > 1:
        # Arguments provided - use CLI mode
        from orchestrator import main
        main()
    # No arguments - try GUI, fall back to CLI if no display
    else:
        if not has_display():
            is_ssh = bool(os.environ.get('SSH_CONNECTION'))
            if is_ssh:
                print("No display available (SSH session detected).")
                print_x11_help()
            else:
                print("No display available. Running in CLI mode.")
                print("=" * 60)
            # Show help automatically
            sys.argv.append('--help')
            from orchestrator import main
            main()
        else:
            # Try GUI mode
            try:
                from gui.app import App
                app = App()
                app.mainloop()
            except Exception as e:
                if "no display" in str(e).lower() or "DISPLAY" in str(e):
                    print(f"Error: {e}")
                    is_ssh = bool(os.environ.get('SSH_CONNECTION'))
                    if is_ssh:
                        print_x11_help()
                    else:
                        print("\nNo display available. Running in CLI mode.")
                        print("=" * 60)
                    # Show help automatically
                    sys.argv.append('--help')
                    from orchestrator import main
                    main()
                else:
                    raise
