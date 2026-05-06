"""
Auto-populate IntendedFor in field map JSON sidecars.

After BIDS conversion, field map sidecars need an IntendedFor field so
fMRIPrep knows which functional runs each field map corrects.  This module
matches field maps to BOLD runs by acquisition-time proximity and writes
the IntendedFor entries automatically.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from ..core.utils import safe_print
except ImportError:
    from core.utils import safe_print


# Maximum time gap (seconds) between AP and PA EPIs to consider them a pair
_PAIR_TIME_WINDOW = 600  # 10 minutes


@dataclass
class _ScanInfo:
    """Metadata extracted from a single JSON sidecar."""
    json_path: Path
    acq_time: Optional[datetime] = None
    phase_dir: str = ""
    shim_setting: Optional[list] = None
    suffix: str = ""  # "epi" or "phasediff" or "bold"


@dataclass
class _FmapGroup:
    """One or more field map files that form a logical group."""
    scans: List[_ScanInfo] = field(default_factory=list)
    avg_time: Optional[datetime] = None


def populate_intended_for(session_dir: Path) -> int:
    """Populate IntendedFor in every field map JSON under *session_dir*.

    Args:
        session_dir: BIDS session directory, e.g.
            ``<bids>/sub-001/ses-01``

    Returns:
        Number of field map JSON files updated.
    """
    session_dir = Path(session_dir)
    fmap_dir = session_dir / "fmap"
    func_dir = session_dir / "func"

    if not fmap_dir.is_dir() or not func_dir.is_dir():
        return 0

    # Discover scans
    fmap_scans = _load_scans(fmap_dir, suffix_filter=("epi", "phasediff"))
    func_scans = _load_scans(func_dir, suffix_filter=("bold",))

    if not fmap_scans or not func_scans:
        return 0

    # Build IntendedFor paths (relative to subject dir, forward slashes)
    subject_dir = session_dir.parent
    intended_paths = []
    for scan in func_scans:
        nii = scan.json_path.with_suffix(".nii.gz")
        if not nii.exists():
            nii = scan.json_path.with_suffix(".nii")
        if nii.exists():
            rel = nii.relative_to(subject_dir).as_posix()
            intended_paths.append(rel)

    if not intended_paths:
        return 0

    # Group field maps
    groups = _build_fmap_groups(fmap_scans)

    # Check if any timing information is available
    has_timing = (
        any(g.avg_time is not None for g in groups)
        and any(s.acq_time is not None for s in func_scans)
    )

    # Assign func runs to groups
    if len(groups) == 1 or not has_timing:
        # Single group or no timing: all runs go to all groups
        assignment: Dict[int, List[str]] = {
            i: list(intended_paths) for i in range(len(groups))
        }
    else:
        assignment = _assign_by_proximity(groups, func_scans, subject_dir)

    # Write IntendedFor into each fieldmap JSON
    updated = 0
    for group_idx, group in enumerate(groups):
        paths_for_group = assignment.get(group_idx, [])
        if not paths_for_group:
            continue
        for scan in group.scans:
            if _write_intended_for(scan.json_path, paths_for_group):
                updated += 1

    if updated:
        safe_print(
            f"  IntendedFor: updated {updated} fieldmap sidecar(s) "
            f"({len(intended_paths)} BOLD run(s))",
            flush=True,
        )

    return updated


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_acq_time(raw: str) -> Optional[datetime]:
    """Parse AcquisitionTime string from dcm2niix."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%H:%M:%S.%f")
    except ValueError:
        try:
            return datetime.strptime(raw, "%H:%M:%S")
        except ValueError:
            return None


