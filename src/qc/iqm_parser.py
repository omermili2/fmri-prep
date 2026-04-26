"""
MRIQC Image Quality Metrics (IQM) Parser - Layer 2 companion

Parses the JSON files produced by MRIQC and flags subjects whose metrics
fall outside acceptable ranges.

MRIQC writes one JSON per scan:
  <mriqc_dir>/sub-001_T1w.json
  <mriqc_dir>/sub-001_ses-01_task-rest_bold.json

Key metrics (see https://mriqc.readthedocs.io/en/stable/measures.html):

  Anatomical (T1w / T2w):
    cjv      Coefficient of Joint Variation      lower = better  (>0.5 = warn)
    cnr      Contrast-to-Noise Ratio             higher = better (<1.5 = warn)
    snr_gm   SNR in gray matter                  higher = better (<5  = warn)
    inu_range Intensity Non-Uniformity range      lower = better  (>0.15 = warn)
    qi_1     Artifact presence (foreground)       lower = better  (>0.02 = warn)

  Functional (BOLD):
    fd_mean  Mean Framewise Displacement (mm)    lower = better  (>0.5 = warn)
    tsnr     Temporal SNR                        higher = better (<50  = warn)
    gsr_x    Ghost-to-Signal Ratio X-direction   lower = better  (>0.1 = warn)
    gsr_y    Ghost-to-Signal Ratio Y-direction   lower = better  (>0.1 = warn)
    aor      AFNI outlier ratio                  lower = better  (>0.1 = warn)
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Thresholds
# Each entry: (warn_threshold, error_threshold, direction)
# direction = "high"  means higher values are worse (flag when value > threshold)
# direction = "low"   means lower values are worse  (flag when value < threshold)
# ---------------------------------------------------------------------------

THRESHOLDS_ANAT: Dict[str, tuple] = {
    "cjv":       (0.50, 0.70, "high"),
    "cnr":       (1.50, 1.00, "low"),
    "snr_gm":    (5.00, 3.00, "low"),
    "inu_range": (0.15, 0.25, "high"),
    "qi_1":      (0.02, 0.05, "high"),
}

THRESHOLDS_BOLD: Dict[str, tuple] = {
    "fd_mean": (0.50, 1.00, "high"),
    "tsnr":    (50.0, 30.0, "low"),
    "gsr_x":   (0.10, 0.20, "high"),
    "gsr_y":   (0.10, 0.20, "high"),
    "aor":     (0.10, 0.20, "high"),
}

METRIC_LABELS: Dict[str, str] = {
    "cjv":       "Coeff. of Joint Variation",
    "cnr":       "Contrast-to-Noise Ratio",
    "snr_gm":    "SNR (gray matter)",
    "inu_range": "Intensity Non-Uniformity",
    "qi_1":      "Artifact presence (QI1)",
    "fd_mean":   "Mean Framewise Displacement",
    "tsnr":      "Temporal SNR",
    "gsr_x":     "Ghost-to-Signal Ratio X",
    "gsr_y":     "Ghost-to-Signal Ratio Y",
    "aor":       "AFNI Outlier Ratio",
}


@dataclass
class IQMFlag:
    sub_id: str
    ses_id: str
    scan_file: str
    modality: str
    metric: str
    metric_label: str
    value: float
    severity: str
    plain_message: str
    action: str


@dataclass
class IQMResult:
    sub_id: str
    ses_id: str
    scan_file: str
    modality: str
    metrics: Dict[str, float] = field(default_factory=dict)
    flags: List[IQMFlag] = field(default_factory=list)

    @property
    def worst_severity(self) -> str:
        if any(f.severity == "ERROR" for f in self.flags):
            return "ERROR"
        if any(f.severity == "WARNING" for f in self.flags):
            return "WARNING"
        return "OK"


def parse_all_subjects(mriqc_dir) -> List[IQMResult]:
    """
    Parse all MRIQC JSON IQM files in mriqc_dir.

    Returns one IQMResult per scan (JSON file) found.
    """
    mriqc_path = Path(mriqc_dir)
    results: List[IQMResult] = []

    if not mriqc_path.exists():
        return results

    for json_file in sorted(mriqc_path.rglob("sub-*.json")):
        result = _parse_iqm_file(json_file)
        if result is not None:
            results.append(result)

    return results


def _parse_iqm_file(json_path: Path) -> Optional[IQMResult]:
    """Parse a single MRIQC IQM JSON file."""
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None

    stem = json_path.stem
    parts = stem.split("_")

    sub_id = next((p.replace("sub-", "") for p in parts if p.startswith("sub-")), "unknown")
    ses_id = next((p.replace("ses-", "") for p in parts if p.startswith("ses-")), "")

    is_bold = "bold" in stem.lower()
    modality = "bold" if is_bold else ("T1w" if "T1w" in stem else "anat")
    thresholds = THRESHOLDS_BOLD if is_bold else THRESHOLDS_ANAT

    metrics: Dict[str, float] = {}
    for key in thresholds:
        val = data.get(key)
        if val is not None:
            try:
                metrics[key] = float(val)
            except (TypeError, ValueError):
                pass

    flags: List[IQMFlag] = []
    for metric, (warn_thresh, err_thresh, direction) in thresholds.items():
        value = metrics.get(metric)
        if value is None:
            continue

        severity = _classify(value, warn_thresh, err_thresh, direction)
        if severity == "OK":
            continue

        label = METRIC_LABELS.get(metric, metric)
        better = "lower" if direction == "high" else "higher"
        flags.append(IQMFlag(
            sub_id=sub_id,
            ses_id=ses_id,
            scan_file=json_path.name,
            modality=modality,
            metric=metric,
            metric_label=label,
            value=value,
            severity=severity,
            plain_message=(
                f"{label} = {value:.3f} "
                f"({'above' if direction == 'high' else 'below'} "
                f"{'warning' if severity == 'WARNING' else 'critical'} threshold). "
                f"Expected {better} values indicate better image quality."
            ),
            action=(
                "Review raw scan images. Consider excluding this subject or re-scanning."
                if severity == "ERROR"
                else "Review MRIQC visual report for this subject."
            ),
        ))

    return IQMResult(
        sub_id=sub_id,
        ses_id=ses_id,
        scan_file=json_path.name,
        modality=modality,
        metrics=metrics,
        flags=flags,
    )


def _classify(value: float, warn: float, error: float, direction: str) -> str:
    if direction == "high":
        if value >= error:
            return "ERROR"
        if value >= warn:
            return "WARNING"
    else:
        if value <= error:
            return "ERROR"
        if value <= warn:
            return "WARNING"
    return "OK"


def get_all_flags(iqm_results: List[IQMResult]) -> List[IQMFlag]:
    flags = []
    for r in iqm_results:
        flags.extend(r.flags)
    return flags
