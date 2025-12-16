import customtkinter as ctk
from tkinter import filedialog, END
import subprocess
import threading
from pathlib import Path
import sys
import os
import time

# --- Custom Logger Widget with Colors ---
class ConsoleLog(ctk.CTkTextbox):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.configure(state="disabled", font=("Consolas", 13))
        self.tag_config("info", foreground="#DCDCDC")     # Light Gray
        self.tag_config("success", foreground="#4CAF50")  # Green
        self.tag_config("warning", foreground="#FFC107")  # Amber
        self.tag_config("error", foreground="#F44336")    # Red
        self.tag_config("header", foreground="#64B5F6")   # Blue (Font size removed to fix scaling error)

    def log(self, message, level="info"):
        # Thread-safe UI update using after()
        self.after(0, self._log_internal, message, level)

    def _log_internal(self, message, level):
        self.configure(state="normal")
        
        # Simple keyword-based coloring
        tag = level
        if "Failed!" in message or "Error" in message or "Traceback" in message:
            tag = "error"
        elif "Done." in message or "COMPLETED" in message:
            tag = "success"
        elif "Processing Subject" in message or "---" in message:
            tag = "header"

        self.insert(END, message + "\n", tag)
        self.see(END)
        self.configure(state="disabled")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window Setup
        self.title("fMRI Pipeline Manager")
        self.geometry("900x700")
        self.minsize(600, 500)
        
        # Grid Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(6, weight=1) # Log area expands
        
        # --- Header ---
        self.frame_header = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_header.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        
        self.label_title = ctk.CTkLabel(self.frame_header, text="fMRI Processing Assistant", font=ctk.CTkFont(size=26, weight="bold"))
        self.label_title.pack(anchor="w")
        
        self.label_subtitle = ctk.CTkLabel(self.frame_header, text="Convert & Preprocess your scans easily", font=ctk.CTkFont(size=14), text_color="gray")
        self.label_subtitle.pack(anchor="w")

        # --- Configuration Frame ---
        self.frame_config = ctk.CTkFrame(self)
        self.frame_config.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        self.frame_config.grid_columnconfigure(1, weight=1)

        # Input Directory
        self.label_input = ctk.CTkLabel(self.frame_config, text="Raw Data Folder:", font=ctk.CTkFont(weight="bold"))
        self.label_input.grid(row=0, column=0, padx=15, pady=15, sticky="w")
        
        self.entry_input = ctk.CTkEntry(self.frame_config, placeholder_text="Select the folder containing all subject folders...")
        self.entry_input.grid(row=0, column=1, padx=10, pady=15, sticky="ew")
        
        self.btn_browse_input = ctk.CTkButton(self.frame_config, text="Browse", width=100, command=self.browse_input)
        self.btn_browse_input.grid(row=0, column=2, padx=15, pady=15)

        # Output Directory
        self.label_output = ctk.CTkLabel(self.frame_config, text="Output Folder:", font=ctk.CTkFont(weight="bold"))
        self.label_output.grid(row=1, column=0, padx=15, pady=15, sticky="w")
        
        self.entry_output = ctk.CTkEntry(self.frame_config, placeholder_text="Select where to save results...")
        self.entry_output.grid(row=1, column=1, padx=10, pady=15, sticky="ew")
        
        self.btn_browse_output = ctk.CTkButton(self.frame_config, text="Browse", width=100, command=self.browse_output)
        self.btn_browse_output.grid(row=1, column=2, padx=15, pady=15)

        # --- Options Frame ---
        self.frame_options = ctk.CTkFrame(self)
        self.frame_options.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        
        self.label_steps = ctk.CTkLabel(self.frame_options, text="Select Steps:", font=ctk.CTkFont(weight="bold"))
        self.label_steps.grid(row=0, column=0, padx=15, pady=15)

        self.check_bids = ctk.CTkCheckBox(self.frame_options, text="1. Convert to BIDS", onvalue=True, offvalue=False)
        self.check_bids.select()
        self.check_bids.grid(row=0, column=1, padx=15, pady=15)

        self.check_fmriprep = ctk.CTkCheckBox(self.frame_options, text="2. Run fMRIPrep", onvalue=True, offvalue=False)
        self.check_fmriprep.select() # Default selected, user can uncheck
        self.check_fmriprep.grid(row=0, column=2, padx=15, pady=15)
        
        self.check_dryrun = ctk.CTkCheckBox(self.frame_options, text="Dry Run (Test)", onvalue=True, offvalue=False)
        self.check_dryrun.grid(row=0, column=3, padx=15, pady=15)

        # --- Run Button ---
        self.btn_run = ctk.CTkButton(self, text="START SELECTED STEPS", height=50, fg_color="#007AFF", hover_color="#0056b3", 
                                     font=ctk.CTkFont(size=16, weight="bold"), command=self.start_pipeline)
        self.btn_run.grid(row=4, column=0, padx=20, pady=20, sticky="ew")

        # --- Progress Indicator ---
        self.progress_bar = ctk.CTkProgressBar(self, mode="indeterminate")
        self.progress_bar.grid(row=5, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.progress_bar.set(0)
        self.progress_bar.grid_remove() # Hide initially

        # --- Log Area ---
        self.label_logs = ctk.CTkLabel(self, text="Execution Logs", font=ctk.CTkFont(size=12, weight="bold"))
        self.label_logs.grid(row=5, column=0, padx=20, pady=(10,0), sticky="w") # Shared row with progress, offset
        
        self.console = ConsoleLog(self)
        self.console.grid(row=6, column=0, padx=20, pady=(5, 20), sticky="nsew")

        self.is_running = False

    def browse_input(self):
        folder = filedialog.askdirectory()
        if folder:
            self.entry_input.delete(0, "end")
            self.entry_input.insert(0, folder)

    def browse_output(self):
        folder = filedialog.askdirectory()
        if folder:
            self.entry_output.delete(0, "end")
            self.entry_output.insert(0, folder)

    def start_pipeline(self):
        input_dir = self.entry_input.get()
        output_dir = self.entry_output.get()

        if not input_dir or not output_dir:
            self.console.log("⚠️  Please select both Input and Output folders.", "warning")
            return
            
        if not self.check_bids.get() and not self.check_fmriprep.get():
            self.console.log("⚠️  Please select at least one step to run.", "warning")
            return

        self.is_running = True
        self.btn_run.configure(state="disabled", text="Processing... (Please Wait)", fg_color="#555555")
        
        # Show and start progress bar
        self.progress_bar.grid()
        self.progress_bar.start()

        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")
        
        self.console.log(f"🚀 Pipeline Started...", "header")
        self.console.log(f"📂 Input: {input_dir}")
        self.console.log(f"📂 Output: {output_dir}")
        
        steps = []
        if self.check_bids.get(): steps.append("BIDS Conversion")
        if self.check_fmriprep.get(): steps.append("fMRIPrep")
        self.console.log(f"⚙️  Steps: {', '.join(steps)}")
        self.console.log("-" * 60)

        # Run in background thread
        threading.Thread(target=self.run_subprocess, args=(input_dir, output_dir)).start()

    def run_subprocess(self, input_dir, output_dir):
        script_path = Path(__file__).parent / "scripts" / "run_pipeline.py"
        
        cmd = [sys.executable, str(script_path), 
               "--input", input_dir, 
               "--output_dir", output_dir]

        if not self.check_bids.get():
            cmd.append("--skip-bids")
        if not self.check_fmriprep.get():
            cmd.append("--skip-fmriprep")
        if self.check_dryrun.get():
            cmd.append("--dry-run")

        try:
            # Popen allowing real-time output reading
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            
            for line in process.stdout:
                self.console.log(line.strip())
            
            process.wait()
            
            if process.returncode == 0:
                self.console.log("-" * 60)
                self.console.log("✅ COMPLETED SUCCESSFULLY!", "success")
                self.btn_run.configure(fg_color="#4CAF50", text="SUCCESS (Run Again?)")
            else:
                self.console.log("-" * 60)
                self.console.log(f"❌ PIPELINE FAILED (Exit Code {process.returncode})", "error")
                self.btn_run.configure(fg_color="#F44336", text="FAILED (Retry?)")

        except Exception as e:
            self.console.log(f"❌ Critical Error: {e}", "error")
            self.btn_run.configure(fg_color="#F44336", text="ERROR")

        # Reset UI state
        self.is_running = False
        self.progress_bar.stop()
        self.progress_bar.grid_remove()
        self.btn_run.configure(state="normal")

if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")  # Modes: "System" (standard), "Dark", "Light"
    ctk.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"
    app = App()
    app.mainloop()
