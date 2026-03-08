"""
QC (Quality Control) module for fMRI pipeline.

Layer 1: BIDSQualityChecker  - post-BIDS scan completeness & parameter checks
Layer 3: motion_parser       - post-fMRIPrep FD/DVARS motion analysis
Layer 4: html_report         - visual HTML QC report
"""

from .checker import BIDSQualityChecker, QCFinding, Severity
from .motion_parser import parse_all_subjects, MotionResult

__all__ = [
    "BIDSQualityChecker",
    "QCFinding",
    "Severity",
    "parse_all_subjects",
    "MotionResult",
]
