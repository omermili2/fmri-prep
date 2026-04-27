"""
MRIQC Image Quality Metrics (IQM) Parser - Layer 2 companion

Parses the JSON files produced by MRIQC and flags subjects whose metrics
fall outside acceptable ranges.

MRIQC writes one JSON per scan:
  <mriqc_dir>/sub-001_T1w.json
  <mriqc_dir>/sub-001_ses-01_task-rest_bold.json

Key metrics (see https://mriqc.readthedocs.io/en/stable/measures.html):

  Anatomical (T1w / T2w):
    cjv      Coefficient of Joint Variation      lower = better  (>0.60 = warn)
    cnr      Contrast-to-Noise Ratio             higher = better (<2.0 = warn)
    snr_gm   SNR in gray matter                  higher = better (<6.0 = warn)
    inu_range Intensity Non-Uniformity range      lower = better  (>0.50 = warn)
    qi_1     Artifact presence (foreground)       lower = better  (>0.02 = warn)

  Functional (BOLD):
    fd_mean  Mean Framewise Displacement (mm)    lower = better  (>0.3 = warn)
    tsnr     Temporal SNR                        higher = better (<40  = warn)
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
    "cjv":       (0.60, 1.00, "high"),
    "cnr":       (2.00, 1.20, "low"),
    "snr_gm":    (6.00, 4.00, "low"),
    "inu_range": (0.50, 0.70, "high"),
    "qi_1":      (0.02, 0.05, "high"),
}

THRESHOLDS_BOLD: Dict[str, tuple] = {
    "fd_mean": (0.30, 0.55, "high"),
    "tsnr":    (40.0, 20.0, "low"),
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

# Short display names used in the HTML report metric bubbles
METRIC_DISPLAY: Dict[str, str] = {
    "cjv":       "CJV",
    "cnr":       "CNR",
    "snr_gm":    "SNR",
    "inu_range": "INU range",
    "qi_1":      "QI1",
    "fd_mean":   "FD mean",
    "tsnr":      "tSNR",
    "gsr_x":     "GSR X",
    "gsr_y":     "GSR Y",
    "aor":       "AOR",
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
    def scan_label(self) -> str:
        """Human-readable scan label derived from filename."""
        import re
        stem = Path(self.scan_file).stem
        parts = []
        m = re.search(r"task-([A-Za-z0-9]+)", stem)
        if m:
            parts.append(f"task-{m.group(1)}")
        m = re.search(r"run-(\d+)", stem)
        if m:
            parts.append(f"run-{m.group(1)}")
        if parts:
            return " ".join(parts)
        return self.modality  # fallback: "T1w" or "bold"

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

    # Only match IQM files (T1w, T2w, bold); skip timeseries/confounds.
    # Use rglob to find files in both flat layout (older MRIQC) and
    # BIDS-derivatives layout (MRIQC ≥22.x: sub-XXX/ses-YYY/anat|func/).
    # Exclude the work/ directory which contains intermediate files.
    for suffix in ("_T1w.json", "_T2w.json", "_bold.json"):
        for json_file in sorted(mriqc_path.rglob(f"sub-*{suffix}")):
            if "work" in json_file.parts:
                continue
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

    if not metrics:
        return None

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


def flag_dataset_outliers(results: List[IQMResult]) -> List[IQMResult]:
    """
    Add within-dataset outlier flags using IQR-based detection.

    For each modality group (T1w / bold) and each metric, computes Q1, Q3,
    and IQR across all scans.  A scan whose metric falls >1.5*IQR beyond
    the "worse" quartile (Q3 for "high-is-bad", Q1 for "low-is-bad") is
    flagged as a WARNING dataset outlier.

    Only runs when there are 3+ scans of the same modality.  Flags are
    appended to each IQMResult's existing ``flags`` list and will appear in
    the report alongside absolute-threshold flags.
    """
    from collections import defaultdict

    # Group results by modality category
    groups: Dict[str, List[IQMResult]] = defaultdict(list)
    for r in results:
        mod_key = "bold" if r.modality == "bold" else "anat"
        groups[mod_key].append(r)

    for mod_key, group in groups.items():
        if len(group) < 3:
            continue

        thresholds = THRESHOLDS_BOLD if mod_key == "bold" else THRESHOLDS_ANAT
        for metric, (_warn, _err, direction) in thresholds.items():
            values = [(r, r.metrics.get(metric)) for r in group]
            valid = [(r, v) for r, v in values if v is not None]
            if len(valid) < 3:
                continue

            nums = sorted(v for _, v in valid)
            q1 = nums[len(nums) // 4]
            q3 = nums[3 * len(nums) // 4]
            iqr = q3 - q1
            if iqr == 0:
                continue

            for r, v in valid:
                is_outlier = False
                if direction == "high" and v > q3 + 1.5 * iqr:
                    is_outlier = True
                elif direction == "low" and v < q1 - 1.5 * iqr:
                    is_outlier = True

                if not is_outlier:
                    continue

                # Skip if already flagged at WARNING or worse for this metric
                already = any(f.metric == metric for f in r.flags)
                if already:
                    continue

                label = METRIC_LABELS.get(metric, metric)
                better = "lower" if direction == "high" else "higher"
                r.flags.append(IQMFlag(
                    sub_id=r.sub_id,
                    ses_id=r.ses_id,
                    scan_file=r.scan_file,
                    modality=r.modality,
                    metric=metric,
                    metric_label=label,
                    value=v,
                    severity="WARNING",
                    plain_message=(
                        f"{label} = {v:.3f} is a dataset outlier "
                        f"(>1.5 IQR from peers). "
                        f"Expected {better} values indicate better image quality."
                    ),
                    action="Compare with other scans in the dataset. "
                           "Review MRIQC visual report for this subject.",
                ))

    return results


def get_all_flags(iqm_results: List[IQMResult]) -> List[IQMFlag]:
    flags = []
    for r in iqm_results:
        flags.extend(r.flags)
    return flags
