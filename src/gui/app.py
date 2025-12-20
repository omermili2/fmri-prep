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
        self.frame_actions.grid_columnconfigure((0, 1), weight=1)

        self.btn_bids_only = ctk.CTkButton(
            self.frame_actions,
            text="▶ Run BIDS Conversion",
            height=50,
            fg_color="#2E7D32",  # Green
            hover_color="#1B5E20",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.run_bids_only
        )
        self.btn_bids_only.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        self.btn_full_pipeline = ctk.CTkButton(
            self.frame_actions,
            text="▶▶ Run Full Pipeline",
            height=50,
            fg_color="#1565C0",  # Blue
            hover_color="#0D47A1",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.run_full_pipeline
        )
        self.btn_full_pipeline.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        
        # Internal state for pipeline steps (not shown in UI)
        self._run_bids = True
        self._run_fmriprep = False

        # --- Progress Indicator ---
        self.frame_progress = ctk.CTkFrame(self.main_scroll, fg_color="transparent")
        self.frame_progress.grid(row=5, column=0, padx=20, pady=(10, 5), sticky="ew")
        self.frame_progress.grid_columnconfigure(0, weight=1)
        self.frame_progress.grid_remove()  # Hide initially
        
        self.progress_bar = ctk.CTkProgressBar(self.frame_progress, mode="determinate")
        self.progress_bar.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.progress_bar.set(0)
        
        self.btn_stop = ctk.CTkButton(
            self.frame_progress,
            text="⏹ Stop",
            width=80,
            height=28,
            fg_color="#C62828",  # Red
            hover_color="#B71C1C",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.request_stop
        )
        self.btn_stop.grid(row=0, column=1)
        
        # Progress tracking variables
        self.total_tasks = 0
        self.completed_tasks = 0
        self.current_process = None
        self.current_output_folder = None
        self.stop_requested = False
        
        # Progress animation variables
        self.progress_animation_id = None
        self.current_progress = 0.0
        self.target_progress = 0.0
        self.task_in_progress = False

        # --- Status Label ---
        self.label_status = ctk.CTkLabel(
            self.main_scroll, 
            text="Ready", 
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
        """Get fMRIPrep options as command line arguments."""
        options = []
        
        # Output spaces
        spaces = []
        if self.check_space_mni.get():
            spaces.append("MNI152NLin2009cAsym")
        if self.check_space_t1w.get():
            spaces.append("T1w")
        if spaces:
            options.extend(["--output-spaces", " ".join(spaces)])
        
        # FreeSurfer
        if not self.check_freesurfer.get():
            options.append("--fs-no-reconall")
        
        # Slice timing
        if not self.check_slice_timing.get():
            options.extend(["--ignore", "slicetiming"])
        
        # SyN SDC
        if self.check_syn_sdc.get():
            options.append("--use-syn-sdc")
        
        # ICA-AROMA
        if self.check_aroma.get():
            options.append("--use-aroma")
        
        return options

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
        
        self._run_bids = True
        self._run_fmriprep = True
        self._start_pipeline_internal("BIDS Conversion + fMRIPrep")

    def _start_pipeline_internal(self, mode_label):
        """Start the pipeline with the configured options."""
        if not self._validate_paths():
            return

        input_dir = self.entry_input.get().strip()
        output_dir = self.entry_output.get().strip()

        self.is_running = True
        self.stop_requested = False
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
        self.console.log(f"📁 Source: {input_dir}")
        self.console.log(f"📂 Output Root: {output_dir}")
        self.console.log("=" * 60)

        self.label_status.configure(text="Processing...", text_color="#FFC107")

        # Run in background thread
        threading.Thread(target=self.run_subprocess, args=(input_dir, output_dir), daemon=True).start()

    def _set_buttons_state(self, state):
        """Enable/disable all action buttons."""
        self.btn_bids_only.configure(state=state)
        self.btn_full_pipeline.configure(state=state)
        self.btn_browse_input.configure(state=state)
        self.btn_browse_output.configure(state=state)

    def run_subprocess(self, input_dir, output_dir):
        script_path = Path(__file__).parent.parent / "orchestrator.py"
        
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
        
        # Add fMRIPrep options if running fMRIPrep
        if self._run_fmriprep:
            fmriprep_opts = self._get_fmriprep_options()
            if fmriprep_opts:
                cmd.extend(["--fmriprep-args", ",".join(fmriprep_opts)])

        try:
            # Platform-specific subprocess options for proper termination
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
                # Unix: create new process group for clean termination
                popen_kwargs['start_new_session'] = True
            
            self.current_process = subprocess.Popen(cmd, **popen_kwargs)
            
            if self.current_process.stdout is None:
                raise RuntimeError("Failed to capture subprocess output")
            
            for line in self.current_process.stdout:
                # Check if stop was requested
                if self.stop_requested:
                    break
                    
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
            
            # Handle stop request
            if self.stop_requested:
                self._perform_stop()
                return
            
            self.current_process.wait()
            
            # Ensure progress bar reaches 100% at completion
            self.after(0, lambda: self.progress_bar.set(1.0))
            
            if self.current_process.returncode == 0:
                self.console.log("=" * 60)
                self.console.log("Conversion complete! Check your output folder for results.", "success")
                self.after(0, self._update_status_success)
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
            sessions_word = "session" if self.total_tasks == 1 else "sessions"
            self.after(0, lambda: self.label_status.configure(
                text=f"Preparing to convert {self.total_tasks} {sessions_word}...", 
                text_color="#FFC107"
            ))
        
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
            
            # User-friendly status message
            self.after(0, lambda s=stage_name, sub=sub_id, ses=ses_id: self.label_status.configure(
                text=f"Subject {sub}, Session {ses}: {s}",
                text_color="#FFC107"
            ))
        
        # [PROGRESS:STATUS:message] - General status update
        elif match := re.match(r'\[PROGRESS:STATUS:(.+)\]', marker):
            message = match.group(1)
            self.after(0, lambda m=message: self.label_status.configure(
                text=m,
                text_color="#FFC107"
            ))
        
        # [PROGRESS:TASK:N] - Task N completed
        elif match := re.match(r'\[PROGRESS:TASK:(\d+)\]', marker):
            self.completed_tasks = int(match.group(1))
            self.task_in_progress = False
            if self.total_tasks > 0:
                # Snap to actual progress
                self.current_progress = self.completed_tasks / self.total_tasks
                self.target_progress = self.current_progress
                self.after(0, lambda p=self.current_progress: self.progress_bar.set(p))
                
                remaining = self.total_tasks - self.completed_tasks
                if remaining > 0:
                    sessions_word = "session" if remaining == 1 else "sessions"
                    self.after(0, lambda r=remaining, w=sessions_word: self.label_status.configure(
                        text=f"{r} {w} remaining...",
                        text_color="#FFC107"
                    ))
        
        # [PROGRESS:COMPLETE] - All done
        elif marker == "[PROGRESS:COMPLETE]":
            self._stop_progress_animation()
            self.current_progress = 1.0
            self.after(0, lambda: self.progress_bar.set(1.0))
            self.after(0, lambda: self.label_status.configure(
                text="Cleaning up and generating report...",
                text_color="#FFC107"
            ))
    
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
        if not self.task_in_progress or self.stop_requested:
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

    def request_stop(self):
        """Handle stop button click - show confirmation dialog."""
        if not self.is_running:
            return
            
        # Show confirmation dialog
        result = messagebox.askyesno(
            "Confirm Stop",
            "Are you sure you want to cancel the execution?\n\nAll processed sessions will be deleted.",
            icon="warning"
        )
        
        if result:  # User clicked Yes
            self.stop_requested = True
            self.btn_stop.configure(state="disabled", text="Stopping...")
            self.console.log("⏹ Stop requested by user...", "warning")
        # If No, just continue (do nothing)
    
    def _perform_stop(self):
        """Terminate process and clean up output folder."""
        # Capture values for background cleanup
        process_to_kill = self.current_process
        folder_to_delete = self.current_output_folder
        
        # Immediately clear references and reset UI
        self.current_process = None
        self.current_output_folder = None
        
        self.console.log("=" * 60)
        self.console.log("⏹ EXECUTION CANCELLED BY USER", "warning")
        self.after(0, lambda: self.label_status.configure(
            text="⏹ Cancelled by user", 
            text_color="#FFC107"
        ))
        
        # Reset UI immediately so user can start new process
        self.after(0, self._reset_ui)
        
        # Cleanup in background thread
        def cleanup_background():
            try:
                # Terminate the subprocess (platform-specific)
                if process_to_kill:
                    try:
                        if IS_WINDOWS:
                            # On Windows, use taskkill to terminate process tree
                            subprocess.run(
                                ['taskkill', '/F', '/T', '/PID', str(process_to_kill.pid)],
                                capture_output=True,
                                timeout=10
                            )
                        else:
                            # On Unix, send SIGTERM to process group
                            try:
                                os.killpg(os.getpgid(process_to_kill.pid), signal.SIGTERM)
                            except (ProcessLookupError, PermissionError):
                                process_to_kill.terminate()
                        
                        try:
                            process_to_kill.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process_to_kill.kill()
                    except Exception:
                        # Last resort
                        try:
                            process_to_kill.kill()
                        except Exception:
                            pass
                
                # Delete the output folder
                if folder_to_delete:
                    output_path = Path(folder_to_delete)
                    if output_path.exists():
                        # On Windows, sometimes files are locked briefly
                        for attempt in range(3):
                            try:
                                shutil.rmtree(output_path)
                                break
                            except PermissionError:
                                import time
                                time.sleep(1)
                        
            except Exception as e:
                # Log errors but don't block - user already moved on
                self.console.log(f"Warning: Background cleanup: {e}", "warning")
        
        threading.Thread(target=cleanup_background, daemon=True).start()
    
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
        self.stop_requested = False
        self.task_in_progress = False
        self._stop_progress_animation()
        self.current_progress = 0.0
        self.target_progress = 0.0
        self.progress_bar.set(0)
        self.frame_progress.grid_remove()
        self.btn_stop.configure(state="normal", text="⏹ Stop")
        self._set_buttons_state("normal")


if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()
