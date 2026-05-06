"""Tests for src.bids.fieldmap_intendedfor."""

import json
from pathlib import Path

import pytest

from src.bids.fieldmap_intendedfor import populate_intended_for


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(tmp_path, sub="001", ses="01"):
    """Create a minimal BIDS subject/session tree and return session_dir."""
    session_dir = tmp_path / f"sub-{sub}" / f"ses-{ses}"
    (session_dir / "fmap").mkdir(parents=True)
    (session_dir / "func").mkdir(parents=True)
    return session_dir


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _touch_nii(json_path):
    """Create an empty .nii.gz alongside a .json sidecar."""
    nii = json_path.with_suffix(".nii.gz")
    nii.write_bytes(b"")
    return nii


def _add_fmap_epi(session_dir, sub, ses, direction, acq_time=None,
                  shim=None, extra=None):
    """Add a pepolar EPI fieldmap pair member."""
    name = f"sub-{sub}_ses-{ses}_dir-{direction}_epi"
    jpath = session_dir / "fmap" / f"{name}.json"
    meta = {"PhaseEncodingDirection": "j-" if direction == "AP" else "j"}
    if acq_time:
        meta["AcquisitionTime"] = acq_time
    if shim:
        meta["ShimSetting"] = shim
    if extra:
        meta.update(extra)
    _write_json(jpath, meta)
    _touch_nii(jpath)
    return jpath


def _add_bold(session_dir, sub, ses, task, acq_time=None,
              run=None, shim=None):
    """Add a BOLD functional run."""
    run_ent = f"_run-{run:02d}" if run else ""
    name = f"sub-{sub}_ses-{ses}_task-{task}{run_ent}_bold"
    jpath = session_dir / "func" / f"{name}.json"
    meta = {}
    if acq_time:
        meta["AcquisitionTime"] = acq_time
    if shim:
        meta["ShimSetting"] = shim
    _write_json(jpath, meta)
    _touch_nii(jpath)
    return jpath


def _add_phasediff(session_dir, sub, ses, acq_time=None):
    """Add a GRE phasediff fieldmap."""
    name = f"sub-{sub}_ses-{ses}_phasediff"
    jpath = session_dir / "fmap" / f"{name}.json"
    meta = {}
    if acq_time:
        meta["AcquisitionTime"] = acq_time
    _write_json(jpath, meta)
    _touch_nii(jpath)
    return jpath


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSinglePairAllRuns:
    """Single AP+PA pair → all BOLD runs assigned to both."""

    def test_single_pair_assigns_all_runs(self, tmp_path):
        sd = _make_session(tmp_path)
        _add_fmap_epi(sd, "001", "01", "AP", acq_time="10:00:00.000000")
        _add_fmap_epi(sd, "001", "01", "PA", acq_time="10:04:00.000000")
        _add_bold(sd, "001", "01", "rest", acq_time="10:10:00.000000")
        _add_bold(sd, "001", "01", "memory", acq_time="10:30:00.000000")
        _add_bold(sd, "001", "01", "motor", acq_time="10:50:00.000000")

        updated = populate_intended_for(sd)

        assert updated == 2  # AP + PA jsons
        ap_meta = _read_json(sd / "fmap" / "sub-001_ses-01_dir-AP_epi.json")
        pa_meta = _read_json(sd / "fmap" / "sub-001_ses-01_dir-PA_epi.json")
        assert len(ap_meta["IntendedFor"]) == 3
        assert len(pa_meta["IntendedFor"]) == 3


class TestMultiplePairsProximity:
    """Multiple fmap pairs → each BOLD assigned to nearest pair."""

    def test_multiple_pairs(self, tmp_path):
        sd = _make_session(tmp_path)
        # First pair at 10:00
        ap1 = sd / "fmap" / "sub-001_ses-01_acq-first_dir-AP_epi.json"
        pa1 = sd / "fmap" / "sub-001_ses-01_acq-first_dir-PA_epi.json"
        _write_json(ap1, {"PhaseEncodingDirection": "j-",
                          "AcquisitionTime": "10:00:00.000000"})
        _touch_nii(ap1)
        _write_json(pa1, {"PhaseEncodingDirection": "j",
                          "AcquisitionTime": "10:02:00.000000"})
        _touch_nii(pa1)

        # Second pair at 11:00
        ap2 = sd / "fmap" / "sub-001_ses-01_acq-second_dir-AP_epi.json"
        pa2 = sd / "fmap" / "sub-001_ses-01_acq-second_dir-PA_epi.json"
        _write_json(ap2, {"PhaseEncodingDirection": "j-",
                          "AcquisitionTime": "11:00:00.000000"})
        _touch_nii(ap2)
        _write_json(pa2, {"PhaseEncodingDirection": "j",
                          "AcquisitionTime": "11:02:00.000000"})
        _touch_nii(pa2)

        # BOLD close to first pair
        _add_bold(sd, "001", "01", "rest", acq_time="10:10:00.000000")
        # BOLD close to second pair
        _add_bold(sd, "001", "01", "memory", acq_time="11:10:00.000000")

        updated = populate_intended_for(sd)
        assert updated == 4

        first_ap = _read_json(ap1)
        first_pa = _read_json(pa1)
        second_ap = _read_json(ap2)
        second_pa = _read_json(pa2)

        # First pair should have rest only
        assert any("task-rest" in p for p in first_ap["IntendedFor"])
        assert not any("task-memory" in p for p in first_ap["IntendedFor"])
        assert first_ap["IntendedFor"] == first_pa["IntendedFor"]

        # Second pair should have memory only
        assert any("task-memory" in p for p in second_ap["IntendedFor"])
        assert not any("task-rest" in p for p in second_ap["IntendedFor"])
        assert second_ap["IntendedFor"] == second_pa["IntendedFor"]


