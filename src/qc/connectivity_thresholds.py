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
MAX_CENSORED_PCT_WARN = 50.0  # % - Warning if >50% volumes censored
MAX_CENSORED_PCT_FAIL = 80.0  # % - Fail if >80% volumes censored (paper threshold)

# Minimum usable scan duration
MIN_USABLE_MINUTES_WARN = 2.0  # minutes - Warning threshold
MIN_USABLE_MINUTES_FAIL = 1.0  # minutes - Paper threshold (absolute minimum)

# Loss of temporal degrees of freedom
# total_loss = num_nuisance_regressors + censored_volumes
# If total_loss exceeds this fraction of total_volumes, warn the researcher.
LOSS_DOF_WARN = 0.60  # 60% — more than half the DoF consumed by denoising + scrubbing
