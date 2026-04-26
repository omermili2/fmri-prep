# fMRI Preprocessing Assistant

A cross-platform GUI and CLI tool for converting DICOM neuroimaging data to BIDS format, running MRIQC image quality assessment, running fMRIPrep preprocessing, and automatically assessing data quality at multiple levels.

---

## Pipeline Overview

The pipeline runs in three main phases, each containing one or more quality-control steps.

```mermaid
flowchart TD
    A([Raw DICOM files\norganized by subject/session]) --> B

    subgraph PHASE1 ["Phase 1: BIDS Conversion  (per subject, parallel)"]
        B[dcm2niix\nDICOM → NIfTI + JSON]
        B --> C
        C["BIDS Quality Checks\nchecker.py\n• Missing T1w / BOLD\n• Truncated runs\n• Small/corrupt files\n• Parameter drift across subjects"]
    end

    subgraph PHASE2 ["Phase 2: MRIQC  (per session, parallel, via Docker)"]
        D["mriqc/runner.py\n• SNR / tSNR / CJV / FD / GSR\n• Per-subject visual HTML reports\n• Group-level outlier detection"]
        D --> D2["Early MRIQC Report\nmriqc_report.html\n→ available before fMRIPrep starts"]
    end

    C --> D
    C --> E

    subgraph PHASE3 ["Phase 3: fMRIPrep  (per subject, parallel, via Docker)"]
        E["runner.py\n• Motion correction\n• Slice-timing correction\n• Susceptibility distortion correction\n• Brain extraction & registration\n• ICA-AROMA denoising (optional)\n→ outputs confounds TSV + preprocessed BOLD"]
    end

    D2 --> F
    E --> F

    subgraph POST ["Post-processing  (after all subjects finish)"]
        F["Motion Analysis\nmotion_parser.py\n• Reads fMRIPrep confounds TSV\n• Mean FD per run\n• % high-motion frames\n• OK / WARNING / RESCAN flags"]
        F --> G
        G["Connectivity QC\n(optional: --connectivity-qc)\nvolume_censoring.py + connectivity_qc.py\n• % volumes censored at 0.2 mm / 0.5 mm FD\n• Usable scan time remaining\n• QC-FC: motion-connectivity correlation\n• DM-FC: distance-dependent artifacts"]
        G --> H
        H["HTML Report\nhtml_report.py\n→ qc_report.html"]
    end

    H --> I([Output folder\nqc_report.html\nconversion_report.txt\nsub-*/ses-*/ BIDS data\nderivatives/ fMRIPrep outputs\nderivatives/mriqc/ MRIQC reports])

    style PHASE1 fill:#e8f4e8,stroke:#4a8c4a
    style PHASE2 fill:#e8edf8,stroke:#4a6aac
    style PHASE3 fill:#f0e8f8,stroke:#7a4aac
    style POST fill:#fdf5e0,stroke:#ac8a4a
```

> **Early feedback:** When MRIQC finishes (Phase 2), a standalone `mriqc_report.html` is generated in the MRIQC output directory. The supervisor can review image quality immediately — without waiting for fMRIPrep to finish.

---

## Stage-by-Stage Explanation

### Phase 1: BIDS Conversion

#### BIDS Conversion
- **Tool:** `dcm2niix` (bundled in `tools/` or system-installed)
- **Input:** DICOM folders organized as `<subject>/<session>/`
- **Output:** NIfTI (`.nii.gz`) + sidecar JSON files in BIDS layout under `sub-<id>/ses-<id>/anat|func/`
- **Runs:** In parallel across all subjects

#### BIDS Quality Checks (`src/qc/checker.py`)
Runs **immediately after each subject's BIDS conversion**, before any further processing.

| Check | What it flags |
|---|---|
| Missing T1w | Session has no anatomical scan — fMRIPrep will fail |
| Missing BOLD | No functional data in session |
| Truncated BOLD run | Fewer timepoints than expected — scan may have been aborted |
| Small file | File size too small to be valid — possible corruption |
| Parameter drift | TR or field strength differs from the cohort median |

---

### Phase 2: MRIQC (`src/mriqc/runner.py`)
Runs **per session in parallel after BIDS conversion**, before fMRIPrep starts. Enabled by default; skip with `--skip-mriqc`.
Requires Docker. One-time image pull: `docker pull nipreps/mriqc:24.0.2`

MRIQC sessions are independent — each session's quality metrics are computed from that session's images alone. The pipeline automatically detects available Docker VM resources (CPU / RAM) and distributes them across parallel containers.

| Metric | Meaning | Red flag |
|---|---|---|
| **SNR / CNR** (T1w) | Structural signal quality | Very low — poor image quality |
| **CJV** (T1w) | Coefficient of joint variation | > 0.7 — motion or B1 artifact |
| **tSNR** (BOLD) | Temporal signal stability | < 30 — noisy data |
| **FD mean** (BOLD) | Average head motion per TR | > 0.5 mm — elevated motion |
| **GSR x/y** (BOLD) | EPI ghosting artifact | > 0.1 — check phase-encode direction |

