import pandas as pd
import numpy as np
from pathlib import Path
from scipy import stats
import os

def expanded_dynamic_sweep():
    base_dir = Path("thesis/data/raw/Timeseries Data/anatomical")
    results = []
    
    subjects = sorted(list(set([p.name.split('_')[0] for p in base_dir.glob("*_schaefer400_ts.csv")])))
    window_size = 30 # 60s if TR=2s
    
    print(f"Analyzing {len(subjects)} subjects...")

    for sub in subjects:
        schaefer_path = base_dir / f"{sub}_ses-MRI1_task-rest_run-1_schaefer400_ts.csv"
        tian_path = base_dir / f"{sub}_ses-MRI1_task-rest_run-1_tian_s2_ts.csv"
        
        if not (schaefer_path.exists() and tian_path.exists()): continue
            
        df_cort = pd.read_csv(schaefer_path)
        df_sub = pd.read_csv(tian_path)
        
        # Networks
        networks = {
            'DMN': [c for c in df_cort.columns if 'Default' in c],
            'SN': [c for c in df_cort.columns if 'SalVentAttn' in c],
            'CEN': [c for c in df_cort.columns if 'Cont' in c],
            'Limbic': [c for c in df_cort.columns if 'Limbic' in c],
            'DorsAttn': [c for c in df_cort.columns if 'DorsAttn' in c],
            'SomMot': [c for c in df_cort.columns if 'SomMot' in c],
            'Vis': [c for c in df_cort.columns if 'Vis' in c]
        }
        
        # Subcortical
        sub_rois = {
            'AMY': [c for c in df_sub.columns if 'amy' in c.lower()],
            'HIP': [c for c in df_sub.columns if 'hip' in c.lower()]
        }
        
        ts_dict = {}
        for name, cols in networks.items():
            if cols: ts_dict[name] = df_cort[cols].mean(axis=1).values
        for name, cols in sub_rois.items():
            if cols: ts_dict[name] = df_sub[cols].mean(axis=1).values
            
        # Calculate dFC Variance for pairs
        pairs = [
            ('CEN', 'DMN'), ('CEN', 'SN'), ('Limbic', 'SN'), 
            ('AMY', 'DMN'), ('AMY', 'SN'), ('HIP', 'DMN'),
            ('Limbic', 'CEN'), ('AMY', 'CEN')
        ]
        
        row = {'sub_id': sub.split('-')[1]}
        
        import antropy as ant
        for name, ts in ts_dict.items():
            if name in networks:
                row[f'entropy_{name}'] = ant.sample_entropy(ts)
        
        for n1, n2 in pairs:
            if n1 in ts_dict and n2 in ts_dict:
                ts1 = ts_dict[n1]
                ts2 = ts_dict[n2]
                corrs = []
                for i in range(len(ts1) - window_size + 1):
                    corrs.append(np.corrcoef(ts1[i:i+window_size], ts2[i:i+window_size])[0, 1])
                row[f'dfc_var_{n1}_{n2}'] = np.var(corrs)
                row[f'sfc_{n1}_{n2}'] = np.corrcoef(ts1, ts2)[0, 1]

        results.append(row)

    df_brain = pd.DataFrame(results)
    df_clin = pd.read_excel('thesis/data/raw/clinical_data_final.xlsx')
    df_clin['sub_id'] = df_clin['record_id'].astype(str).apply(lambda x: x.split('_')[-1] if '_' in x else x)
    df_clin['caps_improvement'] = -(df_clin['CAPS_Total_II'] - df_clin['CAPS_Total_I'])
    
    merged = pd.merge(df_brain, df_clin, on='sub_id', how='inner')
    groups = ['A', 'B', 'C']
    group_map = {'A': 'High-Dose Ketamine', 'B': 'Low-Dose Ketamine', 'C': 'Midazolam (Placebo)'}
    
    metric_cols = [c for c in df_brain.columns if c != 'sub_id']
    
    for col in metric_cols:
        print(f"\n==================================================================")
        print(f"HYPOTHESIS: Baseline {col} vs CAPS Improvement")
        print(f"==================================================================")
        for g in groups:
            subset = merged[merged['group'] == g].dropna(subset=[col, 'caps_improvement'])
            if len(subset) > 2:
                r, p = stats.pearsonr(subset[col], subset['caps_improvement'])
                if p < 0.1:
                    sig = "***" if p < 0.01 else "**" if p < 0.05 else "*"
                    print(f"Group {g} [{group_map[g]}] (n={len(subset)}): r={r:.3f}, p={p:.4f} {sig}")
                else:
                    pass # Only print interesting stuff to avoid clutter

if __name__ == "__main__":
    expanded_dynamic_sweep()
