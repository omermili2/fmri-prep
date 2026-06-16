import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

def calculate_dfc_trace(ts_file, window_size=26):
    try:
        df = pd.read_csv(ts_file)
    except Exception as e:
        print(f"Error reading {ts_file}: {e}")
        return None
    
    # Identify Salience and Default networks
    sn_cols = [c for c in df.columns if 'SalVentAttn' in c]
    dmn_cols = [c for c in df.columns if 'Default' in c]
    
    if not sn_cols or not dmn_cols:
        return None
        
    # Mean timeseries
    sn_ts = df[sn_cols].mean(axis=1)
    dmn_ts = df[dmn_cols].mean(axis=1)
    
    # Sliding window correlation
    corrs = []
    for i in range(len(df) - window_size + 1):
        window_sn = sn_ts[i:i+window_size]
        window_dmn = dmn_ts[i:i+window_size]
        corrs.append(np.corrcoef(window_sn, window_dmn)[0, 1])
        
    return np.array(corrs)

def generate_aggregate_traces():
    data_dir = Path("thesis/data/raw/Timeseries Data/global")
    output_dir = Path("thesis/poster/figures")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    ts_files = list(data_dir.glob("*_ses-MRI1_task-rest_run-1_schaefer400_ts.csv"))
    print(f"Found {len(ts_files)} baseline subjects.")
    
    all_traces = []
    all_variances = []
    valid_subjects = []
    
    for i, ts_file in enumerate(ts_files):
        if i % 10 == 0:
            print(f"Processing subject {i}/{len(ts_files)}...")
        trace = calculate_dfc_trace(ts_file)
        if trace is not None:
            all_traces.append(trace)
            all_variances.append(np.var(trace))
            valid_subjects.append(ts_file.name.split('_')[0])
            
    if not all_traces:
        print("No valid traces found.")
        return
        
    # Truncate to minimum length to handle inhomogeneous shapes
    min_len = min(len(t) for t in all_traces)
    print(f"Truncating all traces to minimum length: {min_len}")
    all_traces = np.array([t[:min_len] for t in all_traces])
    all_variances = np.array(all_variances)
    
    # Median split
    median_var = np.median(all_variances)
    stable_idx = all_variances <= median_var
    unstable_idx = all_variances > median_var
    
    trace_stable = all_traces[stable_idx]
    trace_unstable = all_traces[unstable_idx]
    
    print(f"Stable group: {len(trace_stable)} subjects")
    print(f"Unstable group: {len(trace_unstable)} subjects")
    
    # Calculate means and SE
    mean_stable = np.mean(trace_stable, axis=0)
    se_stable = np.std(trace_stable, axis=0) / np.sqrt(len(trace_stable))
    
    mean_unstable = np.mean(trace_unstable, axis=0)
    se_unstable = np.std(trace_unstable, axis=0) / np.sqrt(len(trace_unstable))
    
    # Plotting
    plt.figure(figsize=(12, 8))
    time = np.arange(len(mean_stable))
    
    # Stable Group
    plt.plot(time, mean_stable, color='#1C517B', linewidth=3, label=f'Stable Group (n={len(trace_stable)})')
    plt.fill_between(time, mean_stable - se_stable, mean_stable + se_stable, color='#1C517B', alpha=0.2)
    
    # Unstable Group
    plt.plot(time, mean_unstable, color='#FA7F5B', linewidth=3, label=f'Unstable Group (n={len(trace_unstable)})')
    plt.fill_between(time, mean_unstable - se_unstable, mean_unstable + se_unstable, color='#FA7F5B', alpha=0.2)
    
    plt.title("Aggregate dFC Traces (Group Average)", fontsize=20, fontweight='bold')
    plt.xlabel("Time (Sliding Windows)", fontsize=16)
    plt.ylabel("SN-DMN Correlation (r)", fontsize=16)
    plt.legend(fontsize=14)
    plt.grid(True, alpha=0.2)
    plt.ylim(-0.4, 0.8) # Adjusted for average scale
    
    output_path = output_dir / "aggregate_dfc_traces.png"
    plt.savefig(output_path, dpi=300)
    plt.close()
    
    print(f"Aggregate dFC traces figure generated: {output_path}")

if __name__ == "__main__":
    generate_aggregate_traces()
