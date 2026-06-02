import os
import pandas as pd
from pathlib import Path
from utils import load_connectivity_data, get_network_indices, calculate_segregation

def main():
    # Path to your consolidated master connectivity data
    base_dir = Path("master_thesis_data/derivatives/connectivity")
    output_file = Path("thesis_dataset.csv")

    if not base_dir.exists():
        print(f"Error: {base_dir} not found. Please update the path in extract_metrics.py")
        return

    data_rows = []
    
    # Networks of interest for the thesis
    NET_A = "SalVentAttn" # Salience Network
    NET_B = "Default"     # Default Mode Network

    print(f"Scanning {base_dir} for connectivity data...")

    # Iterate through subject folders
    for sub_dir in sorted(base_dir.glob("sub-*")):
        sub_id = sub_dir.name
        
        # Iterate through session folders
        for ses_dir in sorted(sub_dir.glob("ses-*")):
            ses_id = ses_dir.name
            
            # Find all connectivity files in this session
            conn_files = list(ses_dir.glob("*_connectivity.npy"))
            
            for conn_path in conn_files:
                # Extract task name from filename
                task = conn_path.name.split("_task-")[1].split("_connectivity")[0]
                
                try:
                    matrix, labels = load_connectivity_data(sub_dir, ses_id, task)
                    networks = get_network_indices(labels)
                    
                    # Calculate our thesis metrics
                    metrics = calculate_segregation(matrix, networks, NET_A, NET_B)
                    
                    # Add metadata
                    row = {
                        "subject": sub_id,
                        "session": ses_id,
                        "task": task
                    }
                    row.update(metrics)
                    data_rows.append(row)
                    print(f"  Processed {sub_id} {ses_id} {task}")
                    
                except Exception as e:
                    print(f"  Failed {sub_id} {ses_id} {task}: {e}")

    if data_rows:
        df = pd.DataFrame(data_rows)
        df.to_csv(output_file, index=False)
        print(f"\nSuccess! Extracted metrics for {len(df)} runs to {output_file}")
    else:
        print("\nNo data found to extract.")

if __name__ == "__main__":
    main()
