"""
Shared utility functions for the fMRI pipeline.
"""

import sys
import io
import threading

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
    """
    with _print_lock:
        print(*args, **kwargs)
        if _log_file:
            log_kwargs = {k: v for k, v in kwargs.items() if k != 'flush'}
            print(*args, **log_kwargs, file=_log_file)
            _log_file.flush()

