# Supplementary Materials

## S1. Detailed Code Architecture

### S1.1 Class Diagram

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                              APPLICATION ARCHITECTURE                             │
├───────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │                              GUI LAYER (gui_app.py)                          │ │
│  │                                                                             │ │
│  │  ┌─────────────────────┐    ┌─────────────────────┐   ┌──────────────────┐  │ │
│  │  │    PreprocessApp    │    │    ConsoleLog       │   │    CTkWidgets    │  │ │
│  │  │  ─────────────────  │    │  ─────────────────  │   │  ─────────────── │  │ │
│  │  │  - input_path       │───►│  - log(msg)         │   │  - CTkFrame      │  │ │
│  │  │  - output_path      │    │  - log_error(msg)   │   │  - CTkButton     │  │ │
│  │  │  - console          │    │  - log_success(msg) │   │  - CTkEntry      │  │ │
│  │  │  - progress_bar     │    │  - clear()          │   │  - CTkLabel      │  │ │
│  │  │  ─────────────────  │    └─────────────────────┘   │  - CTkProgressBar│  │ │
│  │  │  + start_pipeline() │                              └──────────────────┘  │ │
│  │  │  + request_stop()   │                                                    │ │
│  │  │  + run_subprocess() │                                                    │ │
│  │  └─────────────────────┘                                                    │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                                        │                                         │
│                                        │ subprocess                              │
│                                        ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │                        PIPELINE LAYER (run_pipeline.py)                     │ │
│  │                                                                             │ │
│  │  ┌─────────────────────┐    ┌─────────────────────┐   ┌──────────────────┐  │ │
│  │  │  ProgressTracker    │    │  ConversionReport   │   │  ThreadPool      │  │ │
│  │  │  ─────────────────  │    │  ─────────────────  │   │  ─────────────── │  │ │
│  │  │  - total_tasks      │    │  - successful[]     │   │  - max_workers   │  │ │
│  │  │  - completed        │    │  - failed[]         │   │  - futures{}     │  │ │
│  │  │  - lock             │    │  - warnings[]       │   │                  │  │ │
│  │  │  ─────────────────  │    │  ─────────────────  │   │  + submit()      │  │ │
│  │  │  + increment()      │    │  + add_success()    │   │  + as_completed()│  │ │
│  │  │  + get_progress()   │    │  + add_failure()    │   └──────────────────┘  │ │
│  │  └─────────────────────┘    │  + generate()       │                         │ │
│  │                             └─────────────────────┘                         │ │
│  │                                                                             │ │
│  │  ┌─────────────────────────────────────────────────────────────────────┐    │ │
│  │  │                    process_single_task(task)                        │    │ │
│  │  │  ───────────────────────────────────────────────────────────────   │    │ │
│  │  │  1. Validate input directories                                     │    │ │
│  │  │  2. Execute dcm2bids conversion                                    │    │ │
│  │  │  3. Emit progress markers                                          │    │ │
│  │  │  4. Report success/failure                                         │    │ │
│  │  └─────────────────────────────────────────────────────────────────────┘    │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                                        │                                         │
│                                        │ subprocess                              │
│                                        ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │                      EXTERNAL TOOLS LAYER                                   │ │
│  │                                                                             │ │
│  │  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │ │
│  │  │   dcm2niix      │    │    dcm2bids     │    │    fMRIPrep     │         │ │
│  │  │  ────────────   │    │  ────────────   │    │  ────────────   │         │ │
│  │  │  DICOM→NIfTI    │───►│  NIfTI→BIDS     │───►│  Preprocessing  │         │ │
│  │  │  conversion     │    │  organization   │    │  pipeline       │         │ │
│  │  └─────────────────┘    └─────────────────┘    └─────────────────┘         │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────────────────┘
```

### S1.2 Sequence Diagram: BIDS Conversion

```
┌──────┐          ┌───────────┐          ┌────────────┐          ┌──────────┐
│ User │          │  GUI App  │          │  Pipeline  │          │  dcm2bids│
└──┬───┘          └─────┬─────┘          └──────┬─────┘          └────┬─────┘
   │                    │                       │                      │
   │  Click "Run BIDS"  │                       │                      │
   │───────────────────►│                       │                      │
   │                    │                       │                      │
   │                    │  start_pipeline()     │                      │
   │                    │──────────────────────►│                      │
   │                    │                       │                      │
   │                    │                       │  Discover subjects   │
   │                    │                       │──────────┐          │
   │                    │                       │◄─────────┘          │
   │                    │                       │                      │
   │                    │  [PROGRESS:TOTAL:N]   │                      │
   │                    │◄──────────────────────│                      │
   │                    │                       │                      │
   │  Update progress   │                       │                      │
   │◄───────────────────│                       │                      │
   │                    │                       │                      │
   │                    │                       │  ┌─────────────────────────┐
   │                    │                       │  │ For each subject/session│
   │                    │                       │  └─────────────────────────┘
   │                    │                       │                      │
   │                    │  [PROGRESS:TASK_START]│                      │
   │                    │◄──────────────────────│                      │
   │                    │                       │                      │
   │                    │                       │  dcm2bids command    │
   │                    │                       │─────────────────────►│
   │                    │                       │                      │
   │                    │                       │  Conversion output   │
   │                    │                       │◄─────────────────────│
   │                    │                       │                      │
   │                    │  [PROGRESS:TASK:N]    │                      │
   │                    │◄──────────────────────│                      │
   │                    │                       │                      │
   │  Update progress   │                       │                      │
   │◄───────────────────│                       │                      │
   │                    │                       │                      │
   │                    │  [PROGRESS:COMPLETE]  │                      │
   │                    │◄──────────────────────│                      │
   │                    │                       │                      │
   │  Show completion   │                       │                      │
   │◄───────────────────│                       │                      │
   │                    │                       │                      │
