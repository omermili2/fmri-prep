# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

fMRI Preprocessing Assistant — a cross-platform GUI/CLI tool that converts raw DICOM neuroimaging data to BIDS format, runs fMRIPrep preprocessing via Docker, and performs multi-layer quality control. Built for research teams conducting fMRI studies.

## Commands

### Setup
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run
```bash
python run.py                  # GUI (auto-detects display, falls back to CLI)
python run.py --cli --help     # Force CLI mode
python -m src.orchestrator --input /path/to/dicom --output_dir /path/to/output
```

### Test
```bash
pytest                         # Run all tests
pytest test/test_pipeline.py   # Single test file
pytest -k "test_name"          # Single test by name
```

### Type Checking
```bash
pyright                        # Uses pyrightconfig.json (basic mode, Python 3.9)
```

## Architecture

### Entry Points
- `run.py` — Smart launcher: GUI (CustomTkinter) if display available, CLI otherwise. Handles SSH/X11 detection.
- `src/orchestrator.py` — CLI entry point and pipeline coordinator. **Start here to understand the code.**

### Pipeline Flow (sequential stages)
1. **BIDS Conversion** (`src/bids/converter.py`) — dcm2niix converts DICOM→NIfTI, parallelized per subject
2. **Layer 1: BIDS QC** (`src/qc/checker.py`) — Validates immediately after each subject's conversion (missing scans, truncated runs, parameter drift)
3. **Layer 2: MRIQC** (`src/fmriprep/mriqc_runner.py`) — Optional (`--run-mriqc`), Docker-based image quality metrics (SNR, tSNR, CJV, FD, GSR)
4. **fMRIPrep** (`src/fmriprep/runner.py`) — Docker-based preprocessing, parallel per subject
5. **Layer 3: Motion Analysis** (`src/qc/motion_parser.py`) — Reads fMRIPrep confounds TSV after all subjects finish
6. **Layer 4: Connectivity QC** (`src/qc/volume_censoring.py` + `src/qc/connectivity_qc.py`) — Optional (`--connectivity-qc`), QC-FC and DM-FC metrics per Parkes et al.
7. **Layer 5: HTML Report** (`src/reporting/html_report.py`) — Always final step, self-contained HTML aggregating all findings

### Module Responsibilities
- `src/core/` — Subject/session discovery (`discovery.py`), thread-safe progress tracking (`progress.py`), encoding utilities (`utils.py`)
- `src/bids/` — BIDS conversion (`converter.py`) and output file counting (`analyzer.py`)
- `src/fmriprep/` — Docker runners for fMRIPrep and MRIQC; handles dynamic image pull with local tar fallback
- `src/qc/` — All quality control layers; `connectivity_thresholds.py` holds literature-derived threshold constants
- `src/reporting/` — HTML report (`html_report.py`) and text conversion report (`report.py`)
- `src/gui/app.py` — CustomTkinter GUI with console log widget

### Key Patterns
- **Parallelization**: `ThreadPoolExecutor` processes subjects/sessions concurrently. Thread-safe output via `safe_print()` with `_print_lock`.
- **Progress tracking**: `ProgressTracker` emits `[PROGRESS:...]` markers that the GUI parses to update its progress bar.
- **fMRIPrep options**: Passed as base64-encoded JSON for cross-platform compatibility.
- **Dual import style**: `orchestrator.py` uses try/except for both package (`from .core...`) and script (`from core...`) imports.
- **Docker integration**: Both fMRIPrep and MRIQC mount BIDS/derivatives dirs into containers with cross-platform path handling. Fallback to local `.tar` images if online pull fails.

## Configuration
- `pyproject.toml` — Package metadata, pytest config (`testpaths = ["test"]`, `pythonpath = ["src"]`), Pyright settings
- `pyrightconfig.json` — Type checking (basic mode, Python 3.9, includes `src` and `test`)
- `tools/` — Bundled `dcm2niix` binary for BIDS conversion; also holds `.freesurfer_license.txt` (not committed)
