"""
MRIQC Image Quality Metrics (IQM) Parser - Layer 2 companion

Parses the JSON files produced by MRIQC and classifies metric quality using
a two-layer approach:

  **Primary: Within-study IQR-based outlier detection**
  Each scan's metrics are compared to all other scans of the same modality
  (T1w or BOLD) in the dataset.  Values falling >1.5× IQR from the
  "worse" quartile are flagged as WARNING; >3× IQR are flagged as ERROR.
  This adapts automatically to any acquisition protocol.

  **Safety net: Absolute thresholds for extreme values**
  Protocol-independent ERROR thresholds catch values so extreme that they
  indicate a definite problem (e.g. sensor failure, severe artifact,
  aborted scan) regardless of protocol.  When the dataset has fewer than
  3 scans of the same modality (too few for IQR), moderate absolute
  thresholds are used as a WARNING-level fallback.

MRIQC writes one JSON per scan:
  <mriqc_dir>/sub-001_T1w.json
  <mriqc_dir>/sub-001_ses-01_task-rest_bold.json

Key metrics (see https://mriqc.readthedocs.io/en/stable/measures.html):

  Anatomical (T1w / T2w):
    cjv      Coefficient of Joint Variation      lower = better
    cnr      Contrast-to-Noise Ratio             higher = better
    snr_gm   SNR in gray matter                  higher = better
    inu_range Intensity Non-Uniformity range      lower = better
    qi_1     Artifact presence (foreground)       lower = better

  Functional (BOLD):
    fd_mean  Mean Framewise Displacement (mm)    lower = better
    tsnr     Temporal SNR                        higher = better
    gsr_x    Ghost-to-Signal Ratio X-direction   lower = better
    gsr_y    Ghost-to-Signal Ratio Y-direction   lower = better
    aor      AFNI outlier ratio                  lower = better
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Thresholds
#
# Each entry: (fallback_warn, safety_net_error, direction)
#
#   fallback_warn      — WARNING threshold applied when IQR detection is
#                         unavailable (fewer than 3 scans of this modality).
#   safety_net_error   — Absolute ERROR threshold, always applied.  Catches
#                         extreme values regardless of protocol or dataset.
#   direction          — "high" means higher values are worse;
#                         "low"  means lower  values are worse.
# ---------------------------------------------------------------------------

THRESHOLDS_ANAT: Dict[str, tuple] = {
    "cjv":       (0.60, 1.50, "high"),
    "cnr":       (2.00, 0.80, "low"),
    "snr_gm":    (6.00, 2.00, "low"),
    "inu_range": (0.50, 1.00, "high"),
    "qi_1":      (0.02, 0.10, "high"),
}

THRESHOLDS_BOLD: Dict[str, tuple] = {
    "fd_mean": (0.30, 1.00, "high"),
    "tsnr":    (20.0, 5.0,  "low"),
    "gsr_x":   (0.10, 0.30, "high"),
    "gsr_y":   (0.10, 0.30, "high"),
    "aor":     (0.10, 0.30, "high"),
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
    Parse all MRIQC JSON IQM files in mriqc_dir and classify quality.

    Returns one IQMResult per scan (JSON file) found, with flags from:
      1. Absolute safety-net ERROR thresholds (always applied)
      2. IQR-based within-study outlier detection (primary method, 3+ scans)
      3. Absolute fallback WARNING thresholds (when <3 scans per modality)
    """
    mriqc_path = Path(mriqc_dir)
    results: List[IQMResult] = []

    if not mriqc_path.exists():
        return results

    # Only match IQM files (T1w, T2w, bold); skip timeseries/confounds.
    # Use rglob to find files in both flat layout (older MRIQC) and
    # BIDS-derivatives layout (MRIQC >=22.x: sub-XXX/ses-YYY/anat|func/).
    # Exclude the work/ directory which contains intermediate files.
    for suffix in ("_T1w.json", "_T2w.json", "_bold.json"):
        for json_file in sorted(mriqc_path.rglob(f"sub-*{suffix}")):
            if "work" in json_file.parts:
                continue
            result = _parse_iqm_file(json_file)
            if result is not None:
                results.append(result)

    # Apply the full classification pipeline
    _classify_results(results)

    return results


# ---------------------------------------------------------------------------
# Classification pipeline
# ---------------------------------------------------------------------------

def _classify_results(results: List[IQMResult]) -> None:
    """
    Apply the two-layer quality classification to all parsed results.

    Called automatically by ``parse_all_subjects``.  Mutates ``results``
    in place by appending flags to each IQMResult.

    Layer 1 (safety-net absolute ERROR) is already applied during parsing.
    This function adds:
      - Layer 2: IQR-based within-study outlier detection (primary)
      - Layer 3: Fallback WARNING thresholds for small groups
    """
    _flag_iqr_outliers(results)
    _flag_small_dataset_fallback(results)


