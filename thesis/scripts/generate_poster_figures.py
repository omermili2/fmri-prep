import pandas as pd
import numpy as np
from pathlib import Path
from scipy import stats
import matplotlib.pyplot as plt

def generate_figures():
    # Setup paths
    data_file = Path("thesis/data/processed/master_v2_dataset.csv")
    fig_dir = Path("thesis/poster/figures")
    fig_dir.mkdir(parents=True, exist_ok=True)
    
    # Load data
    df = pd.read_csv(data_file)
    group_map = {'A': 'High-Dose Ketamine', 'B': 'Low-Dose Ketamine', 'C': 'Midazolam (Placebo)'}
    df['Treatment'] = df['group'].map(group_map)
    
    colors = {'Midazolam (Placebo)': 'gray', 'Low-Dose Ketamine': 'royalblue', 'High-Dose Ketamine': 'darkorange'}

    # Figure 1: Dimension 1 - Prognostic Biomarker
    plt.figure(figsize=(12, 8))
    for trt in ['Midazolam (Placebo)', 'Low-Dose Ketamine', 'High-Dose Ketamine']:
        subset = df[df['Treatment'] == trt].dropna(subset=['dfc_variance_ses-MRI1', 'caps_improvement'])
        if subset.empty: continue
        plt.scatter(subset['dfc_variance_ses-MRI1'], subset['caps_improvement'], label=trt, color=colors[trt], s=120, alpha=0.8)
        
        m, b = np.polyfit(subset['dfc_variance_ses-MRI1'], subset['caps_improvement'], 1)
        style = '-' if trt == 'High-Dose Ketamine' else '--'
        lw = 4 if trt == 'High-Dose Ketamine' else 2
        plt.plot(subset['dfc_variance_ses-MRI1'], m*subset['dfc_variance_ses-MRI1'] + b, color=colors[trt], linestyle=style, linewidth=lw)

    plt.title("Prognostic Law: Baseline Instability Predicts Failure in High-Dose Ketamine", fontsize=18, pad=20)
    plt.xlabel("Baseline SN-DMN Instability (dFC Variance)", fontsize=16)
    plt.ylabel("Symptom Improvement (CAPS-5 Drop)", fontsize=16)
    plt.axhline(0, color='black', linewidth=1.5, linestyle=':')
    plt.grid(True, alpha=0.3)
    plt.legend(fontsize=14)
    plt.tight_layout()
    plt.savefig(fig_dir / "dimension1_prognostic_result.png", dpi=300)
    plt.close()

    print("Figures successfully generated in thesis/poster/figures/")

if __name__ == "__main__":
    generate_figures()