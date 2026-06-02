import os
import pandas as pd
import numpy as np
from pathlib import Path
from utils import calculate_segregation, get_network_indices

def extract_advanced_metrics():
    """
    Specifically processes the 'Timeseries Data' folder with Schaefer 400 + Tian atlases.
    Compares 'anatomical' and 'global' denoising strategies.
    """
    base_timeseries_dir = Path("master_thesis_data/Timeseries Data")
    output_file = Path("thesis_dataset_advanced.csv")
    
    if not base_timeseries_dir.exists():
        print(f"Error: {base_timeseries_dir} not found.")
        return

    data_rows = []
    strategies = ["anatomical", "global"]
    
    # Networks of interest
    NET_A = "SalVentAttn"
    NET_B = "Default"

    for strategy in strategies:
        strat_dir = base_timeseries_dir / strategy
        if not strat_dir.exists():
            continue
            
        print(f"Processing strategy: {strategy}...")
        
        # Find all schaefer400 files
        schaefer_files = sorted(strat_dir.glob("*_schaefer400_ts.csv"))
        
        for schaefer_path in schaefer_files:
            # Parse filename: sub-XXX_ses-MRI1_task-rest_run-1_schaefer400_ts.csv
            filename = schaefer_path.name
            parts = filename.split("_")
            sub_id = parts[0]
            ses_id = parts[1]
            task = parts[2].replace("task-", "")
            
            # Find matching tian file
            tian_filename = filename.replace("schaefer400", "tian_s2")
            tian_path = strat_dir / tian_filename
            
            if not tian_path.exists():
                print(f"  Warning: Missing subcortical data for {sub_id} {ses_id}")
                continue
                
            try:
                # 1. Load timeseries
                df_cortical = pd.read_csv(schaefer_path)
                df_subcortical = pd.read_csv(tian_path)
                
                # 2. Concatenate (Column-wise)
                df_combined = pd.concat([df_cortical, df_subcortical], axis=1)
                
                # 3. Calculate Correlation Matrix
                matrix = df_combined.corr().values
                labels = df_combined.columns.tolist()
                
                # 4. Get Network Indices
                # (Re-using logic: Schaefer uses '7Networks_HEMI_NET_...', Tian uses 'Tian_...')
                networks = get_network_indices(labels)
                
                # 5. Calculate Metrics
                metrics = calculate_segregation(matrix, networks, NET_A, NET_B)
                
                # 6. Store result
                row = {
                    "subject": sub_id,
                    "session": ses_id,
                    "task": task,
                    "denoising": strategy,
                    "n_rois": len(labels)
                }
                row.update(metrics)
                data_rows.append(row)
                print(f"  Processed {sub_id} {ses_id} ({strategy})")
                
            except Exception as e:
                print(f"  Error processing {sub_id} {ses_id} {strategy}: {e}")

    if data_rows:
        df = pd.DataFrame(data_rows)
        df.to_csv(output_file, index=False)
        print(f"\nSuccess! Advanced metrics extracted to {output_file}")
    else:
        print("\nNo advanced data found.")

if __name__ == "__main__":
    extract_advanced_metrics()