def _load_scans(
    directory: Path,
    suffix_filter: Tuple[str, ...],
) -> List[_ScanInfo]:
    """Read JSON sidecars from *directory* and return _ScanInfo list."""
    scans: List[_ScanInfo] = []
    for jf in sorted(directory.glob("*.json")):
        try:
            with open(jf, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            continue

        # Determine suffix from filename: *_epi.json, *_phasediff.json, *_bold.json
        stem = jf.stem  # e.g. sub-001_ses-01_dir-AP_epi
        file_suffix = stem.rsplit("_", 1)[-1] if "_" in stem else ""
        if file_suffix not in suffix_filter:
            continue

        info = _ScanInfo(
            json_path=jf,
            acq_time=_parse_acq_time(meta.get("AcquisitionTime", "")),
            phase_dir=meta.get("PhaseEncodingDirection", ""),
            shim_setting=meta.get("ShimSetting"),
            suffix=file_suffix,
        )
        scans.append(info)

    return scans


def _build_fmap_groups(fmap_scans: List[_ScanInfo]) -> List[_FmapGroup]:
    """Group pepolar EPI pairs and standalone phasediff maps."""
    groups: List[_FmapGroup] = []
    used = set()

    # Pair pepolar EPIs (AP + PA within time window)
    ap_scans = [s for s in fmap_scans if s.suffix == "epi" and "j-" in s.phase_dir]
    pa_scans = [s for s in fmap_scans if s.suffix == "epi" and s.phase_dir == "j"]

    for ap in ap_scans:
        best_pa = None
        best_dt = None
        for pa in pa_scans:
            if id(pa) in used:
                continue
            if ap.acq_time and pa.acq_time:
                dt = abs((ap.acq_time - pa.acq_time).total_seconds())
                if dt <= _PAIR_TIME_WINDOW and (best_dt is None or dt < best_dt):
                    best_pa = pa
                    best_dt = dt
            elif best_pa is None:
                # No timing — just pair them in order
                best_pa = pa

        group = _FmapGroup(scans=[ap])
        used.add(id(ap))
        if best_pa is not None:
            group.scans.append(best_pa)
            used.add(id(best_pa))
        group.avg_time = _avg_time(group.scans)
        groups.append(group)

    # Unpaired PA EPIs
    for pa in pa_scans:
        if id(pa) not in used:
            group = _FmapGroup(scans=[pa])
            group.avg_time = pa.acq_time
            used.add(id(pa))
            groups.append(group)

    # Unpaired EPIs with no direction
    for scan in fmap_scans:
        if scan.suffix == "epi" and id(scan) not in used:
            group = _FmapGroup(scans=[scan])
            group.avg_time = scan.acq_time
            used.add(id(scan))
            groups.append(group)

    # Phasediff maps: each is its own group
    for scan in fmap_scans:
        if scan.suffix == "phasediff" and id(scan) not in used:
            group = _FmapGroup(scans=[scan])
            group.avg_time = scan.acq_time
            used.add(id(scan))
            groups.append(group)

    return groups


def _avg_time(scans: List[_ScanInfo]) -> Optional[datetime]:
    """Average AcquisitionTime across scans that have one."""
    times = [s.acq_time for s in scans if s.acq_time is not None]
    if not times:
        return None
    total = sum((t - times[0]).total_seconds() for t in times)
    return times[0] + timedelta(seconds=total / len(times))


def _assign_by_proximity(
    groups: List[_FmapGroup],
    func_scans: List[_ScanInfo],
    subject_dir: Path,
) -> Dict[int, List[str]]:
    """Assign each func run to its nearest fmap group by time."""
    assignment: Dict[int, List[str]] = {i: [] for i in range(len(groups))}

    for scan in func_scans:
        nii = scan.json_path.with_suffix(".nii.gz")
        if not nii.exists():
            nii = scan.json_path.with_suffix(".nii")
        if not nii.exists():
            continue
        rel = nii.relative_to(subject_dir).as_posix()

        if scan.acq_time is None:
            # No timing on this run — assign to all groups
            for i in range(len(groups)):
                assignment[i].append(rel)
            continue

        best_idx = 0
        best_dt = float("inf")
        best_shim_match = False

        for i, group in enumerate(groups):
            if group.avg_time is None:
                continue
            dt = abs((scan.acq_time - group.avg_time).total_seconds())
            # Use ShimSetting as tiebreaker when two groups are equidistant
            shim_match = (
                scan.shim_setting is not None
                and any(s.shim_setting == scan.shim_setting for s in group.scans)
            )
            if dt < best_dt or (dt == best_dt and shim_match and not best_shim_match):
                best_dt = dt
                best_idx = i
                best_shim_match = shim_match

        assignment[best_idx].append(rel)

    return assignment


def _write_intended_for(json_path: Path, intended_paths: List[str]) -> bool:
    """Write IntendedFor into a fieldmap JSON sidecar.

    Skips if IntendedFor is already present.  Returns True if the file was
    actually updated.
    """
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        if "IntendedFor" in meta:
            return False

        meta["IntendedFor"] = sorted(intended_paths)

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=4)
        return True

    except Exception as e:
        safe_print(
            f"  Warning: could not write IntendedFor to {json_path.name}: {e}",
            flush=True,
        )
        return False
