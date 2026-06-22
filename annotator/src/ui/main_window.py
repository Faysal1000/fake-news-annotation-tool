"""
Main window orchestrator class.

Defines the AnnotatorTool class which inherits from all mixins
to construct, coordinate, and run the application.
"""

import sys
import json
import threading
import customtkinter as ctk
from PIL import ImageTk

# Mixin Imports
from ui.build_ui import UIBuilderMixin
from modes.mode_controller import ModeControllerMixin
from modes.annotate_mode import AnnotateModeMixin
from modes.review_mode import ReviewModeMixin
from modes.relabel_mode import RelabelModeMixin
from media.media_manager import MediaMixin
from shortcuts.keyboard import ShortcutMixin
from ui.filter_panel import FilterMixin
from ui.stats_popup import StatsMixin
from ui.scripts_popup import ScriptsMixin
from duplicates.duplicate_engine import DuplicateEngineMixin
from ui.duplicate_popup import DuplicateUIMixin
from updater.update_manager import UpdateMixin
from sync.global_sync import GlobalSyncMixin
from ui.dialogs import DialogMixin

from bootstrap import dnd_base, TkinterDnD
import bootstrap
dnd_available = bootstrap.dnd_available

from data.csv_manager import ensure_dirs, migrate_csv_format
from app_paths import ASSETS_DIR, VERSION_FILE

class AnnotatorTool(
    UIBuilderMixin,
    ModeControllerMixin,
    AnnotateModeMixin,
    ReviewModeMixin,
    RelabelModeMixin,
    MediaMixin,
    ShortcutMixin,
    FilterMixin,
    StatsMixin,
    ScriptsMixin,
    DuplicateEngineMixin,
    DuplicateUIMixin,
    UpdateMixin,
    GlobalSyncMixin,
    DialogMixin,
    ctk.CTk,
    dnd_base,
):
    """
    The main GUI application window class.
    Manages the application lifecycle, GUI layouts, and user interactions.
    Handles mode switching, dataset loading/saving, and drag-and-drop bindings.
    """

    def __init__(self):
        """
        Initializes the application window, sets up the styling, prepares state variables,
        and builds the responsive user interface.
        """
        super().__init__()

        # Register Tcl/Tk drag-and-drop extension if available
        global dnd_available
        if dnd_available:
            try:
                self.TkdndVersion = TkinterDnD._require(self)
            except Exception as e:
                print(f"[WARNING] Failed to load tkdnd Tcl library: {e}")
                dnd_available = False

        # Ensure directory structures are created and CSV is migrated on start
        ensure_dirs()
        migrate_csv_format()

        # Apply dark styling and standard blue accent color
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        try:
            if VERSION_FILE.exists():
                with open(VERSION_FILE, "r") as f:
                    v_data = json.load(f)
                    version_str = v_data.get("version", "")
                self.title(f"📰 Fake News Dataset Annotator {version_str}".strip())
            else:
                self.title("📰 Fake News Dataset Annotator")
        except Exception as e:
            print(f"[WARNING] Failed to load version: {e}")
            self.title("📰 Fake News Dataset Annotator")
        
        # Set application icon for window and taskbar
        try:
            icon_ico = ASSETS_DIR / "app_icon.ico"
            icon_png = ASSETS_DIR / "app_icon.png"
            if sys.platform == "win32" and icon_ico.exists():
                self.iconbitmap(icon_ico)
            elif icon_png.exists():
                img = ImageTk.PhotoImage(file=icon_png)
                self.iconphoto(True, img)
                # Keep a reference to prevent garbage collection
                self._app_icon_img = img
        except Exception as e:
            print(f"[WARNING] Failed to load app icon: {e}")
        # Center the window on startup
        window_width = 1200
        window_height = 850
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x_cordinate = int((screen_width / 2) - (window_width / 2))
        y_cordinate = int((screen_height / 2) - (window_height / 2))
        
        self.geometry(f"{window_width}x{window_height}+{x_cordinate}+{y_cordinate}")
        self.minsize(900, 650)

        # Layout state variable for responsive scaling
        self._current_layout_mode = None
        self._update_download_cancel = None
        self._update_download_thread = None

        # Check for remote updates asynchronously to keep application UI responsive
        threading.Thread(target=self._check_for_updates, daemon=True).start()

        # Bind window close event to check for unsaved changes
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        # Image list stores attached images as tuples of (file_path, PIL_image_object)
        # Allows distinguishing between filesystem paths and clipboard images
        self.image_list = []
        
        # Video path stores the path of the selected video (maximum 1 video per record)
        self.video_path = None

        # Holds references to PhotoImage objects so they are not garbage collected
        self.preview_photos = []

        # Tracks media files that are referenced in the CSV but cannot be found in images/ or videos/ directories
        self.missing_media = []

        # Review Mode State
        # Keeps track of the current application mode: 'annotate', 'review', or 'relabel'
        self.current_mode = "annotate"
        # Holds the complete list of records loaded from the dataset CSV
        self.all_dataset_records = []
        # Holds the active filtered subset of records based on the filter constraints
        self.dataset_records = []
        # Active filter parameters used for restricting records shown in Review mode
        self.advanced_filter = None  
        # Current index in the dataset_records list being viewed
        self.current_review_index = 0
        # Stores user progress draft when switching between different views
        self.draft_annotation = None

        # Global Metrics Sync State
        self.global_metrics_enabled = ctk.BooleanVar(value=False)
        self.global_metrics_data = {}
        self.last_global_sync_time = None
        self.last_uploaded_counts = {}
        self.is_global_syncing = False
        self._sync_lock = threading.Lock()

        # Re-label Mode State
        # Holds all records loaded from the kappa calculation target CSV
        self.kappa_records = []
        # Stores columns of the kappa CSV dynamically
        self.kappa_csv_columns = []
        # Current index in the kappa records list being viewed
        self.current_kappa_index = 0

        # Construct widgets, register drop areas, and initialize database statistics
        self._build_ui()
        self._setup_shortcuts()
        self._setup_dnd()
        self._update_stats()

        # Start the background 5-minute sync loop
        self.after(5000, self._sync_global_metrics_loop)

        # Automatically save the annotator name field as the user types
        self.annotator_entry.bind("<KeyRelease>",
            lambda e: self._on_annotator_name_change())
        self.annotator_entry.bind("<FocusOut>",
            lambda e: self._on_annotator_name_change())
