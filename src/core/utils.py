"""
Shared utility functions for the fMRI pipeline.
"""

import sys
import os
import subprocess
import io
import threading
from datetime import datetime

# Thread-safe print lock
_print_lock = threading.Lock()

# Optional file handle for pipeline log
_log_file = None


def set_log_file(path):
    """Open a log file that mirrors all safe_print() output."""
    global _log_file
    _log_file = open(path, "a", encoding="utf-8")


def close_log_file():
    """Flush and close the pipeline log file."""
    global _log_file
    if _log_file:
        _log_file.close()
        _log_file = None


def setup_encoding():
    """
    Ensure UTF-8 output on all platforms (especially Windows).
    Call this at the start of any script that prints to console.
    """
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def safe_print(*args, **kwargs):
    """
    Thread-safe print function.

    Use this instead of print() when multiple threads may be printing simultaneously.
    Prevents output from getting interleaved/corrupted.
    Also writes to the pipeline log file when one is configured via set_log_file().

    Each line written to the log file is prefixed with a timestamp so that
    interleaved parallel output can be reconstructed chronologically.
    """
    with _print_lock:
        print(*args, **kwargs)
        if _log_file:
            try:
                timestamp = datetime.now().strftime("%H:%M:%S")
                log_kwargs = {k: v for k, v in kwargs.items() if k != 'flush'}
                # Build the text, then prefix every line with the timestamp
                msg = io.StringIO()
                print(*args, **log_kwargs, file=msg)
                for line in msg.getvalue().splitlines(True):
                    _log_file.write(f"[{timestamp}] {line}")
                _log_file.flush()
            except Exception:
                # Never let log formatting break the pipeline
                pass


def get_available_memory_gb():
    """
    Detect available system RAM in GB.
    Returns available RAM if detectable, otherwise falls back to total RAM.
    Works on Linux and macOS without external dependencies.
    """
    try:
        if sys.platform == "linux":
            # Read /proc/meminfo for high-accuracy availability on Linux
            with open("/proc/meminfo", "r") as f:
                meminfo = f.read()
            
            # MemAvailable is the best metric (available on kernels >= 3.14)
            for line in meminfo.splitlines():
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    return kb / (1024 * 1024)
            
            # Fallback for older kernels: Free + Buffers + Cached
            info = {}
            for line in meminfo.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    info[parts[0].rstrip(":")] = int(parts[1])
            
            free = info.get("MemFree", 0)
            buffers = info.get("Buffers", 0)
            cached = info.get("Cached", 0)
            return (free + buffers + cached) / (1024 * 1024)

        elif sys.platform == "darwin":
            # On macOS, use sysctl for total (fallback) or vm_stat for a rough estimate
            try:
                vm = subprocess.check_output(["vm_stat"], text=True)
                lines = vm.splitlines()
                # Page size is usually 4096
                page_size = 4096
                for line in lines:
                    if "page size of" in line:
                        page_size = int(line.split()[-2])
                
                stats = {}
                for line in lines[1:]:
                    if ":" in line:
                        parts = line.split(":")
                        stats[parts[0].strip()] = int(parts[1].strip().strip("."))
                
                # Available = Free + Inactive + Speculative
                free_pages = stats.get("Pages free", 0)
                inactive_pages = stats.get("Pages inactive", 0)
                speculative_pages = stats.get("Pages speculative", 0)
                available_bytes = (free_pages + inactive_pages + speculative_pages) * page_size
                return available_bytes / (1024**3)
            except Exception:
                pass

        # Global fallback: Total physical memory
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024 ** 3)
    except Exception:
        return 16.0  # Safe conservative fallback

