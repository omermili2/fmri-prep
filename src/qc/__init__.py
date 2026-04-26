"""
QC (Quality Control) module for fMRI pipeline.

Layer 1: BIDSQualityChecker  - post-BIDS scan completeness & parameter checks
Layer 2: motion_parser       - post-fMRIPrep FD/DVARS motion analysis
Layer 3: connectivity_qc     - Nilearn-based connectivity quality assessment
         - volume_censoring  - Volume scrubbing analysis
         - connectivity_qc   - DM-FC (split-based), modularity metrics

Note: MRIQC IQM parsing has moved to the dedicated ``mriqc`` package.
"""

from .checker import BIDSQualityChecker, QCFinding, Severity
from .motion_parser import parse_all_subjects, MotionResult

# Connectivity QC (optional, requires Nilearn)
try:
    from . import volume_censoring
    from . import connectivity_qc
    CONNECTIVITY_QC_AVAILABLE = True
except ImportError:
    volume_censoring = None
    connectivity_qc = None
    CONNECTIVITY_QC_AVAILABLE = False

__all__ = [
    "BIDSQualityChecker",
    "QCFinding",
    "Severity",
    "parse_all_subjects",
    "MotionResult",
    "volume_censoring",
    "connectivity_qc",
    "CONNECTIVITY_QC_AVAILABLE",
]
