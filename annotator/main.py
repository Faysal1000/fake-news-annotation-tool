"""
Fake News Dataset Annotator Entry Point.

Ensures that the src/ folder is added to python path, then imports
bootstrap and launches the main CTk application window.
"""

import sys
import multiprocessing
from pathlib import Path

# Add src/ directory to python path
src_dir = Path(__file__).parent.resolve() / "src"
sys.path.insert(0, str(src_dir))

from bootstrap import _check_and_install
_check_and_install()

from ui.main_window import AnnotatorTool

if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = AnnotatorTool()
    app.mainloop()
