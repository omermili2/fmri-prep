import os
import gzip
import shutil
from pathlib import Path

def setup_data():
    # Define paths
    project_root = Path(__file__).parent.parent
    source_dir = project_root / "sourcedata" / "0219191_mystudy-0219-1114" / "dcm"
    target_dir = project_root / "dummy_data" / "subjects" / "sub-01" / "scans"

    print(f"Source: {source_dir}")
    print(f"Target: {target_dir}")

    if not source_dir.exists():
        print("Source directory not found!")
        return

    # Create target directory
    target_dir.mkdir(parents=True, exist_ok=True)

    # Process files
    files = list(source_dir.glob("*.dcm.gz"))
    print(f"Found {len(files)} .dcm.gz files.")

    for i, gz_path in enumerate(files):
        # Define output path (remove .gz)
        output_path = target_dir / gz_path.stem
        
        with gzip.open(gz_path, 'rb') as f_in:
            with open(output_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        if (i + 1) % 50 == 0:
            print(f"Processed {i + 1} files...")

    print("Data setup complete.")

if __name__ == "__main__":
    setup_data()

