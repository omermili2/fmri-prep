"""
Volume Censoring Analysis - Layer 5a

Analyzes how many fMRI volumes must be censored (removed) due to motion,
and whether sufficient clean data remains for connectivity analysis.

Based on PMC10977879: Exclusion if >80% volumes censored at 0.2mm FD threshold.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import json

import pandas as pd
import numpy as np

from . import connectivity_thresholds as thresh


@dataclass
class CensoringResult:
    """Result of volume censoring analysis for one BOLD run."""
    sub_id: str
    ses_id: str
    run_label: str
    n_volumes: int
    mean_fd: float

    # Censoring at 0.2mm threshold (paper standard)
    n_censored_02mm: int
    pct_censored_02mm: float
    usable_volumes_02mm: int
    usable_minutes_02mm: float

    # Censoring at 0.5mm threshold (less strict)
    n_censored_05mm: int
    pct_censored_05mm: float
    usable_volumes_05mm: int
    usable_minutes_05mm: float

    # TR (repetition time) in seconds
    tr_sec: float

    # Overall assessment
    connectivity_ready: bool
    severity: str  # "OK", "WARNING", "ERROR"
    plain_message: str
    action: str


def analyze_all_subjects(derivatives_dir, bids_dir=None) -> List[CensoringResult]:
    """
    Analyze volume censoring for all subjects in derivatives directory.

    Args:
        derivatives_dir: fMRIPrep derivatives directory
        bids_dir: BIDS directory (optional, for extracting TR from JSON sidecars)

    Returns:
        List of CensoringResult objects
    """
    results: List[CensoringResult] = []
    deriv_path = Path(derivatives_dir)

    # Search for confounds files
    search_roots = [
        deriv_path / "fmriprep",
        deriv_path,
    ]

    for root in search_roots:
        if not root.exists():
            continue

        tsv_files = sorted(root.rglob("*_desc-confounds_timeseries.tsv"))
        for tsv_path in tsv_files:
            result = _analyze_single_run(tsv_path, bids_dir)
            if result is not None:
                results.append(result)

        if results:
            break

    return results


def _analyze_single_run(confounds_tsv: Path, bids_dir=None) -> Optional[CensoringResult]:
    """Analyze volume censoring for a single BOLD run."""
    try:
        # Extract subject/session/run info from filename
        parts = confounds_tsv.parts
        sub_id = next(
            (p.replace("sub-", "") for p in parts if p.startswith("sub-")), "unknown"
        )
        ses_id = next(
            (p.replace("ses-", "") for p in parts if p.startswith("ses-")), "unknown"
        )

        stem = confounds_tsv.stem.replace("_desc-confounds_timeseries", "")
        run_label = "_".join(
            p for p in stem.split("_")
            if not p.startswith("sub-") and not p.startswith("ses-")
        )

        # Load confounds TSV
        df = pd.read_csv(confounds_tsv, sep="\t", low_memory=False)

        if "framewise_displacement" not in df.columns:
            return None

        fd_series = pd.to_numeric(df["framewise_displacement"], errors="coerce").dropna()

        if fd_series.empty:
            return None

        n_volumes = len(fd_series)
        mean_fd = float(fd_series.mean())

        # Censoring at 0.2mm threshold (paper standard)
        censored_02mm = fd_series > thresh.CENSORING_FD_THRESHOLD
        n_censored_02mm = int(censored_02mm.sum())
        pct_censored_02mm = (n_censored_02mm / n_volumes) * 100.0
        usable_volumes_02mm = n_volumes - n_censored_02mm

        # Censoring at 0.5mm threshold
        censored_05mm = fd_series > 0.5
        n_censored_05mm = int(censored_05mm.sum())
        pct_censored_05mm = (n_censored_05mm / n_volumes) * 100.0
        usable_volumes_05mm = n_volumes - n_censored_05mm

        # Get TR (repetition time) from BOLD JSON sidecar
        tr_sec = _extract_tr(confounds_tsv, bids_dir)

        # Calculate usable scan time
        usable_minutes_02mm = (usable_volumes_02mm * tr_sec) / 60.0
        usable_minutes_05mm = (usable_volumes_05mm * tr_sec) / 60.0

        # Assess connectivity readiness (based on paper criteria)
        connectivity_ready, severity, message, action = _assess_connectivity_readiness(
            mean_fd=mean_fd,
            pct_censored_02mm=pct_censored_02mm,
            usable_minutes_02mm=usable_minutes_02mm,
            run_label=run_label
        )

        return CensoringResult(
            sub_id=sub_id,
            ses_id=ses_id,
            run_label=run_label,
            n_volumes=n_volumes,
            mean_fd=mean_fd,
            n_censored_02mm=n_censored_02mm,
            pct_censored_02mm=pct_censored_02mm,
            usable_volumes_02mm=usable_volumes_02mm,
            usable_minutes_02mm=usable_minutes_02mm,
            n_censored_05mm=n_censored_05mm,
            pct_censored_05mm=pct_censored_05mm,
            usable_volumes_05mm=usable_volumes_05mm,
            usable_minutes_05mm=usable_minutes_05mm,
            tr_sec=tr_sec,
            connectivity_ready=connectivity_ready,
            severity=severity,
            plain_message=message,
            action=action
        )

    except Exception:
        return None


def _extract_tr(confounds_tsv: Path, bids_dir=None) -> float:
    """
    Extract TR (repetition time) from BOLD JSON sidecar.

    Falls back to default if not found.
    """
    if bids_dir is None:
        return thresh.DEFAULT_TR

    # Construct path to corresponding BOLD JSON
    # confounds_tsv: .../derivatives/fmriprep/sub-X/ses-Y/func/sub-X_ses-Y_task-Z_desc-confounds_timeseries.tsv
    # bold_json:     .../sub-X/ses-Y/func/sub-X_ses-Y_task-Z_bold.json

    try:
        bids_path = Path(bids_dir)
        parts = confounds_tsv.stem.replace("_desc-confounds_timeseries", "").split("_")

        sub_id = next((p for p in parts if p.startswith("sub-")), None)
        ses_id = next((p for p in parts if p.startswith("ses-")), None)

        if sub_id and ses_id:
            bold_json_name = confounds_tsv.stem.replace("_desc-confounds_timeseries", "_bold.json")
            bold_json = bids_path / sub_id / ses_id / "func" / bold_json_name

            if bold_json.exists():
                with open(bold_json, 'r') as f:
                    metadata = json.load(f)
                    tr = metadata.get("RepetitionTime")
                    if tr is not None:
                        return float(tr)

    except Exception:
        pass

    return thresh.DEFAULT_TR


def _assess_connectivity_readiness(
    mean_fd: float,
    pct_censored_02mm: float,
    usable_minutes_02mm: float,
    run_label: str
) -> tuple[bool, str, str, str]:
    """
    Assess whether this run is suitable for connectivity analysis.

    Returns:
        (connectivity_ready, severity, message, action)
    """

    # Check paper's exclusion criteria
    fails_mean_fd = mean_fd > thresh.CONNECTIVITY_MEAN_FD_FAIL
    fails_censoring = pct_censored_02mm > thresh.MAX_CENSORED_PCT_FAIL
    fails_duration = usable_minutes_02mm < thresh.MIN_USABLE_MINUTES_FAIL

    # Check warning thresholds
    warns_mean_fd = mean_fd > thresh.CONNECTIVITY_MEAN_FD_WARN
    warns_censoring = pct_censored_02mm > thresh.MAX_CENSORED_PCT_WARN
    warns_duration = usable_minutes_02mm < thresh.MIN_USABLE_MINUTES_WARN

    # Determine overall status
    if fails_mean_fd or fails_censoring or fails_duration:
        connectivity_ready = False
        severity = "ERROR"

        reasons = []
        if fails_mean_fd:
            reasons.append(f"mean FD={mean_fd:.2f}mm (exceeds {thresh.CONNECTIVITY_MEAN_FD_FAIL}mm)")
        if fails_censoring:
            reasons.append(f"{pct_censored_02mm:.0f}% censored (exceeds {thresh.MAX_CENSORED_PCT_FAIL:.0f}%)")
        if fails_duration:
            reasons.append(f"only {usable_minutes_02mm:.1f}min usable (minimum {thresh.MIN_USABLE_MINUTES_FAIL}min)")

        message = f"NOT suitable for connectivity analysis: {'; '.join(reasons)}"
        action = "Consider excluding this run from connectivity analyses or re-scanning subject."

    elif warns_mean_fd or warns_censoring or warns_duration:
        connectivity_ready = True
        severity = "WARNING"

        concerns = []
        if warns_mean_fd:
            concerns.append(f"elevated motion (FD={mean_fd:.2f}mm)")
        if warns_censoring:
            concerns.append(f"{pct_censored_02mm:.0f}% volumes censored")
        if warns_duration:
            concerns.append(f"short usable duration ({usable_minutes_02mm:.1f}min)")

        message = f"Marginally suitable for connectivity: {'; '.join(concerns)}"
        action = "Usable but apply strict scrubbing and verify results with sensitivity analyses."

    else:
        connectivity_ready = True
        severity = "OK"
        message = (
            f"Suitable for connectivity analysis: mean FD={mean_fd:.2f}mm, "
            f"{pct_censored_02mm:.0f}% censored at 0.2mm, "
            f"{usable_minutes_02mm:.1f}min usable"
        )
        action = "Proceed with connectivity analysis."

    return connectivity_ready, severity, message, action
