# Figures Guide for Thesis

This document provides guidance for creating figures to include in your thesis.

## Recommended Figures

### Figure 1: System Overview
**Location**: Chapter 1 (Introduction) or Chapter 3 (Methodology)

Create a high-level diagram showing:
- User → GUI → Pipeline → External Tools → Output
- Include icons for each component
- Use consistent color scheme

**Tool suggestion**: Draw.io, Lucidchart, or PowerPoint

---

### Figure 2: GUI Screenshot
**Location**: Chapter 4 (Implementation)

Take a screenshot of the application showing:
- The main window with all components visible
- Example paths filled in
- Progress bar in action (if possible)

**Capture at**: 1920x1080 resolution, light theme

---

### Figure 3: BIDS Directory Structure
**Location**: Chapter 2 (Literature Review) or Chapter 3 (Methodology)

Create a tree diagram showing:
```
dataset/
├── dataset_description.json
├── participants.tsv
├── sub-001/
│   ├── ses-01/
│   │   ├── anat/
│   │   │   └── sub-001_ses-01_T1w.nii.gz
│   │   └── func/
│   │       └── sub-001_ses-01_task-rest_bold.nii.gz
...
```

Use color coding:
- Blue: Folders
- Green: Data files
- Orange: Metadata files

---

### Figure 4: fMRIPrep Pipeline Steps
**Location**: Chapter 3 (Methodology)

Create a flowchart showing preprocessing steps:

```
Input BIDS Data
      ↓
┌─────────────────┐
│ Brain Extraction│
└────────┬────────┘
         ↓
┌─────────────────┐
│Tissue Segmentation│
└────────┬────────┘
         ↓
┌─────────────────┐
│ Spatial Normal. │
└────────┬────────┘
         ↓
┌─────────────────┐
│Motion Correction│
└────────┬────────┘
         ↓
┌─────────────────┐
│Registration     │
└────────┬────────┘
         ↓
Preprocessed Data
```

---

### Figure 5: Performance Benchmarks
**Location**: Chapter 5 (Results)

Create a bar chart or line graph showing:
- X-axis: Number of parallel workers (1, 2, 4, 8, 12)
- Y-axis: Processing time (minutes)
- Multiple series for different dataset sizes

Also include:
- Speedup ratio comparison
- Efficiency metrics

---

### Figure 6: Data Flow Diagram
**Location**: Chapter 3 (Methodology)

Create a comprehensive data flow diagram:
```
DICOM Files → dcm2niix → NIfTI → dcm2bids → BIDS → fMRIPrep → Derivatives
```

Show transformation at each step with sample file names.

---

### Figure 7: Sample fMRIPrep Outputs
**Location**: Chapter 5 (Results)

Include actual fMRIPrep outputs:
- Brain extraction result (before/after)
- Registration quality visualization
- Motion parameters plot
- Carpet plot example

**Source**: From actual pipeline runs on your test data

---

### Figure 8: Error Handling Flowchart
**Location**: Chapter 4 (Implementation) or Appendix

Flowchart showing error detection and recovery:
```
Start Processing
      ↓
  [Check Input] → Error? → [Show Message] → [Retry/Exit]
      ↓
  [Convert] → Error? → [Log & Report] → [Continue/Abort]
      ...
```

---

### Figure 9: GUI Wireframe Evolution
**Location**: Chapter 4 (Implementation)

Show the evolution of the GUI design:
- Initial concept sketch
- Intermediate version
- Final implementation

Demonstrates design decisions and user feedback incorporation.

---

### Figure 10: Comparison Table (Visual)
**Location**: Chapter 6 (Discussion)

Visual comparison matrix:
```
Feature          | This Tool | CLI Tools | Manual
─────────────────┼───────────┼───────────┼────────
GUI Interface    |    ✓      |     ✗     |    ✗
Parallel Proc.   |    ✓      |  Varies   |    ✗
Auto Reports     |    ✓      |  Varies   |    ✗
...
```

Use icons/colors for visual impact.

---

## Figure Formatting Guidelines

### Resolution
- Raster images: Minimum 300 DPI
- Vector images: Preferred for diagrams (SVG, PDF)

### Size
- Full-width figures: 6.5 inches wide
- Half-width figures: 3 inches wide

### Color Scheme
Suggested consistent colors:
- Primary: #2196F3 (blue)
- Secondary: #4CAF50 (green)
- Accent: #FFC107 (amber)
- Error: #F44336 (red)
- Neutral: #9E9E9E (gray)

### Font
- Sans-serif for labels (Arial, Helvetica, Open Sans)
- Same font family as thesis body
- Minimum 8pt for figure labels

### File Naming
```
fig01_system_overview.png
fig02_gui_screenshot.png
fig03_bids_structure.pdf
fig04_fmriprep_pipeline.pdf
...
```

---

## Tools for Creating Figures

### Diagrams & Flowcharts
- [Draw.io](https://draw.io) - Free, browser-based
- [Lucidchart](https://lucidchart.com) - Professional, collaborative
- [PlantUML](https://plantuml.com) - Code-based diagrams

### Data Visualization
- Python: matplotlib, seaborn, plotly
- R: ggplot2
- Excel/Google Sheets for simple charts

### Brain Images
- [FSLeyes](https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/FSLeyes) - MRI visualization
- [MRIcroGL](https://www.nitrc.org/projects/mricrogl) - 3D rendering
- [Nilearn](https://nilearn.github.io/) - Python neuroimaging plots

### Screenshots
- macOS: Cmd+Shift+4
- Windows: Snipping Tool or Win+Shift+S
- Consider using CleanShot X or ShareX for annotations

---

## Placeholder Images

Until you create the actual figures, you can use these placeholders in your thesis:

```markdown
![Figure 1: System Overview](figures/fig01_system_overview.png)
*Figure 1: High-level architecture of the fMRI preprocessing pipeline*
```

Create simple placeholder images with text indicating what the figure will show.

