import matplotlib.pyplot as plt
import numpy as np
import nibabel as nib
from nilearn import plotting, datasets, surface
from pathlib import Path

def generate_meaningful_brain_plots():
    # 1. Setup paths
    atlas_path = "src/qc/atlas_data/Schaefer2018_400Parcels_7Networks_order_Tian_Subcortex_S2_3T_MNI152NLin2009cAsym_2mm.nii.gz"
    output_dir = Path("thesis/poster/figures")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Loading atlas from {atlas_path}...")
    atlas_img = nib.load(atlas_path)
    atlas_data = atlas_img.get_fdata()
    
    # 2. Define Network ROI indices based on the order file
    # SalVentAttn (Salience) LH: 124-145, RH: 326-350 (approx based on labels)
    # Default LH: 181-232, RH: 394-432 (approx based on labels)
    # Subcortical Amygdala (Tian): 3, 4, 19, 20
    
    salience_indices = list(range(124, 146)) + list(range(326, 351))
    default_indices = list(range(181, 233)) + list(range(394, 433))
    amygdala_indices = [3, 4, 19, 20] 
    visual_indices = list(range(33, 64)) + list(range(233, 263))
    sommot_indices = list(range(64, 101)) + list(range(263, 303))
    
    # 3. Create a weight map for visualization
    weight_map_data = np.zeros_like(atlas_data)
    
    for idx in salience_indices:
        weight_map_data[atlas_data == idx] = 2.0  # Salience (Warm)
    for idx in default_indices:
        weight_map_data[atlas_data == idx] = -2.0 # Default (Cold)
    for idx in amygdala_indices:
        weight_map_data[atlas_data == idx] = 1.5  # Amygdala (Warm highlight)
    for idx in visual_indices:
        weight_map_data[atlas_data == idx] = 0.5  # Visual (Neutral/Control)
    for idx in sommot_indices:
        weight_map_data[atlas_data == idx] = -0.5 # Somatomotor (Neutral/Control)
        
    weight_map_img = nib.Nifti1Image(weight_map_data, atlas_img.affine, atlas_img.header)
    
    # 4. Project to Surface (fsaverage)
    print("Projecting to surface and generating plots...")
    fsaverage = datasets.fetch_surf_fsaverage('fsaverage5')
    
    # Project the volume to the surface
    lh_surf_data = surface.vol_to_surf(weight_map_img, fsaverage.pial_left)
    rh_surf_data = surface.vol_to_surf(weight_map_img, fsaverage.pial_right)
    
    # Generate 4 views: LH Lateral, LH Medial, RH Lateral, RH Medial
    fig, axes = plt.subplots(2, 2, figsize=(16, 10), subplot_kw={'projection': '3d'})
    
    # LH Lateral
    plotting.plot_surf_stat_map(fsaverage.pial_left, lh_surf_data, hemi='left', view='lateral',
                          bg_map=fsaverage.sulc_left, axes=axes[0,0], cmap='Spectral', colorbar=False,
                          title="Left Hemisphere (Lateral)")
    
    # LH Medial
    plotting.plot_surf_stat_map(fsaverage.pial_left, lh_surf_data, hemi='left', view='medial',
                          bg_map=fsaverage.sulc_left, axes=axes[0,1], cmap='Spectral', colorbar=False,
                          title="Left Hemisphere (Medial)")
    
    # RH Lateral
    plotting.plot_surf_stat_map(fsaverage.pial_right, rh_surf_data, hemi='right', view='lateral',
                          bg_map=fsaverage.sulc_right, axes=axes[1,0], cmap='Spectral', colorbar=False,
                          title="Right Hemisphere (Lateral)")
    
    # RH Medial
    plotting.plot_surf_stat_map(fsaverage.pial_right, rh_surf_data, hemi='right', view='medial',
                          bg_map=fsaverage.sulc_right, axes=axes[1,1], cmap='Spectral', colorbar=False,
                          title="Right Hemisphere (Medial)")
    
    plt.suptitle("Functional Anatomy of the Predictive Model:\nTarget Networks (Salience/DMN) vs. Control Networks (Visual/Somatomotor)", 
                 fontsize=20, y=0.95)
    
    output_path = output_dir / "brain_network_map.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"Meaningful brain plot generated: {output_path}")

if __name__ == "__main__":
    generate_meaningful_brain_plots()
