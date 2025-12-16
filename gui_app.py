import customtkinter as ctk
from tkinter import filedialog, END
import subprocess
import threading
from pathlib import Path
import sys
import os


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
        self.title("fMRI Pipeline Manager")
        self.geometry("950x750")
        self.minsize(700, 550)
        
        # Grid Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(7, weight=1)  # Log area expands
        
        # --- Header ---
        self.frame_header = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_header.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        
        self.label_title = ctk.CTkLabel(
            self.frame_header, 
            text="fMRI Processing Assistant", 
            font=ctk.CTkFont(size=26, weight="bold")
        )
        self.label_title.pack(anchor="w")
        
        self.label_subtitle = ctk.CTkLabel(
            self.frame_header, 
            text="Convert DICOM to BIDS format & Run fMRIPrep preprocessing", 
            font=ctk.CTkFont(size=14), 
            text_color="gray"
        )
        self.label_subtitle.pack(anchor="w")

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
            placeholder_text="Select folder containing subject folders (e.g., 110/, 111/, ...)"
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
            placeholder_text="Select a NEW folder for BIDS output (will create bids_output/ inside)"
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
        self.label_output_info.grid(row=2, column=1, padx=10, pady=(0, 10), sticky="w")

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
        
        self.check_dryrun = ctk.CTkCheckBox(
            self.frame_options, 
            text="🧪 Dry Run (Preview)", 
            onvalue=True, 
            offvalue=False
        )
        self.check_dryrun.grid(row=0, column=3, padx=15, pady=15)

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
        self.progress_bar = ctk.CTkProgressBar(self, mode="indeterminate")
        self.progress_bar.grid(row=4, column=0, padx=20, pady=(10, 5), sticky="ew")
        self.progress_bar.set(0)
        self.progress_bar.grid_remove()  # Hide initially

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
        
        # Initial welcome message
        self.console.log("Welcome! Select your source DICOM folder and output folder to begin.", "info")
        self.console.log("", "info")
        self.console.log("📌 Your source data structure should be:", "info")
        self.console.log("   /source_folder/110/MRI1/scans/.../*.dcm", "info")
        self.console.log("   /source_folder/110/MRI2/scans/.../*.dcm", "info")
        self.console.log("", "info")
        self.console.log("📌 Output will be created as:", "info")
        self.console.log("   /output_folder/bids_output/sub-110/ses-01/...", "info")
        self.console.log("   /output_folder/bids_output/sub-110/ses-02/...", "info")

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
            bids_path = Path(output_dir) / "bids_output"
            self.label_output_info.configure(
                text=f"→ BIDS data will be saved to: {bids_path}"
            )

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

        if str(input_path).startswith(str(output_path) + os.sep):
            self.console.log("⚠️  Input folder cannot be inside the output folder!", "warning")
            return False

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
        self._set_buttons_state("disabled")
        
        # Show and start progress bar
        self.progress_bar.grid()
        self.progress_bar.start()

        # Clear and prepare console
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")
        
        self.console.log("🚀 Pipeline Started", "header")
        self.console.log(f"📁 Source: {input_dir}")
        self.console.log(f"📂 Output: {output_dir}")
        
        bids_path = Path(output_dir) / "bids_output"
        self.console.log(f"📂 BIDS Output: {bids_path}")
        
        steps = []
        if self.check_bids.get():
            steps.append("BIDS Conversion")
        if self.check_fmriprep.get():
            steps.append("fMRIPrep")
        if self.check_dryrun.get():
            steps.append("(DRY RUN)")
            
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
        if self.check_dryrun.get():
            cmd.append("--dry-run")

        try:
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                text=True, 
                bufsize=1
            )
            
            for line in process.stdout:
                self.console.log(line.strip())
            
            process.wait()
            
            if process.returncode == 0:
                self.console.log("=" * 60)
                self.console.log("✅ COMPLETED SUCCESSFULLY!", "success")
                self.after(0, self._update_status_success)
            else:
                self.console.log("=" * 60)
                self.console.log(f"❌ PIPELINE FAILED (Exit Code {process.returncode})", "error")
                self.after(0, self._update_status_error)

        except Exception as e:
            self.console.log(f"❌ Critical Error: {e}", "error")
            self.after(0, self._update_status_error)

        # Reset UI state (thread-safe)
        self.after(0, self._reset_ui)

    def _update_status_success(self):
        self.label_status.configure(text="✓ Completed Successfully", text_color="#4CAF50")

    def _update_status_error(self):
        self.label_status.configure(text="✗ Failed - Check logs", text_color="#F44336")

    def _reset_ui(self):
        self.is_running = False
        self.progress_bar.stop()
        self.progress_bar.grid_remove()
        self._set_buttons_state("normal")


if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()
