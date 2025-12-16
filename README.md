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

1.  **Clone the Project**:
    ```bash
    git clone https://github.com/omermili2/fmri-prep.git
    cd fmri-prep
    ```
2.  **Run Setup Script**:
    ```bash
    ./scripts/setup_env.sh
    ```
    This script will check for prerequisites (Python, Docker, dcm2niix), create the virtual environment, and install libraries.
3.  **Add FreeSurfer License**:
    Place your `license.txt` file in the project root and rename it to `.freesurfer_license.txt`.

## How to Run (GUI)

The easiest way to use the tool is via the graphical interface:

```bash
source venv/bin/activate
python gui_app.py
```

1.  **Raw Data Folder:** Select the *parent* folder containing your subject directories (e.g., `MyStudyData/` which contains `110/`, `111/`, etc.).
2.  **Output Folder:** Select where you want the results.
3.  **Select Steps:** Check "Convert to BIDS" and/or "Run fMRIPrep".
4.  **Start:** Click the button.

## Master Pipeline (CLI)

For advanced users or server automation:

```bash
./scripts/run_pipeline.py \
  --input <path_to_raw_dicoms_root> \
  --output_dir <path_to_output> \
  --session <session_id>
```

**Options:**
- `--dry-run`: Print commands without executing (safe test).
- `--skip-bids`: Skip the conversion step.
- `--skip-fmriprep`: Skip the preprocessing step.

### Example:

```bash
./scripts/run_pipeline.py \
  --input /data/MyRawScans \
  --output_dir /data/Processed \
  --session 01
```
