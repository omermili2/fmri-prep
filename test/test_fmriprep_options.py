#!/usr/bin/env python3
"""
Tests for fMRIPrep options parsing and validation.
"""

import pytest
from pathlib import Path
from unittest.mock import patch

# Import from new modular structure
from fmriprep.runner import to_docker_path, find_freesurfer_license, check_docker


class TestFmriprepPathConversion:
    """Tests for Docker path conversion."""
    
    def test_unix_path_unchanged(self):
        """Test that Unix paths are returned unchanged."""
        with patch('sys.platform', 'darwin'):
            result = to_docker_path("/Users/test/data")
            assert result == "/Users/test/data"
    
    def test_windows_path_conversion(self):
        """Test that Windows paths are converted correctly."""
        with patch('sys.platform', 'win32'):
            # Simulate Windows path
            result = to_docker_path("C:\\Users\\test\\data")
            # Note: This test assumes the function handles Windows paths
            assert "/" in result or "\\" not in result


class TestFmriprepLicenseDetection:
    """Tests for FreeSurfer license file detection."""
    
    def test_function_exists(self):
        """Test that license detection function exists."""
        assert callable(find_freesurfer_license)
    
    def test_returns_path_or_none(self):
        """Test that function returns Path or None."""
        result = find_freesurfer_license()
        assert result is None or isinstance(result, Path)


class TestDockerCheck:
    """Tests for Docker availability checking."""
    
    def test_check_docker_returns_tuple(self):
        """Test that check_docker returns a tuple."""
        result = check_docker()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert result[1] is None or isinstance(result[1], str)


class TestFmriprepOptionsBuilding:
    """Tests for building fMRIPrep options."""
    
    def test_module_has_main(self):
        """Test that module has main function."""
        from fmriprep import runner
        assert hasattr(runner, 'main')
        assert hasattr(runner, 'run_fmriprep')


class TestExtraArgsProcessing:
    """Tests for processing extra arguments from GUI."""
    
    def test_empty_extra_args(self):
        """Test with no extra arguments."""
        extra_args = ""
        result = [arg.strip() for arg in extra_args.split(",") if arg.strip()]
        assert result == []
    
    def test_single_extra_arg(self):
        """Test with single extra argument."""
        extra_args = "--use-aroma"
        result = [arg.strip() for arg in extra_args.split(",") if arg.strip()]
        assert result == ["--use-aroma"]
    
    def test_multiple_extra_args(self):
        """Test with multiple extra arguments."""
        extra_args = "--use-aroma,--output-spaces MNI152NLin2009cAsym,--fs-no-reconall"
        result = [arg.strip() for arg in extra_args.split(",") if arg.strip()]
        assert len(result) == 3
        assert "--use-aroma" in result
    
    def test_extra_args_with_spaces(self):
        """Test extra arguments with key-value pairs."""
        extra_args = "--output-spaces MNI152NLin2009cAsym T1w"
        result = [arg.strip() for arg in extra_args.split(",") if arg.strip()]
        assert result == ["--output-spaces MNI152NLin2009cAsym T1w"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
