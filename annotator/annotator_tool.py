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
REQUIRED = {"customtkinter": "customtkinter", "PIL": "Pillow", "tkinterdnd2": "tkinterdnd2"}

def _check_and_install():
    """Check for required packages and install them if missing.
    
    Iterates through the REQUIRED dict, tries to import each module,
    and collects any that fail. If there are missing packages, it runs
    pip install using the requirements.txt file located next to this script.
    """
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
               "source", "source_category", "category", "annotator", "annotation_confidence", "timestamp"]

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
SOURCE_CATEGORIES = ["", "News Channel", "Newspaper", "Facebook",
                        "Twitter", "Instagram", "Reddit", "YouTube", "Blog",
                         "Website", "Miscellaneous"]

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
    if not CSV_PATH.exists():
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
              "news_categories": {}}
    if not CSV_PATH.exists():
        return result
    with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            result["total"] += 1
            label = row.get("label", "").strip()
            if label == "Fake":
                result["fake"] += 1
                sub = row.get("multi_category", "").strip()
                if sub in result["fake_subcategories"]:
                    result["fake_subcategories"][sub] += 1
            elif label == "Real":
                result["real"] += 1
            # Count news categories
            cat = row.get("category", "").strip()
            if cat:
                result["news_categories"][cat] = result["news_categories"].get(cat, 0) + 1
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

