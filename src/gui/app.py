import customtkinter as ctk
from tkinter import filedialog, END, messagebox
import subprocess
import threading
from pathlib import Path
import sys
import os
import re
import platform
import json
import base64

# Detect platform
IS_WINDOWS = platform.system() == 'Windows'

# Cross-platform monospace font
MONO_FONT = "Consolas" if IS_WINDOWS else "Monaco" if platform.system() == 'Darwin' else "DejaVu Sans Mono"


# --- Custom Logger Widget with Colors ---
class ConsoleLog(ctk.CTkTextbox):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.configure(state="disabled", font=(MONO_FONT, 13))
        self.tag_config("info", foreground="#DCDCDC")     # Light Gray
        self.tag_config("success", foreground="#4CAF50")  # Green
        self.tag_config("warning", foreground="#FFC107")  # Amber
        self.tag_config("error", foreground="#F44336")    # Red
        self.tag_config("header", foreground="#64B5F6")   # Blue

    def log(self, message, level="info"):
        # Thread-safe UI update using after()
        self.after(0, self._log_internal, message, level)

    def _log_internal(self, message, level):
        self.configure(state="normal")
        
        # Simple keyword-based coloring
        tag = level
        if "Failed!" in message or "Error" in message or "Traceback" in message or "[FAIL]" in message:
            tag = "error"
        elif "Done." in message or "COMPLETED" in message or "[OK]" in message:
            tag = "success"
        elif "Processing" in message or "===" in message:
            tag = "header"

        self.insert(END, message + "\n", tag)
        self.see(END)
        self.configure(state="disabled")


