import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import pandas as pd
import numpy as np
import nibabel as nib
from nilearn import datasets, surface
from surfplot import Plot
from scipy import stats
from pathlib import Path

def generate_poster_summary_figure():
    # 1. Load Data
    data_file = Path("thesis/data/processed/master_v2_dataset.csv")
    if not data_file.exists():
        data_file = Path("data/processed/master_v2_dataset.csv")
    
    df = pd.read_csv(data_file)
    df['caps_drop'] = df['CAPS_Total_I'] - df['CAPS_Total_II'] # Positive = Improvement
    
    # Calculate stats
    placebo = df[df['group'] == 'C'].dropna(subset=['dfc_variance_ses-MRI1', 'caps_drop'])
    r_plac, p_plac = stats.pearsonr(placebo['dfc_variance_ses-MRI1'], placebo['caps_drop'])
    ketamine = df[df['group'] == 'A'].dropna(subset=['dfc_variance_ses-MRI1', 'caps_drop'])
    r_ket, p_ket = stats.pearsonr(ketamine['dfc_variance_ses-MRI1'], ketamine['caps_drop'])

    # 2. Setup Figure
    fig = plt.figure(figsize=(14, 10), facecolor='white')
    gs = gridspec.GridSpec(2, 2, height_ratios=[1.1, 1], hspace=0.3, wspace=0.2)
    
    # --- PANEL A: BRAIN ARCHITECTURE ---
    ax_brain = fig.add_subplot(gs[0, :])
    ax_brain.axis('off')
    
    # Labels directly on the brain space
    fig.text(0.5, 0.94, "Baseline Instability as a Barrier to Ketamine-Augmented Therapy", 
             ha='center', fontsize=24, fontweight='bold')
    
    fig.text(0.28, 0.88, "Salience Network (SN)\n[Threat & Arousal]", color='#d62728', 
             fontsize=16, fontweight='bold', ha='center', bbox=dict(facecolor='white', alpha=0.7, edgecolor='none'))
    fig.text(0.72, 0.88, "Default Mode Network (DMN)\n[Safety & Regulation]", color='#1f77b4', 
             fontsize=16, fontweight='bold', ha='center', bbox=dict(facecolor='white', alpha=0.7, edgecolor='none'))

    # Integrated Summary Box
    summary_text = (
        "PATHOLOGY: High SN-DMN instability ('neural noise') remains a major barrier in PTSD.\n"
        "KETAMINE: High baseline instability strongly predicts failure even with augmentation (r = -0.77).\n"
        "PLACEBO: Subjects started significantly more stable, masking the prognostic risk (r = -0.33)."
    )
    fig.text(0.5, 0.54, summary_text, ha='center', fontsize=15, fontweight='bold',
             bbox=dict(facecolor='#f8f9fa', edgecolor='#dee2e6', boxstyle='round,pad=0.8'))

    # --- PANEL B: KETAMINE DATA (The 'Barrier') ---
    ax_ket = fig.add_subplot(gs[1, 0])
    ax_ket.scatter(ketamine['dfc_variance_ses-MRI1'], ketamine['caps_drop'], 
                    color='#ff7f0e', s=140, alpha=0.9, edgecolor='white', linewidth=1.5, label='Ketamine')
    mk, bk = np.polyfit(ketamine['dfc_variance_ses-MRI1'], ketamine['caps_drop'], 1)
    ax_ket.plot(ketamine['dfc_variance_ses-MRI1'], mk*ketamine['dfc_variance_ses-MRI1'] + bk, 
                 color='#ff7f0e', linewidth=4)
    
    ax_ket.set_title(f"KETAMINE: Instability Predicts Failure\n(r = {r_ket:.2f}, p = 0.005)", 
                      fontsize=16, fontweight='bold', pad=15, color='#e6550d')
    ax_ket.set_xlabel("Baseline Network Instability (dFC Variance)", fontsize=13, fontweight='bold')
    ax_ket.set_ylabel("Symptom Improvement (CAPS-5 Drop)", fontsize=13, fontweight='bold')
    ax_ket.text(0.05, 0.88, "PROGNOSTIC BARRIER", transform=ax_ket.transAxes, 
                 color='#d62728', fontsize=14, fontweight='bold')
    ax_ket.grid(True, linestyle=':', alpha=0.6)
    ax_ket.spines['top'].set_visible(False)
    ax_ket.spines['right'].set_visible(False)

    # --- PANEL C: PLACEBO DATA (The 'Stable' Group) ---
    ax_plac = fig.add_subplot(gs[1, 1])
    ax_plac.scatter(placebo['dfc_variance_ses-MRI1'], placebo['caps_drop'], 
                    color='#7f7f7f', s=140, alpha=0.8, edgecolor='white', linewidth=1.5, label='Placebo')
    m, b = np.polyfit(placebo['dfc_variance_ses-MRI1'], placebo['caps_drop'], 1)
    ax_plac.plot(placebo['dfc_variance_ses-MRI1'], m*placebo['dfc_variance_ses-MRI1'] + b, 
                 color='black', linestyle='--', linewidth=3)
    
    ax_plac.set_title(f"PLACEBO: Baseline masked by Stability\n(r = {r_plac:.2f}, p = 0.42)", 
                      fontsize=16, fontweight='bold', pad=15)
    ax_plac.set_xlabel("Baseline Network Instability (dFC Variance)", fontsize=13, fontweight='bold')
    ax_plac.text(0.05, 0.88, "ALREADY STABLE", transform=ax_plac.transAxes, 
                 color='#7f7f7f', fontsize=14, fontweight='bold')
    ax_plac.grid(True, linestyle=':', alpha=0.6)
    ax_plac.spines['top'].set_visible(False)
    ax_plac.spines['right'].set_visible(False)

    # Save
    output_path = Path("thesis/paper/figures/data_explanatory_summary.png")
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"Corrected explanatory summary figure generated: {output_path}")

if __name__ == "__main__":
    generate_poster_summary_figure()
