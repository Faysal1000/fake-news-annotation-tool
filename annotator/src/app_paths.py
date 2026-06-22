"""
Application path constants.

Resolves all filesystem paths after the frozen/script check.
"""

import sys
from pathlib import Path

if getattr(sys, 'frozen', False):
    _exe_path = Path(sys.executable).resolve()
    if ".app/Contents/MacOS" in _exe_path.as_posix():
        SCRIPT_DIR = _exe_path.parents[3]
    else:
        SCRIPT_DIR = _exe_path.parent
else:
    SCRIPT_DIR = Path(__file__).parent.parent.resolve()

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    ASSETS_DIR = Path(sys._MEIPASS) / "assets"
    VERSION_FILE = Path(sys._MEIPASS) / "version.json"
else:
    ASSETS_DIR = SCRIPT_DIR / "src" / "assets"
    VERSION_FILE = SCRIPT_DIR / "src" / "version.json"

IMAGES_DIR = SCRIPT_DIR / "images"
VIDEOS_DIR = SCRIPT_DIR / "videos"
CSV_PATH = SCRIPT_DIR / "dataset.csv"
CONFIG_PATH = SCRIPT_DIR / ".annotator_config.json"
KAPPA_CSV_PATH = SCRIPT_DIR / "relabeling_for_kappa.csv"

UPDATE_API_URL = "https://api.github.com/repos/Faysal1000/fake-news-annotation-tool/releases/latest"
UPDATE_DOWNLOAD_BASE_URL = "https://github.com/Faysal1000/fake-news-annotation-tool/releases/latest/download"
UPDATE_CHUNK_SIZE = 8192
