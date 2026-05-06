# MRIQC Report Guide

This guide explains how to read the MRIQC section of the pipeline report.
The MRIQC report is generated as soon as MRIQC finishes (before fMRIPrep),
so you can check image quality early without waiting for the full pipeline.

---

## When Is the MRIQC Report Generated?

The pipeline produces two reports that include MRIQC results:

1. **`mriqc_report.html`** — Standalone early report, written immediately after
   MRIQC completes. Open this while fMRIPrep is still running for early QC
   feedback.
2. **`full_pipeline_report.html`** — Final report including all pipeline stages.
   The MRIQC section in this report is identical.

---

## Structural (T1w) Metrics

These metrics evaluate the quality of the T1-weighted anatomical scan.

| Metric | Full Name | What It Measures | Why It Matters |
|--------|-----------|------------------|----------------|
| **SNR** | Signal-to-Noise Ratio (GM) | Ratio of mean gray-matter signal to background noise | Low SNR means noisy images — segmentation and registration become unreliable |
| **CNR** | Contrast-to-Noise Ratio | Difference between gray and white matter signal, relative to noise | Low CNR makes it hard to distinguish tissue types; affects parcellation accuracy |
| **CJV** | Coefficient of Joint Variation | Overlap between GM and WM intensity distributions | High CJV signals motion blur or severe B1-field inhomogeneity — tissues become indistinguishable |
| **INU range** | Intensity Non-Uniformity Range | Spread of the estimated bias field | Large values indicate strong B1 shading across the image, which distorts tissue intensities |
| **QI1** | Quality Index 1 | Proportion of artifact-contaminated voxels in the air background | High QI1 means ringing, ghosting, or wrap-around artifacts are present outside the head |

---

## Functional (BOLD) Metrics

These metrics evaluate the quality of each functional (BOLD) run.

| Metric | Full Name | What It Measures | Why It Matters |
|--------|-----------|------------------|----------------|
| **tSNR** | Temporal Signal-to-Noise Ratio | Mean signal divided by temporal standard deviation, averaged across the brain | Low tSNR means the BOLD signal is noisy over time — activation detection suffers |
| **FD mean** | Mean Framewise Displacement | Average volume-to-volume head movement (mm) | High FD indicates excessive head motion — corrupts both activation and connectivity analyses |
| **GSR X** | Ghost-to-Signal Ratio (X) | Ratio of ghost signal to true signal along the X (frequency-encode) direction | High GSR means EPI ghosting artifacts are present, which can overlap with brain signal |
| **GSR Y** | Ghost-to-Signal Ratio (Y) | Same as GSR X but along Y (phase-encode) direction | Phase-encode ghosting is more common; high values suggest shimming or acquisition problems |
| **AOR** | AFNI Outlier Ratio | Fraction of volumes flagged as intensity outliers by AFNI's 3dToutcount | High AOR means many time-points have unexpected signal — often from motion or scanner spikes |

---

## How to Read Carpet Plots

Carpet plots are the gold-standard visual QC tool for fMRI temporal data.
They are shown as collapsible panels below each BOLD row in the report.

### Anatomy of a Carpet Plot

- **Rows** = brain voxels (grouped by tissue type: cortical gray matter,
  subcortical, white matter, CSF)
- **Columns** = time-points (TRs), left to right
- **Color** = signal intensity (normalized)
- **Traces above the carpet** = summary time-series, typically framewise
  displacement (FD) and DVARS

### What to Look For

| Pattern | What It Means | Action |
|---------|---------------|--------|
| **Smooth horizontal bands, no vertical stripes** | Clean data — signal is stable across time | No action needed |
| **Vertical stripes** (sharp columns of color change) | Whole-brain signal shift at those time-points — usually head motion | Check FD trace above; if isolated, scrubbing may salvage the run |
| **Slow vertical drift** (gradual color gradient left-to-right) | Scanner drift or physiological low-frequency noise | Usually removed by high-pass filtering in preprocessing |
| **Bright/dark horizontal bands in CSF rows** | CSF pulsation — expected physiological noise | Normal; confound regression handles this |
| **Large blocks of vertical stripes** | Sustained period of motion | If >20% of the run is affected, consider re-scanning |
| **Global intensity shift** (entire carpet changes color at one point) | Scanner spike or subject repositioning | Check if fMRIPrep motion correction recovered the run |

### Tips

- Compare carpet plots across sessions for the same subject — consistent
  quality suggests reliable data.
- If the FD trace shows spikes but the carpet looks clean, motion correction
  was effective.
- If the carpet shows stripes but FD is low, the issue may be physiological
  (respiration, cardiac) rather than motion.

---

## Severity Badges

Each metric is color-coded based on literature-derived thresholds:

| Badge | Meaning | Action |
|-------|---------|--------|
| **OK** (green) | Value is within the normal range for fMRI data | No action needed |
| **Warning** (yellow) | Value is borderline — data may be usable but warrants inspection | Review the carpet plot and consider whether the run is critical |
| **Error** (red) | Value is outside the acceptable range | Inspect carefully; the run may need to be excluded or re-acquired |

The overall row status shows the worst severity across all metrics for that
scan. For example, if tSNR is OK but FD mean is Error, the row status is Error.

---

## Other Report Sections (Reference)

The full pipeline report includes additional sections beyond MRIQC:

- **Scan Quality** — BIDS validation checks run immediately after DICOM
  conversion (missing scans, truncated runs, parameter drift)
- **Motion Analysis** — Framewise displacement analysis from fMRIPrep confounds
  files, with per-run FD statistics and high-motion frame counts
- **Connectivity QC** — Optional Nilearn-based functional connectivity quality
  assessment using the scrubbing strategy (volume censoring, degrees-of-freedom
  loss, connectivity matrices)
- **Pipeline Failures** — Sessions that could not be fully processed, with
  stage and error details