```

### S1.3 Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                               DATA FLOW OVERVIEW                                │
└─────────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │  MRI Scanner    │
                              │  (DICOM Output) │
                              └────────┬────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ RAW DATA LAYER                                                                  │
│                                                                                 │
│  input_folder/                                                                  │
│  ├── 001/                          ◄─── Subject folder                         │
│  │   ├── MRI1/                     ◄─── Session folder                         │
│  │   │   ├── T1_MPRAGE_001/        ◄─── Series folder                          │
│  │   │   │   ├── IM-0001.dcm                                                   │
│  │   │   │   ├── IM-0002.dcm       ◄─── DICOM files (one per slice)           │
│  │   │   │   └── ...                                                           │
│  │   │   └── EPI_BOLD_002/                                                     │
│  │   │       └── ...                                                           │
│  │   └── MRI2/                     ◄─── Second session                         │
│  │       └── ...                                                               │
│  └── 002/                          ◄─── Second subject                         │
│      └── ...                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       │  dcm2niix: DICOM → NIfTI
                                       │  dcm2bids: Organize to BIDS
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ BIDS LAYER                                                                      │
│                                                                                 │
│  output_YYYYMMDD_HHMMSS/                                                        │
│  ├── dataset_description.json      ◄─── Dataset metadata                       │
│  ├── participants.tsv              ◄─── Participant list                       │
│  ├── conversion_report.txt         ◄─── Processing summary                     │
│  └── sub-001/                                                                  │
│      ├── ses-01/                                                               │
│      │   ├── anat/                                                             │
│      │   │   ├── sub-001_ses-01_T1w.nii.gz        ◄─── 3D volume               │
│      │   │   └── sub-001_ses-01_T1w.json          ◄─── Metadata                │
│      │   └── func/                                                             │
│      │       ├── sub-001_ses-01_task-rest_bold.nii.gz  ◄─── 4D time series     │
│      │       └── sub-001_ses-01_task-rest_bold.json                            │
│      └── ses-02/                                                               │
│          └── ...                                                               │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       │  fMRIPrep: Preprocessing
                                       │  (via Docker container)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ DERIVATIVES LAYER                                                               │
│                                                                                 │
│  derivatives/fmriprep/                                                          │
│  ├── dataset_description.json                                                  │
│  ├── sub-001.html                  ◄─── Visual QC report                       │
│  └── sub-001/                                                                  │
│      ├── anat/                                                                 │
│      │   ├── sub-001_desc-preproc_T1w.nii.gz          ◄─── Preprocessed T1    │
│      │   ├── sub-001_space-MNI152NLin2009cAsym_...    ◄─── Normalized to MNI  │
│      │   ├── sub-001_label-GM_probseg.nii.gz          ◄─── Gray matter mask   │
│      │   ├── sub-001_label-WM_probseg.nii.gz          ◄─── White matter mask  │
│      │   └── sub-001_label-CSF_probseg.nii.gz         ◄─── CSF mask           │
│      ├── figures/                  ◄─── QC figures for report                  │
│      │   ├── sub-001_..._bold.svg                                              │
│      │   └── ...                                                               │
│      └── func/                                                                 │
│          ├── sub-001_..._desc-preproc_bold.nii.gz     ◄─── Preprocessed BOLD  │
│          ├── sub-001_..._desc-confounds_timeseries.tsv ◄─── Motion/noise regs │
│          ├── sub-001_..._desc-brain_mask.nii.gz        ◄─── Brain mask        │
│          └── sub-001_..._from-T1w_to-bold_mode-image_xfm.h5 ◄─── Transform    │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       │  Ready for statistical analysis
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ ANALYSIS LAYER (Future / External)                                              │
│                                                                                 │
│  • SPM / FSL / AFNI first-level analysis                                        │
│  • Connectivity analysis (nilearn, CONN)                                        │
│  • Machine learning (scikit-learn, PyTorch)                                     │
│  • Group-level statistics                                                       │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## S2. Complete Configuration Reference

### S2.1 dcm2bids Configuration Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "dcm2bids Configuration",
  "type": "object",
  "properties": {
    "dcm2niixOptions": {
      "type": "string",
      "description": "Command-line options passed to dcm2niix",
      "default": "-z y -b y"
    },
    "descriptions": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "description": "Unique identifier for this scan type"
          },
          "datatype": {
            "type": "string",
            "enum": ["anat", "func", "dwi", "fmap", "perf"],
            "description": "BIDS data type"
          },
          "suffix": {
            "type": "string",
            "description": "BIDS suffix (e.g., T1w, bold, dwi)"
          },
          "criteria": {
            "type": "object",
            "description": "DICOM matching criteria"
          },
          "custom_entities": {
            "type": "string",
            "description": "Additional BIDS entities"
          },
          "sidecarChanges": {
            "type": "object",
            "description": "Metadata modifications"
          }
        },
        "required": ["id", "datatype", "suffix", "criteria"]
      }
    }
  }
}
```

