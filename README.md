# fMRI Processing Pipeline (BIDS + fMRIPrep)

This project provides an automated pipeline to convert raw DICOM MRI scans into the BIDS standard and preprocess them using fMRIPrep. It is designed to be modular and user-friendly, eventually allowing non-technical users to process data with minimal configuration.

## Project Structure

- `sourcedata/`: Raw, disorganized DICOM data (compressed).
- `test_data/`: Decompressed DICOM data used for testing the pipeline.
- `bids_output/`: The final, organized BIDS dataset.
- `scripts/`: Helper scripts for data setup and processing.
- `dcm2bids_config.json`: Configuration file mapping DICOM series to BIDS filenames.
- `requirements.txt`: Python dependencies.

## Prerequisites

1.  **Python 3.12+** (Installed via Homebrew or standard installer)
2.  **dcm2niix** (DICOM to NIfTI converter)
    - Install: `brew install dcm2niix` (on macOS)
3.  **Docker Desktop** (Required for fMRIPrep)

## Setup

1.  **Create a Virtual Environment** (Isolates dependencies):
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Prepare Test Data**:
    (Only needed if starting from compressed source data)
    ```bash
    python scripts/setup_test_data.py
    ```

## Migration & Portable Usage

To move this project to another computer (e.g., a high-performance server):

1.  **Copy the Project**: Transfer this entire folder.
2.  **Install Docker & dcm2niix**: Ensure these system tools are installed on the new machine.
3.  **Run Setup Script**:
    ```bash
    ./scripts/setup_env.sh
    ```
    This script will check for prerequisites, create the virtual environment, and install Python libraries.
4.  **Add FreeSurfer License**:
    Place your `license.txt` file in the project root and rename it to `.freesurfer_license.txt`.

## Master Pipeline (CLI)

Instead of running steps individually, you can use the master script to orchestrate the entire flow:

```bash
./scripts/run_pipeline.py \
  --input <path_to_raw_dicoms> \
  --subject <subject_id> \
  --session <session_id>
```

**Options:**
- `--dry-run`: Print commands without executing (safe test).
- `--skip-bids`: Skip the conversion step (if data is already in BIDS).
- `--skip-fmriprep`: Skip the preprocessing step.

### Example:

```bash
./scripts/run_pipeline.py \
  --input test_data/sourcedata/sub-01/scans \
  --subject 01 \
  --session 01
```
## Manual Steps

If you prefer to run steps manually:

### Phase 2: BIDS Conversion

We use `dcm2bids` to convert DICOMs. The process involves:

1.  **Inspection**: `dcm2bids_helper` scans the raw data to identify scan types (T1w, functional tasks, etc.).
2.  **Configuration**: `dcm2bids_config.json` defines rules to rename scans (e.g., "If name contains 'T1w', save as 'sub-01_T1w'").
3.  **Conversion**: The tool reads the config and organizes the files.

### Running the Conversion

To convert the test data for Subject 01, Session 01:

```bash
dcm2bids -d test_data/sourcedata/sub-01/scans \
         -p 01 \
         -s 01 \
         -c dcm2bids_config.json \
         -o bids_output
```

## Phase 3: fMRIPrep Preprocessing

To run fMRIPrep on the BIDS data:

```bash
./scripts/run_fmriprep.sh <bids_dir> <output_dir> <participant_label>
```

Example:
```bash
./scripts/run_fmriprep.sh bids_output derivatives 01
```

