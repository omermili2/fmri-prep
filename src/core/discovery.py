"""
Subject and session discovery for DICOM data.

This module handles automatic detection of subjects and sessions
from various folder naming conventions commonly used in MRI labs.
"""

import re
from pathlib import Path


def find_subject_folders(input_root):
    """
    Scan input directory for subject folders.
    
    Args:
        input_root: Path to the root directory containing subject folders
        
    Returns:
        List of Path objects representing subject directories
        
    Example:
        >>> subjects = find_subject_folders("/data/raw")
        >>> # Returns [Path("/data/raw/001"), Path("/data/raw/002"), ...]
    """
    root = Path(input_root)
    if not root.exists():
        return []
    return [d for d in root.iterdir() if d.is_dir() and not d.name.startswith('.')]


def find_sessions(subject_path):
    """
    Find session folders within a subject directory.
    
    Supports multiple naming conventions commonly used in MRI labs:
    
    - MRI1, MRI2, MRI3 ...         → ses-01, ses-02, ses-03
    - ses-01, ses-02 ...           → ses-01, ses-02 (already BIDS-like)
    - session1, session_1          → ses-01, ses-01
    - timepoint1, tp1, tp_2        → ses-01, ses-01, ses-02
    - baseline, pre, screening     → ses-01
    - followup, post               → ses-02
    - scans                        → ses-01 (single session)
    
    Args:
        subject_path: Path to the subject directory
        
    Returns:
        List of tuples: [(session_id, session_path), ...]
        Session IDs are zero-padded to 2 digits (e.g., "01", "02")
        
    Example:
        >>> sessions = find_sessions(Path("/data/raw/001"))
        >>> # Returns [("01", Path("/data/raw/001/MRI1")), ("02", Path("/data/raw/001/MRI2"))]
    """
    sessions = []
    
    for d in sorted(Path(subject_path).iterdir()):
        if not d.is_dir() or d.name.startswith('.'):
            continue
        
        name = d.name.lower()
        
        # Already BIDS format (ses-01, ses-02)
        if re.match(r'^ses-\d+$', d.name):
            ses_id = d.name.replace('ses-', '')
            sessions.append((ses_id, d))
        
        # MRI1, MRI2, etc.
        elif match := re.match(r'^mri(\d+)$', name):
            ses_id = match.group(1).zfill(2)
            sessions.append((ses_id, d))
        
        # session1, session_1, session-1
        elif match := re.match(r'^session[_-]?(\d+)$', name):
            ses_id = match.group(1).zfill(2)
            sessions.append((ses_id, d))
        
        # timepoint1, tp1
        elif match := re.match(r'^(?:timepoint|tp)[_-]?(\d+)$', name):
            ses_id = match.group(1).zfill(2)
            sessions.append((ses_id, d))
        
        # baseline, followup (assign sequential numbers)
        elif name in ['baseline', 'pre', 'screening']:
            sessions.append(('01', d))
        elif name in ['followup', 'post', 'followup1']:
            sessions.append(('02', d))
        elif name in ['followup2', 'post2']:
            sessions.append(('03', d))
        
        # scans folder directly under subject (single session)
        elif name == 'scans':
            sessions.append(('01', d))
        
        # Fallback: check if this dir contains DICOM-like subdirectories
        else:
            # Check if there are subdirs that might contain DICOMs
            subdirs = [x for x in d.iterdir() if x.is_dir()]
            if subdirs or any(f.suffix.lower() in ['.dcm', '.ima', '.gz'] for f in d.rglob('*') if f.is_file()):
                # Assume it's a session, assign sequential ID
                ses_num = str(len(sessions) + 1).zfill(2)
                sessions.append((ses_num, d))
    
    # Fallback: if no sessions found, treat subject folder as single session
    return sessions if sessions else [('01', Path(subject_path))]


def sanitize_id(raw_id):
    """
    Sanitize ID to be BIDS-compliant (alphanumeric only).
    
    Removes common prefixes like "sub-", "subject-" and strips
    any non-alphanumeric characters.
    
    Args:
        raw_id: The raw subject/session ID from folder name
        
    Returns:
        Cleaned alphanumeric ID, or None if nothing remains
        
    Example:
        >>> sanitize_id("sub-001")
        "001"
        >>> sanitize_id("subject_123")
        "123"
        >>> sanitize_id("Patient-A")
        "PatientA"
    """
    clean = raw_id
    
    # Remove common prefixes (longer prefixes first to avoid partial matches)
    for prefix in ['subject-', 'subject', 'sub-', 'sub']:
        if clean.lower().startswith(prefix):
            clean = clean[len(prefix):]
            break
    
    # Keep only alphanumeric
    clean = re.sub(r'[^a-zA-Z0-9]', '', clean)
    return clean if clean else None


def has_dicom_files(path):
    """
    Check if a path contains DICOM files (directly or nested).
    
    Looks for common DICOM file extensions: .dcm, .DCM, .ima, .IMA, .dcm.gz
    
    Args:
        path: Directory path to search
        
    Returns:
        True if DICOM files are found, False otherwise
    """
    dcm_patterns = ['*.dcm', '*.DCM', '*.ima', '*.IMA', '*.dcm.gz']
    for pattern in dcm_patterns:
        if list(Path(path).rglob(pattern)):
            return True
    return False

