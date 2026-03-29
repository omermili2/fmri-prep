#!/usr/bin/env python3
"""
Quick verification script for Connectivity QC implementation.

Tests that all required modules are importable and functional.
"""

import sys
from pathlib import Path

def test_imports():
    """Test that all required packages can be imported."""
    print("Testing imports...")

    try:
        import nilearn
        print(f"  ✓ nilearn {nilearn.__version__}")
    except ImportError as e:
        print(f"  ✗ nilearn not found: {e}")
        print("    Install with: pip install nilearn")
        return False

    try:
        import nibabel as nib
        print(f"  ✓ nibabel {nib.__version__}")
    except ImportError as e:
        print(f"  ✗ nibabel not found: {e}")
        print("    Install with: pip install nibabel")
        return False

    try:
        import sklearn
        print(f"  ✓ scikit-learn {sklearn.__version__}")
    except ImportError as e:
        print(f"  ✗ scikit-learn not found: {e}")
        print("    Install with: pip install scikit-learn")
        return False

    try:
        import networkx as nx
        print(f"  ✓ networkx {nx.__version__}")
    except ImportError as e:
        print(f"  ✗ networkx not found: {e}")
        print("    Install with: pip install networkx")
        return False

    return True


def test_qc_modules():
    """Test that QC modules are importable."""
    print("\nTesting QC modules...")

    try:
        from src.qc import connectivity_thresholds
        print("  ✓ connectivity_thresholds")
    except ImportError as e:
        print(f"  ✗ connectivity_thresholds: {e}")
        return False

    try:
        from src.qc import volume_censoring
        print("  ✓ volume_censoring")
    except ImportError as e:
        print(f"  ✗ volume_censoring: {e}")
        return False

    try:
        from src.qc import connectivity_qc
        print("  ✓ connectivity_qc")
    except ImportError as e:
        print(f"  ✗ connectivity_qc: {e}")
        return False

    try:
        from src.qc import CONNECTIVITY_QC_AVAILABLE
        if CONNECTIVITY_QC_AVAILABLE:
            print("  ✓ CONNECTIVITY_QC_AVAILABLE = True")
        else:
            print("  ⚠ CONNECTIVITY_QC_AVAILABLE = False (Nilearn not detected)")
            return False
    except ImportError as e:
        print(f"  ✗ CONNECTIVITY_QC_AVAILABLE: {e}")
        return False

    return True


def test_nilearn_atlas():
    """Test that Nilearn can fetch an atlas."""
    print("\nTesting Nilearn atlas download...")

    try:
        from nilearn import datasets
        print("  Fetching Schaefer atlas (100 parcels)...")
        atlas = datasets.fetch_atlas_schaefer_2018(n_rois=100, resolution_mm=2, verbose=0)
        print(f"  ✓ Atlas loaded: {len(atlas['labels'])} regions")
        return True
    except Exception as e:
        print(f"  ✗ Atlas fetch failed: {e}")
        return False


def test_thresholds():
    """Test threshold values."""
    print("\nTesting threshold definitions...")

    try:
        from src.qc import connectivity_thresholds as thresh

        assert thresh.CONNECTIVITY_MEAN_FD_WARN == 0.25, "FD warn threshold incorrect"
        assert thresh.CONNECTIVITY_MEAN_FD_FAIL == 0.50, "FD fail threshold incorrect"
        assert thresh.MAX_CENSORED_PCT_FAIL == 80.0, "Censoring threshold incorrect"
        assert thresh.MIN_USABLE_MINUTES_FAIL == 1.0, "Minimum duration incorrect"

        print(f"  ✓ Mean FD warn: {thresh.CONNECTIVITY_MEAN_FD_WARN}mm")
        print(f"  ✓ Mean FD fail: {thresh.CONNECTIVITY_MEAN_FD_FAIL}mm")
        print(f"  ✓ Max censored: {thresh.MAX_CENSORED_PCT_FAIL}%")
        print(f"  ✓ Min duration: {thresh.MIN_USABLE_MINUTES_FAIL}min")
        return True
    except Exception as e:
        print(f"  ✗ Threshold test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Connectivity QC Implementation Verification")
    print("=" * 60)

    all_passed = True

    # Test 1: Dependencies
    if not test_imports():
        all_passed = False
        print("\n⚠ Some dependencies are missing. Run:")
        print("  pip install -r requirements.txt")

    # Test 2: QC modules
    if not test_qc_modules():
        all_passed = False
        print("\n⚠ QC modules not importable. Check installation.")

    # Test 3: Nilearn functionality
    if not test_nilearn_atlas():
        all_passed = False
        print("\n⚠ Nilearn atlas fetch failed. Check internet connection.")

    # Test 4: Threshold values
    if not test_thresholds():
        all_passed = False
        print("\n⚠ Threshold values incorrect.")

    # Summary
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ ALL TESTS PASSED")
        print("\nConnectivity QC is ready to use!")
        print("\nUsage:")
        print("  python -m src.orchestrator \\")
        print("    --input /path/to/dicom \\")
        print("    --output_dir /path/to/output \\")
        print("    --connectivity-qc")
    else:
        print("✗ SOME TESTS FAILED")
        print("\nPlease address the issues above before using connectivity QC.")
        sys.exit(1)
    print("=" * 60)


if __name__ == "__main__":
    main()
