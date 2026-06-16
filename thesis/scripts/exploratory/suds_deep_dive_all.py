import pandas as pd
from scipy import stats

def deep_dive_suds_all():
    df_clin = pd.read_excel('thesis/data/raw/clinical_data_final.xlsx')
    group_map = {'A': 'High-Dose Ketamine', 'B': 'Low-Dose Ketamine', 'C': 'Midazolam (Placebo)'}
    df_clin['Treatment'] = df_clin['group'].map(group_map)
    df_clin['suds_change'] = df_clin['PE5_SUDS_mean'] - df_clin['PE2_SUDS_mean'] # Negative = Less distress at end
    df_clin['caps_improvement'] = -(df_clin['CAPS_Total_II'] - df_clin['CAPS_Total_I']) # Positive = Better outcome
    
    for g in ['A', 'B', 'C']:
        subset = df_clin[df_clin['group'] == g].dropna(subset=['suds_change', 'caps_improvement'])
        r, p = stats.pearsonr(subset['suds_change'], subset['caps_improvement'])
        print(f"Group {g} [{group_map[g]}]: r={r:.3f}, p={p:.4f}")
        print(f"  Mean SUDS Change: {subset['suds_change'].mean():.1f}")
        print(f"  Mean CAPS Improv: {subset['caps_improvement'].mean():.1f}")

if __name__ == "__main__":
    deep_dive_suds_all()