import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple

def load_connectivity_data(subject_dir: Path, session: str, task: str) -> Tuple[np.ndarray, List[str]]:
    """
    Load connectivity matrix and labels for a specific subject, session, and task.
    """
    conn_file = subject_dir / session / f"{subject_dir.name}_{session}_task-{task}_connectivity.npy"
    label_file = subject_dir / session / f"{subject_dir.name}_{session}_task-{task}_labels.txt"
    
    if not conn_file.exists() or not label_file.exists():
        raise FileNotFoundError(f"Missing connectivity files for {subject_dir.name} {session} {task}")
        
    matrix = np.load(conn_file)
    with open(label_file, "r") as f:
        labels = [line.strip() for line in f.readlines()]
        
    return matrix, labels

def get_network_indices(labels: List[str]) -> Dict[str, List[int]]:
    """
    Group ROI indices by network name based on Schaefer labels.
    """
    networks = {}
    for i, label in enumerate(labels):
        if label.startswith("Tian_") or label.startswith("tian_"):
            net = "Subcortical"
        else:
            parts = label.split("_")
            net = parts[2] if len(parts) >= 3 else "Unknown"
        
        if net not in networks:
            networks[net] = []
        networks[net].append(i)
    return networks

def calculate_segregation(matrix: np.ndarray, networks: Dict[str, List[int]], net_a: str, net_b: str) -> Dict[str, float]:
    """
    Calculate segregation metrics between two networks (e.g., 'SalVentAttn' and 'Default').
    
    Formula for System Segregation (Chan et al., 2014):
    (MeanWithin - MeanBetween) / MeanWithin
    """
    idx_a = networks.get(net_a, [])
    idx_b = networks.get(net_b, [])
    
    if not idx_a or not idx_b:
        return {"mean_a": np.nan, "mean_b": np.nan, "mean_between": np.nan, "segregation": np.nan}

    # Within-network correlations (excluding diagonal)
    def get_within(indices):
        sub = matrix[np.ix_(indices, indices)]
        mask = ~np.eye(sub.shape[0], dtype=bool)
        return np.mean(sub[mask])

    within_a = get_within(idx_a)
    within_b = get_within(idx_b)
    
    # Between-network correlations
    between = np.mean(matrix[np.ix_(idx_a, idx_b)])
    
    # System Segregation (relative to each network or averaged)
    # Usually calculated using the within-network mean of the specific system
    seg_a = (within_a - between) / within_a if within_a != 0 else np.nan
    seg_b = (within_b - between) / within_b if within_b != 0 else np.nan
    
    return {
        f"within_{net_a}": within_a,
        f"within_{net_b}": within_b,
        f"between_{net_a}_{net_b}": between,
        "system_segregation_index": (seg_a + seg_b) / 2 # Average segregation
    }