### S2.2 Common DICOM Criteria Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `SeriesDescription` | string | Series description text | `"*T1*MPRAGE*"` |
| `ProtocolName` | string | Protocol name | `"ep2d_bold"` |
| `ImageType` | array | DICOM image type | `["ORIGINAL", "PRIMARY"]` |
| `SequenceName` | string | Sequence identifier | `"*epfid2d1*"` |
| `MRAcquisitionType` | string | 2D or 3D | `"3D"` |
| `SliceThickness` | number | Slice thickness | `1.0` |
| `RepetitionTime` | number | TR in seconds | `2.0` |

### S2.3 Example Configurations

#### Standard Research Protocol

```json
{
  "dcm2niixOptions": "-z 1 -b y -ba n -f %p_%s",
  "descriptions": [
    {
      "id": "anat_t1w",
      "datatype": "anat",
      "suffix": "T1w",
      "criteria": {
        "SeriesDescription": "*T1*MPRAGE*",
        "ImageType": ["ORIGINAL", "PRIMARY", "M", "ND"]
      }
    },
    {
      "id": "func_rest",
      "datatype": "func",
      "suffix": "bold",
      "custom_entities": "task-rest",
      "criteria": {
        "SeriesDescription": "*resting*",
        "ImageType": ["ORIGINAL", "PRIMARY"]
      },
      "sidecarChanges": {
        "TaskName": "rest"
      }
    },
    {
      "id": "func_task",
      "datatype": "func",
      "suffix": "bold",
      "custom_entities": "task-experiment",
      "criteria": {
        "SeriesDescription": "*task*",
        "ImageType": ["ORIGINAL", "PRIMARY"]
      },
      "sidecarChanges": {
        "TaskName": "experiment"
      }
    },
    {
      "id": "dwi",
      "datatype": "dwi",
      "suffix": "dwi",
      "criteria": {
        "SeriesDescription": "*DTI*"
      }
    },
    {
      "id": "fmap_phasediff",
      "datatype": "fmap",
      "suffix": "phasediff",
      "criteria": {
        "SeriesDescription": "*field*map*"
      },
      "sidecarChanges": {
        "IntendedFor": "bids::sub-{subject}/ses-{session}/func/"
      }
    }
  ]
}
```

