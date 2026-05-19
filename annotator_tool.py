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
    # On macOS, if it's inside a .app bundle, navigate up 3 levels to the folder containing the .app
    if ".app/Contents/MacOS" in _exe_path.as_posix():
        SCRIPT_DIR = _exe_path.parents[2]
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
# - timestamp:  ISO-format datetime when the entry was saved
# - heading:         Optional headline/title of the news item
# - multi_category:  Sub-classification for fake news (Misinformation/Rumor/Clickbait)
#                    or "Real" when the label is Real
# - source_category: Platform/medium where the news was found (required)
CSV_COLUMNS = ["id", "heading", "text", "image_path", "label", "multi_category",
               "source", "source_category", "category", "annotator", "timestamp"]

# CATEGORIES: Predefined category options for the dropdown menu.
# First entry is empty string (no category selected).
# "Other" is provided as a catch-all for categories not in the list.
CATEGORIES = ["", "Politics", "Health", "Science", "Technology", "Sports",
              "Entertainment", "Business", "Education", "Environment",
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

        # Build all UI elements, set up drag-and-drop, and refresh stats
        self._build_ui()
        self._setup_dnd()
        self._update_stats()

        # AUTO-SAVE ANNOTATOR NAME:
        # Whenever the user types in or tabs away from the annotator field,
        # immediately persist the name to the config file. This way the
        # name is remembered even if the user closes the tool without saving.
        self.annotator_entry.bind("<KeyRelease>", lambda e: save_config(self.annotator_entry.get().strip()))
        self.annotator_entry.bind("<FocusOut>", lambda e: save_config(self.annotator_entry.get().strip()))

    # =========================================================================
    # UI CONSTRUCTION
    # =========================================================================

    def _build_ui(self):
        """Build the entire GUI layout.
        
        Creates a scrollable main frame and adds all input sections:
        annotator name, label selection, category dropdown, source field,
        text area, image controls, action buttons, and a status bar.
        """
        # Scrollable container so the UI works on smaller screens
        main = ctk.CTkScrollableFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=18, pady=10)

        # ----- Application title at the top of the window -----
        ctk.CTkLabel(main, text="📰 Fake News Dataset Annotator",
                     font=ctk.CTkFont(size=26, weight="bold")).pack(pady=(5, 2))

        # ----- Stats bar: shows total entry count and image count -----
        self.stats_label = ctk.CTkLabel(main, text="", font=ctk.CTkFont(size=13))
        self.stats_label.pack(pady=(0, 10))

        # ----- ANNOTATOR NAME FIELD (required) -----
        # Pre-filled from config file if the user has used the tool before.
        self._section(main, "👤 Annotator Name *")
        self.annotator_entry = ctk.CTkEntry(main, placeholder_text="Your name", height=36)
        self.annotator_entry.pack(fill="x", padx=10, pady=(0, 8))
        self.annotator_entry.insert(0, load_config())  # Load saved name from config

        # ----- LABEL SELECTION (required) -----
        # Two radio buttons: "Fake" (red) and "Real" (green).
        # Exactly one must be selected before saving.
        # A trace is attached to label_var so that selecting a label
        # dynamically shows/hides the multi-category sub-classification.
        self._section(main, "🏷️ Label *")
        label_frame = ctk.CTkFrame(main, fg_color="transparent")
        label_frame.pack(fill="x", padx=10, pady=(0, 8))
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
        # Header label inside the frame
        ctk.CTkLabel(self.multi_cat_frame, text="⚠️ Fake News Type *",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#f39c12").pack(anchor="w", padx=12, pady=(8, 4))
        # Radio button row for the three sub-types
        multi_btn_frame = ctk.CTkFrame(self.multi_cat_frame, fg_color="transparent")
        multi_btn_frame.pack(fill="x", padx=12, pady=(0, 8))
        # Each sub-type has its own colour to aid quick visual identification
        self.radio_misinfo = ctk.CTkRadioButton(
            multi_btn_frame, text="Misinformation", variable=self.multi_cat_var,
            value="Misinformation", font=ctk.CTkFont(size=13),
            fg_color="#e67e22", hover_color="#d35400")
        self.radio_misinfo.pack(side="left", padx=(0, 20))
        self.radio_rumor = ctk.CTkRadioButton(
            multi_btn_frame, text="Rumor", variable=self.multi_cat_var,
            value="Rumor", font=ctk.CTkFont(size=13),
            fg_color="#9b59b6", hover_color="#8e44ad")
        self.radio_rumor.pack(side="left", padx=(0, 20))
        self.radio_clickbait = ctk.CTkRadioButton(
            multi_btn_frame, text="Clickbait", variable=self.multi_cat_var,
            value="Clickbait", font=ctk.CTkFont(size=13),
            fg_color="#e74c3c", hover_color="#c0392b")
        self.radio_clickbait.pack(side="left")

        # ----- NEWS CATEGORY & SOURCE CATEGORY (both required) -----
        # Placed side by side on the same row to save vertical space.
        # News Category: topic of the news (Politics, Health, etc.)
        # Source Category: platform/medium where the news was found
        self._section(main, "📂 News Category & 📡 Source Category *")
        cat_row = ctk.CTkFrame(main, fg_color="transparent")
        cat_row.pack(fill="x", padx=10, pady=(0, 8))
        # Left side: News Category dropdown
        ctk.CTkLabel(cat_row, text="News Category:",
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 5))
        self.category_var = ctk.StringVar(value="")  # Empty = no category
        self.category_menu = ctk.CTkOptionMenu(cat_row, variable=self.category_var,
                                                values=CATEGORIES, width=200, height=34)
        self.category_menu.pack(side="left", padx=(0, 25))
        # Right side: Source Category dropdown
        ctk.CTkLabel(cat_row, text="Source Category:",
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 5))
        self.source_cat_var = ctk.StringVar(value="")  # Empty = nothing selected
        self.source_cat_menu = ctk.CTkOptionMenu(cat_row, variable=self.source_cat_var,
                                                  values=SOURCE_CATEGORIES, width=200, height=34)
        self.source_cat_menu.pack(side="left")

        # ----- SOURCE LINK FIELD (optional) -----
        # Free-text field for the specific source link (URL, etc.)
        self._section(main, "🔗 Source Link (optional)")
        self.source_entry = ctk.CTkEntry(main, placeholder_text="Paste URL or link here", height=36)
        self.source_entry.pack(fill="x", padx=10, pady=(0, 8))

        # ----- HEADING FIELD (optional) -----
        # A short headline or title for the news item. Stored in the
        # 'heading' CSV column. Optional — the annotator can leave it blank.
        self._section(main, "📌 Heading (optional)")
        self.heading_entry = ctk.CTkEntry(main, placeholder_text="News headline / title", height=36)
        self.heading_entry.pack(fill="x", padx=10, pady=(0, 8))

        # ----- TEXT INPUT AREA -----
        # Large multiline text box for the news content.
        # Required if no image is provided. A warning shows if under 10 words.
        self._section(main, "📝 News Text (required if no image)")
        self.text_box = ctk.CTkTextbox(main, height=160, font=ctk.CTkFont(size=13),
                                        border_width=1, border_color="#555")
        self.text_box.pack(fill="x", padx=10, pady=(0, 8))

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
                       width=160, height=36).pack(side="left", padx=(0, 10))
        # Paste button - grabs image from clipboard (screenshot, copied image, etc.)
        ctk.CTkButton(img_btn_frame, text="📋 Paste from Clipboard", command=self._paste_image,
                       width=200, height=36).pack(side="left", padx=(0, 10))
        # Remove all button - clears all attached images at once
        ctk.CTkButton(img_btn_frame, text="❌ Remove All Images", command=self._remove_all_images,
                       width=170, height=36, fg_color="#e74c3c",
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

        # ----- ACTION BUTTONS -----
        btn_frame = ctk.CTkFrame(main, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=(10, 5))
        # Save button - validates input, saves image(s), appends CSV row
        ctk.CTkButton(btn_frame, text="💾  Save Entry", command=self._save_entry,
                       height=44, font=ctk.CTkFont(size=16, weight="bold"),
                       fg_color="#2ecc71", hover_color="#27ae60",
                       text_color="black").pack(side="left", expand=True, fill="x", padx=(0, 10))
        # Clear button - resets all fields EXCEPT annotator name
        ctk.CTkButton(btn_frame, text="🗑️  Clear All", command=self._clear_all,
                       height=44, width=180, font=ctk.CTkFont(size=16, weight="bold"),
                       fg_color="#555", hover_color="#777").pack(side="left")

        # ----- STATUS BAR -----
        # Shows feedback messages: "Ready", "Entry saved", validation errors, etc.
        self.status_label = ctk.CTkLabel(main, text="Ready", font=ctk.CTkFont(size=12),
                                          text_color="#888")
        self.status_label.pack(pady=(8, 5))

    def _section(self, parent, text):
        """Create a bold section heading label in the UI.
        
        Used to visually separate different input areas (Annotator, Label, etc.).
        
        Args:
            parent: The parent widget to place the label in.
            text: The heading text to display.
        """
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=14, weight="bold"),
                     anchor="w").pack(fill="x", padx=10, pady=(10, 3))

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

        # Create a thumbnail card for each image in a grid (4 columns)
        for i, (path, pil_img) in enumerate(self.image_list):
            try:
                # Open or copy the image and create a thumbnail
                if path:
                    img = Image.open(path)
                else:
                    img = pil_img.copy()
                img.thumbnail((130, 100))  # Resize to fit inside the box
                photo = ImageTk.PhotoImage(img)
                self.preview_photos.append(photo)  # Keep reference alive

                # Create a card frame for this thumbnail
                frame = ctk.CTkFrame(grid_frame, fg_color="#222240",
                                      corner_radius=6)
                frame.grid(row=i // 4, column=i % 4, padx=4, pady=4)

                # Display the thumbnail image
                lbl = ctk.CTkLabel(frame, image=photo, text="")
                lbl.pack(padx=4, pady=(4, 0))

                # Show the filename (truncated to 18 chars)
                name = path.name if path else f"clipboard_{i+1}.png"
                ctk.CTkLabel(frame, text=name[:18], font=ctk.CTkFont(size=9),
                             text_color="#aaa").pack(pady=(0, 1))

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
        heading = self.heading_entry.get().strip()  # Optional headline
        text = self.text_box.get("1.0", "end-1c").strip()  # Get text without trailing newline
        source = self.source_entry.get().strip()
        source_category = self.source_cat_var.get()  # Required platform/medium
        category = self.category_var.get()
        multi_cat = self.multi_cat_var.get()  # Sub-classification for fake news
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
                "timestamp": datetime.now().isoformat(),
            })

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
        self.heading_entry.delete(0, "end")        # Clear the heading field
        self.source_entry.delete(0, "end")         # Clear the source field
        self.label_var.set("")                      # Deselect the label radio buttons
        self.category_var.set("")                   # Reset category dropdown
        self.source_cat_var.set("")                  # Reset source category dropdown
        self.multi_cat_var.set("")                   # Reset multi-category selection
        self.multi_cat_frame.pack_forget()           # Hide multi-category panel
        self._remove_all_images()                   # Clear all attached images

    def _clear_all(self):
        """Clear all fields except the annotator name.
        
        Triggered by the 'Clear All' button. The annotator name is
        intentionally preserved because the same person typically
        annotates many entries in a single session.
        """
        self._clear_fields()
        self.status_label.configure(text="All fields cleared", text_color="#888")

    def _update_stats(self):
        """Refresh the stats bar at the top of the UI.
        
        Reads the current entry count from the CSV and image count from
        the images/ folder, then updates the stats label to display them.
        Called after each save and at startup.
        """
        total = get_entry_count()
        img_count = get_image_count()
        self.stats_label.configure(
            text=f"Total entries: {total}  |  Images: {img_count}"
        )


# =============================================================================
# ENTRY POINT
# =============================================================================
# When this script is run directly (not imported), create the application
# window and start the tkinter event loop. The event loop keeps the window
# open and responsive until the user closes it.

if __name__ == "__main__":
    app = AnnotatorTool()
    app.mainloop()
