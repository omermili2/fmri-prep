#!/usr/bin/env python3
"""
Tests for Connectivity QC implementation.

Verifies that all required modules are importable and functional,
and that the QC-FC removal / DM-FC split overhaul is correct.
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

    def test_matplotlib_import(self):
        """Test that matplotlib is installed."""
        import matplotlib
        assert matplotlib.__version__


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

    def test_qc_fc_constants_removed(self):
        """Confirm QC_FC_WARN and QC_FC_FAIL no longer exist."""
        from qc import connectivity_thresholds as thresh
        assert not hasattr(thresh, "QC_FC_WARN")
        assert not hasattr(thresh, "QC_FC_FAIL")

    def test_dm_fc_fd_split(self):
        """Test new DM_FC_FD_SPLIT constant."""
        from qc import connectivity_thresholds as thresh
        assert thresh.DM_FC_FD_SPLIT == 0.2

    def test_dm_fc_min_frames(self):
        """Test new DM_FC_MIN_FRAMES constant."""
        from qc import connectivity_thresholds as thresh
        assert thresh.DM_FC_MIN_FRAMES == 20

    def test_dm_fc_warn_updated(self):
        """Test DM-FC thresholds updated for split-based metric."""
        from qc import connectivity_thresholds as thresh
        assert thresh.DM_FC_WARN == 0.10

    def test_dm_fc_fail_updated(self):
        from qc import connectivity_thresholds as thresh
        assert thresh.DM_FC_FAIL == 0.20


class TestDataclassFields:
    """Test that ConnectivityQCResult has the correct fields."""

    def test_no_qc_fc_fields(self):
        """Confirm dataclass has no qc_fc_* fields."""
        from qc.connectivity_qc import ConnectivityQCResult
        r = ConnectivityQCResult(
            sub_id="01", ses_id="01", run_label="task-rest",
            mean_fd=0.1, n_volumes=200
        )
        assert not hasattr(r, "qc_fc_value")
        assert not hasattr(r, "qc_fc_severity")

    def test_has_heatmap_fields(self):
        """Confirm dataclass has heatmap_base64 and network_summary_base64."""
        from qc.connectivity_qc import ConnectivityQCResult
        r = ConnectivityQCResult(
            sub_id="01", ses_id="01", run_label="task-rest",
            mean_fd=0.1, n_volumes=200
        )
        assert hasattr(r, "heatmap_base64")
        assert hasattr(r, "network_summary_base64")
        assert r.heatmap_base64 is None
        assert r.network_summary_base64 is None

    def test_has_dm_fc_note(self):
        """Confirm dataclass has dm_fc_note field."""
        from qc.connectivity_qc import ConnectivityQCResult
        r = ConnectivityQCResult(
            sub_id="01", ses_id="01", run_label="task-rest",
            mean_fd=0.1, n_volumes=200
        )
        assert hasattr(r, "dm_fc_note")
        assert r.dm_fc_note == ""


class TestNetworkParsing:
    """Test _parse_network_assignments function."""

    def test_schaefer_labels(self):
        """Test parsing Schaefer-format labels."""
        from qc.connectivity_qc import _parse_network_assignments

        labels = [
            "7Networks_LH_Vis_1",
            "7Networks_LH_Vis_2",
            "7Networks_RH_SomMot_1",
            "7Networks_LH_DorsAttn_1",
            "Tian_S1_subcortex_1",
            "Tian_S1_subcortex_2",
        ]
        networks = _parse_network_assignments(labels)
        assert "Vis" in networks
        assert "SomMot" in networks
        assert "DorsAttn" in networks
        assert "Subcortical" in networks
        assert len(networks["Vis"]) == 2
        assert len(networks["Subcortical"]) == 2
        assert len(networks["SomMot"]) == 1

    def test_all_tian(self):
        """Test that all-Tian labels go to Subcortical."""
        from qc.connectivity_qc import _parse_network_assignments

        labels = ["Tian_a", "Tian_b", "Tian_c"]
        networks = _parse_network_assignments(labels)
        assert list(networks.keys()) == ["Subcortical"]
        assert len(networks["Subcortical"]) == 3


class TestAnalyzeAllSubjectsSignature:
    """Test that analyze_all_subjects no longer accepts compute_qc_fc."""

    def test_no_compute_qc_fc_parameter(self):
        """Confirm compute_qc_fc is not in the function signature."""
        import inspect
        from qc.connectivity_qc import analyze_all_subjects
        sig = inspect.signature(analyze_all_subjects)
        assert "compute_qc_fc" not in sig.parameters


class TestNilearnAtlas:
    """Test Nilearn atlas fetching."""

    def test_schaefer_atlas_fetch(self):
        """Test that Nilearn can fetch the Schaefer atlas."""
        from nilearn import datasets
        atlas = datasets.fetch_atlas_schaefer_2018(n_rois=100, resolution_mm=2, verbose=0)
        assert len(atlas['labels']) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
