# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

fMRI Preprocessing Assistant — a cross-platform GUI/CLI tool that converts raw DICOM neuroimaging data to BIDS format, runs MRIQC image quality assessment, runs fMRIPrep preprocessing via Docker, and performs multi-layer quality control. Built for research teams conducting fMRI studies.

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

### Pipeline Flow (sequential phases)
1. **Phase 1: BIDS Conversion** (`src/bids/converter.py`) — dcm2niix converts DICOM→NIfTI, parallelized per subject
2. **BIDS QC** (`src/qc/checker.py`) — Validates immediately after each subject's conversion (missing scans, truncated runs, parameter drift)
3. **Phase 2: MRIQC** (`src/mriqc/runner.py`) — Docker-based image quality metrics (SNR, tSNR, CJV, FD, GSR); parallel per session; generates early standalone report
4. **Phase 3: fMRIPrep** (`src/fmriprep/runner.py`) — Docker-based preprocessing, parallel per subject
5. **Motion Analysis** (`src/qc/motion_parser.py`) — Reads fMRIPrep confounds TSV after all subjects finish
6. **Connectivity QC** (`src/qc/volume_censoring.py` + `src/qc/connectivity_qc.py`) — Optional (`--connectivity-qc`), QC-FC and DM-FC metrics per Parkes et al.
7. **HTML Report** (`src/reporting/html_report.py`) — Always final step, self-contained HTML aggregating all findings

### Module Responsibilities
- `src/core/` — Subject/session discovery (`discovery.py`), thread-safe progress tracking (`progress.py`), encoding utilities (`utils.py`)
- `src/bids/` — BIDS conversion (`converter.py`) and output file counting (`analyzer.py`)
- `src/mriqc/` — MRIQC Docker runner (`runner.py`) and IQM metrics parser (`iqm_parser.py`); handles image pull with local tar fallback
- `src/fmriprep/` — fMRIPrep Docker runner; handles dynamic image pull with local tar fallback
- `src/qc/` — Quality control layers: BIDS validation (`checker.py`), motion analysis (`motion_parser.py`), connectivity QC (`connectivity_qc.py`, `volume_censoring.py`); `connectivity_thresholds.py` holds literature-derived threshold constants
- `src/reporting/` — HTML reports (`html_report.py`: full QC report + standalone MRIQC report) and text conversion report (`report.py`)
- `src/gui/app.py` — CustomTkinter GUI with console log widget

### Key Patterns
- **Parallelization**: `ThreadPoolExecutor` processes subjects/sessions concurrently. Thread-safe output via `safe_print()` with `_print_lock`.
- **Progress tracking**: `ProgressTracker` emits `[PROGRESS:...]` markers that the GUI parses to update its progress bar.
- **fMRIPrep options**: Passed as base64-encoded JSON for cross-platform compatibility.
- **QC threshold overrides**: Passed as base64-encoded JSON via `--qc-thresholds`. Each QC module (`iqm_parser`, `motion_parser`, `connectivity_thresholds`) has an `apply_overrides()` function that updates module-level globals before any QC code runs. The GUI builds the override dict from its editable threshold table.
- **Dual import style**: `orchestrator.py` uses try/except for both package (`from .core...`) and script (`from core...`) imports.
- **Docker integration**: Both fMRIPrep and MRIQC mount BIDS/derivatives dirs into containers with cross-platform path handling. Fallback to local `.tar` images if online pull fails.

## Configuration
- `pyproject.toml` — Package metadata, pytest config (`testpaths = ["test"]`, `pythonpath = ["src"]`), Pyright settings
- `pyrightconfig.json` — Type checking (basic mode, Python 3.9, includes `src` and `test`)
- `tools/` — Bundled `dcm2niix` binary for BIDS conversion; also holds `.freesurfer_license.txt` (not committed)
