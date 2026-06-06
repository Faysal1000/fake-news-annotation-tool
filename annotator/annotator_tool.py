#!/usr/bin/env python3
"""
Fake News Dataset Annotation Tool
==================================
A GUI-based annotation tool for constructing a multimodal fake news
detection dataset. Built with CustomTkinter for a modern dark-themed UI.

This tool allows multiple annotators to:
  - Enter news text content
  - Attach one or more images (browse, paste, or drag-and-drop)
  - Select a label (Fake / Real)
  - Optionally specify a source and category
  - Save everything to a CSV file with images stored in an 'images/' folder

The CSV uses UUID-based IDs so multiple annotators can merge their datasets
without ID collisions. Multiple images for a single entry are joined with
semicolons (;) in the image_path column.

Usage:
    python annotator_tool.py
"""

import subprocess
import sys
from pathlib import Path

# =============================================================================
# AUTO-INSTALL MISSING DEPENDENCIES
# =============================================================================
# Maps Python module names to their pip package names.
# Before the main imports, we check if each module is importable.
# If any are missing, we install everything from requirements.txt.
# This lets any user run the script directly without a manual pip install step.
REQUIRED = {"customtkinter": "customtkinter", "PIL": "Pillow", "tkinterdnd2": "tkinterdnd2", "requests": "requests"}

def _check_and_install():
    """Check for required packages and install them if missing.
    
    Iterates through the REQUIRED dict, tries to import each module,
    and collects any that fail. If there are missing packages, it runs
    pip install using the requirements.txt file located next to this script.
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
        req_file = Path(__file__).parent.resolve() / "requirements.txt"
        print(f"[INFO] Missing packages: {missing}. Installing from requirements.txt ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(req_file)])

# Run the dependency check immediately on script load
_check_and_install()

# =============================================================================
# IMPORTS (only reached after dependencies are guaranteed installed)
# =============================================================================
# pyrefly: ignore [missing-import]
import customtkinter as ctk          # Modern themed tkinter widgets
from tkinter import filedialog, messagebox  # Native file dialog and message popups
import tkinter as tk                 # Base tkinter (used for some constants)
# pyrefly: ignore [missing-import]
from PIL import Image, ImageTk, ImageGrab  # Image processing, display, clipboard
import csv                           # CSV reading and writing
import os                            # OS-level file operations
import shutil                        # File copy utility
import json                          # Config file persistence
import uuid                          # UUID generation for unique entry IDs
from datetime import datetime        # Timestamps for each saved entry
import requests                      # For version checking
import threading                     # For non-blocking API calls
import platform                      # For OS detection

# Try to import tkinterdnd2 for drag-and-drop wrapper support
try:
    # pyrefly: ignore [missing-import]
    from tkinterdnd2 import TkinterDnD, DND_FILES
    dnd_available = True
    dnd_base = TkinterDnD.DnDWrapper
except ImportError:
    dnd_available = False
    dnd_base = object

# =============================================================================
# CONSTANTS
# =============================================================================
# SCRIPT_DIR: The directory where data files (CSV, images, config) are stored.
# When running as a normal Python script, this is the script's directory.
# When running as a PyInstaller bundle, this is the directory containing
# the executable, so that dataset.csv and images/ appear next to the .app/.exe.
if getattr(sys, 'frozen', False):
    # Running as a PyInstaller bundle
    _exe_path = Path(sys.executable).resolve()
    # On macOS, if it's inside a .app bundle, navigate up 4 levels to the folder containing the .app
    # _exe_path = .../FakeNewsAnnotator.app/Contents/MacOS/FakeNewsAnnotator
    if ".app/Contents/MacOS" in _exe_path.as_posix():
        SCRIPT_DIR = _exe_path.parents[3]
    else:
        SCRIPT_DIR = _exe_path.parent
else:
    # Running as a normal Python script
    SCRIPT_DIR = Path(__file__).parent.resolve()

# IMAGES_DIR: Folder where all uploaded/pasted images are saved.
IMAGES_DIR = SCRIPT_DIR / "images"

# CSV_PATH: The main dataset CSV file. Created automatically on first save.
CSV_PATH = SCRIPT_DIR / "dataset.csv"

# CONFIG_PATH: Hidden JSON file that remembers the annotator's name across sessions.
CONFIG_PATH = SCRIPT_DIR / ".annotator_config.json"

# CSV_COLUMNS: The column headers for the dataset CSV file.
# - id:         UUID string (unique per entry, safe for merging across annotators)
# - text:       The news text content (can be empty if image is provided)
# - image_path: Relative path(s) to image(s), semicolon-separated if multiple
# - label:      "Fake" or "Real" (required)
# - source:     Where the news came from (optional)
# - category:   Predefined topic category (optional)
# - annotator:  Name of the person who annotated this entry
# - annotation_confidence: Confidence level of the annotation (0-100, default 100)
# - timestamp:  ISO-format datetime when the entry was saved
# - heading:         Optional headline/title of the news item
# - multi_category:  Sub-classification for fake news (Misinformation/Rumor/Clickbait)
#                    or "Real" when the label is Real
# - source_category: Platform/medium where the news was found (required)
CSV_COLUMNS = ["id", "heading", "text", "image_path", "label", "multi_category",
               "source", "source_category", "category", "annotator", "annotation_confidence",
               "additional_notes", "timestamp"]

# CATEGORIES: Predefined category options for the dropdown menu.
# First entry is empty string (no category selected).
# "Other" is provided as a catch-all for categories not in the list.
CATEGORIES = ["", "Politics", "Health", "Science", "Technology", "Sports",
              "Entertainment", "Religion", "Education", "Environment",
              "International", "Miscellaneous"]

# MULTI_CATEGORIES: Sub-classification options shown when the label is "Fake".
# The annotator must pick exactly one to describe the type of fake news.
MULTI_CATEGORIES = ["Misinformation", "Rumor", "Clickbait"]

# SOURCE_CATEGORIES: Predefined platform/medium options for the source category
# dropdown. This field is required — the annotator must specify where the
# news item was found or published.
SOURCE_CATEGORIES = ["", "News Channel", "Newspaper", "Facebook", "Tiktok",
                        "Twitter", "Instagram", "Reddit", "YouTube",
                         "Blog", "Website", "Miscellaneous"]

# IMAGE_EXTENSIONS: Allowed image file extensions. Only these file types
# can be browsed, pasted, or dropped into the tool.
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp")


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def ensure_dirs():
    """Create the images directory if it does not already exist.
    
    Called once at startup to make sure the 'images/' folder is ready
    before any image save operations.
    """
    IMAGES_DIR.mkdir(exist_ok=True)


def generate_id():
    """Generate a UUID4 string to use as a unique entry ID.
    
    UUID4 is random-based, so there is virtually zero chance of collision
    even when multiple annotators work independently and merge later.
    
    Returns:
        str: A UUID string like '550e8400-e29b-41d4-a716-446655440000'
    """
    return str(uuid.uuid4())


def get_image_count():
    """Count how many image files currently exist in the images/ folder.
    
    Only counts files whose extension matches IMAGE_EXTENSIONS.
    Used for generating the sequential image number in filenames
    and for displaying stats in the UI.
    
    Returns:
        int: Number of image files in the images directory.
    """
    if not IMAGES_DIR.exists():
        return 0
    return len([f for f in IMAGES_DIR.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS])


def get_entry_count():
    """Count how many data rows exist in the dataset CSV file.
    
    Reads the CSV with DictReader (skipping the header automatically)
    and counts the rows. Used for displaying stats in the UI.
    
    Returns:
        int: Number of entries (rows) in the CSV, or 0 if file doesn't exist.
    """
    if not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0:
        return 0
    with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.DictReader(f))


def get_label_counts():
    """Count entries by label (Fake/Real), fake news subcategories, and news categories.
    
    Reads the CSV and tallies:
      - Total entries
      - Fake entries
      - Real entries
      - Fake subcategory breakdown (Misinformation, Rumor, Clickbait)
      - News category breakdown (Politics, Health, etc.)
    
    Returns:
        dict: Keys 'total', 'fake', 'real', 'fake_subcategories' (a dict
              mapping subcategory name to count), and 'news_categories'
              (a dict mapping category name to count).
    """
    result = {"total": 0, "fake": 0, "real": 0,
              "fake_subcategories": {"Misinformation": 0, "Rumor": 0, "Clickbait": 0},
              "news_categories": {},
              "only_image": 0, "only_text": 0, "both_text_image": 0}
    if not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0:
        return result
    with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            result["total"] += 1
            label = (row.get("label") or "").strip()
            if label == "Fake":
                result["fake"] += 1
                sub = (row.get("multi_category") or "").strip()
                if sub in result["fake_subcategories"]:
                    result["fake_subcategories"][sub] += 1
            elif label == "Real":
                result["real"] += 1
            # Count news categories
            cat = (row.get("category") or "").strip()
            if cat:
                result["news_categories"][cat] = result["news_categories"].get(cat, 0) + 1
            
            # Content breakdown
            has_text = bool((row.get("text") or "").strip())
            image_paths = row.get("image_path") or ""
            has_image = bool([p for p in image_paths.split(";") if p.strip()])
            
            if has_text and has_image:
                result["both_text_image"] += 1
            elif has_text and not has_image:
                result["only_text"] += 1
            elif not has_text and has_image:
                result["only_image"] += 1
    return result


def save_config(annotator_name):
    """Persist the annotator's name to a hidden JSON config file.
    
    This is called automatically whenever the annotator name field changes
    (on every keystroke and focus-out), so the name is remembered for
    the next session without needing to click Save.
    
    Args:
        annotator_name: The annotator's name string to save.
    """
    with open(CONFIG_PATH, "w") as f:
        json.dump({"annotator": annotator_name}, f)


def load_config():
    """Load the previously saved annotator name from the config file.
    
    Called once at startup to pre-fill the annotator name field.
    
    Returns:
        str: The saved annotator name, or empty string if no config exists.
    """
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            return json.load(f).get("annotator", "")
    return ""


def sanitize_name(name):
    """Convert an annotator name into a filesystem-safe string.
    
    Replaces any non-alphanumeric character with an underscore.
    Used when building image filenames to avoid spaces or special chars.
    
    Args:
        name: Raw annotator name string.
    
    Returns:
        str: Sanitized name safe for use in filenames.
    """
    return "".join(c if c.isalnum() else "_" for c in name.strip())


# =============================================================================
# MAIN APPLICATION CLASS
# =============================================================================

class FlowFrame(ctk.CTkFrame):
    """A custom frame that automatically wraps its children to a new line if they exceed the frame's width."""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.bind("<Configure>", self._on_configure)

    def _arrange(self):
        width = self.winfo_width()
        if width <= 10:  # Skip if frame is not fully drawn yet
            return
            
        rows = []
        current_row = []
        x = 0
        max_height = 0
        
        for child in self.winfo_children():
            cw = child.winfo_reqwidth()
            ch = child.winfo_reqheight()
            
            if x + cw > width and current_row:
                rows.append((current_row, x - 10, max_height))  # x - 10 to remove trailing spacing
                current_row = []
                x = 0
                max_height = 0
                
            current_row.append((child, cw, ch))
            x += cw + 10  # Horizontal spacing between labels
            max_height = max(max_height, ch)
            
        if current_row:
            rows.append((current_row, x - 10, max_height))
            
        y = 0
        total_height = 0
        for row_items, row_width, row_height in rows:
            start_x = (width - row_width) // 2
            start_x = max(0, start_x)  # Prevent negative x if width is very small
            
            x_offset = start_x
            for child, cw, ch in row_items:
                child.place(x=x_offset, y=y)
                x_offset += cw + 10
                
            y += row_height + 5  # Vertical spacing
            total_height += row_height + 5
            
        if total_height > 0:
            total_height -= 5 # Remove trailing vertical spacing
            
        if total_height != self.winfo_reqheight() and total_height > 0:
            self.configure(height=total_height)

    def _on_configure(self, event=None):
        self._arrange()