class App(ctk.CTk):
    def __init__(self):
        # Force dark mode before initializing
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        
        super().__init__()

        # Window Setup
        self.title("fMRI Preprocessing Assistant")
        self.geometry("950x800")
        self.minsize(700, 600)
        
        # Main scrollable container
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        self.main_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.main_scroll.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.main_scroll.grid_columnconfigure(0, weight=1)
        
        # --- Header ---
        self.frame_header = ctk.CTkFrame(self.main_scroll, fg_color="transparent")
        self.frame_header.grid(row=0, column=0, padx=20, pady=(20, 5), sticky="ew")
        
        self.label_title = ctk.CTkLabel(
            self.frame_header, 
            text="fMRI Preprocessing Assistant", 
            font=ctk.CTkFont(size=26, weight="bold")
        )
        self.label_title.pack(anchor="center")
        
        self.label_subtitle = ctk.CTkLabel(
            self.frame_header, 
            text="Convert DICOM to BIDS format & Run fMRIPrep preprocessing", 
            font=ctk.CTkFont(size=14), 
            text_color="gray"
        )
        self.label_subtitle.pack(anchor="center", pady=(0, 5))

        # --- Configuration Frame ---
        self.frame_config = ctk.CTkFrame(self.main_scroll)
        self.frame_config.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        self.frame_config.grid_columnconfigure(1, weight=1)

        # Input Directory
        self.label_input = ctk.CTkLabel(
            self.frame_config, 
            text="Source Folder:",
            font=ctk.CTkFont(weight="bold")
        )
        self.label_input.grid(row=0, column=0, padx=15, pady=15, sticky="w")
        
        self.entry_input = ctk.CTkEntry(
            self.frame_config, 
            placeholder_text="DICOM folder, BIDS dataset, or previous pipeline output"
        )
        self.entry_input.grid(row=0, column=1, padx=10, pady=15, sticky="ew")
        
        self.btn_browse_input = ctk.CTkButton(
            self.frame_config, 
            text="Browse", 
            width=100, 
            command=self.browse_input
        )
        self.btn_browse_input.grid(row=0, column=2, padx=15, pady=15)

        # Output Directory
        self.label_output = ctk.CTkLabel(
            self.frame_config, 
            text="Output Root Folder:",
            font=ctk.CTkFont(weight="bold")
        )
        self.label_output.grid(row=1, column=0, padx=15, pady=15, sticky="w")
        
        self.entry_output = ctk.CTkEntry(
            self.frame_config, 
            placeholder_text="Select a NEW folder for BIDS output"
        )
        self.entry_output.grid(row=1, column=1, padx=10, pady=15, sticky="ew")
        
        self.btn_browse_output = ctk.CTkButton(
            self.frame_config, 
            text="Browse", 
            width=100, 
            command=self.browse_output
        )
        self.btn_browse_output.grid(row=1, column=2, padx=15, pady=15)

        # Output info label
        self.label_output_info = ctk.CTkLabel(
            self.frame_config,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="#888888"
        )
        self.label_output_info.grid(row=2, column=1, padx=10, pady=0, sticky="w")
        self.label_output_info.grid_remove()  # Hide initially since it's empty

        # --- BIDS Options Frame ---
        self.frame_bids_options = ctk.CTkFrame(self.main_scroll, fg_color="transparent")
        self.frame_bids_options.grid(row=2, column=0, padx=20, pady=(5, 0), sticky="ew")
        
        self.check_mriqc_with_bids = ctk.CTkCheckBox(
            self.frame_bids_options,
            text="Include MRIQC image quality assessment",
            font=ctk.CTkFont(size=12),
            onvalue=True,
            offvalue=False
        )
        self.check_mriqc_with_bids.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.check_mriqc_with_bids.deselect()  # Default: OFF

        self.check_anonymize = ctk.CTkCheckBox(
            self.frame_bids_options,
            text="Enable anonymization (remove patient info from metadata)",
            font=ctk.CTkFont(size=12),
            onvalue=True,
            offvalue=False
        )
        self.check_anonymize.grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.check_anonymize.deselect()  # Default: OFF (preserve full metadata)

        # --- fMRIPrep Options Frame (Collapsible) ---
        self.frame_fmriprep_container = ctk.CTkFrame(self.main_scroll)
        self.frame_fmriprep_container.grid(row=3, column=0, padx=20, pady=(10, 0), sticky="ew")
        self.frame_fmriprep_container.grid_columnconfigure(0, weight=1)
        
        # Header with toggle button
        self.frame_fmriprep_header = ctk.CTkFrame(self.frame_fmriprep_container, fg_color="transparent")
        self.frame_fmriprep_header.grid(row=0, column=0, sticky="ew")
        self.frame_fmriprep_header.grid_columnconfigure(1, weight=1)
        
        self.btn_toggle_fmriprep = ctk.CTkButton(
            self.frame_fmriprep_header,
            text=">",
            width=25,
            height=25,
            fg_color="transparent",
            hover_color="#333333",
            command=self._toggle_fmriprep_options
        )
        self.btn_toggle_fmriprep.grid(row=0, column=0, padx=(10, 5), pady=10)
        
        self.label_fmriprep_header = ctk.CTkLabel(
            self.frame_fmriprep_header,
            text="fMRIPrep Options (click to expand)",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.label_fmriprep_header.grid(row=0, column=1, pady=10, sticky="w")
        
        # Make header clickable
        self.label_fmriprep_header.bind("<Button-1>", lambda e: self._toggle_fmriprep_options())
        
        # Collapsible content frame
        self.frame_fmriprep_options = ctk.CTkFrame(self.frame_fmriprep_container, fg_color="#1a1a1a")
        self.fmriprep_options_visible = False  # Start collapsed
        
        # --- Output Spaces Section ---
        self.label_output_spaces = ctk.CTkLabel(
            self.frame_fmriprep_options,
            text="Output Spaces (at least one required):",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.label_output_spaces.grid(row=0, column=0, columnspan=2, padx=15, pady=(15, 5), sticky="w")
        
        self.check_space_mni = ctk.CTkCheckBox(
            self.frame_fmriprep_options,
            text="MNI152NLin2009cAsym @ 2mm (standard brain template)",
            font=ctk.CTkFont(size=11),
            command=self._validate_fmriprep_options
        )
        self.check_space_mni.grid(row=1, column=0, padx=30, pady=3, sticky="w")
        self.check_space_mni.select()  # Default: ON

        self.check_space_t1w = ctk.CTkCheckBox(
            self.frame_fmriprep_options,
            text="Native T1w space (subject's own brain)",
            font=ctk.CTkFont(size=11),
            command=self._validate_fmriprep_options
        )
        self.check_space_t1w.grid(row=2, column=0, padx=30, pady=3, sticky="w")
        self.check_space_t1w.deselect()  # Default: OFF

        # --- Processing Options Section ---
        self.label_processing = ctk.CTkLabel(
            self.frame_fmriprep_options,
            text="Processing Options:",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.label_processing.grid(row=3, column=0, columnspan=2, padx=15, pady=(15, 5), sticky="w")

        self.check_slice_timing = ctk.CTkCheckBox(
            self.frame_fmriprep_options,
            text="Slice timing correction",
            font=ctk.CTkFont(size=11)
        )
        self.check_slice_timing.grid(row=4, column=0, padx=30, pady=3, sticky="w")
        self.check_slice_timing.select()  # Default: ON

        self.check_freesurfer = ctk.CTkCheckBox(
            self.frame_fmriprep_options,
            text="FreeSurfer surface reconstruction (adds approx. 6h per subject)",
            font=ctk.CTkFont(size=11)
        )
        self.check_freesurfer.grid(row=5, column=0, padx=30, pady=3, sticky="w")
        self.check_freesurfer.deselect()  # Default: OFF (skip FreeSurfer)

        self.check_syn_sdc = ctk.CTkCheckBox(
            self.frame_fmriprep_options,
            text="Fieldmap-less distortion correction (SyN SDC)",
            font=ctk.CTkFont(size=11)
        )
        self.check_syn_sdc.grid(row=6, column=0, padx=30, pady=3, sticky="w")
        self.check_syn_sdc.deselect()  # Default: OFF
        
        # Validation warning label
        self.label_fmriprep_warning = ctk.CTkLabel(
            self.frame_fmriprep_options,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="#FFC107"
        )
        self.label_fmriprep_warning.grid(row=7, column=0, columnspan=2, padx=15, pady=(0, 10), sticky="w")

        # --- Action Buttons ---
        self.frame_actions = ctk.CTkFrame(self.main_scroll, fg_color="transparent")
        self.frame_actions.grid(row=4, column=0, padx=20, pady=10, sticky="ew")
        self.frame_actions.grid_columnconfigure((0, 1, 2, 3), weight=1)

        # Dataset summary label (above buttons, hidden until a folder is selected)
        self.label_dataset_summary = ctk.CTkLabel(
            self.frame_actions,
            text="",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#888888"
        )
        self.label_dataset_summary.grid(row=0, column=0, columnspan=4, pady=(0, 4))
        self.label_dataset_summary.grid_remove()

        self.btn_bids_only = ctk.CTkButton(
            self.frame_actions,
            text="Run BIDS Conversion",
            height=50,
            fg_color="#2E7D32",  # Green
            hover_color="#1B5E20",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.run_bids_only
        )
        self.btn_bids_only.grid(row=1, column=0, padx=10, pady=(10, 2), sticky="ew")

        self.btn_fmriprep_only = ctk.CTkButton(
            self.frame_actions,
            text="Run fMRIPrep Only",
            height=50,
            fg_color="#7B1FA2",  # Purple
            hover_color="#4A148C",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.run_fmriprep_only
        )
        self.btn_fmriprep_only.grid(row=1, column=1, padx=10, pady=(10, 2), sticky="ew")

        self.btn_connectivity_qc = ctk.CTkButton(
            self.frame_actions,
            text="Run Connectivity QC",
            height=50,
            fg_color="#00796B",  # Teal
            hover_color="#004D40",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.run_connectivity_qc_only
        )
        self.btn_connectivity_qc.grid(row=1, column=2, padx=10, pady=(10, 2), sticky="ew")

        self.btn_full_pipeline = ctk.CTkButton(
            self.frame_actions,
            text="Run Full Pipeline",
            height=50,
            fg_color="#1565C0",  # Blue
            hover_color="#0D47A1",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.run_full_pipeline
        )
        self.btn_full_pipeline.grid(row=1, column=3, padx=10, pady=(10, 2), sticky="ew")

        # Time estimate / requirement labels (below each button)
        est_font = ctk.CTkFont(size=11)
        est_color = "#888888"
        est_wrap = 160  # wrap text to fit within the button column width
        self.label_est_bids = ctk.CTkLabel(
            self.frame_actions, text="", font=est_font,
            text_color=est_color, wraplength=est_wrap)
        self.label_est_bids.grid(row=2, column=0, pady=(0, 6))
        self.label_est_bids.grid_remove()

        self.label_est_fmriprep = ctk.CTkLabel(
            self.frame_actions, text="", font=est_font,
            text_color=est_color, wraplength=est_wrap)
        self.label_est_fmriprep.grid(row=2, column=1, pady=(0, 6))
        self.label_est_fmriprep.grid_remove()

        self.label_est_conn = ctk.CTkLabel(
            self.frame_actions, text="", font=est_font,
            text_color=est_color, wraplength=est_wrap)
        self.label_est_conn.grid(row=2, column=2, pady=(0, 6))
        self.label_est_conn.grid_remove()

        self.label_est_full = ctk.CTkLabel(
            self.frame_actions, text="", font=est_font,
            text_color=est_color, wraplength=est_wrap)
        self.label_est_full.grid(row=2, column=3, pady=(0, 6))
        self.label_est_full.grid_remove()
        
        # Internal state for pipeline steps (not shown in UI)
        self._run_bids = True
        self._run_fmriprep = False
        self._fmriprep_only_mode = False
        self._connectivity_only_mode = False

        # Store original button colors for enable/disable toggling
        self._btn_colors = {
            "bids":      ("#2E7D32", "#1B5E20"),
            "fmriprep":  ("#7B1FA2", "#4A148C"),
            "conn":      ("#00796B", "#004D40"),
            "full":      ("#1565C0", "#0D47A1"),
        }
        self._disabled_color = "#555555"

        # Start with all buttons disabled until folders are selected
        self._update_button_states()

        # --- Progress Indicator ---
        self.frame_progress = ctk.CTkFrame(self.main_scroll, fg_color="transparent")
        self.frame_progress.grid(row=5, column=0, padx=20, pady=(10, 5), sticky="ew")
        self.frame_progress.grid_columnconfigure(0, weight=1)
        self.frame_progress.grid_remove()  # Hide initially
        
        self.progress_bar = ctk.CTkProgressBar(self.frame_progress, mode="determinate")
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        self.progress_bar.set(0)
        
        # Progress tracking variables
        self.total_tasks = 0
        self.completed_tasks = 0
        self.current_process = None
        self.current_output_folder = None
        
        # Progress animation variables
        self.progress_animation_id = None
        self.current_progress = 0.0
        self.target_progress = 0.0
        self.task_in_progress = False

        # --- Log Area ---
        self.label_logs = ctk.CTkLabel(
            self.main_scroll, 
            text="Execution Logs",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.label_logs.grid(row=6, column=0, padx=20, pady=(10, 0), sticky="w")
        
        self.console = ConsoleLog(self.main_scroll, height=250)
        self.console.grid(row=7, column=0, padx=20, pady=(5, 20), sticky="ew")

        self.is_running = False
        

    def browse_input(self):
        folder = filedialog.askdirectory(title="Select Source Folder")
        if folder:
            self.entry_input.delete(0, "end")
            self.entry_input.insert(0, folder)
            self._update_output_info()
            self._update_button_states()

    def browse_output(self):
        initial_dir = None
        input_dir = self.entry_input.get().strip()
        if input_dir:
            try:
                initial_dir = str(Path(input_dir).resolve().parent)
            except Exception:
                initial_dir = None

        if initial_dir:
            folder = filedialog.askdirectory(
                title="Select Output Root Folder",
                initialdir=initial_dir
            )
        else:
            folder = filedialog.askdirectory(title="Select Output Root Folder")

        if folder:
            self.entry_output.delete(0, "end")
            self.entry_output.insert(0, folder)
            self._update_output_info()
            self._update_button_states()

    def _update_output_info(self):
        """Update the output info label to show where files will be saved."""
        output_dir = self.entry_output.get()
        if output_dir:
            output_path = Path(output_dir) / "output_<timestamp>"
            self.label_output_info.configure(
                text=f"→ All the results will be saved to: {output_path}"
            )
            self.label_output_info.grid()  # Show the label
        else:
            self.label_output_info.grid_remove()  # Hide when empty

    # --- Time-estimate constants (minutes) ---
    _BIDS_MIN_PER_SESSION = 2        # BIDS conversion + QC per session
    _FMRIPREP_MIN_PER_SUBJECT = 300  # ~5 hours per subject (all sessions)
    _MRIQC_MIN_PER_SUBJECT = 20      # ~20 min per subject
    _CONNECTIVITY_MIN_PER_SUBJECT = 8

    def _update_button_states(self):
        """Enable/disable buttons based on what the source folder contains.

        The Source folder can point to:
        - Raw DICOM data  -> enables BIDS Conversion and Full Pipeline
        - A BIDS dataset  -> enables fMRIPrep Only (and the above)
        - Pipeline output with derivatives/ -> enables Connectivity QC (and the above)

        The Output folder is always just a destination for results.
        """
        input_dir = self.entry_input.get().strip()

        has_subjects = False
        has_bids_data = False
        has_derivatives = False

        if input_dir and Path(input_dir).is_dir():
            src = Path(input_dir)

            # Check for output_* subfolders (previous pipeline run) and
            # auto-resolve to the most recent one
            output_subs = sorted(
                [p for p in src.iterdir()
                 if p.is_dir() and p.name.startswith("output_")],
                key=lambda p: p.stat().st_mtime, reverse=True
            )
            check_path = output_subs[0] if output_subs else src

            has_subjects = any(
                p.is_dir() and not p.name.startswith(".")
                for p in src.iterdir()
            )
            has_bids_data = (
                any(p.name.startswith("sub-") and p.is_dir()
                    for p in check_path.iterdir())
                and (check_path / "dataset_description.json").exists()
            )
            has_derivatives = (check_path / "derivatives").is_dir()

        # --- Apply button states ---
        # BIDS Conversion: needs any subject-like folders (raw DICOMs)
        self._set_button_enabled(
            self.btn_bids_only, self.label_est_bids, "bids",
            enabled=has_subjects,
            reason="Select a Source DICOM Folder"
        )

        # Full Pipeline: same as BIDS Conversion
        self._set_button_enabled(
            self.btn_full_pipeline, self.label_est_full, "full",
            enabled=has_subjects,
            reason="Select a Source DICOM Folder"
        )

        # fMRIPrep Only: needs BIDS data (sub-* + dataset_description.json)
        self._set_button_enabled(
            self.btn_fmriprep_only, self.label_est_fmriprep, "fmriprep",
            enabled=has_bids_data,
            reason="Source must contain BIDS data (sub-* folders)"
        )

        # Connectivity QC: needs fMRIPrep derivatives
        self._set_button_enabled(
            self.btn_connectivity_qc, self.label_est_conn, "conn",
            enabled=has_derivatives,
            reason="Source must contain fMRIPrep output (derivatives/)"
        )

        # Update time estimates for enabled buttons
        self._update_time_estimates()

    def _set_button_enabled(self, btn, est_label, color_key, enabled, reason):
        """Enable or disable a button with visual feedback."""
        if enabled:
            fg, hover = self._btn_colors[color_key]
            btn.configure(state="normal", fg_color=fg, hover_color=hover)
        else:
            btn.configure(
                state="disabled",
                fg_color=self._disabled_color,
                hover_color=self._disabled_color
            )
            est_label.configure(text=reason, text_color="#aa4444")
            est_label.grid()

    @staticmethod
    def _fmt_time(minutes):
        """Format minutes as 'Xh XXmin' or 'XXmin'."""
        if minutes < 60:
            return f"{minutes:.0f}min"
        h = int(minutes // 60)
        m = int(minutes % 60)
        if m == 0:
            return f"{h}h"
        return f"{h}h {m:02d}min"

    def _update_time_estimates(self):
        """Scan the source folder and update dataset summary + time labels."""
        input_dir = self.entry_input.get().strip()

        if not input_dir or not Path(input_dir).is_dir():
            self.label_dataset_summary.grid_remove()
            self.check_mriqc_with_bids.configure(
                text="Include MRIQC image quality assessment"
            )
            return

        # Count subjects and sessions
        n_subjects = 0
        n_sessions = 0
        src = Path(input_dir)
        for child in src.iterdir():
            if child.is_dir() and not child.name.startswith("."):
                n_subjects += 1
                ses_count = sum(
                    1 for s in child.iterdir()
                    if s.is_dir() and not s.name.startswith(".")
                )
                n_sessions += max(ses_count, 1)

        if n_subjects == 0:
            self.label_dataset_summary.grid_remove()
            self.check_mriqc_with_bids.configure(
                text="Include MRIQC image quality assessment"
            )
            return

        # Show dataset summary above buttons
        self.label_dataset_summary.configure(
            text=f"Detected {n_subjects} subject(s), {n_sessions} session(s)"
        )
        self.label_dataset_summary.grid()

        # Compute estimates
        bids_min = n_sessions * self._BIDS_MIN_PER_SESSION
        fmriprep_min = n_subjects * self._FMRIPREP_MIN_PER_SUBJECT
        conn_min = n_subjects * self._CONNECTIVITY_MIN_PER_SUBJECT
        full_min = bids_min + fmriprep_min + conn_min

        # Update time labels below enabled buttons only
        # (disabled buttons keep their requirement text from _update_button_states)
        btn_label_pairs = [
            (self.btn_bids_only, self.label_est_bids, bids_min),
            (self.btn_fmriprep_only, self.label_est_fmriprep, fmriprep_min),
            (self.btn_connectivity_qc, self.label_est_conn, conn_min),
            (self.btn_full_pipeline, self.label_est_full, full_min),
        ]
        for btn, lbl, minutes in btn_label_pairs:
            if str(btn.cget("state")) != "disabled":
                lbl.configure(
                    text=f"approx. {self._fmt_time(minutes)}",
                    text_color="#888888"
                )
                lbl.grid()

        # Update MRIQC checkbox with total estimate
        mriqc_min = n_subjects * self._MRIQC_MIN_PER_SUBJECT
        self.check_mriqc_with_bids.configure(
            text=f"Include MRIQC image quality assessment (approx. {self._fmt_time(mriqc_min)})"
        )

    def _toggle_fmriprep_options(self):
        """Toggle the visibility of fMRIPrep options panel."""
        if self.fmriprep_options_visible:
            self.frame_fmriprep_options.grid_remove()
            self.btn_toggle_fmriprep.configure(text=">")
            self.label_fmriprep_header.configure(text="fMRIPrep Options (click to expand)")
            self.fmriprep_options_visible = False
        else:
            self.frame_fmriprep_options.grid(row=1, column=0, sticky="ew", padx=5, pady=(0, 10))
            self.btn_toggle_fmriprep.configure(text="v")
            self.label_fmriprep_header.configure(text="fMRIPrep Options")
            self.fmriprep_options_visible = True

    def _validate_fmriprep_options(self):
        """Validate fMRIPrep options and show warnings for invalid combinations."""
        warnings = []
        
        # Check that at least one output space is selected
        if not self.check_space_mni.get() and not self.check_space_t1w.get():
            warnings.append("Select at least one output space")
        
        if warnings:
            self.label_fmriprep_warning.configure(text=" | ".join(warnings))
        else:
            self.label_fmriprep_warning.configure(text="")
        
        return len(warnings) == 0

    def _get_fmriprep_options(self):
        options = {}
        
        # Output spaces
        spaces = []
        if self.check_space_mni.get():
            spaces.append("MNI152NLin2009cAsym:res-2")
        if self.check_space_t1w.get():
            spaces.append("T1w")
        if spaces:
            options["output_spaces"] = spaces
        
        # FreeSurfer
        options["fs_reconall"] = self.check_freesurfer.get()
        
        # Slice timing
        options["skip_slice_timing"] = not self.check_slice_timing.get()
        
        # SyN SDC
        options["use_syn_sdc"] = self.check_syn_sdc.get()
        
        return options
    
    def _encode_fmriprep_options(self, options):
        """Encode fMRIPrep options as base64 JSON for safe cross-platform passing."""
        json_str = json.dumps(options)
        return base64.b64encode(json_str.encode('utf-8')).decode('ascii')

    def _validate_paths(self):
        """Validate input and output paths before running."""
        input_dir = self.entry_input.get().strip()
        output_dir = self.entry_output.get().strip()

        if not input_dir:
            self.console.log("Please select a source DICOM folder.", "warning")
            return False
            
        if not output_dir:
            self.console.log("Please select an output folder.", "warning")
            return False

        # Resolve to absolute paths for comparison
        input_path = Path(input_dir).resolve()
        output_path = Path(output_dir).resolve()

        if not input_path.exists():
            self.console.log(f"Source folder does not exist: {input_dir}", "warning")
            return False

        # Prevent output inside input or same as input
        if output_path == input_path:
            self.console.log("Output folder cannot be the same as input folder!", "warning")
            self.console.log("   Please select a different output location.", "warning")
            return False

        if str(output_path).startswith(str(input_path) + os.sep):
            self.console.log("Output folder cannot be inside the input folder!", "warning")
            self.console.log("   Please select a different output location.", "warning")
            return False

        # Note: Output CAN be parent of input - timestamped subfolder will be created

        return True

    def run_bids_only(self):
        """Run BIDS conversion only, with optional MRIQC."""
        self._run_bids = True
        self._run_fmriprep = False
        self._fmriprep_only_mode = False
        if self.check_mriqc_with_bids.get():
            import importlib
            import sys
            src_dir = str(Path(__file__).parent.parent)
            if src_dir not in sys.path:
                sys.path.insert(0, src_dir)
            mriqc_module = importlib.import_module("fmriprep.mriqc_runner")
            self._run_with_docker_preflight(
                "BIDS Conversion + MRIQC",
                preflight_fn=mriqc_module.mriqc_preflight,
            )
        else:
            self._start_pipeline_internal("BIDS Conversion")

    def run_full_pipeline(self):
        """Run both BIDS conversion and fMRIPrep."""
        # Validate fMRIPrep options
        if not self._validate_fmriprep_options():
            self.console.log("Please fix fMRIPrep options before running.", "warning")
            # Expand options panel if collapsed
            if not self.fmriprep_options_visible:
                self._toggle_fmriprep_options()
            return
        
        # Run Docker preflight check before starting
        self._run_bids = True
        self._run_fmriprep = True
        self._fmriprep_only_mode = False
        self._run_with_docker_preflight("BIDS Conversion + fMRIPrep")

    def run_connectivity_qc_only(self):
        """Run connectivity QC (Nilearn) on an existing fMRIPrep output folder."""
        source_folder = self.entry_input.get().strip()

        if not source_folder:
            self.console.log("Please select a Source folder containing fMRIPrep output.", "warning")
            return

        bids_path = Path(source_folder).resolve()
        if not bids_path.exists():
            self.console.log(f"Folder does not exist: {source_folder}", "warning")
            return

        # Auto-select most recent output_* subfolder if needed
        output_subfolders = [p for p in bids_path.iterdir()
                             if p.is_dir() and p.name.startswith("output_")]
        if output_subfolders:
            most_recent = max(output_subfolders, key=lambda p: p.stat().st_mtime)
            bids_path = most_recent.resolve()
            self.console.log(f"Using output folder: {most_recent.name}", "info")

        has_subjects = any(p.name.startswith("sub-") and p.is_dir() for p in bids_path.iterdir())
        if not has_subjects:
            self.console.log("No 'sub-*' folders found. Select a folder with pipeline output.", "warning")
            return

        derivatives = bids_path / "derivatives"
        if not derivatives.exists():
            self.console.log("No 'derivatives/' folder found. fMRIPrep must run before Connectivity QC.", "warning")
            return

        self._run_bids = False
        self._run_fmriprep = False
        self._fmriprep_only_mode = False
        self._connectivity_only_mode = True
        self._connectivity_bids_folder = str(bids_path)
        self._start_pipeline_internal("Connectivity QC (Nilearn)")

    def run_fmriprep_only(self):
        """Run fMRIPrep on an existing BIDS folder (Source folder = BIDS data)."""
        # Validate fMRIPrep options
        if not self._validate_fmriprep_options():
            self.console.log("Please fix fMRIPrep options before running.", "warning")
            if not self.fmriprep_options_visible:
                self._toggle_fmriprep_options()
            return

        source_folder = self.entry_input.get().strip()

        if not source_folder:
            self.console.log("Please select a Source folder containing BIDS data.", "warning")
            return

        bids_path = Path(source_folder).resolve()
        if not bids_path.exists():
            self.console.log(f"Folder does not exist: {source_folder}", "warning")
            return

        # Auto-select most recent output_* subfolder if needed
        output_subfolders = [p for p in bids_path.iterdir()
                            if p.is_dir() and p.name.startswith("output_")]
        if output_subfolders:
            most_recent = max(output_subfolders, key=lambda p: p.stat().st_mtime)
            bids_path = most_recent.resolve()
            self.console.log(f"Using output folder: {most_recent.name}", "info")

        # Validate BIDS structure
        dataset_desc = bids_path / "dataset_description.json"
        if not dataset_desc.exists():
            self.console.log("Source folder doesn't contain BIDS data (missing dataset_description.json).", "warning")
            self.console.log("   Point Source to a folder from a previous BIDS conversion.", "info")
            return

        has_subjects = any(p.name.startswith("sub-") and p.is_dir() for p in bids_path.iterdir())
        if not has_subjects:
            self.console.log("No 'sub-*' folders found in the Source folder.", "warning")
            return

        bids_folder = str(bids_path)

        self._run_bids = False
        self._run_fmriprep = True
        self._fmriprep_only_mode = True
        self._bids_folder_for_fmriprep = bids_folder
        self._run_with_docker_preflight("fMRIPrep Only")

    def _run_with_docker_preflight(self, mode_label, preflight_fn=None):
        """Run Docker preflight checks before starting a pipeline step.

        Args:
            mode_label:   Display label shown in the log header.
            preflight_fn: Optional callable(callback) -> (bool, str|None).
                          Defaults to fMRIPrep's preflight_check if not provided.
        """
        # Clear console and show preflight status
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")

        label = "MRIQC" if preflight_fn else "fMRIPrep"
        self.console.log(f"Running pre-flight checks for{label}...", "header")
        self.console.log("=" * 60)

        # Disable buttons during preflight
        self._set_buttons_state("disabled")

        def preflight_thread():
            try:
                def log_callback(message):
                    self.console.log(message)

                if preflight_fn is not None:
                    success, error_msg = preflight_fn(callback=log_callback)
                else:
                    # Default: fMRIPrep preflight (dynamic import)
                    import importlib.util
                    runner_path = Path(__file__).parent.parent / "fmriprep" / "runner.py"
                    spec = importlib.util.spec_from_file_location("runner", runner_path)
                    if spec is None or spec.loader is None:
                        raise ImportError(f"Could not load module from {runner_path}")
                    runner_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(runner_module)
                    success, error_msg = runner_module.preflight_check(
                        callback=log_callback,
                        auto_start_docker=True,
                        auto_pull_image=True,
                    )

                if success:
                    self.console.log("")
                    self.console.log("All pre-flight checks passed!", "success")
                    self.console.log("=" * 60)
                    self.console.log("")
                    self.after(100, lambda: self._start_pipeline_internal(mode_label))
                else:
                    self.console.log("")
                    self.console.log("Pre-flight check failed:", "error")
                    if error_msg:
                        for line in error_msg.split('\n'):
                            self.console.log(f"   {line}", "error")
                    self._set_buttons_state("normal")

            except Exception as e:
                self.console.log(f"Error during pre-flight check:{e}", "error")
                self._set_buttons_state("normal")

        threading.Thread(target=preflight_thread, daemon=True).start()

    def _start_pipeline_internal(self, mode_label):
        """Start the pipeline with the configured options."""
        if self._fmriprep_only_mode:
            bids_folder = self._bids_folder_for_fmriprep
        else:
            if not self._validate_paths():
                return
            bids_folder = None

        input_dir = self.entry_input.get().strip()
        output_dir = self.entry_output.get().strip()

        self.is_running = True
        self.current_output_folder = None
        self._set_buttons_state("disabled")
        
        # Reset and show progress bar
        self.total_tasks = 0
        self.completed_tasks = 0
        self.current_progress = 0.0
        self.target_progress = 0.0
        self.task_in_progress = False
        self.progress_bar.set(0)
        self.frame_progress.grid()

        # Clear and prepare console
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")
        
        self.console.log(f"{mode_label}", "header")
        if self._fmriprep_only_mode:
            self.console.log(f"BIDS Folder: {bids_folder}")
        else:
            self.console.log(f"Source: {input_dir}")
            self.console.log(f"Output Root: {output_dir}")
        self.console.log("=" * 60)

        # Run in background thread
        threading.Thread(
            target=self.run_subprocess, 
            args=(input_dir, output_dir, bids_folder), 
            daemon=True
        ).start()

    def _set_buttons_state(self, state):
        """Enable/disable all action buttons."""
        self.btn_bids_only.configure(state=state)
        self.btn_fmriprep_only.configure(state=state)
        self.btn_connectivity_qc.configure(state=state)
        self.btn_full_pipeline.configure(state=state)
        self.btn_browse_input.configure(state=state)
        self.btn_browse_output.configure(state=state)

    def run_subprocess(self, input_dir, output_dir, bids_folder=None):
        script_path = Path(__file__).parent.parent / "orchestrator.py"
        
        # Connectivity QC only mode
        if self._connectivity_only_mode:
            cmd = [
                sys.executable, str(script_path),
                "--qc-only", "--bids-folder", self._connectivity_bids_folder,
                "--connectivity-qc"
            ]
            self._connectivity_only_mode = False
        # For fMRIPrep-only mode, use the BIDS folder as input
        elif self._fmriprep_only_mode and bids_folder:
            cmd = [
                sys.executable, str(script_path),
                "--bids-folder", bids_folder
            ]
        else:
            cmd = [
                sys.executable, str(script_path), 
                "--input", input_dir, 
                "--output_dir", output_dir
            ]

        if not self._run_bids:
            cmd.append("--skip-bids")
        if not self._run_fmriprep:
            cmd.append("--skip-fmriprep")
        if self.check_anonymize.get():
            cmd.append("--anonymize")

        # Add --run-mriqc if the MRIQC checkbox is ticked
        if self.check_mriqc_with_bids.get():
            cmd.append("--run-mriqc")

        # Add fMRIPrep options if running fMRIPrep (platform-agnostic via base64 JSON)
        if self._run_fmriprep:
            fmriprep_opts = self._get_fmriprep_options()
            if fmriprep_opts:
                encoded_opts = self._encode_fmriprep_options(fmriprep_opts)
                cmd.extend(["--fmriprep-opts", encoded_opts])

        try:
            popen_kwargs = {
                'stdout': subprocess.PIPE,
                'stderr': subprocess.STDOUT,
                'text': True,
                'bufsize': 1,
                'encoding': 'utf-8',
                'errors': 'replace'
            }
            if IS_WINDOWS:
                popen_kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs['start_new_session'] = True
            
            self.current_process = subprocess.Popen(cmd, **popen_kwargs)
            
            if self.current_process.stdout is None:
                raise RuntimeError("Failed to capture subprocess output")
            
            for line in self.current_process.stdout:
                stripped_line = line.strip()
                
                # Capture output folder path
                if stripped_line.startswith("Output folder:"):
                    self.current_output_folder = stripped_line.replace("Output folder:", "").strip()
                
                # Parse progress markers
                if stripped_line.startswith("[PROGRESS:"):
                    self._handle_progress_marker(stripped_line)
                    continue  # Don't display progress markers in console
                
                # Display all other lines
                self.console.log(stripped_line)
            
            self.current_process.wait()
            
            # Ensure progress bar reaches 100% at completion
            self.after(0, lambda: self.progress_bar.set(1.0))
            
            if self.current_process.returncode == 0:
                self.console.log("=" * 60)
                self.console.log("Conversion complete! Check your output folder for results.", "success")
                # No status message - only show errors/warnings
            else:
                self.console.log("=" * 60)
                self.console.log("Conversion finished with some problems. Check the report for details.", "error")

        except Exception as e:
            self.console.log(f"Critical Error:{e}", "error")

        # Reset UI state (thread-safe)
        self.current_process = None
        self.after(0, self._reset_ui)
    
    def _handle_progress_marker(self, marker):
        """Parse and handle progress markers from the pipeline."""
        # [PROGRESS:TOTAL:N] - Total number of tasks
        if match := re.match(r'\[PROGRESS:TOTAL:(\d+)\]', marker):
            self.total_tasks = int(match.group(1))
            self.completed_tasks = 0
            self.current_progress = 0.0
            self.target_progress = 0.0
        
        # [PROGRESS:TASK_START:N] - Task N starting
        elif match := re.match(r'\[PROGRESS:TASK_START:(\d+)\]', marker):
            if self.total_tasks > 0:
                # Set target to almost complete this task (95% of the way to next milestone)
                task_num = int(match.group(1))
                self.target_progress = (task_num + 0.95) / self.total_tasks
                self.task_in_progress = True
                self._start_progress_animation()
        
        # [PROGRESS:STAGE:stage_num:total_stages:sub_id:ses_id:stage_name] - Conversion stage update
        elif match := re.match(r'\[PROGRESS:STAGE:(\d+):(\d+):([^:]+):([^:]+):(.+)\]', marker):
            stage_num = int(match.group(1))
            total_stages = int(match.group(2))
            sub_id = match.group(3)
            ses_id = match.group(4)
            stage_name = match.group(5)
            
            # Calculate sub-progress within this task
            if self.total_tasks > 0:
                task_base = self.completed_tasks / self.total_tasks
                stage_progress = (stage_num / total_stages) / self.total_tasks
                self.target_progress = task_base + stage_progress * 0.95
            
            # Progress tracking only - no status message for normal progress
        
        # [PROGRESS:STATUS:message] - General status update (no UI status for normal messages)
        elif match := re.match(r'\[PROGRESS:STATUS:(.+)\]', marker):
            pass  # Progress tracking only - no status message
        
        # [PROGRESS:TASK:N] - Task N completed
        elif match := re.match(r'\[PROGRESS:TASK:(\d+)\]', marker):
            self.completed_tasks = int(match.group(1))
            self.task_in_progress = False
            if self.total_tasks > 0:
                # Snap to actual progress
                self.current_progress = self.completed_tasks / self.total_tasks
                self.target_progress = self.current_progress
                self.after(0, lambda p=self.current_progress: self.progress_bar.set(p))
                
                # Progress tracking only - no status message for normal progress
        
        # [PROGRESS:COMPLETE] - All done
        elif marker == "[PROGRESS:COMPLETE]":
            self._stop_progress_animation()
            self.current_progress = 1.0
            self.after(0, lambda: self.progress_bar.set(1.0))
            # No status message - only show errors/warnings
    
    def _start_progress_animation(self):
        """Start animating the progress bar gradually."""
        if self.progress_animation_id:
            self.after_cancel(self.progress_animation_id)
        self._animate_progress()
    
    def _stop_progress_animation(self):
        """Stop the progress animation."""
        if self.progress_animation_id:
            self.after_cancel(self.progress_animation_id)
            self.progress_animation_id = None
    
    def _animate_progress(self):
        """Gradually animate progress towards target."""
        if not self.task_in_progress:
            self.progress_animation_id = None
            return
        
        # Gradually move towards target (ease out effect)
        if self.current_progress < self.target_progress:
            # Move 2% of remaining distance each tick
            remaining = self.target_progress - self.current_progress
            increment = max(0.001, remaining * 0.02)  # At least 0.1% per tick
            self.current_progress = min(self.target_progress, self.current_progress + increment)
            self.progress_bar.set(self.current_progress)
        
        # Continue animation every 100ms
        self.progress_animation_id = self.after(100, self._animate_progress)

    def _reset_ui(self):
        self.is_running = False
        self.task_in_progress = False
        self._stop_progress_animation()
        self.current_progress = 0.0
        self.target_progress = 0.0
        self.progress_bar.set(0)
        self.frame_progress.grid_remove()
        self._set_buttons_state("normal")


if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()
