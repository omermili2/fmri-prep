#!/usr/bin/env python3
"""
Tests for Connectivity QC implementation.

Verifies that all required modules are importable and functional,
and that the load_confounds_strategy-based approach is correctly wired.
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

    def test_volume_censoring_removed(self):
        """Test that volume_censoring module no longer exists."""
        with pytest.raises(ImportError):
            from qc import volume_censoring  # noqa: F401

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

    def test_old_constants_removed(self):
        """Confirm DM-FC, modularity, and CENSORING_FD constants no longer exist."""
        from qc import connectivity_thresholds as thresh
        assert not hasattr(thresh, "QC_FC_WARN")
        assert not hasattr(thresh, "QC_FC_FAIL")
        assert not hasattr(thresh, "DM_FC_WARN")
        assert not hasattr(thresh, "DM_FC_FAIL")
        assert not hasattr(thresh, "DM_FC_FD_SPLIT")
        assert not hasattr(thresh, "DM_FC_MIN_FRAMES")
        assert not hasattr(thresh, "MIN_MODULARITY_WARN")
        assert not hasattr(thresh, "MIN_MODULARITY_FAIL")
        assert not hasattr(thresh, "CENSORING_FD_THRESHOLD")
        assert not hasattr(thresh, "DEFAULT_TR")

    def test_loss_dof_warn(self):
        """Test new LOSS_DOF_WARN constant."""
        from qc import connectivity_thresholds as thresh
        assert thresh.LOSS_DOF_WARN == 0.60


class TestDataclassFields:
    """Test that ConnectivityQCResult has the correct fields."""

    def test_new_fields_present(self):
        """Confirm dataclass has the new per-run metric fields."""
        from qc.connectivity_qc import ConnectivityQCResult
        r = ConnectivityQCResult(
            sub_id="01", ses_id="01", run_label="task-rest",
        )
        assert hasattr(r, "total_volumes")
        assert hasattr(r, "censored_volumes")
        assert hasattr(r, "pct_censored")
        assert hasattr(r, "usable_minutes")
        assert hasattr(r, "tr_sec")
        assert hasattr(r, "mean_fd")
        assert hasattr(r, "n_regressors")
        assert hasattr(r, "loss_of_dof")
        assert hasattr(r, "loss_of_dof_pct")
        assert hasattr(r, "rescan_warning")

    def test_old_fields_removed(self):
        """Confirm dataclass no longer has DM-FC or modularity fields."""
        from qc.connectivity_qc import ConnectivityQCResult
        r = ConnectivityQCResult(
            sub_id="01", ses_id="01", run_label="task-rest",
        )
        assert not hasattr(r, "dm_fc_value")
        assert not hasattr(r, "dm_fc_severity")
        assert not hasattr(r, "dm_fc_note")
        assert not hasattr(r, "modularity_q")
        assert not hasattr(r, "modularity_severity")
        assert not hasattr(r, "qc_fc_value")
        assert not hasattr(r, "qc_fc_severity")

    def test_has_heatmap_fields(self):
        """Confirm dataclass has heatmap_base64 and network_summary_base64."""
        from qc.connectivity_qc import ConnectivityQCResult
        r = ConnectivityQCResult(
            sub_id="01", ses_id="01", run_label="task-rest",
        )
        assert hasattr(r, "heatmap_base64")
        assert hasattr(r, "network_summary_base64")
        assert r.heatmap_base64 is None
        assert r.network_summary_base64 is None


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
    """Test that analyze_all_subjects has the new signature."""

    def test_no_old_parameters(self):
        """Confirm old parameters are gone from the function signature."""
        import inspect
        from qc.connectivity_qc import analyze_all_subjects
        sig = inspect.signature(analyze_all_subjects)
        assert "compute_qc_fc" not in sig.parameters
        assert "compute_dm_fc" not in sig.parameters
        assert "compute_modularity" not in sig.parameters


class TestQualityAssessment:
    """Test the _assess_quality threshold logic."""

    def test_ok_run(self):
        from qc.connectivity_qc import _assess_quality
        severity, ready, rescan, msg, action = _assess_quality(
            mean_fd=0.10, pct_censored=5.0, usable_minutes=4.5, loss_of_dof_pct=15.0
        )
        assert severity == "OK"
        assert ready is True
        assert rescan is False

    def test_warning_high_fd(self):
        from qc.connectivity_qc import _assess_quality
        severity, ready, rescan, msg, action = _assess_quality(
            mean_fd=0.35, pct_censored=10.0, usable_minutes=4.0, loss_of_dof_pct=20.0
        )
        assert severity == "WARNING"
        assert ready is True
        assert "elevated FD" in msg

    def test_warning_high_dof_loss(self):
        from qc.connectivity_qc import _assess_quality
        severity, ready, rescan, msg, action = _assess_quality(
            mean_fd=0.10, pct_censored=10.0, usable_minutes=4.0, loss_of_dof_pct=65.0
        )
        assert severity == "WARNING"
        assert "DoF loss" in msg

    def test_error_high_fd(self):
        from qc.connectivity_qc import _assess_quality
        severity, ready, rescan, msg, action = _assess_quality(
            mean_fd=0.60, pct_censored=10.0, usable_minutes=4.0, loss_of_dof_pct=20.0
        )
        assert severity == "ERROR"
        assert ready is False
        assert rescan is True

    def test_error_too_much_censored(self):
        from qc.connectivity_qc import _assess_quality
        severity, ready, rescan, msg, action = _assess_quality(
            mean_fd=0.20, pct_censored=85.0, usable_minutes=0.5, loss_of_dof_pct=90.0
        )
        assert severity == "ERROR"
        assert ready is False

    def test_error_too_short(self):
        from qc.connectivity_qc import _assess_quality
        severity, ready, rescan, msg, action = _assess_quality(
            mean_fd=0.15, pct_censored=30.0, usable_minutes=0.8, loss_of_dof_pct=40.0
        )
        assert severity == "ERROR"
        assert ready is False


class TestNilearnAtlas:
    """Test Nilearn atlas fetching."""

    def test_schaefer_atlas_fetch(self):
        """Test that Nilearn can fetch the Schaefer atlas."""
        from nilearn import datasets
        atlas = datasets.fetch_atlas_schaefer_2018(n_rois=100, resolution_mm=2, verbose=0)
        assert len(atlas['labels']) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