class AnnotatorTool(ctk.CTk, dnd_base):
    """Main GUI application for annotating fake news dataset entries.
    
    Inherits from customtkinter.CTk (the main window class).
    Manages the entire annotation workflow: input fields, image handling,
    validation, and saving to CSV.
    """

    def __init__(self):
        """Initialize the annotation tool window.
        
        Sets up the dark theme, creates the images directory,
        initializes the image list, builds the UI, sets up drag-and-drop,
        and binds the annotator name field to auto-save on edit.
        """
        super().__init__()

        # Initialize Drag & Drop if available
        global dnd_available
        if dnd_available:
            try:
                self.TkdndVersion = TkinterDnD._require(self)
            except Exception as e:
                print(f"[WARNING] Failed to load tkdnd Tcl library: {e}")
                dnd_available = False

        # Make sure the images/ directory exists before anything else
        ensure_dirs()

        # Set the visual theme to dark mode with blue accent color
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Configure the main window title, size, and minimum dimensions
        self.title("📰 Fake News Dataset Annotator")
        
        # --- INITIAL WINDOW SIZE SETTINGS ---
        # You can change the initial opening size by modifying these two values:
        window_width = 1200
        window_height = 850
        
        # Calculate screen center coordinates
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x_cordinate = int((screen_width / 2) - (window_width / 2))
        y_cordinate = int((screen_height / 2) - (window_height / 2))
        
        self.geometry(f"{window_width}x{window_height}+{x_cordinate}+{y_cordinate}")
        self.minsize(900, 650)

        # Track current column layout mode for responsive resizing
        self._current_layout_mode = None

        # Check for updates in the background
        threading.Thread(target=self._check_for_updates, daemon=True).start()

        # Handle window close safely
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        # IMAGE LIST: Stores all images attached to the current entry.
        # Each item in the list is a tuple of (file_path, pil_image):
        #   - (Path, None)  -> image selected from file system (path stored)
        #   - (None, Image)  -> image pasted from clipboard (PIL object stored)
        # This list is cleared after each save.
        self.image_list = []

        # PREVIEW PHOTOS: Keeps references to ImageTk.PhotoImage objects.
        # Tkinter requires us to hold a reference to displayed images,
        # otherwise they get garbage collected and disappear from the UI.
        self.preview_photos = []

        # REVIEW MODE STATE:
        # Tracks which mode the app is in ('annotate' or 'review')
        self.current_mode = "annotate"
        # Holds all CSV rows loaded into memory for browsing in review mode
        self.all_dataset_records = []
        # Holds the currently filtered subset of records
        self.dataset_records = []
        # The currently active advanced filter settings in Review mode
        self.advanced_filter = None  # dict with keys: labels, types, categories, annotators, min_conf, max_conf
        # Index of the currently displayed record in review mode
        self.current_review_index = 0
        # Temporarily stores the user's in-progress annotation when switching modes
        self.draft_annotation = None

        # Build all UI elements, set up drag-and-drop, and refresh stats
        self._build_ui()
        self._setup_dnd()
        self._update_stats()

        # AUTO-SAVE ANNOTATOR NAME:
        # Whenever the user types in or tabs away from the annotator field,
        # immediately persist the name to the config file. This way the
        # name is remembered even if the user closes the tool without saving.
        self.annotator_entry.bind("<KeyRelease>",
            lambda e: save_config(self.annotator_entry.get().strip()) if self.current_mode == "annotate" else None)
        self.annotator_entry.bind("<FocusOut>",
            lambda e: save_config(self.annotator_entry.get().strip()) if self.current_mode == "annotate" else None)

    # =========================================================================
    # UI CONSTRUCTION
    # =========================================================================

    def _build_ui(self):
        """Build the entire GUI layout.
        
        Creates a two-column responsive desktop layout:
        - Top: stats badge cards (centered)
        - Left column: heading, text, images
        - Right column: form controls (annotator, label, categories, etc.)
        - Bottom: navigation + action buttons
        """
        # Main container (no scrolling — desktop-optimized)
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=18, pady=10)
        self._main_frame = main  # Store reference for responsive layout

        # ----- TOP BAR: Mode switcher (left) + Title (center) -----
        top_bar = ctk.CTkFrame(main, fg_color="transparent", height=38)
        top_bar.pack(fill="x", pady=(5, 2))
        top_bar.pack_propagate(False)  # keep fixed height for place() centering

        self.mode_switcher = ctk.CTkSegmentedButton(
            top_bar, values=["📝 Annotate", "🔍 Review"],
            command=self._toggle_mode,
            font=ctk.CTkFont(size=12),
            selected_color="#1f6aa5", selected_hover_color="#144870",
            height=28, width=180
        )
        self.mode_switcher.set("📝 Annotate")
        self.mode_switcher.pack(side="left", padx=(0, 10))
        
        # Filter button + indicator on the right (hidden by default, shown in Review mode)
        self.filter_indicator = ctk.CTkLabel(top_bar, text="",
                                              font=ctk.CTkFont(size=12),
                                              text_color="#f39c12")
        # Not packed yet — shown only in Review mode
        
        self.filter_btn = ctk.CTkButton(top_bar, text="🔍 Filter", command=self._show_filter_popup,
                                         width=80, height=32,
                                         font=ctk.CTkFont(size=13),
                                         fg_color="#2d2d5e", hover_color="#3d3d7e",
                                         border_width=1, border_color="#555",
                                         corner_radius=6)
        # Not packed yet — shown only in Review mode

        ctk.CTkLabel(top_bar, text="📰 Fake News Dataset Annotator",
                     font=ctk.CTkFont(size=22, weight="bold")).place(relx=0.5, rely=0.5, anchor="center")

        # ----- Stats bar: colored badge cards -----
        self.stats_frame = FlowFrame(main, fg_color="transparent")
        self.stats_frame.pack(fill="x", pady=(4, 2))

        # ----- Category stats bar: news category counts -----
        self.category_stats_frame = FlowFrame(main, fg_color="transparent")
        self.category_stats_frame.pack(fill="x", pady=(0, 6))

        # ----- BOTTOM BAR: Grid layout with 2 equal columns -----
        self.bottom_bar = ctk.CTkFrame(main, fg_color="#1a1a2e", corner_radius=8,
                                        border_width=1, border_color="#333")
        self.bottom_bar.pack(side="bottom", fill="x", pady=(6, 0))
        self.bottom_bar.columnconfigure(0, weight=1, uniform="btm")  # left half (nav)
        self.bottom_bar.columnconfigure(1, weight=1, uniform="btm")  # right half (buttons)

        # Left side: review navigation (hidden by default, placed via grid when needed)
        self.nav_frame = ctk.CTkFrame(self.bottom_bar, fg_color="transparent")
        # Not placed yet — shown only in Review mode via grid()

        self.prev_btn = ctk.CTkButton(self.nav_frame, text="← Previous",
                                       command=self._prev_record, width=100, height=32,
                                       font=ctk.CTkFont(size=12),
                                       fg_color="transparent", border_width=1,
                                       border_color="#555", hover_color="#333")
        self.prev_btn.pack(side="left", padx=(0, 10))

        # Center: record counter
        self.record_center_frame = ctk.CTkFrame(self.nav_frame, fg_color="transparent")
        self.record_center_frame.pack(side="left", expand=True)
        
        self.record_index_entry = ctk.CTkEntry(self.record_center_frame, width=50, height=28,
                                                font=ctk.CTkFont(size=13, weight="bold"), justify="center")
        self.record_index_entry.pack(side="left")
        self.record_index_entry.bind("<Return>", self._jump_to_record)
        
        self.record_total_label = ctk.CTkLabel(self.record_center_frame, text="/ 0",
                                                font=ctk.CTkFont(size=13), text_color="#aaa")
        self.record_total_label.pack(side="left", padx=(4, 0))

        self.next_btn = ctk.CTkButton(self.nav_frame, text="Next →",
                                       command=self._next_record, width=100, height=32,
                                       font=ctk.CTkFont(size=12),
                                       fg_color="#1f6aa5", hover_color="#144870")
        self.next_btn.pack(side="left", padx=(10, 0))

        # Action buttons — always in right column only
        self.action_btn_frame = ctk.CTkFrame(self.bottom_bar, fg_color="transparent")
        self.action_btn_frame.grid(row=0, column=1, sticky="ew", padx=(8, 8), pady=6)

        self.primary_btn = ctk.CTkButton(self.action_btn_frame, text="💾  Save Entry",
                       command=self._save_entry,
                       height=38, font=ctk.CTkFont(size=14, weight="bold"),
                       fg_color="#2ecc71", hover_color="#27ae60",
                       text_color="black")
        self.primary_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.secondary_btn = ctk.CTkButton(self.action_btn_frame, text="🗑  Clear All",
                       command=self._clear_all,
                       height=38, width=130, font=ctk.CTkFont(size=14),
                       fg_color="#444", hover_color="#555",
                       border_width=1, border_color="#666")
        self.secondary_btn.pack(side="left")

        # =====================================================================
        # TWO-COLUMN CONTENT AREA (fills remaining space between stats & bottom)
        # =====================================================================
        self.content_container = ctk.CTkFrame(main, fg_color="transparent")
        self.content_container.pack(fill="both", expand=True, pady=(4, 0))

        # --- LEFT COLUMN: Heading + Text + Images ---
        self.left_col = ctk.CTkFrame(self.content_container, fg_color="transparent")

        # News Heading
        self._section(self.left_col, "News Heading (optional)")
        self.heading_entry = ctk.CTkTextbox(self.left_col, height=55, font=ctk.CTkFont(size=13),
                                            border_width=1, border_color="#555")
        self.heading_entry.pack(fill="x", padx=10, pady=(0, 6))

        # News Text
        self._section(self.left_col, "📝 News Text (required if no image)")
        self.text_box = ctk.CTkTextbox(self.left_col, height=120, font=ctk.CTkFont(size=13),
                                        border_width=1, border_color="#555")
        self.text_box.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        # Image section
        self._section(self.left_col, "🖼️ Images (required if no text)")
        img_btn_frame = ctk.CTkFrame(self.left_col, fg_color="transparent")
        img_btn_frame.pack(fill="x", padx=10, pady=(0, 4))

        ctk.CTkButton(img_btn_frame, text="📁 Browse", command=self._browse_image,
                       width=100, height=26, font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(img_btn_frame, text="📋 Paste", command=self._paste_image,
                       width=100, height=26, font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(img_btn_frame, text="❌ Remove All", command=self._remove_all_images,
                       width=110, height=26, font=ctk.CTkFont(size=12),
                       fg_color="#e74c3c", hover_color="#c0392b").pack(side="left")

        # Drag and drop zone / image preview area
        self.drop_frame = ctk.CTkFrame(self.left_col, height=80, border_width=2,
                                        border_color="#666", fg_color="#1a1a2e")
        self.drop_frame.pack(fill="both", padx=10, pady=(4, 6))

        self.drop_label = ctk.CTkLabel(self.drop_frame,
                                        text="📥 Drag & Drop image(s) here\nor use Browse / Paste buttons above",
                                        font=ctk.CTkFont(size=13), text_color="#888")
        self.drop_label.pack(expand=True, fill="both", pady=15)

        # --- RIGHT COLUMN: Form controls ---
        self.right_col = ctk.CTkFrame(self.content_container, fg_color="#1a1a2e",
                                       corner_radius=10, border_width=1, border_color="#333")

        # Annotator name
        self._section(self.right_col, "Annotator name *")
        self.annotator_entry = ctk.CTkEntry(self.right_col, placeholder_text="Your name", height=32)
        self.annotator_entry.pack(fill="x", padx=12, pady=(0, 8))

        saved_name = load_config()
        if saved_name:
            self.annotator_entry.insert(0, saved_name)

        # News Label (Fake / Real) — toggle-style buttons
        self._section(self.right_col, "News Authenticity *")
        label_frame = ctk.CTkFrame(self.right_col, fg_color="transparent")
        label_frame.pack(fill="x", padx=12, pady=(0, 6))

        self.label_var = ctk.StringVar(value="")

        # Fake toggle button (left half)
        self.fake_toggle_btn = ctk.CTkButton(
            label_frame, text="❌  FAKE",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40, corner_radius=8,
            fg_color="transparent", hover_color="#4a1a1a",
            border_width=2, border_color="#555",
            text_color="#888",
            command=lambda: self._set_label("Fake")
        )
        self.fake_toggle_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

        # Real toggle button (right half)
        self.real_toggle_btn = ctk.CTkButton(
            label_frame, text="✅  REAL",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40, corner_radius=8,
            fg_color="transparent", hover_color="#1a4a1a",
            border_width=2, border_color="#555",
            text_color="#888",
            command=lambda: self._set_label("Real")
        )
        self.real_toggle_btn.pack(side="left", fill="x", expand=True, padx=(4, 0))

        # Multi-category sub-classification (shown only for Fake)
        self.multi_cat_frame = ctk.CTkFrame(self.right_col, fg_color="#222244",
                                             corner_radius=8, border_width=1,
                                             border_color="#444")
        # Initially hidden
        self.multi_cat_var = ctk.StringVar(value="")

        mc_header = ctk.CTkFrame(self.multi_cat_frame, fg_color="transparent")
        mc_header.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(mc_header, text="⚠️ Fake News Type",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#f39c12").pack(side="left", padx=(0, 2))
        ctk.CTkLabel(mc_header, text="*",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#e74c3c").pack(side="left")

        mc_radios = ctk.CTkFrame(self.multi_cat_frame, fg_color="transparent")
        mc_radios.pack(fill="x", padx=10, pady=(0, 8))

        self.radio_misinfo = ctk.CTkRadioButton(
            mc_radios, text="Misinformation", variable=self.multi_cat_var,
            value="Misinformation", font=ctk.CTkFont(size=12),
            fg_color="#e67e22", hover_color="#d35400")
        self.radio_misinfo.pack(side="left", padx=(0, 12))
        
        self.radio_rumor = ctk.CTkRadioButton(
            mc_radios, text="Rumor", variable=self.multi_cat_var,
            value="Rumor", font=ctk.CTkFont(size=12),
            fg_color="#9b59b6", hover_color="#8e44ad")
        self.radio_rumor.pack(side="left", padx=(0, 12))
        
        self.radio_clickbait = ctk.CTkRadioButton(
            mc_radios, text="Clickbait", variable=self.multi_cat_var,
            value="Clickbait", font=ctk.CTkFont(size=12),
            fg_color="#e74c3c", hover_color="#c0392b")
        self.radio_clickbait.pack(side="left")

        # News Category + Source Category (side by side on one row)
        cat_row_header = ctk.CTkFrame(self.right_col, fg_color="transparent")
        cat_row_header.pack(fill="x", padx=10, pady=(10, 3))
        cat_row_header.columnconfigure(0, weight=1, uniform="catcol")
        cat_row_header.columnconfigure(1, weight=1, uniform="catcol")

        # News Category label
        nc_lbl_frame = ctk.CTkFrame(cat_row_header, fg_color="transparent")
        nc_lbl_frame.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(nc_lbl_frame, text="News Category",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        ctk.CTkLabel(nc_lbl_frame, text=" *",
                     font=ctk.CTkFont(size=15, weight="bold"), text_color="#e74c3c").pack(side="left")

        # Source Category label
        sc_lbl_frame = ctk.CTkFrame(cat_row_header, fg_color="transparent")
        sc_lbl_frame.grid(row=0, column=1, sticky="w", padx=(8, 0))
        ctk.CTkLabel(sc_lbl_frame, text="Source Category",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        ctk.CTkLabel(sc_lbl_frame, text=" *",
                     font=ctk.CTkFont(size=15, weight="bold"), text_color="#e74c3c").pack(side="left")

        # Dropdown row
        cat_row = ctk.CTkFrame(self.right_col, fg_color="transparent")
        cat_row.pack(fill="x", padx=12, pady=(0, 8))
        cat_row.columnconfigure(0, weight=1, uniform="catdrop")
        cat_row.columnconfigure(1, weight=1, uniform="catdrop")

        self.category_var = ctk.StringVar(value="")
        self.category_menu = ctk.CTkOptionMenu(cat_row, variable=self.category_var,
                                                values=CATEGORIES, height=32,
                                                dynamic_resizing=False)
        self.category_menu.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.source_cat_var = ctk.StringVar(value="")
        self.source_cat_menu = ctk.CTkOptionMenu(cat_row, variable=self.source_cat_var,
                                                  values=SOURCE_CATEGORIES, height=32,
                                                  dynamic_resizing=False)
        self.source_cat_menu.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # Confidence (full width)
        self._section(self.right_col, "Confidence (%)")
        self.confidence_entry = ctk.CTkEntry(self.right_col, placeholder_text="100", height=32, justify="center")
        self.confidence_entry.pack(fill="x", padx=12, pady=(0, 8))
        self.confidence_entry.insert(0, "100")

        # Source Link (single line)
        self._section(self.right_col, "Source Link")
        self.source_entry = ctk.CTkEntry(self.right_col, placeholder_text="Paste URL or link here", height=32)
        self.source_entry.pack(fill="x", padx=12, pady=(0, 8))

        # Additional Notes (expandable, fills remaining space)
        self._section(self.right_col, "Additional Notes")
        notes_hint = ctk.CTkLabel(self.right_col, text="For annotator use only — e.g., personal notes or remarks outside of classification",
                                   font=ctk.CTkFont(size=10, slant="italic"), text_color="#666")
        notes_hint.pack(fill="x", padx=12, pady=(0, 2))
        self.notes_entry = ctk.CTkTextbox(self.right_col, font=ctk.CTkFont(size=13),
                                           border_width=1, border_color="#555")
        self.notes_entry.pack(fill="both", expand=True, padx=12, pady=(0, 8))


        # =====================================================================
        # RESPONSIVE LAYOUT: Arrange columns based on window width
        # =====================================================================
        self._arrange_columns()
        self.content_container.bind("<Configure>", self._on_content_resize)

        # ----- STATUS BAR (REMOVED) -----
        class DummyLabel:
            def configure(self, *args, **kwargs): pass
        self.status_label = DummyLabel()

    def _section(self, parent, text):
        """Create a bold section heading label in the UI.
        
        Used to visually separate different input areas (Annotator, Label, etc.).
        If the text ends with '*', it displays the '*' in red color.
        """
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=10, pady=(10, 3))
        
        if text.endswith("*"):
            main_text = text[:-1].rstrip()
            lbl = ctk.CTkLabel(frame, text=main_text, font=ctk.CTkFont(size=15, weight="bold"))
            lbl.pack(side="left")
            ast = ctk.CTkLabel(frame, text=" *", font=ctk.CTkFont(size=15, weight="bold"), text_color="#e74c3c")
            ast.pack(side="left")
        else:
            lbl = ctk.CTkLabel(frame, text=text, font=ctk.CTkFont(size=15, weight="bold"))
            lbl.pack(side="left")

    def _inline_label(self, parent, text, width=140):
        """Create a fixed-width frame for inline labels to ensure vertical alignment of inputs."""
        frame = ctk.CTkFrame(parent, width=width, height=36, fg_color="transparent")
        frame.pack_propagate(False)
        frame.pack(side="left", padx=(0, 10))
        
        if text.endswith("*"):
            main_text = text[:-1].rstrip()
            ctk.CTkLabel(frame, text=main_text, font=ctk.CTkFont(size=13)).pack(side="left")
            ctk.CTkLabel(frame, text=" *", font=ctk.CTkFont(size=13, weight="bold"), text_color="#e74c3c").pack(side="left")
        else:
            ctk.CTkLabel(frame, text=text, font=ctk.CTkFont(size=13)).pack(side="left")

    # =========================================================================
    # TWO-COLUMN LAYOUT
    # =========================================================================

    def _arrange_columns(self):
        """Arrange the left and right columns in a fixed two-column grid layout."""
        self.content_container.columnconfigure(0, weight=1, uniform="col")
        self.content_container.columnconfigure(1, weight=1, uniform="col")
        self.content_container.rowconfigure(0, weight=1)

        self.left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.right_col.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

    def _on_content_resize(self, event=None):
        """No-op: layout is always two columns."""
        pass

    # =========================================================================
    # LABEL CHANGE HANDLER
    # =========================================================================

    def _set_label(self, value):
        """Set the label value and update toggle button visuals.
        
        Called when the user clicks the FAKE or REAL toggle button.
        Updates the button styling to show which is selected.
        """
        self.label_var.set(value)
        self._update_label_toggles()
        self._on_label_change()

    def _update_label_toggles(self):
        """Update the visual state of the Fake/Real toggle buttons."""
        selected = self.label_var.get()
        if selected == "Fake":
            self.fake_toggle_btn.configure(
                fg_color="#4a1a1a", border_color="#e74c3c",
                text_color="#e74c3c"
            )
            self.real_toggle_btn.configure(
                fg_color="transparent", border_color="#555",
                text_color="#888"
            )
        elif selected == "Real":
            self.real_toggle_btn.configure(
                fg_color="#1a4a1a", border_color="#2ecc71",
                text_color="#2ecc71"
            )
            self.fake_toggle_btn.configure(
                fg_color="transparent", border_color="#555",
                text_color="#888"
            )
        else:
            # Neither selected — reset both
            self.fake_toggle_btn.configure(
                fg_color="transparent", border_color="#555",
                text_color="#888"
            )
            self.real_toggle_btn.configure(
                fg_color="transparent", border_color="#555",
                text_color="#888"
            )

    def _on_label_change(self):
        """Show or hide the multi-category panel based on the selected label.
        
        Called whenever the user clicks a label toggle button (Fake or Real).
        - If "Fake" is selected: the multi-category frame is shown so the
          annotator can pick a fake news sub-type (Misinformation/Rumor/Clickbait).
        - If "Real" is selected: the multi-category frame is hidden and the
          multi_cat_var is cleared (multi_category will be set to "Real" on save).
        """
        if self.label_var.get() == "Fake":
            # Show the multi-category sub-classification panel after the label frame
            self.multi_cat_frame.pack(fill="x", padx=12, pady=(0, 8),
                                       after=self.fake_toggle_btn.master)
        else:
            # Hide the panel and reset the selection
            self.multi_cat_frame.pack_forget()
            self.multi_cat_var.set("")
        self._update_label_toggles()

    # =========================================================================
    # DRAG AND DROP SUPPORT
    # =========================================================================

    def _setup_dnd(self):
        """Attempt to set up drag-and-drop support for the drop zone.
        
        Uses tkinterdnd2 which requires the tkdnd Tcl package.
        If either the Python package or the Tcl extension is unavailable,
        the drop zone shows a fallback message directing users to use
        Browse or Paste instead. This gracefully degrades on systems
        without drag-and-drop support.
        """
        global dnd_available
        if dnd_available:
            try:
                # Register the drop zone frame to accept file drops
                self.drop_frame.drop_target_register(DND_FILES)
                # Bind the drop event to our handler
                self.drop_frame.dnd_bind('<<Drop>>', self._on_drop)
            except Exception as e:
                print(f"[WARNING] Failed to register drop target: {e}")
                self.drop_label.configure(text="Drag & Drop not available\n(Use Browse or Paste instead)")
                dnd_available = False
        else:
            self.drop_label.configure(text="Drag & Drop not available\n(Use Browse or Paste instead)")

    def _on_drop(self, event):
        """Handle files dropped onto the drag-and-drop zone.
        
        Parses the dropped file paths (tkdnd can provide them in different
        formats depending on the OS), filters for valid image extensions,
        and adds each valid image to the image list.
        
        Args:
            event: The tkdnd drop event containing file path data.
        """
        # Get the raw dropped data string
        raw = event.data.strip()
        paths = []
        
        # Use regex to parse paths, supporting spaces in paths wrapped in braces
        import re
        for match in re.finditer(r'\{([^{}]+)\}|(\S+)', raw):
            p = match.group(1) or match.group(2)
            if p:
                paths.append(p.strip())

        # Try to add each dropped file as an image
        added = 0
        for p in paths:
            path = Path(p)
            if path.suffix.lower() in IMAGE_EXTENSIONS:
                self._add_image_from_path(path)
                added += 1
        # If nothing valid was dropped, show a warning
        if added == 0:
            messagebox.showwarning("Invalid File", "Please drop image files only (jpg, png, gif, bmp, webp).")

    # =========================================================================
    # IMAGE OPERATIONS
    # =========================================================================

    def _browse_image(self):
        """Open a file dialog for the user to select one or more image files.
        
        The dialog is filtered to only show image file types defined in
        IMAGE_EXTENSIONS. Multiple selection is enabled so the user can
        pick several images at once for a single entry.
        """
        ftypes = [("Image files", " ".join(f"*{e}" for e in IMAGE_EXTENSIONS))]
        paths = filedialog.askopenfilenames(title="Select Image(s)", filetypes=ftypes)
        for path in paths:
            self._add_image_from_path(Path(path))

    def _paste_image(self):
        """Grab an image from the system clipboard and add it to the image list.
        
        Handles two clipboard scenarios:
        1. A PIL Image object (e.g., from a screenshot tool)
        2. A list of file paths (e.g., copied files from Finder/Explorer)
        
        If no image is found in the clipboard, shows an informational message.
        """
        try:
            img = ImageGrab.grabclipboard()
            if img is None:
                messagebox.showinfo("No Image", "No image found in clipboard.")
                return
            if isinstance(img, list):
                # Clipboard contains file paths (e.g., user copied files)
                added = False
                for f in img:
                    if Path(f).suffix.lower() in IMAGE_EXTENSIONS:
                        self._add_image_from_path(Path(f))
                        added = True
                if not added:
                    messagebox.showinfo("No Image", "No image file found in clipboard.")
                return
            # Clipboard contains a direct PIL Image (e.g., screenshot)
            # Store as (None, pil_image) since there is no file path
            self.image_list.append((None, img))
            self._refresh_previews()
            self.status_label.configure(text="Image pasted from clipboard", text_color="#2ecc71")
        except Exception as e:
            messagebox.showerror("Error", f"Could not paste image: {e}")

    def _add_image_from_path(self, path: Path):
        """Add an image to the image list from a file path.
        
        Validates that the file has an allowed image extension and that
        PIL can actually open it (not a corrupt/fake file). If valid,
        appends (path, None) to the image list and refreshes previews.
        
        Args:
            path: Path object pointing to the image file.
        """
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            messagebox.showwarning("Invalid File", "Please select an image file only.")
            return
        try:
            Image.open(path)  # Validate it is a real, readable image
            self.image_list.append((path, None))
            self._refresh_previews()
            self.status_label.configure(text=f"Image added: {path.name}", text_color="#2ecc71")
        except Exception as e:
            messagebox.showerror("Error", f"Could not open image: {e}")

    def _refresh_previews(self):
        """Rebuild the thumbnail preview grid inside the drop zone box.
        
        When no images are selected, shows the drag-and-drop hint text.
        When images are present, replaces the hint with a thumbnail grid
        showing each image with its filename and a remove button.
        All previews are rendered INSIDE the drop_frame box.
        
        Note: We must keep references to ImageTk.PhotoImage objects in
        self.preview_photos, otherwise Python's garbage collector will
        destroy them and the images will disappear from the UI.
        """
        # Clear everything inside the drop frame
        for widget in self.drop_frame.winfo_children():
            widget.destroy()
        self.preview_photos.clear()

        count = len(self.image_list)

        if count == 0:
            # No images: show the drag-and-drop hint text and set minimum height
            self.drop_frame.configure(height=100)
            self.drop_label = ctk.CTkLabel(self.drop_frame,
                                            text="📥 Drag & Drop image(s) here\nor use Browse / Paste buttons above",
                                            font=ctk.CTkFont(size=14), text_color="#888")
            self.drop_label.pack(expand=True, fill="both", pady=20)
            return

        # Images present: show count label + thumbnail grid inside the box
        # Reset height so the frame expands to fit content
        self.drop_frame.configure(height=0)

        # Count label at the top of the box
        ctk.CTkLabel(self.drop_frame,
                     text=f"{count} image(s) selected",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#2ecc71").pack(pady=(8, 4))

        # Grid container for thumbnails
        grid_frame = ctk.CTkFrame(self.drop_frame, fg_color="transparent")
        grid_frame.pack(fill="x", padx=8, pady=(0, 8))

        # Use small thumbnails (5 columns) for all modes, since clicking them opens the large popup
        thumb_size = (100, 80)
        cols = 5

        # Create a thumbnail card for each image in a grid
        for i, (path, pil_img) in enumerate(self.image_list):
            try:
                # Open or copy the image and create a thumbnail
                if path:
                    img = Image.open(path)
                else:
                    img = pil_img.copy()
                img.thumbnail(thumb_size)
                ctk_photo = ctk.CTkImage(light_image=img, dark_image=img,
                                         size=(img.width, img.height))
                self.preview_photos.append(ctk_photo)  # Keep reference alive

                # Create a card frame for this thumbnail
                frame = ctk.CTkFrame(grid_frame, fg_color="#222240",
                                      corner_radius=6)
                frame.grid(row=i // cols, column=i % cols, padx=4, pady=4)

                # Display the thumbnail image (click to enlarge)
                lbl = ctk.CTkLabel(frame, image=ctk_photo, text="", cursor="hand2")
                lbl.pack(padx=4, pady=(4, 0))
                lbl.bind("<Button-1>", lambda e, idx=i: self._show_image_popup(idx))

                # Show the filename (truncated to 18 chars)
                name = path.name if path else f"clipboard_{i+1}.png"
                ctk.CTkLabel(frame, text=name[:18], font=ctk.CTkFont(size=9),
                             text_color="#aaa").pack(pady=(0, 1))

                # Hint to click for full view (only in review mode)
                if self.current_mode == "review":
                    ctk.CTkLabel(frame, text="🔍 Click to enlarge",
                                 font=ctk.CTkFont(size=9), text_color="#666").pack(pady=(0, 1))

                # Small remove button for this specific image
                # Uses lambda with default arg to capture the current index
                rm_btn = ctk.CTkButton(frame, text="x", width=26, height=20,
                                        font=ctk.CTkFont(size=10),
                                        fg_color="#e74c3c", hover_color="#c0392b",
                                        command=lambda idx=i: self._remove_image(idx))
                rm_btn.pack(pady=(0, 4))
            except Exception:
                # Skip images that fail to load (corrupt files, etc.)
                pass

    def _show_image_popup(self, index):
        """Open a popup window to view the selected image at full size.

        Creates a Toplevel window that displays the image scaled to fit
        the screen while maintaining its aspect ratio.

        Args:
            index: Zero-based index of the image to display.
        """
        if index < 0 or index >= len(self.image_list):
            return

        path, pil_img = self.image_list[index]
        try:
            if path:
                img = Image.open(path)
            else:
                img = pil_img.copy()
        except Exception:
            return

        # Create a dark popup window
        popup = ctk.CTkToplevel(self)
        popup.title("Image Viewer")
        popup.configure(fg_color="#111")
        popup.attributes("-topmost", True)

        # Scale image to fit within 80% of screen dimensions
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        max_w = int(screen_w * 0.8)
        max_h = int(screen_h * 0.8)
        img.thumbnail((max_w, max_h), Image.LANCZOS)

        popup.geometry(f"{img.width + 40}x{img.height + 80}")

        ctk_photo = ctk.CTkImage(light_image=img, dark_image=img,
                                  size=(img.width, img.height))
        # Must keep a reference so the image isn't garbage collected
        popup._photo_ref = ctk_photo

        lbl = ctk.CTkLabel(popup, image=ctk_photo, text="")
        lbl.pack(expand=True, fill="both", padx=10, pady=(10, 5))

        name = path.name if path else f"clipboard_{index+1}.png"
        ctk.CTkLabel(popup, text=name, font=ctk.CTkFont(size=12),
                     text_color="#aaa").pack(pady=(0, 5))

        ctk.CTkButton(popup, text="Close", width=100, height=30,
                      command=popup.destroy).pack(pady=(0, 10))

    def _remove_image(self, index):
        """Remove a single image from the image list by its index.
        
        After removal, refreshes the preview grid to update the display.
        
        Args:
            index: Zero-based index of the image to remove.
        """
        if 0 <= index < len(self.image_list):
            self.image_list.pop(index)
            self._refresh_previews()
            self.status_label.configure(text="Image removed", text_color="#888")

    def _remove_all_images(self):
        """Remove all images from the image list and clear the preview area."""
        self.image_list.clear()
        self._refresh_previews()
        self.status_label.configure(text="All images removed", text_color="#888")

    # =========================================================================
    # SAVE ENTRY TO CSV
    # =========================================================================

    def _save_entry(self):
        """Validate all inputs and save the current entry to the CSV file.
        
        This is the main save workflow:
        1. Read all field values from the UI
        2. Validate required fields (annotator, label, text-or-image)
        3. Show a warning if text is very short (< 10 words)
        4. Generate a UUID for this entry
        5. Copy/save each attached image to the images/ folder with the
           naming convention: {Label}_{count:05d}_{uuid}_{annotator}.{ext}
        6. Append a row to the CSV file with all metadata
        7. Show a success popup and clear the fields for the next entry
        """
        # --- Step 1: Read all current field values ---
        annotator = self.annotator_entry.get().strip()
        label = self.label_var.get()
        heading = self.heading_entry.get("1.0", "end-1c").strip()  # Optional headline
        text = self.text_box.get("1.0", "end-1c").strip()  # Get text without trailing newline
        source = self.source_entry.get().strip()
        source_category = self.source_cat_var.get()  # Required platform/medium
        category = self.category_var.get()
        multi_cat = self.multi_cat_var.get()  # Sub-classification for fake news
        confidence_str = self.confidence_entry.get().strip()
        has_image = len(self.image_list) > 0

        # --- Step 2: Validate required fields ---
        # Collect all validation errors and show them at once
        errors = []
        if not annotator:
            errors.append("Annotator name is required.")
        if not label:
            errors.append("Label (Fake/Real) must be selected.")
        if label == "Fake" and not multi_cat:
            # When the label is Fake, the annotator must select a sub-type
            errors.append("Fake News Type (Misinformation/Rumor/Clickbait) must be selected.")
        if not category:
            errors.append("News Category is required.")
        if not source_category:
            errors.append("Source Category is required.")
        if not text and not has_image:
            errors.append("At least one of Text or Image must be provided.")

        # Validate confidence value
        confidence = 100
        if not confidence_str:
            confidence = 100
        else:
            try:
                confidence = int(confidence_str)
                if not (0 <= confidence <= 100):
                    errors.append("Annotation Confidence must be an integer between 0 and 100.")
            except ValueError:
                errors.append("Annotation Confidence must be a valid integer between 0 and 100.")

        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors))
            return

        # Determine the multi_category value:
        # - For Fake entries: use the annotator's selection (Misinformation/Rumor/Clickbait)
        # - For Real entries: automatically set to "Real"
        if label == "Real":
            multi_cat = "Real"

        # --- Step 3: Warn if text is very short (non-blocking) ---
        # The user can choose to proceed anyway
        if text and len(text.split()) < 10:
            proceed = messagebox.askyesno(
                "Short Text Warning",
                f"The text has only {len(text.split())} word(s). "
                "Are you sure you want to save?"
            )
            if not proceed:
                return

        # --- Step 4: Generate unique ID for this entry ---
        # UUID ensures no collisions when merging datasets from multiple annotators
        entry_id = generate_id()
        # Sanitize annotator name for use in filenames (replace special chars)
        sanitized_annotator = sanitize_name(annotator)
        # List to collect relative paths for all images in this entry
        image_rel_paths = []

        # --- Step 5 & 6: File operations (Images and CSV) ---
        # Wrap in try-except because on Windows, the CSV might be locked by Excel
        try:
            # --- Step 5: Process and save each attached image ---
            if has_image:
                for path, pil_img in self.image_list:
                    # Get the current count of images in the folder (for sequential numbering)
                    img_count = get_image_count() + 1
    
                    # Determine the file extension
                    # For file-based images, use the original extension
                    # For clipboard-pasted images, default to .png
                    if path:
                        ext = path.suffix.lower()
                    else:
                        ext = ".png"
    
                    # Build the image filename following the naming convention:
                    # {Label}_{5-digit-count}_{uuid}_{annotator}.{extension}
                    # Example: Fake_00042_550e8400-e29b-41d4-a716-446655440000_Faysal.jpg
                    img_filename = f"{label}_{img_count:05d}_{entry_id}_{sanitized_annotator}{ext}"
                    img_dest = IMAGES_DIR / img_filename
    
                    # Save the image to the images/ directory
                    if path:
                        # File-based image: copy the original file preserving metadata
                        shutil.copy2(path, img_dest)
                    else:
                        # Clipboard image: save the PIL Image object
                        src_img = pil_img
                        # Convert RGBA to RGB if saving as JPEG (JPEG doesnt support alpha)
                        if src_img.mode == "RGBA" and ext in (".jpg", ".jpeg"):
                            src_img = src_img.convert("RGB")
                        src_img.save(img_dest)
    
                    # Store the RELATIVE path (not absolute) for the CSV
                    # This makes the dataset portable across different machines
                    image_rel_paths.append(f"images/{img_filename}")
    
            # Join multiple image paths with semicolons for the CSV column
            # Example: "images/Fake_00001_uuid_Faysal.jpg;images/Fake_00002_uuid_Faysal.png"
            image_path_str = ";".join(image_rel_paths)
    
            # --- Step 6: Append the entry as a new row in the CSV ---
            file_has_content = CSV_PATH.exists() and CSV_PATH.stat().st_size > 0
            with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
                # Write the header row only if this is a brand new or empty CSV file
                if not file_has_content:
                    writer.writeheader()
                # Write the data row with all collected fields
                writer.writerow({
                    "id": entry_id,
                    "heading": heading,
                    "text": text,
                    "image_path": image_path_str,
                    "label": label,
                    "multi_category": multi_cat,
                    "source": source,
                    "source_category": source_category,
                    "category": category,
                    "annotator": annotator,
                    "annotation_confidence": confidence,
                    "additional_notes": self.notes_entry.get("0.0", "end-1c").strip(),
                    "timestamp": datetime.now().isoformat(),
                })
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save data. Please make sure the dataset CSV file is not open in Excel or another program.\n\nError: {e}")
            return

        # Persist the annotator name for future sessions
        save_config(annotator)

        # --- Step 7: Show success feedback and reset for next entry ---
        self.status_label.configure(
            text=f"Entry saved successfully!", text_color="#2ecc71"
        )
        # Refresh the stats bar to show updated counts
        self._update_stats()
        # Clear all input fields (except annotator name) for the next entry
        self._clear_fields()
        # Show a confirmation popup so the user knows the save completed
        messagebox.showinfo("Save Complete", f"Entry saved successfully!\nID: {entry_id}")

    # =========================================================================
    # CLEAR FIELDS AND UPDATE STATS
    # =========================================================================

    def _clear_fields(self):
        """Clear all input fields EXCEPT the annotator name.
        
        Called after each successful save to prepare for the next entry.
        Also called by _clear_all. Resets: text, heading, source, label,
        category, multi-category, and all attached images.
        """
        self.text_box.delete("1.0", "end")       # Clear the text area
        self.heading_entry.delete("1.0", "end")       # Clear the heading field
        self.source_entry.delete(0, "end")         # Clear the source field
        self.notes_entry.delete("0.0", "end")      # Clear additional notes
        self.label_var.set("")                      # Deselect the label radio buttons
        self._update_label_toggles()                 # Reset Fake/Real button visuals
        self.category_var.set("")                   # Reset category dropdown
        self.source_cat_var.set("")                  # Reset source category dropdown
        self.multi_cat_var.set("")                   # Reset multi-category selection
        self.multi_cat_frame.pack_forget()           # Hide multi-category panel
        self._remove_all_images()                   # Clear all attached images
        self.confidence_entry.delete(0, "end")      # Clear confidence field
        self.confidence_entry.insert(0, "100")      # Reset default value to 100

    def _clear_all(self):
        """Clear all fields except the annotator name.
        
        Triggered by the 'Clear All' button. The annotator name is
        intentionally preserved because the same person typically
        annotates many entries in a single session.
        """
        self._clear_fields()
        self.status_label.configure(text="All fields cleared", text_color="#888")

    def _has_unsaved_annotate_work(self):
        """Check if there is any unsaved work in Annotate mode."""
        if self.current_mode != "annotate":
            return False
        
        if self.label_var.get(): return True
        if self.heading_entry.get("1.0", "end-1c").strip(): return True
        if self.text_box.get("1.0", "end-1c").strip(): return True
        if self.source_entry.get().strip(): return True
        if self.source_cat_var.get(): return True
        if self.category_var.get(): return True
        if self.multi_cat_var.get(): return True
        if len(self.image_list) > 0: return True
        
        return False

    def _on_closing(self):
        """Handle the window close event to prevent accidental data loss."""
        if self.current_mode == "review":
            if not self._check_unsaved_changes():
                return
        elif self.current_mode == "annotate":
            if self._has_unsaved_annotate_work():
                confirm = messagebox.askyesno(
                    "Unsaved Work",
                    "You have unsaved annotation work. Are you sure you want to exit without saving?"
                )
                if not confirm:
                    return
        self.destroy()

    def _apply_advanced_filter(self, keep_index=False):
        """Filter the dataset based on the advanced filter settings."""
        if self.current_mode != "review":
            return

        filt = self.advanced_filter

        if not filt:
            # No filter active — show everything
            self.dataset_records = list(self.all_dataset_records)
        else:
            filtered = list(self.all_dataset_records)

            # Filter by label
            sel_labels = filt.get("labels")
            if sel_labels:
                filtered = [r for r in filtered if (r.get("label") or "") in sel_labels]

            # Filter by fake news type (multi_category)
            sel_types = filt.get("types")
            if sel_types:
                filtered = [r for r in filtered if (r.get("multi_category") or "") in sel_types]

            # Filter by news category
            sel_cats = filt.get("categories")
            if sel_cats:
                filtered = [r for r in filtered if (r.get("category") or "") in sel_cats]

            # Filter by source category
            sel_src_cats = filt.get("source_categories")
            if sel_src_cats:
                filtered = [r for r in filtered if (r.get("source_category") or "") in sel_src_cats]

            # Filter by annotator
            sel_annotators = filt.get("annotators")
            if sel_annotators:
                filtered = [r for r in filtered if (r.get("annotator") or "") in sel_annotators]

            # Filter by content type (Image Only / Text & Image / Text Only)
            sel_content_types = filt.get("content_types")
            if sel_content_types:
                def _content_type(r):
                    has_text = bool((r.get("text") or "").strip())
                    has_image = bool((r.get("image_path") or "").strip())
                    if has_text and has_image:
                        return "Text & Image"
                    elif has_image:
                        return "Image Only"
                    elif has_text:
                        return "Text Only"
                    return ""
                filtered = [r for r in filtered if _content_type(r) in sel_content_types]

            # Filter by confidence interval
            min_conf = filt.get("min_conf")
            max_conf = filt.get("max_conf")
            if min_conf is not None or max_conf is not None:
                lo = min_conf if min_conf is not None else 0
                hi = max_conf if max_conf is not None else 100
                def _conf_in_range(r):
                    try:
                        c = int(r.get("annotation_confidence") or "100")
                    except ValueError:
                        c = 100
                    return lo <= c <= hi
                filtered = [r for r in filtered if _conf_in_range(r)]

            self.dataset_records = filtered

        if not keep_index:
            self.current_review_index = 0
        elif self.current_review_index >= len(self.dataset_records):
            self.current_review_index = max(0, len(self.dataset_records) - 1)

        self._update_stats()
        self._update_filter_indicator()

        # In Review mode, always attempt to display the current record
        if self.dataset_records:
            self.record_index_entry.configure(state="normal")
            self._display_record(self.current_review_index)
        else:
            self._clear_fields()
            self.record_index_entry.configure(state="normal")
            self.record_index_entry.delete(0, "end")
            self.record_index_entry.insert(0, "0")
            self.record_index_entry.configure(state="disabled")
            self.record_total_label.configure(text="of 0")
            self.prev_btn.configure(state="disabled")
            self.next_btn.configure(state="disabled")

    def _update_filter_indicator(self):
        """Update the filter indicator label next to the filter button."""
        if self.advanced_filter:
            count = 0
            f = self.advanced_filter
            if f.get("labels"): count += 1
            if f.get("types"): count += 1
            if f.get("categories"): count += 1
            if f.get("source_categories"): count += 1
            if f.get("annotators"): count += 1
            if f.get("content_types"): count += 1
            if f.get("min_conf") is not None or f.get("max_conf") is not None: count += 1
            self.filter_indicator.configure(text=f"⚡ {count} filter(s)")
            self.filter_btn.configure(fg_color="#4a3f00", border_color="#f39c12")
        else:
            self.filter_indicator.configure(text="")
            self.filter_btn.configure(fg_color="#2d2d5e", border_color="#555")

    def _collect_unique_values(self, field):
        """Collect all unique non-empty values for a given field from all records."""
        values = set()
        for r in self.all_dataset_records:
            v = (r.get(field) or "").strip()
            if v:
                values.add(v)
        return sorted(values)

    def _show_filter_popup(self):
        """Open a filter settings popup with checkboxes and confidence range."""
        popup = ctk.CTkToplevel(self)
        popup.title("Filter Records")
        popup.configure(fg_color="#1a1a2e")
        popup.attributes("-topmost", True)
        popup.resizable(True, True)

        # Size and center the popup
        pw, ph = 600, 580
        popup.geometry(f"{pw}x{ph}")
        popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (pw // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (ph // 2)
        popup.geometry(f"+{x}+{y}")

        # Title
        ctk.CTkLabel(popup, text="🔽 Filter Settings",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(12, 6))

        # Scrollable content area
        scroll = ctk.CTkScrollableFrame(popup, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        # Pre-populate from current filter
        cur = self.advanced_filter or {}

        # ── Helper to build a checkbox section ──
        def _checkbox_section(parent, title, options, pre_selected):
            """Build a section with a title and checkboxes; returns list of (value, BooleanVar) tuples."""
            frame = ctk.CTkFrame(parent, fg_color="#222244", corner_radius=8,
                                  border_width=1, border_color="#444")
            frame.pack(fill="x", pady=(6, 2))

            ctk.CTkLabel(frame, text=title,
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color="#ccc").pack(anchor="w", padx=10, pady=(6, 2))

            vars_list = []
            row_frame = ctk.CTkFrame(frame, fg_color="transparent")
            row_frame.pack(fill="x", padx=10, pady=(0, 6))

            for i, opt in enumerate(options):
                var = ctk.BooleanVar(value=(opt in pre_selected) if pre_selected else False)
                cb = ctk.CTkCheckBox(row_frame, text=opt, variable=var,
                                      font=ctk.CTkFont(size=12),
                                      height=24, checkbox_width=18, checkbox_height=18)
                cb.grid(row=i // 4, column=i % 4, sticky="w", padx=(0, 12), pady=2)
                vars_list.append((opt, var))
            return vars_list

        # ── 1. Label (Fake / Real) ──
        label_vars = _checkbox_section(scroll, "Label",
                                       ["Fake", "Real"],
                                       cur.get("labels", set()))

        # ── 2. Fake News Type ──
        type_vars = _checkbox_section(scroll, "Fake News Type",
                                      MULTI_CATEGORIES,
                                      cur.get("types", set()))

        # ── 3. News Category ──
        all_categories = self._collect_unique_values("category")
        cat_vars = _checkbox_section(scroll, "News Category",
                                     all_categories if all_categories else ["(no data)"],
                                     cur.get("categories", set()))

        # ── 4. Source Category ──
        all_src_cats = self._collect_unique_values("source_category")
        src_cat_vars = _checkbox_section(scroll, "Source Category",
                                         all_src_cats if all_src_cats else ["(no data)"],
                                         cur.get("source_categories", set()))

        # ── 5. Annotator ──
        all_annotators = self._collect_unique_values("annotator")
        ann_vars = _checkbox_section(scroll, "Annotator",
                                     all_annotators if all_annotators else ["(no data)"],
                                     cur.get("annotators", set()))

        # ── 6. Content Type ──
        content_type_vars = _checkbox_section(scroll, "Content Type",
                                              ["Image Only", "Text & Image", "Text Only"],
                                              cur.get("content_types", set()))

        # ── 7. Confidence Interval ──
        conf_frame = ctk.CTkFrame(scroll, fg_color="#222244", corner_radius=8,
                                   border_width=1, border_color="#444")
        conf_frame.pack(fill="x", pady=(6, 2))

        ctk.CTkLabel(conf_frame, text="Confidence Interval",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#ccc").pack(anchor="w", padx=10, pady=(6, 2))

        conf_row = ctk.CTkFrame(conf_frame, fg_color="transparent")
        conf_row.pack(fill="x", padx=10, pady=(0, 8))

        ctk.CTkLabel(conf_row, text="Min:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        min_conf_entry = ctk.CTkEntry(conf_row, width=60, height=26,
                                       font=ctk.CTkFont(size=12), justify="center")
        min_conf_entry.pack(side="left", padx=(0, 16))
        min_conf_entry.insert(0, str(cur.get("min_conf", 0)))

        ctk.CTkLabel(conf_row, text="Max:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        max_conf_entry = ctk.CTkEntry(conf_row, width=60, height=26,
                                       font=ctk.CTkFont(size=12), justify="center")
        max_conf_entry.pack(side="left")
        max_conf_entry.insert(0, str(cur.get("max_conf", 100)))

        # ── Buttons ──
        btn_container = ctk.CTkFrame(popup, fg_color="transparent")
        btn_container.pack(fill="x", padx=12, pady=(4, 12))

        # Collect all checkbox var lists for the clear-all function
        all_checkbox_vars = label_vars + type_vars + cat_vars + src_cat_vars + ann_vars + content_type_vars

        def _clear_selections():
            """Uncheck every checkbox and reset confidence to 0–100 without closing."""
            for _, var in all_checkbox_vars:
                var.set(False)
            min_conf_entry.delete(0, "end")
            min_conf_entry.insert(0, "0")
            max_conf_entry.delete(0, "end")
            max_conf_entry.insert(0, "100")

        def _apply():
            # Collect selected values
            sel_labels = {v for v, var in label_vars if var.get()}
            sel_types = {v for v, var in type_vars if var.get()}
            sel_cats = {v for v, var in cat_vars if var.get() and v != "(no data)"}
            sel_src_cats = {v for v, var in src_cat_vars if var.get() and v != "(no data)"}
            sel_annotators = {v for v, var in ann_vars if var.get() and v != "(no data)"}
            sel_content_types = {v for v, var in content_type_vars if var.get()}

            # Parse confidence
            try:
                mn = int(min_conf_entry.get().strip())
            except ValueError:
                mn = 0
            try:
                mx = int(max_conf_entry.get().strip())
            except ValueError:
                mx = 100
            mn = max(0, min(100, mn))
            mx = max(0, min(100, mx))
            if mn > mx:
                mn, mx = mx, mn

            # Check if any filter is actually active
            has_filter = (
                bool(sel_labels) or bool(sel_types) or bool(sel_cats) or
                bool(sel_src_cats) or bool(sel_annotators) or bool(sel_content_types) or
                mn > 0 or mx < 100
            )

            if has_filter:
                self.advanced_filter = {
                    "labels": sel_labels if sel_labels else None,
                    "types": sel_types if sel_types else None,
                    "categories": sel_cats if sel_cats else None,
                    "source_categories": sel_src_cats if sel_src_cats else None,
                    "annotators": sel_annotators if sel_annotators else None,
                    "content_types": sel_content_types if sel_content_types else None,
                    "min_conf": mn if mn > 0 else None,
                    "max_conf": mx if mx < 100 else None,
                }
            else:
                self.advanced_filter = None

            self._apply_advanced_filter()
            popup.destroy()

        def _clear_and_apply():
            self.advanced_filter = None
            self._apply_advanced_filter()
            popup.destroy()

        # Row 1: Apply + Clear All Selections
        row1 = ctk.CTkFrame(btn_container, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 6))

        ctk.CTkButton(row1, text="✅ Apply Filter", command=_apply,
                       height=36, font=ctk.CTkFont(size=14, weight="bold"),
                       fg_color="#2ecc71", hover_color="#27ae60",
                       text_color="black").pack(side="left", expand=True, fill="x", padx=(0, 6))

        ctk.CTkButton(row1, text="↺ Clear All", command=_clear_selections,
                       height=36, font=ctk.CTkFont(size=13),
                       fg_color="#555", hover_color="#777",
                       width=130).pack(side="left")

        # Row 2: Clear Filter + Cancel
        row2 = ctk.CTkFrame(btn_container, fg_color="transparent")
        row2.pack(fill="x")

        ctk.CTkButton(row2, text="🗑️ Clear Filter", command=_clear_and_apply,
                       height=36, font=ctk.CTkFont(size=13, weight="bold"),
                       fg_color="#e74c3c", hover_color="#c0392b").pack(side="left", expand=True, fill="x", padx=(0, 6))

        ctk.CTkButton(row2, text="Cancel", command=popup.destroy,
                       height=36, font=ctk.CTkFont(size=13),
                       fg_color="transparent", border_width=1,
                       border_color="#555", width=130).pack(side="left")

    def _create_stat_badge(self, parent, label, count, dot_color="#888"):
        """Create a colored badge card for the stats bar.
        
        Each badge shows a colored dot, a bold count number, and a label.
        """
        badge = ctk.CTkFrame(parent, fg_color="#1e1e3a", corner_radius=8,
                              border_width=1, border_color="#333")
        
        inner = ctk.CTkFrame(badge, fg_color="transparent")
        inner.pack(padx=10, pady=6)
        
        # Colored dot
        dot = ctk.CTkFrame(inner, width=10, height=10, corner_radius=5,
                            fg_color=dot_color)
        dot.pack(side="left", padx=(0, 6))
        dot.pack_propagate(False)
        
        # Count number (bold)
        ctk.CTkLabel(inner, text=str(count),
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ffffff").pack(side="left", padx=(0, 6))
        
        # Label text (smaller)
        ctk.CTkLabel(inner, text=label,
                     font=ctk.CTkFont(size=11),
                     text_color="#aaa").pack(side="left")

    def _create_stat_label(self, parent, text, filter_key=None, is_separator=False):
        """Helper to create stat labels inside a frame (display only, no click filtering)."""
        if is_separator:
            lbl = ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=13))
            return

        color = "#ffffff" if ctk.get_appearance_mode() == "Dark" else "#000000"
        fnt = ctk.CTkFont(size=13)
        lbl = ctk.CTkLabel(parent, text=text, font=fnt, text_color=color)

    def _update_stats(self):
        """Refresh the stats bar at the top of the UI with colored badge cards.
        
        In Review mode with a filter active, shows counts from the filtered
        subset. Otherwise shows global counts from the CSV.
        Called after each save and at startup.
        """
        # Determine if we should show filtered counts
        use_filtered = (self.current_mode == "review" and self.advanced_filter
                        and hasattr(self, 'dataset_records'))

        if use_filtered:
            # Compute counts from the filtered records
            records = self.dataset_records
            total = len(records)
            fake = sum(1 for r in records if (r.get("label") or "") == "Fake")
            real = sum(1 for r in records if (r.get("label") or "") == "Real")
            sub = {"Misinformation": 0, "Rumor": 0, "Clickbait": 0}
            news_cats = {}
            img_count = 0
            only_image = 0
            only_text = 0
            both_text_image = 0
            for r in records:
                mc = (r.get("multi_category") or "").strip()
                if mc in sub:
                    sub[mc] += 1
                cat = (r.get("category") or "").strip()
                if cat:
                    news_cats[cat] = news_cats.get(cat, 0) + 1
                ip = (r.get("image_path") or "").strip()
                img_list = [p for p in ip.split(";") if p.strip()]
                if ip:
                    img_count += len(img_list)
                
                # Content breakdown
                has_text = bool((r.get("text") or "").strip())
                has_image = bool(img_list)
                if has_text and has_image:
                    both_text_image += 1
                elif has_text and not has_image:
                    only_text += 1
                elif not has_text and has_image:
                    only_image += 1
            global_total = len(self.all_dataset_records)
        else:
            counts = get_label_counts()
            img_count = get_image_count()
            total = counts["total"]
            fake = counts["fake"]
            real = counts["real"]
            sub = counts["fake_subcategories"]
            news_cats = counts["news_categories"]
            only_image = counts["only_image"]
            only_text = counts["only_text"]
            both_text_image = counts["both_text_image"]
            global_total = None

        # Clear existing widgets
        for widget in self.stats_frame.winfo_children():
            widget.destroy()
        for widget in self.category_stats_frame.winfo_children():
            widget.destroy()

        # Badge cards — each stat gets a colored badge
        # Total entries
        if use_filtered:
            self._create_stat_badge(self.stats_frame, f"Filtered / {global_total}", total, "#3498db")
        else:
            self._create_stat_badge(self.stats_frame, "Total", total, "#3498db")
        
        # Label counts (skip zeros when filtered)
        if not use_filtered or fake > 0:
            self._create_stat_badge(self.stats_frame, "Fake", fake, "#e74c3c")
        if not use_filtered or real > 0:
            self._create_stat_badge(self.stats_frame, "Real", real, "#2ecc71")
        
        # Subcategory counts
        if not use_filtered or sub["Misinformation"] > 0:
            self._create_stat_badge(self.stats_frame, "Misinfo", sub["Misinformation"], "#e67e22")
        if not use_filtered or sub["Rumor"] > 0:
            self._create_stat_badge(self.stats_frame, "Rumor", sub["Rumor"], "#9b59b6")
        if not use_filtered or sub["Clickbait"] > 0:
            self._create_stat_badge(self.stats_frame, "Clickbait", sub["Clickbait"], "#f39c12")
        
        # Content breakdown
        self._create_stat_badge(self.stats_frame, "Images", img_count, "#1abc9c")
        if not use_filtered or only_text > 0:
            self._create_stat_badge(self.stats_frame, "Text Only", only_text, "#34495e")
        if not use_filtered or both_text_image > 0:
            self._create_stat_badge(self.stats_frame, "Text & Img", both_text_image, "#16a085")
        if not use_filtered or only_image > 0:
            self._create_stat_badge(self.stats_frame, "Img Only", only_image, "#2c3e50")

        # Category stats line
        if news_cats:
            lbl = ctk.CTkLabel(self.category_stats_frame, text="News Categories  ▸  ", font=ctk.CTkFont(size=12), text_color="#aaa")
            
            sorted_cats = sorted(news_cats.items())
            for i, (cat, count) in enumerate(sorted_cats):
                self._create_stat_label(self.category_stats_frame, f"{cat}: {count}", filter_key=cat)
                if i < len(sorted_cats) - 1:
                    self._create_stat_label(self.category_stats_frame, "|", is_separator=True)
        else:
            lbl = ctk.CTkLabel(self.category_stats_frame, text="News Categories  ▸  No entries yet", font=ctk.CTkFont(size=12), text_color="#aaa")

        # Explicitly trigger layout arrangement
        self.stats_frame.update_idletasks()
        self.category_stats_frame.update_idletasks()
        self.stats_frame._arrange()
        self.category_stats_frame._arrange()


    # =========================================================================
    # REVIEW MODE
    # =========================================================================

    def _toggle_mode(self, mode_name):
        """Switch between Annotate and Review modes.

        When switching to Review: saves the current annotation as a draft,
        loads the CSV, and displays the first record.
        When switching to Annotate: restores the saved draft.
        """
        if "Annotate" in mode_name:
            if self.current_mode == "annotate":
                return
            if not self._check_unsaved_changes():
                self.mode_switcher.set("🔍 Review")
                return
            self.current_mode = "annotate"
            self.nav_frame.grid_forget()
            self.filter_btn.pack_forget()
            self.filter_indicator.pack_forget()
            # Swap buttons to Annotate mode
            self.primary_btn.configure(text="💾  Save Entry", command=self._save_entry)
            self.secondary_btn.configure(text="🗑  Clear All", command=self._clear_all,
                                          fg_color="#444", hover_color="#555")
            self._restore_draft()
            self._update_stats()
        elif "Review" in mode_name:
            if self.current_mode == "review":
                return
            self._save_draft()
            self.current_mode = "review"
            self._load_dataset()
            if not self.all_dataset_records:
                messagebox.showinfo("No Data",
                    "No entries found in dataset.csv.\nAnnotate some entries first!")
                self.mode_switcher.set("📝 Annotate")
                self.current_mode = "annotate"
                self._restore_draft()
                self._update_stats()
                return
            # Swap buttons to Review mode
            self.primary_btn.configure(text="💾  Update Entry", command=self._update_entry)
            self.secondary_btn.configure(text="🗑  Delete", command=self._delete_entry,
                                          fg_color="#e74c3c", hover_color="#c0392b")
            self.nav_frame.grid(row=0, column=0, sticky="ew", padx=(8, 8), pady=6)
            self.filter_btn.pack(side="right", padx=(4, 0))
            self.filter_indicator.pack(side="right", padx=(4, 0))
            self._update_filter_indicator()

    def _load_dataset(self):
        """Load all records from the dataset CSV into memory for review."""
        self.all_dataset_records = []
        if not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0:
            self.dataset_records = []
            return
        with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.all_dataset_records.append(row)
                
        self._apply_advanced_filter()

    def _display_record(self, index):
        """Populate all UI fields with data from the record at the given index.

        Loads text fields, dropdowns, label selection, confidence, and
        any images referenced in the record's image_path column.
        """
        if not self.dataset_records or index < 0 or index >= len(self.dataset_records):
            return

        record = self.dataset_records[index]

        # Update the navigation counter and button states
        total = len(self.dataset_records)
        self.record_index_entry.configure(state="normal")
        self.record_index_entry.delete(0, "end")
        self.record_index_entry.insert(0, str(index + 1))
        self.record_total_label.configure(text=f"of {total}")
        self.prev_btn.configure(state="normal" if index > 0 else "disabled")
        self.next_btn.configure(state="normal" if index < total - 1 else "disabled")

        # Clear all fields before populating
        self._clear_fields()

        # Populate each field from the record
        self.annotator_entry.delete(0, "end")
        self.annotator_entry.insert(0, record.get("annotator") or "")

        label = record.get("label") or ""
        if label:
            self.label_var.set(label)
            self._on_label_change()

        multi_cat = record.get("multi_category") or ""
        if label == "Fake" and multi_cat in MULTI_CATEGORIES:
            self.multi_cat_var.set(multi_cat)

        self.category_var.set(record.get("category") or "")
        self.source_cat_var.set(record.get("source_category") or "")

        self.source_entry.delete(0, "end")
        self.source_entry.insert(0, record.get("source") or "")

        # Additional notes
        self.notes_entry.delete("0.0", "end")
        notes = record.get("additional_notes") or ""
        if notes:
            self.notes_entry.insert("0.0", notes)

        self.heading_entry.delete("1.0", "end")
        heading = record.get("heading") or ""
        if heading:
            self.heading_entry.insert("1.0", heading)

        self.text_box.delete("1.0", "end")
        text = record.get("text") or ""
        if text:
            self.text_box.insert("1.0", text)

        self.confidence_entry.delete(0, "end")
        self.confidence_entry.insert(0, record.get("annotation_confidence") or "100")

        # Load images referenced in the record
        self.image_list.clear()
        image_paths = record.get("image_path") or ""
        if image_paths:
            for rel_path in image_paths.split(";"):
                rel_path = rel_path.strip()
                if rel_path:
                    full_path = SCRIPT_DIR / rel_path
                    if full_path.exists():
                        self.image_list.append((full_path, None))
        self._refresh_previews()

    def _check_unsaved_changes(self):
        """Check if current review record has unsaved edits before navigating.
        
        Returns:
            True if safe to navigate (no changes, or user chose to discard/save).
            False if navigation should be aborted (Cancel or save failed).
        """
        if not self.dataset_records or self.current_review_index < 0:
            return True
            
        record = self.dataset_records[self.current_review_index]
        
        annotator = self.annotator_entry.get().strip()
        label = self.label_var.get()
        heading = self.heading_entry.get("1.0", "end-1c").strip()
        text = self.text_box.get("1.0", "end-1c").strip()
        source = self.source_entry.get().strip()
        source_category = self.source_cat_var.get()
        category = self.category_var.get()
        multi_cat = self.multi_cat_var.get() if label == "Fake" else ("Real" if label == "Real" else "")
        confidence = self.confidence_entry.get().strip()
        
        changed = False
        if annotator != (record.get("annotator") or ""): changed = True
        elif label != (record.get("label") or ""): changed = True
        elif heading != (record.get("heading") or ""): changed = True
        elif text != (record.get("text") or ""): changed = True
        elif source != (record.get("source") or ""): changed = True
        elif source_category != (record.get("source_category") or ""): changed = True
        elif category != (record.get("category") or ""): changed = True
        elif multi_cat != (record.get("multi_category") or ""): changed = True
        elif confidence != (record.get("annotation_confidence") or "100"): changed = True
        
        if not changed:
            orig_images = [p.strip().replace("\\", "/") for p in (record.get("image_path") or "").split(";") if p.strip()]
            if len(self.image_list) != len(orig_images):
                changed = True
            else:
                for (path, pil_img), orig_rel_path in zip(self.image_list, orig_images):
                    if path is None:
                        changed = True
                        break
                    try:
                        rel = path.relative_to(SCRIPT_DIR)
                        if str(rel).replace("\\", "/") != orig_rel_path:
                            changed = True
                            break
                    except ValueError:
                        changed = True
                        break
                
        if not changed:
            return True
            
        response = messagebox.askyesnocancel(
            "Unsaved Changes",
            "You have unsaved changes in this record.\n\n"
            "Do you want to save them before moving?"
        )
        
        if response is True:  # Yes — try to save
            save_ok = self._update_entry(show_success=False)
            if not save_ok:
                # Save failed (validation error). Give the user a second
                # chance to discard instead of trapping them.
                discard = messagebox.askyesno(
                    "Save Failed",
                    "Could not save due to validation errors.\n\n"
                    "Do you want to discard your changes and continue?"
                )
                return discard  # True = discard & continue, False = stay
            return True
        elif response is False:  # No — discard changes
            return True
        else:  # Cancel
            return False

    def _next_record(self):
        """Navigate to the next record in the dataset."""
        if self.current_review_index < len(self.dataset_records) - 1:
            if not self._check_unsaved_changes():
                return
            self.current_review_index += 1
            self._display_record(self.current_review_index)

    def _prev_record(self):
        """Navigate to the previous record in the dataset."""
        if self.current_review_index > 0:
            if not self._check_unsaved_changes():
                return
            self.current_review_index -= 1
            self._display_record(self.current_review_index)

    def _jump_to_record(self, event=None):
        """Jump to the record index typed in the entry field."""
        try:
            val = int(self.record_index_entry.get().strip())
            # Convert to 0-based index
            idx = val - 1
            if 0 <= idx < len(self.dataset_records):
                if self.current_review_index != idx:
                    if not self._check_unsaved_changes():
                        # Reset to current valid index
                        self.record_index_entry.delete(0, "end")
                        self.record_index_entry.insert(0, str(self.current_review_index + 1))
                        self.focus_set()
                        return
                    self.current_review_index = idx
                    self._display_record(self.current_review_index)
                # Unfocus the entry widget so we don't accidentally keep typing
                self.focus_set()
            else:
                # Reset to current valid index
                self.record_index_entry.delete(0, "end")
                self.record_index_entry.insert(0, str(self.current_review_index + 1))
                messagebox.showwarning("Invalid Record", f"Please enter a number between 1 and {len(self.dataset_records)}.")
        except ValueError:
            # Reset if not a valid number
            self.record_index_entry.delete(0, "end")
            self.record_index_entry.insert(0, str(self.current_review_index + 1))

    def _update_entry(self, show_success=True):
        """Validate fields and save changes to the currently displayed record.

        Re-validates all required fields, processes any new images,
        updates the in-memory record, and rewrites the CSV file.
        """
        if not self.dataset_records:
            return False

        annotator = self.annotator_entry.get().strip()
        label = self.label_var.get()
        heading = self.heading_entry.get("1.0", "end-1c").strip()
        text = self.text_box.get("1.0", "end-1c").strip()
        source = self.source_entry.get().strip()
        source_category = self.source_cat_var.get()
        category = self.category_var.get()
        multi_cat = self.multi_cat_var.get()
        confidence_str = self.confidence_entry.get().strip()
        has_image = len(self.image_list) > 0

        # Validate required fields
        errors = []
        if not annotator:
            errors.append("Annotator name is required.")
        if not label:
            errors.append("Label (Fake/Real) must be selected.")
        if label == "Fake" and not multi_cat:
            errors.append("Fake News Type must be selected.")
        if not category:
            errors.append("News Category is required.")
        if not source_category:
            errors.append("Source Category is required.")
        if not text and not has_image:
            errors.append("At least one of Text or Image must be provided.")

        confidence = 100
        if confidence_str:
            try:
                confidence = int(confidence_str)
                if not (0 <= confidence <= 100):
                    errors.append("Annotation Confidence must be between 0 and 100.")
            except ValueError:
                errors.append("Annotation Confidence must be a valid integer.")

        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors))
            return False

        if label == "Real":
            multi_cat = "Real"

        record = self.dataset_records[self.current_review_index]
        entry_id = record.get("id") or generate_id()
        sanitized_annotator = sanitize_name(annotator)

        # Process images: keep existing project images, copy new external ones
        try:
            image_rel_paths = []
            for path, pil_img in self.image_list:
                if path:
                    try:
                        rel = path.relative_to(SCRIPT_DIR)
                        image_rel_paths.append(str(rel).replace("\\", "/"))
                    except ValueError:
                        img_count = get_image_count() + 1
                        ext = path.suffix.lower()
                        img_filename = f"{label}_{img_count:05d}_{entry_id}_{sanitized_annotator}{ext}"
                        img_dest = IMAGES_DIR / img_filename
                        shutil.copy2(path, img_dest)
                        image_rel_paths.append(f"images/{img_filename}")
                else:
                    img_count = get_image_count() + 1
                    img_filename = f"{label}_{img_count:05d}_{entry_id}_{sanitized_annotator}.png"
                    img_dest = IMAGES_DIR / img_filename
                    src_img = pil_img
                    if src_img.mode == "RGBA":
                        src_img = src_img.convert("RGB")
                    src_img.save(img_dest)
                    image_rel_paths.append(f"images/{img_filename}")
    
            # Update the in-memory record
            record["annotator"] = annotator
            record["label"] = label
            record["heading"] = heading
            record["text"] = text
            record["source"] = source
            record["source_category"] = source_category
            record["category"] = category
            record["multi_category"] = multi_cat
            record["annotation_confidence"] = str(confidence)
            record["additional_notes"] = self.notes_entry.get("0.0", "end-1c").strip()
            record["image_path"] = ";".join(image_rel_paths)
            if "timestamp" not in record or not record.get("timestamp"):
                record["timestamp"] = datetime.now().isoformat()
    
            self._rewrite_csv()
        except Exception as e:
            messagebox.showerror("Update Error", f"Failed to update entry. Please make sure the dataset CSV file is not open in Excel or another program.\n\nError: {e}")
            return False

        # Apply filter again to reflect changes visually and filter out records that no longer match
        self._apply_advanced_filter(keep_index=True)
        if show_success:
            messagebox.showinfo("Update Complete",
                f"Record {self.current_review_index + 1} updated successfully!")
        return True

    def _delete_entry(self):
        """Delete the currently displayed record after user confirmation.

        Removes the record from memory, rewrites the CSV, and adjusts
        the review index. If no records remain, switches back to Annotate mode.
        """
        if not self.dataset_records:
            return

        confirm = messagebox.askyesno("Confirm Delete",
            f"Are you sure you want to delete Record {self.current_review_index + 1}?\n\n"
            "This action cannot be undone.")
        if not confirm:
            return

        deleted_record = self.dataset_records.pop(self.current_review_index)
        
        # Also remove from all_dataset_records
        all_idx = next((i for i, r in enumerate(self.all_dataset_records) if (r.get("id") or "") == (deleted_record.get("id") or "")), -1)
        if all_idx >= 0:
            self.all_dataset_records.pop(all_idx)

        try:
            self._rewrite_csv()
        except Exception as e:
            # Revert the deletion in memory since saving failed
            self.dataset_records.insert(self.current_review_index, deleted_record)
            if all_idx >= 0:
                self.all_dataset_records.insert(all_idx, deleted_record)
            messagebox.showerror("Delete Error", f"Failed to delete entry. Please make sure the dataset CSV file is not open in Excel or another program.\n\nError: {e}")
            return

        self._apply_advanced_filter(keep_index=True)

        if not self.all_dataset_records:
            messagebox.showinfo("No Records", "All records have been deleted.")
            self.mode_switcher.set("📝 Annotate")
            self._toggle_mode("📝 Annotate")
            return

    def _rewrite_csv(self):
        """Rewrite the entire CSV file from the in-memory records list."""
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            for record in self.all_dataset_records:
                writer.writerow(record)

    def _save_draft(self):
        """Save the current annotation field values as a draft.

        Called when switching from Annotate to Review mode so the user's
        in-progress work is not lost.
        """
        self.draft_annotation = {
            "annotator": self.annotator_entry.get().strip(),
            "label": self.label_var.get(),
            "multi_cat": self.multi_cat_var.get(),
            "category": self.category_var.get(),
            "source_category": self.source_cat_var.get(),
            "source": self.source_entry.get().strip(),
            "heading": self.heading_entry.get("1.0", "end-1c").strip(),
            "text": self.text_box.get("1.0", "end-1c").strip(),
            "confidence": self.confidence_entry.get().strip(),
            "additional_notes": self.notes_entry.get("0.0", "end-1c").strip(),
            "images": list(self.image_list),
        }

    def _restore_draft(self):
        """Restore previously saved annotation field values.

        Called when switching from Review back to Annotate mode.
        If no draft was saved, clears all fields instead.
        """
        if self.draft_annotation is None:
            self._clear_fields()
            return

        draft = self.draft_annotation
        self.draft_annotation = None

        self._clear_fields()
        self.annotator_entry.delete(0, "end")
        self.annotator_entry.insert(0, draft["annotator"])

        if draft["label"]:
            self.label_var.set(draft["label"])
            self._on_label_change()

        if draft["multi_cat"]:
            self.multi_cat_var.set(draft["multi_cat"])

        self.category_var.set(draft["category"])
        self.source_cat_var.set(draft["source_category"])

        self.source_entry.delete(0, "end")
        self.source_entry.insert(0, draft["source"])

        self.heading_entry.delete("1.0", "end")
        if draft["heading"]:
            self.heading_entry.insert("1.0", draft["heading"])

        self.text_box.delete("1.0", "end")
        if draft["text"]:
            self.text_box.insert("1.0", draft["text"])

        self.confidence_entry.delete(0, "end")
        self.confidence_entry.insert(0, draft["confidence"] or "100")

        # Restore additional notes
        self.notes_entry.delete("0.0", "end")
        notes = draft.get("additional_notes", "")
        if notes:
            self.notes_entry.insert("0.0", notes)

        self.image_list = draft["images"]
        self._refresh_previews()

    def _get_resource_path(self, relative_path):
        """Get absolute path to resource, works for dev and for PyInstaller."""
        try:
            # PyInstaller creates a temp folder and stores path in _MEIPASS
            base_path = Path(sys._MEIPASS)
        except Exception:
            base_path = Path(__file__).parent.resolve()
        
        return str(base_path / relative_path)

    def _check_for_updates(self):
        """Check GitHub for a new release tag in the background."""
        try:
            # Load current version
            version_file = self._get_resource_path("version.json")
            if not os.path.exists(version_file):
                return
            
            with open(version_file, "r") as f:
                data = json.load(f)
                current_version = data.get("version", "v1.0.0").strip().lower().lstrip('v')

            # Fetch latest version from GitHub API
            url = "https://api.github.com/repos/Faysal1000/fake-news-annotation-tool/releases/latest"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                latest_tag = response.json().get("tag_name")
                if latest_tag:
                    latest_normalized = latest_tag.strip().lower().lstrip('v')
                    if latest_normalized != current_version:
                        # Update needed! Safely call the UI method from the main thread
                        self.after(2000, lambda: self._show_update_popup(latest_tag))
        except Exception as e:
            print(f"Update check failed (this is non-fatal): {e}")

    def _show_update_popup(self, latest_version):
        """Show a popup with the OS-specific command to update the app."""
        popup = ctk.CTkToplevel(self)
        popup.title("Update Available")
        popup.geometry("600x350")
        popup.attributes("-topmost", True)
        
        # Center the popup relative to main window
        popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - 300
        y = self.winfo_y() + (self.winfo_height() // 2) - 175
        popup.geometry(f"+{x}+{y}")
        
        ctk.CTkLabel(popup, text=f"🎉 A new version ({latest_version}) is available!", 
                     font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 10))
        
        ctk.CTkLabel(popup, text="Please update to get the latest features and bug fixes.", 
                     font=ctk.CTkFont(size=14)).pack(pady=(0, 15))
        
        # Determine OS and Architecture
        system = platform.system()
        machine = platform.machine().lower()
        
        if system == "Darwin":
            if "arm" in machine or "aarch" in machine:
                command = 'mkdir -p ~/Desktop/"Fake News Dataset" && cd ~/Desktop/"Fake News Dataset" && curl -L -O https://github.com/Faysal1000/fake-news-annotation-tool/releases/latest/download/FakeNewsAnnotator-macOS-AppleSilicon.zip && unzip -o FakeNewsAnnotator-macOS-AppleSilicon.zip && rm FakeNewsAnnotator-macOS-AppleSilicon.zip'
            else:
                command = 'mkdir -p ~/Desktop/"Fake News Dataset" && cd ~/Desktop/"Fake News Dataset" && curl -L -O https://github.com/Faysal1000/fake-news-annotation-tool/releases/latest/download/FakeNewsAnnotator-macOS-Intel.zip && unzip -o FakeNewsAnnotator-macOS-Intel.zip && rm FakeNewsAnnotator-macOS-Intel.zip'
        elif system == "Windows":
            command = 'mkdir "%USERPROFILE%\\Desktop\\Fake News Dataset" 2>nul & cd "%USERPROFILE%\\Desktop\\Fake News Dataset" & curl -L -O https://github.com/Faysal1000/fake-news-annotation-tool/releases/latest/download/FakeNewsAnnotator-Windows.exe'
        else:
            command = 'mkdir -p ~/Desktop/"Fake News Dataset" && cd ~/Desktop/"Fake News Dataset" && curl -L -O https://github.com/Faysal1000/fake-news-annotation-tool/releases/latest/download/FakeNewsAnnotator-Linux && chmod +x FakeNewsAnnotator-Linux'

        # Textbox to show the command
        cmd_box = ctk.CTkTextbox(popup, height=80, font=ctk.CTkFont(family="Courier", size=12))
        cmd_box.pack(fill="x", padx=20, pady=10)
        cmd_box.insert("0.0", command)
        cmd_box.configure(state="disabled") # Make it read-only
        
        def copy_to_clipboard():
            self.clipboard_clear()
            self.clipboard_append(command)
            self.update()
            copy_btn.configure(text="✅ Copied!")
            self.after(2000, lambda: copy_btn.configure(text="📋 Copy Command"))
            
        btn_frame = ctk.CTkFrame(popup, fg_color="transparent")
        btn_frame.pack(pady=20)
        
        copy_btn = ctk.CTkButton(btn_frame, text="📋 Copy Command", command=copy_to_clipboard)
        copy_btn.pack(side="left", padx=10)
        
        ctk.CTkButton(btn_frame, text="Close", fg_color="transparent", border_width=1, 
                      command=popup.destroy).pack(side="left", padx=10)


if __name__ == "__main__":
    app = AnnotatorTool()
    app.mainloop()
