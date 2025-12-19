# fMRIPrep Preprocessing Guide

## 📚 Table of Contents
1. [What is fMRIPrep?](#what-is-fmriprep)
2. [Why Preprocessing is Needed](#why-preprocessing-is-needed)
3. [The Complete Pipeline](#the-complete-pipeline)
4. [Step-by-Step Explanation](#step-by-step-explanation)
5. [Output Files](#output-files)
6. [The Confounds File](#the-confounds-file)
7. [Quality Control Reports](#quality-control-reports)
8. [What fMRIPrep Does NOT Do](#what-fmriprep-does-not-do)
9. [Configuration Options](#configuration-options)
10. [Troubleshooting](#troubleshooting)

---

## What is fMRIPrep?

**fMRIPrep** (functional MRI Preprocessing) is an automated pipeline that transforms raw fMRI data into analysis-ready data. Developed by the Poldrack Lab at Stanford, it is now the **gold standard** in the neuroimaging community.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           fMRIPrep                                      │
│                                                                         │
│   "A robust preprocessing pipeline for fMRI data that requires         │
│    minimal user input while providing comprehensive quality            │
│    control reports"                                                     │
│                                                                         │
│   Website: https://fmriprep.org/                                       │
│   Paper: https://doi.org/10.1038/s41592-018-0235-4                    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Philosophy

| Principle | Description |
|-----------|-------------|
| **Glass box** | Every step is documented and transparent |
| **Reproducible** | Same inputs always produce same outputs |
| **Best practices** | Automatically selects optimal algorithms |
| **No tuning** | Works out-of-the-box for most datasets |

### Why Docker?

fMRIPrep runs inside a **Docker container** because it has hundreds of dependencies:

```
┌──────────────────────────────────────┐
│           Docker Container           │
│  ┌────────────────────────────────┐  │
│  │         fMRIPrep               │  │
│  │  ┌─────┐ ┌─────┐ ┌──────────┐  │  │
│  │  │ FSL │ │ANTS │ │FreeSurfer│  │  │
│  │  └─────┘ └─────┘ └──────────┘  │  │
│  │  ┌─────┐ ┌─────┐ ┌──────────┐  │  │
│  │  │Nipype│ │Python│ │ And more│  │  │
│  │  └─────┘ └─────┘ └──────────┘  │  │
│  └────────────────────────────────┘  │
└──────────────────────────────────────┘
         Your computer just runs Docker
```

---

## Why Preprocessing is Needed

Raw fMRI data is **unusable** for analysis due to several problems:

### Problems in Raw fMRI Data

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    PROBLEMS IN RAW fMRI DATA                            │
│                                                                         │
│   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    │
│   │  HEAD MOTION    │    │  DISTORTIONS    │    │  SLICE TIMING   │    │
│   │                 │    │                 │    │                 │    │
│   │   ↗ ↘ ↙ ↖      │    │    ~~~~         │    │  t=0 ─────      │    │
│   │  Subject moves  │    │  Warped brain   │    │  t=1 ─────      │    │
│   │  during scan    │    │  near sinuses   │    │  t=2 ─────      │    │
│   └─────────────────┘    └─────────────────┘    └─────────────────┘    │
│                                                                         │
│   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    │
│   │  DIFFERENT      │    │  NON-BRAIN      │    │  NOISE          │    │
│   │  BRAIN SHAPES   │    │  TISSUE         │    │                 │    │
│   │                 │    │                 │    │  ~~~~ ~~~~      │    │
│   │  Person A ≠ B   │    │  Skull, eyes    │    │  Scanner drift  │    │
│   │                 │    │  still in image │    │  Breathing      │    │
│   └─────────────────┘    └─────────────────┘    └─────────────────┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### What fMRIPrep Fixes

| Problem | Solution | Why It Matters |
|---------|----------|----------------|
| **Head motion** | Motion correction (realignment) | 1mm movement can create false activations |
| **Slice timing** | Slice timing correction | Slices acquired at different times |
| **Distortions** | Susceptibility distortion correction | EPI images are warped |
| **Different brains** | Spatial normalization to MNI | Enables group comparisons |
| **Non-brain tissue** | Brain extraction (skull stripping) | Removes confounding tissue |
| **Noise** | Confound estimation | Identifies signals to regress out |

---

## The Complete Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         fMRIPrep PROCESSING FLOW                            │
│                                                                             │
│  ┌──────────────────────────┐    ┌──────────────────────────┐              │
│  │   ANATOMICAL WORKFLOW    │    │   FUNCTIONAL WORKFLOW    │              │
│  │      (T1w image)         │    │     (BOLD images)        │              │
│  └────────────┬─────────────┘    └────────────┬─────────────┘              │
│               │                               │                             │
│               ▼                               ▼                             │
│  ┌──────────────────────────┐    ┌──────────────────────────┐              │
│  │  1. Brain Extraction     │    │  5. Reference Generation │              │
│  │     (Skull Stripping)    │    │     (Pick best volume)   │              │
│  └────────────┬─────────────┘    └────────────┬─────────────┘              │
│               │                               │                             │
│               ▼                               ▼                             │
│  ┌──────────────────────────┐    ┌──────────────────────────┐              │
│  │  2. Tissue Segmentation  │    │  6. Head Motion Correction│             │
│  │     (GM, WM, CSF)        │    │     (Realignment)        │              │
│  └────────────┬─────────────┘    └────────────┬─────────────┘              │
│               │                               │                             │
│               ▼                               ▼                             │
│  ┌──────────────────────────┐    ┌──────────────────────────┐              │
│  │  3. Surface Recon        │    │  7. Slice Timing         │              │
│  │     (Optional)           │    │     Correction           │              │
│  └────────────┬─────────────┘    └────────────┬─────────────┘              │
│               │                               │                             │
│               ▼                               ▼                             │
│  ┌──────────────────────────┐    ┌──────────────────────────┐              │
│  │  4. Spatial              │    │  8. Susceptibility       │              │
│  │     Normalization        │◄───┤     Distortion Correction│              │
│  │     (to MNI template)    │    │     (if fieldmaps exist) │              │
│  └────────────┬─────────────┘    └────────────┬─────────────┘              │
│               │                               │                             │
│               └───────────────┬───────────────┘                             │
│                               ▼                                             │
│               ┌──────────────────────────┐                                  │
│               │  9. BOLD-to-T1w          │                                  │
│               │     Registration         │                                  │
│               └────────────┬─────────────┘                                  │
│                            │                                                │
│                            ▼                                                │
│               ┌──────────────────────────┐                                  │
│               │  10. Confound Estimation │                                  │
│               │      (Motion, Noise)     │                                  │
│               └────────────┬─────────────┘                                  │
│                            │                                                │
│                            ▼                                                │
│               ┌──────────────────────────┐                                  │
│               │  11. Output Generation   │                                  │
│               │      (Images + Reports)  │                                  │
│               └──────────────────────────┘                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Step-by-Step Explanation

### Step 1: Brain Extraction (Skull Stripping)

**What it does:** Removes non-brain tissue (skull, eyes, skin, neck) from the T1w image.

**Why it matters:**
- Reduces file size
- Prevents non-brain tissue from interfering with registration
- Required for tissue segmentation

**Algorithm:** ANTs `antsBrainExtraction.sh` with OASIS template

```
Before:                    After:
┌─────────────┐            ┌─────────────┐
│  ┌─────┐    │            │             │
│  │Skull│    │            │  ┌─────┐    │
│  │Brain│    │     ──►    │  │Brain│    │
│  │Neck │    │            │  └─────┘    │
│  └─────┘    │            │             │
└─────────────┘            └─────────────┘
```

**Output:** `sub-001_desc-brain_mask.nii.gz`

---

### Step 2: Tissue Segmentation

**What it does:** Classifies each voxel into tissue types:

| Tissue | Description | Use |
|--------|-------------|-----|
| **Gray Matter (GM)** | Cortex, where neurons are | Where to look for activity |
| **White Matter (WM)** | Connection fibers | Nuisance signal source |
| **CSF** | Fluid around brain | Nuisance signal source |

**Algorithm:** FSL FAST

**Output files:**
```
sub-001_label-GM_probseg.nii.gz   # Gray matter probability (0-1)
sub-001_label-WM_probseg.nii.gz   # White matter probability
sub-001_label-CSF_probseg.nii.gz  # CSF probability
sub-001_dseg.nii.gz               # Discrete: 1=CSF, 2=GM, 3=WM
```

---

### Step 3: Surface Reconstruction (Optional)

**What it does:** Creates a 3D mesh of the brain's cortical surface.

**Why it matters:**
- Enables surface-based analysis
- Better visualization
- Required for cortical thickness analysis

**Algorithm:** FreeSurfer `recon-all`

**Note:** Our pipeline uses `--fs-no-reconall` to **skip this** (saves ~6 hours!)

---

### Step 4: Spatial Normalization

**What it does:** Warps the individual brain to a standard template (MNI152).

**Why it matters:**
- Different people have different brain shapes
- To compare brains, they must be in the same space
- MNI coordinates are universally understood

**Algorithm:** ANTs SyN (Symmetric Normalization)

```
Individual Brain              MNI Template (Standard)
┌─────────────┐               ┌─────────────┐
│   ┌───┐     │               │   ┌───┐     │
│   │   │ ◄───┼──── warp ────►│   │   │     │
│   │   │     │               │   │   │     │
│   └───┘     │               │   └───┘     │
└─────────────┘               └─────────────┘
   Unique shape                 Standard shape
```

**Output:**
```
sub-001_from-T1w_to-MNI152NLin2009cAsym_mode-image_xfm.h5   # Forward transform
sub-001_from-MNI152NLin2009cAsym_to-T1w_mode-image_xfm.h5   # Inverse transform
sub-001_space-MNI152NLin2009cAsym_desc-preproc_T1w.nii.gz   # T1 in MNI space
```

---

### Step 5: BOLD Reference Generation

**What it does:** Creates a single reference image from the 4D BOLD data.

**Why it matters:**
- Can't register a 4D volume directly
- Need a high-quality single frame
- Usually uses mean of initial volumes

---

### Step 6: Head Motion Correction

**What it does:** Aligns all BOLD volumes to the reference, correcting for head movement.

**Why it matters:**
- Subject moves during 10-30 minute scan
- Even 1mm motion can create artifacts
- Motion is #1 source of fMRI artifacts

**Algorithm:** FSL MCFLIRT

```
Volume 1     Volume 50    Volume 100   Volume 150
┌─────┐      ┌─────┐      ┌─────┐      ┌─────┐
│     │      │  ↗  │      │  ↘  │      │     │
│ ●   │      │   ● │      │ ●   │      │  ●  │
│     │      │     │      │     │      │     │
└─────┘      └─────┘      └─────┘      └─────┘
 Reference    Moved        Moved        Moved
    │           │            │            │
    └───────────┴────────────┴────────────┘
                      │
                      ▼
               All aligned to
               same position
```

**Output:** 6 motion parameters per volume (X, Y, Z translation + pitch, roll, yaw rotation)

---

### Step 7: Slice Timing Correction

**What it does:** Corrects for slices being acquired at different times.

**Why it matters:**
- 2-second TR means slice 1 at t=0, slice 40 at t=1.95s
- This timing difference affects analysis
- Interpolates all slices to common time point

**Algorithm:** AFNI 3dTshift or FSL slicetimer

```
Slice 40 ────── acquired at t=1.95s ──────┐
Slice 30 ────── acquired at t=1.46s ──────┤
Slice 20 ────── acquired at t=0.97s ──────┼──► All interpolated
Slice 10 ────── acquired at t=0.49s ──────┤    to t=1.0s (middle)
Slice 1  ────── acquired at t=0.00s ──────┘
```

---

### Step 8: Susceptibility Distortion Correction

**What it does:** Fixes geometric distortions from magnetic field inhomogeneities.

**Why it matters:**
- EPI images are heavily distorted near air-tissue boundaries
- Orbitofrontal cortex and temporal poles are "stretched"
- Critical for accurate localization

**Methods:**
- Phase-difference fieldmap
- "Pepolar" method (two EPIs with opposite phase encoding)

```
Before SDC:              After SDC:
┌───────────────┐        ┌───────────────┐
│    ~~~~       │        │    ────       │
│   ~~~~        │   ──►  │   ────        │
│  Distorted    │        │  Corrected    │
│   front       │        │   front       │
└───────────────┘        └───────────────┘
```

---

### Step 9: BOLD-to-T1w Registration

**What it does:** Aligns functional data to anatomical data.

**Why it matters:**
- BOLD has low resolution (~3mm)
- T1w has high resolution (~1mm)
- Need to know where activity is anatomically

**Algorithm:** FSL FLIRT + FreeSurfer bbregister

---

### Step 10: Confound Estimation

**What it does:** Extracts nuisance signals for regression during analysis.

**This is CRUCIAL for analysis quality!**

See [The Confounds File](#the-confounds-file) section for details.

---

## Output Files

### Complete Output Structure

```
derivatives/fmriprep/
│
├── dataset_description.json          # BIDS derivatives metadata
│
├── sub-001.html                      # ◄─── INTERACTIVE QC REPORT
│
├── sub-001/
│   │
│   ├── anat/                         # ANATOMICAL OUTPUTS
│   │   │
│   │   ├── sub-001_desc-brain_mask.nii.gz           # Brain mask
│   │   ├── sub-001_desc-preproc_T1w.nii.gz          # Preprocessed T1 (native)
│   │   ├── sub-001_space-MNI152NLin2009cAsym_desc-preproc_T1w.nii.gz  # T1 in MNI
│   │   │
│   │   ├── sub-001_label-CSF_probseg.nii.gz         # CSF probability
│   │   ├── sub-001_label-GM_probseg.nii.gz          # Gray matter probability
│   │   ├── sub-001_label-WM_probseg.nii.gz          # White matter probability
│   │   ├── sub-001_dseg.nii.gz                      # Discrete segmentation
│   │   │
│   │   ├── sub-001_from-T1w_to-MNI152NLin2009cAsym_mode-image_xfm.h5
│   │   └── sub-001_from-MNI152NLin2009cAsym_to-T1w_mode-image_xfm.h5
│   │
│   ├── func/                         # FUNCTIONAL OUTPUTS
│   │   │
│   │   │  # ◄─── THE MAIN OUTPUT (use this for analysis!)
│   │   ├── sub-001_task-rest_space-MNI152NLin2009cAsym_desc-preproc_bold.nii.gz
│   │   │
│   │   │  # ◄─── CONFOUNDS (for regression)
│   │   ├── sub-001_task-rest_desc-confounds_timeseries.tsv
│   │   ├── sub-001_task-rest_desc-confounds_timeseries.json
│   │   │
│   │   ├── sub-001_task-rest_space-MNI152NLin2009cAsym_desc-brain_mask.nii.gz
│   │   ├── sub-001_task-rest_space-MNI152NLin2009cAsym_boldref.nii.gz
│   │   │
│   │   ├── sub-001_task-rest_from-orig_to-T1w_mode-image_xfm.txt
│   │   └── sub-001_task-rest_from-T1w_to-orig_mode-image_xfm.txt
│   │
│   └── figures/                      # QC FIGURES
│       ├── sub-001_desc-about_T1w.html
│       ├── sub-001_dseg.svg
│       ├── sub-001_task-rest_desc-carpetplot_bold.svg
│       ├── sub-001_task-rest_desc-confoundcorr_bold.svg
│       └── sub-001_task-rest_desc-sdc_bold.svg
│
└── logs/
    └── CITATION.md                   # How to cite fMRIPrep
```

### Key Output Files

#### 1. Preprocessed BOLD (Main Output)

```
sub-001_task-rest_space-MNI152NLin2009cAsym_desc-preproc_bold.nii.gz
│        │         │                        │
│        │         │                        └── "preproc" = preprocessed
│        │         └── In MNI standard space
│        └── Task name from BIDS
└── Subject ID
```

**This is what you use for analysis!** It's:
- ✓ Motion corrected
- ✓ Slice-timing corrected
- ✓ Distortion corrected (if fieldmaps)
- ✓ Aligned to MNI template
- ✗ NOT smoothed (you do this)
- ✗ NOT filtered (you do this)

---

## The Confounds File

### What's in `desc-confounds_timeseries.tsv`

This file has **one row per volume** (timepoint) with columns for each confound:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CONFOUNDS FILE CONTENTS                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   MOTION (24 parameters typically used):                                    │
│   ├── trans_x, trans_y, trans_z     - Translation in mm                   │
│   ├── rot_x, rot_y, rot_z           - Rotation in radians                 │
│   ├── *_derivative1                  - Velocity (first derivative)        │
│   └── *_power2                       - Squared terms                       │
│                                                                             │
│   QUALITY METRICS:                                                          │
│   ├── framewise_displacement         - Total motion (should be < 0.5mm)   │
│   └── dvars                          - Signal intensity changes            │
│                                                                             │
│   PHYSIOLOGICAL NOISE (aCompCor):                                           │
│   └── a_comp_cor_00 to _05           - PCA components from WM/CSF         │
│                                                                             │
│   GLOBAL SIGNALS:                                                           │
│   ├── global_signal                  - Mean across brain                   │
│   ├── csf                            - Mean in CSF                         │
│   └── white_matter                   - Mean in WM                          │
│                                                                             │
│   DRIFT CORRECTION:                                                         │
│   └── cosine00, cosine01, ...        - Low-frequency drift                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Example Confounds (first 5 rows)

```
framewise_displacement  dvars    trans_x   trans_y   trans_z   rot_x    rot_y    rot_z
n/a                     n/a      0.0000    0.0000    0.0000    0.0000   0.0000   0.0000
0.023                   45.23    0.0123   -0.0045    0.0089    0.0002   0.0001   0.0003
0.046                   52.89    0.0345   -0.0123    0.0156    0.0004   0.0002   0.0005
0.012                   38.45    0.0289   -0.0098    0.0134    0.0003   0.0001   0.0004
0.089                   61.23    0.0567   -0.0234    0.0289    0.0007   0.0003   0.0006
```

### Using Confounds in Analysis

```python
# Example in Python (nilearn):
import pandas as pd
from nilearn.glm.first_level import FirstLevelModel

# Load confounds
confounds = pd.read_csv(
    'sub-001_task-rest_desc-confounds_timeseries.tsv', 
    sep='\t'
)

# Select which confounds to use (common choice)
confound_columns = [
    'trans_x', 'trans_y', 'trans_z',
    'rot_x', 'rot_y', 'rot_z',
    'a_comp_cor_00', 'a_comp_cor_01', 'a_comp_cor_02',
    'a_comp_cor_03', 'a_comp_cor_04', 'a_comp_cor_05'
]

# Handle NaN in first row
confounds_selected = confounds[confound_columns].fillna(0)

# Include in your model
model = FirstLevelModel(
    t_r=2.0,
    confounds=confounds_selected
)
```

---

## Quality Control Reports

### The HTML Report (`sub-001.html`)

**Open this in a browser!** It contains:

1. **Summary** — Processing overview, warnings, errors
2. **Anatomical** — Brain extraction, segmentation, normalization
3. **Functional** — Registration, distortion correction, carpet plot

### The Carpet Plot

The **carpet plot** is the most important QC visualization:

```
┌─────────────────────────────────────────────────────────────────────┐
│  CARPET PLOT                                                        │
│                                                                     │
│  Y-axis: All voxels (grouped by tissue type)                       │
│  X-axis: Time (volumes)                                            │
│  Color: Signal intensity                                            │
│                                                                     │
│  Cortex    ▓▓▓▓▓▓▓▓▓▓▒▒▓▓▓▓▓▓▓▓▓▓▓▓░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓    │
│            ▓▓▓▓▓▓▓▓▓▓▒▒▓▓▓▓▓▓▓▓▓▓▓▓░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓    │
│            ▓▓▓▓▓▓▓▓▓▓▒▒▓▓▓▓▓▓▓▓▓▓▓▓░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓    │
│  Subcort   ░░░░░░░░░░▓▓░░░░░░░░░░░░▓▓░░░░░░░░░░░░░░░░░░░░░░░░░    │
│  WM        ░░░░░░░░░░▓▓░░░░░░░░░░░░▓▓░░░░░░░░░░░░░░░░░░░░░░░░░    │
│  CSF       ░░░░░░░░░░▓▓░░░░░░░░░░░░▓▓░░░░░░░░░░░░░░░░░░░░░░░░░    │
│                      ↑              ↑                               │
│                   Motion!        Motion!                            │
│                                                                     │
│  Motion    ──────────╱╲────────────╱╲───────────────────────────   │
│  params                                                             │
│                                                                     │
│  FD        ──────────│────────────│─────────────────────────────   │
│                      ↑            ↑                                 │
│                   Bad volumes (FD > 0.5mm)                          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**What to look for:**
| Pattern | Meaning | Action |
|---------|---------|--------|
| Vertical stripes | Motion artifact | Consider excluding subject |
| Smooth horizontal bands | Good data | Proceed with analysis |
| FD spikes > 0.5mm | High motion volumes | Censor or scrub |
| Gradual intensity drift | Scanner drift | Included in confounds |

---

## What fMRIPrep Does NOT Do

fMRIPrep intentionally leaves some steps to you:

| Step | Why Left Out | Your Responsibility |
|------|--------------|---------------------|
| **Smoothing** | Depends on analysis | 6mm for group, none for MVPA |
| **Temporal filtering** | Task vs resting-state differ | High-pass typically 128s |
| **Nuisance regression** | Many valid strategies | Use confounds file |
| **Statistical analysis** | Not preprocessing | Your analysis pipeline |

### Recommended Next Steps

```python
from nilearn import image
from nilearn.glm.first_level import FirstLevelModel

# 1. Load preprocessed BOLD
bold = image.load_img(
    'sub-001_task-rest_space-MNI152NLin2009cAsym_desc-preproc_bold.nii.gz'
)

# 2. Smooth (optional, depends on analysis)
smoothed = image.smooth_img(bold, fwhm=6)  # 6mm FWHM

# 3. High-pass filter and nuisance regression happen in GLM
model = FirstLevelModel(
    t_r=2.0,
    high_pass=1/128,  # 128 second cutoff
    smoothing_fwhm=6
)

# 4. Fit your model
model.fit(run_imgs=bold, confounds=confounds_selected)
```

---

## Configuration Options

### Current Settings (from run_fmriprep.py)

```python
docker_cmd = [
    "docker", "run", "-t", "--rm",
    "-v", f"{bids_dir}:/data:ro",
    "-v", f"{output_dir}:/out",
    "-v", f"{license_path}:/opt/freesurfer/license.txt:ro",
    "nipreps/fmriprep:latest",
    "/data", "/out",
    "participant",
    "--participant-label", participant_label,
    "--fs-no-reconall",       # Skip FreeSurfer (saves 6+ hours)
    "--skip-bids-validation", # We validated already
    "--nthreads", "4",        # CPU threads
    "--omp-nthreads", "4",    # OpenMP threads
    "--mem_mb", "8000"        # Memory limit (8GB)
]
```

### Useful Additional Options

| Option | Description | Example |
|--------|-------------|---------|
| `--output-spaces` | Output resolution | `MNI152NLin2009cAsym:res-2` |
| `--dummy-scans` | Remove first N volumes | `--dummy-scans 4` |
| `--use-aroma` | ICA-AROMA denoising | `--use-aroma` |
| `--ignore` | Skip steps | `--ignore fieldmaps` |
| `--fd-spike-threshold` | Motion threshold | `--fd-spike-threshold 0.5` |

---

## Troubleshooting

### Common Issues

#### "Docker is not running"
```
Solution:
  1. Start Docker Desktop
  2. Wait for it to fully initialize
  3. Try again
```

#### "FreeSurfer license not found"
```
Solution:
  1. Get a free license from https://surfer.nmr.mgh.harvard.edu/registration.html
  2. Save as .freesurfer_license.txt in project root
```

#### "Out of memory"
```
Solution:
  1. Increase Docker memory (Docker Desktop → Settings → Resources)
  2. Reduce --nthreads
  3. Process fewer subjects at once
```

#### "No output produced"
```
Solution:
  1. Check BIDS structure is valid
  2. Look at logs in derivatives/fmriprep/logs/
  3. Check HTML report for errors
```

### Checking Processing Time

Typical processing times:
| Step | Time per Subject |
|------|------------------|
| Without FreeSurfer | 4-8 hours |
| With FreeSurfer | 12-24 hours |
| Per additional task | +1-2 hours |

---

## Quick Reference

### Manual Command

```bash
docker run -t --rm \
  -v /path/to/bids:/data:ro \
  -v /path/to/output:/out \
  -v /path/to/license.txt:/opt/freesurfer/license.txt:ro \
  nipreps/fmriprep:latest \
  /data /out participant \
  --participant-label 001 \
  --fs-no-reconall \
  --nthreads 4 \
  --mem_mb 8000
```

### Useful Links

- [fMRIPrep Documentation](https://fmriprep.org/en/stable/)
- [fMRIPrep Paper](https://doi.org/10.1038/s41592-018-0235-4)
- [Confounds Documentation](https://fmriprep.org/en/stable/outputs.html#confounds)
- [Output Spaces](https://fmriprep.org/en/stable/spaces.html)

### Citation

If you use fMRIPrep, cite:
> Esteban O, Markiewicz CJ, Blair RW, et al. fMRIPrep: a robust preprocessing 
> pipeline for functional MRI. Nat Methods. 2019;16(1):111-116.

---

*This guide is part of the fMRI Preprocessing Assistant project.*

