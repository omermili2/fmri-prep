import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

def generate_conceptual_state_space():
    output_dir = Path("thesis/poster/figures")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Simulate State Space Data (Reflecting the Barrier Finding)
    np.random.seed(42)
    n_pts = 20
    # Group A (Ketamine) - High instability, Low complexity at baseline
    base_instability = np.random.normal(0.8, 0.1, n_pts)
    base_entropy = np.random.normal(1.5, 0.1, n_pts)
    
    # Placebo - Started more stable
    plac_base_instability = np.random.normal(0.4, 0.1, 10)
    plac_base_entropy = np.random.normal(1.8, 0.1, 10)
    
    # Post-treatment Ketamine - Most stay "Stuck" if they started high
    ket_post_instability = base_instability[10:] + np.random.normal(0, 0.05, 10)
    ket_post_entropy = base_entropy[10:] + np.random.normal(0, 0.1, 10)
    
    # Placebo - Good outcomes associated with entropy change
    plac_post_entropy = plac_base_entropy + 0.4

    # 2. Plotting
    fig, ax = plt.subplots(figsize=(10, 8), facecolor='white')
    
    # Zones
    ax.axvspan(0.6, 1.1, 1.0, 2.0, color='#d62728', alpha=0.08) # Pathological
    ax.axvspan(0.0, 0.5, 2.0, 2.5, color='#2ca02c', alpha=0.08) # Healthy

    # Ketamine pts (The Barrier)
    ax.scatter(base_instability[10:], base_entropy[10:], color='orange', s=100, alpha=0.4, 
               edgecolor='black', label='Ketamine Baseline (Unstable)')
    ax.scatter(ket_post_instability, ket_post_entropy, color='#ff7f0e', s=200, marker='*', 
               edgecolor='black', label='Ketamine Post (Still Stuck)')
    
    # Placebo pts (The Stable success)
    ax.scatter(plac_base_instability, plac_base_entropy, color='gray', s=100, alpha=0.4, 
               label='Placebo Baseline (Already Stable)')
    ax.scatter(plac_base_instability, plac_post_entropy, color='black', s=120, marker='X', 
               label='Placebo Post (Success)')

    ax.set_title("Neural State-Space: Instability as a Barrier", fontsize=20, fontweight='bold', pad=25)
    ax.set_xlabel("Network Instability (dFC Variance) [High = Stuck]", fontsize=15, fontweight='bold')
    ax.set_ylabel("Neural Complexity (Entropy) [High = Fluid]", fontsize=15, fontweight='bold')
    
    ax.set_xlim(0, 1.1)
    ax.set_ylim(1.0, 2.5)
    ax.grid(True, linestyle=':', alpha=0.6)
    
    # Region Labels
    ax.text(0.85, 1.2, "PROGNOSTIC BARRIER\nKetamine therapy fails\nagainst high noise", color='#d62728', 
            ha='center', fontsize=12, fontweight='bold', bbox=dict(facecolor='white', alpha=0.7, edgecolor='none'))
    ax.text(0.25, 2.3, "THERAPEUTIC WINDOW\nPlacebo success driven\nby baseline stability", color='#2ca02c', 
            ha='center', fontsize=12, fontweight='bold', bbox=dict(facecolor='white', alpha=0.7, edgecolor='none'))

    plt.legend(loc='lower left', fontsize=10, frameon=True, shadow=True)
    plt.tight_layout()
    
    output_path = output_dir / "conceptual_state_space.png"
    plt.savefig(output_path, dpi=300)
    plt.close()
    
    print(f"Corrected state-space figure generated: {output_path}")

if __name__ == "__main__":
    generate_conceptual_state_space()
