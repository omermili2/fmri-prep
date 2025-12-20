#!/usr/bin/env python3
"""
Tests for configuration file loading and validation.
"""

import pytest
import json
from pathlib import Path


class TestDcm2bidsConfig:
    """Tests for dcm2bids configuration file."""
    
    @pytest.fixture
    def config_path(self):
        """Get path to the actual config file."""
        return Path(__file__).parent.parent / "config" / "dcm2bids_config.json"
    
    def test_config_exists(self, config_path):
        """Test that config file exists."""
        assert config_path.exists(), f"Config file not found at {config_path}"
    
    def test_config_is_valid_json(self, config_path):
        """Test that config file is valid JSON."""
        with open(config_path) as f:
            config = json.load(f)
        assert isinstance(config, dict)
    
    def test_config_has_descriptions(self, config_path):
        """Test that config has descriptions array."""
        with open(config_path) as f:
            config = json.load(f)
        
        assert "descriptions" in config
        assert isinstance(config["descriptions"], list)
        assert len(config["descriptions"]) > 0
    
    def test_each_description_has_required_fields(self, config_path):
        """Test that each description has required fields."""
        with open(config_path) as f:
            config = json.load(f)
        
        required_fields = ["id", "datatype", "suffix", "criteria"]
        
        for desc in config["descriptions"]:
            for field in required_fields:
                assert field in desc, f"Missing field '{field}' in description: {desc.get('id', 'unknown')}"
    
    def test_datatypes_are_valid(self, config_path):
        """Test that datatypes are valid BIDS datatypes."""
        with open(config_path) as f:
            config = json.load(f)
        
        valid_datatypes = ["anat", "func", "dwi", "fmap", "perf", "eeg", "meg", "ieeg"]
        
        for desc in config["descriptions"]:
            assert desc["datatype"] in valid_datatypes, \
                f"Invalid datatype '{desc['datatype']}' in {desc['id']}"
    
    def test_has_t1w_description(self, config_path):
        """Test that config includes T1w anatomical scan."""
        with open(config_path) as f:
            config = json.load(f)
        
        t1w_found = any(
            desc.get("suffix") == "T1w" and desc.get("datatype") == "anat"
            for desc in config["descriptions"]
        )
        assert t1w_found, "Config should include T1w anatomical description"
    
    def test_dcm2niix_options_present(self, config_path):
        """Test that dcm2niix options are specified."""
        with open(config_path) as f:
            config = json.load(f)
        
        assert "dcm2niixOptions" in config
        assert isinstance(config["dcm2niixOptions"], str)
    
    def test_criteria_has_series_description(self, config_path):
        """Test that criteria includes SeriesDescription matching."""
        with open(config_path) as f:
            config = json.load(f)
        
        for desc in config["descriptions"]:
            criteria = desc.get("criteria", {})
            # At least one matching criterion should be present
            assert len(criteria) > 0, f"Empty criteria in {desc['id']}"


class TestConfigPatternMatching:
    """Tests for DICOM matching patterns."""
    
    def test_wildcard_pattern_matching(self):
        """Test that wildcard patterns work correctly."""
        import fnmatch
        
        # Test T1 pattern
        pattern = "*T1*"
        assert fnmatch.fnmatch("T1_MPRAGE_SAG", pattern)
        assert fnmatch.fnmatch("anat_ses-01_T1w", pattern)
        assert not fnmatch.fnmatch("T2_FLAIR", pattern)
    
    def test_task_pattern_matching(self):
        """Test task-specific patterns."""
        import fnmatch
        
        pattern = "*task-sound*"
        assert fnmatch.fnmatch("func_ses-01_task-sound_run-01", pattern)
        assert not fnmatch.fnmatch("func_ses-01_task-story_run-01", pattern)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

