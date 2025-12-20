"""
Shared utility functions for the fMRI pipeline.
"""

import sys
import io
import threading

# Thread-safe print lock
_print_lock = threading.Lock()


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
    """
    with _print_lock:
        print(*args, **kwargs)

