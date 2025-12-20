#!/usr/bin/env python3
"""
fMRI Preprocessing Assistant - Entry Point

Usage:
    python run.py          # Launch GUI
    python run.py --help   # Show help
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

if __name__ == "__main__":
    # Import from the new modular structure
    from gui.app import App
    
    app = App()
    app.mainloop()