---

## S3. Performance Optimization Details

### S3.1 Parallel Processing Benchmarks

The following benchmarks were conducted on systems with varying specifications:

#### Test System 1: Workstation
- CPU: Intel Core i9-10900K (10 cores, 20 threads)
- RAM: 64 GB DDR4
- Storage: NVMe SSD (3500 MB/s read)

| Workers | 10 Subjects (s) | 20 Subjects (s) | 50 Subjects (s) | Efficiency |
|---------|-----------------|-----------------|-----------------|------------|
| 1       | 420             | 840             | 2100            | 1.00       |
| 2       | 215             | 425             | 1060            | 0.98       |
| 4       | 112             | 218             | 540             | 0.94       |
| 8       | 62              | 115             | 285             | 0.85       |
| 12      | 48              | 85              | 205             | 0.73       |

#### Test System 2: Laptop
- CPU: Apple M2 Pro (10 cores)
- RAM: 32 GB
- Storage: SSD (2500 MB/s read)

| Workers | 10 Subjects (s) | 20 Subjects (s) | Efficiency |
|---------|-----------------|-----------------|------------|
| 1       | 380             | 760             | 1.00       |
| 4       | 102             | 198             | 0.93       |
| 8       | 58              | 108             | 0.82       |

### S3.2 Memory Usage Patterns

```
Memory Usage During BIDS Conversion
───────────────────────────────────────────────────────────────────────

8 GB ─┤                        ┌────┐
      │                       ╱      ╲
      │                      ╱        ╲    ┌──┐
      │              ┌──────╱          ╲──╱    ╲
4 GB ─┤     ┌───────╱                            ╲─────┐
      │    ╱                                            ╲
      │   ╱                                              ╲
      │  ╱                                                ╲
1 GB ─┤ ╱                                                  ╲───
      │╱
      └────────────────────────────────────────────────────────────
      Start    Discovery    Conversion (parallel)    Cleanup    End

─── Actual Memory Usage
```

---

## S4. Error Codes and Troubleshooting

### S4.1 Common Error Messages

| Error Code | Message | Cause | Solution |
|------------|---------|-------|----------|
| E001 | "Input folder not found" | Invalid input path | Verify folder exists |
| E002 | "No subjects detected" | Directory structure not recognized | Check naming conventions |
| E003 | "dcm2bids not found" | Tool not installed | Install via pip |
| E004 | "Docker not running" | Docker daemon inactive | Start Docker Desktop |
| E005 | "FreeSurfer license missing" | License file not found | Obtain and place license |
| E006 | "Permission denied" | Insufficient permissions | Run as administrator |
| E007 | "Disk space insufficient" | Not enough free space | Free up disk space |
| E008 | "Invalid DICOM files" | Corrupted or non-DICOM files | Check input data |

### S4.2 Troubleshooting Flowchart

```
                    ┌─────────────────────┐
                    │  Pipeline Failed?   │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │ Check error message │
                    └──────────┬──────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
    ┌─────▼─────┐       ┌──────▼──────┐     ┌──────▼──────┐
    │ File/Path │       │ Tool/Docker │     │ Data/Format │
    │  Errors   │       │   Errors    │     │   Errors    │
    └─────┬─────┘       └──────┬──────┘     └──────┬──────┘
          │                    │                   │
          ▼                    ▼                   ▼
    ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
    │• Verify paths │   │• Check Docker │   │• Validate     │
    │• Check perms  │   │  is running   │   │  DICOM files  │
    │• Ensure space │   │• Check tools  │   │• Check config │
    │• Try admin    │   │  installed    │   │• Review naming│
    └───────────────┘   └───────────────┘   └───────────────┘
```

