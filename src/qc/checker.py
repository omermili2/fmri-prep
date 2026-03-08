"""
BIDS Quality Checker - Layer 1

Runs after BIDS conversion to detect issues that would require re-scanning:
- Missing expected scan types (no T1w, no BOLD)
- Truncated runs (too few timepoints / TRs)
- Suspiciously small files (possible corruption or abort)
- Scan parameter drift across subjects (TR, field strength)

No external dependencies beyond Python stdlib — reads NIfTI headers directly.
Thread-safe: designed to be shared across parallel worker threads.
"""

import gzip
import json
import struct
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class Severity(Enum):
    OK = "OK"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class QCFinding:
    severity: Severity
    sub_id: str
    ses_id: str
    category: str
    message: str
    plain_message: str
    action: str


class BIDSQualityChecker:
    """
    Checks BIDS data quality immediately after conversion.

    Detects common issues that would require calling patients back for re-scanning.
    Thread-safe: can be shared across parallel worker threads.

    Usage:
        checker = BIDSQualityChecker(min_bold_trs=50)

        # Called once per session after BIDS conversion succeeds:
        findings = checker.check_session(bids_dir, sub_id, ses_id)

        # After all sessions processed:
        errors   = checker.get_errors()
        warnings = checker.get_warnings()
    """

    MIN_ANAT_SIZE_MB = 1.0
    MIN_FUNC_SIZE_MB = 5.0

    def __init__(self, min_bold_trs: int = 50):
        self.min_bold_trs = min_bold_trs
        self._lock = threading.Lock()
        self.findings: List[QCFinding] = []
        self._param_baseline: Dict = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_session(self, bids_dir, sub_id: str, ses_id: str) -> List[QCFinding]:
        """
        Run all quality checks for a single subject/session.

        Returns the list of findings for this session (also stored internally).
        """
        session_path = Path(bids_dir) / f"sub-{sub_id}" / f"ses-{ses_id}"
        if not session_path.exists():
            session_path = Path(bids_dir) / f"sub-{sub_id}"

        session_findings: List[QCFinding] = []
        session_findings += self._check_missing_scans(session_path, sub_id, ses_id)
        session_findings += self._check_file_sizes(session_path, sub_id, ses_id)
        session_findings += self._check_bold_trs(session_path, sub_id, ses_id)
        session_findings += self._check_params(session_path, sub_id, ses_id)

        with self._lock:
            self.findings.extend(session_findings)

        return session_findings

    def get_errors(self) -> List[QCFinding]:
        with self._lock:
            return [f for f in self.findings if f.severity == Severity.ERROR]

    def get_warnings(self) -> List[QCFinding]:
        with self._lock:
            return [f for f in self.findings if f.severity == Severity.WARNING]

    def get_all(self) -> List[QCFinding]:
        with self._lock:
            return list(self.findings)

    def has_critical_issues(self) -> bool:
        return bool(self.get_errors())

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_missing_scans(
        self, session_path: Path, sub_id: str, ses_id: str
    ) -> List[QCFinding]:
        findings = []
        anat_dir = session_path / "anat"
        func_dir = session_path / "func"

        has_t1w = bool(list(anat_dir.glob("*T1w.nii.gz"))) if anat_dir.exists() else False
        has_bold = bool(list(func_dir.glob("*bold.nii.gz"))) if func_dir.exists() else False

        if not has_t1w:
            findings.append(
                QCFinding(
                    severity=Severity.ERROR,
                    sub_id=sub_id,
                    ses_id=ses_id,
                    category="missing_scan",
                    message="No T1w anatomical scan found",
                    plain_message=(
                        "No structural brain image (T1w) was found for this session. "
                        "fMRIPrep cannot run without a T1w scan."
                    ),
                    action="Re-scan: acquire a T1w structural scan for this patient.",
                )
            )

        if not has_bold:
            findings.append(
                QCFinding(
                    severity=Severity.WARNING,
                    sub_id=sub_id,
                    ses_id=ses_id,
                    category="missing_scan",
                    message="No BOLD functional scan found",
                    plain_message=(
                        "No functional brain scan (BOLD) was found in this session."
                    ),
                    action=(
                        "Verify this session was intended to include BOLD scans. "
                        "If yes, re-scan the patient."
                    ),
                )
            )

        return findings

    def _check_file_sizes(
        self, session_path: Path, sub_id: str, ses_id: str
    ) -> List[QCFinding]:
        findings = []

        for nii_file in session_path.rglob("*.nii.gz"):
            try:
                size_mb = nii_file.stat().st_size / (1024 * 1024)
            except OSError:
                continue

            parts_str = nii_file.as_posix()
            if "/anat/" in parts_str:
                min_mb, scan_type = self.MIN_ANAT_SIZE_MB, "structural (T1w/T2w)"
            elif "/func/" in parts_str:
                min_mb, scan_type = self.MIN_FUNC_SIZE_MB, "functional (BOLD)"
            else:
                continue

            if size_mb < min_mb:
                findings.append(
                    QCFinding(
                        severity=Severity.ERROR,
                        sub_id=sub_id,
                        ses_id=ses_id,
                        category="small_file",
                        message=f"{nii_file.name}: {size_mb:.1f} MB (minimum expected: {min_mb:.0f} MB)",
                        plain_message=(
                            f"The {scan_type} scan '{nii_file.name}' is suspiciously small "
                            f"({size_mb:.1f} MB). The scan may be corrupted or the acquisition "
                            f"was aborted early."
                        ),
                        action="Re-scan the patient — the scan data appears incomplete.",
                    )
                )

        return findings

    def _check_bold_trs(
        self, session_path: Path, sub_id: str, ses_id: str
    ) -> List[QCFinding]:
        findings = []
        func_dir = session_path / "func"
        if not func_dir.exists():
            return findings

        for bold_file in sorted(func_dir.glob("*bold.nii.gz")):
            n_trs = self._read_nifti_n_trs(bold_file)
            if n_trs is None:
                continue
            if n_trs < self.min_bold_trs:
                findings.append(
                    QCFinding(
                        severity=Severity.ERROR,
                        sub_id=sub_id,
                        ses_id=ses_id,
                        category="truncated_run",
                        message=(
                            f"{bold_file.name}: only {n_trs} TRs "
                            f"(minimum expected: {self.min_bold_trs})"
                        ),
                        plain_message=(
                            f"The functional scan '{bold_file.name}' has only {n_trs} "
                            f"timepoints. A complete scan should have at least "
                            f"{self.min_bold_trs}. The scan was likely aborted early."
                        ),
                        action=(
                            "Check whether the scan was interrupted. "
                            "Consider re-scanning this patient."
                        ),
                    )
                )

        return findings

    def _check_params(
        self, session_path: Path, sub_id: str, ses_id: str
    ) -> List[QCFinding]:
        """Check scan parameters for cross-subject consistency."""
        findings = []
        params: Dict = {}

        for json_file in sorted(session_path.rglob("*bold.json")):
            try:
                with open(json_file, encoding="utf-8") as f:
                    meta = json.load(f)
                tr = meta.get("RepetitionTime")
                fs = meta.get("MagneticFieldStrength")
                if tr is not None:
                    params["TR"] = float(tr)
                if fs is not None:
                    params["FieldStrength"] = float(fs)
                break
            except Exception:
                continue

        if not params:
            return findings

        with self._lock:
            if not self._param_baseline:
                self._param_baseline = dict(params)
                return findings
            baseline = dict(self._param_baseline)

        if "TR" in params and "TR" in baseline:
            if abs(params["TR"] - baseline["TR"]) > 0.01:
                findings.append(
                    QCFinding(
                        severity=Severity.WARNING,
                        sub_id=sub_id,
                        ses_id=ses_id,
                        category="param_drift",
                        message=(
                            f"TR mismatch: {params['TR']}s "
                            f"(cohort baseline: {baseline['TR']}s)"
                        ),
                        plain_message=(
                            f"The scan timing (TR = {params['TR']}s) differs from "
                            f"other subjects in this dataset ({baseline['TR']}s). "
                            f"This inconsistency may affect group analysis results."
                        ),
                        action=(
                            "Verify the scan protocol was applied correctly. "
                            "Check with the MRI technician."
                        ),
                    )
                )

        if "FieldStrength" in params and "FieldStrength" in baseline:
            if params["FieldStrength"] != baseline["FieldStrength"]:
                findings.append(
                    QCFinding(
                        severity=Severity.ERROR,
                        sub_id=sub_id,
                        ses_id=ses_id,
                        category="param_drift",
                        message=(
                            f"Field strength mismatch: {params['FieldStrength']}T "
                            f"(expected: {baseline['FieldStrength']}T)"
                        ),
                        plain_message=(
                            f"This scan was acquired at {params['FieldStrength']}T field "
                            f"strength, but other subjects used {baseline['FieldStrength']}T. "
                            f"Scans from different field strengths cannot be directly compared."
                        ),
                        action=(
                            "Verify the correct scanner was used. This subject's data "
                            "may need to be excluded from group analysis."
                        ),
                    )
                )

        return findings

    # ------------------------------------------------------------------
    # NIfTI header reading (no nibabel needed)
    # ------------------------------------------------------------------

    def _read_nifti_n_trs(self, nii_gz_path: Path) -> Optional[int]:
        """
        Read the number of timepoints (4th dimension) from a .nii.gz header.

        Reads the NIfTI-1 binary header directly using gzip + struct.
        NIfTI-1 layout: dim array (8 x int16) starts at byte offset 40.
          dim[0] = number of dimensions
          dim[4] = number of volumes / timepoints

        Tries little-endian first; falls back to big-endian if dim[0] is invalid.
        """
        try:
            with gzip.open(nii_gz_path, "rb") as f:
                hdr = f.read(56)

            if len(hdr) < 56:
                return None

            dims = struct.unpack("<8h", hdr[40:56])
            if not (1 <= dims[0] <= 7):
                dims = struct.unpack(">8h", hdr[40:56])

            n_dims = dims[0]
            if n_dims >= 4:
                return int(dims[4])
            elif n_dims == 3:
                return 1
            return None
        except Exception:
            return None
