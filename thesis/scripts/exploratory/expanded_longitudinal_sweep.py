import pandas as pd
import numpy as np
from pathlib import Path
from scipy import stats
import os
import antropy as ant

def expanded_longitudinal_sweep():
    base_dir = Path("thesis/data/raw/Timeseries Data/anatomical")
    results = []
    
    subjects = sorted(list(set([p.name.split('_')[0] for p in base_dir.glob("*_schaefer400_ts.csv")])))
    sessions = ['ses-MRI1', 'ses-MRI2']
    
    print(f"Analyzing {len(subjects)} subjects across T1 and T2...")

    for sub in subjects:
        sub_id = sub.split('-')[1]
        for ses in sessions:
            schaefer_path = base_dir / f"{sub}_{ses}_task-rest_run-1_schaefer400_ts.csv"
            if not schaefer_path.exists(): continue
                
            df_cort = pd.read_csv(schaefer_path)
            
            # Networks
            networks = {
                'DMN': [c for c in df_cort.columns if 'Default' in c],
                'SN': [c for c in df_cort.columns if 'SalVentAttn' in c],
                'CEN': [c for c in df_cort.columns if 'Cont' in c],
                'Limbic': [c for c in df_cort.columns if 'Limbic' in c]
            }
            
            row = {'sub_id': sub_id, 'session': ses}
            for name, cols in networks.items():
                if cols:
                    ts = df_cort[cols].mean(axis=1).values
                    row[f'entropy_{name}'] = ant.sample_entropy(ts)
            
            results.append(row)

    df_brain = pd.DataFrame(results)
    
    # Pivot to get change
    df_pivoted = df_brain.pivot(index='sub_id', columns='session')
    df_pivoted.columns = [f"{col}_{ses}" for col, ses in df_pivoted.columns]
    df_pivoted = df_pivoted.reset_index()
    
    for net in ['DMN', 'SN', 'CEN', 'Limbic']:
        t1_col = f'entropy_{net}_ses-MRI1'
        t2_col = f'entropy_{net}_ses-MRI2'
        if t1_col in df_pivoted.columns and t2_col in df_pivoted.columns:
            df_pivoted[f'entropy_change_{net}'] = df_pivoted[t2_col] - df_pivoted[t1_col]

    df_clin = pd.read_excel('thesis/data/raw/clinical_data_final.xlsx')
    df_clin['sub_id'] = df_clin['record_id'].astype(str).apply(lambda x: x.split('_')[-1] if '_' in x else x)
    df_clin['caps_improvement'] = -(df_clin['CAPS_Total_II'] - df_clin['CAPS_Total_I'])
    
    merged = pd.merge(df_pivoted, df_clin, on='sub_id', how='inner')
    groups = ['A', 'B', 'C']
    group_map = {'A': 'High-Dose Ketamine', 'B': 'Low-Dose Ketamine', 'C': 'Midazolam (Placebo)'}
    
    for net in ['DMN', 'SN', 'CEN', 'Limbic']:
        col = f'entropy_change_{net}'
        if col not in merged.columns: continue
            
        print(f"\n==================================================================")
        print(f"HYPOTHESIS: {net} Entropy Change (T2-T1) vs CAPS Improvement")
        print(f"==================================================================")
        for g in groups:
            subset = merged[merged['group'] == g].dropna(subset=[col, 'caps_improvement'])
            if len(subset) > 2:
                r, p = stats.pearsonr(subset[col], subset['caps_improvement'])
                if p < 0.2: # Relaxed p for exploration
                    sig = "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else "trend"
                    print(f"Group {g} [{group_map[g]}] (n={len(subset)}): r={r:.3f}, p={p:.4f} {sig}")

if __name__ == "__main__":
    expanded_longitudinal_sweep()