class TestNoFieldmaps:
    """No fmap directory → returns 0."""

    def test_no_fmaps(self, tmp_path):
        sd = _make_session(tmp_path)
        # Remove the fmap dir
        (sd / "fmap").rmdir()
        _add_bold(sd, "001", "01", "rest")
        assert populate_intended_for(sd) == 0


class TestNoFuncRuns:
    """No func runs → returns 0."""

    def test_no_func(self, tmp_path):
        sd = _make_session(tmp_path)
        (sd / "func").rmdir()
        _add_fmap_epi(sd, "001", "01", "AP")
        _add_fmap_epi(sd, "001", "01", "PA")
        assert populate_intended_for(sd) == 0


class TestExistingIntendedForPreserved:
    """Pre-existing IntendedFor is not overwritten."""

    def test_existing_preserved(self, tmp_path):
        sd = _make_session(tmp_path)
        ap = _add_fmap_epi(sd, "001", "01", "AP")
        _add_fmap_epi(sd, "001", "01", "PA")
        _add_bold(sd, "001", "01", "rest")

        # Pre-populate AP with an existing IntendedFor
        meta = _read_json(ap)
        meta["IntendedFor"] = ["ses-01/func/sub-001_ses-01_task-custom_bold.nii.gz"]
        _write_json(ap, meta)

        updated = populate_intended_for(sd)
        # Only PA should be updated
        assert updated == 1

        ap_meta = _read_json(ap)
        assert ap_meta["IntendedFor"] == [
            "ses-01/func/sub-001_ses-01_task-custom_bold.nii.gz"
        ]


class TestPhasediffFieldmap:
    """Single phasediff fieldmap gets all runs."""

    def test_phasediff(self, tmp_path):
        sd = _make_session(tmp_path)
        pd_json = _add_phasediff(sd, "001", "01", acq_time="10:00:00.000000")
        _add_bold(sd, "001", "01", "rest", acq_time="10:10:00.000000")
        _add_bold(sd, "001", "01", "memory", acq_time="10:30:00.000000")

        updated = populate_intended_for(sd)
        assert updated == 1

        meta = _read_json(pd_json)
        assert len(meta["IntendedFor"]) == 2


class TestNoAcquisitionTimeFallback:
    """No AcquisitionTime on any scan → all runs assigned to all fmaps."""

    def test_no_acq_time(self, tmp_path):
        sd = _make_session(tmp_path)
        _add_fmap_epi(sd, "001", "01", "AP")  # no acq_time
        _add_fmap_epi(sd, "001", "01", "PA")  # no acq_time
        _add_bold(sd, "001", "01", "rest")
        _add_bold(sd, "001", "01", "memory")

        updated = populate_intended_for(sd)
        assert updated == 2

        ap_meta = _read_json(sd / "fmap" / "sub-001_ses-01_dir-AP_epi.json")
        assert len(ap_meta["IntendedFor"]) == 2


class TestUnpairedEPI:
    """Single AP with no matching PA still gets IntendedFor."""

    def test_unpaired(self, tmp_path):
        sd = _make_session(tmp_path)
        _add_fmap_epi(sd, "001", "01", "AP", acq_time="10:00:00.000000")
        # No PA at all
        _add_bold(sd, "001", "01", "rest", acq_time="10:10:00.000000")

        updated = populate_intended_for(sd)
        assert updated == 1

        meta = _read_json(sd / "fmap" / "sub-001_ses-01_dir-AP_epi.json")
        assert len(meta["IntendedFor"]) == 1


class TestPathFormat:
    """IntendedFor uses forward slashes and is relative to subject dir."""

    def test_forward_slashes(self, tmp_path):
        sd = _make_session(tmp_path)
        _add_fmap_epi(sd, "001", "01", "AP")
        _add_fmap_epi(sd, "001", "01", "PA")
        _add_bold(sd, "001", "01", "rest")

        populate_intended_for(sd)

        meta = _read_json(sd / "fmap" / "sub-001_ses-01_dir-AP_epi.json")
        for path in meta["IntendedFor"]:
            assert "\\" not in path, "Paths must use forward slashes"
            assert path.startswith("ses-01/func/"), (
                f"Path should be relative to subject dir: {path}"
            )
            assert path.endswith(".nii.gz")

    def test_exact_path(self, tmp_path):
        sd = _make_session(tmp_path)
        _add_fmap_epi(sd, "001", "01", "AP")
        _add_bold(sd, "001", "01", "rest")

        populate_intended_for(sd)

        meta = _read_json(sd / "fmap" / "sub-001_ses-01_dir-AP_epi.json")
        assert meta["IntendedFor"] == [
            "ses-01/func/sub-001_ses-01_task-rest_bold.nii.gz"
        ]


class TestEmptySessionDir:
    """Non-existent session directory → returns 0."""

    def test_nonexistent(self, tmp_path):
        assert populate_intended_for(tmp_path / "nonexistent") == 0
