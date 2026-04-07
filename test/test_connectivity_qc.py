#!/usr/bin/env python3
"""
Tests for Connectivity QC implementation.

Verifies that all required modules are importable and functional.
"""

import pytest


class TestConnectivityImports:
    """Test that connectivity QC dependencies can be imported."""

    def test_nilearn_import(self):
        """Test that nilearn is installed."""
        import nilearn
        assert nilearn.__version__

    def test_nibabel_import(self):
        """Test that nibabel is installed."""
        import nibabel as nib
        assert nib.__version__

    def test_sklearn_import(self):
        """Test that scikit-learn is installed."""
        import sklearn
        assert sklearn.__version__

    def test_networkx_import(self):
        """Test that networkx is installed."""
        import networkx as nx
        assert nx.__version__


class TestConnectivityQcModules:
    """Test that QC modules are importable."""

    def test_connectivity_thresholds_import(self):
        """Test that connectivity_thresholds module is importable."""
        from qc import connectivity_thresholds
        assert connectivity_thresholds

    def test_volume_censoring_import(self):
        """Test that volume_censoring module is importable."""
        from qc import volume_censoring
        assert volume_censoring

    def test_connectivity_qc_import(self):
        """Test that connectivity_qc module is importable."""
        from qc import connectivity_qc
        assert connectivity_qc

    def test_connectivity_qc_available_flag(self):
        """Test that CONNECTIVITY_QC_AVAILABLE is True when deps are installed."""
        from qc import CONNECTIVITY_QC_AVAILABLE
        assert CONNECTIVITY_QC_AVAILABLE


class TestConnectivityThresholds:
    """Test threshold values match literature-derived constants."""

    def test_mean_fd_warn(self):
        from qc import connectivity_thresholds as thresh
        assert thresh.CONNECTIVITY_MEAN_FD_WARN == 0.25

    def test_mean_fd_fail(self):
        from qc import connectivity_thresholds as thresh
        assert thresh.CONNECTIVITY_MEAN_FD_FAIL == 0.50

    def test_max_censored_pct(self):
        from qc import connectivity_thresholds as thresh
        assert thresh.MAX_CENSORED_PCT_FAIL == 80.0

    def test_min_usable_minutes(self):
        from qc import connectivity_thresholds as thresh
        assert thresh.MIN_USABLE_MINUTES_FAIL == 1.0


class TestNilearnAtlas:
    """Test Nilearn atlas fetching."""

    def test_schaefer_atlas_fetch(self):
        """Test that Nilearn can fetch the Schaefer atlas."""
        from nilearn import datasets
        atlas = datasets.fetch_atlas_schaefer_2018(n_rois=100, resolution_mm=2, verbose=0)
        assert len(atlas['labels']) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
