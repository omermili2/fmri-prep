"""
Connectivity Quality Control - Layer 5b

Implements advanced QC metrics for functional connectivity analysis:
1. DM-FC (split-based): Distance-dependent motion effects using high/low-FD split
2. Network Modularity: Verification of network structure preservation

Based on PMC10977879 and Nilearn's connectivity tools.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Tuple
import re
import warnings

import numpy as np
import pandas as pd

try:
    import nibabel as nib
    from nilearn import datasets, maskers, image
    from nilearn.connectome import ConnectivityMeasure
    from scipy.spatial.distance import pdist, squareform
    from scipy.stats import pearsonr, spearmanr
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

    # Basic motion metrics
    mean_fd: float
    n_volumes: int

    # DM-FC: Distance-dependent motion (split-based)
    dm_fc_value: Optional[float] = None
    dm_fc_severity: str = "UNKNOWN"
    dm_fc_note: str = ""

    # Network modularity
    modularity_q: Optional[float] = None
    modularity_severity: str = "UNKNOWN"

    # Overall assessment
    connectivity_ready: bool = False
    worst_severity: str = "UNKNOWN"
    plain_message: str = ""
    action: str = ""

    # Atlas used
    atlas_name: str = "schaefer_116_tian"
    n_rois: int = 0

    # Heatmap visualizations (base64-encoded PNG)
    heatmap_base64: Optional[str] = None
    network_summary_base64: Optional[str] = None

    # Error tracking
    error_message: Optional[str] = None


def analyze_all_subjects(
    derivatives_dir,
    bids_dir=None,
    atlas='schaefer_116_tian',
    compute_dm_fc=True,
    compute_modularity=False,  # Expensive, off by default
    mni_space='MNI152NLin2009cAsym'
) -> List[ConnectivityQCResult]:
    """
    Analyze connectivity quality for all subjects.

    Args:
        derivatives_dir: fMRIPrep derivatives directory
        bids_dir: BIDS directory (optional, for participant demographics)
        atlas: Atlas name ('schaefer_116_tian', 'schaefer_200', 'aal', etc.)
        compute_dm_fc: Calculate DM-FC metric
        compute_modularity: Calculate network modularity (slow)

    Returns:
        List of ConnectivityQCResult objects
    """
    if not NILEARN_AVAILABLE:
        return []

    # Load atlas once — avoids repeated failed download attempts per run
    try:
        atlas_img, atlas_labels = _load_atlas(atlas)
    except Exception as e:
        warnings.warn(f"Connectivity QC skipped: could not load atlas — {e}")
        return []

    deriv_path = Path(derivatives_dir)
    output_dir = deriv_path

    # Search for preprocessed BOLD files
    search_roots = [
        deriv_path / "fmriprep",
        deriv_path,
    ]

    # Collect files from all search roots, deduplicating by resolved path
    seen_paths: set = set()
    bold_files = []
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
            compute_dm_fc=compute_dm_fc,
            compute_modularity=compute_modularity,
            output_dir=output_dir
        )
        if result is not None:
            results.append(result)

    return results


def _analyze_single_run(
    bold_path: Path,
    atlas_img,
    atlas_labels,
    atlas_name: str,
    compute_dm_fc: bool,
    compute_modularity: bool,
    output_dir: Optional[Path] = None
) -> Optional[ConnectivityQCResult]:
    """Analyze connectivity quality for a single BOLD run."""

    try:
        # Extract subject/session/run info
        parts = bold_path.parts
        sub_id = next(
            (p.replace("sub-", "") for p in parts if p.startswith("sub-")), "unknown"
        )
        ses_id = next(
            (p.replace("ses-", "") for p in parts if p.startswith("ses-")), "unknown"
        )

        stem = re.sub(r"_space-.*$", "", bold_path.name.replace(".nii.gz", ""))
        run_label = "_".join(
            p for p in stem.split("_")
            if not p.startswith("sub-") and not p.startswith("ses-")
        )

        # Find corresponding confounds file
        confounds_name = re.sub(
            r"_space-[^_]+(_res-[^_]+)?_desc-preproc_bold\.nii\.gz$",
            "_desc-confounds_timeseries.tsv",
            bold_path.name
        )
        confounds_path = bold_path.parent / confounds_name

        if not confounds_path.exists():
            return None

        # Load confounds
        confounds_df = pd.read_csv(confounds_path, sep="\t", low_memory=False)

        if "framewise_displacement" not in confounds_df.columns:
            return None

        fd_series = pd.to_numeric(
            confounds_df["framewise_displacement"], errors="coerce"
        ).fillna(0)  # Fill first NaN with 0

        mean_fd = float(fd_series.mean())
        n_volumes = len(fd_series)

        n_rois = len(atlas_labels) if atlas_labels else 0

        # Extract time series using Nilearn masker (no bandpass for split approach)
        masker = maskers.NiftiLabelsMasker(
            labels_img=atlas_img,
            standardize="zscore_sample",
            detrend=True,
            low_pass=0.1,
            high_pass=0.01,
            t_r=2.0,  # Default TR, should ideally read from JSON
            memory="nilearn_cache",
            memory_level=1,
            verbose=0
        )

        # Select minimal confounds (basic strategy)
        confound_cols = _select_confounds(confounds_df)
        confounds_minimal = confounds_df[confound_cols].fillna(0)

        # Extract time series
        time_series = masker.fit_transform(str(bold_path), confounds=confounds_minimal)

        # Compute connectivity matrix
        conn_measure = ConnectivityMeasure(kind='correlation')
        connectivity_matrix = conn_measure.fit_transform([time_series])[0]

        # Initialize result
        result = ConnectivityQCResult(
            sub_id=sub_id,
            ses_id=ses_id,
            run_label=run_label,
            mean_fd=mean_fd,
            n_volumes=n_volumes,
            atlas_name=atlas_name,
            n_rois=n_rois
        )

        # Save connectivity outputs (matrix, time series, labels)
        if output_dir is not None:
            _save_connectivity_outputs(
                output_dir, sub_id, ses_id, run_label,
                connectivity_matrix, time_series, atlas_labels
            )

        # Generate heatmap visualizations
        if MATPLOTLIB_AVAILABLE:
            result.heatmap_base64 = _generate_heatmap(
                connectivity_matrix, atlas_labels
            )
            result.network_summary_base64 = _generate_network_summary(
                connectivity_matrix, atlas_labels
            )

        # Compute DM-FC (split-based distance-dependent motion)
        if compute_dm_fc:
            dm_fc_result = _compute_dm_fc_split(
                time_series, masker, fd_series
            )
            if dm_fc_result is not None:
                dm_fc_value, dm_fc_note = dm_fc_result
                result.dm_fc_value = dm_fc_value
                result.dm_fc_note = dm_fc_note

                if abs(dm_fc_value) >= thresh.DM_FC_FAIL:
                    result.dm_fc_severity = "ERROR"
                elif abs(dm_fc_value) >= thresh.DM_FC_WARN:
                    result.dm_fc_severity = "WARNING"
                else:
                    result.dm_fc_severity = "OK"
            else:
                # Too few frames in one split — treated as OK (low motion is good)
                result.dm_fc_value = None
                result.dm_fc_severity = "OK"
                result.dm_fc_note = "Insufficient high-motion frames for split (scan is low-motion)"

        # Compute modularity (expensive, optional)
        if compute_modularity:
            try:
                import networkx as nx
                from networkx.algorithms import community

                # Convert connectivity to graph
                threshold = 0.3  # Only keep strong connections
                adj_matrix = (connectivity_matrix > threshold).astype(int)
                G = nx.from_numpy_array(adj_matrix)

                # Louvain community detection
                communities = community.louvain_communities(G, seed=42)
                result.modularity_q = community.modularity(G, communities)

                if result.modularity_q < thresh.MIN_MODULARITY_FAIL:
                    result.modularity_severity = "ERROR"
                elif result.modularity_q < thresh.MIN_MODULARITY_WARN:
                    result.modularity_severity = "WARNING"
                else:
                    result.modularity_severity = "OK"

            except Exception:
                result.modularity_q = None
                result.modularity_severity = "UNKNOWN"

        # Overall assessment
        _assess_overall_quality(result)

        return result

    except Exception as e:
        # Return partial result with error message
        return ConnectivityQCResult(
            sub_id="unknown",
            ses_id="unknown",
            run_label=str(bold_path.name),
            mean_fd=0.0,
            n_volumes=0,
            error_message=str(e)
        )


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
        # Default: 100 Schaefer cortical + 16 Tian subcortical = 116
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


def _select_confounds(confounds_df: pd.DataFrame) -> List[str]:
    """
    Select minimal confound regressors for connectivity analysis.

    Strategy: 6 motion parameters + their derivatives + CSF/WM signals
    (avoid global signal regression for connectivity)
    """
    selected = []

    # Motion parameters (6 rigid body: 3 translation + 3 rotation)
    motion_params = ['trans_x', 'trans_y', 'trans_z', 'rot_x', 'rot_y', 'rot_z']
    for param in motion_params:
        if param in confounds_df.columns:
            selected.append(param)
            # Add derivatives
            deriv = f"{param}_derivative1"
            if deriv in confounds_df.columns:
                selected.append(deriv)

    # CSF signal (cerebrospinal fluid - non-neural)
    if 'csf' in confounds_df.columns:
        selected.append('csf')

    # White matter signal (non-neural)
    if 'white_matter' in confounds_df.columns:
        selected.append('white_matter')

    return selected


def _get_roi_centroids(masker) -> Optional[np.ndarray]:
    """
    Extract ROI centroids (in mm) from a fitted NiftiLabelsMasker.

    Returns an (n_rois, 3) array of MNI coordinates, or None on failure.
    """
    try:
        if not hasattr(masker, 'labels_img_'):
            return None

        labels_img = masker.labels_img_
        labels_data = labels_img.get_fdata()
        unique_labels = np.unique(labels_data)[1:]  # Exclude 0 (background)

        coords = []
        for label in unique_labels:
            label_mask = labels_data == label
            label_coords = np.argwhere(label_mask)
            if len(label_coords) > 0:
                centroid = label_coords.mean(axis=0)
                centroid_mm = nib.affines.apply_affine(labels_img.affine, centroid)
                coords.append(centroid_mm)

        if len(coords) < 2:
            return None

        return np.array(coords)
    except Exception:
        return None


def _compute_dm_fc_split(
    time_series: np.ndarray,
    masker,
    fd_series: pd.Series
) -> Optional[Tuple[float, str]]:
    """
    Compute DM-FC using a high/low-FD split approach.

    1. Split FD timeseries by threshold into high_mask and low_mask
    2. If either group has <MIN_FRAMES frames -> return None
    3. Split time series into high_ts and low_ts
    4. Compute connectivity matrix for each split (Pearson correlation)
    5. diff_conn = high_conn - low_conn
    6. Compute pairwise Euclidean distances between ROI centroids
    7. pearsonr(distances, diff_conn) for upper triangle
    8. Strong negative r -> motion inflates short-range connections (bad)
    9. Near-zero r -> denoising worked (good)

    Returns:
        (dm_fc_value, note) tuple, or None if too few frames in either split.
    """
    try:
        fd_values = fd_series.values.astype(float)
        n_timepoints = time_series.shape[0]

        # Ensure FD and time series have same length
        min_len = min(len(fd_values), n_timepoints)
        fd_values = fd_values[:min_len]
        ts = time_series[:min_len]

        # Split by FD threshold
        high_mask = fd_values > thresh.DM_FC_FD_SPLIT
        low_mask = ~high_mask

        n_high = int(high_mask.sum())
        n_low = int(low_mask.sum())

        if n_high < thresh.DM_FC_MIN_FRAMES or n_low < thresh.DM_FC_MIN_FRAMES:
            return None

        # Split time series
        high_ts = ts[high_mask]
        low_ts = ts[low_mask]

        # Compute connectivity for each split
        conn_measure = ConnectivityMeasure(kind='correlation')
        high_conn = conn_measure.fit_transform([high_ts])[0]
        low_conn = conn_measure.fit_transform([low_ts])[0]

        # Difference: high-motion minus low-motion connectivity
        diff_conn = high_conn - low_conn

        # Get ROI centroids for distance calculation
        coords = _get_roi_centroids(masker)
        if coords is None:
            return None

        # Compute pairwise Euclidean distances
        distances = squareform(pdist(coords, metric='euclidean'))

        # Extract upper triangle
        n_rois = diff_conn.shape[0]
        triu_indices = np.triu_indices(n_rois, k=1)

        distance_values = distances[triu_indices]
        diff_values = diff_conn[triu_indices]

        # Correlate distance with connectivity difference
        if len(distance_values) > 0 and len(diff_values) > 0:
            # Filter out NaN/Inf
            valid = np.isfinite(distance_values) & np.isfinite(diff_values)
            if valid.sum() < 10:
                return None

            corr, pval = pearsonr(distance_values[valid], diff_values[valid])
            note = (
                f"Split: {n_high} high-FD / {n_low} low-FD frames "
                f"(threshold={thresh.DM_FC_FD_SPLIT}mm); "
                f"r={corr:.3f}, p={pval:.4f}"
            )
            return (float(corr), note)

    except Exception:
        pass

    return None


def _save_connectivity_outputs(
    output_dir: Path,
    sub_id: str,
    ses_id: str,
    run_label: str,
    connectivity_matrix: np.ndarray,
    time_series: np.ndarray,
    atlas_labels: List[str]
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


def _generate_heatmap(
    connectivity_matrix: np.ndarray,
    atlas_labels: List[str]
) -> Optional[str]:
    """Generate a 116x116 correlation heatmap and return as base64 PNG."""
    if not MATPLOTLIB_AVAILABLE:
        return None
    try:
        fig, ax = plt.subplots(1, 1, figsize=(8, 7))
        im = ax.imshow(
            connectivity_matrix,
            cmap="RdBu_r",
            vmin=-1,
            vmax=1,
            interpolation="nearest"
        )
        ax.set_title("Connectivity Matrix (Pearson r)", fontsize=12)
        ax.set_xlabel("ROI")
        ax.set_ylabel("ROI")
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
    atlas_labels: List[str]
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
                # Average connectivity between networks
                values = connectivity_matrix[np.ix_(roi_i, roi_j)]
                summary[i, j] = np.nanmean(values)

        fig, ax = plt.subplots(1, 1, figsize=(6, 5))
        im = ax.imshow(
            summary,
            cmap="RdBu_r",
            vmin=-0.5,
            vmax=0.5,
            interpolation="nearest"
        )
        ax.set_xticks(range(n_nets))
        ax.set_yticks(range(n_nets))
        ax.set_xticklabels(net_names, rotation=45, ha="right", fontsize=9)
        ax.set_yticklabels(net_names, fontsize=9)
        ax.set_title("Network-level Connectivity", fontsize=12)

        # Annotate cells with values
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


def _assess_overall_quality(result: ConnectivityQCResult):
    """Assess overall connectivity quality and populate messages."""

    # Determine worst severity
    severities = [result.dm_fc_severity, result.modularity_severity]
    if "ERROR" in severities:
        result.worst_severity = "ERROR"
        result.connectivity_ready = False
    elif "WARNING" in severities:
        result.worst_severity = "WARNING"
        result.connectivity_ready = True  # Marginal
    elif "OK" in severities:
        result.worst_severity = "OK"
        result.connectivity_ready = True
    else:
        result.worst_severity = "UNKNOWN"
        result.connectivity_ready = False

    # Build message
    messages = []
    if result.dm_fc_value is not None:
        messages.append(f"DM-FC={result.dm_fc_value:.3f} ({result.dm_fc_severity})")
    elif result.dm_fc_note:
        messages.append(f"DM-FC: {result.dm_fc_note}")
    if result.modularity_q is not None:
        messages.append(f"Modularity Q={result.modularity_q:.3f} ({result.modularity_severity})")

    if messages:
        result.plain_message = "; ".join(messages)
    else:
        result.plain_message = "Connectivity metrics could not be computed"

    # Action recommendation
    if result.worst_severity == "ERROR":
        result.action = "Not recommended for connectivity analysis due to motion artifacts."
    elif result.worst_severity == "WARNING":
        result.action = "Usable for connectivity but apply stringent scrubbing and verify with sensitivity analyses."
    elif result.worst_severity == "OK":
        result.action = "Suitable for connectivity analysis."
    else:
        result.action = "Unable to assess connectivity quality."
