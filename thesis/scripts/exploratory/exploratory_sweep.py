import pandas as pd
import numpy as np
from scipy import stats

def exploratory_sweep():
    # Load Master Dataset
    df = pd.read_csv('thesis/data/processed/master_v2_dataset.csv')
    
    # We already have caps_improvement. Let's make sure it's loaded properly.
    
    groups = ['A', 'B', 'C']
    group_map = {'A': 'High-Dose Ketamine', 'B': 'Low-Dose Ketamine', 'C': 'Midazolam (Placebo)'}
    
    print("==================================================================")
    print("HYPOTHESIS 1: The Dissociative Subtype (CAPS_Dissociation_I)")
    print("Literature: Ketamine is a dissociative. Does baseline dissociation predict outcome?")
    print("==================================================================")
    for g in groups:
        subset = df[df['group'] == g].dropna(subset=['CAPS_Dissociation_I', 'caps_improvement'])
        if len(subset) > 2:
            r, p = stats.pearsonr(subset['CAPS_Dissociation_I'], subset['caps_improvement'])
            print(f"Group {g} [{group_map[g]}] (n={len(subset)}): r={r:.3f}, p={p:.4f}")

    print("\n==================================================================")
    print("HYPOTHESIS 2: The Depressive Comorbidity (BDI_Total_I)")
    print("Literature: Ketamine is a powerful rapid antidepressant. Does it work better for depressed PTSD patients?")
    print("==================================================================")
    for g in groups:
        subset = df[df['group'] == g].dropna(subset=['BDI_Total_I', 'caps_improvement'])
        if len(subset) > 2:
            r, p = stats.pearsonr(subset['BDI_Total_I'], subset['caps_improvement'])
            print(f"Group {g} [{group_map[g]}] (n={len(subset)}): r={r:.3f}, p={p:.4f}")

    print("\n==================================================================")
    print("HYPOTHESIS 3: Anxiety Baseline (STAI_Total_I)")
    print("Literature: Baseline anxiety levels might moderate exposure therapy engagement.")
    print("==================================================================")
    for g in groups:
        subset = df[df['group'] == g].dropna(subset=['STAI_Total_I', 'caps_improvement'])
        if len(subset) > 2:
            r, p = stats.pearsonr(subset['STAI_Total_I'], subset['caps_improvement'])
            print(f"Group {g} [{group_map[g]}] (n={len(subset)}): r={r:.3f}, p={p:.4f}")

    print("\n==================================================================")
    print("HYPOTHESIS 4: Therapy Engagement (SUDS_mean_overall)")
    print("Literature: Subjective Units of Distress (SUDS) indicate engagement in PE. Does Ketamine alter engagement vs outcome?")
    print("==================================================================")
    for g in groups:
        subset = df[df['group'] == g].dropna(subset=['SUDS_mean_overall', 'caps_improvement'])
        if len(subset) > 2:
            r, p = stats.pearsonr(subset['SUDS_mean_overall'], subset['caps_improvement'])
            print(f"Group {g} [{group_map[g]}] (n={len(subset)}): r={r:.3f}, p={p:.4f}")
            
    print("\n==================================================================")
    print("HYPOTHESIS 5: Group Differences in Therapy Engagement (SUDS)")
    print("Does Ketamine lower distress during PE?")
    print("==================================================================")
    for g in groups:
        subset = df[df['group'] == g].dropna(subset=['SUDS_mean_overall'])
        if len(subset) > 2:
            print(f"Group {g} [{group_map[g]}] Mean Overall SUDS: {subset['SUDS_mean_overall'].mean():.1f}")
            
if __name__ == "__main__":
    exploratory_sweep()