def _flag_iqr_outliers(results: List[IQMResult]) -> None:
    """
    Primary quality detector: within-study IQR-based outlier flagging.

    For each modality group (T1w / bold) and each metric, computes Q1, Q3,
    and IQR across all scans.  Flags scans whose metric falls beyond the
    "worse" quartile:

      >1.5 IQR  →  WARNING  (standard outlier)
      >3.0 IQR  →  ERROR    (extreme outlier)

    Only runs when there are 3+ scans of the same modality.  Flags are
    appended to each IQMResult's existing ``flags`` list.
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
        for metric, (_fallback, _safety, direction) in thresholds.items():
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
                # Determine outlier level
                if direction == "high":
                    deviation = v - q3
                else:
                    deviation = q1 - v

                if deviation <= 0:
                    continue  # within IQR — not an outlier

                # Skip if already flagged for this metric (e.g. safety-net)
                already = any(f.metric == metric for f in r.flags)
                if already:
                    continue

                if deviation > 3.0 * iqr:
                    severity = "ERROR"
                    iqr_label = ">3.0 IQR"
                elif deviation > 1.5 * iqr:
                    severity = "WARNING"
                    iqr_label = ">1.5 IQR"
                else:
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
                    severity=severity,
                    plain_message=(
                        f"{label} = {v:.3f} is a dataset outlier "
                        f"({iqr_label} from peers). "
                        f"Expected {better} values indicate better quality."
                    ),
                    action=(
                        "Review raw scan images. Compare with other scans "
                        "in the dataset."
                        if severity == "ERROR"
                        else "Review MRIQC visual report for this subject."
                    ),
                ))


def _flag_small_dataset_fallback(results: List[IQMResult]) -> None:
    """
    Fallback WARNING flags for modality groups with <3 scans.

    When there are too few scans for IQR-based detection, moderate
    absolute thresholds are applied as WARNING-level flags so that
    borderline values are not silently ignored.
    """
    from collections import defaultdict

    groups: Dict[str, List[IQMResult]] = defaultdict(list)
    for r in results:
        mod_key = "bold" if r.modality == "bold" else "anat"
        groups[mod_key].append(r)

    for mod_key, group in groups.items():
        if len(group) >= 3:
            continue  # IQR detection handles this group

        thresholds = THRESHOLDS_BOLD if mod_key == "bold" else THRESHOLDS_ANAT
        for r in group:
            for metric, (fallback_warn, _safety, direction) in thresholds.items():
                value = r.metrics.get(metric)
                if value is None:
                    continue

                # Skip if already flagged for this metric (e.g. safety-net)
                already = any(f.metric == metric for f in r.flags)
                if already:
                    continue

                crosses = (
                    (direction == "high" and value >= fallback_warn) or
                    (direction == "low" and value <= fallback_warn)
                )
                if not crosses:
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
                    value=value,
                    severity="WARNING",
                    plain_message=(
                        f"{label} = {value:.3f} "
                        f"({'above' if direction == 'high' else 'below'} "
                        f"warning threshold of {fallback_warn}). "
                        f"Expected {better} values indicate better quality. "
                        f"(Too few scans for within-study comparison.)"
                    ),
                    action="Review MRIQC visual report for this subject.",
                ))


# ---------------------------------------------------------------------------
# Single-file parsing
# ---------------------------------------------------------------------------

def _parse_iqm_file(json_path: Path) -> Optional[IQMResult]:
    """
    Parse a single MRIQC IQM JSON file.

    Applies only the safety-net absolute ERROR thresholds.  IQR-based
    detection and fallback warnings are added later by ``_classify_results``.
    """
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

    # Apply safety-net absolute ERROR thresholds only.
    # These catch extreme values regardless of protocol or dataset size.
    flags: List[IQMFlag] = []
    for metric, (_fallback, safety_net, direction) in thresholds.items():
        value = metrics.get(metric)
        if value is None:
            continue

        crosses = (
            (direction == "high" and value >= safety_net) or
            (direction == "low" and value <= safety_net)
        )
        if not crosses:
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
            severity="ERROR",
            plain_message=(
                f"{label} = {value:.3f} crosses the absolute safety-net "
                f"threshold ({safety_net}). This indicates a likely problem "
                f"regardless of protocol. "
                f"Expected {better} values indicate better quality."
            ),
            action="Review raw scan images. Consider excluding this "
                   "subject or re-scanning.",
        ))

    return IQMResult(
        sub_id=sub_id,
        ses_id=ses_id,
        scan_file=json_path.name,
        modality=modality,
        metrics=metrics,
        flags=flags,
    )


# ---------------------------------------------------------------------------
# Legacy API — kept for backwards compatibility
# ---------------------------------------------------------------------------

def flag_dataset_outliers(results: List[IQMResult]) -> List[IQMResult]:
    """Add within-dataset outlier flags.  Now called automatically by
    ``parse_all_subjects``; this wrapper is kept for direct callers."""
    _flag_iqr_outliers(results)
    return results


def get_all_flags(iqm_results: List[IQMResult]) -> List[IQMFlag]:
    flags = []
    for r in iqm_results:
        flags.extend(r.flags)
    return flags
