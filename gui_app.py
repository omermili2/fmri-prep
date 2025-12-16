import customtkinter as ctk
from tkinter import filedialog, END, messagebox
import subprocess
import threading
from pathlib import Path
import sys
import os
import re
import shutil
from datetime import datetime


# --- Custom Logger Widget with Colors ---
class ConsoleLog(ctk.CTkTextbox):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.configure(state="disabled", font=("Consolas", 13))
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
        if "Failed!" in message or "Error" in message or "Traceback" in message:
            tag = "error"
        elif "Done." in message or "COMPLETED" in message or "✓" in message:
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
        self.geometry("950x750")
        self.minsize(700, 550)
        
        # Grid Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(7, weight=1)  # Log area expands
        
        # --- Header ---
        self.frame_header = ctk.CTkFrame(self, fg_color="transparent")
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
        self.frame_config = ctk.CTkFrame(self)
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

        # --- Options Frame ---
        self.frame_options = ctk.CTkFrame(self)
        self.frame_options.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        
        self.label_steps = ctk.CTkLabel(
            self.frame_options, 
            text="Pipeline Steps:", 
            font=ctk.CTkFont(weight="bold")
        )
        self.label_steps.grid(row=0, column=0, padx=15, pady=15)

        self.check_bids = ctk.CTkCheckBox(
            self.frame_options, 
            text="BIDS Conversion", 
            onvalue=True, 
            offvalue=False
        )
        self.check_bids.select()  # Default ON
        self.check_bids.grid(row=0, column=1, padx=15, pady=15)

        self.check_fmriprep = ctk.CTkCheckBox(
            self.frame_options, 
            text="fMRIPrep (Preprocessing)", 
            onvalue=True, 
            offvalue=False
        )
        # NOT selected by default - BIDS only is the common first step
        self.check_fmriprep.grid(row=0, column=2, padx=15, pady=15)

        # --- Quick Action Buttons ---
        self.frame_actions = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_actions.grid(row=3, column=0, padx=20, pady=5, sticky="ew")
        self.frame_actions.grid_columnconfigure((0, 1, 2), weight=1)

        self.btn_bids_only = ctk.CTkButton(
            self.frame_actions,
            text="▶ Run BIDS Only",
            height=45,
            fg_color="#2E7D32",  # Green
            hover_color="#1B5E20",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.run_bids_only
        )
        self.btn_bids_only.grid(row=0, column=0, padx=5, pady=10, sticky="ew")

        self.btn_full_pipeline = ctk.CTkButton(
            self.frame_actions,
            text="▶▶ Run Full Pipeline",
            height=45,
            fg_color="#1565C0",  # Blue
            hover_color="#0D47A1",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.run_full_pipeline
        )
        self.btn_full_pipeline.grid(row=0, column=1, padx=5, pady=10, sticky="ew")

        self.btn_custom = ctk.CTkButton(
            self.frame_actions,
            text="⚙ Run Selected Steps",
            height=45,
            fg_color="#424242",  # Gray
            hover_color="#212121",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.start_pipeline
        )
        self.btn_custom.grid(row=0, column=2, padx=5, pady=10, sticky="ew")

        # --- Progress Indicator ---
        self.frame_progress = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_progress.grid(row=4, column=0, padx=20, pady=(10, 5), sticky="ew")
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
            self, 
            text="Ready", 
            font=ctk.CTkFont(size=12),
            text_color="#888888"
        )
        self.label_status.grid(row=5, column=0, padx=20, pady=(0, 5), sticky="w")

        # --- Log Area ---
        self.label_logs = ctk.CTkLabel(
            self, 
            text="📋 Execution Logs", 
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.label_logs.grid(row=6, column=0, padx=20, pady=(10, 0), sticky="w")
        
        self.console = ConsoleLog(self)
        self.console.grid(row=7, column=0, padx=20, pady=(5, 20), sticky="nsew")

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
            output_path = Path(output_dir) / "output_<timestamp>" / "bids_output"
            self.label_output_info.configure(
                text=f"→ BIDS data will be saved to: {output_path}"
            )
            self.label_output_info.grid()  # Show the label
        else:
            self.label_output_info.grid_remove()  # Hide when empty

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
        """Quick action: Run BIDS conversion only."""
        self.check_bids.select()
        self.check_fmriprep.deselect()
        self.start_pipeline()

    def run_full_pipeline(self):
        """Quick action: Run both BIDS and fMRIPrep."""
        self.check_bids.select()
        self.check_fmriprep.select()
        self.start_pipeline()

    def start_pipeline(self):
        """Start the pipeline with currently selected options."""
        if not self._validate_paths():
            return
            
        if not self.check_bids.get() and not self.check_fmriprep.get():
            self.console.log("⚠️  Please select at least one step to run.", "warning")
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
        
        self.console.log("🚀 Pipeline Started", "header")
        self.console.log(f"📁 Source: {input_dir}")
        self.console.log(f"📂 Output Root: {output_dir}")
        self.console.log(f"📂 A timestamped folder (output_<timestamp>) will be created inside")
        
        steps = []
        if self.check_bids.get():
            steps.append("BIDS Conversion")
        if self.check_fmriprep.get():
            steps.append("fMRIPrep")
            
        self.console.log(f"⚙️  Steps: {', '.join(steps)}")
        self.console.log("=" * 60)

        self.label_status.configure(text="Processing...", text_color="#FFC107")

        # Run in background thread
        threading.Thread(target=self.run_subprocess, args=(input_dir, output_dir), daemon=True).start()

    def _set_buttons_state(self, state):
        """Enable/disable all action buttons."""
        self.btn_bids_only.configure(state=state)
        self.btn_full_pipeline.configure(state=state)
        self.btn_custom.configure(state=state)
        self.btn_browse_input.configure(state=state)
        self.btn_browse_output.configure(state=state)

    def run_subprocess(self, input_dir, output_dir):
        script_path = Path(__file__).parent / "scripts" / "run_pipeline.py"
        
        cmd = [
            sys.executable, str(script_path), 
            "--input", input_dir, 
            "--output_dir", output_dir
        ]

        if not self.check_bids.get():
            cmd.append("--skip-bids")
        if not self.check_fmriprep.get():
            cmd.append("--skip-fmriprep")

        try:
            self.current_process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                text=True, 
                bufsize=1
            )
            
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
                self.console.log("✅ COMPLETED SUCCESSFULLY!", "success")
                self.after(0, self._update_status_success)
            else:
                self.console.log("=" * 60)
                self.console.log(f"❌ PIPELINE FAILED (Exit Code {self.current_process.returncode})", "error")
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
            self.after(0, lambda: self.label_status.configure(
                text=f"Processing 0/{self.total_tasks} tasks...", 
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
        
        # [PROGRESS:TASK:N] - Task N completed
        elif match := re.match(r'\[PROGRESS:TASK:(\d+)\]', marker):
            self.completed_tasks = int(match.group(1))
            self.task_in_progress = False
            if self.total_tasks > 0:
                # Snap to actual progress
                self.current_progress = self.completed_tasks / self.total_tasks
                self.target_progress = self.current_progress
                self.after(0, lambda p=self.current_progress: self.progress_bar.set(p))
                self.after(0, lambda: self.label_status.configure(
                    text=f"Processing {self.completed_tasks}/{self.total_tasks} tasks...",
                    text_color="#FFC107"
                ))
        
        # [PROGRESS:COMPLETE] - All done
        elif marker == "[PROGRESS:COMPLETE]":
            self._stop_progress_animation()
            self.current_progress = 1.0
            self.after(0, lambda: self.progress_bar.set(1.0))
            self.after(0, lambda: self.label_status.configure(
                text="Finalizing...",
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
        try:
            # Terminate the subprocess
            if self.current_process:
                self.current_process.terminate()
                try:
                    self.current_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.current_process.kill()
                self.current_process = None
            
            # Delete the output folder
            if self.current_output_folder:
                output_path = Path(self.current_output_folder)
                if output_path.exists():
                    self.console.log(f"🗑 Deleting output folder: {output_path}", "warning")
                    shutil.rmtree(output_path)
                    self.console.log("✓ Output folder deleted", "info")
                self.current_output_folder = None
            
            self.console.log("=" * 60)
            self.console.log("⏹ EXECUTION CANCELLED BY USER", "warning")
            self.after(0, lambda: self.label_status.configure(
                text="⏹ Cancelled by user", 
                text_color="#FFC107"
            ))
            
        except Exception as e:
            self.console.log(f"❌ Error during cleanup: {e}", "error")
        
        # Reset UI
        self.after(0, self._reset_ui)
    
    def _update_status_success(self):
        self.label_status.configure(text="✓ Completed Successfully", text_color="#4CAF50")

    def _update_status_error(self):
        self.label_status.configure(text="✗ Failed - Check logs", text_color="#F44336")

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
