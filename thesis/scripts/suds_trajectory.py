import pandas as pd
import numpy as np
from scipy import stats
import matplotlib.pyplot as plt
from pathlib import Path

def analyze_suds():
    df_clin = pd.read_excel('thesis/data/raw/clinical_data_final.xlsx')
    
    # We want to look at PE2, PE3, PE4, PE5 SUDS mean and max
    # Columns available: 'PE2_SUDS_mean', 'PE3_SUDS_mean', 'PE4_SUDS_mean', 'PE5_SUDS_mean'
    # Also 'PE2_SUDS_max', etc.
    
    group_map = {'A': 'High-Dose Ketamine', 'B': 'Low-Dose Ketamine', 'C': 'Midazolam (Placebo)'}
    df_clin['Treatment'] = df_clin['group'].map(group_map)
    
    # Let's focus on subjects that have SUDS data
    # Calculate habituation: Drop in SUDS from PE2 to PE5
    df_clin['suds_habituation'] = df_clin['PE5_SUDS_mean'] - df_clin['PE2_SUDS_mean'] # Negative means distress went down
    
    print("==================================================================")
    print("SUDS HABITUATION (PE5 Mean - PE2 Mean)")
    print("==================================================================")
    for g in ['A', 'B', 'C']:
        subset = df_clin[df_clin['group'] == g].dropna(subset=['suds_habituation'])
        print(f"Group {g} [{group_map[g]}] (n={len(subset)}): Mean Habituation = {subset['suds_habituation'].mean():.2f}")
        
    print("\n==================================================================")
    print("CORRELATION: SUDS Habituation vs CAPS Improvement")
    print("==================================================================")
    df_clin['caps_improvement'] = -(df_clin['CAPS_Total_II'] - df_clin['CAPS_Total_I'])
    for g in ['A', 'B', 'C']:
        subset = df_clin[df_clin['group'] == g].dropna(subset=['suds_habituation', 'caps_improvement'])
        if len(subset) > 2:
            r, p = stats.pearsonr(subset['suds_habituation'], subset['caps_improvement'])
            print(f"Group {g} [{group_map[g]}] (n={len(subset)}): r={r:.3f}, p={p:.4f}")

    # Plot the Trajectory
    suds_means = []
    suds_errs = []
    sessions = ['PE2', 'PE3', 'PE4', 'PE5']
    cols = ['PE2_SUDS_mean', 'PE3_SUDS_mean', 'PE4_SUDS_mean', 'PE5_SUDS_mean']
    
    plt.figure(figsize=(10, 6))
    colors = {'Midazolam (Placebo)': 'gray', 'Low-Dose Ketamine': 'royalblue', 'High-Dose Ketamine': 'darkorange'}
    
    for trt in ['Midazolam (Placebo)', 'Low-Dose Ketamine', 'High-Dose Ketamine']:
        subset = df_clin[df_clin['Treatment'] == trt]
        means = [subset[col].mean() for col in cols]
        errs = [subset[col].sem() for col in cols] # Standard error
        
        plt.errorbar(sessions, means, yerr=errs, label=trt, color=colors[trt], marker='o', linewidth=2, capsize=5)

    plt.title("Emotional Habituation During Prolonged Exposure Therapy", fontsize=16)
    plt.xlabel("Therapy Session", fontsize=14)
    plt.ylabel("Mean SUDS (Subjective Units of Distress)", fontsize=14)
    plt.grid(True, alpha=0.3)
    plt.legend()
    fig_dir = Path("thesis/poster/figures")
    fig_dir.mkdir(parents=True, exist_ok=True)
    plt.savefig(fig_dir / "suds_trajectory.png", dpi=300)
    print("\nSaved trajectory plot to thesis/poster/figures/suds_trajectory.png")

if __name__ == "__main__":
    analyze_suds()
