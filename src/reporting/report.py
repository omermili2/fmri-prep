"""
Conversion report generation for non-technical users.

This module creates human-readable reports explaining what happened
during BIDS conversion, what succeeded, what failed, and next steps.
"""

import threading
from datetime import datetime


class ConversionReport:
    """
    Tracks conversion results and generates human-readable reports.
    
    Thread-safe: can be updated from multiple parallel worker threads.
    
    Usage:
        report = ConversionReport()
        report.input_folder = "/path/to/input"
        report.output_folder = "/path/to/output"
        
        # During processing:
        report.add_success("001", "01", 45.2)
        report.add_failure("002", "01", "No DICOM files found", "BIDS")
        
        # After processing:
        report_text = report.generate_report()
    """
    
    def __init__(self):
        self._lock = threading.Lock()
        self.start_time = datetime.now()
        self.end_time = None
        
        # Results tracking
        self.successful = []   # List of {sub_id, ses_id, duration, details, output_files}
        self.failed = []       # List of {sub_id, ses_id, error, stage}
        self.warnings = []     # List of warning messages
        self.skipped = []      # List of skipped items with reasons
        
        # Configuration
        self.total_tasks = 0
        self.config_file = None
        self.input_folder = None
        self.output_folder = None
        self.skip_bids = False
        self.skip_fmriprep = False
        
        # Statistics
        self.output_stats = {}   # Scan type counts
        self.cleanup_info = {}   # Info about cleanup
    
    def add_success(self, sub_id, ses_id, duration, details="", output_files=None):
        """
        Record a successful conversion.
        
        Args:
            sub_id: Subject ID
            ses_id: Session ID  
            duration: Time taken in seconds
            details: Optional details about what was converted
            output_files: Optional list of output files created
        """
        with self._lock:
            self.successful.append({
                'sub_id': sub_id, 
                'ses_id': ses_id, 
                'duration': duration,
                'details': details,
                'output_files': output_files or []
            })
    
    def add_failure(self, sub_id, ses_id, error, stage="BIDS"):
        """
        Record a failed conversion.
        
        Args:
            sub_id: Subject ID
            ses_id: Session ID
            error: Error message or exception
            stage: Which stage failed ("BIDS" or "fMRIPrep")
        """
        with self._lock:
            self.failed.append({
                'sub_id': sub_id, 
                'ses_id': ses_id, 
                'error': str(error),
                'stage': stage
            })
    
    def add_skipped(self, sub_id, ses_id, reason):
        """Record a skipped session with reason."""
        with self._lock:
            self.skipped.append({
                'sub_id': sub_id,
                'ses_id': ses_id,
                'reason': reason
            })
    
    def add_warning(self, message):
        """Add a warning message to the report."""
        with self._lock:
            self.warnings.append(message)
    
    def set_output_stats(self, stats):
        """Set scan type statistics after scanning output."""
        with self._lock:
            self.output_stats = stats
    
    def set_cleanup_info(self, count, size_bytes):
        """Set information about cleanup."""
        with self._lock:
            self.cleanup_info = {'count': count, 'size': size_bytes}
    
    def finalize(self):
        """Mark the report as complete with end time."""
        self.end_time = datetime.now()
    
    def _simplify_error(self, error):
        """Convert technical errors to user-friendly messages."""
        error_lower = error.lower()
        
        if 'no such file' in error_lower or 'not found' in error_lower:
            return "The input files could not be found. Please check if the DICOM folder exists."
        elif 'permission denied' in error_lower:
            return "The program doesn't have permission to access these files. Check folder permissions."
        elif 'timeout' in error_lower:
            return "The conversion took too long (over 30 minutes). The data might be very large or there may be an issue."
        elif 'no dicom' in error_lower or 'no valid' in error_lower:
            return "No valid DICOM files were found in this folder."
        elif 'disk' in error_lower or 'space' in error_lower:
            return "Not enough disk space to complete the conversion."
        elif 'memory' in error_lower:
            return "Not enough computer memory (RAM) available."
        elif 'dcm2niix' in error_lower:
            return "The DICOM to NIfTI converter encountered an issue. The scan may be incomplete or corrupted."
        elif len(error) > 100:
            return error[:100] + "... (see detailed error below)"
        else:
            return error
    
    def _format_duration(self, seconds):
        """Format duration in human-readable format."""
        if seconds < 60:
            return f"{seconds:.1f} seconds"
        elif seconds < 3600:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins} min {secs} sec"
        else:
            hours = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            return f"{hours} hr {mins} min"
    
    def generate_report(self):
        """
        Generate a comprehensive human-readable report.
        
        The report is designed for non-technical users and includes:
        - Summary of what happened
        - List of successful conversions
        - Explanation of any failures with troubleshooting tips
        - Description of output folder structure
        - Next steps
        
        Returns:
            Multi-line string with the complete report
        """
        self.finalize()
        total_duration = (self.end_time - self.start_time).total_seconds()
        
        lines = []
        
        # Header with visual appeal
        lines.append("")
        lines.append("+" + "=" * 68 + "+")
        lines.append("|" + " " * 68 + "|")
        lines.append("|" + "BIDS CONVERSION REPORT".center(68) + "|")
        lines.append("|" + "fMRI Preprocessing Assistant".center(68) + "|")
        lines.append("|" + " " * 68 + "|")
        lines.append("+" + "=" * 68 + "+")
        lines.append("")
        
        # Date and time
        lines.append(f"  Generated: {self.end_time.strftime('%B %d, %Y at %I:%M %p')}")
        lines.append("")
        
        # ===== SUMMARY SECTION =====
        lines.append("-" * 70)
        lines.append("  SUMMARY")
        lines.append("-" * 70)
        lines.append("")
        
        success_count = len(self.successful)
        fail_count = len(self.failed)
        skip_count = len(self.skipped)
        
        # Big status box
        if fail_count == 0 and success_count > 0:
            lines.append("  +---------------------------------------------------------+")
            lines.append("  |                                                         |")
            lines.append("  |     SUCCESS! All your data was converted correctly.     |")
            lines.append("  |                                                         |")
            lines.append("  +---------------------------------------------------------+")
        elif fail_count > 0 and success_count > 0:
            lines.append("  +---------------------------------------------------------+")
            lines.append("  |                                                         |")
            lines.append("  |   PARTIAL SUCCESS - Some sessions had problems.         |")
            lines.append("  |   Please review the errors below.                       |")
            lines.append("  |                                                         |")
            lines.append("  +---------------------------------------------------------+")
        elif fail_count > 0 and success_count == 0:
            lines.append("  +---------------------------------------------------------+")
            lines.append("  |                                                         |")
            lines.append("  |   CONVERSION FAILED - No data was converted.            |")
            lines.append("  |   Please review the errors below for guidance.          |")
            lines.append("  |                                                         |")
            lines.append("  +---------------------------------------------------------+")
        else:
            lines.append("  +---------------------------------------------------------+")
            lines.append("  |                                                         |")
            lines.append("  |   NO DATA PROCESSED - Nothing was found to convert.     |")
            lines.append("  |                                                         |")
            lines.append("  +---------------------------------------------------------+")
        
        lines.append("")
        lines.append(f"  Scanning sessions processed:  {self.total_tasks}")
        lines.append(f"  Successfully converted:       {success_count}")
        if fail_count > 0:
            lines.append(f"  Failed (needs attention):     {fail_count}")
        if skip_count > 0:
            lines.append(f"  Skipped:                      {skip_count}")
        lines.append(f"  Total time:                   {self._format_duration(total_duration)}")
        
        if self.total_tasks > 0:
            success_rate = (success_count / self.total_tasks) * 100
            lines.append(f"  Success rate:                 {success_rate:.0f}%")
        lines.append("")
        
        # ===== WHAT WAS CREATED =====
        if success_count > 0:
            lines.append("-" * 70)
            lines.append("  YOUR CONVERTED DATA")
            lines.append("-" * 70)
            lines.append("")
            lines.append(f"  Output location:")
            lines.append(f"  {self.output_folder}")
            lines.append("")
            
            # Output statistics
            if self.output_stats and self.output_stats.get('total_nifti', 0) > 0:
                lines.append("  What was created:")
                lines.append("")
                lines.append(f"    {self.output_stats['total_nifti']} brain scan files (.nii.gz format)")
                if self.output_stats.get('anat', 0) > 0:
                    lines.append(f"      - {self.output_stats['anat']} anatomical scans (brain structure images)")
                if self.output_stats.get('func', 0) > 0:
                    lines.append(f"      - {self.output_stats['func']} functional scans (brain activity recordings)")
                if self.output_stats.get('dwi', 0) > 0:
                    lines.append(f"      - {self.output_stats['dwi']} diffusion scans (white matter imaging)")
                if self.output_stats.get('fmap', 0) > 0:
                    lines.append(f"      - {self.output_stats['fmap']} fieldmaps (distortion correction images)")
                lines.append("")
            
            # List successful conversions
            lines.append("  Sessions that were converted:")
            lines.append("")
            sorted_success = sorted(self.successful, key=lambda x: (x['sub_id'], x['ses_id']))
            for item in sorted_success:
                dur = self._format_duration(item['duration'])
                lines.append(f"    [OK] Subject {item['sub_id']}, Session {item['ses_id']} ({dur})")
            lines.append("")
        
        # ===== PROBLEMS / ERRORS =====
        if self.failed:
            lines.append("-" * 70)
            lines.append("  PROBLEMS THAT NEED ATTENTION")
            lines.append("-" * 70)
            lines.append("")
            lines.append("  The following sessions could NOT be converted:")
            lines.append("")
            
            sorted_failed = sorted(self.failed, key=lambda x: (x['sub_id'], x['ses_id']))
            for item in sorted_failed:
                lines.append(f"    [FAILED] Subject {item['sub_id']}, Session {item['ses_id']}")
                lines.append(f"             What went wrong: {self._simplify_error(item['error'])}")
                lines.append("")
            
            lines.append("  HOW TO FIX THESE PROBLEMS:")
            lines.append("")
            lines.append("    1. Check that DICOM files exist in the source folder")
            lines.append("    2. Make sure the files aren't corrupted (try opening one in a DICOM viewer)")
            lines.append("    3. Verify you have enough disk space (at least 2x the raw data size)")
            lines.append("    4. If problems persist, contact your lab's technical support")
            lines.append("")
        
        # ===== WARNINGS =====
        if self.warnings:
            lines.append("-" * 70)
            lines.append("  NOTES AND WARNINGS")
            lines.append("-" * 70)
            lines.append("")
            for warning in self.warnings:
                lines.append(f"    - {warning}")
            lines.append("")
        
        # ===== DATA FORMAT EXPLANATION =====
        if success_count > 0:
            lines.append("-" * 70)
            lines.append("  UNDERSTANDING YOUR OUTPUT FOLDER")
            lines.append("-" * 70)
            lines.append("")
            lines.append("  Your data is now in 'BIDS format' - a standard way to organize brain")
            lines.append("  imaging data. Here's what you'll find:")
            lines.append("")
            lines.append("    dataset_description.json")
            lines.append("        A file describing your dataset (required by BIDS)")
            lines.append("")
            lines.append("    sub-001/                    <- One folder per participant")
            lines.append("      ses-01/                   <- One folder per scanning session")
            lines.append("        anat/                   <- Structural brain images (T1, T2)")
            lines.append("          sub-001_ses-01_T1w.nii.gz     <- Compressed brain image")
            lines.append("          sub-001_ses-01_T1w.json       <- Scan parameters")
            lines.append("        func/                   <- Functional brain images (BOLD)")
            lines.append("          sub-001_ses-01_task-rest_bold.nii.gz")
            lines.append("          sub-001_ses-01_task-rest_bold.json")
            lines.append("")
            lines.append("    conversion_report.txt       <- This report file")
            lines.append("")
            lines.append("  File naming explained:")
            lines.append("    - sub-XXX: participant/subject ID")
            lines.append("    - ses-YY: session number (01, 02, etc.)")
            lines.append("    - T1w, T2w: type of anatomical scan")
            lines.append("    - bold: functional MRI data")
            lines.append("    - .nii.gz: compressed brain image format")
            lines.append("    - .json: metadata about the scan")
            lines.append("")
        
        # ===== NEXT STEPS =====
        lines.append("-" * 70)
        lines.append("  WHAT TO DO NEXT")
        lines.append("-" * 70)
        lines.append("")
        
        step = 1
        if fail_count > 0:
            lines.append(f"  {step}. FIX THE FAILED CONVERSIONS (see problems section above)")
            step += 1
        
        if success_count > 0:
            lines.append(f"  {step}. VERIFY YOUR DATA")
            lines.append("     Open a few .nii.gz files in a viewer like FSLeyes or ITK-SNAP")
            lines.append("     to make sure the brain images look correct.")
            lines.append("")
            step += 1
            
            lines.append(f"  {step}. QUALITY CHECK")
            lines.append("     Run MRIQC on your data to check image quality before preprocessing.")
            lines.append("     Website: https://mriqc.readthedocs.io/")
            lines.append("")
            step += 1
            
            lines.append(f"  {step}. PREPROCESS YOUR DATA")
            lines.append("     Use the 'Run Full Pipeline' button in the fMRI Preprocessing")
            lines.append("     Assistant to run fMRIPrep on your converted data.")
            lines.append("")
        
        # ===== TECHNICAL DETAILS =====
        lines.append("-" * 70)
        lines.append("  TECHNICAL DETAILS (for troubleshooting)")
        lines.append("-" * 70)
        lines.append("")
        lines.append(f"    Source folder:     {self.input_folder}")
        lines.append(f"    Output folder:     {self.output_folder}")
        lines.append(f"    Config file:       {self.config_file}")
        lines.append(f"    Started:           {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"    Finished:          {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"    Duration:          {self._format_duration(total_duration)}")
        
        if self.cleanup_info:
            size_mb = self.cleanup_info.get('size', 0) / (1024 * 1024)
            lines.append(f"    Temp files cleaned: {self.cleanup_info.get('count', 0)} ({size_mb:.1f} MB)")
        lines.append("")
        
        # Footer
        lines.append("+" + "=" * 68 + "+")
        lines.append("|" + "Report generated by fMRI Preprocessing Assistant".center(68) + "|")
        lines.append("|" + "For help, contact your lab's technical support".center(68) + "|")
        lines.append("+" + "=" * 68 + "+")
        lines.append("")
        
        return "\n".join(lines)

