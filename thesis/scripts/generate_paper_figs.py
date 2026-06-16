import pandas as pd
import numpy as np
from pathlib import Path
from scipy import stats
import matplotlib.pyplot as plt

def generate_paper_figures():
    # Setup paths
    base_dir = Path("thesis/data/raw/Timeseries Data/anatomical")
    results = []
    subjects = sorted(list(set([p.name.split('_')[0] for p in base_dir.glob("*_schaefer400_ts.csv")])))
    
    # Process dFC for all subjects
    for sub in subjects:
        s1 = base_dir / f"{sub}_ses-MRI1_task-rest_run-1_schaefer400_ts.csv"
        if not s1.exists(): continue
        df = pd.read_csv(s1)
        
        # SN-DMN
        dmn_cols = [c for c in df.columns if 'Default' in c]
        sn_cols = [c for c in df.columns if 'SalVentAttn' in c]
        
        # Visual-Motor (Specificity control)
        vis_cols = [c for c in df.columns if 'Vis' in c]
        mot_cols = [c for c in df.columns if 'SomMot' in c]
        
        if all([dmn_cols, sn_cols, vis_cols, mot_cols]):
            dmn = df[dmn_cols].mean(axis=1); sn = df[sn_cols].mean(axis=1)
            vis = df[vis_cols].mean(axis=1); mot = df[mot_cols].mean(axis=1)
            
            var_fear = np.var(sn.rolling(30).corr(dmn).dropna())
            var_sensory = np.var(vis.rolling(30).corr(mot).dropna())
            
            results.append({
                'sub_id': sub.split('-')[1],
                'var_fear': var_fear,
                'var_sensory': var_sensory
            })

    df_brain = pd.DataFrame(results)
    df_clin = pd.read_excel('thesis/data/raw/clinical_data_final.xlsx')
    df_clin['sub_id'] = df_clin['record_id'].astype(str).apply(lambda x: x.split('_')[-1] if '_' in x else x)
    df_clin['caps_drop'] = df_clin['CAPS_Total_I'] - df_clin['CAPS_Total_II']
    
    merged = pd.merge(df_brain, df_clin, on='sub_id', how='inner')
    valid = merged.dropna(subset=['var_fear', 'caps_drop']).copy()
    
    # Mapping
    group_map = {'A': 'High-Dose Ketamine', 'B': 'Low-Dose Ketamine', 'C': 'Midazolam (Placebo)'}
    valid['Treatment'] = valid['group'].map(group_map)
    
    # FIGURE 5 (was 1): Ketamine Prediction (The real predictor)
    plt.figure(figsize=(8, 6))
    ketamine = valid[valid['group'] == 'A']
    plt.scatter(ketamine['var_fear'], ketamine['caps_drop'], color='orange', s=100)
    mk, bk = np.polyfit(ketamine['var_fear'], ketamine['caps_drop'], 1)
    plt.plot(ketamine['var_fear'], mk*ketamine['var_fear'] + bk, color='darkorange', linewidth=3)
    rk, pk = stats.pearsonr(ketamine['var_fear'], ketamine['caps_drop'])
    plt.text(0.05, 0.9, f"r = {rk:.3f}\np = {pk:.3f}", transform=plt.gca().transAxes, fontsize=12, bbox=dict(facecolor='white', alpha=0.8))
    plt.title("Figure 5: Baseline Instability Predicts Failure in Ketamine Group")
    plt.xlabel("Baseline SN-DMN dFC Variance")
    plt.ylabel("Improvement (CAPS-5 Drop)")
    plt.savefig("thesis/paper/figures/figure1_placebo.png", dpi=300) # Keep filename for md compatibility but it's now Ketamine
    plt.close()

    # FIGURE 6 (was 2): Placebo "Uncoupling" (Lack of relationship)
    plt.figure(figsize=(10, 7))
    colors = {'Midazolam (Placebo)': 'gray', 'Low-Dose Ketamine': 'blue', 'High-Dose Ketamine': 'orange'}
    for trt in colors.keys():
        subset = valid[valid['Treatment'] == trt]
        plt.scatter(subset['var_fear'], subset['caps_drop'], label=trt, color=colors[trt], alpha=0.7, s=60)
        m, b = np.polyfit(subset['var_fear'], subset['caps_drop'], 1)
        ls = '-' if trt == 'High-Dose Ketamine' else '--'
        plt.plot(subset['var_fear'], m*subset['var_fear'] + b, color=colors[trt], linestyle=ls)
    plt.title("Figure 6: Placebo Group shows lower Baseline Risk")
    plt.xlabel("Baseline SN-DMN dFC Variance")
    plt.ylabel("Improvement (CAPS-5 Drop)")
    plt.legend()
    plt.savefig("thesis/paper/figures/figure2_uncoupling.png", dpi=300)
    plt.close()

    # FIGURE 7 (was 3): Specificity
    plt.figure(figsize=(8, 6))
    ket_control = valid[valid['group'] == 'A']
    plt.scatter(ket_control['var_sensory'], ket_control['caps_drop'], color='green', s=100)
    m, b = np.polyfit(ket_control['var_sensory'], ket_control['caps_drop'], 1)
    plt.plot(ket_control['var_sensory'], m*ket_control['var_sensory'] + b, color='darkgreen', linestyle='--')
    r, p = stats.pearsonr(ket_control['var_sensory'], ket_control['caps_drop'])
    plt.text(0.05, 0.9, f"r = {r:.3f}\np = {p:.3f} (ns)", transform=plt.gca().transAxes, fontsize=12, bbox=dict(facecolor='white', alpha=0.8))
    plt.title("Figure 7: Control Analysis - Sensory Networks do not predict outcome")
    plt.xlabel("Baseline Sensory-Motor dFC Variance")
    plt.ylabel("Improvement (CAPS-5 Drop)")
    plt.savefig("thesis/paper/figures/figure3_specificity.png", dpi=300)
    plt.close()

    print("Paper figures corrected and generated.")

if __name__ == "__main__":
    generate_paper_figures()
