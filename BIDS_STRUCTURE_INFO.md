# BIDS Conversion: Expected Inputs & Outputs

This document explains what happens during the "Convert to BIDS" step.

## 1. Input Structure (Raw Data)
The tool expects a **root directory** containing one or more subject folders. Inside each subject folder, it looks for DICOM files (either directly or in subfolders like `dcm/`).

**Example Input Structure:**
```
/path/to/raw_data/
├── sub-01/              <-- Subject Folder (Name determines ID)
│   └── dcm/
│       ├── image001.dcm
│       ├── image002.dcm
│       └── ...
├── sub-02/
│   └── dcm/
│       └── ...
└── ...
```

*   **Subject ID:** The script automatically cleans the folder name. `sub-01` becomes `sub-01` in BIDS. `Patient_72` becomes `sub-Patient72`.
*   **File Types:** It supports standard `.dcm` files.

## 2. Output Structure (BIDS Standard)
The tool creates a `bids_output` folder. This is a highly standardized structure required by scientific tools.

**Example Output Structure:**
```
/path/to/output_folder/bids_output/
├── dataset_description.json      <-- Vital metadata for the dataset
├── sub-01/
│   ├── ses-01/                   <-- Session folder (default: ses-01)
│   │   ├── anat/                 <-- Anatomical scans
│   │   │   ├── sub-01_ses-01_T1w.nii.gz      (Image)
│   │   │   └── sub-01_ses-01_T1w.json        (Metadata)
│   │   └── func/                 <-- Functional (fMRI) scans
│   │       ├── sub-01_ses-01_task-rest_bold.nii.gz
│   │       └── sub-01_ses-01_task-rest_bold.json
└── sub-02/
    └── ...
```

*   **NIfTI (.nii.gz):** The actual 3D/4D image data (converted from DICOM).
*   **JSON (.json):** Sidecar files containing scan parameters (TR, TE, Slice Timing).
*   **Anat vs Func:** The `dcm2bids_config.json` file controls which scans go into `anat` (structural) or `func` (functional) based on their protocol names.

