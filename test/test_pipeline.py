#!/usr/bin/env python3
"""
Tests for the pipeline module (run_pipeline.py)
"""

import pytest
import tempfile
import os
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from run_pipeline import find_subject_folders, find_sessions


class TestFindSubjectFolders:
    """Tests for subject folder detection."""
    
    def test_find_subjects_in_directory(self, tmp_path):
        """Test that subject folders are correctly identified."""
        # Create test structure
        (tmp_path / "001").mkdir()
        (tmp_path / "002").mkdir()
        (tmp_path / "003").mkdir()
        (tmp_path / ".hidden").mkdir()  # Should be ignored
        
        subjects = find_subject_folders(tmp_path)
        
        assert len(subjects) == 3
        assert all(s.name in ["001", "002", "003"] for s in subjects)
    
    def test_empty_directory(self, tmp_path):
        """Test with empty directory."""
        subjects = find_subject_folders(tmp_path)
        assert len(subjects) == 0
    
    def test_nonexistent_directory(self):
        """Test with non-existent directory."""
        subjects = find_subject_folders("/nonexistent/path")
        assert len(subjects) == 0
    
    def test_ignores_files(self, tmp_path):
        """Test that files are ignored, only directories counted."""
        (tmp_path / "subject1").mkdir()
        (tmp_path / "README.txt").write_text("test")
        
        subjects = find_subject_folders(tmp_path)
        assert len(subjects) == 1


class TestFindSessions:
    """Tests for session detection within subject folders."""
    
    def test_mri_pattern(self, tmp_path):
        """Test MRI1, MRI2 naming pattern."""
        (tmp_path / "MRI1").mkdir()
        (tmp_path / "MRI2").mkdir()
        (tmp_path / "MRI3").mkdir()
        
        sessions = find_sessions(tmp_path)
        
        assert len(sessions) == 3
        session_ids = [s[0] for s in sessions]
        assert "01" in session_ids
        assert "02" in session_ids
        assert "03" in session_ids
    
    def test_bids_pattern(self, tmp_path):
        """Test ses-01, ses-02 naming pattern."""
        (tmp_path / "ses-01").mkdir()
        (tmp_path / "ses-02").mkdir()
        
        sessions = find_sessions(tmp_path)
        
        assert len(sessions) == 2
        session_ids = [s[0] for s in sessions]
        assert "01" in session_ids
        assert "02" in session_ids
    
    def test_session_pattern(self, tmp_path):
        """Test session1, session_2 naming pattern."""
        (tmp_path / "session1").mkdir()
        (tmp_path / "session_2").mkdir()
        
        sessions = find_sessions(tmp_path)
        
        assert len(sessions) == 2
    
    def test_timepoint_pattern(self, tmp_path):
        """Test timepoint1, tp2 naming pattern."""
        (tmp_path / "timepoint1").mkdir()
        (tmp_path / "tp2").mkdir()
        
        sessions = find_sessions(tmp_path)
        
        assert len(sessions) == 2
    
    def test_baseline_followup(self, tmp_path):
        """Test baseline/followup naming pattern."""
        (tmp_path / "baseline").mkdir()
        (tmp_path / "followup").mkdir()
        
        sessions = find_sessions(tmp_path)
        
        assert len(sessions) == 2
        session_ids = [s[0] for s in sessions]
        assert "01" in session_ids  # baseline -> 01
        assert "02" in session_ids  # followup -> 02
    
    def test_scans_folder(self, tmp_path):
        """Test 'scans' folder as single session."""
        (tmp_path / "scans").mkdir()
        
        sessions = find_sessions(tmp_path)
        
        assert len(sessions) == 1
        assert sessions[0][0] == "01"
    
    def test_ignores_hidden(self, tmp_path):
        """Test that hidden directories are ignored."""
        (tmp_path / "MRI1").mkdir()
        (tmp_path / ".hidden").mkdir()
        
        sessions = find_sessions(tmp_path)
        
        assert len(sessions) == 1
    
    def test_no_session_folders_fallback(self, tmp_path):
        """Test that subject folder with no session subfolders uses fallback."""
        # Create only files, no directories - mimics DICOMs directly in subject folder
        (tmp_path / "file1.dcm").write_text("test")
        (tmp_path / "file2.dcm").write_text("test")
        
        sessions = find_sessions(tmp_path)
        # Should return the subject path itself as session 01 (fallback behavior)
        assert len(sessions) == 1
        assert sessions[0][0] == "01"
        assert sessions[0][1] == tmp_path


class TestSessionIdNormalization:
    """Tests for session ID normalization to two digits."""
    
    def test_single_digit_padded(self, tmp_path):
        """Test that single digit numbers are padded."""
        (tmp_path / "MRI1").mkdir()
        
        sessions = find_sessions(tmp_path)
        
        assert sessions[0][0] == "01"  # Not "1"
    
    def test_double_digit_preserved(self, tmp_path):
        """Test that double digit numbers are preserved."""
        (tmp_path / "MRI12").mkdir()
        
        sessions = find_sessions(tmp_path)
        
        assert sessions[0][0] == "12"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

