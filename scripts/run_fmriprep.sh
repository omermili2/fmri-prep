#!/bin/bash

# fMRIPrep Runner Script
# Usage: ./run_fmriprep.sh <bids_dir> <output_dir> <participant_label> [freesurfer_license_path]

# Parse arguments
BIDS_DIR=$(realpath "$1")
OUTPUT_DIR=$(realpath "$2")
PARTICIPANT_LABEL="$3"
LICENSE_PATH="${4:-$(pwd)/.freesurfer_license.txt}" 

# Handle the case where the 4th arg is --dry-run (if license path is omitted)
if [ "$LICENSE_PATH" == "--dry-run" ]; then
   LICENSE_PATH="$(pwd)/.freesurfer_license.txt"
fi

# Check for --dry-run flag in any argument position
DRY_RUN=false
for arg in "$@"; do
  if [ "$arg" == "--dry-run" ]; then
    DRY_RUN=true
    break
  fi
done

# Check if Docker is running (unless dry-run)
if [ "$DRY_RUN" = false ]; then
    if ! docker info > /dev/null 2>&1; then
      echo "Error: Docker is not running. Please start Docker Desktop."
      exit 1
    fi
fi

# Check arguments
if [ -z "$BIDS_DIR" ] || [ -z "$OUTPUT_DIR" ] || [ -z "$PARTICIPANT_LABEL" ]; then
  echo "Usage: ./run_fmriprep.sh <bids_dir> <output_dir> <participant_label> [freesurfer_license_path] [--dry-run]"
  exit 1
fi

# Create output directory if it doesn't exist
mkdir -p "$OUTPUT_DIR"

echo "Starting fMRIPrep for participant: $PARTICIPANT_LABEL"
echo "BIDS Directory: $BIDS_DIR"
echo "Output Directory: $OUTPUT_DIR"

# Build the Docker command
CMD="docker run -ti --rm \
  -v \"$BIDS_DIR\":/data:ro \
  -v \"$OUTPUT_DIR\":/out \
  -v \"$LICENSE_PATH\":/opt/freesurfer/license.txt:ro \
  nipreps/fmriprep:latest \
  /data /out \
  participant \
  --participant-label \"$PARTICIPANT_LABEL\" \
  --fs-no-reconall \
  --skip-bids-validation \
  --nthreads 4 \
  --omp-nthreads 4 \
  --mem_mb 8000"

# Check for --dry-run flag in any argument position
for arg in "$@"; do
  if [ "$arg" == "--dry-run" ]; then
    echo ""
    echo "--- DRY RUN MODE ---"
    echo "The following command would be executed:"
    echo ""
    echo "$CMD"
    echo ""
    exit 0
  fi
done

# Run the command
eval $CMD

