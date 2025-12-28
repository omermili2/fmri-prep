#!/usr/bin/env python3
"""
Pytest configuration and shared fixtures.
"""

import pytest
import sys
from pathlib import Path

# Add src to path for all tests
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def project_root():
    """Get the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def sample_dicom_structure(tmp_path):
    """
    Create a sample DICOM-like directory structure for testing.
    
    Structure:
        tmp_path/
        ├── 001/
        │   ├── MRI1/
        │   │   └── scans/
        │   │       └── series_001/
        │   └── MRI2/
        │       └── scans/
        └── 002/
            └── MRI1/
                └── scans/
    """
    # Subject 001
    sub_001 = tmp_path / "001"
    (sub_001 / "MRI1" / "scans" / "series_001").mkdir(parents=True)
    (sub_001 / "MRI2" / "scans" / "series_001").mkdir(parents=True)
    
    # Subject 002
    sub_002 = tmp_path / "002"
    (sub_002 / "MRI1" / "scans" / "series_001").mkdir(parents=True)
    
    return tmp_path


@pytest.fixture
def sample_bids_structure(tmp_path):
    """
    Create a sample BIDS directory structure for testing.
    """
    import json
    
    # Create dataset_description.json
    dataset_desc = {
        "Name": "Test Dataset",
        "BIDSVersion": "1.8.0",
        "DatasetType": "raw"
    }
    (tmp_path / "dataset_description.json").write_text(json.dumps(dataset_desc))
    
    # Subject 001
    anat_dir = tmp_path / "sub-001" / "ses-01" / "anat"
    anat_dir.mkdir(parents=True)
    (anat_dir / "sub-001_ses-01_T1w.nii.gz").write_bytes(b"fake nifti")
    (anat_dir / "sub-001_ses-01_T1w.json").write_text('{"test": true}')
    
    func_dir = tmp_path / "sub-001" / "ses-01" / "func"
    func_dir.mkdir(parents=True)
    (func_dir / "sub-001_ses-01_task-rest_bold.nii.gz").write_bytes(b"fake nifti")
    (func_dir / "sub-001_ses-01_task-rest_bold.json").write_text('{"TaskName": "rest"}')
    
    # Subject 002
    anat_dir_2 = tmp_path / "sub-002" / "ses-01" / "anat"
    anat_dir_2.mkdir(parents=True)
    (anat_dir_2 / "sub-002_ses-01_T1w.nii.gz").write_bytes(b"fake nifti")
    
    return tmp_path
