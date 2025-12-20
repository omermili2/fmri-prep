"""
Progress tracking for parallel pipeline execution.
"""

import threading
from .utils import safe_print


class ProgressTracker:
    """
    Thread-safe progress tracking for parallel task execution.
    
    Emits progress markers that can be parsed by the GUI for
    real-time progress bar updates.
    
    Markers emitted:
        [PROGRESS:TASK_START:N] - Task N is starting
        [PROGRESS:TASK:N]       - N tasks have completed
    """
    
    def __init__(self, total):
        """
        Initialize progress tracker.
        
        Args:
            total: Total number of tasks to track
        """
        self.total = total
        self.completed = 0
        self._lock = threading.Lock()
    
    def increment(self):
        """
        Mark one task as completed.
        
        Returns:
            Current count of completed tasks
        """
        with self._lock:
            self.completed += 1
            count = self.completed
        safe_print(f"[PROGRESS:TASK:{count}]", flush=True)
        return count
    
    def task_start(self, task_num):
        """
        Signal that a task is starting.
        
        Args:
            task_num: The task number (0-indexed)
        """
        safe_print(f"[PROGRESS:TASK_START:{task_num}]", flush=True)
    
    def get_completed_count(self):
        """
        Get the current count of completed tasks.
        
        Returns:
            Number of tasks completed so far
        """
        with self._lock:
            return self.completed

