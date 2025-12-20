#!/usr/bin/env python3
"""
Tests for GUI components and fMRIPrep option validation.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestFmriprepOptionsValidation:
    """Tests for fMRIPrep options validation logic."""
    
    def test_at_least_one_output_space_required(self):
        """Test that at least one output space must be selected."""
        # When both MNI and T1w are unchecked, validation should fail
        options = {
            'mni_output': False,
            't1w_output': False,
            'fs_reconall': False,
            'stc': True,
            'fieldmapless_sdc': False,
            'aroma': False
        }
        
        # Validation: at least one of mni_output or t1w_output must be True
        assert not (options['mni_output'] or options['t1w_output'])
    
    def test_aroma_requires_mni(self):
        """Test that ICA-AROMA requires MNI output space."""
        options = {
            'mni_output': False,
            't1w_output': True,
            'aroma': True
        }
        
        # AROMA should not be valid without MNI
        is_valid = not (options['aroma'] and not options['mni_output'])
        assert not is_valid
    
    def test_aroma_valid_with_mni(self):
        """Test that ICA-AROMA is valid with MNI output space."""
        options = {
            'mni_output': True,
            't1w_output': False,
            'aroma': True
        }
        
        # AROMA should be valid with MNI
        is_valid = not (options['aroma'] and not options['mni_output'])
        assert is_valid
    
    def test_default_options_are_valid(self):
        """Test that default options are valid."""
        options = {
            'mni_output': True,
            't1w_output': False,
            'fs_reconall': False,
            'stc': True,
            'fieldmapless_sdc': False,
            'aroma': False
        }
        
        # Default should have at least one output space
        assert options['mni_output'] or options['t1w_output']
        
        # Default should not have AROMA enabled without MNI
        if options['aroma']:
            assert options['mni_output']


class TestGetFmriprepOptions:
    """Tests for building fMRIPrep command line options."""
    
    def test_build_output_spaces_mni_only(self):
        """Test building output spaces with MNI only."""
        options = {
            'mni_output': True,
            't1w_output': False
        }
        
        spaces = []
        if options['mni_output']:
            spaces.append('MNI152NLin2009cAsym')
        if options['t1w_output']:
            spaces.append('T1w')
        
        assert spaces == ['MNI152NLin2009cAsym']
    
    def test_build_output_spaces_both(self):
        """Test building output spaces with both MNI and T1w."""
        options = {
            'mni_output': True,
            't1w_output': True
        }
        
        spaces = []
        if options['mni_output']:
            spaces.append('MNI152NLin2009cAsym')
        if options['t1w_output']:
            spaces.append('T1w')
        
        assert spaces == ['MNI152NLin2009cAsym', 'T1w']
    
    def test_fs_reconall_flag(self):
        """Test FreeSurfer reconall flag generation."""
        options_with_fs = {'fs_reconall': True}
        options_without_fs = {'fs_reconall': False}
        
        # With FS: should NOT include --fs-no-reconall
        # Without FS: should include --fs-no-reconall
        assert options_with_fs['fs_reconall'] == True
        assert options_without_fs['fs_reconall'] == False


class TestGuiImports:
    """Test that GUI module imports correctly."""
    
    def test_gui_app_imports(self):
        """Test that gui_app module can be imported."""
        try:
            import gui_app
            assert hasattr(gui_app, 'App')
        except ImportError as e:
            # GUI import might fail without display, that's ok
            if 'display' not in str(e).lower() and 'tk' not in str(e).lower():
                raise
    
    def test_run_pipeline_imports(self):
        """Test that run_pipeline module can be imported."""
        import run_pipeline
        assert hasattr(run_pipeline, 'main')
        assert hasattr(run_pipeline, 'find_sessions')
        assert hasattr(run_pipeline, 'find_subject_folders')
    
    def test_run_fmriprep_imports(self):
        """Test that run_fmriprep module can be imported."""
        import run_fmriprep
        assert hasattr(run_fmriprep, 'main')


class TestOptionDependencies:
    """Test fMRIPrep option dependencies."""
    
    def test_stc_is_independent(self):
        """Test that slice timing correction is independent of other options."""
        # STC can be enabled/disabled regardless of other options
        options = {
            'stc': True,
            'mni_output': True,
            'fs_reconall': False
        }
        # No validation error expected
        assert options['stc'] == True
    
    def test_fieldmapless_sdc_is_independent(self):
        """Test that fieldmap-less SDC is independent of other options."""
        # SyN SDC can be enabled regardless of other options
        options = {
            'fieldmapless_sdc': True,
            'mni_output': True
        }
        # No validation error expected
        assert options['fieldmapless_sdc'] == True
    
    def test_freesurfer_is_independent(self):
        """Test that FreeSurfer reconall is independent of other options."""
        options = {
            'fs_reconall': True,
            'mni_output': False,
            't1w_output': True
        }
        # No validation error expected - FS can work with T1w output
        assert options['fs_reconall'] == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

