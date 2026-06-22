"""
Dependency and drag-and-drop capability verification.

Checks if all required external packages are present in the python environment.
If packages are missing and this is not a compiled executable, runs pip to
install dependencies located in the script directory. Also attempts to load
tkinterdnd2 dynamically.
"""

import subprocess
import sys
from pathlib import Path

REQUIRED = {"customtkinter": "customtkinter", "PIL": "Pillow", "tkinterdnd2": "tkinterdnd2", "requests": "requests"}

def _check_and_install():
    """
    Checks if all required external packages are present in the python environment.
    If packages are missing and this is not a compiled executable, runs pip to
    install dependencies located in the script directory.
    """
    if getattr(sys, 'frozen', False):
        return
    missing = []
    for module, pip_name in REQUIRED.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(pip_name)
    if missing:
        # Find requirements.txt next to this module or in parent
        req_file = Path(__file__).parent.resolve() / "requirements.txt"
        if not req_file.exists():
            req_file = Path(__file__).parent.parent.resolve() / "annotator" / "requirements.txt"
        if not req_file.exists():
            req_file = Path(__file__).parent.parent.resolve() / "requirements.txt"
        if not req_file.exists():
            req_file = Path(__file__).parent.parent.parent.resolve() / "requirements.txt"
        print(f"[INFO] Missing packages: {missing}. Installing from requirements.txt ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(req_file)])

# Run the dependency setup check on startup before main imports
_check_and_install()

try:
    # pyrefly: ignore [missing-import]
    from tkinterdnd2 import TkinterDnD, DND_FILES
    dnd_available = True
    dnd_base = TkinterDnD.DnDWrapper
except ImportError:
    dnd_available = False
    dnd_base = object
    DND_FILES = None
