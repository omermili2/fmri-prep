# Thesis Analysis Tools

This directory contains the foundation for your thesis analysis on **Ketamine's modulation of Salience–Default Mode Network segregation in PTSD**.

## Contents

1.  **`utils.py`**: Contains the core mathematical logic.
    *   **`load_connectivity_data`**: Loads your processed brain matrices.
    *   **`get_network_indices`**: Identifies which brain regions belong to the Salience (`SalVentAttn`) and Default Mode (`Default`) networks.
    *   **`calculate_segregation`**: Implements the **System Segregation Index (Chan et al., 2014)**, which is the peer-reviewed standard for your research question.

2.  **`extract_metrics.py`**: Your batch processing script.
    *   **What it does**: It automatically scans your pipeline output folders, finds every subject and session, and calculates the segregation metrics.
    *   **How to use it**: Open the file and update the `base_dir` path to point to your latest output folder. Then run:
        ```bash
        python extract_metrics.py
        ```
    *   **Output**: It creates `thesis_dataset.csv`, which is your master spreadsheet for all 37 subjects.

3.  **`Network_Analysis.ipynb`**: Your interactive workspace.
    *   **What it does**: This Jupyter Notebook loads your `thesis_dataset.csv` and provides ready-to-use code for:
        *   Plotting your network segregation (e.g., comparing Baseline vs. Post-Treatment).
        *   Running your first statistical tests (Paired T-Tests).
    *   **How to use it**: Open it in VS Code, PyCharm, or a Jupyter browser and run the cells.

## Methodology Note
These tools use **System Segregation**, defined as:
`((Within_Correlation - Between_Correlation) / Within_Correlation)`

A higher value means the networks are more "segregated" (distinct), while a lower value means they are "integrating" (merging). This is the direct answer to your thesis question!
