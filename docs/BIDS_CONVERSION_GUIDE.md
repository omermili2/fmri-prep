# BIDS Conversion Guide

## 📚 Table of Contents
1. [What is BIDS?](#what-is-bids)
2. [Why BIDS Matters](#why-bids-matters)
3. [Input: Raw DICOM Data](#input-raw-dicom-data)
4. [The Conversion Process](#the-conversion-process)
5. [Output: BIDS Format](#output-bids-format)
6. [File Naming Conventions](#file-naming-conventions)
7. [Troubleshooting](#troubleshooting)

---

## What is BIDS?

**BIDS** = Brain Imaging Data Structure

BIDS is an international standard for organizing neuroimaging data. It specifies:
- How to name files
- How to organize folders
- What metadata to include

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         BIDS STANDARD                                   │
│                                                                         │
│   "A simple and intuitive way to organize and describe                  │
│    neuroimaging and behavioral data"                                    │
│                                                                         │
│   Website: https://bids.neuroimaging.io/                               │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Why BIDS Matters

### Before BIDS (Chaos)
```
my_study/
├── john_brain_scan_final_v2.nii
├── john_fmri_FIXED.nii
├── mary_t1_20231215.nii
├── data_backup/
│   └── old_scans/
│       └── ???
└── README.txt (last updated 2019)
```

### With BIDS (Order)
```
my_study/
├── dataset_description.json
├── participants.tsv
├── sub-01/
│   └── ses-01/
│       ├── anat/
│       │   └── sub-01_ses-01_T1w.nii.gz
│       └── func/
│           └── sub-01_ses-01_task-rest_bold.nii.gz
└── sub-02/
    └── ...
```

### Benefits of BIDS

| Benefit | Description |
|---------|-------------|
| **Tool Compatibility** | Works with fMRIPrep, MRIQC, and 100+ BIDS apps |
| **Data Sharing** | Required by OpenNeuro, many journals |
| **Reproducibility** | Anyone can understand your data structure |
| **Automation** | Tools can automatically find and process your data |
| **Future-Proofing** | Your data remains usable for years |

---

## Input: Raw DICOM Data

### What Comes From the Scanner

When someone gets an MRI scan, the scanner produces **DICOM files**:

```
MRI Scanner
    │
    ▼
001_Localizer/           ← Scout images (positioning)
    ├── IM-0001-0001.dcm
    ├── IM-0001-0002.dcm
    └── ... (20 files)
    
002_T1_MPRAGE/           ← Structural scan (brain anatomy)
    ├── IM-0002-0001.dcm
    ├── IM-0002-0002.dcm
    └── ... (192 files = 192 slices)
    
003_rest_fMRI/           ← Functional scan (brain activity)
    ├── IM-0003-0001.dcm
    └── ... (8000 files = 200 timepoints × 40 slices)
```

**Key insight:** Each `.dcm` file is a **single 2D slice**. A 3D brain image is split across hundreds of files!

### Expected Input Structure

```
sourcedata/
├── 001/                      # Subject folder (any naming works)
│   └── MRI1/                 # Session folder
│       ├── 001_Localizer/    # Scan series (will be ignored)
│       ├── 002_T1_MPRAGE/    # Anatomical scan
│       │   ├── IM-0001.dcm
│       │   ├── IM-0002.dcm
│       │   └── ...
│       └── 003_rest_fMRI/    # Functional scan
│           ├── IM-0001.dcm
│           └── ...
├── 002/
│   └── MRI1/
│       └── ...
└── 003/
    ├── MRI1/                 # First session
    └── MRI2/                 # Second session (e.g., 6-month followup)
```

### Supported Session Naming

The pipeline automatically recognizes these session folder names:

| Input Name | Converted To |
|------------|--------------|
| `MRI1`, `MRI2` | `ses-01`, `ses-02` |
| `ses-01`, `ses-02` | `ses-01`, `ses-02` |
| `session1`, `session_1` | `ses-01` |
| `baseline`, `pre` | `ses-01` |
| `followup`, `post` | `ses-02` |
| `timepoint1`, `tp1` | `ses-01` |

---

## The Conversion Process

### Overview

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                           BIDS CONVERSION PIPELINE                                    │
│                                                                                      │
│  DICOM Files  ──►  dcm2niix  ──►  Organize  ──►  Link Field Maps  ──►  BIDS        │
│  (Scanner)       (Converter)    (Auto-classify)  (IntendedFor)       (Standard)     │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### Step 1: Reading DICOM Headers

Each DICOM file contains metadata:
```
SeriesDescription: "T1_MPRAGE"
PatientID: "001"
AcquisitionDate: "20241217"
ImageType: ["ORIGINAL", "PRIMARY", "M"]
...
```

### Step 2: Converting to NIfTI (dcm2niix)

**dcm2niix** converts DICOM to NIfTI format:

```
192 DICOM slices  ──►  1 NIfTI file
     (2D)                  (3D)

8000 DICOM files  ──►  1 NIfTI file
  (2D slices)           (4D: 3D × time)
```

**What happens to each voxel:**
```
DICOM pixel → Rescale (slope/intercept) → Reorient to RAS → Write to NIfTI
```

**Orientation correction:**
- Scanners store images in various orientations
- dcm2niix rotates/flips to standard **RAS** orientation:
  - **R**ight → Left (X axis)
  - **A**nterior → Posterior (Y axis)
  - **S**uperior → Inferior (Z axis)

### Step 3: Automatic Classification

The pipeline reads JSON sidecar files (created by dcm2niix) to automatically classify scans:

```
JSON sidecar has:                    Classification:
SeriesDescription: "T1_MPRAGE"   ──► anat/T1w
SeriesDescription: "bold_rest"   ──► func/bold (task-rest)
SeriesDescription: "dwi_64dir"   ──► dwi/dwi
```

**Recognized scan types:**
- **Anatomical**: T1w (MPRAGE, SPGR, BRAVO), T2w, FLAIR
- **Functional**: BOLD, fMRI, EPI sequences
- **Diffusion**: DWI, DTI, HARDI
- **Fieldmaps**: SE-EPI, phasediff, AP/PA pairs

### Step 4: Organizing into BIDS

```
tmp_dcm2niix/T1_MPRAGE_4.nii.gz
                    │
                    ▼
sub-001/ses-01/anat/sub-001_ses-01_T1w.nii.gz
```

### Step 5: Linking Field Maps to BOLD Runs

When the scan protocol includes field maps (AP/PA spin-echo EPI pairs or GRE phase-difference maps), the pipeline automatically populates the `IntendedFor` field in each field map's JSON sidecar. This tells fMRIPrep which BOLD runs each field map should correct for susceptibility distortion.

**How matching works:**
- If there is a single field map pair, all BOLD runs in that session are assigned to it
- If there are multiple field map pairs, each pair is matched to the nearest BOLD runs by acquisition time
- If no timing information is available, all BOLD runs are conservatively assigned to all field maps
- Existing `IntendedFor` values are never overwritten

**Example** — after conversion, the field map JSON sidecar automatically contains:
```json
{
    "PhaseEncodingDirection": "j-",
    "AcquisitionTime": "10:00:00.000000",
    "IntendedFor": [
        "ses-01/func/sub-001_ses-01_task-rest_bold.nii.gz",
        "ses-01/func/sub-001_ses-01_task-memory_bold.nii.gz"
    ]
}
```

No manual editing is required. If your protocol does not include field maps, this step is skipped automatically.

### Visual Summary

```
Input:                              Output:
sourcedata/001/MRI1/                output_20241217/sub-001/ses-01/
├── 001_Localizer/     ─────────►   (ignored - scout images)
│   └── *.dcm
├── 002_T1_MPRAGE/     ─────────►   anat/
│   └── *.dcm (192)                 ├── sub-001_ses-01_T1w.nii.gz
│                                   └── sub-001_ses-01_T1w.json
├── 003_rest_fMRI/     ─────────►   func/
│   └── *.dcm (8000)                ├── sub-001_ses-01_task-rest_bold.nii.gz
│                                   └── sub-001_ses-01_task-rest_bold.json
└── 004_DWI/           ─────────►   dwi/
    └── *.dcm                       ├── sub-001_ses-01_dwi.nii.gz
                                    └── sub-001_ses-01_dwi.json
```

---

## Output: BIDS Format

### Complete Output Structure

```
output_20241217_143022/
│
├── dataset_description.json    # Required: dataset metadata
├── conversion_report.txt       # Human-readable summary
│
├── sub-001/                    # Subject 1
│   └── ses-01/                 # Session 1
│       │
│       ├── anat/               # Anatomical scans
│       │   ├── sub-001_ses-01_T1w.nii.gz      # T1-weighted image
│       │   ├── sub-001_ses-01_T1w.json        # Metadata
│       │   ├── sub-001_ses-01_T2w.nii.gz      # T2-weighted (if exists)
│       │   └── sub-001_ses-01_T2w.json
│       │
│       ├── func/               # Functional scans
│       │   ├── sub-001_ses-01_task-rest_run-01_bold.nii.gz   # Resting-state fMRI
│       │   ├── sub-001_ses-01_task-rest_run-01_bold.json
│       │   ├── sub-001_ses-01_task-memory_run-01_bold.nii.gz  # Task fMRI
│       │   └── sub-001_ses-01_task-memory_run-01_bold.json
│       │
│       ├── dwi/                # Diffusion imaging
│       │   ├── sub-001_ses-01_dwi.nii.gz
│       │   ├── sub-001_ses-01_dwi.json
│       │   ├── sub-001_ses-01_dwi.bval       # b-values
│       │   └── sub-001_ses-01_dwi.bvec       # b-vectors
│       │
│       └── fmap/               # Fieldmaps
│           ├── sub-001_ses-01_dir-AP_epi.nii.gz
│           └── sub-001_ses-01_dir-AP_epi.json
│
├── sub-002/
│   └── ...
│
└── sub-003/
    ├── ses-01/                 # First visit
    └── ses-02/                 # Follow-up visit
```

### Key Files Explained

#### dataset_description.json
```json
{
    "Name": "fMRI Pipeline Output",
    "BIDSVersion": "1.8.0",
    "DatasetType": "raw",
    "Authors": ["Pipeline"]
}
```

#### JSON Sidecar (e.g., T1w.json)
```json
{
    "Modality": "MR",
    "MagneticFieldStrength": 3,
    "Manufacturer": "Siemens",
    "ManufacturersModelName": "Prisma",
    "SequenceName": "tfl3d1",
    "RepetitionTime": 2.3,
    "EchoTime": 0.00293,
    "FlipAngle": 8,
    ...
}
```

---

## File Naming Conventions

### BIDS Naming Pattern

```
sub-<label>_ses-<label>_<key>-<value>_<suffix>.<extension>
    │           │           │              │         │
    │           │           │              │         └── .nii.gz, .json
    │           │           │              └── T1w, bold, dwi
    │           │           └── task-rest, run-01, dir-AP
    │           └── Session label (optional)
    └── Subject label
```

### Examples

| File | Meaning |
|------|---------|
| `sub-001_T1w.nii.gz` | Subject 1, T1-weighted scan |
| `sub-001_ses-01_T1w.nii.gz` | Subject 1, Session 1, T1-weighted |
| `sub-001_ses-01_task-rest_run-01_bold.nii.gz` | Subject 1, Resting-state fMRI, Run 1 |
| `sub-001_ses-01_task-memory_run-02_bold.nii.gz` | Subject 1, Memory task, Run 2 |

### Modality Folders

| Folder | Contents | Suffixes |
|--------|----------|----------|
| `anat/` | Structural images | T1w, T2w, FLAIR |
| `func/` | Functional images | bold |
| `dwi/` | Diffusion imaging | dwi |
| `fmap/` | Fieldmaps | phasediff, epi |
| `perf/` | Perfusion | asl |

---

## Troubleshooting

### Common Issues

#### "No DICOM files found"
```
Problem: Pipeline can't find your data
Solution: 
  1. Check folder structure
  2. Ensure files have .dcm or .ima extension
  3. Check for hidden folders (starting with .)
```

#### "No files were organized into BIDS structure"
```
Problem: dcm2niix converted files but they weren't recognized
Solution:
  1. Check SeriesDescription in your DICOM files
  2. Look at the JSON files in tmp_dcm2niix folder (if kept)
  3. Ensure scans have standard naming (bold, t1, mprage, etc.)
```

#### "Invalid BIDS"
```
Problem: BIDS validator shows errors
Solution:
  1. Check JSON files have required fields
  2. Verify task name matches for functional scans
  3. Ensure dataset_description.json exists
```

### Viewing DICOM Headers

To check what's in your DICOM files:

```bash
# Using dcm2niix (creates JSON with all headers)
dcm2niix -b o -f test /path/to/dicom/folder

# Using pydicom (Python)
python -c "
import pydicom
ds = pydicom.dcmread('IM-0001.dcm')
print(ds.SeriesDescription)
"
```

---

## Quick Reference

### Conversion Command (Manual)

```bash
dcm2niix \
  -z y \
  -b y \
  -ba n \
  -f %p_%s \
  -o /path/to/output \
  /path/to/dicom/folder
```

### Validate BIDS Output

```bash
# Install BIDS validator
npm install -g bids-validator

# Run validation
bids-validator /path/to/bids/dataset
```

### Useful Links

- [BIDS Specification](https://bids-specification.readthedocs.io/)
- [dcm2niix Documentation](https://github.com/rordenlab/dcm2niix)
- [BIDS Validator](https://bids-standard.github.io/bids-validator/)

---

*This guide is part of the fMRI Preprocessing Assistant project.*