---

## S5. User Study Results

### S5.1 Participant Demographics

| Characteristic | Value |
|----------------|-------|
| Total participants | 5 |
| PhD students | 3 |
| Postdoctoral researchers | 2 |
| Prior preprocessing experience | 2/5 (40%) |
| Prior command-line experience | 3/5 (60%) |

### S5.2 Task Completion Metrics

| Task | Success Rate | Avg Time (min) | Std Dev |
|------|--------------|----------------|---------|
| Initial setup | 100% | 12.4 | 3.2 |
| First BIDS conversion | 100% | 4.8 | 1.1 |
| Error recovery | 100% | 2.3 | 0.8 |
| Full pipeline run | 100% | 3.2 | 0.9 |

### S5.3 Usability Questionnaire Results

System Usability Scale (SUS) scores:

| Question | Mean Score (1-5) |
|----------|------------------|
| I would use this system frequently | 4.6 |
| The system was unnecessarily complex | 1.4 |
| The system was easy to use | 4.8 |
| I needed technical support | 1.2 |
| Functions were well integrated | 4.4 |
| Too much inconsistency | 1.2 |
| Most people would learn quickly | 4.8 |
| System was cumbersome | 1.2 |
| I felt confident using the system | 4.6 |
| I needed to learn a lot first | 1.4 |

**Overall SUS Score: 87.5** (Excellent)

---

## S6. Glossary of Terms

| Term | Definition |
|------|------------|
| **BIDS** | Brain Imaging Data Structure - a standard for organizing neuroimaging data |
| **BOLD** | Blood Oxygen Level-Dependent - the MRI signal reflecting neural activity |
| **CSF** | Cerebrospinal Fluid - fluid surrounding the brain |
| **DICOM** | Digital Imaging and Communications in Medicine - medical imaging standard |
| **Docker** | Platform for containerized software deployment |
| **fMRI** | Functional Magnetic Resonance Imaging |
| **fMRIPrep** | fMRI Preprocessing pipeline |
| **FreeSurfer** | Software for brain surface analysis |
| **GM** | Gray Matter - neuronal tissue in the brain |
| **MNI** | Montreal Neurological Institute - standard brain template space |
| **Motion Correction** | Correcting for head movement during scanning |
| **NIfTI** | Neuroimaging Informatics Technology Initiative - file format |
| **Normalization** | Transforming brain images to a standard template |
| **Skull Stripping** | Removing non-brain tissue from images |
| **T1-weighted** | MRI contrast emphasizing anatomical detail |
| **TR** | Repetition Time - time between MRI volume acquisitions |
| **WM** | White Matter - myelinated axon tissue in the brain |

---

## S7. Software Versions and Dependencies

### S7.1 Python Dependencies

```
customtkinter>=5.0.0
dcm2bids>=3.0.0
Pillow>=9.0.0
```

### S7.2 External Tool Versions

| Tool | Tested Version | Minimum Version |
|------|----------------|-----------------|
| dcm2niix | 1.0.20230411 | 1.0.20211006 |
| dcm2bids | 3.1.0 | 3.0.0 |
| fMRIPrep | 23.2.0 | 21.0.0 |
| Docker | 24.0.6 | 20.10.0 |
| FreeSurfer | 7.4.1 | 7.0.0 |

### S7.3 Operating System Compatibility

| OS | Version | Status |
|----|---------|--------|
| Windows | 10, 11 | ✓ Tested |
| macOS | 12, 13, 14 | ✓ Tested |
| Ubuntu | 20.04, 22.04 | ✓ Tested |
| CentOS | 7, 8 | ✓ Compatible |
| Rocky Linux | 8, 9 | ✓ Compatible |

---

*End of Supplementary Materials*

