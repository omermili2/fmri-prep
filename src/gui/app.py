import customtkinter as ctk
from tkinter import filedialog, END, messagebox
import subprocess
import threading
from pathlib import Path
import sys
import os
import re
import shutil
import signal
import platform
import json
import base64
from datetime import datetime

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
            text="📁 Source DICOM Folder:", 
            font=ctk.CTkFont(weight="bold")
        )
        self.label_input.grid(row=0, column=0, padx=15, pady=15, sticky="w")
        
        self.entry_input = ctk.CTkEntry(
            self.frame_config, 
            placeholder_text="Select folder containing subject folders"
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
            text="📂 Output Root Folder:", 
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
        
        self.check_anonymize = ctk.CTkCheckBox(
            self.frame_bids_options,
            text="Enable anonymization (remove patient info from metadata)",
            font=ctk.CTkFont(size=12),
            onvalue=True,
            offvalue=False
        )
        self.check_anonymize.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.check_anonymize.deselect()  # Default: OFF (preserve full metadata)
        
        self.check_keep_temp = ctk.CTkCheckBox(
            self.frame_bids_options,
            text="Keep temporary files (for debugging)",
            font=ctk.CTkFont(size=12),
            onvalue=True,
            offvalue=False
        )
        self.check_keep_temp.grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.check_keep_temp.deselect()  # Default: OFF (clean up temp files)

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
            text="▶",
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
            text="MNI152NLin2009cAsym (standard brain template)",
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
        
        self.check_freesurfer = ctk.CTkCheckBox(
            self.frame_fmriprep_options,
            text="FreeSurfer surface reconstruction (adds ~6 hours per subject)",
            font=ctk.CTkFont(size=11)
        )
        self.check_freesurfer.grid(row=4, column=0, padx=30, pady=3, sticky="w")
        self.check_freesurfer.deselect()  # Default: OFF (skip FreeSurfer)
        
        self.check_slice_timing = ctk.CTkCheckBox(
            self.frame_fmriprep_options,
            text="Slice timing correction",
            font=ctk.CTkFont(size=11)
        )
        self.check_slice_timing.grid(row=5, column=0, padx=30, pady=3, sticky="w")
        self.check_slice_timing.select()  # Default: ON
        
        self.check_syn_sdc = ctk.CTkCheckBox(
            self.frame_fmriprep_options,
            text="Fieldmap-less distortion correction (SyN SDC)",
            font=ctk.CTkFont(size=11)
        )
        self.check_syn_sdc.grid(row=6, column=0, padx=30, pady=3, sticky="w")
        self.check_syn_sdc.deselect()  # Default: OFF
        
        self.check_aroma = ctk.CTkCheckBox(
            self.frame_fmriprep_options,
            text="ICA-AROMA denoising (requires MNI output)",
            font=ctk.CTkFont(size=11),
            command=self._validate_fmriprep_options
        )
        self.check_aroma.grid(row=7, column=0, padx=30, pady=(3, 10), sticky="w")
        self.check_aroma.deselect()  # Default: OFF
        
        # Validation warning label
        self.label_fmriprep_warning = ctk.CTkLabel(
            self.frame_fmriprep_options,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="#FFC107"
        )
        self.label_fmriprep_warning.grid(row=8, column=0, columnspan=2, padx=15, pady=(0, 10), sticky="w")

        # --- Action Buttons ---
        self.frame_actions = ctk.CTkFrame(self.main_scroll, fg_color="transparent")
        self.frame_actions.grid(row=4, column=0, padx=20, pady=10, sticky="ew")
        self.frame_actions.grid_columnconfigure((0, 1, 2), weight=1)

        self.btn_bids_only = ctk.CTkButton(
            self.frame_actions,
            text="📊 Run BIDS Conversion",
            height=50,
            fg_color="#2E7D32",  # Green
            hover_color="#1B5E20",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.run_bids_only
        )
        self.btn_bids_only.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        self.btn_fmriprep_only = ctk.CTkButton(
            self.frame_actions,
            text="🧠 Run fMRIPrep Only",
            height=50,
            fg_color="#7B1FA2",  # Purple
            hover_color="#4A148C",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.run_fmriprep_only
        )
        self.btn_fmriprep_only.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        
        self.btn_full_pipeline = ctk.CTkButton(
            self.frame_actions,
            text="🚀 Run Full Pipeline",
            height=50,
            fg_color="#1565C0",  # Blue
            hover_color="#0D47A1",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.run_full_pipeline
        )
        self.btn_full_pipeline.grid(row=0, column=2, padx=10, pady=10, sticky="ew")
        
        # Internal state for pipeline steps (not shown in UI)
        self._run_bids = True
        self._run_fmriprep = False
        self._fmriprep_only_mode = False

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

        # --- Status Label ---
        self.label_status = ctk.CTkLabel(
            self.main_scroll, 
            text="", 
            font=ctk.CTkFont(size=12),
            text_color="#888888"
        )
        self.label_status.grid(row=6, column=0, padx=20, pady=(0, 5), sticky="w")

        # --- Log Area ---
        self.label_logs = ctk.CTkLabel(
            self.main_scroll, 
            text="📋 Execution Logs", 
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.label_logs.grid(row=7, column=0, padx=20, pady=(10, 0), sticky="w")
        
        self.console = ConsoleLog(self.main_scroll, height=250)
        self.console.grid(row=8, column=0, padx=20, pady=(5, 20), sticky="ew")

        self.is_running = False
        

    def browse_input(self):
        folder = filedialog.askdirectory(title="Select Source DICOM Folder")
        if folder:
            self.entry_input.delete(0, "end")
            self.entry_input.insert(0, folder)
            self._update_output_info()

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

    def _update_output_info(self):
        """Update the output info label to show where files will be saved."""
        output_dir = self.entry_output.get()
        if output_dir:
            output_path = Path(output_dir) / "output_<timestamp>"
            self.label_output_info.configure(
                text=f"→ BIDS data will be saved to: {output_path}"
            )
            self.label_output_info.grid()  # Show the label
        else:
            self.label_output_info.grid_remove()  # Hide when empty

    def _toggle_fmriprep_options(self):
        """Toggle the visibility of fMRIPrep options panel."""
        if self.fmriprep_options_visible:
            self.frame_fmriprep_options.grid_remove()
            self.btn_toggle_fmriprep.configure(text="▶")
            self.label_fmriprep_header.configure(text="fMRIPrep Options (click to expand)")
            self.fmriprep_options_visible = False
        else:
            self.frame_fmriprep_options.grid(row=1, column=0, sticky="ew", padx=5, pady=(0, 10))
            self.btn_toggle_fmriprep.configure(text="▼")
            self.label_fmriprep_header.configure(text="fMRIPrep Options")
            self.fmriprep_options_visible = True

    def _validate_fmriprep_options(self):
        """Validate fMRIPrep options and show warnings for invalid combinations."""
        warnings = []
        
        # Check that at least one output space is selected
        if not self.check_space_mni.get() and not self.check_space_t1w.get():
            warnings.append("⚠ Select at least one output space")
        
        # ICA-AROMA requires MNI output
        if self.check_aroma.get() and not self.check_space_mni.get():
            warnings.append("⚠ ICA-AROMA requires MNI output space")
            # Auto-enable MNI when AROMA is selected
            self.check_space_mni.select()
        
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
            spaces.append("MNI152NLin2009cAsym")
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
        
        # ICA-AROMA
        options["use_aroma"] = self.check_aroma.get()
        
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
            self.console.log("⚠️  Please select a source DICOM folder.", "warning")
            return False
            
        if not output_dir:
            self.console.log("⚠️  Please select an output folder.", "warning")
            return False

        # Resolve to absolute paths for comparison
        input_path = Path(input_dir).resolve()
        output_path = Path(output_dir).resolve()

        if not input_path.exists():
            self.console.log(f"⚠️  Source folder does not exist: {input_dir}", "warning")
            return False

        # Prevent output inside input or same as input
        if output_path == input_path:
            self.console.log("⚠️  Output folder cannot be the same as input folder!", "warning")
            self.console.log("   Please select a different output location.", "warning")
            return False

        if str(output_path).startswith(str(input_path) + os.sep):
            self.console.log("⚠️  Output folder cannot be inside the input folder!", "warning")
            self.console.log("   Please select a different output location.", "warning")
            return False

        # Note: Output CAN be parent of input - timestamped subfolder will be created

        return True

    def run_bids_only(self):
        """Run BIDS conversion only."""
        self._run_bids = True
        self._run_fmriprep = False
        self._start_pipeline_internal("BIDS Conversion")

    def run_full_pipeline(self):
        """Run both BIDS conversion and fMRIPrep."""
        # Validate fMRIPrep options
        if not self._validate_fmriprep_options():
            self.console.log("⚠️  Please fix fMRIPrep options before running.", "warning")
            # Expand options panel if collapsed
            if not self.fmriprep_options_visible:
                self._toggle_fmriprep_options()
            return
        
        # Run Docker preflight check before starting
        self._run_bids = True
        self._run_fmriprep = True
        self._fmriprep_only_mode = False
        self._run_with_docker_preflight("BIDS Conversion + fMRIPrep")

    def run_fmriprep_only(self):
        """Run fMRIPrep on an existing BIDS folder (uses input folder as BIDS folder)."""
        # Validate fMRIPrep options
        if not self._validate_fmriprep_options():
            self.console.log("⚠️  Please fix fMRIPrep options before running.", "warning")
            # Expand options panel if collapsed
            if not self.fmriprep_options_visible:
                self._toggle_fmriprep_options()
            return
        
        # For fMRIPrep Only, use the OUTPUT folder as the BIDS folder
        # (since that's where the BIDS conversion wrote the data)
        bids_folder = self.entry_output.get().strip()
        
        if not bids_folder:
            self.console.log("⚠️  Please select the BIDS output folder in the Output Root Folder field.", "warning")
            self.console.log("   This should be the folder from a previous BIDS conversion.", "info")
            return
        
        # Validate it looks like a BIDS folder
        bids_path = Path(bids_folder).resolve()
        if not bids_path.exists():
            self.console.log(f"⚠️  Folder does not exist: {bids_folder}", "warning")
            return
        
        # Check if this is the root folder with output_* subfolders
        # If so, automatically use the most recent one
        output_subfolders = [p for p in bids_path.iterdir() 
                            if p.is_dir() and p.name.startswith("output_")]
        
        if output_subfolders:
            # Use the most recent output folder (by modification time)
            most_recent = max(output_subfolders, key=lambda p: p.stat().st_mtime)
            bids_path = most_recent.resolve()
            self.console.log(f"ℹ️  Found output folder: {most_recent.name}", "info")
            self.console.log(f"   Using this as the BIDS folder.", "info")
        
        # Resolve path and check for dataset_description.json
        dataset_desc = bids_path / "dataset_description.json"
        dataset_desc_resolved = dataset_desc.resolve() if dataset_desc.exists() else None
        
        # Debug: list what files are actually in the folder
        try:
            files_in_folder = [f.name for f in bids_path.iterdir() if f.is_file()]
            self.console.log(f"ℹ️  Files in folder: {', '.join(files_in_folder[:10])}", "info")
        except Exception as e:
            self.console.log(f"⚠️  Could not list files: {e}", "warning")
        
        if not dataset_desc.exists():
            # On Windows, check case-insensitively
            if sys.platform == 'win32':
                found_file = None
                try:
                    for item in bids_path.iterdir():
                        if item.is_file() and item.name.lower() == "dataset_description.json":
                            found_file = item
                            break
                except Exception as e:
                    self.console.log(f"⚠️  Error checking files: {e}", "warning")
                
                if found_file:
                    dataset_desc = found_file
                    self.console.log(f"ℹ️  Found file with different case: {found_file.name}", "info")
                else:
                    self.console.log("⚠️  Selected folder doesn't appear to be a valid BIDS folder.", "warning")
                    self.console.log("   (Missing dataset_description.json)", "warning")
                    self.console.log(f"   Checked path: {bids_path}", "info")
                    self.console.log(f"   Absolute path: {bids_path.resolve()}", "info")
                    self.console.log("   Tip: Select the OUTPUT folder from a previous BIDS conversion.", "info")
                    self.console.log("   It should contain 'dataset_description.json' and 'sub-*' folders.", "info")
                    return
            else:
                self.console.log("⚠️  Selected folder doesn't appear to be a valid BIDS folder.", "warning")
                self.console.log("   (Missing dataset_description.json)", "warning")
                self.console.log(f"   Checked path: {bids_path}", "info")
                self.console.log(f"   Absolute path: {bids_path.resolve()}", "info")
                self.console.log("   Tip: Select the OUTPUT folder from a previous BIDS conversion.", "info")
                self.console.log("   It should contain 'dataset_description.json' and 'sub-*' folders.", "info")
                return
        
        # Check for subject folders
        has_subjects = any(p.name.startswith("sub-") and p.is_dir() for p in bids_path.iterdir())
        if not has_subjects:
            self.console.log("⚠️  No 'sub-*' folders found in the BIDS folder.", "warning")
            self.console.log(f"   Checked: {bids_path}", "info")
            self.console.log("   Make sure you're selecting the correct BIDS output folder.", "info")
            return
        
        # Update bids_folder to the actual path we're using
        bids_folder = str(bids_path.resolve())
        
        self._run_bids = False
        self._run_fmriprep = True
        self._fmriprep_only_mode = True
        self._bids_folder_for_fmriprep = bids_folder
        self._run_with_docker_preflight("fMRIPrep Only")

    def _run_with_docker_preflight(self, mode_label):
        """Run Docker preflight checks before starting fMRIPrep pipeline."""
        # Clear console and show preflight status
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")
        
        self.console.log("🔍 Running pre-flight checks for fMRIPrep...", "header")
        self.console.log("=" * 60)
        
        # Disable buttons during preflight
        self._set_buttons_state("disabled")
        
        # Run preflight in background thread
        def preflight_thread():
            try:
                # Import the preflight function (dynamic import for flexibility)
                import importlib.util
                runner_path = Path(__file__).parent.parent / "fmriprep" / "runner.py"
                spec = importlib.util.spec_from_file_location("runner", runner_path)
                if spec is None or spec.loader is None:
                    raise ImportError(f"Could not load module from {runner_path}")
                runner_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(runner_module)
                preflight_check = runner_module.preflight_check
                
                def log_callback(message):
                    self.console.log(message)
                
                success, error_msg = preflight_check(
                    callback=log_callback,
                    auto_start_docker=True,
                    auto_pull_image=True
                )
                
                if success:
                    self.console.log("")
                    self.console.log("✅ All pre-flight checks passed!", "success")
                    self.console.log("=" * 60)
                    self.console.log("")
                    # Now start the actual pipeline
                    self.after(100, lambda: self._start_pipeline_internal(mode_label))
                else:
                    self.console.log("")
                    self.console.log("❌ Pre-flight check failed:", "error")
                    if error_msg:
                        for line in error_msg.split('\n'):
                            self.console.log(f"   {line}", "error")
                    self._set_buttons_state("normal")
                    self.label_status.configure(text="Pre-flight check failed", text_color="#F44336")
                    
            except Exception as e:
                self.console.log(f"❌ Error during pre-flight check: {e}", "error")
                self._set_buttons_state("normal")
                self.label_status.configure(text="Error", text_color="#F44336")
        
        threading.Thread(target=preflight_thread, daemon=True).start()

    def _start_pipeline_internal(self, mode_label):
        """Start the pipeline with the configured options."""
        # For fMRIPrep-only mode, we use the BIDS folder directly
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
        
        self.console.log(f"🚀 {mode_label}", "header")
        if self._fmriprep_only_mode:
            self.console.log(f"📁 BIDS Folder: {bids_folder}")
        else:
            self.console.log(f"📁 Source: {input_dir}")
            self.console.log(f"📂 Output Root: {output_dir}")
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
        self.btn_full_pipeline.configure(state=state)
        self.btn_fmriprep_only.configure(state=state)
        self.btn_browse_input.configure(state=state)
        self.btn_browse_output.configure(state=state)

    def run_subprocess(self, input_dir, output_dir, bids_folder=None):
        script_path = Path(__file__).parent.parent / "orchestrator.py"
        
        # For fMRIPrep-only mode, use the BIDS folder as input
        if self._fmriprep_only_mode and bids_folder:
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
        
        if self.check_keep_temp.get():
            cmd.append("--keep-temp")
        
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
                self.after(0, self._update_status_error)

        except Exception as e:
            self.console.log(f"❌ Critical Error: {e}", "error")
            self.after(0, self._update_status_error)

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
    
    def _update_status_success(self):
        self.label_status.configure(
            text="All done! Your converted files are ready.", 
            text_color="#4CAF50"
        )

    def _update_status_error(self):
        self.label_status.configure(
            text="Something went wrong. See the logs below for details.", 
            text_color="#F44336"
        )

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
