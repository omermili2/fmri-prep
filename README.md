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
3. (Optional) Expand **fMRIPrep Options** to configure preprocessing:
   - By default, the pipeline runs a **short fMRIPrep** without FreeSurfer recon-all.
   - To enable the long surface pipeline, check the option  
     **"Enable LONG FreeSurfer recon-all (~6+ hours per subject)"** under *Processing Options*.
4. **Click a button:**
   - 🟢 **Run BIDS Conversion** — Convert DICOM → BIDS only
   - 🔵 **Run Full Pipeline** — BIDS + fMRIPrep preprocessing

---

## Project Structure

```
fMRI_Masters/
├── run.py                  # Entry point - run this!
├── src/                    # Source code
│   ├── orchestrator.py     # Main pipeline orchestrator
│   ├── gui/                # GUI application
│   ├── core/               # Discovery, progress, utilities
│   ├── bids/               # BIDS conversion (using dcm2niix)
│   ├── fmriprep/           # fMRIPrep runner
│   └── reporting/          # Report generation
├── docs/                   # Documentation
│   ├── BIDS_CONVERSION_GUIDE.md
│   └── FMRIPREP_GUIDE.md
├── test/                   # Test suite
└── tools/                  # Local dcm2niix binary
```

---

## Requirements

| Requirement | For |
|-------------|-----|
| Python 3.10+ | Core application |
| dcm2niix | BIDS conversion (included in tools/ or install separately) |
| Docker Desktop | fMRIPrep only |
| [FreeSurfer License](https://surfer.nmr.mgh.harvard.edu/registration.html) | fMRIPrep only (free) |

---

## Documentation

| Guide | Description |
|-------|-------------|
| [BIDS Conversion Guide](docs/BIDS_CONVERSION_GUIDE.md) | Input format, conversion process, output structure |
| [fMRIPrep Guide](docs/FMRIPREP_GUIDE.md) | Preprocessing steps, output files, quality control, confounds |

---

## Command Line Usage

```bash
# BIDS conversion only
python -m src.orchestrator --input /path/to/dicom --output_dir /path/to/output --skip-fmriprep

# Full pipeline (BIDS + fMRIPrep), default = SHORT run (no FreeSurfer recon-all)
python -m src.orchestrator --input /path/to/dicom --output_dir /path/to/output

# Explicitly request LONG run with FreeSurfer recon-all via options
python -m src.orchestrator --input /path/to/dicom --output_dir /path/to/output \
  --fmriprep-opts "$(python - << 'PY'
import base64, json
opts = {'fs_reconall': True}
print(base64.b64encode(json.dumps(opts).encode('utf-8')).decode('ascii'))
PY
)"

# With anonymization (removes patient info from metadata)
python -m src.orchestrator --input /path/to/dicom --output_dir /path/to/output --anonymize
```

---

## License

MIT License

## References

- [BIDS Specification](https://bids-specification.readthedocs.io/)
- [dcm2niix](https://github.com/rordenlab/dcm2niix)
- [fMRIPrep](https://fmriprep.org/)
