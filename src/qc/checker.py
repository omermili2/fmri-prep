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

    Detects common data quality issues after BIDS conversion.
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

    def add_bold_notes(
        self, sub_id: str, ses_id: str, bold_notes: list
    ) -> List[QCFinding]:
        """
        Create QC findings from BOLD conversion notes (dropped fragments,
        duplicate runs kept).

        ``bold_notes`` is a list of dicts produced by ``_organize_to_bids()``:
            {"action": "dropped"|"kept", "task": str,
             "file": str, "volumes": int, "series_desc": str}
        """
        new_findings: List[QCFinding] = []
        if not bold_notes:
            return new_findings

        dropped = [n for n in bold_notes if n["action"] == "dropped"]
        excluded = [n for n in bold_notes if n["action"] == "kept_excluded"]
        kept = [n for n in bold_notes if n["action"] == "kept"]

        # --- Report each dropped fragment ---
        for d in dropped:
            new_findings.append(
                QCFinding(
                    severity=Severity.WARNING,
                    sub_id=sub_id,
                    ses_id=ses_id,
                    category="bold_fragment_dropped",
                    message=(
                        f"Dropped BOLD fragment: task-{d['task']} "
                        f"({d['volumes']} volumes, series: {d['series_desc']})"
                    ),
                    plain_message=(
                        f"A BOLD fragment with only {d['volumes']} volume(s) "
                        f"(task-{d['task']}, series '{d['series_desc']}') "
                        f"was detected and excluded from preprocessing. "
                        f"This is typically a dcm2niix split artifact."
                    ),
                    action="",
                )
            )

        # --- Report shorter duplicate runs excluded from fMRIPrep ---
        for exc in excluded:
            # Find the kept run for the same task
            same_task_kept = [n for n in kept if n["task"] == exc["task"]]
            kept_vols = same_task_kept[0]["volumes"] if same_task_kept else "?"
            new_findings.append(
                QCFinding(
                    severity=Severity.WARNING,
                    sub_id=sub_id,
                    ses_id=ses_id,
                    category="duplicate_bold_run",
                    message=(
                        f"task-{exc['task']}: shorter run ({exc['volumes']} vols) "
                        f"excluded from fMRIPrep, longer run ({kept_vols} vols) kept"
                    ),
                    plain_message=(
                        f"Multiple BOLD runs found for task-{exc['task']}. "
                        f"The shorter run ({exc['volumes']} vols) was excluded "
                        f"from fMRIPrep preprocessing; the longer run "
                        f"({kept_vols} vols) was kept. Both files remain in "
                        f"the BIDS directory."
                    ),
                    action="",
                )
            )

        if new_findings:
            with self._lock:
                self.findings.extend(new_findings)

        return new_findings

    def check_run_consistency(
        self, bids_dir, subjects_tasks: Dict
    ) -> List[QCFinding]:
        """
        Compare scan profiles across sessions within the same subject.

        For each subject with 2+ sessions, the first session (sorted) is
        treated as the baseline.  Any subsequent session whose scan counts
        differ produces a WARNING-level finding.

        Returns the list of new findings (also stored internally).
        """
        bids_path = Path(bids_dir)
        new_findings: List[QCFinding] = []

        for sub_id, sub_tasks in subjects_tasks.items():
            # Collect unique session IDs for this subject
            ses_ids = sorted({t["ses_id"] for t in sub_tasks})
            if len(ses_ids) < 2:
                continue

            # Build a scan profile for each session
            profiles: Dict[str, Dict[str, int]] = {}
            for ses_id in ses_ids:
                session_path = bids_path / f"sub-{sub_id}" / f"ses-{ses_id}"
                if not session_path.exists():
                    continue
                profiles[ses_id] = self._build_scan_profile(session_path)

            if len(profiles) < 2:
                continue

            baseline_ses = ses_ids[0]
            baseline = profiles.get(baseline_ses)
            if baseline is None:
                continue

            for ses_id in ses_ids[1:]:
                profile = profiles.get(ses_id)
                if profile is None:
                    continue

                # Compare all keys present in either profile
                all_keys = sorted(set(baseline) | set(profile))
                for key in all_keys:
                    b_count = baseline.get(key, 0)
                    s_count = profile.get(key, 0)
                    if b_count != s_count:
                        new_findings.append(
                            QCFinding(
                                severity=Severity.WARNING,
                                sub_id=sub_id,
                                ses_id=ses_id,
                                category="run_consistency",
                                message=(
                                    f"ses-{ses_id} has {s_count} {key} file(s) "
                                    f"but ses-{baseline_ses} has {b_count}"
                                ),
                                plain_message=(
                                    f"Session ses-{ses_id} has {s_count} {key} "
                                    f"file(s) while the baseline session "
                                    f"ses-{baseline_ses} has {b_count}. "
                                    f"The scan protocol may differ."
                                ),
                                action="",
                            )
                        )

        if new_findings:
            with self._lock:
                self.findings.extend(new_findings)

        return new_findings

    @staticmethod
    def _build_scan_profile(session_path: Path) -> Dict[str, int]:
        """
        Build a dict of scan-type → count for a BIDS session directory.

        Keys produced:
          - ``task-<name>_bold`` for each task name found under func/
          - ``T1w`` for structural scans under anat/
          - ``fmap`` for fieldmap files under fmap/
        """
        import re

        profile: Dict[str, int] = {}

        func_dir = session_path / "func"
        if func_dir.exists():
            for f in func_dir.glob("*_bold.nii.gz"):
                m = re.search(r"task-([A-Za-z0-9]+)", f.name)
                key = f"task-{m.group(1)}_bold" if m else "bold"
                profile[key] = profile.get(key, 0) + 1

        anat_dir = session_path / "anat"
        if anat_dir.exists():
            count = len(list(anat_dir.glob("*T1w.nii.gz")))
            if count:
                profile["T1w"] = count

        fmap_dir = session_path / "fmap"
        if fmap_dir.exists():
            count = len(list(fmap_dir.glob("*.nii.gz")))
            if count:
                profile["fmap"] = count

        return profile

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
                        "No T1w anatomical scan was found for this session. "
                        "fMRIPrep requires a T1w scan as input."
                    ),
                    action="",
                )
            )

        if not has_bold:
            findings.append(
                QCFinding(
                    severity=Severity.ERROR,
                    sub_id=sub_id,
                    ses_id=ses_id,
                    category="missing_scan",
                    message="No BOLD functional scan found",
                    plain_message=(
                        "No BOLD functional scan was found in this session. "
                        "fMRIPrep requires BOLD images and will be skipped."
                    ),
                    action="",
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
                            f"The {scan_type} scan '{nii_file.name}' is {size_mb:.1f} MB, "
                            f"below the expected minimum of {min_mb:.0f} MB."
                        ),
                        action="",
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
                            f"The functional scan '{bold_file.name}' has {n_trs} "
                            f"timepoints (minimum expected: {self.min_bold_trs})."
                        ),
                        action="",
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
                            f"TR for this session is {params['TR']}s; "
                            f"other subjects in this dataset have TR = {baseline['TR']}s."
                        ),
                        action="",
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
                            f"Field strength is {params['FieldStrength']}T; "
                            f"other subjects in this dataset used {baseline['FieldStrength']}T."
                        ),
                        action="",
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