class AnnotatorTool(ctk.CTk):
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

        # Make sure the images/ directory exists before anything else
        ensure_dirs()

        # Set the visual theme to dark mode with blue accent color
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Configure the main window title, size, and minimum dimensions
        self.title("📰 Fake News Dataset Annotator")
        self.geometry("950x900")
        self.minsize(850, 750)

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
        # The currently active filter in Review mode
        self.active_filter = None
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
        
        Creates a scrollable main frame and adds all input sections:
        annotator name, label selection, category dropdown, source field,
        text area, image controls, and action buttons.
        """
        # Scrollable container so the UI works on smaller screens
        main = ctk.CTkScrollableFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=18, pady=10)

        # ----- TOP BAR: Mode switcher (left) + Title (center) -----
        top_bar = ctk.CTkFrame(main, fg_color="transparent")
        top_bar.pack(fill="x", pady=(5, 2))

        self.mode_switcher = ctk.CTkSegmentedButton(
            top_bar, values=["📝 Annotate", "🔍 Review"],
            command=self._toggle_mode,
            font=ctk.CTkFont(size=10),
            selected_color="#1f6aa5", selected_hover_color="#144870",
            height=24, width=150
        )
        self.mode_switcher.set("📝 Annotate")
        self.mode_switcher.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(top_bar, text="📰 Fake News Dataset Annotator",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(side="left", expand=True)

        # ----- Stats bar: shows total entry count, image count, and label counts -----
        self.stats_frame = ctk.CTkFrame(main, fg_color="transparent")
        self.stats_frame.pack(pady=(0, 2))

        # ----- Category stats bar: shows news category counts on a second line -----
        self.category_stats_frame = ctk.CTkFrame(main, fg_color="transparent")
        self.category_stats_frame.pack(pady=(0, 10))

        # ----- REVIEW NAVIGATION BAR (hidden by default, shown in Review mode) -----
        self.nav_frame = ctk.CTkFrame(main, fg_color="#1a1a2e", corner_radius=6,
                                       border_width=1, border_color="#444")
        self.prev_btn = ctk.CTkButton(self.nav_frame, text="◀ Prev",
                                       command=self._prev_record, width=80, height=28,
                                       font=ctk.CTkFont(size=12))
        self.prev_btn.pack(side="left", padx=8, pady=5)
        
        # Center frame for editable record index
        self.record_center_frame = ctk.CTkFrame(self.nav_frame, fg_color="transparent")
        self.record_center_frame.pack(side="left", expand=True)
        
        ctk.CTkLabel(self.record_center_frame, text="Record", font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 5))
        
        self.record_index_entry = ctk.CTkEntry(self.record_center_frame, width=50, height=24, font=ctk.CTkFont(size=13, weight="bold"), justify="center")
        self.record_index_entry.pack(side="left")
        self.record_index_entry.bind("<Return>", self._jump_to_record)
        
        self.record_total_label = ctk.CTkLabel(self.record_center_frame, text="of 0", font=ctk.CTkFont(size=13))
        self.record_total_label.pack(side="left", padx=(5, 0))
        self.next_btn = ctk.CTkButton(self.nav_frame, text="Next ▶",
                                       command=self._next_record, width=80, height=28,
                                       font=ctk.CTkFont(size=12))
        self.next_btn.pack(side="right", padx=8, pady=5)

        # ----- ANNOTATOR NAME FIELD -----
        annotator_row = ctk.CTkFrame(main, fg_color="transparent")
        annotator_row.pack(fill="x", padx=10, pady=(10, 8))

        self._inline_label(annotator_row, "Annotator name *")
        self.annotator_entry = ctk.CTkEntry(annotator_row, placeholder_text="Your name", height=28)
        self.annotator_entry.pack(side="left", fill="x", expand=True)

        # ----- LABEL SELECTION (required) -----
        # Two radio buttons: "Fake" (red) and "Real" (green).
        # Exactly one must be selected before saving.
        # A trace is attached to label_var so that selecting a label
        # dynamically shows/hides the multi-category sub-classification.
        label_frame = ctk.CTkFrame(main, fg_color="transparent")
        label_frame.pack(fill="x", padx=10, pady=(10, 8))
        self._inline_label(label_frame, "News Label *")
        self.label_var = ctk.StringVar(value="")  # Empty = nothing selected yet
        self.radio_fake = ctk.CTkRadioButton(label_frame, text="Fake", variable=self.label_var,
                                              value="Fake", font=ctk.CTkFont(size=14),
                                              fg_color="#e74c3c", hover_color="#c0392b",
                                              command=self._on_label_change)
        self.radio_fake.pack(side="left", padx=(0, 30))
        self.radio_real = ctk.CTkRadioButton(label_frame, text="Real", variable=self.label_var,
                                              value="Real", font=ctk.CTkFont(size=14),
                                              fg_color="#2ecc71", hover_color="#27ae60",
                                              command=self._on_label_change)
        self.radio_real.pack(side="left")
        
        self.confidence_entry = ctk.CTkEntry(label_frame, placeholder_text="100", width=80, height=28)
        self.confidence_entry.pack(side="right")
        self.confidence_entry.insert(0, "100")
        
        ctk.CTkLabel(label_frame, text="Confidence %",
                     font=ctk.CTkFont(size=13)).pack(side="right", padx=(0, 10))

        # ----- MULTI-CATEGORY SUB-CLASSIFICATION -----
        # This section is only visible when the label is "Fake".
        # The annotator must pick exactly one sub-type: Misinformation, Rumor,
        # or Clickbait to describe the nature of the fake news.
        # When the label is "Real", this section is hidden and the
        # multi_category column is automatically set to "Real" on save.
        self.multi_cat_frame = ctk.CTkFrame(main, fg_color="#1a1a2e",
                                             corner_radius=8, border_width=1,
                                             border_color="#444")
        # Initially hidden — will be shown by _on_label_change when "Fake" is selected
        self.multi_cat_var = ctk.StringVar(value="")  # Empty = nothing selected yet
        # Ensure it aligns perfectly with the other inline labels by fixing the label width
        header_frame = ctk.CTkFrame(self.multi_cat_frame, width=140, height=28, fg_color="transparent")
        header_frame.pack_propagate(False) # Force width to 140
        header_frame.pack(side="left", padx=(10, 10), pady=(10, 10))
        
        ctk.CTkLabel(header_frame, text="⚠️ Fake News Type",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#f39c12").pack(side="left", padx=(0, 2))
        ctk.CTkLabel(header_frame, text="*",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#e74c3c").pack(side="left")

        # Each sub-type has its own colour to aid quick visual identification
        self.radio_misinfo = ctk.CTkRadioButton(
            self.multi_cat_frame, text="Misinformation", variable=self.multi_cat_var,
            value="Misinformation", font=ctk.CTkFont(size=13),
            fg_color="#e67e22", hover_color="#d35400")
        self.radio_misinfo.pack(side="left", padx=(0, 20), pady=(10, 10))
        
        self.radio_rumor = ctk.CTkRadioButton(
            self.multi_cat_frame, text="Rumor", variable=self.multi_cat_var,
            value="Rumor", font=ctk.CTkFont(size=13),
            fg_color="#9b59b6", hover_color="#8e44ad")
        self.radio_rumor.pack(side="left", padx=(0, 20), pady=(10, 10))
        
        self.radio_clickbait = ctk.CTkRadioButton(
            self.multi_cat_frame, text="Clickbait", variable=self.multi_cat_var,
            value="Clickbait", font=ctk.CTkFont(size=13),
            fg_color="#e74c3c", hover_color="#c0392b")
        self.radio_clickbait.pack(side="left", pady=(10, 10))

        # ----- NEWS CATEGORY & SOURCE CATEGORY (both required) -----
        # Placed side by side on the same row to save vertical space.
        # News Category: topic of the news (Politics, Health, etc.)
        # Source Category: platform/medium where the news was found
        cat_row = ctk.CTkFrame(main, fg_color="transparent")
        cat_row.pack(fill="x", padx=10, pady=(10, 8))
        # Left side: News Category dropdown
        self._inline_label(cat_row, "News Category *")
        self.category_var = ctk.StringVar(value="")  # Empty = no category
        self.category_menu = ctk.CTkOptionMenu(cat_row, variable=self.category_var,
                                                values=CATEGORIES, height=28)
        self.category_menu.pack(side="left", fill="x", expand=True)
        
        # Spacer
        ctk.CTkFrame(cat_row, width=30, height=28, fg_color="transparent").pack(side="left")
        
        # Right side: Source Category dropdown
        self._inline_label(cat_row, "Source Category *")
        self.source_cat_var = ctk.StringVar(value="")  # Empty = nothing selected
        self.source_cat_menu = ctk.CTkOptionMenu(cat_row, variable=self.source_cat_var,
                                                  values=SOURCE_CATEGORIES, height=28)
        self.source_cat_menu.pack(side="left", fill="x", expand=True)

        # ----- SOURCE LINK FIELD (optional) -----
        source_row = ctk.CTkFrame(main, fg_color="transparent")
        source_row.pack(fill="x", padx=10, pady=(10, 8))

        self._inline_label(source_row, "Source Link")
        self.source_entry = ctk.CTkEntry(source_row, placeholder_text="Paste URL or link here", height=28)
        self.source_entry.pack(side="left", fill="x", expand=True)

        # ----- NEWS HEADING FIELD (optional) -----
        # Placed as a separate section with a label above and 2-line input box below.
        self._section(main, "News Heading (optional)")
        self.heading_entry = ctk.CTkTextbox(main, height=55, font=ctk.CTkFont(size=13),
                                            border_width=1, border_color="#555")
        self.heading_entry.pack(fill="x", padx=10, pady=(0, 8))

        # ----- TEXT INPUT AREA -----
        # Large multiline text box for the news content.
        # Required if no image is provided. A warning shows if under 10 words.
        self._section(main, "📝 News Text (required if no image)")
        self.text_box = ctk.CTkTextbox(main, height=160, font=ctk.CTkFont(size=13),
                                        border_width=1, border_color="#555")
        self.text_box.pack(fill="x", padx=10, pady=(0, 8))

        # Prevent mouse wheel scrolling in textboxes from bubbling up to the parent scrollable frame
        def block_scroll(widget):
            tags = list(widget._textbox.bindtags())
            if 'Text' in tags:
                tags.insert(tags.index('Text') + 1, 'BlockScroll')
                widget._textbox.bindtags(tuple(tags))
            widget._textbox.bind_class('BlockScroll', '<MouseWheel>', lambda e: "break")
            widget._textbox.bind_class('BlockScroll', '<Button-4>', lambda e: "break")
            widget._textbox.bind_class('BlockScroll', '<Button-5>', lambda e: "break")

        block_scroll(self.heading_entry)
        block_scroll(self.text_box)

        # ----- IMAGE INPUT SECTION -----
        # Supports three ways to add images:
        #   1. Browse button: opens a file dialog (multi-select enabled)
        #   2. Paste button: grabs image from system clipboard
        #   3. Drag-and-drop zone: drop image files directly (set up separately)
        # Multiple images can be added for a single entry.
        self._section(main, "🖼️ Images (required if no text) — multiple allowed")
        img_btn_frame = ctk.CTkFrame(main, fg_color="transparent")
        img_btn_frame.pack(fill="x", padx=10, pady=(0, 4))

        # Browse button - opens native file picker filtered to image types only
        ctk.CTkButton(img_btn_frame, text="📁 Browse Images", command=self._browse_image,
                       width=130, height=28).pack(side="left", padx=(0, 10))
        # Paste button - grabs image from clipboard (screenshot, copied image, etc.)
        ctk.CTkButton(img_btn_frame, text="📋 Paste from Clipboard", command=self._paste_image,
                       width=160, height=28).pack(side="left", padx=(0, 10))
        # Remove all button - clears all attached images at once
        ctk.CTkButton(img_btn_frame, text="❌ Remove All Images", command=self._remove_all_images,
                       width=140, height=28, fg_color="#e74c3c",
                       hover_color="#c0392b").pack(side="left")

        # ----- DRAG AND DROP ZONE / IMAGE PREVIEW AREA -----
        # This box serves dual purpose:
        #   - When empty: shows drag-and-drop hint text
        #   - When images are added: shows thumbnail grid inside the box
        # The box expands dynamically to fit the thumbnails.
        self.drop_frame = ctk.CTkFrame(main, height=100, border_width=2,
                                        border_color="#666", fg_color="#1a1a2e")
        self.drop_frame.pack(fill="x", padx=10, pady=(4, 8))

        # Hint label shown when no images are selected
        self.drop_label = ctk.CTkLabel(self.drop_frame,
                                        text="📥 Drag & Drop image(s) here\nor use Browse / Paste buttons above",
                                        font=ctk.CTkFont(size=14), text_color="#888")
        self.drop_label.pack(expand=True, fill="both", pady=20)



        # ----- ACTION BUTTONS (Annotate Mode) -----
        self.annotate_btn_frame = ctk.CTkFrame(main, fg_color="transparent")
        self.annotate_btn_frame.pack(fill="x", padx=10, pady=(10, 5))
        ctk.CTkButton(self.annotate_btn_frame, text="💾  Save Entry", command=self._save_entry,
                       height=44, font=ctk.CTkFont(size=16, weight="bold"),
                       fg_color="#2ecc71", hover_color="#27ae60",
                       text_color="black").pack(side="left", expand=True, fill="x", padx=(0, 10))
        ctk.CTkButton(self.annotate_btn_frame, text="🗑️  Clear All", command=self._clear_all,
                       height=44, width=180, font=ctk.CTkFont(size=16, weight="bold"),
                       fg_color="#555", hover_color="#777").pack(side="left")

        # ----- ACTION BUTTONS (Review Mode, hidden by default) -----
        self.review_btn_frame = ctk.CTkFrame(main, fg_color="transparent")
        # Not packed yet — shown only when the user switches to Review mode
        ctk.CTkButton(self.review_btn_frame, text="💾  Update Entry", command=self._update_entry,
                       height=44, font=ctk.CTkFont(size=16, weight="bold"),
                       fg_color="#3498db", hover_color="#2980b9",
                       text_color="white").pack(side="left", expand=True, fill="x", padx=(0, 10))
        ctk.CTkButton(self.review_btn_frame, text="🗑️  Delete Entry", command=self._delete_entry,
                       height=44, width=180, font=ctk.CTkFont(size=16, weight="bold"),
                       fg_color="#e74c3c", hover_color="#c0392b").pack(side="left")

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
    # LABEL CHANGE HANDLER
    # =========================================================================

    def _on_label_change(self):
        """Show or hide the multi-category panel based on the selected label.
        
        Called whenever the user clicks a label radio button (Fake or Real).
        - If "Fake" is selected: the multi-category frame is shown so the
          annotator can pick a fake news sub-type (Misinformation/Rumor/Clickbait).
        - If "Real" is selected: the multi-category frame is hidden and the
          multi_cat_var is cleared (multi_category will be set to "Real" on save).
        """
        if self.label_var.get() == "Fake":
            # Show the multi-category sub-classification panel
            self.multi_cat_frame.pack(fill="x", padx=10, pady=(0, 8),
                                       after=self.radio_fake.master)
        else:
            # Hide the panel and reset the selection
            self.multi_cat_frame.pack_forget()
            self.multi_cat_var.set("")

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
        try:
            # pyrefly: ignore [missing-import]
            from tkinterdnd2 import DND_FILES, TkinterDnD
            self.drop_target_register = None
            try:
                # Load the tkdnd Tcl extension into the Tk interpreter
                self.tk.call('package', 'require', 'tkdnd')
                # Register the drop zone frame to accept file drops
                self.drop_frame.drop_target_register('DND_Files')
                # Bind the drop event to our handler
                self.drop_frame.dnd_bind('<<Drop>>', self._on_drop)
            except Exception:
                # tkdnd Tcl package not available on this system
                self.drop_label.configure(text="Drag & Drop not available\n(Use Browse or Paste instead)")
        except ImportError:
            # tkinterdnd2 Python package not installed
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
        # tkdnd wraps paths with spaces in curly braces: {/path/to/my file.png}
        # If braces are present, extract paths from within them
        if '{' in raw:
            import re
            paths = re.findall(r'\{(.+?)\}', raw)
        else:
            # Simple case: space-separated paths (no spaces in filenames)
            paths = raw.split()

        # Try to add each dropped file as an image
        added = 0
        for p in paths:
            path = Path(p.strip())
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
                photo = ImageTk.PhotoImage(img)
                self.preview_photos.append(photo)  # Keep reference alive

                # Create a card frame for this thumbnail
                frame = ctk.CTkFrame(grid_frame, fg_color="#222240",
                                      corner_radius=6)
                frame.grid(row=i // cols, column=i % cols, padx=4, pady=4)

                # Display the thumbnail image (click to enlarge)
                lbl = ctk.CTkLabel(frame, image=photo, text="", cursor="hand2")
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

        photo = ImageTk.PhotoImage(img)
        # Must keep a reference so the image isn't garbage collected
        popup._photo_ref = photo

        lbl = ctk.CTkLabel(popup, image=photo, text="")
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
            file_exists = CSV_PATH.exists()
            with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                # Write the header row only if this is a brand new CSV file
                if not file_exists:
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
        self.label_var.set("")                      # Deselect the label radio buttons
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

    def _apply_filter(self, filter_name, keep_index=False):
        """Filter the dataset based on the clicked stat."""
        if self.current_mode != "review":
            return
        
        self.active_filter = filter_name
        
        if not filter_name or filter_name == "Total":
            self.dataset_records = list(self.all_dataset_records)
        elif filter_name in ("Fake", "Real"):
            self.dataset_records = [r for r in self.all_dataset_records if r.get("label") == filter_name]
        elif filter_name in ("Misinformation", "Rumor", "Clickbait"):
            self.dataset_records = [r for r in self.all_dataset_records if r.get("multi_category") == filter_name]
        else:
            # Must be a News Category
            self.dataset_records = [r for r in self.all_dataset_records if r.get("category") == filter_name]
            
        if not keep_index:
            self.current_review_index = 0
        elif self.current_review_index >= len(self.dataset_records):
            self.current_review_index = max(0, len(self.dataset_records) - 1)
            
        self._update_stats() # Re-render stats to update highlights
        
        # In Review mode, always attempt to display the current record
        if self.dataset_records:
            self._display_record(self.current_review_index)
        else:
            self._clear_fields()
            self.record_index_entry.delete(0, "end")
            self.record_index_entry.insert(0, "0")
            self.record_total_label.configure(text="of 0")
            self.prev_btn.configure(state="disabled")
            self.next_btn.configure(state="disabled")

    def _create_stat_label(self, parent, text, filter_key=None, is_separator=False):
        """Helper to create interactive stat labels inside a frame."""
        if is_separator:
            lbl = ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=13))
            lbl.pack(side="left", padx=5)
            return
            
        is_active = (self.current_mode == "review") and (
            (filter_key == self.active_filter) or 
            (self.active_filter is None and filter_key == "Total")
        )
        
        color = "#f39c12" if is_active else ("#ffffff" if ctk.get_appearance_mode() == "Dark" else "#000000")
        fnt = ctk.CTkFont(size=13, weight="bold" if is_active else "normal", underline=is_active)
        
        lbl = ctk.CTkLabel(parent, text=text, font=fnt, text_color=color)
        lbl.pack(side="left")
        
        if filter_key:
            lbl.bind("<Button-1>", lambda e, k=filter_key: self._apply_filter(k))
            if self.current_mode == "review":
                lbl.configure(cursor="hand2")
            else:
                lbl.configure(cursor="arrow")

    def _update_stats(self):
        """Refresh the stats bar at the top of the UI.
        
        Reads the current entry count from the CSV, image count from
        the images/ folder, label/subcategory counts, and news category
        counts, then dynamically builds clickable stat labels.
        Called after each save and at startup.
        """
        counts = get_label_counts()
        img_count = get_image_count()
        total = counts["total"]
        fake = counts["fake"]
        real = counts["real"]
        sub = counts["fake_subcategories"]

        # Clear existing widgets
        for widget in self.stats_frame.winfo_children():
            widget.destroy()
        for widget in self.category_stats_frame.winfo_children():
            widget.destroy()

        # Line 1: Total, Images, Fake, Real + always show subcategory breakdown
        self._create_stat_label(self.stats_frame, f"Total: {total}", filter_key="Total")
        self._create_stat_label(self.stats_frame, "|", is_separator=True)
        self._create_stat_label(self.stats_frame, f"Images: {img_count}", filter_key=None)
        self._create_stat_label(self.stats_frame, "|", is_separator=True)
        self._create_stat_label(self.stats_frame, f"Fake: {fake}", filter_key="Fake")
        self._create_stat_label(self.stats_frame, "|", is_separator=True)
        self._create_stat_label(self.stats_frame, f"Real: {real}", filter_key="Real")
        self._create_stat_label(self.stats_frame, "||", is_separator=True)
        self._create_stat_label(self.stats_frame, f"Misinformation: {sub['Misinformation']}", filter_key="Misinformation")
        self._create_stat_label(self.stats_frame, "|", is_separator=True)
        self._create_stat_label(self.stats_frame, f"Rumor: {sub['Rumor']}", filter_key="Rumor")
        self._create_stat_label(self.stats_frame, "|", is_separator=True)
        self._create_stat_label(self.stats_frame, f"Clickbait: {sub['Clickbait']}", filter_key="Clickbait")

        # Line 2: News category counts
        news_cats = counts["news_categories"]
        if news_cats:
            lbl = ctk.CTkLabel(self.category_stats_frame, text="News Categories  ▸  ", font=ctk.CTkFont(size=12), text_color="#aaa")
            lbl.pack(side="left", padx=(0, 5))
            
            sorted_cats = sorted(news_cats.items())
            for i, (cat, count) in enumerate(sorted_cats):
                self._create_stat_label(self.category_stats_frame, f"{cat}: {count}", filter_key=cat)
                if i < len(sorted_cats) - 1:
                    self._create_stat_label(self.category_stats_frame, "|", is_separator=True)
        else:
            lbl = ctk.CTkLabel(self.category_stats_frame, text="News Categories  ▸  No entries yet", font=ctk.CTkFont(size=12), text_color="#aaa")
            lbl.pack(side="left")


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
            self.current_mode = "annotate"
            self.nav_frame.pack_forget()
            self.review_btn_frame.pack_forget()
            self.annotate_btn_frame.pack(fill="x", padx=10, pady=(10, 5))
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
            self.annotate_btn_frame.pack_forget()
            self.review_btn_frame.pack(fill="x", padx=10, pady=(10, 5))
            self.nav_frame.pack(fill="x", padx=10, pady=(5, 15),
                                after=self.review_btn_frame)

    def _load_dataset(self):
        """Load all records from the dataset CSV into memory for review."""
        self.all_dataset_records = []
        if not CSV_PATH.exists():
            self.dataset_records = []
            return
        with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.all_dataset_records.append(row)
                
        self._apply_filter(self.active_filter)

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
        self.record_index_entry.delete(0, "end")
        self.record_index_entry.insert(0, str(index + 1))
        self.record_total_label.configure(text=f"of {total}")
        self.prev_btn.configure(state="normal" if index > 0 else "disabled")
        self.next_btn.configure(state="normal" if index < total - 1 else "disabled")

        # Clear all fields before populating
        self._clear_fields()

        # Populate each field from the record
        self.annotator_entry.delete(0, "end")
        self.annotator_entry.insert(0, record.get("annotator", ""))

        label = record.get("label", "")
        if label:
            self.label_var.set(label)
            self._on_label_change()

        multi_cat = record.get("multi_category", "")
        if label == "Fake" and multi_cat in MULTI_CATEGORIES:
            self.multi_cat_var.set(multi_cat)

        self.category_var.set(record.get("category", ""))
        self.source_cat_var.set(record.get("source_category", ""))

        self.source_entry.delete(0, "end")
        self.source_entry.insert(0, record.get("source", ""))

        self.heading_entry.delete("1.0", "end")
        heading = record.get("heading", "")
        if heading:
            self.heading_entry.insert("1.0", heading)

        self.text_box.delete("1.0", "end")
        text = record.get("text", "")
        if text:
            self.text_box.insert("1.0", text)

        self.confidence_entry.delete(0, "end")
        self.confidence_entry.insert(0, record.get("annotation_confidence", "100"))

        # Load images referenced in the record
        self.image_list.clear()
        image_paths = record.get("image_path", "")
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
        if annotator != record.get("annotator", ""): changed = True
        elif label != record.get("label", ""): changed = True
        elif heading != record.get("heading", ""): changed = True
        elif text != record.get("text", ""): changed = True
        elif source != record.get("source", ""): changed = True
        elif source_category != record.get("source_category", ""): changed = True
        elif category != record.get("category", ""): changed = True
        elif multi_cat != record.get("multi_category", ""): changed = True
        elif confidence != record.get("annotation_confidence", "100"): changed = True
        
        if not changed:
            orig_images = [p for p in record.get("image_path", "").split(";") if p.strip()]
            if len(self.image_list) != len(orig_images):
                changed = True
                
        if not changed:
            return True
            
        response = messagebox.askyesnocancel(
            "Unsaved Changes",
            "You have unsaved changes in this record.\n\n"
            "Do you want to save them before moving?"
        )
        
        if response is True:  # Yes
            return self._update_entry(show_success=False)
        elif response is False:  # No
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
        entry_id = record.get("id", generate_id())
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
            record["image_path"] = ";".join(image_rel_paths)
    
            self._rewrite_csv()
        except Exception as e:
            messagebox.showerror("Update Error", f"Failed to update entry. Please make sure the dataset CSV file is not open in Excel or another program.\n\nError: {e}")
            return False

        # Apply filter again to reflect changes visually and filter out records that no longer match
        self._apply_filter(self.active_filter, keep_index=True)
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
        all_idx = next((i for i, r in enumerate(self.all_dataset_records) if r["id"] == deleted_record["id"]), -1)
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

        self._apply_filter(self.active_filter, keep_index=True)

        if not self.all_dataset_records:
            messagebox.showinfo("No Records", "All records have been deleted.")
            self.mode_switcher.set("📝 Annotate")
            self._toggle_mode("📝 Annotate")
            return

    def _rewrite_csv(self):
        """Rewrite the entire CSV file from the in-memory records list."""
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
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

        self.image_list = draft["images"]
        self._refresh_previews()


# =============================================================================
# ENTRY POINT
# =============================================================================
# When this script is run directly (not imported), create the application
# window and start the tkinter event loop. The event loop keeps the window
# open and responsive until the user closes it.

if __name__ == "__main__":
    app = AnnotatorTool()
    app.mainloop()
