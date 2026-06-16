import pandas as pd
import numpy as np
from pathlib import Path
from scipy import stats

def static_fc_sweep():
    base_dir = Path("thesis/data/raw/Timeseries Data/anatomical")
    results = []
    
    subjects = sorted(list(set([p.name.split('_')[0] for p in base_dir.glob("*_schaefer400_ts.csv")])))
    
    for sub in subjects:
        schaefer_path = base_dir / f"{sub}_ses-MRI1_task-rest_run-1_schaefer400_ts.csv"
        tian_path = base_dir / f"{sub}_ses-MRI1_task-rest_run-1_tian_s2_ts.csv"
        
        if not (schaefer_path.exists() and tian_path.exists()): continue
            
        df_cort = pd.read_csv(schaefer_path)
        df_sub = pd.read_csv(tian_path)
        
        dmn_cols = [c for c in df_cort.columns if 'Default' in c]
        sn_cols = [c for c in df_cort.columns if 'SalVentAttn' in c]
        amy_cols = [c for c in df_sub.columns if 'amy' in c.lower()]
        hip_cols = [c for c in df_sub.columns if 'hip' in c.lower()]
        
        if dmn_cols and sn_cols and amy_cols and hip_cols:
            dmn_ts = df_cort[dmn_cols].mean(axis=1)
            sn_ts = df_cort[sn_cols].mean(axis=1)
            amy_ts = df_sub[amy_cols].mean(axis=1)
            hip_ts = df_sub[hip_cols].mean(axis=1)
            
            sfc_sn_dmn = np.corrcoef(sn_ts, dmn_ts)[0, 1]
            sfc_amy_dmn = np.corrcoef(amy_ts, dmn_ts)[0, 1]
            sfc_hip_dmn = np.corrcoef(hip_ts, dmn_ts)[0, 1]
            sfc_amy_hip = np.corrcoef(amy_ts, hip_ts)[0, 1]
            
            results.append({
                'sub_id': sub.split('-')[1],
                'sfc_sn_dmn': sfc_sn_dmn,
                'sfc_amy_dmn': sfc_amy_dmn,
                'sfc_hip_dmn': sfc_hip_dmn,
                'sfc_amy_hip': sfc_amy_hip
            })

    df_brain = pd.DataFrame(results)
    df_clin = pd.read_excel('thesis/data/raw/clinical_data_final.xlsx')
    df_clin['sub_id'] = df_clin['record_id'].astype(str).apply(lambda x: x.split('_')[-1] if '_' in x else x)
    df_clin['caps_improvement'] = -(df_clin['CAPS_Total_II'] - df_clin['CAPS_Total_I'])
    
    merged = pd.merge(df_brain, df_clin, on='sub_id', how='inner')
    groups = ['A', 'B', 'C']
    group_map = {'A': 'High-Dose Ketamine', 'B': 'Low-Dose Ketamine', 'C': 'Midazolam (Placebo)'}
    
    metrics = [
        ('SN-DMN', 'sfc_sn_dmn'),
        ('Amygdala-vmPFC (DMN)', 'sfc_amy_dmn'),
        ('Hippocampus-vmPFC (DMN)', 'sfc_hip_dmn'),
        ('Amygdala-Hippocampus', 'sfc_amy_hip')
    ]
    
    for metric_name, metric_col in metrics:
        print(f"\n==================================================================")
        print(f"HYPOTHESIS: Baseline Static {metric_name} vs CAPS Improvement")
        print(f"==================================================================")
        for g in groups:
            subset = merged[merged['group'] == g].dropna(subset=[metric_col, 'caps_improvement'])
            if len(subset) > 2:
                r, p = stats.pearsonr(subset[metric_col], subset['caps_improvement'])
                sig = "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""
                print(f"Group {g} [{group_map[g]}] (n={len(subset)}): r={r:.3f}, p={p:.4f} {sig}")

if __name__ == "__main__":
    static_fc_sweep()