After MRIQC completes, a **standalone MRIQC report** (`derivatives/mriqc/mriqc_report.html`) is generated automatically. This provides early feedback on image quality before the longer fMRIPrep step begins.

> Always open the visual HTML reports — the images tell the full story.

---

### Phase 3: fMRIPrep (`src/fmriprep/runner.py`)
The core preprocessing step. Runs **per subject via Docker**, in parallel.

Performs:
- Motion correction & slice-timing correction
- Susceptibility distortion correction (fieldmap-based)
- Brain extraction & MNI registration
- Confound time series extraction (motion params, WM/CSF signals, CompCor)

**Output:** `derivatives/fmriprep/sub-<id>/` containing preprocessed BOLD NIfTI files and `*_confounds_timeseries.tsv`.

---

### Post-processing

#### Motion Analysis (`src/qc/motion_parser.py`)
Runs **after all fMRIPrep jobs complete**. Reads the confounds TSV files fMRIPrep produces.

| Flag | Condition |
|---|---|
| OK | Mean FD < 0.5 mm and < 20% high-motion frames |
| WARNING | Mean FD 0.5–0.8 mm or 20–50% high-motion frames |
| RESCAN | Mean FD > 0.8 mm or > 50% high-motion frames |

#### Connectivity QC (`src/qc/volume_censoring.py` + `src/qc/connectivity_qc.py`) — *optional*
Runs **after motion analysis**, only with `--connectivity-qc` flag. Requires `nilearn` and `nibabel`.
Based on [Parkes et al. / PMC10977879](https://pmc.ncbi.nlm.nih.gov/articles/PMC10977879/).

| Sub-layer | Metric | What it means | Pass threshold |
|---|---|---|---|
| **4a** | % volumes censored | Timepoints removed at 0.2 mm FD | < 80% |
| **4a** | Usable scan time | Clean data remaining after scrubbing | >= 1 minute |
| **4b** | QC-FC | Correlation between motion and connectivity | < 0.1 (warn > 0.2) |
| **4b** | DM-FC | Distance-dependent motion artifact | near 0 (fail > 0.1) |

Result labels: **Ready** / **Marginal** / **Not Suitable**

#### HTML Report (`src/reporting/html_report.py`)
Always the **last step**. Aggregates all QC findings into a single self-contained HTML file.

Sections in the report:
1. Overall status banner (green / yellow / red)
2. Per-subject summary table
3. BIDS quality findings
4. MRIQC Image Quality Metrics (unless `--skip-mriqc` was used)
5. Motion analysis
6. Connectivity QC (if enabled)

---

## Output Structure

```
output_YYYYMMDD_HHMMSS/
├── sub-001/ses-01/              ← BIDS data (anat/, func/, etc.)
├── sub-002/ses-01/
├── ...
├── derivatives/
│   ├── fmriprep/
│   │   └── sub-001/            ← Preprocessed BOLD + confounds TSV files
│   └── mriqc/
│       ├── mriqc_report.html   ← Early MRIQC report (available before fMRIPrep)
│       ├── group_T1w.html
│       ├── group_bold.html
│       └── sub-001/anat/*.html
├── qc_report.html              ← Final QC report — open this in a browser
├── conversion_report.txt       ← Text summary of all pipeline steps
├── execution_logs/
│   ├── raw_execution_log.log   ← Full pipeline console output with timestamps
│   └── execution_logs_summary.txt ← Structured per-subject/session summary
└── fmriprep_debug.log          ← Detailed error log for failed fMRIPrep runs
```

---

## Quick Start

### 1. Run the GUI

```bash
python run.py
```

Dependencies are installed automatically on first run from `requirements.txt`. To install manually:

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Select folders and run

1. **Select Source Folder** — your DICOM data (organized by subject/session)
2. **Select Output Folder** — where to save results
3. (Optional) Expand **fMRIPrep Options** to configure preprocessing and anonymization
4. Click a button:
   - **BIDS Only** — DICOM to BIDS conversion only
   - **BIDS + MRIQC** — Conversion + image quality assessment (generates early MRIQC report)
   - **fMRIPrep Only** — Run fMRIPrep on existing BIDS data
   - **Connectivity QC Only** — Run connectivity analysis on existing fMRIPrep output
   - **Full Pipeline** — BIDS + MRIQC + fMRIPrep + all QC layers

> **Note:** Action buttons remain disabled until both Source and Output folders are selected (BIDS Only, BIDS + MRIQC, Full Pipeline), or until the Source folder contains the appropriate data (fMRIPrep Only requires BIDS NIfTI data; Connectivity QC requires fMRIPrep confounds output).

---

## Command Line Usage

```bash
# Full pipeline (BIDS + MRIQC + fMRIPrep + QC) — MRIQC runs by default
python -m src.orchestrator --input /path/to/dicom --output_dir /path/to/output

# BIDS + MRIQC only (skip fMRIPrep)
python -m src.orchestrator --input /path/to/dicom --output_dir /path/to/output --skip-fmriprep

# BIDS conversion only (skip fMRIPrep and MRIQC)
python -m src.orchestrator --input /path/to/dicom --output_dir /path/to/output --skip-fmriprep --skip-mriqc

# Full pipeline + connectivity QC (requires nilearn)
python -m src.orchestrator --input /path/to/dicom --output_dir /path/to/output --connectivity-qc

# Re-run QC only on an existing output folder (no reprocessing)
python -m src.orchestrator --qc-only --bids-folder /path/to/output_YYYYMMDD_HHMMSS

# With DICOM metadata anonymization
python -m src.orchestrator --input /path/to/dicom --output_dir /path/to/output --anonymize

# Long FreeSurfer recon-all run (adds ~6+ hours per subject)
python -m src.orchestrator --input /path/to/dicom --output_dir /path/to/output \
  --fmriprep-opts "$(python - << 'PY'
import base64, json
print(base64.b64encode(json.dumps({'fs_reconall': True}).encode()).decode())
PY
)"
```

---

## Requirements

| Requirement | Purpose |
|---|---|
| Python 3.10+ | Core application |
| `dcm2niix` | BIDS conversion (bundled in `tools/` or system-installed) |
| Docker Desktop | fMRIPrep and MRIQC (both run in containers) |
| [FreeSurfer License](https://surfer.nmr.mgh.harvard.edu/registration.html) | Required by fMRIPrep (free registration) |
| `nilearn`, `nibabel` | Connectivity QC only (`pip install -r requirements.txt`) |

### Docker Desktop Performance

On macOS and Windows, Docker runs inside a VM with its own resource limits. The pipeline automatically detects Docker's available CPUs and RAM and will warn if they are low. For best performance:

1. Open **Docker Desktop > Settings > Resources**
2. Set **CPUs** to at least half your machine's cores (e.g. 8 of 14)
3. Set **Memory** to at least half your RAM (e.g. 48 GB of 96 GB)
4. Click **Apply & Restart**

---

## Project Structure

```
fMRI_Masters/
├── run.py                      # Entry point — auto-installs deps, launches GUI or CLI
├── src/
│   ├── orchestrator.py         # Pipeline coordinator — start here to understand the code
│   ├── gui/                    # GUI application (CustomTkinter)
│   ├── core/                   # Subject discovery, progress tracking, utilities
│   ├── bids/                   # BIDS conversion using dcm2niix
│   │   ├── converter.py        # DICOM → NIfTI conversion (parallel per subject)
│   │   └── analyzer.py         # Count output files by modality
│   ├── mriqc/                  # MRIQC image quality assessment (dedicated module)
│   │   ├── runner.py           # MRIQC Docker runner (parallel per session)
│   │   └── iqm_parser.py       # Parses MRIQC IQM JSON metrics & flags outliers
│   ├── fmriprep/               # fMRIPrep preprocessing
│   │   └── runner.py           # fMRIPrep Docker runner (parallel per subject)
│   ├── qc/                     # Quality control layers
│   │   ├── checker.py          # BIDS quality checks (missing scans, corruption)
│   │   ├── motion_parser.py    # Motion analysis from fMRIPrep confounds
│   │   ├── volume_censoring.py # Volume censoring analysis
│   │   ├── connectivity_qc.py  # QC-FC and DM-FC metrics
│   │   └── connectivity_thresholds.py  # Thresholds from literature
│   └── reporting/
│       ├── html_report.py      # HTML QC report generator (full + standalone MRIQC)
│       └── report.py           # Text conversion report
├── docs/
│   ├── BIDS_CONVERSION_GUIDE.md
│   └── FMRIPREP_GUIDE.md
├── test/                       # Test suite (66 tests)
└── tools/                      # Bundled dcm2niix binary
```

---

## Documentation

| Guide | Description |
|---|---|
| [BIDS Conversion Guide](docs/BIDS_CONVERSION_GUIDE.md) | Input folder format, conversion steps, output layout |
| [fMRIPrep Guide](docs/FMRIPREP_GUIDE.md) | Preprocessing steps, output files, confounds |

---

## License

MIT License

## References

- [BIDS Specification](https://bids-specification.readthedocs.io/)
- [dcm2niix](https://github.com/rordenlab/dcm2niix)
- [fMRIPrep](https://fmriprep.org/)
- [MRIQC](https://mriqc.readthedocs.io/)
- Parkes et al. (2018) — QC-FC and DM-FC metrics for connectivity studies
