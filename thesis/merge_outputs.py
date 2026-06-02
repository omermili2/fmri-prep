import shutil
import os
from pathlib import Path

def merge_connectivity_data(source_output_dirs: list, master_dir: str):
    """
    Copies subject connectivity data from multiple fMRIPrep output folders
    into a single master directory for batch analysis.
    """
    master_path = Path(master_dir) / "derivatives" / "connectivity"
    master_path.mkdir(parents=True, exist_ok=True)
    
    print(f"Master directory initialized at: {master_path}")
    
    for source_dir in source_output_dirs:
        source_path = Path(source_dir) / "derivatives" / "connectivity"
        
        if not source_path.exists():
            print(f"Warning: Skipping {source_dir} (No connectivity derivatives found)")
            continue
            
        print(f"Scanning {source_dir}...")
        
        # Find all subject folders in the source
        for sub_dir in source_path.glob("sub-*"):
            dest_sub_path = master_path / sub_dir.name
            
            if dest_sub_path.exists():
                print(f"  [INFO] {sub_dir.name} already exists in master. Merging sessions...")
            
            # Copy the subject folder (and all sessions/files) to the master
            # dirs_exist_ok=True allows us to merge sessions if the subject folder already exists
            try:
                shutil.copytree(sub_dir, dest_sub_path, dirs_exist_ok=True)
                print(f"  [SUCCESS] Merged {sub_dir.name}")
            except Exception as e:
                print(f"  [ERROR] Failed to copy {sub_dir.name}: {e}")

    print("\nMerge Complete!")
    print(f"You can now point extract_metrics.py to: {master_path}")

if __name__ == "__main__":
    # --- CONFIGURATION ---
    # List all your output folders here
    SOURCE_FOLDERS = [
        "../output_20260507_192526",
        # "../output_JUNE_01",
        # "../output_JUNE_05",
    ]
    
    # This is where all subjects will be consolidated
    MASTER_DESTINATION = "./master_thesis_data"
    
    merge_connectivity_data(SOURCE_FOLDERS, MASTER_DESTINATION)
