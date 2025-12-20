"""
BIDS output analysis and statistics.
"""

from pathlib import Path


def count_output_files(bids_dir):
    """
    Count NIfTI files by scan type in the output directory.
    
    Args:
        bids_dir: Path to the BIDS output directory
        
    Returns:
        Dictionary with counts:
        {
            'total_nifti': int,
            'anat': int,      # Anatomical scans (T1w, T2w, etc.)
            'func': int,      # Functional scans (BOLD)
            'dwi': int,       # Diffusion-weighted imaging
            'fmap': int,      # Field maps
            'other': int,     # Unclassified
            'subject_count': int,
            'session_count': int
        }
    """
    stats = {
        'total_nifti': 0,
        'anat': 0,
        'func': 0,
        'dwi': 0,
        'fmap': 0,
        'other': 0,
        'subjects': set(),
        'sessions': set()
    }
    
    bids_path = Path(bids_dir)
    if not bids_path.exists():
        return stats
    
    for nii in bids_path.rglob('*.nii.gz'):
        stats['total_nifti'] += 1
        
        # Determine scan type from path
        path_parts = nii.parts
        if 'anat' in path_parts:
            stats['anat'] += 1
        elif 'func' in path_parts:
            stats['func'] += 1
        elif 'dwi' in path_parts:
            stats['dwi'] += 1
        elif 'fmap' in path_parts:
            stats['fmap'] += 1
        else:
            stats['other'] += 1
        
        # Track subjects and sessions
        for part in path_parts:
            if part.startswith('sub-'):
                stats['subjects'].add(part)
            elif part.startswith('ses-'):
                stats['sessions'].add(part)
    
    # Convert sets to counts
    stats['subject_count'] = len(stats['subjects'])
    stats['session_count'] = len(stats['sessions'])
    del stats['subjects']
    del stats['sessions']
    
    return stats

