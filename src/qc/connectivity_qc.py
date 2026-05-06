"""
Connectivity Quality Control — Nilearn-based

Uses Nilearn's ``load_confounds_strategy`` with the ``"scrubbing"`` preset
to handle confound selection and volume censoring in one standardised call.
Heatmaps are computed on **scrubbed** (denoised + censored) data.

Per-run metrics:
  - Censored volumes / % censored / usable scan time
  - Mean framewise displacement
  - Number of nuisance regressors selected by the strategy
  - Loss of temporal degrees of freedom (regressors + censored volumes)
  - Full (116×116) and network-level (~8×8) connectivity heatmaps
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict
import re
import warnings

import numpy as np
import pandas as pd

try:
    import nibabel as nib
    from nilearn import datasets, maskers
    from nilearn.connectome import ConnectivityMeasure
    from nilearn.interfaces.fmriprep import load_confounds_strategy
    NILEARN_AVAILABLE = True
except ImportError:
    NILEARN_AVAILABLE = False
    warnings.warn(
        "Nilearn not available. Connectivity QC will be skipped. "
        "Install with: pip install nilearn nibabel"
    )

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

import base64
from io import BytesIO

from . import connectivity_thresholds as thresh


@dataclass
class ConnectivityQCResult:
    """Result of connectivity quality control for one BOLD run."""
    sub_id: str
    ses_id: str
    run_label: str

    # Volume / censoring metrics
    total_volumes: int = 0
    censored_volumes: int = 0
    pct_censored: float = 0.0
    usable_minutes: float = 0.0
    tr_sec: float = 0.0

    # Motion
    mean_fd: float = 0.0

    # Denoising complexity
    n_regressors: int = 0
    loss_of_dof: int = 0
    loss_of_dof_pct: float = 0.0

    # Overall assessment
    connectivity_ready: bool = False
    worst_severity: str = "UNKNOWN"
    rescan_warning: bool = False

    # Atlas used
    atlas_name: str = "schaefer_116_tian"
    n_rois: int = 0

    # Heatmap visualisations (base64-encoded PNG)
    heatmap_base64: Optional[str] = None
    network_summary_base64: Optional[str] = None

    # Error tracking
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def analyze_all_subjects(
    derivatives_dir,
    bids_dir=None,
    atlas='schaefer_116_tian',
    mni_space='MNI152NLin2009cAsym',
) -> List[ConnectivityQCResult]:
    """
    Analyse connectivity quality for all preprocessed BOLD runs.

    Args:
        derivatives_dir: fMRIPrep derivatives directory.
        bids_dir: BIDS directory (unused here — kept for API compat).
        atlas: Atlas name ('schaefer_116_tian', 'schaefer_200', etc.).
        mni_space: MNI template space to match BOLD files.

    Returns:
        List of ConnectivityQCResult objects.
    """
    if not NILEARN_AVAILABLE:
        return []

    # Load atlas once
    try:
        atlas_img, atlas_labels = _load_atlas(atlas)
    except Exception as e:
        warnings.warn(f"Connectivity QC skipped: could not load atlas — {e}")
        return []

    deriv_path = Path(derivatives_dir)

    # Search for preprocessed BOLD files
    search_roots = [
        deriv_path / "fmriprep",
        deriv_path,
    ]

    seen_paths: set = set()
    bold_files: List[Path] = []
    for root in search_roots:
        if not root.exists():
            continue
        for bold_path in sorted(
            root.rglob(f"*space-{mni_space}*_desc-preproc_bold.nii.gz")
        ):
            resolved = bold_path.resolve()
            if resolved not in seen_paths:
                seen_paths.add(resolved)
                bold_files.append(bold_path)

    results: List[ConnectivityQCResult] = []
    for bold_path in bold_files:
        result = _analyze_single_run(
            bold_path,
            atlas_img=atlas_img,
            atlas_labels=atlas_labels,
            atlas_name=atlas,
            output_dir=deriv_path,
        )
        if result is not None:
            results.append(result)

    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_confounds_tsv(bold_path: Path) -> Optional[Path]:
    """Derive the confounds TSV path from a preprocessed BOLD NIfTI path.

    fMRIPrep places them in the same directory with the pattern:
        sub-*_ses-*_task-*_run-*_desc-confounds_timeseries.tsv
    """
    # Strip space/desc/suffix entities to get the BIDS prefix
    stem = bold_path.name.split("_space-")[0]
    tsv_name = f"{stem}_desc-confounds_timeseries.tsv"
    tsv_path = bold_path.parent / tsv_name
    if tsv_path.exists():
        return tsv_path
    # Fallback: search for any confounds TSV with the same prefix
    prefix = stem.rsplit("_", 1)[0]  # drop last entity for safety
    for candidate in bold_path.parent.glob(f"{prefix}*_desc-confounds_timeseries.tsv"):
        return candidate
    return None


# ---------------------------------------------------------------------------
# Per-run analysis
# ---------------------------------------------------------------------------

def _analyze_single_run(
    bold_path: Path,
    atlas_img,
    atlas_labels,
    atlas_name: str,
    output_dir: Optional[Path] = None,
) -> Optional[ConnectivityQCResult]:
    """Analyse connectivity quality for a single BOLD run."""
    try:
        # --- Extract subject / session / run identifiers ---
        parts = bold_path.parts
        sub_id = next(
            (p.replace("sub-", "") for p in parts if p.startswith("sub-")),
            "unknown",
        )
        ses_id = next(
            (p.replace("ses-", "") for p in parts if p.startswith("ses-")),
            "unknown",
        )
        stem = re.sub(r"_space-.*$", "", bold_path.name.replace(".nii.gz", ""))
        run_label = "_".join(
            p for p in stem.split("_")
            if not p.startswith("sub-") and not p.startswith("ses-")
        )

        # --- Load confounds via Nilearn's scrubbing strategy ---
        confounds, sample_mask = load_confounds_strategy(
            str(bold_path), denoise_strategy="scrubbing"
        )

        # --- NIfTI header: total volumes and TR ---
        img = nib.load(str(bold_path))
        total_volumes = int(img.shape[3]) if len(img.shape) >= 4 else 0
        tr_sec = float(img.header.get_zooms()[3]) if len(img.header.get_zooms()) >= 4 else 2.0

        # --- Censoring metrics ---
        usable_volumes = len(sample_mask) if sample_mask is not None else total_volumes
        censored_volumes = total_volumes - usable_volumes
        pct_censored = (censored_volumes / total_volumes * 100.0) if total_volumes > 0 else 0.0
        usable_minutes = (usable_volumes * tr_sec) / 60.0

        # --- Mean FD from the raw confounds TSV ---
        # load_confounds_strategy returns only selected regressors, which
        # typically does not include framewise_displacement.  Read FD
        # directly from the sibling confounds TSV instead.
        mean_fd = 0.0
        confounds_tsv = _find_confounds_tsv(bold_path)
        if confounds_tsv is not None:
            raw_df = pd.read_csv(confounds_tsv, sep="\t", low_memory=False)
            if "framewise_displacement" in raw_df.columns:
                fd = pd.to_numeric(
                    raw_df["framewise_displacement"], errors="coerce"
                ).dropna()
                if not fd.empty:
                    mean_fd = float(fd.mean())

        # --- Denoising complexity ---
        n_regressors = confounds.shape[1]
        loss_of_dof = n_regressors + censored_volumes
        loss_of_dof_pct = (loss_of_dof / total_volumes * 100.0) if total_volumes > 0 else 0.0

        n_rois = len(atlas_labels) if atlas_labels else 0

        # --- Quality assessment ---
        severity, ready, rescan = _assess_quality(
            mean_fd=mean_fd,
            pct_censored=pct_censored,
            usable_minutes=usable_minutes,
            loss_of_dof_pct=loss_of_dof_pct,
        )

        result = ConnectivityQCResult(
            sub_id=sub_id,
            ses_id=ses_id,
            run_label=run_label,
            total_volumes=total_volumes,
            censored_volumes=censored_volumes,
            pct_censored=pct_censored,
            usable_minutes=usable_minutes,
            tr_sec=tr_sec,
            mean_fd=mean_fd,
            n_regressors=n_regressors,
            loss_of_dof=loss_of_dof,
            loss_of_dof_pct=loss_of_dof_pct,
            connectivity_ready=ready,
            worst_severity=severity,
            rescan_warning=rescan,
            atlas_name=atlas_name,
            n_rois=n_rois,
        )

        # --- Extract denoised time-series (scrubbed) ---
        masker = maskers.NiftiLabelsMasker(
            labels_img=atlas_img,
            standardize="zscore_sample",
            detrend=True,
            low_pass=0.1,
            high_pass=0.01,
            t_r=tr_sec,
            memory="nilearn_cache",
            memory_level=1,
            verbose=0,
        )

        time_series = masker.fit_transform(
            str(bold_path),
            confounds=confounds,
            sample_mask=sample_mask,
        )

        # --- Connectivity matrix (Pearson) ---
        conn_measure = ConnectivityMeasure(kind="correlation")
        connectivity_matrix = conn_measure.fit_transform([time_series])[0]

        # --- Save outputs ---
        if output_dir is not None:
            _save_connectivity_outputs(
                output_dir, sub_id, ses_id, run_label,
                connectivity_matrix, time_series, atlas_labels,
            )

        # --- Heatmaps ---
        if MATPLOTLIB_AVAILABLE:
            result.heatmap_base64 = _generate_heatmap(
                connectivity_matrix, atlas_labels,
            )
            result.network_summary_base64 = _generate_network_summary(
                connectivity_matrix, atlas_labels,
            )

        return result

    except Exception as e:
        return ConnectivityQCResult(
            sub_id="unknown",
            ses_id="unknown",
            run_label=str(bold_path.name),
            error_message=str(e),
        )


# ---------------------------------------------------------------------------
# Quality assessment
# ---------------------------------------------------------------------------

def _assess_quality(
    mean_fd: float,
    pct_censored: float,
    usable_minutes: float,
    loss_of_dof_pct: float,
) -> tuple:
    """
    Apply thresholds and return (severity, ready, rescan).
    """
    fails_fd = mean_fd > thresh.CONNECTIVITY_MEAN_FD_FAIL
    fails_censor = pct_censored > thresh.MAX_CENSORED_PCT_FAIL
    fails_duration = usable_minutes < thresh.MIN_USABLE_MINUTES_FAIL

    warns_fd = mean_fd > thresh.CONNECTIVITY_MEAN_FD_WARN
    warns_censor = pct_censored > thresh.MAX_CENSORED_PCT_WARN
    warns_duration = usable_minutes < thresh.MIN_USABLE_MINUTES_WARN
    warns_dof = loss_of_dof_pct > (thresh.LOSS_DOF_WARN * 100.0)

    if fails_fd or fails_censor or fails_duration:
        return ("ERROR", False, True)

    if warns_fd or warns_censor or warns_duration or warns_dof:
        return ("WARNING", True, False)

    return ("OK", True, False)


# ---------------------------------------------------------------------------
# Atlas loading (unchanged)
# ---------------------------------------------------------------------------

_ATLAS_DATA_DIR = Path(__file__).parent / "atlas_data"

_BUNDLED_ATLAS_LABELS = {
    116: _ATLAS_DATA_DIR / "Schaefer2018_100Parcels_7Networks_Tian_S1_order.txt",
}

_BUNDLED_ATLAS_NIFTI = {
    116: _ATLAS_DATA_DIR / "Schaefer2018_100Parcels_7Networks_order_Tian_Subcortex_S1_3T_MNI152NLin2009cAsym_2mm.nii.gz",
}


def _read_atlas_labels(n_rois: int) -> List[str]:
    """Read ROI names from a bundled label file (column 2 of each line)."""
    label_file = _BUNDLED_ATLAS_LABELS.get(n_rois)
    if label_file and label_file.exists():
        labels = []
        for line in label_file.read_text().splitlines():
            parts = line.split()
            if len(parts) >= 2:
                labels.append(parts[1])
        if labels:
            return labels
    return [f"ROI_{i + 1:03d}" for i in range(n_rois)]


def _fetch_atlas_offline(n_rois: int):
    """
    Load Schaefer+Tian atlas fully offline — no internet download.

    Search order:
    1. Bundled NIfTI in src/qc/atlas_data/
    2. Local nilearn cache directories
    3. Raise RuntimeError with instructions
    """
    # 1. Bundled atlas
    bundled = _BUNDLED_ATLAS_NIFTI.get(n_rois)
    if bundled and bundled.exists():
        labels = _read_atlas_labels(n_rois)
        return str(bundled), labels

    # 2. Local nilearn cache
    search_roots = [
        Path.home() / "nilearn_data",
        Path("/home/fmriprep/nilearn_data"),
        Path("/tmp/nilearn_data"),
    ]
    nii_pattern = f"*Schaefer2018*Parcels*2mm*.nii*"
    for root in search_roots:
        if not root.exists():
            continue
        matches = sorted(root.rglob(nii_pattern))
        if matches:
            labels = _read_atlas_labels(n_rois)
            return str(matches[0]), labels

    raise RuntimeError(
        f"Schaefer+Tian {n_rois}-parcel atlas not available. "
        f"Place the NIfTI in {_ATLAS_DATA_DIR} or ~/nilearn_data/schaefer_2018/."
    )


def _load_atlas(atlas_name: str):
    """Load brain atlas using Nilearn datasets, with offline fallback."""
    atlas_name_lower = atlas_name.lower()

    if "schaefer" in atlas_name_lower:
        n_rois = 116
        if "200" in atlas_name_lower:
            n_rois = 200
        elif "400" in atlas_name_lower:
            n_rois = 400
        return _fetch_atlas_offline(n_rois)

    elif "aal" in atlas_name_lower:
        atlas = datasets.fetch_atlas_aal()
        return atlas['maps'], atlas['labels']

    elif "harvard" in atlas_name_lower or "cortical" in atlas_name_lower:
        atlas = datasets.fetch_atlas_harvard_oxford('cort-maxprob-thr25-2mm')
        return atlas['maps'], atlas['labels']

    else:
        return _fetch_atlas_offline(116)


# ---------------------------------------------------------------------------
# Output persistence (unchanged)
# ---------------------------------------------------------------------------

def _save_connectivity_outputs(
    output_dir: Path,
    sub_id: str,
    ses_id: str,
    run_label: str,
    connectivity_matrix: np.ndarray,
    time_series: np.ndarray,
    atlas_labels: List[str],
) -> None:
    """Save connectivity matrix, time series, and ROI labels to derivatives."""
    try:
        conn_dir = output_dir / "connectivity" / f"sub-{sub_id}" / f"ses-{ses_id}"
        conn_dir.mkdir(parents=True, exist_ok=True)

        prefix = f"sub-{sub_id}_ses-{ses_id}_{run_label}" if run_label else f"sub-{sub_id}_ses-{ses_id}"

        np.save(conn_dir / f"{prefix}_connectivity.npy", connectivity_matrix)
        np.save(conn_dir / f"{prefix}_timeseries.npy", time_series)

        labels_path = conn_dir / f"{prefix}_labels.txt"
        labels_path.write_text("\n".join(atlas_labels))
    except Exception:
        pass  # Non-critical — don't fail the analysis


# ---------------------------------------------------------------------------
# Heatmap visualisations (unchanged)
# ---------------------------------------------------------------------------

def _generate_heatmap(
    connectivity_matrix: np.ndarray,
    atlas_labels: List[str],
) -> Optional[str]:
    """Generate a 116×116 correlation heatmap and return as base64 PNG."""
    if not MATPLOTLIB_AVAILABLE:
        return None
    try:
        fig, ax = plt.subplots(1, 1, figsize=(8, 7))
        im = ax.imshow(
            connectivity_matrix,
            cmap="RdBu_r",
            vmin=-1,
            vmax=1,
            interpolation="nearest",
        )
        ax.set_title("Connectivity Matrix (Pearson r) — scrubbed data", fontsize=12)

        # --- Network boundary lines and labels ---
        networks = _parse_network_assignments(atlas_labels)
        # Build ordered list of (network_name, start_idx, end_idx)
        # by scanning labels in order to preserve atlas ROI ordering.
        seen_order: List[str] = []
        for label in atlas_labels:
            if label.startswith("Tian_") or label.startswith("tian_"):
                net = "Subcortical"
            else:
                parts = label.split("_")
                net = parts[2] if len(parts) >= 3 else "Unknown"
            if net not in seen_order:
                seen_order.append(net)

        n_rois = len(atlas_labels)
        tick_positions = []
        tick_labels = []
        offset = 0
        for net_name in seen_order:
            count = len(networks.get(net_name, []))
            if count == 0:
                continue
            # Boundary line before this group (skip first)
            if offset > 0:
                ax.axhline(y=offset - 0.5, color="black", linewidth=0.5, alpha=0.6)
                ax.axvline(x=offset - 0.5, color="black", linewidth=0.5, alpha=0.6)
            tick_positions.append(offset + count / 2.0 - 0.5)
            tick_labels.append(net_name)
            offset += count

        ax.set_xticks(tick_positions)
        ax.set_yticks(tick_positions)
        ax.set_xticklabels(tick_labels, rotation=45, ha="right", fontsize=8)
        ax.set_yticklabels(tick_labels, fontsize=8)

        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="Correlation")
        fig.tight_layout()

        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("ascii")
    except Exception:
        return None


def _parse_network_assignments(atlas_labels: List[str]) -> Dict[str, List[int]]:
    """
    Parse atlas labels into network groups.

    Schaefer labels: '7Networks_{hemi}_{network}_{region}_{index}'
      -> Split by '_', index 2 = network name (Vis, SomMot, DorsAttn, etc.)
    Tian labels: 'Tian_*' -> grouped as 'Subcortical'

    Returns:
        Dict mapping network name -> list of ROI indices (0-based)
    """
    networks: Dict[str, List[int]] = {}
    for i, label in enumerate(atlas_labels):
        if label.startswith("Tian_") or label.startswith("tian_"):
            net = "Subcortical"
        else:
            parts = label.split("_")
            if len(parts) >= 3:
                net = parts[2]
            else:
                net = "Unknown"
        networks.setdefault(net, []).append(i)
    return networks


def _generate_network_summary(
    connectivity_matrix: np.ndarray,
    atlas_labels: List[str],
) -> Optional[str]:
    """
    Collapse 116 ROIs into ~8 networks and render an annotated summary heatmap.

    Returns base64 PNG string.
    """
    if not MATPLOTLIB_AVAILABLE:
        return None
    try:
        networks = _parse_network_assignments(atlas_labels)
        if len(networks) < 2:
            return None

        net_names = sorted(networks.keys())
        n_nets = len(net_names)
        summary = np.zeros((n_nets, n_nets))

        for i, net_i in enumerate(net_names):
            for j, net_j in enumerate(net_names):
                roi_i = networks[net_i]
                roi_j = networks[net_j]
                values = connectivity_matrix[np.ix_(roi_i, roi_j)]
                summary[i, j] = np.nanmean(values)

        fig, ax = plt.subplots(1, 1, figsize=(6, 5))
        im = ax.imshow(
            summary,
            cmap="RdBu_r",
            vmin=-0.5,
            vmax=0.5,
            interpolation="nearest",
        )
        ax.set_xticks(range(n_nets))
        ax.set_yticks(range(n_nets))
        ax.set_xticklabels(net_names, rotation=45, ha="right", fontsize=9)
        ax.set_yticklabels(net_names, fontsize=9)
        ax.set_title("Network-level Connectivity (scrubbed)", fontsize=12)

        for i in range(n_nets):
            for j in range(n_nets):
                val = summary[i, j]
                color = "white" if abs(val) > 0.25 else "black"
                ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                        fontsize=8, color=color)

        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="Mean r")
        fig.tight_layout()

        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("ascii")
    except Exception:
        return None
