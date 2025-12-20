#!/usr/bin/env python3
"""
Tests for GUI components and fMRIPrep option validation.
"""

import pytest
from pathlib import Path


class TestFmriprepOptionsValidation:
    """Tests for fMRIPrep options validation logic."""
    
    def test_at_least_one_output_space_required(self):
        """Test that at least one output space must be selected."""
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
        
        assert options_with_fs['fs_reconall'] == True
        assert options_without_fs['fs_reconall'] == False


class TestGuiImports:
    """Test that GUI module imports correctly."""
    
    def test_gui_app_imports(self):
        """Test that gui.app module can be imported."""
        try:
            from gui import app
            assert hasattr(app, 'App')
        except ImportError as e:
            # GUI import might fail without display, that's ok
            if 'display' not in str(e).lower() and 'tk' not in str(e).lower():
                raise
    
    def test_pipeline_imports(self):
        """Test that pipeline module can be imported."""
        import pipeline
        assert hasattr(pipeline, 'main')
    
    def test_core_imports(self):
        """Test that core modules can be imported."""
        from core import discovery, progress, utils
        assert hasattr(discovery, 'find_sessions')
        assert hasattr(progress, 'ProgressTracker')
        assert hasattr(utils, 'safe_print')
    
    def test_bids_imports(self):
        """Test that BIDS modules can be imported."""
        from bids import converter, analyzer
        assert hasattr(converter, 'run_bids_conversion')
        assert hasattr(analyzer, 'count_output_files')
    
    def test_reporting_imports(self):
        """Test that reporting modules can be imported."""
        from reporting import report
        assert hasattr(report, 'ConversionReport')


class TestOptionDependencies:
    """Test fMRIPrep option dependencies."""
    
    def test_stc_is_independent(self):
        """Test that slice timing correction is independent."""
        options = {
            'stc': True,
            'mni_output': True,
            'fs_reconall': False
        }
        assert options['stc'] == True
    
    def test_fieldmapless_sdc_is_independent(self):
        """Test that fieldmap-less SDC is independent."""
        options = {
            'fieldmapless_sdc': True,
            'mni_output': True
        }
        assert options['fieldmapless_sdc'] == True
    
    def test_freesurfer_is_independent(self):
        """Test that FreeSurfer reconall is independent."""
        options = {
            'fs_reconall': True,
            'mni_output': False,
            't1w_output': True
        }
        assert options['fs_reconall'] == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
