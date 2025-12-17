# fMRI Preprocessing Assistant

A cross-platform GUI application for converting DICOM neuroimaging data to BIDS format and running fMRIPrep preprocessing.

## Features

- **BIDS Conversion**: Convert DICOM files to Brain Imaging Data Structure (BIDS) format
- **fMRIPrep Integration**: Run fMRIPrep preprocessing via Docker
- **Aggressive Parallel Processing**: Processes ALL subjects and sessions simultaneously for maximum speed
- **Minimal Output**: Clean BIDS structure with no temporary files left behind
- **Comprehensive Report**: Human-readable conversion report for non-technical users
- **Cross-Platform**: Works on Windows, macOS, and Linux
- **Progress Tracking**: Real-time progress bar and detailed logging
- **Stop & Clean**: Cancel execution at any time with automatic cleanup

---

## Installation

### Prerequisites

- Python 3.10 or higher
- Docker Desktop (required for fMRIPrep)
- dcm2niix (bundled for Windows, auto-installed via dcm2bids for others)

### Setup

    ```bash
# Clone or download the repository
cd fMRI_Masters

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
    source venv/bin/activate

# Install dependencies
    pip install -r requirements.txt
    ```

### Requirements

```
customtkinter    # Modern GUI framework
dcm2bids         # DICOM to BIDS conversion
pydicom          # DICOM file reading
pandas           # Data handling
numpy            # Numerical operations
```

---

## Usage

### Launch the GUI

```bash
python gui_app.py
```

### Steps

1. **Select Source DICOM Folder**: Choose the folder containing your subject directories
2. **Select Output Folder**: Choose where to save the BIDS output
3. **Click a button**:
   - **Run BIDS Conversion**: Convert DICOM to BIDS format only
   - **Run Full Pipeline**: Convert to BIDS + run fMRIPrep preprocessing

### Expected Input Structure

```
source_folder/
├── 001/                    # Subject folder (any naming)
│   ├── MRI1/               # Session 1 (MRI1, ses-01, session1, etc.)
│   │   └── scans/          # Can have nested folders
│   │       ├── t1_mprage/
│   │       │   └── *.dcm
│   │       └── rest_fmri/
│   │           └── *.dcm
│   └── MRI2/               # Session 2
│       └── scans/
│           └── *.dcm
├── 002/                    # Another subject
│   └── MRI1/
│       └── ...
└── ...
```

**Supported session naming patterns:**
- `MRI1`, `MRI2`, `MRI3` → `ses-01`, `ses-02`, `ses-03`
- `ses-01`, `ses-02` → kept as-is
- `session1`, `session_2` → `ses-01`, `ses-02`
- `baseline`, `followup` → `ses-01`, `ses-02`

---

## BIDS Output Format

### Directory Structure

After conversion, your data will be organized directly in a timestamped output folder (minimal structure, no extra subfolders):

```
output_20241216_123456/           # Timestamped output folder
├── dataset_description.json      # Dataset metadata
├── conversion_report.txt         # Human-readable summary report
│
├── sub-001/                      # Subject 001
│   ├── ses-01/                   # Session 01
│   │   ├── anat/                 # Anatomical images
│   │   │   ├── sub-001_ses-01_T1w.nii.gz
│   │   │   └── sub-001_ses-01_T1w.json
│   │   │
│   │   ├── func/                 # Functional images
│   │   │   ├── sub-001_ses-01_task-rest_bold.nii.gz
│   │   │   └── sub-001_ses-01_task-rest_bold.json
│   │   │
│   │   ├── dwi/                  # Diffusion images (if available)
│   │   │   ├── sub-001_ses-01_dwi.nii.gz
│   │   │   ├── sub-001_ses-01_dwi.bval
│   │   │   └── sub-001_ses-01_dwi.bvec
│   │   │
│   │   └── fmap/                 # Field maps (if available)
│   │       └── sub-001_ses-01_phasediff.nii.gz
│   │
│   └── ses-02/                   # Session 02
│       └── ...
│
├── sub-002/
│   └── ...
│
└── derivatives/                  # fMRIPrep output (if full pipeline)
    └── fmriprep/
```

**Note:** Temporary files are automatically cleaned up after conversion.

### File Types

| Extension | Description |
|-----------|-------------|
| `.nii.gz` | Compressed NIfTI brain images |
| `.json` | Metadata sidecar (scan parameters) |
| `.bval` | Diffusion b-values (DWI only) |
| `.bvec` | Diffusion gradient directions (DWI only) |

### BIDS Naming Convention

```
sub-<subject>_ses-<session>_<modality>.nii.gz
```

