"""
Connectivity Quality Control Thresholds

Based on best practices from:
- Parkes et al. (2018) NeuroImage
- Ciric et al. (2017) NeuroImage
- PMC10977879 (Quality control practices for functional connectivity)

These thresholds are stricter than general motion QC because connectivity
analysis is particularly sensitive to motion artifacts.
"""

# Motion thresholds for connectivity analysis
CONNECTIVITY_MEAN_FD_WARN = 0.25  # mm - Stricter than general QC (0.5mm)
CONNECTIVITY_MEAN_FD_FAIL = 0.50  # mm - Absolute failure threshold

# Volume censoring thresholds
CENSORING_FD_THRESHOLD = 0.2  # mm - Threshold for marking "bad" volumes
MAX_CENSORED_PCT_WARN = 50.0  # % - Warning if >50% volumes censored
MAX_CENSORED_PCT_FAIL = 80.0  # % - Fail if >80% volumes censored (paper threshold)

# Minimum usable scan duration
MIN_USABLE_MINUTES_WARN = 2.0  # minutes - Warning threshold
MIN_USABLE_MINUTES_FAIL = 1.0  # minutes - Paper threshold (absolute minimum)

# QC-FC thresholds (motion-connectivity correlation)
QC_FC_WARN = 0.10  # Partial correlation threshold
QC_FC_FAIL = 0.20  # Strong motion-connectivity contamination

# DM-FC thresholds (distance-dependent motion effects)
DM_FC_WARN = 0.05  # Distance-motion correlation threshold
DM_FC_FAIL = 0.10  # Strong distance-dependent artifacts

# Network modularity thresholds
MIN_MODULARITY_WARN = 0.30  # Q statistic
MIN_MODULARITY_FAIL = 0.20  # Poor network structure preservation

# TR (repetition time) typical value for calculating scan duration
DEFAULT_TR = 2.0  # seconds - used if TR not found in metadata
