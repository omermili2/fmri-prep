"""
QC (Quality Control) module for fMRI pipeline.

Layer 1: BIDSQualityChecker  - post-BIDS scan completeness & parameter checks
Layer 2: iqm_parser          - MRIQC Image Quality Metrics parser & flagging
Layer 3: motion_parser       - post-fMRIPrep FD/DVARS motion analysis
Layer 4: connectivity_qc     - Nilearn-based connectivity quality assessment
         - volume_censoring  - Volume scrubbing analysis
         - connectivity_qc   - DM-FC (split-based), modularity metrics
Layer 5: html_report         - visual HTML QC report (final output)
"""

from .checker import BIDSQualityChecker, QCFinding, Severity
from .motion_parser import parse_all_subjects, MotionResult
from .iqm_parser import parse_all_subjects as parse_iqm_subjects, IQMResult, IQMFlag

# Layer 4: Connectivity QC (optional, requires Nilearn)
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
    "parse_iqm_subjects",
    "IQMResult",
    "IQMFlag",
    "volume_censoring",
    "connectivity_qc",
    "CONNECTIVITY_QC_AVAILABLE",
]
