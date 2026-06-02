import multiprocessing

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
        self.minsize(750, 600)
        
        # Capture default button theme colours (used to toggle enabled state)
        _probe_btn = ctk.CTkButton(self, width=1)
        self._default_btn_color = _probe_btn.cget("fg_color")
        self._default_btn_hover = _probe_btn.cget("hover_color")
        _probe_btn.destroy()

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

        # Input Directory (Multi-Folder Support)
        self.label_input = ctk.CTkLabel(
            self.frame_config, 
            text="Source Folders:",
            font=ctk.CTkFont(weight="bold")
        )
        self.label_input.grid(row=0, column=0, padx=15, pady=(15, 0), sticky="nw")
        
        # Scrollable frame for input folders
        self.frame_input_list = ctk.CTkScrollableFrame(self.frame_config, height=100)
        self.frame_input_list.grid(row=0, column=1, padx=10, pady=15, sticky="ew")
        self.frame_input_list.grid_columnconfigure(0, weight=1)
        
        self.input_folders = []
        self._input_labels = []

        # Buttons for input
        self.frame_input_btns = ctk.CTkFrame(self.frame_config, fg_color="transparent")
        self.frame_input_btns.grid(row=0, column=2, padx=15, pady=15, sticky="n")

        self.btn_add_input = ctk.CTkButton(
            self.frame_input_btns, 
            text="Add Folder", 
            width=100, 
            command=self.add_input_folder
        )
        self.btn_add_input.pack(pady=(0, 5))

        self.btn_clear_input = ctk.CTkButton(
            self.frame_input_btns, 
            text="Clear All", 
            width=100, 
            fg_color="#D32F2F",
            hover_color="#B71C1C",
            command=self.clear_input_folders
        )
        self.btn_clear_input.pack()

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

        # --- fMRIPrep Options Frame (Collapsible) ---
        self.frame_fmriprep_container = ctk.CTkFrame(self.main_scroll)
        self.frame_fmriprep_container.grid(row=4, column=0, padx=20, pady=(10, 0), sticky="ew")
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

        self.check_anonymize = ctk.CTkCheckBox(
            self.frame_fmriprep_options,
            text="Anonymize DICOM metadata (remove patient info)",
            font=ctk.CTkFont(size=11)
        )
        self.check_anonymize.grid(row=7, column=0, padx=30, pady=3, sticky="w")
        self.check_anonymize.deselect()  # Default: OFF (preserve full metadata)

        # Validation warning label
        self.label_fmriprep_warning = ctk.CTkLabel(
            self.frame_fmriprep_options,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="#FFC107"
        )
        self.label_fmriprep_warning.grid(row=8, column=0, columnspan=2, padx=15, pady=(0, 10), sticky="w")

        # --- Quality Check Thresholds (Collapsible) ---
        self._build_qc_thresholds_section()

        # --- Researcher Comments ---
        self.frame_comments = ctk.CTkFrame(self.main_scroll)
        self.frame_comments.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        self.frame_comments.grid_columnconfigure(0, weight=1)

        self.label_comments = ctk.CTkLabel(
            self.frame_comments,
            text="Researcher Comments:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.label_comments.grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")

        self.text_researcher_comments = ctk.CTkTextbox(
            self.frame_comments,
            height=90,
            wrap="word",
            font=ctk.CTkFont(size=13),
        )
        self.text_researcher_comments.grid(row=1, column=0, padx=15, pady=(0, 5), sticky="ew")

        # Placeholder text — shown while the textbox is empty and unfocused
        self._comments_placeholder = (
            "Enter session notes (e.g., excessive motion, technical issues, "
            "task performance, participant alertness, or any deviations from protocol)"
        )
        self._comments_placeholder_active = True
        self.text_researcher_comments.insert("1.0", self._comments_placeholder)
        self.text_researcher_comments.configure(text_color="#888888")
        self.text_researcher_comments.bind("<FocusIn>", self._comments_focus_in)
        self.text_researcher_comments.bind("<FocusOut>", self._comments_focus_out)

        # Save button + saved-state tracking
        self._saved_comments_text = ""  # Last saved text

        self.btn_save_comments = ctk.CTkButton(
            self.frame_comments,
            text="Save Comments",
            width=140,
            height=30,
            fg_color="#555555",
            state="disabled",
            command=self._save_researcher_comments,
        )
        self.btn_save_comments.grid(row=2, column=0, padx=15, pady=(2, 12), sticky="e")

        # Re-evaluate Save button whenever text changes
        self.text_researcher_comments.bind("<KeyRelease>", self._on_comments_changed)

        # --- Action Buttons ---
        self.frame_actions = ctk.CTkFrame(self.main_scroll, fg_color="transparent")
        self.frame_actions.grid(row=6, column=0, padx=20, pady=10, sticky="ew")
        self.frame_actions.grid_columnconfigure((0, 1, 2, 3, 4), weight=1, uniform="btn")

        # Dataset summary label (above buttons, hidden until a folder is selected)
        self.label_dataset_summary = ctk.CTkLabel(
            self.frame_actions,
            text="",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#888888"
        )
        self.label_dataset_summary.grid(row=0, column=0, columnspan=5, pady=(0, 4))
        self.label_dataset_summary.grid_remove()

        self.btn_bids_only = ctk.CTkButton(
            self.frame_actions,
            text="BIDS Only",
            height=50,
            fg_color="#2E7D32",  # Green
            hover_color="#1B5E20",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.run_bids_only
        )
        self.btn_bids_only.grid(row=1, column=0, padx=10, pady=(10, 2), sticky="ew")

        self.btn_mriqc_only = ctk.CTkButton(
            self.frame_actions,
            text="BIDS + MRIQC",
            height=50,
            fg_color="#F57F17",  # Amber/dark yellow
            hover_color="#E65100",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.run_mriqc_only
        )
        self.btn_mriqc_only.grid(row=1, column=1, padx=10, pady=(10, 2), sticky="ew")

        self.btn_fmriprep_only = ctk.CTkButton(
            self.frame_actions,
            text="fMRIPrep Only",
            height=50,
            fg_color="#7B1FA2",  # Purple
            hover_color="#4A148C",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.run_fmriprep_only
        )
        self.btn_fmriprep_only.grid(row=1, column=2, padx=10, pady=(10, 2), sticky="ew")

        self.btn_connectivity_qc = ctk.CTkButton(
            self.frame_actions,
            text="Connectivity QC Only",
            height=50,
            fg_color="#00796B",  # Teal
            hover_color="#004D40",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.run_connectivity_qc_only
        )
        self.btn_connectivity_qc.grid(row=1, column=3, padx=10, pady=(10, 2), sticky="ew")

        self.btn_full_pipeline = ctk.CTkButton(
            self.frame_actions,
            text="Full Pipeline",
            height=50,
            fg_color="#1565C0",  # Blue
            hover_color="#0D47A1",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.run_full_pipeline
        )
        self.btn_full_pipeline.grid(row=1, column=4, padx=10, pady=(10, 2), sticky="ew")

        # --- Stability & Advanced Options (Main Dashboard) ---
        self.frame_stability = ctk.CTkFrame(self.frame_actions, fg_color="transparent")
        self.frame_stability.grid(row=3, column=0, columnspan=5, padx=10, pady=(15, 0), sticky="ew")
        
        # Column 0: Skip MRIQC
        self.check_skip_mriqc = ctk.CTkCheckBox(
            self.frame_stability,
            text="Skip MRIQC",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#FFB300"
        )
        self.check_skip_mriqc.grid(row=0, column=0, padx=(0, 15), sticky="w")
        self.check_skip_mriqc.select()

        # Column 1: Connectivity QC
        self.check_connectivity = ctk.CTkCheckBox(
            self.frame_stability,
            text="Connectivity QC",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.check_connectivity.grid(row=0, column=1, padx=(0, 15), sticky="w")
        self.check_connectivity.select()

        # Column 2: Strategy Dropdown
        self.label_strat = ctk.CTkLabel(self.frame_stability, text="Strategy:", font=ctk.CTkFont(size=11))
        self.label_strat.grid(row=0, column=2, padx=(10, 2), sticky="e")
        self.combo_strategy = ctk.CTkComboBox(
            self.frame_stability,
            values=["anatomical", "global", "both"],
            width=100,
            font=ctk.CTkFont(size=11)
        )
        self.combo_strategy.set("anatomical")
        self.combo_strategy.grid(row=0, column=3, padx=(0, 15), sticky="w")

        # Column 3: Atlas Dropdown
        self.label_atlas = ctk.CTkLabel(self.frame_stability, text="Atlas:", font=ctk.CTkFont(size=11))
        self.label_atlas.grid(row=0, column=4, padx=(10, 2), sticky="e")
        self.combo_atlas = ctk.CTkComboBox(
            self.frame_stability,
            values=["Schaefer-116", "Schaefer-432 (Amir's)"],
            width=120,
            font=ctk.CTkFont(size=11)
        )
        self.combo_atlas.set("Schaefer-116")
        self.combo_atlas.grid(row=0, column=5, padx=(0, 15), sticky="w")

        # Column 4: Parallel Workers
        self.label_parallel = ctk.CTkLabel(self.frame_stability, text="Parallel:", font=ctk.CTkFont(size=11))
        self.label_parallel.grid(row=0, column=6, padx=(10, 2), sticky="e")
        
        # Safe default: 1 worker per 20GB RAM
        try:
            from core.utils import get_available_memory_gb
            avail_gb = get_available_memory_gb()
            safe_workers = max(int(avail_gb // 20), 1)
        except:
            safe_workers = 2

        self.slider_parallel = ctk.CTkSlider(
            self.frame_stability,
            from_=1,
            to=min(multiprocessing.cpu_count(), 12),
            number_of_steps=min(multiprocessing.cpu_count(), 12) - 1,
            width=80,
            command=self._update_parallel_label
        )
        self.slider_parallel.set(safe_workers)
        self.slider_parallel.grid(row=0, column=7, padx=5, sticky="ew")

        self.label_parallel_val = ctk.CTkLabel(
            self.frame_stability,
            text=str(safe_workers),
            width=20,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.label_parallel_val.grid(row=0, column=8, sticky="w")

        # Time estimate / requirement labels (below each button)
        est_font = ctk.CTkFont(size=11)
        est_color = "#888888"
        est_wrap = 140  # wrap text to fit within the button column width
        est_grid = dict(row=2, pady=(0, 6), sticky="ew")

        self.label_est_bids = ctk.CTkLabel(
            self.frame_actions, text="", font=est_font,
            text_color=est_color, wraplength=est_wrap)
        self.label_est_bids.grid(column=0, **est_grid)
        self.label_est_bids.grid_remove()

        self.label_est_mriqc = ctk.CTkLabel(
            self.frame_actions, text="", font=est_font,
            text_color=est_color, wraplength=est_wrap)
        self.label_est_mriqc.grid(column=1, **est_grid)
        self.label_est_mriqc.grid_remove()

        self.label_est_fmriprep = ctk.CTkLabel(
            self.frame_actions, text="", font=est_font,
            text_color=est_color, wraplength=est_wrap)
        self.label_est_fmriprep.grid(column=2, **est_grid)
        self.label_est_fmriprep.grid_remove()

        self.label_est_conn = ctk.CTkLabel(
            self.frame_actions, text="", font=est_font,
            text_color=est_color, wraplength=est_wrap)
        self.label_est_conn.grid(column=3, **est_grid)
        self.label_est_conn.grid_remove()

        self.label_est_full = ctk.CTkLabel(
            self.frame_actions, text="", font=est_font,
            text_color=est_color, wraplength=est_wrap)
        self.label_est_full.grid(column=4, **est_grid)
        self.label_est_full.grid_remove()

        # Internal state for pipeline steps (not shown in UI)
        self._run_bids = True
        self._run_fmriprep = False
        self._run_mriqc = True
        self._fmriprep_only_mode = False
        self._connectivity_only_mode = False

        # Store original button colors for enable/disable toggling
        self._btn_colors = {
            "bids":      ("#2E7D32", "#1B5E20"),
            "mriqc":     ("#F57F17", "#E65100"),
            "fmriprep":  ("#7B1FA2", "#4A148C"),
            "conn":      ("#00796B", "#004D40"),
            "full":      ("#1565C0", "#0D47A1"),
        }
        self._disabled_color = "#555555"

        # Start with all buttons disabled until folders are selected
        self._update_button_states()

        # --- Progress Indicator ---
        self.frame_progress = ctk.CTkFrame(self.main_scroll, fg_color="transparent")
        self.frame_progress.grid(row=7, column=0, padx=20, pady=(10, 5), sticky="ew")
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
        self.label_logs.grid(row=8, column=0, padx=20, pady=(10, 0), sticky="w")

        self.console = ConsoleLog(self.main_scroll, height=250)
        self.console.grid(row=9, column=0, padx=20, pady=(5, 20), sticky="ew")

        self.is_running = False
        

    @property
    def primary_input(self):
        """Returns the first input folder or empty string."""
        return self.input_folders[0] if self.input_folders else ""

    def add_input_folder(self):
        folder = filedialog.askdirectory(title="Add Source Folder")
        if folder:
            folder_path = str(Path(folder).resolve())
            if folder_path not in self.input_folders:
                self.input_folders.append(folder_path)
                self._refresh_input_list()
                self._update_output_info()
                self._update_button_states()

    def clear_input_folders(self):
        self.input_folders = []
        self._refresh_input_list()
        self._update_output_info()
        self._update_button_states()

    def _refresh_input_list(self):
        # Clear existing widgets in the frame
        for widget in self.frame_input_list.winfo_children():
            widget.destroy()
        
        if not self.input_folders:
            lbl = ctk.CTkLabel(self.frame_input_list, text="No folders selected", text_color="gray")
            lbl.pack(pady=10)
            return

        for i, path in enumerate(self.input_folders):
            row_frame = ctk.CTkFrame(self.frame_input_list, fg_color="transparent")
            row_frame.pack(fill="x", padx=5, pady=2)
            
            # Use a shorter display path if it's very long
            display_path = path
            if len(path) > 60:
                display_path = "..." + path[-57:]
                
            lbl = ctk.CTkLabel(row_frame, text=f"{i+1}. {display_path}", anchor="w")
            lbl.pack(side="left", fill="x", expand=True)
            
            # Individual remove button
            btn = ctk.CTkButton(
                row_frame, text="X", width=25, height=20, 
                fg_color="#D32F2F", hover_color="#B71C1C",
                command=lambda p=path: self._remove_input_folder(p)
            )
            btn.pack(side="right", padx=5)

    def _remove_input_folder(self, path):
        if path in self.input_folders:
            self.input_folders.remove(path)
            self._refresh_input_list()
            self._update_output_info()
            self._update_button_states()

    def browse_output(self):
        initial_dir = None
        input_dir = self.primary_input
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

    # --- Researcher Comments helpers ---

    def _comments_focus_in(self, _event=None):
        """Remove placeholder text when the user clicks into the comments box."""
        if self._comments_placeholder_active:
            self.text_researcher_comments.delete("1.0", "end")
            self.text_researcher_comments.configure(text_color="#DCDCDC")
            self._comments_placeholder_active = False

    def _comments_focus_out(self, _event=None):
        """Restore placeholder if the comments box is empty when focus leaves."""
        content = self.text_researcher_comments.get("1.0", "end-1c").strip()
        if not content:
            self._comments_placeholder_active = True
            self.text_researcher_comments.insert("1.0", self._comments_placeholder)
            self.text_researcher_comments.configure(text_color="#888888")

    def _get_researcher_comments(self) -> str:
        """Return the current comments text, ignoring the placeholder."""
        if self._comments_placeholder_active:
            return ""
        return self.text_researcher_comments.get("1.0", "end-1c").strip()

    def _on_comments_changed(self, _event=None):
        """Enable the Save button only if text differs from last saved version."""
        current = self._get_researcher_comments()
        if current and current != self._saved_comments_text:
            self.btn_save_comments.configure(
                state="normal", fg_color=self._default_btn_color,
                hover_color=self._default_btn_hover
            )
        else:
            self.btn_save_comments.configure(
                state="disabled", fg_color="#555555"
            )

    def _save_researcher_comments(self):
        """Save the current comments and disable the button until text changes."""
        self._saved_comments_text = self._get_researcher_comments()
        self.btn_save_comments.configure(state="disabled", fg_color="#555555")
        # Write to the comments file so the running pipeline picks up changes
        self._write_comments_file()
        self.console.log("Researcher comments saved.", "success")

    def _write_comments_file(self):
        """Write current comments to the output folder so the orchestrator
        can read the latest version just before generating reports."""
        folder = self.current_output_folder
        if not folder:
            return  # Pipeline hasn't started yet or folder unknown
        try:
            comments_path = Path(folder) / "execution_logs" / ".researcher_comments.txt"
            comments_path.parent.mkdir(parents=True, exist_ok=True)
            comments_path.write_text(self._saved_comments_text or "", encoding="utf-8")
        except Exception:
            pass  # Best-effort; don't disrupt the user

    # --- Time-estimate constants (minutes) ---
    _BIDS_MIN_PER_SESSION = 2        # BIDS conversion + QC per session
    _FMRIPREP_MIN_PER_SUBJECT = 300  # ~5 hours per subject (all sessions)
    _MRIQC_MIN_PER_SUBJECT = 20      # ~20 min per subject
    _CONNECTIVITY_MIN_PER_SUBJECT = 8

    # ------------------------------------------------------------------
    # Folder-type detectors
    # ------------------------------------------------------------------

    @staticmethod
    def _has_bids_nifti(root):
        """Return True if *root* is a BIDS dataset with raw NIfTI data.

        Checks for:
        1. ``dataset_description.json`` at the root (BIDS marker).
        2. At least one ``sub-*`` folder **directly** under root (not
           inside ``derivatives/``).
        3. At least one ``.nii`` or ``.nii.gz`` file inside a top-level
           ``sub-*`` tree (raw imaging data, not derivatives).

        This deliberately ignores ``derivatives/sub-*`` so that the
        fMRIPrep-Only button only lights up when actual raw BIDS data
        is present.
        """
        if not (root / "dataset_description.json").exists():
            return False

        for sub in root.iterdir():
            if not (sub.is_dir() and sub.name.startswith("sub-")):
                continue
            # Walk at most two levels (sub-*/[ses-*/]{anat,func}/*.nii*)
            search_dirs = [sub]
            for ses in sub.iterdir():
                if ses.is_dir() and ses.name.startswith("ses-"):
                    search_dirs.append(ses)
            for parent in search_dirs:
                for modality in ("anat", "func"):
                    mod_dir = parent / modality
                    if not mod_dir.is_dir():
                        continue
                    for f in mod_dir.iterdir():
                        if f.name.endswith((".nii", ".nii.gz")):
                            return True
        return False

    @staticmethod
    def _has_fmriprep_derivatives(root):
        """Return True if *root* contains fMRIPrep derivative results.

        Looks for the fMRIPrep-specific confounds file
        (``*_desc-confounds_timeseries.tsv``) under ``derivatives/``.
        This file is unique to fMRIPrep output and cannot be confused
        with raw BIDS data or MRIQC results.

        Searches in both ``derivatives/fmriprep/sub-*`` (nipreps layout)
        and ``derivatives/sub-*`` (flat layout) to cover all variants.
        """
        deriv = root / "derivatives"
        if not deriv.is_dir():
            return False

        # Candidate roots that may contain sub-* result folders
        search_roots = [deriv]
        fmriprep_dir = deriv / "fmriprep"
        if fmriprep_dir.is_dir():
            search_roots.insert(0, fmriprep_dir)

        for search_root in search_roots:
            for sub in search_root.iterdir():
                if not (sub.is_dir() and sub.name.startswith("sub-")):
                    continue
                # Look for confounds TSV up to two levels deep
                # (sub-*/func/ or sub-*/ses-*/func/)
                func_dirs = []
                func_direct = sub / "func"
                if func_direct.is_dir():
                    func_dirs.append(func_direct)
                for ses in sub.iterdir():
                    if ses.is_dir() and ses.name.startswith("ses-"):
                        ses_func = ses / "func"
                        if ses_func.is_dir():
                            func_dirs.append(ses_func)
                for func_dir in func_dirs:
                    for f in func_dir.iterdir():
                        if f.name.endswith("_desc-confounds_timeseries.tsv"):
                            return True
        return False

    # ------------------------------------------------------------------

    def _update_button_states(self):
        """Enable/disable buttons based on what the source folder contains
        and whether an output folder has been selected.

        The Source folder can point to:
        - Raw DICOM data  -> enables BIDS Conversion and Full Pipeline
        - A BIDS dataset  -> enables fMRIPrep Only (and the above)
        - Pipeline output with derivatives/ -> enables Connectivity QC (and the above)

        Buttons that produce new output (BIDS Only, BIDS + MRIQC, Full Pipeline)
        require both Source AND Output folders.  Buttons that operate on existing
        data (fMRIPrep Only, Connectivity QC Only) only require Source.
        """
        input_dir = self.primary_input
        output_dir = self.entry_output.get().strip()
        has_output = bool(output_dir)

        has_subjects = False
        has_bids_data = False
        has_fmriprep_results = False

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

            # BIDS detector: dataset_description.json + raw NIfTI under
            # top-level sub-* folders (ignores derivatives/sub-*)
            has_bids_data = self._has_bids_nifti(check_path)

            # fMRIPrep detector: confounds TSV files under derivatives/
            has_fmriprep_results = self._has_fmriprep_derivatives(check_path)

        # Determine the reason to show when a button that needs output is disabled
        if not input_dir and not has_output:
            output_reason = "Select Source and Output folders"
        elif not input_dir:
            output_reason = "Select a Source DICOM Folder"
        else:
            output_reason = "Select an Output Root Folder"

        # --- Apply button states ---
        # BIDS Conversion: needs subject folders + output folder
        self._set_button_enabled(
            self.btn_bids_only, self.label_est_bids, "bids",
            enabled=has_subjects and has_output,
            reason=output_reason if not has_output else "Select a Source DICOM Folder"
        )

        # BIDS + MRIQC: needs subject folders + output folder
        self._set_button_enabled(
            self.btn_mriqc_only, self.label_est_mriqc, "mriqc",
            enabled=has_subjects and has_output,
            reason=output_reason if not has_output else "Select a Source DICOM Folder"
        )

        # Full Pipeline: needs subject folders + output folder
        self._set_button_enabled(
            self.btn_full_pipeline, self.label_est_full, "full",
            enabled=has_subjects and has_output,
            reason=output_reason if not has_output else "Select a Source DICOM Folder"
        )

        # fMRIPrep Only: needs raw BIDS NIfTI data (not just any sub-* folder)
        self._set_button_enabled(
            self.btn_fmriprep_only, self.label_est_fmriprep, "fmriprep",
            enabled=has_bids_data,
            reason="Source must contain BIDS data (NIfTI files in sub-*/)"
        )

        # Connectivity QC: needs actual fMRIPrep confounds/results
        self._set_button_enabled(
            self.btn_connectivity_qc, self.label_est_conn, "conn",
            enabled=has_fmriprep_results,
            reason="Source must contain fMRIPrep results (derivatives/)"
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
        input_dir = self.primary_input

        if not input_dir or not Path(input_dir).is_dir():
            self.label_dataset_summary.grid_remove()
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
            return

        # Show dataset summary above buttons
        self.label_dataset_summary.configure(
            text=f"Detected {n_subjects} subject(s), {n_sessions} session(s)"
        )
        self.label_dataset_summary.grid()

        # Compute estimates
        bids_min = n_sessions * self._BIDS_MIN_PER_SESSION
        mriqc_min = n_subjects * self._MRIQC_MIN_PER_SUBJECT
        fmriprep_min = n_subjects * self._FMRIPREP_MIN_PER_SUBJECT
        conn_min = n_subjects * self._CONNECTIVITY_MIN_PER_SUBJECT
        full_min = bids_min + mriqc_min + fmriprep_min + conn_min

        # Update time labels below enabled buttons only
        # (disabled buttons keep their requirement text from _update_button_states)
        btn_label_pairs = [
            (self.btn_bids_only, self.label_est_bids, bids_min),
            (self.btn_mriqc_only, self.label_est_mriqc, bids_min + mriqc_min),
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

    # ------------------------------------------------------------------
    # QC Thresholds section
    # ------------------------------------------------------------------

    def _build_qc_thresholds_section(self):
        """Create the collapsible Quality Check Thresholds section."""
        import importlib
        import sys as _sys
        src_dir = str(Path(__file__).parent.parent)
        if src_dir not in _sys.path:
            _sys.path.insert(0, src_dir)
        _iqm = importlib.import_module("mriqc.iqm_parser")
        _mp = importlib.import_module("qc.motion_parser")
        _ct = importlib.import_module("qc.connectivity_thresholds")

        # Container
        self.frame_qc_container = ctk.CTkFrame(self.main_scroll)
        self.frame_qc_container.grid(row=5, column=0, padx=20, pady=(10, 0), sticky="ew")
        self.frame_qc_container.grid_columnconfigure(0, weight=1)

        # Header with toggle
        frame_qc_header = ctk.CTkFrame(self.frame_qc_container, fg_color="transparent")
        frame_qc_header.grid(row=0, column=0, sticky="ew")
        frame_qc_header.grid_columnconfigure(1, weight=1)

        self.btn_toggle_qc = ctk.CTkButton(
            frame_qc_header, text=">", width=25, height=25,
            fg_color="transparent", hover_color="#333333",
            command=self._toggle_qc_thresholds,
        )
        self.btn_toggle_qc.grid(row=0, column=0, padx=(10, 5), pady=10)

        self.label_qc_header = ctk.CTkLabel(
            frame_qc_header,
            text="Quality Check Thresholds (click to expand)",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.label_qc_header.grid(row=0, column=1, pady=10, sticky="w")
        self.label_qc_header.bind("<Button-1>", lambda e: self._toggle_qc_thresholds())

        # Content frame (hidden by default)
        self.frame_qc_content = ctk.CTkFrame(self.frame_qc_container, fg_color="#1a1a1a")
        self.qc_thresholds_visible = False

        # Entry widgets: (section, metric, level) -> CTkEntry
        self._qc_entries: dict = {}
        self._qc_defaults: dict = {}
        self._qc_override_map: dict = {}
        self._qc_iqm_directions: dict = {}

        # ---- Typography ----
        _font      = ctk.CTkFont(size=12)
        _font_sm   = ctk.CTkFont(size=11)
        _hdr_font  = ctk.CTkFont(size=11, weight="bold")
        _title_font = ctk.CTkFont(size=13, weight="bold")

        # ---- Palette ----
        _title_clr = "#E8E8E8"    # white titles
        _clr_warn = "#FFC107"
        _clr_err  = "#F44336"
        _card_bg  = "#222222"
        _card_r   = 8
        _stripe   = "#282828"      # alternate-row tint
        _divider  = "#333333"

        _entry_w  = 80
        _entry_h  = 30

        # Grab default border colour for reset
        _probe = ctk.CTkEntry(self.frame_qc_content, width=1)
        self._qc_entry_default_border = _probe.cget("border_color")
        _probe.destroy()

        # ---- Helpers ----
        def _make_entry(parent, default_val):
            e = ctk.CTkEntry(parent, width=_entry_w, height=_entry_h,
                             font=_font_sm, justify="center",
                             corner_radius=4)
            e.insert(0, str(default_val))
            e.bind("<KeyRelease>", lambda ev: self._on_qc_entry_changed())
            return e

        _side_pad = 30   # left/right padding for title & divider
        _entry_px = (4, 10)  # (left, right) padx — pulls entries closer to labels
        _ew_total = _entry_w + _entry_px[0] + _entry_px[1]  # column minsize

        def _build_card(parent, title, metrics, section_key,
                        is_iqm=True):
            """Build one card (rounded frame with title, header row, data rows).

            Uses a 3-column layout directly on the card so that headers
            and data entries share the same columns and stay aligned.

            *metrics* is a list of tuples:
              IQM:  (display_label, metric_key, warn_val, error_val, direction)
              Other: (display_label, gui_key, warn_val, warn_override_keys,
                      error_val, error_override_keys)
            """
            card = ctk.CTkFrame(parent, fg_color=_card_bg,
                                corner_radius=_card_r)
            # Column 0 stretches for labels; 1 & 2 are fixed-width for entries
            card.grid_columnconfigure(0, weight=1)
            card.grid_columnconfigure(1, minsize=_ew_total)
            card.grid_columnconfigure(2, minsize=_ew_total)

            # -- Title --
            ctk.CTkLabel(card, text=title, font=_title_font,
                         text_color=_title_clr
                         ).grid(row=0, column=0, columnspan=3,
                                padx=_side_pad, pady=(14, 3), sticky="ew")

            # -- Thin line under title --
            ctk.CTkFrame(card, fg_color=_divider, height=1
                         ).grid(row=1, column=0, columnspan=3,
                                sticky="ew", padx=_side_pad, pady=(3, 8))

            # -- Column headers (same grid columns as entries) --
            ctk.CTkLabel(card, text="Warning", font=_hdr_font,
                         text_color=_clr_warn
                         ).grid(row=2, column=1, padx=_entry_px, pady=(0, 4))
            ctk.CTkLabel(card, text="Error", font=_hdr_font,
                         text_color=_clr_err
                         ).grid(row=2, column=2, padx=_entry_px, pady=(0, 4))

            # -- Data rows (full-width stripes, edge to edge) --
            for i, m in enumerate(metrics):
                r = 3 + i
                row_bg = _stripe if i % 2 == 0 else _card_bg

                stripe = ctk.CTkFrame(card, fg_color=row_bg,
                                      corner_radius=4, height=34)
                stripe.grid(row=r, column=0, columnspan=3,
                            sticky="nsew", padx=0, pady=1)
                stripe.grid_columnconfigure(0, weight=1)
                stripe.grid_columnconfigure(1, minsize=_ew_total)
                stripe.grid_columnconfigure(2, minsize=_ew_total)

                if is_iqm:
                    label_text, metric_key, wv, ev, direction = m
                    self._qc_iqm_directions[(section_key, metric_key)] = direction
                    ctk.CTkLabel(stripe, text=label_text, font=_font,
                                 fg_color="transparent"
                                 ).grid(row=0, column=0, padx=(12, 6),
                                        pady=4, sticky="w")
                    ew = _make_entry(stripe, wv)
                    ew.grid(row=0, column=1, padx=_entry_px, pady=4)
                    self._qc_entries[(section_key, metric_key, "warn")] = ew
                    self._qc_defaults[(section_key, metric_key, "warn")] = str(wv)
                    ee = _make_entry(stripe, ev)
                    ee.grid(row=0, column=2, padx=_entry_px, pady=4)
                    self._qc_entries[(section_key, metric_key, "error")] = ee
                    self._qc_defaults[(section_key, metric_key, "error")] = str(ev)
                else:
                    label_text, gui_key, wv, w_keys, ev, e_keys = m
                    ctk.CTkLabel(stripe, text=label_text, font=_font,
                                 fg_color="transparent"
                                 ).grid(row=0, column=0, padx=(12, 6),
                                        pady=4, sticky="w")
                    if wv is not None:
                        ew = _make_entry(stripe, wv)
                        ew.grid(row=0, column=1, padx=_entry_px, pady=4)
                        k = (section_key, gui_key, "warn")
                        self._qc_entries[k] = ew
                        self._qc_defaults[k] = str(wv)
                        self._qc_override_map[k] = w_keys
                    else:
                        ctk.CTkLabel(stripe, text="", fg_color="transparent"
                                     ).grid(row=0, column=1, padx=_entry_px,
                                            pady=4)
                    if ev is not None:
                        ee = _make_entry(stripe, ev)
                        ee.grid(row=0, column=2, padx=_entry_px, pady=4)
                        k = (section_key, gui_key, "error")
                        self._qc_entries[k] = ee
                        self._qc_defaults[k] = str(ev)
                        self._qc_override_map[k] = e_keys
                    else:
                        ctk.CTkLabel(stripe, text="-", font=_font,
                                     text_color="#555555", fg_color="transparent"
                                     ).grid(row=0, column=2, padx=_entry_px,
                                            pady=4)

            # Bottom padding inside card
            card.grid_rowconfigure(3 + len(metrics), minsize=10)
            return card

        # ---- Layout: full-width 2x2 with dividers ----
        self.frame_qc_content.grid_columnconfigure(0, weight=1)
        f_grid = ctk.CTkFrame(self.frame_qc_content, fg_color="transparent")
        f_grid.grid(row=0, column=0, padx=10, pady=(12, 0), sticky="ew")
        f_grid.grid_columnconfigure((0, 2), weight=1, uniform="qc")

        _gap = 10  # half-gap (cards sit _gap px away from divider)

        # Dividers
        ctk.CTkFrame(f_grid, fg_color=_divider, width=1
                     ).grid(row=0, column=1, rowspan=3, sticky="ns", pady=10)
        ctk.CTkFrame(f_grid, fg_color=_divider, height=1
                     ).grid(row=1, column=0, columnspan=3, sticky="ew", padx=10)

        # ---- Build the four cards ----

        # Display names for IQM metrics
        _anat_labels = {
            "cjv": "Coeff. of Joint Variation",
            "cnr": "Contrast-to-Noise Ratio",
            "snr_gm": "Signal-to-Noise Ratio",
            "inu_range": "Intensity Non-Uniformity Range",
            "qi_1": "Artifact presence (QI1)",
        }
        _bold_labels = {
            "fd_mean": "Mean FD (mm)",
            "tsnr": "Temporal SNR",
            "gsr_x": "Ghost-to-Signal Ratio X",
            "gsr_y": "Ghost-to-Signal Ratio Y",
            "aor": "AFNI Outlier Ratio",
        }

        # Top-left: MRIQC Anatomical
        anat_metrics = []
        for mk, (w, e, d) in _iqm.THRESHOLDS_ANAT.items():
            anat_metrics.append((_anat_labels.get(mk, mk), mk, w, e, d))
        c_anat = _build_card(f_grid, "MRIQC - Anatomical",
                             anat_metrics, "iqm_anat")
        c_anat.grid(row=0, column=0, padx=(0, _gap), pady=(0, _gap),
                    sticky="nsew")

        # Top-right: MRIQC BOLD
        bold_metrics = []
        for mk, (w, e, d) in _iqm.THRESHOLDS_BOLD.items():
            bold_metrics.append((_bold_labels.get(mk, mk), mk, w, e, d))
        c_bold = _build_card(f_grid, "MRIQC - BOLD",
                             bold_metrics, "iqm_bold")
        c_bold.grid(row=0, column=2, padx=(_gap, 0), pady=(0, _gap),
                    sticky="nsew")

        # Bottom-left: Motion Analysis
        motion_metrics = [
            ("Mean FD (mm)", "mean_fd",
             _mp.WARN_MEAN_FD, ["warn_mean_fd", "fd_threshold"],
             _mp.RESCAN_MEAN_FD, ["rescan_mean_fd"]),
            ("High-Motion Frames (%)", "high_motion_pct",
             _mp.WARN_MOTION_PERCENT, ["warn_motion_percent"],
             _mp.RESCAN_MOTION_PERCENT, ["rescan_motion_percent"]),
        ]
        c_mot = _build_card(f_grid, "Motion Analysis",
                            motion_metrics, "motion", is_iqm=False)
        c_mot.grid(row=2, column=0, padx=(0, _gap), pady=(_gap, 0),
                   sticky="nsew")

        # Bottom-right: Connectivity Quality Check
        conn_metrics = [
            ("Mean FD (mm)", "mean_fd",
             _ct.CONNECTIVITY_MEAN_FD_WARN, ["connectivity_mean_fd_warn"],
             _ct.CONNECTIVITY_MEAN_FD_FAIL, ["connectivity_mean_fd_fail"]),
            ("Censored Volumes (%)", "censored_pct",
             _ct.MAX_CENSORED_PCT_WARN, ["max_censored_pct_warn"],
             _ct.MAX_CENSORED_PCT_FAIL, ["max_censored_pct_fail"]),
            ("Usable Time (min)", "usable_min",
             _ct.MIN_USABLE_MINUTES_WARN, ["min_usable_minutes_warn"],
             _ct.MIN_USABLE_MINUTES_FAIL, ["min_usable_minutes_fail"]),
            ("Loss of Degrees of Freedom", "dof_loss",
             _ct.LOSS_DOF_WARN, ["loss_dof_warn"],
             None, None),
        ]
        c_conn = _build_card(f_grid, "Connectivity Quality Check",
                             conn_metrics, "connectivity", is_iqm=False)
        c_conn.grid(row=2, column=2, padx=(_gap, 0), pady=(_gap, 0),
                    sticky="nsew")

        # ---- Footer: buttons (left) + warning (right) ----
        f_footer = ctk.CTkFrame(self.frame_qc_content, fg_color="transparent")
        f_footer.grid(row=1, column=0, sticky="ew", padx=18, pady=(10, 14))
        f_footer.grid_columnconfigure(2, weight=1)

        self.btn_qc_reset = ctk.CTkButton(
            f_footer, text="Reset to Defaults", width=130,
            command=self._reset_qc_thresholds,
        )
        self.btn_qc_reset.grid(row=0, column=0, sticky="w")

        self.btn_qc_save = ctk.CTkButton(
            f_footer, text="Save", width=100,
            fg_color="#555555", state="disabled",
            command=self._save_qc_thresholds,
        )
        self.btn_qc_save.grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.label_qc_warning = ctk.CTkLabel(
            f_footer, text="", font=_font_sm, text_color="#FFC107",
        )
        self.label_qc_warning.grid(row=0, column=2, sticky="e", padx=(12, 0))

        # Snapshot of saved values (starts equal to defaults)
        self._qc_saved: dict = dict(self._qc_defaults)

    # --- QC section helpers ---

    @staticmethod
    def _is_valid_number(val: str) -> bool:
        """Return True if *val* is a well-formed decimal number.

        Accepts: ``"0.6"``, ``"12"``, ``"0.25"``, ``".5"``
        Rejects: ``""``, ``"."``, ``"0."``, ``"3."``, ``"abc"``, ``"--1"``
        """
        if not val:
            return False
        try:
            float(val)
        except ValueError:
            return False
        # float() accepts trailing dots ("0.", "3.") — reject those
        if val.endswith("."):
            return False
        return True

    def _on_qc_entry_changed(self):
        """Live validation on every keystroke — highlight only truly invalid fields."""
        _default_border = self._qc_entry_default_border
        has_error = False
        error_msg = ""
        has_unsaved = False

        for key, entry in self._qc_entries.items():
            val = entry.get().strip()

            if self._is_valid_number(val):
                entry.configure(border_color=_default_border)
            elif val in ("", ".", "-", "-."):
                # Empty or bare punctuation mid-typing — don't highlight
                entry.configure(border_color=_default_border)
            else:
                entry.configure(border_color="#F44336")
                if not has_error:
                    error_msg = f"'{val}' is not a valid number"
                has_error = True

            # Check if value differs from saved snapshot
            if val != self._qc_saved.get(key, ""):
                has_unsaved = True

        if has_error:
            self.label_qc_warning.configure(text=error_msg)
        else:
            self.label_qc_warning.configure(text="")

        # Enable/disable save button (only when all values are complete numbers)
        all_complete = all(
            self._is_valid_number(e.get().strip())
            for e in self._qc_entries.values()
        )
        if has_unsaved and all_complete:
            self.btn_qc_save.configure(
                state="normal", fg_color=self._default_btn_color,
                hover_color=self._default_btn_hover)
        else:
            self.btn_qc_save.configure(
                state="disabled", fg_color="#555555")

    def _toggle_qc_thresholds(self):
        """Toggle visibility of the QC thresholds panel."""
        if self.qc_thresholds_visible:
            self.frame_qc_content.grid_remove()
            self.btn_toggle_qc.configure(text=">")
            self.label_qc_header.configure(text="Quality Check Thresholds (click to expand)")
            self.qc_thresholds_visible = False
        else:
            self.frame_qc_content.grid(row=1, column=0, sticky="ew", padx=5, pady=(0, 10))
            self.btn_toggle_qc.configure(text="v")
            self.label_qc_header.configure(text="Quality Check Thresholds")
            self.qc_thresholds_visible = True

    def _validate_qc_thresholds(self) -> bool:
        """Check all QC threshold entries are valid non-empty floats."""
        _default_border = self._qc_entry_default_border
        errors = []
        for key, entry in self._qc_entries.items():
            val = entry.get().strip()
            if self._is_valid_number(val):
                entry.configure(border_color=_default_border)
            else:
                section, metric, level = key
                if not val:
                    errors.append(f"{metric} ({level}) is empty")
                else:
                    errors.append(f"{metric} ({level}): '{val}' is not a valid number")
                entry.configure(border_color="#F44336")

        if errors:
            self.label_qc_warning.configure(
                text=errors[0] + (f"  (+{len(errors)-1} more)" if len(errors) > 1 else "")
            )
            return False

        self.label_qc_warning.configure(text="")
        return True

    def _get_qc_thresholds(self) -> dict:
        """Read all QC entries and return a dict of only changed values."""
        result: dict = {}

        for key, entry in self._qc_entries.items():
            val = entry.get().strip()
            default = self._qc_defaults[key]
            if val == default:
                continue

            section, metric, level = key

            if section in ("iqm_anat", "iqm_bold"):
                # IQM: emit [warn, error, direction] tuple for the metric
                warn_key = (section, metric, "warn")
                error_key = (section, metric, "error")
                if section not in result:
                    result[section] = {}
                if metric not in result[section]:
                    direction = self._qc_iqm_directions[(section, metric)]
                    warn_v = float(self._qc_entries[warn_key].get().strip())
                    error_v = float(self._qc_entries[error_key].get().strip())
                    result[section][metric] = [warn_v, error_v, direction]

            elif section in ("motion", "connectivity"):
                # Use the override map to emit the right key(s)
                override_keys = self._qc_override_map.get(key, [])
                if section not in result:
                    result[section] = {}
                for ok in override_keys:
                    result[section][ok] = float(val)

        return result

    def _reset_qc_thresholds(self):
        """Reset all QC threshold entries to their defaults."""
        _default_border = self._qc_entry_default_border
        for key, entry in self._qc_entries.items():
            entry.delete(0, "end")
            entry.insert(0, self._qc_defaults[key])
            entry.configure(border_color=_default_border)
        self.label_qc_warning.configure(text="")
        self._qc_saved = dict(self._qc_defaults)
        self.btn_qc_save.configure(state="disabled", fg_color="#555555")

    def _save_qc_thresholds(self):
        """Save the current threshold values (marks them as the baseline for unsaved detection)."""
        if not self._validate_qc_thresholds():
            return
        self._qc_saved = {
            key: entry.get().strip() for key, entry in self._qc_entries.items()
        }
        self.btn_qc_save.configure(state="disabled", fg_color="#555555")
        self.console.log("QC threshold overrides saved.", "success")

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
        input_dir = self.primary_input
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
        """Run BIDS conversion only (no MRIQC, no fMRIPrep)."""
        self._run_bids = True
        self._run_fmriprep = False
        self._run_mriqc = False
        self._fmriprep_only_mode = False
        self._start_pipeline_internal("BIDS Conversion")

    def run_mriqc_only(self):
        """Run BIDS conversion + MRIQC (no fMRIPrep)."""
        self._run_bids = True
        self._run_fmriprep = False
        self._run_mriqc = True
        self._fmriprep_only_mode = False
        import importlib
        import sys
        src_dir = str(Path(__file__).parent.parent)
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        mriqc_module = importlib.import_module("mriqc.runner")
        self._run_with_docker_preflight(
            "BIDS Conversion + MRIQC",
            preflight_fn=mriqc_module.mriqc_preflight,
        )

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
        self._run_mriqc = True
        self._fmriprep_only_mode = False
        self._run_with_docker_preflight("Full Pipeline (BIDS + MRIQC + fMRIPrep)")

    def run_connectivity_qc_only(self):
        """Run connectivity QC (Nilearn) on an existing fMRIPrep output folder."""
        source_folder = self.primary_input

        if not source_folder:
            self.console.log("Please select a Source folder containing fMRIPrep output.", "warning")
            return

        bids_path = Path(source_folder).resolve()
        if not bids_path.exists():
            self.console.log(f"Folder does not exist: {source_folder}", "warning")
            return

        # Check if this is a subject folder or contains subject folders
        is_subject_folder = bids_path.name.startswith("sub-")
        has_subject_subfolders = any(p.name.startswith("sub-") and p.is_dir() for p in bids_path.iterdir())
        
        if not is_subject_folder and not has_subject_subfolders:
            # Auto-select most recent output_* subfolder if needed (standard pipeline behavior)
            output_subfolders = [p for p in bids_path.iterdir()
                                 if p.is_dir() and p.name.startswith("output_")]
            if output_subfolders:
                most_recent = max(output_subfolders, key=lambda p: p.stat().st_mtime)
                bids_path = most_recent.resolve()
                self.console.log(f"Using output folder: {most_recent.name}", "info")
                is_subject_folder = bids_path.name.startswith("sub-")
                has_subject_subfolders = any(p.name.startswith("sub-") and p.is_dir() for p in bids_path.iterdir())

        if not is_subject_folder and not has_subject_subfolders:
            self.console.log("No 'sub-*' folders found. Select a subject folder or a folder with pipeline output.", "warning")
            return

        # Check for derivatives or just raw fMRIPrep files (relaxed check)
        derivatives = bids_path / "derivatives"
        has_fmriprep_files = any(p.name in ["anat", "func"] or p.name.startswith("ses-") for p in bids_path.iterdir())
        
        if not derivatives.exists() and not has_fmriprep_files and not is_subject_folder:
            self.console.log("No 'derivatives/' or fMRIPrep files found.", "warning")
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

        source_folder = self.primary_input

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
        self._run_mriqc = False
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
        # Validate QC thresholds before starting
        if not self._validate_qc_thresholds():
            self.console.log("Please fix invalid QC threshold values before running.", "warning")
            if not self.qc_thresholds_visible:
                self._toggle_qc_thresholds()
            self._set_buttons_state("normal")
            return

        if self._fmriprep_only_mode:
            bids_folder = self._bids_folder_for_fmriprep
        else:
            if not self._validate_paths():
                return
            bids_folder = None

        input_dir = self.primary_input
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
        self.btn_mriqc_only.configure(state=state)
        self.btn_fmriprep_only.configure(state=state)
        self.btn_connectivity_qc.configure(state=state)
        self.btn_full_pipeline.configure(state=state)
        self.btn_browse_input.configure(state=state)
        self.btn_browse_output.configure(state=state)

    def _update_parallel_label(self, value):
        """Update the numeric label for parallel workers as the slider moves."""
        self.label_parallel_val.configure(text=str(int(value)))

    def run_subprocess(self, input_dir, output_dir, bids_folder=None):
        script_path = Path(__file__).parent.parent / "orchestrator.py"

        # Connectivity QC only mode
        if self._connectivity_only_mode:
            cmd = [
                sys.executable, str(script_path),
                "--qc-only", "--bids-folder", self._connectivity_bids_folder
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

        # Add parallelism from slider
        parallel_workers = int(self.slider_parallel.get())
        cmd.extend(["--parallel", str(parallel_workers)])

        # Advanced Connectivity Options
        if self.check_connectivity.get():
            cmd.append("--connectivity-qc")

            # Map Atlas
            atlas_val = self.combo_atlas.get()
            atlas_flag = "schaefer_432_tian" if "432" in atlas_val else "schaefer_116_tian"
            cmd.extend(["--connectivity-atlas", atlas_flag])

            # Map Strategy
            strat_val = self.combo_strategy.get()
            strat_flag = "scrubbing" if strat_val == "anatomical" else strat_val
            cmd.extend(["--connectivity-strategy", strat_flag])

        # MRIQC Handling
        mriqc_requested = getattr(self, '_run_mriqc', True)
        if not mriqc_requested or self.check_skip_mriqc.get():
            cmd.append("--skip-mriqc")

        if not self._run_bids:

            cmd.append("--skip-bids")
        if not self._run_fmriprep:
            cmd.append("--skip-fmriprep")
        if self.check_anonymize.get():
            cmd.append("--anonymize")

        # Add --skip-mriqc when MRIQC is not requested (MRIQC runs by default)
        if not getattr(self, '_run_mriqc', True):
            cmd.append("--skip-mriqc")

        # Add fMRIPrep options if running fMRIPrep (platform-agnostic via base64 JSON)
        if self._run_fmriprep:
            fmriprep_opts = self._get_fmriprep_options()
            if fmriprep_opts:
                encoded_opts = self._encode_fmriprep_options(fmriprep_opts)
                cmd.extend(["--fmriprep-opts", encoded_opts])

        # Researcher comments are written to a file in the output folder
        # once the orchestrator prints the output path (see _write_comments_file).
        # Pass initial comments via CLI so the orchestrator can seed the file,
        # but the orchestrator will always re-read the file before report generation.
        comments = self._saved_comments_text
        if comments:
            encoded_comments = base64.b64encode(
                comments.encode('utf-8')
            ).decode('ascii')
            cmd.extend(["--researcher-comments", encoded_comments])

        # QC threshold overrides
        qc_thresholds = self._get_qc_thresholds()
        if qc_thresholds:
            encoded_qc = base64.b64encode(
                json.dumps(qc_thresholds).encode('utf-8')
            ).decode('ascii')
            cmd.extend(["--qc-thresholds", encoded_qc])

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
                
                # Capture output folder path and seed the comments file
                if stripped_line.startswith("Output folder:"):
                    self.current_output_folder = stripped_line.replace("Output folder:", "").strip()
                    self._write_comments_file()
                
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
