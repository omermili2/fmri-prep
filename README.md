# fMRI Preprocessing Assistant

A cross-platform GUI application for converting DICOM neuroimaging data to BIDS format and running fMRIPrep preprocessing.

## Quick Start

### 1. Install Dependencies

```bash
# Create virtual environment
python -m venv venv

# Activate
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install
pip install -r requirements.txt
```

### 2. Run the Application

```bash
python run.py
```

### 3. Use the GUI

1. **Select Source Folder** — Your DICOM data (organized by subject/session)
2. **Select Output Folder** — Where to save results
3. **Click a button:**
   - 🟢 **Run BIDS Conversion** — Convert DICOM → BIDS only
   - 🔵 **Run Full Pipeline** — BIDS + fMRIPrep preprocessing

---

## Project Structure

```
fMRI_Masters/
├── run.py                  # Entry point - run this!
├── src/                    # Source code
│   ├── gui_app.py          # GUI application
│   ├── run_pipeline.py     # BIDS conversion pipeline
│   └── run_fmriprep.py     # fMRIPrep runner
├── config/                 # Configuration
│   └── dcm2bids_config.json
├── docs/                   # Documentation
│   ├── BIDS_CONVERSION_GUIDE.md
│   ├── FMRIPREP_GUIDE.md
│   └── FREESURFER_LICENSE.md
├── tools/                  # External tools (dcm2niix)
├── scripts/                # Setup scripts
└── thesis/                 # Thesis documents
```

---

## Requirements

| Requirement | For |
|-------------|-----|
| Python 3.10+ | Core application |
| Docker Desktop | fMRIPrep only |
| [FreeSurfer License](https://surfer.nmr.mgh.harvard.edu/registration.html) | fMRIPrep only (free) |

---

## Documentation

| Guide | Description |
|-------|-------------|
| [BIDS Conversion Guide](docs/BIDS_CONVERSION_GUIDE.md) | Input format, conversion process, output structure, configuration |
| [fMRIPrep Guide](docs/FMRIPREP_GUIDE.md) | Preprocessing steps, output files, quality control, confounds |

---

## Command Line Usage

```bash
# BIDS conversion only
python src/run_pipeline.py --input /path/to/dicom --output_dir /path/to/output --skip-fmriprep

# Full pipeline (BIDS + fMRIPrep)
python src/run_pipeline.py --input /path/to/dicom --output_dir /path/to/output
```

---

## License

MIT License

## References

- [BIDS Specification](https://bids-specification.readthedocs.io/)
- [dcm2bids](https://unfmontreal.github.io/Dcm2Bids/)
- [fMRIPrep](https://fmriprep.org/)