| Component | Description | Examples |
|-----------|-------------|----------|
| `sub-XXX` | Subject identifier | sub-001, sub-pilot01 |
| `ses-XX` | Session number | ses-01, ses-02 |
| `task-XXX` | Task name (func only) | task-rest, task-motor |
| `run-XX` | Run number | run-01, run-02 |
| Suffix | Image type | T1w, T2w, bold, dwi |

### Example JSON Sidecar

Each `.nii.gz` file has a corresponding `.json` with metadata:

```json
{
    "Modality": "MR",
    "MagneticFieldStrength": 3,
    "Manufacturer": "Siemens",
    "RepetitionTime": 2.0,
    "EchoTime": 0.03,
    "FlipAngle": 90,
    "SliceTiming": [0, 0.5, 1.0, 1.5],
    "PhaseEncodingDirection": "j-"
}
```

---

## Configuration

### dcm2bids_config.json

This file defines how DICOM series are mapped to BIDS format:

```json
{
  "descriptions": [
    {
      "id": "anat_t1w",
      "datatype": "anat",
      "suffix": "T1w",
      "criteria": {
        "SeriesDescription": "*T1*"
      }
    },
    {
      "id": "func_rest",
      "datatype": "func",
      "suffix": "bold",
      "custom_entities": "task-rest",
      "criteria": {
        "SeriesDescription": "*rest*"
      },
      "sidecarChanges": {
        "TaskName": "rest"
      }
    }
  ]
}
```

**Key fields:**
- `datatype`: BIDS folder (anat, func, dwi, fmap)
- `suffix`: File suffix (T1w, T2w, bold, dwi)
- `criteria`: Rules to match DICOM series (uses SeriesDescription, etc.)
- `custom_entities`: Additional BIDS entities (task-xxx, run-xx)

### Customizing for Your Data

1. Run `dcm2bids_helper` on a sample DICOM folder to see available series
2. Check the generated JSON files in `tmp_dcm2bids/helper/`
3. Update `dcm2bids_config.json` to match your SeriesDescription patterns

---

## Parallel Processing

The pipeline automatically:
- Detects the number of CPU cores
- Processes sessions of the same subject in parallel
- Moves to the next subject after all sessions complete

Example with 3 subjects, 2 sessions each:
```
Subject 1/3: sub-001 (2 sessions)
  ├── ses-01 ──┬── Running in parallel
  └── ses-02 ──┘
       ↓ Complete
Subject 2/3: sub-002 (2 sessions)
  ├── ses-01 ──┬── Running in parallel
  └── ses-02 ──┘
       ↓ Complete
Subject 3/3: sub-003 (2 sessions)
  └── ...
```

---

## fMRIPrep (Full Pipeline)

When running the full pipeline, fMRIPrep is executed via Docker after BIDS conversion.

### Requirements

1. **Docker Desktop** must be installed and running
2. **FreeSurfer License**: Place your license file at `.freesurfer_license.txt` in the project root

### Output

fMRIPrep outputs are saved to:
```
output_<timestamp>/
├── bids_output/          # Raw BIDS data
└── derivatives/          # Preprocessed data
    └── fmriprep/
        ├── sub-001/
        │   └── ses-01/
        │       ├── anat/
        │       └── func/
        └── sub-001.html  # QC report
```

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| "dcm2bids not found" | Ensure virtual environment is activated |
| Unicode errors on Windows | Fixed in latest version (uses UTF-8 encoding) |
| "Docker not running" | Start Docker Desktop before running full pipeline |
| No DICOM files found | Check folder structure matches expected pattern |
| Progress bar stuck | Check logs for error messages |

### Logs

- GUI logs are displayed in the "Execution Logs" panel
- Detailed dcm2bids logs: `bids_output/tmp_dcm2bids/log/`
- fMRIPrep logs: `derivatives/sub-XX/ses-XX/log/`

---

## Command Line Usage

You can also run the pipeline directly:

```bash
# BIDS conversion only
python scripts/run_pipeline.py \
    --input /path/to/source \
    --output_dir /path/to/output

# Skip fMRIPrep (default)
python scripts/run_pipeline.py \
    --input /path/to/source \
    --output_dir /path/to/output \
    --skip-fmriprep

# Full pipeline
python scripts/run_pipeline.py \
    --input /path/to/source \
    --output_dir /path/to/output

# Single subject
python scripts/run_pipeline.py \
    --input /path/to/subject/folder \
    --output_dir /path/to/output \
    --subject 001 \
    --session 01
```

---

## License

MIT License

## References

- [BIDS Specification](https://bids-specification.readthedocs.io/)
- [dcm2bids Documentation](https://unfmontreal.github.io/Dcm2Bids/)
- [fMRIPrep Documentation](https://fmriprep.org/)
