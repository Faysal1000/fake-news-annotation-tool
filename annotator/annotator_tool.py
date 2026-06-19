# !/usr/bin/env python3
"""
Fake News Dataset Annotation Tool

This is a graphical user interface application built with CustomTkinter for building 
multimodal datasets. The tool supports three distinct workflows:
1. Annotation Mode: Create new dataset records by entering titles/texts and 
   attaching image and video media (via browser selection, copy/paste, or drag-and-drop).
2. Review Mode: Load, filter, inspect, and update previously saved annotations.
3. Re-label Mode: Perform blind secondary ratings on existing samples to calculate 
   agreement statistics like Cohen's Kappa or Fleiss' Kappa.

All dataset records are saved locally in a portable CSV file format. Images and videos 
are copied into dedicated media directories under unique, UUID-based file paths to 
prevent conflicts during multi-annotator mergers.

Usage:
    python annotator_tool.py
"""

import subprocess
import sys
from pathlib import Path

# Dependency Verification
# This map matches the internal python library names with the pip packages required.
# Before loading the application, we check if they are importable. If they are not,
# the tool automatically triggers pip to install them from the requirements file.
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
        req_file = Path(__file__).parent.resolve() / "requirements.txt"
        print(f"[INFO] Missing packages: {missing}. Installing from requirements.txt ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(req_file)])

# Run the dependency setup check on startup before main imports
_check_and_install()

# Core application imports
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
import random                        # For balanced kappa sample randomization
import time                          # For background sync timers
import re                            # For version number parsing
import shlex                         # For safe POSIX updater script quoting
import zipfile                       # For extracting macOS release archives
import webbrowser                    # For opening heading searches in the default browser
from urllib.parse import quote_plus  # For safely building Google search URLs

# Safe drag-and-drop setup
# Attempts to load tkinterdnd2 dynamically. If the library or underlying Tcl system
# is missing, drag-and-drop features are disabled but the app will still open normally.
try:
    # pyrefly: ignore [missing-import]
    from tkinterdnd2 import TkinterDnD, DND_FILES
    dnd_available = True
    dnd_base = TkinterDnD.DnDWrapper
except ImportError:
    dnd_available = False
    dnd_base = object

# Application paths
# Resolve SCRIPT_DIR to point to the base folder where data files are stored.
# If running as a PyInstaller bundle, we adjust the path to point next to
# the executable (and handle .app bundles on macOS specifically).
if getattr(sys, 'frozen', False):
    _exe_path = Path(sys.executable).resolve()
    if ".app/Contents/MacOS" in _exe_path.as_posix():
        SCRIPT_DIR = _exe_path.parents[3]
    else:
        SCRIPT_DIR = _exe_path.parent
else:
    SCRIPT_DIR = Path(__file__).parent.resolve()

# Directory for bundled read-only assets (icons, badges)
# PyInstaller extracts these to sys._MEIPASS at runtime
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    ASSETS_DIR = Path(sys._MEIPASS) / "assets"
    VERSION_FILE = Path(sys._MEIPASS) / "version.json"
else:
    ASSETS_DIR = SCRIPT_DIR / "assets"
    VERSION_FILE = SCRIPT_DIR / "version.json"

# Directory for storing saved image files
IMAGES_DIR = SCRIPT_DIR / "images"

# Directory for storing saved video files
VIDEOS_DIR = SCRIPT_DIR / "videos"

# Path to the primary dataset file
CSV_PATH = SCRIPT_DIR / "dataset.csv"

# Configuration file storing settings like the last annotator's name
CONFIG_PATH = SCRIPT_DIR / ".annotator_config.json"

# CSV file containing annotations targeted for inter-rater agreement checking
KAPPA_CSV_PATH = SCRIPT_DIR / "relabeling_for_kappa.csv"

# GitHub release metadata used by the in-app updater
UPDATE_API_URL = "https://api.github.com/repos/Faysal1000/fake-news-annotation-tool/releases/latest"
UPDATE_DOWNLOAD_BASE_URL = "https://github.com/Faysal1000/fake-news-annotation-tool/releases/latest/download"
UPDATE_CHUNK_SIZE = 8192


class UpdateCancelled(Exception):
    """Raised when the user cancels an in-progress updater download."""

# CSV database headers and their descriptions:
# - id: Unique UUID string (safe for merging without risk of index collisions)
# - heading: Optional article title or headline
# - text: Core textual content (optional if media is attached)
# - image_path: Local paths to files inside the images directory (semicolon-separated for multiple files)
# - video_path: Local path to the attached video file (maximum of 1)
# - label: Classification labels ("Fake" or "Real")
# - multi_category: Fine-grained subtype ("Misinformation", "Satire", "Clickbait", or "Real")
# - source: Direct URL or reference link to the original news source
# - source_category: Category describing where the news was retrieved (e.g. platform type)
# - category: Topic class of the news item (e.g. Politics, Science)
# - annotator: Identifier name of the reviewer
# - annotation_confidence: Numerical user confidence score (0 to 100)
# - additional_notes: Optional workspace comments for the annotator's personal reference
# - timestamp: Date and time when the record was successfully saved
CSV_COLUMNS = ["id", "heading", "text", "image_path", "video_path", "label", "multi_category",
               "source", "source_category", "category", "annotator", "annotation_confidence",
               "additional_notes", "timestamp"]

# Topic classification list for the news category dropdown
CATEGORIES = ["", "Politics", "Health", "Science", "Technology", "Sports",
              "Entertainment", "Religion", "Education", "Environment",
              "International", "Miscellaneous"]

# Classifications for news labeled as Fake
MULTI_CATEGORIES = ["Misinformation", "Satire", "Clickbait"]

# Detailed dashboard columns and metrics shared by local and team statistics.
DETAILED_STATS_COLUMNS = ["Total", "Real", "Fake", "Misinfo", "Satire", "Clickbait"]
DETAILED_STATS_METRICS = [
    "Total Items", "Total Images", "Total Videos",
    "Text Only", "Image Only", "Video Only",
    "Text + Image", "Text + Video", "Image + Video", "Text + Image + Video"
]

# Minimum character length for heading or text combined to be considered as a 'Text' modality
MIN_TEXT_LENGTH = 30

# Medium category dropdown options to specify where the news was found
SOURCE_CATEGORIES = ["", "News Channel", "Newspaper", "Facebook", "Tiktok",
                     "Twitter", "Instagram", "Reddit", "YouTube",
                     "Blog", "Website", "Miscellaneous"]

# Allowed file extensions for media uploads
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp")
VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".mkv", ".webm")

# Data utilities

def ensure_dirs():
    """
    Generates required directories for media storage if they are not already present.
    """
    IMAGES_DIR.mkdir(exist_ok=True)
    VIDEOS_DIR.mkdir(exist_ok=True)

def migrate_csv_format():
    """
    Checks if the local dataset.csv is in an outdated format and updates it.
    New columns like video_path are appended as empty strings to protect data integrity.
    """
    if not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0:
        return
    
    with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return
            
    if header == CSV_COLUMNS:
        return
        
    print("[INFO] Migrating dataset.csv to match the latest schema version...")
    with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        old_data = list(reader)
        
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in old_data:
            for col in CSV_COLUMNS:
                if col not in row:
                    row[col] = ""
            writer.writerow(row)

def generate_id():
    """
    Generate a UUID4 string to use as a unique entry ID.
    
    UUID4 is random-based, so there is virtually zero chance of collision
    even when multiple annotators work independently and merge later.
    
    Returns:
        str: A UUID string.
    """
    return str(uuid.uuid4())

def get_image_count():
    """
    Count how many image files currently exist in the images/ folder.
    
    Only counts files whose extension matches IMAGE_EXTENSIONS.
    Used for generating the sequential image number in filenames
    and for displaying stats in the UI.
    
    Returns:
        int: Number of image files in the images directory.
    """
    if not IMAGES_DIR.exists():
        return 0
    return len([f for f in IMAGES_DIR.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS])

def get_video_count():
    """
    Count how many video files currently exist in the videos/ folder.
    
    Returns:
        int: Number of video files in the videos directory.
    """
    if not VIDEOS_DIR.exists():
        return 0
    return len([f for f in VIDEOS_DIR.iterdir() if f.suffix.lower() in VIDEO_EXTENSIONS])

def get_entry_count():
    """
    Count how many data rows exist in the dataset CSV file.
    
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
    """
    Count entries by label (Fake/Real), fake news subcategories, and news categories.
    
    Reads the CSV and tallies:
      - Total entries
      - Fake entries
      - Real entries
      - Fake subcategory breakdown (Misinformation, Satire, Clickbait)
      - News category breakdown (Politics, Health, etc.)
    
    Returns:
        dict: Keys 'total', 'fake', 'real', 'fake_subcategories', and 'news_categories'.
    """
    result = {"total": 0, "fake": 0, "real": 0,
              "fake_subcategories": {"Misinformation": 0, "Satire": 0, "Clickbait": 0},
              "news_categories": {},
              "only_image": 0, "only_text": 0, "both_text_image": 0, "videos": 0}
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
            
            cat = (row.get("category") or "").strip()
            if cat:
                result["news_categories"][cat] = result["news_categories"].get(cat, 0) + 1
            
            has_text = bool((row.get("text") or "").strip())
            image_paths = row.get("image_path") or ""
            has_image = bool([p for p in image_paths.split(";") if p.strip()])
            has_video = bool((row.get("video_path") or "").strip())
            has_media = has_image or has_video
            
            if has_text and has_media:
                result["both_text_image"] += 1
            elif has_text and not has_media:
                result["only_text"] += 1
            elif not has_text and has_media:
                result["only_image"] += 1
                
            if has_video:
                result["videos"] += 1
    return result

def get_full_config():
    """
    Load the full configuration dictionary from the config file.
    """
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_full_config(config_dict):
    """
    Save the full configuration dictionary to the config file.
    """
    with open(CONFIG_PATH, "w") as f:
        json.dump(config_dict, f)

def get_machine_id():
    """
    Get or generate a unique machine ID for global metrics syncing.
    """
    cfg = get_full_config()
    if "machine_id" not in cfg:
        cfg["machine_id"] = str(uuid.uuid4())
        save_full_config(cfg)
    return cfg["machine_id"]

def save_config(annotator_name):
    """
    Persist the annotator's name to a hidden JSON config file.
    
    This is called automatically whenever the annotator name field changes
    (on every keystroke and focus-out), so the name is remembered for
    the next session without needing to click Save.
    
    Args:
        annotator_name: The annotator's name string to save.
    """
    cfg = get_full_config()
    cfg["annotator"] = annotator_name
    save_full_config(cfg)

def load_config():
    """
    Load the previously saved annotator name from the config file.
    
    Called once at startup to pre-fill the annotator name field.
    
    Returns:
        str: The saved annotator name, or empty string if no config exists.
    """
    return get_full_config().get("annotator", "")

def sanitize_name(name):
    """
    Convert an annotator name into a filesystem-safe string.
    
    Replaces any non-alphanumeric character with an underscore.
    Used when building image filenames to avoid spaces or special chars.
    
    Args:
        name: Raw annotator name string.
    
    Returns:
        str: Sanitized name safe for use in filenames.
    """
    return "".join(c if c.isalnum() else "_" for c in name.strip())

# SCRIPT LOGIC (inlined so the bundled app works without separate script files)

def _aggregate_datasets(annotators_dir, output_csv_path, output_images_dir, output_videos_dir):
    """
    Merge annotations from multiple annotator directories into a single dataset.
    Each annotator folder should contain dataset.csv, images/, and videos/.
    Returns a summary string on success, raises on failure.
    """
    if not os.path.exists(annotators_dir):
        raise FileNotFoundError(f"Annotators directory not found: {annotators_dir}")

    os.makedirs(output_images_dir, exist_ok=True)
    os.makedirs(output_videos_dir, exist_ok=True)

    annotators = []
    for entry in os.listdir(annotators_dir):
        entry_path = os.path.join(annotators_dir, entry)
        if os.path.isdir(entry_path) and not entry.startswith('.'):
            annotators.append(entry)

    if not annotators:
        raise ValueError(f"No annotator directories found inside: {annotators_dir}")

    fieldnames = list(CSV_COLUMNS)
    all_rows = []
    total_images_copied = 0
    total_videos_copied = 0

    for annotator in sorted(annotators):
        annotator_dir = os.path.join(annotators_dir, annotator)
        csv_path = os.path.join(annotator_dir, "dataset.csv")
        images_dir = os.path.join(annotator_dir, "images")
        videos_dir = os.path.join(annotator_dir, "videos")

        if os.path.isdir(images_dir):
            for img_file in os.listdir(images_dir):
                if img_file.startswith('.'):
                    continue
                src = os.path.join(images_dir, img_file)
                dst = os.path.join(output_images_dir, img_file)
                if os.path.isfile(src):
                    shutil.copy2(src, dst)
                    total_images_copied += 1

        if os.path.isdir(videos_dir):
            for vid_file in os.listdir(videos_dir):
                if vid_file.startswith('.'):
                    continue
                src = os.path.join(videos_dir, vid_file)
                dst = os.path.join(output_videos_dir, vid_file)
                if os.path.isfile(src):
                    shutil.copy2(src, dst)
                    total_videos_copied += 1

        if os.path.isfile(csv_path):
            with open(csv_path, mode='r', encoding='utf-8', errors='replace') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    clean_row = {}
                    for field in fieldnames:
                        val = row.get(field)
                        clean_row[field] = val.strip() if val is not None else ""
                    all_rows.append(clean_row)

    with open(output_csv_path, mode='w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_rows:
            writer.writerow(row)

    return (
        f"Aggregation complete!\n\n"
        f"Annotators found: {len(annotators)} ({', '.join(sorted(annotators))})\n"
        f"Total rows merged: {len(all_rows)}\n"
        f"Images copied: {total_images_copied}\n"
        f"Videos copied: {total_videos_copied}\n\n"
        f"Output CSV: {output_csv_path}"
    )


def _generate_kappa_sample(input_csv_path, output_csv_path, n,
                           real_pct=50.0, misinfo_pct=33.33,
                           satire_pct=33.33, clickbait_pct=33.34):
    """
    Generate a balanced random sample from the master dataset for kappa testing.
    Distribution is configurable via percentage parameters.
    real_pct: percentage of total sample that should be Real.
    misinfo_pct/satire_pct/clickbait_pct: percentage of the Fake portion for each sub-category.
    Returns a summary string on success.
    """
    input_path = Path(input_csv_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_csv_path}")

    # Load all rows
    rows = []
    with open(input_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    if not rows:
        raise ValueError("No data rows found in the input CSV.")

    # Split into category buckets
    fake_subcats = ["Misinformation", "Satire", "Clickbait"]
    buckets = {"Real": [], "Misinformation": [], "Satire": [], "Clickbait": []}
    for row in rows:
        label = (row.get("label") or "").strip()
        multi_cat = (row.get("multi_category") or "").strip()
        if label == "Real":
            buckets["Real"].append(row)
        elif label == "Fake" and multi_cat in fake_subcats:
            buckets[multi_cat].append(row)

    # Calculate quotas
    n_real = round(n * real_pct / 100.0)
    n_fake = n - n_real
    n_misinfo = round(n_fake * misinfo_pct / 100.0)
    n_satire = round(n_fake * satire_pct / 100.0)
    n_clickbait = n_fake - n_misinfo - n_satire  # ensure exact sum
    quotas = {"Real": n_real, "Misinformation": n_misinfo,
              "Satire": n_satire, "Clickbait": n_clickbait}

    # Phase 1: sample up to quota
    sampled = {}
    shortfall = 0
    surplus_cats = []
    for cat, quota in quotas.items():
        available = buckets[cat]
        if len(available) <= quota:
            sampled[cat] = list(available)
            shortfall += quota - len(available)
        else:
            sampled[cat] = random.sample(available, quota)
            surplus_cats.append(cat)

    # Phase 2: redistribute shortfall
    while shortfall > 0 and surplus_cats:
        extra_per = max(1, shortfall // len(surplus_cats))
        next_surplus = []
        for cat in surplus_cats:
            already = {id(r) for r in sampled[cat]}
            remaining = [r for r in buckets[cat] if id(r) not in already]
            take = min(extra_per, len(remaining), shortfall)
            if take > 0:
                sampled[cat].extend(random.sample(remaining, take))
                shortfall -= take
            if len(buckets[cat]) - len(sampled[cat]) > 0:
                next_surplus.append(cat)
        surplus_cats = next_surplus

    # Combine and shuffle
    result = []
    counts = {}
    for cat in ["Real", "Misinformation", "Satire", "Clickbait"]:
        items = sampled.get(cat, [])
        counts[cat] = len(items)
        result.extend(items)
    random.shuffle(result)

    # Write output CSV
    output_path = Path(output_csv_path)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in result:
            clean_row = {col: row.get(col, "") for col in CSV_COLUMNS}
            writer.writerow(clean_row)

    total = len(result)
    fake_pct_used = round(100.0 - real_pct, 2)
    return (
        f"Kappa sample generated!\n\n"
        f"Input: {input_csv_path}\n"
        f"Requested: {n} | Sampled: {total}\n\n"
        f"Distribution: Real {real_pct:.2f}% | Fake {fake_pct_used:.2f}%\n"
        f"Fake split: Misinfo {misinfo_pct:.2f}% | Satire {satire_pct:.2f}% | Clickbait {clickbait_pct:.2f}%\n\n"
        f"Breakdown:\n"
        f"  Real: {counts['Real']}\n"
        f"  Misinformation: {counts['Misinformation']}\n"
        f"  Satire: {counts['Satire']}\n"
        f"  Clickbait: {counts['Clickbait']}\n\n"
        f"Output: {output_csv_path}"
    )


def _compute_cohen_kappa(ratings_a, ratings_b, categories):
    """
    Compute Cohen's Kappa for two annotators.
    ratings_a, ratings_b: lists of category labels (same length).
    categories: the set of all possible category labels.
    Returns kappa value (float).
    """
    n = len(ratings_a)
    if n == 0:
        return 0.0

    cats = sorted(categories)
    cat_index = {c: i for i, c in enumerate(cats)}
    k = len(cats)

    # Build confusion matrix
    matrix = [[0] * k for _ in range(k)]
    for a, b in zip(ratings_a, ratings_b):
        if a in cat_index and b in cat_index:
            matrix[cat_index[a]][cat_index[b]] += 1

    # Observed agreement
    p_o = sum(matrix[i][i] for i in range(k)) / n

    # Expected agreement by chance
    p_e = 0.0
    for i in range(k):
        row_sum = sum(matrix[i][j] for j in range(k))
        col_sum = sum(matrix[j][i] for j in range(k))
        p_e += (row_sum * col_sum)
    p_e /= (n * n)

    if p_e == 1.0:
        return 1.0
    return (p_o - p_e) / (1.0 - p_e)


def _compute_fleiss_kappa(ratings_table, categories):
    """
    Compute Fleiss' Kappa for multiple annotators.
    ratings_table: list of dicts, each dict maps category -> count of raters who chose it.
    categories: list of all category labels.
    Returns kappa value (float).
    """
    n_subjects = len(ratings_table)
    if n_subjects == 0:
        return 0.0

    cats = sorted(categories)
    k = len(cats)

    # Number of raters per subject (should be the same for all)
    n_raters = sum(ratings_table[0].get(c, 0) for c in cats)
    if n_raters <= 1:
        return 0.0

    # Calculate P_i (agreement for each subject)
    P_i_list = []
    for subject in ratings_table:
        sum_sq = sum(subject.get(c, 0) ** 2 for c in cats)
        P_i = (sum_sq - n_raters) / (n_raters * (n_raters - 1))
        P_i_list.append(P_i)

    P_bar = sum(P_i_list) / n_subjects

    # Calculate p_j (proportion of all assignments to each category)
    total_assignments = n_subjects * n_raters
    p_j = {}
    for c in cats:
        p_j[c] = sum(subject.get(c, 0) for subject in ratings_table) / total_assignments

    P_e_bar = sum(pj ** 2 for pj in p_j.values())

    if P_e_bar == 1.0:
        return 1.0
    return (P_bar - P_e_bar) / (1.0 - P_e_bar)


def _calculate_kappa(kappa_csv_path, mode="cohen"):
    """
    Calculate inter-rater agreement from the relabeling_for_kappa.csv file.
    Computes agreement for both 'label' and 'multi_category' columns.

    mode: 'cohen' for Cohen's Kappa (exactly 2 annotators) or
          'fleiss' for Fleiss' Kappa (2+ annotators).

    Returns a formatted results string, or raises an error if data is incomplete.
    """
    csv_path = Path(kappa_csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Kappa CSV not found: {kappa_csv_path}")

    # Read all rows and discover annotator columns
    rows = []
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        for row in reader:
            rows.append(row)

    if not rows:
        raise ValueError("No records found in the kappa CSV.")

    # Find annotator names from column pattern: {name}_label
    annotator_names = []
    for h in headers:
        if h.endswith("_label") and h != "label":
            name = h[:-6]  # strip "_label"
            annotator_names.append(name)

    if not annotator_names:
        raise ValueError(
            "No annotator rating columns found.\n\n"
            "Annotators need to complete Re-label mode first.\n"
            "Expected columns like: AnnotatorName_label"
        )

    if mode == "cohen" and len(annotator_names) < 2:
        raise ValueError(
            f"Cohen's Kappa requires at least 2 annotators, "
            f"but found {len(annotator_names)}."
        )

    if mode == "fleiss" and len(annotator_names) < 2:
        raise ValueError(
            f"Fleiss' Kappa requires at least 2 annotators, "
            f"but found {len(annotator_names)}."
        )

    # Check for missing ratings and collect per-annotator missing info
    missing_info = []
    for name in annotator_names:
        label_col = f"{name}_label"
        multi_col = f"{name}_multi_category"
        missing_label_rows = []
        missing_multi_rows = []
        for i, row in enumerate(rows):
            label_val = (row.get(label_col) or "").strip()
            multi_val = (row.get(multi_col) or "").strip()
            if not label_val:
                missing_label_rows.append(i + 1)
            if not multi_val:
                missing_multi_rows.append(i + 1)
        
        if missing_label_rows:
            if len(missing_label_rows) <= 5:
                row_list = ", ".join(str(r) for r in missing_label_rows)
            else:
                row_list = ", ".join(str(r) for r in missing_label_rows[:5]) + f"... ({len(missing_label_rows)} total)"
            missing_info.append(f"  {name}: missing {len(missing_label_rows)} labels (rows: {row_list})")
            
        if missing_multi_rows:
            if len(missing_multi_rows) <= 5:
                row_list = ", ".join(str(r) for r in missing_multi_rows)
            else:
                row_list = ", ".join(str(r) for r in missing_multi_rows[:5]) + f"... ({len(missing_multi_rows)} total)"
            missing_info.append(f"  {name}: missing {len(missing_multi_rows)} multi-categories (rows: {row_list})")

    if missing_info:
        raise ValueError(
            "Some annotators have incomplete ratings.\n"
            "All records must be labeled before calculating Kappa.\n\n"
            + "\n".join(missing_info)
        )

    # Collect all unique categories for label and multi_category
    label_cats = set()
    multi_cats = set()
    for name in annotator_names:
        for row in rows:
            lv = (row.get(f"{name}_label") or "").strip()
            mv = (row.get(f"{name}_multi_category") or "").strip()
            if lv:
                label_cats.add(lv)
            if mv:
                multi_cats.add(mv)

    results = []
    results.append(f"Inter-Rater Reliability Results")
    results.append(f"Mode: {'Cohen (pairwise)' if mode == 'cohen' else 'Fleiss'}'s Kappa")
    results.append(f"Annotators ({len(annotator_names)}): {', '.join(annotator_names)}")
    results.append(f"Records: {len(rows)}")
    results.append("")

    if mode == "cohen":
        # Cohen's Kappa: pairwise for every pair of annotators
        from itertools import combinations
        pairs = list(combinations(annotator_names, 2))

        results.append(f"--- Label (Fake/Real) ---")
        label_kappas = []
        for a_name, b_name in pairs:
            a_labels = [(row.get(f"{a_name}_label") or "").strip() for row in rows]
            b_labels = [(row.get(f"{b_name}_label") or "").strip() for row in rows]
            k = _compute_cohen_kappa(a_labels, b_labels, label_cats)
            label_kappas.append(k)
            results.append(f"  {a_name} vs {b_name}: {k:.4f} ({_interpret_kappa(k)})")

        if len(pairs) > 1:
            avg_label = sum(label_kappas) / len(label_kappas)
            results.append(f"  Average: {avg_label:.4f} ({_interpret_kappa(avg_label)})")

        results.append("")
        results.append(f"--- Multi-Category ---")
        multi_kappas = []
        for a_name, b_name in pairs:
            a_multi = [(row.get(f"{a_name}_multi_category") or "").strip() for row in rows]
            b_multi = [(row.get(f"{b_name}_multi_category") or "").strip() for row in rows]
            k = _compute_cohen_kappa(a_multi, b_multi, multi_cats)
            multi_kappas.append(k)
            results.append(f"  {a_name} vs {b_name}: {k:.4f} ({_interpret_kappa(k)})")

        if len(pairs) > 1:
            avg_multi = sum(multi_kappas) / len(multi_kappas)
            results.append(f"  Average: {avg_multi:.4f} ({_interpret_kappa(avg_multi)})")

    else:
        # Fleiss' Kappa: 2+ annotators
        # Build ratings table for labels
        label_table = []
        for row in rows:
            counts = {c: 0 for c in label_cats}
            for name in annotator_names:
                val = (row.get(f"{name}_label") or "").strip()
                if val in counts:
                    counts[val] += 1
            label_table.append(counts)
        k_label = _compute_fleiss_kappa(label_table, label_cats)

        # Build ratings table for multi-category
        multi_table = []
        for row in rows:
            counts = {c: 0 for c in multi_cats}
            for name in annotator_names:
                val = (row.get(f"{name}_multi_category") or "").strip()
                if val in counts:
                    counts[val] += 1
            multi_table.append(counts)
        k_multi = _compute_fleiss_kappa(multi_table, multi_cats)

        results.append(f"--- Label (Fake/Real) ---")
        results.append(f"  Fleiss' Kappa: {k_label:.4f}")
        results.append(f"  Interpretation: {_interpret_kappa(k_label)}")
        results.append("")
        results.append(f"--- Multi-Category ---")
        results.append(f"  Fleiss' Kappa: {k_multi:.4f}")
        results.append(f"  Interpretation: {_interpret_kappa(k_multi)}")

    return "\n".join(results)


def _interpret_kappa(k):
    """Return a human-readable interpretation of a kappa score (Landis & Koch scale)."""
    if k < 0:
        return "Poor (less than chance agreement)"
    elif k < 0.21:
        return "Slight agreement"
    elif k < 0.41:
        return "Fair agreement"
    elif k < 0.61:
        return "Moderate agreement"
    elif k < 0.81:
        return "Substantial agreement"
    else:
        return "Almost perfect agreement"


# MAIN APPLICATION CONTAINER CLASS

class FlowFrame(ctk.CTkFrame):
    """
    A custom frame container that automatically wraps child widgets to the next line
    when they exceed the available horizontal width of the frame.
    """
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.bind("<Configure>", self._on_configure)

    def _arrange(self):
        width = self.winfo_width()
        if width <= 10:  # Skip layout calculation if frame is not fully initialized/drawn yet
            return
            
        rows = []
        current_row = []
        x = 0
        max_height = 0
        
        # Group child widgets into rows based on their required widths
        for child in self.winfo_children():
            cw = child.winfo_reqwidth()
            ch = child.winfo_reqheight()
            
            # Wrap to next row if this child overflows the current width
            if x + cw > width and current_row:
                rows.append((current_row, x - 10, max_height))  # Subtract 10 to account for trailing space
                current_row = []
                x = 0
                max_height = 0
                
            current_row.append((child, cw, ch))
            x += cw + 10  # Horizontal spacing between elements
            max_height = max(max_height, ch)
            
        if current_row:
            rows.append((current_row, x - 10, max_height))
            
        # Draw and position the rows and elements dynamically
        y = 0
        total_height = 0
        for row_items, row_width, row_height in rows:
            start_x = (width - row_width) // 2
            start_x = max(0, start_x)  # Prevent negative alignment coordinates
            
            x_offset = start_x
            for child, cw, ch in row_items:
                child.place(x=x_offset, y=y)
                x_offset += cw + 10
                
            y += row_height + 5  # Vertical spacing between rows
            total_height += row_height + 5
            
        if total_height > 0:
            total_height -= 5 # Remove trailing vertical spacing
            
        if total_height != self.winfo_reqheight() and total_height > 0:
            self.configure(height=total_height)

    def _on_configure(self, event=None):
        self._arrange()

class AnnotatorTool(ctk.CTk, dnd_base):
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

    # UI Construction Methods

    def _build_ui(self):
        """
        Creates and positions all widgets inside the application window.
        Uses a two-column desktop layout consisting of:
        - Top Bar: mode select buttons and filter indicators
        - Left Panel: heading, body text, and media upload zone
        - Right Panel: classification fields (authenticity, category, confidence, source)
        - Bottom Bar: navigation controls and action buttons
        """
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=18, pady=10)
        self._main_frame = main

        # Top Bar containing Mode Selector and main header label
        top_bar = ctk.CTkFrame(main, fg_color="transparent", height=38)
        top_bar.pack(fill="x", pady=(5, 2))
        top_bar.pack_propagate(False)

        self.mode_switcher = ctk.CTkSegmentedButton(
            top_bar, values=["📝 Annotate", "🔍 Review", "🔄 Re-label"],
            command=self._toggle_mode,
            font=ctk.CTkFont(size=12),
            selected_color="#1f6aa5", selected_hover_color="#144870",
            height=28, width=270
        )
        self.mode_switcher.set("📝 Annotate")
        self.mode_switcher.pack(side="left", padx=(0, 10))
        
        # Filter controls for Review mode
        self.filter_indicator = ctk.CTkLabel(top_bar, text="",
                                              font=ctk.CTkFont(size=12),
                                              text_color="#f39c12")
        
        self.filter_btn = ctk.CTkButton(top_bar, text="🔍 Filter", command=self._show_filter_popup,
                                         width=80, height=32,
                                         font=ctk.CTkFont(size=13),
                                         fg_color="#2d2d5e", hover_color="#3d3d7e",
                                         border_width=1, border_color="#555",
                                         corner_radius=6)

        # Scripts button - always visible in all modes, opens the script runner popup
        self.scripts_btn = ctk.CTkButton(top_bar, text="🛠 Scripts", command=self._show_scripts_popup,
                                          width=90, height=32,
                                          font=ctk.CTkFont(size=13),
                                          fg_color="#2d2d5e", hover_color="#3d3d7e",
                                          border_width=1, border_color="#555",
                                          corner_radius=6)
        self.scripts_btn.pack(side="right", padx=(4, 0))

        ctk.CTkLabel(top_bar, text="📰 Fake News Dataset Annotator",
                     font=ctk.CTkFont(size=22, weight="bold")).place(relx=0.5, rely=0.5, anchor="center")

        # Top stats cards area
        self.stats_frame = FlowFrame(main, fg_color="transparent")
        self.stats_frame.pack(fill="x", pady=(4, 2))

        # Secondary categories stats cards
        self.category_stats_frame = FlowFrame(main, fg_color="transparent")
        self.category_stats_frame.pack(fill="x", pady=(0, 6))

        # Bottom controls container
        self.bottom_bar = ctk.CTkFrame(main, fg_color="#1a1a2e", corner_radius=8,
                                        border_width=1, border_color="#333")
        self.bottom_bar.pack(side="bottom", fill="x", pady=(6, 0))
        self.bottom_bar.columnconfigure(0, weight=1, uniform="btm")
        self.bottom_bar.columnconfigure(1, weight=1, uniform="btm")

        # Left controls (Navigation)
        self.nav_frame = ctk.CTkFrame(self.bottom_bar, fg_color="transparent")

        self.prev_btn = ctk.CTkButton(self.nav_frame, text="← Previous",
                                       command=self._prev_record, width=100, height=32,
                                       font=ctk.CTkFont(size=12),
                                       fg_color="transparent", border_width=1,
                                       border_color="#555", hover_color="#333")
        self.prev_btn.pack(side="left", padx=(0, 10))

        # Page index / total counter block
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

        # Right controls (Save / Clear actions)
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

        # Two Column Main Area
        self.content_container = ctk.CTkFrame(main, fg_color="transparent")
        self.content_container.pack(fill="both", expand=True, pady=(4, 0))

        # Left Column containing input text area and drop targets
        self.left_col = ctk.CTkFrame(self.content_container, fg_color="transparent")

        # Heading entry field
        heading_header = self._section(self.left_col, "News Heading (optional)")
        self.heading_search_btn = ctk.CTkButton(
            heading_header,
            text="🔎 Search",
            command=self._open_heading_search,
            width=84,
            height=26,
            font=ctk.CTkFont(size=12),
            fg_color="#2d2d5e",
            hover_color="#3d3d7e",
            border_width=1,
            border_color="#555",
            corner_radius=6
        )
        self.heading_entry = ctk.CTkTextbox(self.left_col, height=55, font=ctk.CTkFont(size=13),
                                            border_width=1, border_color="#555", undo=True)
        self.heading_entry.pack(fill="x", padx=10, pady=(0, 6))
        self.heading_entry.bind("<KeyRelease>", self._update_heading_search_visibility)

        # Article text entry field
        self._section(self.left_col, "📝 News Text (required if no image)")
        self.text_box = ctk.CTkTextbox(self.left_col, height=120, font=ctk.CTkFont(size=13),
                                        border_width=1, border_color="#555", undo=True)
        self.text_box.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        # Upload / Pasting controls
        self._section(self.left_col, "🖼️ Images & Video (required if no text)")
        img_btn_frame = ctk.CTkFrame(self.left_col, fg_color="transparent")
        img_btn_frame.pack(fill="x", padx=10, pady=(0, 4))

        ctk.CTkButton(img_btn_frame, text="📁 Browse", command=self._browse_media,
                       width=100, height=26, font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(img_btn_frame, text="📋 Paste", command=self._paste_image,
                       width=100, height=26, font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(img_btn_frame, text="❌ Remove All", command=self._remove_all_images,
                       width=110, height=26, font=ctk.CTkFont(size=12),
                       fg_color="#e74c3c", hover_color="#c0392b").pack(side="left")

        # Main drop target frame for Drag and Drop operations
        self.drop_frame = ctk.CTkFrame(self.left_col, height=80, border_width=2,
                                        border_color="#666", fg_color="#1a1a2e")
        self.drop_frame.pack(fill="both", padx=10, pady=(4, 6))

        self.drop_label = ctk.CTkLabel(self.drop_frame,
                                        text="📥 Drag & Drop image(s) / video here\nor use Browse / Paste buttons above",
                                        font=ctk.CTkFont(size=13), text_color="#888")
        self.drop_label.pack(expand=True, fill="both", pady=15)

        # Right Column containing categorical selectors and validation constraints
        self.right_col = ctk.CTkFrame(self.content_container, fg_color="#1a1a2e",
                                       corner_radius=10, border_width=1, border_color="#333")

        # Annotator Name
        self._section(self.right_col, "Annotator name *")
        self.annotator_entry = ctk.CTkEntry(self.right_col, placeholder_text="Your name", height=32)
        self.annotator_entry.pack(fill="x", padx=12, pady=(0, 8))

        saved_name = load_config()
        if saved_name:
            self.annotator_entry.insert(0, saved_name)

        # Authenticity Selectors
        self._section(self.right_col, "News Authenticity *")
        label_frame = ctk.CTkFrame(self.right_col, fg_color="transparent")
        label_frame.pack(fill="x", padx=12, pady=(0, 6))
        label_frame.grid_columnconfigure((0, 1), weight=1, uniform="toggles")

        self.label_var = ctk.StringVar(value="")

        # Fake authenticity option
        self.fake_toggle_btn = ctk.CTkButton(
            label_frame, text="❌  FAKE",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40, corner_radius=8,
            fg_color="transparent", hover_color="#4a1a1a",
            border_width=2, border_color="#555",
            text_color="#888",
            command=lambda: self._set_label("Fake")
        )
        self.fake_toggle_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        # Real authenticity option
        self.real_toggle_btn = ctk.CTkButton(
            label_frame, text="✅  REAL",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40, corner_radius=8,
            fg_color="transparent", hover_color="#1a4a1a",
            border_width=2, border_color="#555",
            text_color="#888",
            command=lambda: self._set_label("Real")
        )
        self.real_toggle_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # Multi-category selection subframe (displayed for Fake news only)
        self.multi_cat_frame = ctk.CTkFrame(self.right_col, fg_color="#222244",
                                             corner_radius=8, border_width=1,
                                             border_color="#444")
        self.multi_cat_var = ctk.StringVar(value="")

        # Done review badge container for kappa mode
        self.done_indicator_frame = ctk.CTkFrame(self.right_col, fg_color="transparent")
        self.done_indicator_frame.bind("<Configure>", self._on_done_indicator_configure)
        
        # Preload the reviewed badge image for the Done popup
        self.reviewed_badge_img = None
        try:
            r_img = Image.open(ASSETS_DIR / "reviewed_badge.png")
            self.reviewed_badge_img = ctk.CTkImage(light_image=r_img, dark_image=r_img, size=(220, 220))
        except Exception: pass

        self.done_label = ctk.CTkLabel(self.done_indicator_frame, text="")
        self.done_label.pack(expand=True, fill="both", pady=10)

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
        
        self.radio_satire = ctk.CTkRadioButton(
            mc_radios, text="Satire", variable=self.multi_cat_var,
            value="Satire", font=ctk.CTkFont(size=12),
            fg_color="#9b59b6", hover_color="#8e44ad")
        self.radio_satire.pack(side="left", padx=(0, 12))
        
        self.radio_clickbait = ctk.CTkRadioButton(
            mc_radios, text="Clickbait", variable=self.multi_cat_var,
            value="Clickbait", font=ctk.CTkFont(size=12),
            fg_color="#e74c3c", hover_color="#c0392b")
        self.radio_clickbait.pack(side="left")

        # Main news and platform category selectors
        cat_row_header = ctk.CTkFrame(self.right_col, fg_color="transparent")
        cat_row_header.pack(fill="x", padx=10, pady=(10, 3))
        cat_row_header.columnconfigure(0, weight=1, uniform="catcol")
        cat_row_header.columnconfigure(1, weight=1, uniform="catcol")

        nc_lbl_frame = ctk.CTkFrame(cat_row_header, fg_color="transparent")
        nc_lbl_frame.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(nc_lbl_frame, text="News Category",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        ctk.CTkLabel(nc_lbl_frame, text=" *",
                     font=ctk.CTkFont(size=15, weight="bold"), text_color="#e74c3c").pack(side="left")

        sc_lbl_frame = ctk.CTkFrame(cat_row_header, fg_color="transparent")
        sc_lbl_frame.grid(row=0, column=1, sticky="w", padx=(8, 0))
        ctk.CTkLabel(sc_lbl_frame, text="Source Category",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        ctk.CTkLabel(sc_lbl_frame, text=" *",
                     font=ctk.CTkFont(size=15, weight="bold"), text_color="#e74c3c").pack(side="left")

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

        # Confidence rating
        self._section(self.right_col, "Confidence (%)")
        self.confidence_entry = ctk.CTkEntry(self.right_col, placeholder_text="100", height=32, justify="center")
        self.confidence_entry.pack(fill="x", padx=12, pady=(0, 8))
        self.confidence_entry.insert(0, "100")

        # News Source link
        self._section(self.right_col, "Source Link")
        self.source_entry = ctk.CTkEntry(self.right_col, placeholder_text="Paste URL or link here", height=32)
        self.source_entry.pack(fill="x", padx=12, pady=(0, 8))

        # Internal Annotator notes textbox
        self._section(self.right_col, "Additional Notes")
        notes_hint = ctk.CTkLabel(self.right_col, text="For annotator use only — e.g., personal notes or remarks outside of classification",
                                   font=ctk.CTkFont(size=10, slant="italic"), text_color="#666")
        notes_hint.pack(fill="x", padx=12, pady=(0, 2))
        self.notes_entry = ctk.CTkTextbox(self.right_col, font=ctk.CTkFont(size=13),
                                           border_width=1, border_color="#555", undo=True)
        self.notes_entry.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        # Establish base columns
        self._arrange_columns()
        self.content_container.bind("<Configure>", self._on_content_resize)

        class DummyLabel:
            def configure(self, *args, **kwargs): pass
        self.status_label = DummyLabel()

    def _section(self, parent, text):
        """
        Creates a bold text header to separate sections inside the control panel.
        Displays trailing '*' symbols in standard red to denote required fields.
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

        return frame

    def _inline_label(self, parent, text, width=140):
        """
        Helper to construct fixed-width label wrappers for horizontal layout alignment.
        """
        frame = ctk.CTkFrame(parent, width=width, height=36, fg_color="transparent")
        frame.pack_propagate(False)
        frame.pack(side="left", padx=(0, 10))
        
        if text.endswith("*"):
            main_text = text[:-1].rstrip()
            ctk.CTkLabel(frame, text=main_text, font=ctk.CTkFont(size=13)).pack(side="left")
            ctk.CTkLabel(frame, text=" *", font=ctk.CTkFont(size=13, weight="bold"), text_color="#e74c3c").pack(side="left")
        else:
            ctk.CTkLabel(frame, text=text, font=ctk.CTkFont(size=13)).pack(side="left")

    # Column Grid Resizing

    def _arrange_columns(self):
        """
        Fixes the content container to use a balanced two-column grid.
        """
        self.content_container.columnconfigure(0, weight=1, uniform="col")
        self.content_container.columnconfigure(1, weight=1, uniform="col")
        self.content_container.rowconfigure(0, weight=1)

        self.left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.right_col.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

    def _on_content_resize(self, event=None):
        pass

    def _on_done_indicator_configure(self, event):
        """
        Handler to scale the reviewed check badge dynamically with window resizing constraints.
        """
        if not self.reviewed_badge_img:
            return
        w = event.width
        h = event.height
        size = min(w - 24, h - 30, 220)
        size = max(100, size)
        if self.reviewed_badge_img.cget("size") != (size, size):
            self.reviewed_badge_img.configure(size=(size, size))

    # Event Handlers for UI Elements

    def _set_label(self, value):
        """
        Sets the active label variable (Fake / Real) and updates button highlighting.
        """
        self.label_var.set(value)
        self._update_label_toggles()
        self._on_label_change()

    def _update_label_toggles(self):
        """
        Dynamically applies color themes to authenticity select toggles when selected.
        Red highlighting is used for Fake authenticity, green for Real authenticity.
        """
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
            self.fake_toggle_btn.configure(
                fg_color="transparent", border_color="#555",
                text_color="#888"
            )
            self.real_toggle_btn.configure(
                fg_color="transparent", border_color="#555",
                text_color="#888"
            )

    def _on_label_change(self):
        """
        Displays the multi-category type selector frame if Fake is selected.
        Hides the category type frame and resets options if Real is selected.
        """
        if self.label_var.get() == "Fake":
            if self.current_mode == "relabel":
                self.multi_cat_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8),
                                           after=self.fake_toggle_btn.master)
            else:
                self.multi_cat_frame.pack(fill="x", expand=False, padx=12, pady=(0, 8),
                                           after=self.fake_toggle_btn.master)
        else:
            self.multi_cat_frame.pack_forget()
            self.multi_cat_var.set("")
        self._update_label_toggles()

    def _on_annotator_name_change(self):
        """
        Saves user credentials to local settings files and refreshes dashboard statistics when modified.
        """
        name = self.annotator_entry.get().strip()
        if self.current_mode == "annotate":
            save_config(name)
        elif self.current_mode == "relabel":
            save_config(name)
            self._update_kappa_stats()

    def _setup_shortcuts(self):
        """
        Registers productivity shortcuts for Review and Re-label modes.
        """
        for sequence in ("<Control-s>", "<Control-S>", "<Command-s>", "<Command-S>"):
            self.bind_all(sequence, self._shortcut_save_and_next)

        for sequence in ("<Control-d>", "<Control-D>", "<Command-d>", "<Command-D>"):
            self.bind_all(sequence, self._shortcut_delete_record)

        self.bind_all("<Left>", self._shortcut_prev_record)
        self.bind_all("<Right>", self._shortcut_next_record)

    def _shortcut_event_is_for_main_window(self, event=None):
        """
        Returns False when focus is inside a child popup instead of the main app window.
        """
        try:
            if event is not None and hasattr(event, "widget"):
                return str(event.widget.winfo_toplevel()) == str(self)

            focused = self.focus_get()
            if focused is None:
                return True
            return str(focused.winfo_toplevel()) == str(self)
        except tk.TclError:
            return False

    def _focused_widget_is_text_input(self):
        """
        Detects focused text entry widgets so arrow shortcuts do not steal cursor movement.
        """
        try:
            focused = self.focus_get()
            if focused is None:
                return False
            widget_class = (focused.winfo_class() or "").lower()
            return "entry" in widget_class or "text" in widget_class or "spinbox" in widget_class
        except tk.TclError:
            return False

    def _shortcut_save_and_next(self, event=None):
        """
        Saves the current Review/Re-label decision and moves to the next record when possible.
        """
        if not self._shortcut_event_is_for_main_window(event):
            return None

        if self.current_mode == "review":
            record_id = ""
            if self.dataset_records and 0 <= self.current_review_index < len(self.dataset_records):
                record_id = self.dataset_records[self.current_review_index].get("id") or ""

            if self._update_entry(show_success=False):
                active_id = ""
                if self.dataset_records and 0 <= self.current_review_index < len(self.dataset_records):
                    active_id = self.dataset_records[self.current_review_index].get("id") or ""

                if record_id and active_id and active_id != record_id:
                    return "break"

                if self.current_review_index < len(self.dataset_records) - 1:
                    self._next_record()
                else:
                    self.status_label.configure(text="Record updated. You are at the last record.", text_color="#2ecc71")
            return "break"

        if self.current_mode == "relabel":
            self._save_kappa_decision(auto_advance=True)
            return "break"

        return None

    def _shortcut_prev_record(self, event=None):
        """
        Navigates to the previous record from the keyboard in Review/Re-label modes.
        """
        if not self._shortcut_event_is_for_main_window(event) or self._focused_widget_is_text_input():
            return None

        if self.current_mode in ("review", "relabel"):
            self._prev_record()
            return "break"

        return None

    def _shortcut_next_record(self, event=None):
        """
        Navigates to the next record from the keyboard in Review/Re-label modes.
        """
        if not self._shortcut_event_is_for_main_window(event) or self._focused_widget_is_text_input():
            return None

        if self.current_mode in ("review", "relabel"):
            self._next_record()
            return "break"

        return None

    def _shortcut_delete_record(self, event=None):
        """
        Deletes the active record from Review mode via Cmd/Ctrl+D.
        """
        if not self._shortcut_event_is_for_main_window(event):
            return None

        if self.current_mode == "review":
            self._delete_entry()
            return "break"

        return None

    def _get_heading_text(self):
        """
        Returns the current heading textbox content.
        """
        return self.heading_entry.get("1.0", "end-1c").strip()

    def _update_heading_search_visibility(self, event=None):
        """
        Shows the Google search button only in Review/Re-label modes when a heading exists.
        """
        if not hasattr(self, "heading_search_btn"):
            return

        should_show = self.current_mode in ("review", "relabel") and bool(self._get_heading_text())
        is_visible = bool(self.heading_search_btn.winfo_manager())

        if should_show and not is_visible:
            self.heading_search_btn.pack(side="right", padx=(8, 0))
        elif not should_show and is_visible:
            self.heading_search_btn.pack_forget()

    def _open_heading_search(self):
        """
        Opens a Google search for the current heading in the default system browser.
        """
        heading = self._get_heading_text()
        if not heading:
            self._update_heading_search_visibility()
            return

        webbrowser.open(f"https://www.google.com/search?q={quote_plus(heading)}", new=2)

    # Drag and Drop Implementation

    def _setup_dnd(self):
        """
        Registers drop bindings for the media zone if the tkinterdnd library is loaded.
        """
        global dnd_available
        if dnd_available:
            try:
                self.drop_frame.drop_target_register(DND_FILES)
                self.drop_frame.dnd_bind('<<Drop>>', self._on_drop)
            except Exception as e:
                print(f"[WARNING] Failed to register drop target: {e}")
                self.drop_label.configure(text="Drag & Drop not available\n(Use Browse or Paste instead)")
                dnd_available = False
        else:
            self.drop_label.configure(text="Drag & Drop not available\n(Use Browse or Paste instead)")

    def _on_drop(self, event):
        """
        Processes file paths dropped into the drag-and-drop area.
        Parses raw dropped string data to handle spaces in paths, which are typical 
        on macOS/Windows environments and usually wrapped in curly braces by the Tcl handler.
        It then filters the resolved paths and registers eligible image/video media.
        """
        raw = event.data.strip()
        paths = []
        
        # Regex separates paths, handling space characters enclosed in braces
        import re
        for match in re.finditer(r'\{([^{}]+)\}|(\S+)', raw):
            p = match.group(1) or match.group(2)
            if p:
                paths.append(p.strip())

        # Distribute file paths based on extension matches
        added = 0
        for p in paths:
            path = Path(p)
            if path.suffix.lower() in IMAGE_EXTENSIONS:
                self._add_image_from_path(path)
                added += 1
            elif path.suffix.lower() in VIDEO_EXTENSIONS:
                self._add_video_from_path(path)
                added += 1
                
        if added == 0:
            messagebox.showwarning("Invalid File", "Please drop image or video files only.")

    # Media Operations and Attachments

    def _browse_media(self):
        """
        Triggers a native file browser dialog configured with extensions for images and videos.
        Dispatches selected items to their respective image or video handler functions.
        """
        ftypes = [
            ("All Media", " ".join(f"*{e}" for e in IMAGE_EXTENSIONS + VIDEO_EXTENSIONS)),
            ("Image files", " ".join(f"*{e}" for e in IMAGE_EXTENSIONS)),
            ("Video files", " ".join(f"*{e}" for e in VIDEO_EXTENSIONS))
        ]
        paths = filedialog.askopenfilenames(title="Select Media", filetypes=ftypes)
        for path in paths:
            p = Path(path)
            if p.suffix.lower() in IMAGE_EXTENSIONS:
                self._add_image_from_path(p)
            elif p.suffix.lower() in VIDEO_EXTENSIONS:
                self._add_video_from_path(p)

    def _paste_image(self):
        """
        Retrieves clipboard contents. Supports both raw raster screenshots (as PIL Image objects)
        and file lists (where files are copied directly in Explorer or Finder).
        Displays a notification if no compatible content is discovered.
        """
        try:
            img = ImageGrab.grabclipboard()
            if img is None:
                messagebox.showinfo("No Image", "No image found in clipboard.")
                return
            if isinstance(img, list):
                # User copied file paths directly
                added = False
                for f in img:
                    if Path(f).suffix.lower() in IMAGE_EXTENSIONS:
                        self._add_image_from_path(Path(f))
                        added = True
                if not added:
                    messagebox.showinfo("No Image", "No image file found in clipboard.")
                return
            # Raw clipboard raster data
            self.image_list.append((None, img))
            self._refresh_previews()
            self.status_label.configure(text="Image pasted from clipboard", text_color="#2ecc71")
        except Exception as e:
            messagebox.showerror("Error", f"Could not paste image: {e}")

    def _add_image_from_path(self, path: Path):
        """
        Performs structural checks on image files from path. Verifies that the file suffix
        matches eligible types and confirms the file is readable by attempting to initialize PIL.
        Stores path as a reference tuple and triggers preview updates.
        """
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            messagebox.showwarning("Invalid File", "Please select an image file only.")
            return
        try:
            Image.open(path)  
            self.image_list.append((path, None))
            self._refresh_previews()
            self.status_label.configure(text=f"Image added: {path.name}", text_color="#2ecc71")
        except Exception as e:
            messagebox.showerror("Error", f"Could not open image: {e}")

    def _add_video_from_path(self, path: Path):
        """
        Validates and registers a video file. Only one video may be attached to a dataset record.
        """
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            messagebox.showwarning("Invalid File", "Please select a video file only.")
            return
        if self.video_path is not None:
            messagebox.showwarning("Limit Reached", "Only one video can be inserted per entry.")
            return
        self.video_path = path
        self._refresh_previews()
        self.status_label.configure(text=f"Video added: {path.name}", text_color="#2ecc71")

    def _refresh_previews(self):
        """
        Redraws the layout container for the drop frame.
        When empty, displays drag instruction instructions.
        When populated, compiles a horizontal grid listing all images, video attachments,
        and unresolved missing-file cards (referenced in CSV but absent locally).
        Stores references to CTkImage properties in self.preview_photos to shield objects from GC.
        """
        for widget in self.drop_frame.winfo_children():
            widget.destroy()
        self.preview_photos.clear()

        count = len(self.image_list) + (1 if self.video_path else 0)
        missing_count = len(self.missing_media) if hasattr(self, 'missing_media') else 0
        total_display = count + missing_count

        if total_display == 0:
            self.drop_frame.configure(height=100)
            self.drop_label = ctk.CTkLabel(self.drop_frame,
                                            text="📥 Drag & Drop image(s) here\nor use Browse / Paste buttons above",
                                            font=ctk.CTkFont(size=14), text_color="#888")
            self.drop_label.pack(expand=True, fill="both", pady=20)
            return

        self.drop_frame.configure(height=0)

        count_text = f"{count} media item(s) selected"
        if missing_count > 0:
            count_text += f"  •  ⚠️ {missing_count} file(s) missing"
        count_color = "#e74c3c" if missing_count > 0 and count == 0 else "#2ecc71"
        ctk.CTkLabel(self.drop_frame,
                     text=count_text,
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=count_color).pack(pady=(8, 4))

        grid_frame = ctk.CTkFrame(self.drop_frame, fg_color="transparent")
        grid_frame.pack(fill="x", padx=8, pady=(0, 8))

        thumb_size = (100, 80)
        cols = 5

        # Render preview thumbnails for attached images
        for i, (path, pil_img) in enumerate(self.image_list):
            try:
                if path:
                    img = Image.open(path)
                else:
                    img = pil_img.copy()
                img.thumbnail(thumb_size)
                ctk_photo = ctk.CTkImage(light_image=img, dark_image=img,
                                         size=(img.width, img.height))
                self.preview_photos.append(ctk_photo)  

                frame = ctk.CTkFrame(grid_frame, fg_color="#222240",
                                      corner_radius=6)
                frame.grid(row=i // cols, column=i % cols, padx=4, pady=4)

                lbl = ctk.CTkLabel(frame, image=ctk_photo, text="", cursor="hand2")
                lbl.pack(padx=4, pady=(4, 0))
                lbl.bind("<Button-1>", lambda e, idx=i: self._show_image_popup(idx))

                name = path.name if path else f"clipboard_{i+1}.png"
                ctk.CTkLabel(frame, text=name[:18], font=ctk.CTkFont(size=9),
                             text_color="#aaa").pack(pady=(0, 1))

                if self.current_mode in ("review", "relabel"):
                    ctk.CTkLabel(frame, text="🔍 Click to enlarge",
                                 font=ctk.CTkFont(size=9), text_color="#666").pack(pady=(0, 1))

                if self.current_mode != "relabel":
                    rm_btn = ctk.CTkButton(frame, text="x", width=26, height=20,
                                            font=ctk.CTkFont(size=10),
                                            fg_color="#e74c3c", hover_color="#c0392b",
                                            command=lambda idx=i: self._remove_image(idx))
                    rm_btn.pack(pady=(0, 4))
            except Exception:
                pass

        # Render video icon card if present
        if self.video_path:
            i = len(self.image_list)
            frame = ctk.CTkFrame(grid_frame, fg_color="#402222", corner_radius=6)
            frame.grid(row=i // cols, column=i % cols, padx=4, pady=4)
            
            lbl = ctk.CTkLabel(frame, text="🎬\nVideo", font=ctk.CTkFont(size=24), width=100, height=80, cursor="hand2")
            lbl.pack(padx=4, pady=(4, 0))
            lbl.bind("<Button-1>", lambda e: self._play_video())
            
            name = self.video_path.name
            ctk.CTkLabel(frame, text=name[:18], font=ctk.CTkFont(size=9), text_color="#aaa").pack(pady=(0, 1))
            
            if self.current_mode in ("review", "relabel"):
                ctk.CTkLabel(frame, text="🔍 Click to play", font=ctk.CTkFont(size=9), text_color="#666").pack(pady=(0, 1))
                
            if self.current_mode != "relabel":
                rm_btn = ctk.CTkButton(frame, text="x", width=26, height=20, font=ctk.CTkFont(size=10),
                                        fg_color="#e74c3c", hover_color="#c0392b", command=self._remove_video)
                rm_btn.pack(pady=(0, 4))

        # Render warning panels for missing media references
        if hasattr(self, 'missing_media') and self.missing_media:
            next_idx = len(self.image_list) + (1 if self.video_path else 0)
            for j, (media_type, rel_path) in enumerate(self.missing_media):
                idx = next_idx + j
                frame = ctk.CTkFrame(grid_frame, fg_color="#3a1a1a",
                                      corner_radius=6, border_width=2,
                                      border_color="#e74c3c")
                frame.grid(row=idx // cols, column=idx % cols, padx=4, pady=4)

                icon = "🖼️" if media_type == "image" else "🎬"
                ctk.CTkLabel(frame, text=f"⚠️ {icon}",
                             font=ctk.CTkFont(size=20),
                             width=100, height=50).pack(padx=4, pady=(4, 0))

                ctk.CTkLabel(frame, text="FILE MISSING",
                             font=ctk.CTkFont(size=9, weight="bold"),
                             text_color="#e74c3c").pack(pady=(0, 1))

                filename = Path(rel_path).name if rel_path else "unknown"
                ctk.CTkLabel(frame, text=filename[:20],
                             font=ctk.CTkFont(size=8),
                             text_color="#999").pack(pady=(0, 4))

    def _show_image_popup(self, index):
        """
        Creates a dedicated modal-style window to show a high-resolution display of the selected image.
        Resizes the target image proportionally to fit inside a maximum threshold of 80% screen dimensions.
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

        popup = ctk.CTkToplevel(self)
        popup.title("Image Viewer")
        popup.configure(fg_color="#111")
        popup.attributes("-topmost", True)

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        max_w = int(screen_w * 0.8)
        max_h = int(screen_h * 0.8)
        img.thumbnail((max_w, max_h), Image.LANCZOS)

        popup.geometry(f"{img.width + 40}x{img.height + 80}")

        ctk_photo = ctk.CTkImage(light_image=img, dark_image=img,
                                  size=(img.width, img.height))
        popup._photo_ref = ctk_photo

        lbl = ctk.CTkLabel(popup, image=ctk_photo, text="")
        lbl.pack(expand=True, fill="both", padx=10, pady=(10, 5))

        name = path.name if path else f"clipboard_{index+1}.png"
        ctk.CTkLabel(popup, text=name, font=ctk.CTkFont(size=12),
                     text_color="#aaa").pack(pady=(0, 5))

        ctk.CTkButton(popup, text="Close", width=100, height=30,
                      command=popup.destroy).pack(pady=(0, 10))

    def _play_video(self):
        if not self.video_path: return
        path_str = str(self.video_path)
        try:
            if platform.system() == "Darwin":
                subprocess.call(('open', path_str))
            elif platform.system() == "Windows":
                os.startfile(path_str)
            else:
                subprocess.call(('xdg-open', path_str))
        except Exception as e:
            messagebox.showerror("Error", f"Could not play video: {e}")

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

    def _remove_video(self):
        self.video_path = None
        self._refresh_previews()
        self.status_label.configure(text="Video removed", text_color="#888")

    def _remove_all_images(self):
        """Remove all images and video from the entry."""
        self.image_list.clear()
        self.video_path = None
        self._refresh_previews()
        self.status_label.configure(text="All media removed", text_color="#888")

    # Record Persistence and Initialization

    def _save_entry(self):
        """
        Validates input fields, processes attached media files, and appends the annotated record
        to the local CSV dataset.
        
        The save workflow consists of:
        1. Extracting values from input entries.
        2. Enforcing structural validations (checking for name, category, source category, 
           label selection, and requiring either text or media).
        3. Warning users about short text inputs (under 10 words).
        4. Storing attachments inside images/ and videos/ subfolders using structured filenames 
           conforming to naming templates.
        5. Appending a standardized row to dataset.csv, writing the header first if the file is new.
        6. Preserving the annotator's name in configuration files and resetting fields.
        """
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
        has_media = has_image or (self.video_path is not None)

        # Enforce validation rules
        errors = []
        if not annotator:
            errors.append("Annotator name is required.")
        if not label:
            errors.append("Label (Fake/Real) must be selected.")
        if label == "Fake" and not multi_cat:
            errors.append("Fake News Type (Misinformation/Satire/Clickbait) must be selected.")
        if not category:
            errors.append("News Category is required.")
        if not source_category:
            errors.append("Source Category is required.")
        if not text and not has_media:
            errors.append("At least one of Text, Image, or Video must be provided.")

        # Ensure confidence ratings represent valid integer values between 0 and 100
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

        # Automatically map Real news classification subtype to Real
        if label == "Real":
            multi_cat = "Real"

        # Present warning confirmation if textual content is short
        if text and len(text.split()) < 10:
            proceed = messagebox.askyesno(
                "Short Text Warning",
                f"The text has only {len(text.split())} word(s). Are you sure you want to save?"
            )
            if not proceed:
                return

        # Generate unique database entry ID
        entry_id = generate_id()
        sanitized_annotator = sanitize_name(annotator)
        image_rel_paths = []

        try:
            # Transfer images to images directory using template patterns
            if has_image:
                for path, pil_img in self.image_list:
                    img_count = get_image_count() + 1
    
                    if path:
                        ext = path.suffix.lower()
                    else:
                        ext = ".png"
    
                    img_filename = f"{label}_{img_count:05d}_{entry_id}_{sanitized_annotator}{ext}"
                    img_dest = IMAGES_DIR / img_filename
    
                    if path:
                        shutil.copy2(path, img_dest)
                    else:
                        src_img = pil_img
                        # JPEGs do not support transparency layers; drop alpha if copying to JPEG
                        if src_img.mode == "RGBA" and ext in (".jpg", ".jpeg"):
                            src_img = src_img.convert("RGB")
                        src_img.save(img_dest)
    
                    image_rel_paths.append(f"images/{img_filename}")
    
            image_path_str = ";".join(image_rel_paths)
            
            # Transfer video files if registered
            video_rel_path = ""
            if self.video_path:
                vid_count = get_video_count() + 1
                ext = self.video_path.suffix.lower()
                vid_filename = f"{label}_{vid_count:05d}_{entry_id}_{sanitized_annotator}{ext}"
                vid_dest = VIDEOS_DIR / vid_filename
                shutil.copy2(self.video_path, vid_dest)
                video_rel_path = f"videos/{vid_filename}"
    
            # Open the CSV file and write data, initializing headers if file is empty
            file_has_content = CSV_PATH.exists() and CSV_PATH.stat().st_size > 0
            with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
                if not file_has_content:
                    writer.writeheader()
                writer.writerow({
                    "id": entry_id,
                    "heading": heading,
                    "text": text,
                    "image_path": image_path_str,
                    "video_path": video_rel_path,
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
            messagebox.showerror("Save Error", f"Failed to save data. Please check if the dataset file is currently locked.\n\nError: {e}")
            return

        save_config(annotator)
        self.status_label.configure(text=f"Entry saved successfully!", text_color="#2ecc71")
        self._update_stats()
        self._clear_fields()
        messagebox.showinfo("Save Complete", f"Entry saved successfully!\nID: {entry_id}")

    def _clear_fields(self):
        """
        Resets input controllers to their default values, skipping the annotator name.
        Hides context-dependent panels and clears attachments from preview frames.
        """
        self.text_box.delete("1.0", "end")       
        self.heading_entry.delete("1.0", "end")       
        self.source_entry.delete(0, "end")         
        self.notes_entry.delete("0.0", "end")      
        self.label_var.set("")                      
        self._update_label_toggles()                 
        self.category_var.set("")                   
        self.source_cat_var.set("")                  
        self.multi_cat_var.set("")                   
        self.multi_cat_frame.pack_forget()           
        self._remove_all_images()                   
        self.confidence_entry.delete(0, "end")      
        self.confidence_entry.insert(0, "100")      
        self._update_heading_search_visibility()

    def _clear_all(self):
        """
        Clears workspace fields. Maintains annotator identifiers for productivity.
        """
        self._clear_fields()
        self.status_label.configure(text="All fields cleared", text_color="#888")

    def _has_unsaved_annotate_work(self):
        """
        Verifies if input controls in Annotate mode contain modifications relative to
        an empty form.
        """
        if self.current_mode != "annotate":
            return False
        
        if self.label_var.get() != "": return True
        if self.heading_entry.get("1.0", "end-1c").strip() != "": return True
        if self.text_box.get("1.0", "end-1c").strip() != "": return True
        if self.source_entry.get().strip() != "": return True
        if self.source_cat_var.get() != "": return True
        if self.category_var.get() != "": return True
        if self.multi_cat_var.get() != "": return True
        if self.confidence_entry.get().strip() not in ("", "100"): return True
        if self.notes_entry.get("0.0", "end-1c").strip() != "": return True
        if len(self.image_list) > 0: return True
        if self.video_path is not None: return True
        
        return False

    def _on_closing(self):
        """
        Intercepts closure signals. Prompts validation alerts depending on active work modes
        to shield annotators from unsaved changes.
        """
        if self.current_mode == "review":
            if not self._check_unsaved_changes():
                return
        elif self.current_mode == "relabel":
            if not self._check_unsaved_kappa_changes():
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
        """
        Filters the full dataset based on advanced criteria selected in the filter popup.
        
        This method processes the in-memory master list of records (all_dataset_records)
        and applies active filter parameters such as labels, sub-types, categories, source platforms,
        annotator names, content types (text/image/video combinations), the presence of notes,
        and confidence intervals.
        
        Args:
            keep_index: If True, preserves the current record review index. If False, or if
                        the current index is out of bounds after filtering, resets the index to 0.
        """
        if self.current_mode != "review":
            return

        filt = self.advanced_filter

        # If no filter criteria are active, restore the full dataset list
        if not filt:
            self.dataset_records = list(self.all_dataset_records)
        else:
            filtered = list(self.all_dataset_records)

            # Filter records by active authenticity labels (Fake / Real)
            sel_labels = filt.get("labels")
            if sel_labels:
                filtered = [r for r in filtered if (r.get("label") or "") in sel_labels]

            # Filter records by fake news classification sub-types
            sel_types = filt.get("types")
            if sel_types:
                filtered = [r for r in filtered if (r.get("multi_category") or "") in sel_types]

            # Filter records by topic categories (e.g. Politics, Sports)
            sel_cats = filt.get("categories")
            if sel_cats:
                filtered = [r for r in filtered if (r.get("category") or "") in sel_cats]

            # Filter records by news source categories (e.g. newspaper, social media)
            sel_src_cats = filt.get("source_categories")
            if sel_src_cats:
                filtered = [r for r in filtered if (r.get("source_category") or "") in sel_src_cats]

            # Filter records by the name of the annotator who saved them
            sel_annotators = filt.get("annotators")
            if sel_annotators:
                filtered = [r for r in filtered if (r.get("annotator") or "") in sel_annotators]

            # Filter records by their structural content type (e.g. text only, text & media)
            sel_content_types = filt.get("content_types")
            if sel_content_types:
                def _content_type(r):
                    has_text = bool((r.get("text") or "").strip())
                    has_image = bool((r.get("image_path") or "").strip())
                    has_video = bool((r.get("video_path") or "").strip())
                    has_media = has_image or has_video
                    if has_text and has_media:
                        return "Text & Image"
                    elif has_media:
                        return "Image Only"
                    elif has_text:
                        return "Text Only"
                    return ""
                
                # Check for video attachments separately from standard text/image breakdowns
                check_has_video = "Has Video" in sel_content_types
                other_types = sel_content_types - {"Has Video"}
                if other_types and check_has_video:
                    filtered = [r for r in filtered if _content_type(r) in other_types or bool((r.get("video_path") or "").strip())]
                elif check_has_video:
                    filtered = [r for r in filtered if bool((r.get("video_path") or "").strip())]
                else:
                    filtered = [r for r in filtered if _content_type(r) in other_types]

            # Filter records to only show those containing internal annotator notes
            if filt.get("has_notes"):
                filtered = [r for r in filtered if (r.get("additional_notes") or "").strip()]

            # Filter records by annotation confidence interval limits
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

        # Resolve index indexing boundaries for review navigation
        if not keep_index:
            self.current_review_index = 0
        elif self.current_review_index >= len(self.dataset_records):
            self.current_review_index = max(0, len(self.dataset_records) - 1)

        # Refresh the stats dashboard badges and active filter text
        self._update_stats()
        self._update_filter_indicator()

        # Update the form UI to display the current record, or clear fields if empty
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
        """
        Updates the UI filter status label and button styling.
        
        Reflects the count of active filter parameters on the label next to the
        filter button. If filters are active, highlights the button with a yellow warning color.
        """
        if self.advanced_filter:
            count = 0
            f = self.advanced_filter
            if f.get("labels"): count += 1
            if f.get("types"): count += 1
            if f.get("categories"): count += 1
            if f.get("source_categories"): count += 1
            if f.get("annotators"): count += 1
            if f.get("content_types"): count += 1
            if f.get("has_notes"): count += 1
            if f.get("min_conf") is not None or f.get("max_conf") is not None: count += 1
            self.filter_indicator.configure(text=f"⚡ {count} filter(s)")
            self.filter_btn.configure(fg_color="#4a3f00", border_color="#f39c12")
        else:
            self.filter_indicator.configure(text="")
            self.filter_btn.configure(fg_color="#2d2d5e", border_color="#555")

    def _collect_unique_values(self, field):
        """
        Collects all unique, non-empty values for a specified column from all loaded records.
        
        This helper is used to dynamically construct selection options inside the filter dialog
        based on actual values present in the CSV database (such as unique annotator names).
        
        Args:
            field: The column name in the dataset records to extract values from.
            
        Returns:
            A sorted list of unique non-empty string values.
        """
        values = set()
        for r in self.all_dataset_records:
            v = (r.get(field) or "").strip()
            if v:
                values.add(v)
        return sorted(values)

    def _show_filter_popup(self):
        """
        Opens a modal window containing advanced filter controls for Review mode.
        
        Constructs checklists for labels, sub-types, categories, platforms,
        annotators, and content types. Includes entry fields for setting the
        minimum and maximum confidence interval boundaries.
        """
        popup = ctk.CTkToplevel(self)
        popup.title("Filter Records")
        popup.configure(fg_color="#1a1a2e")
        popup.attributes("-topmost", True)
        popup.resizable(True, True)

        # Center the popup window on the screen relative to the main app coordinates
        pw, ph = 600, 580
        popup.geometry(f"{pw}x{ph}")
        popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (pw // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (ph // 2)
        popup.geometry(f"+{x}+{y}")

        # Section Header Label
        ctk.CTkLabel(popup, text="🔽 Filter Settings",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(12, 6))

        # Scrollable container supporting vertical layout overflows
        scroll = ctk.CTkScrollableFrame(popup, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        # Load active filter selections to pre-populate checkbox variables
        cur = self.advanced_filter or {}

        def _checkbox_section(parent, title, options, pre_selected):
            """
            Builds a card frame containing checklists for a categorical filter section.
            
            Returns a list of (option_value, BooleanVar) tuples to read selection states.
            """
            frame = ctk.CTkFrame(parent, fg_color="#222244", corner_radius=8,
                                  border_width=1, border_color="#444")
            frame.pack(fill="x", pady=(6, 2))

            ctk.CTkLabel(frame, text=title,
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color="#ccc").pack(anchor="w", padx=10, pady=(6, 2))

            vars_list = []
            row_frame = ctk.CTkFrame(frame, fg_color="transparent")
            row_frame.pack(fill="x", padx=10, pady=(0, 6))

            # Render checkboxes in a 4-column grid layout
            for i, opt in enumerate(options):
                var = ctk.BooleanVar(value=(opt in pre_selected) if pre_selected else False)
                cb = ctk.CTkCheckBox(row_frame, text=opt, variable=var,
                                      font=ctk.CTkFont(size=12),
                                      height=24, checkbox_width=18, checkbox_height=18)
                cb.grid(row=i // 4, column=i % 4, sticky="w", padx=(0, 12), pady=2)
                vars_list.append((opt, var))
            return vars_list

        # Authenticity labels (Fake / Real)
        label_vars = _checkbox_section(scroll, "Label",
                                       ["Fake", "Real"],
                                       cur.get("labels", set()))

        # Fake News Sub-classification Types
        type_vars = _checkbox_section(scroll, "Fake News Type",
                                      MULTI_CATEGORIES,
                                      cur.get("types", set()))

        # Topic Categories (politics, science, etc.) compiled dynamically from data
        all_categories = self._collect_unique_values("category")
        cat_vars = _checkbox_section(scroll, "News Category",
                                     all_categories if all_categories else ["(no data)"],
                                     cur.get("categories", set()))

        # Platform medium categories compiled dynamically from data
        all_src_cats = self._collect_unique_values("source_category")
        src_cat_vars = _checkbox_section(scroll, "Source Category",
                                         all_src_cats if all_src_cats else ["(no data)"],
                                         cur.get("source_categories", set()))

        # Annotators names compiled dynamically from data
        all_annotators = self._collect_unique_values("annotator")
        ann_vars = _checkbox_section(scroll, "Annotator",
                                     all_annotators if all_annotators else ["(no data)"],
                                     cur.get("annotators", set()))

        # Media and Text content structure categories
        content_type_vars = _checkbox_section(scroll, "Content Type",
                                              ["Image Only", "Text & Image", "Text Only", "Has Video"],
                                              cur.get("content_types", set()))

        # Filter checkbox to toggle showing only records that contain non-empty annotator notes/comments.
        # This BooleanVar tracks the checkbox state and is pre-filled from the current filter settings.
        has_notes_var = ctk.BooleanVar(value=cur.get("has_notes", False))
        notes_filter_frame = ctk.CTkFrame(scroll, fg_color="#222244", corner_radius=8,
                                           border_width=1, border_color="#444")
        notes_filter_frame.pack(fill="x", pady=(6, 2))
        
        # Section title label for the additional notes filter block
        ctk.CTkLabel(notes_filter_frame, text="Additional Notes",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#ccc").pack(anchor="w", padx=10, pady=(6, 2))
        
        # Checklist checkbox container frame
        notes_cb_frame = ctk.CTkFrame(notes_filter_frame, fg_color="transparent")
        notes_cb_frame.pack(fill="x", padx=10, pady=(0, 6))
        
        # Checkbox controlling whether we restrict results to entries with user notes
        ctk.CTkCheckBox(notes_cb_frame, text="Only show entries with additional notes",
                        variable=has_notes_var, font=ctk.CTkFont(size=12),
                        height=24, checkbox_width=18, checkbox_height=18).pack(anchor="w")

        # Confidence Interval Range Selector
        # This frame groups controls that restrict the loaded subset to records within a specific confidence interval (0 to 100).
        conf_frame = ctk.CTkFrame(scroll, fg_color="#222244", corner_radius=8,
                                   border_width=1, border_color="#444")
        conf_frame.pack(fill="x", pady=(6, 2))

        # Title for the confidence interval settings section
        ctk.CTkLabel(conf_frame, text="Confidence Interval",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#ccc").pack(anchor="w", padx=10, pady=(6, 2))

        # Horizontal alignment row frame containing labels and text entries for min and max bounds
        conf_row = ctk.CTkFrame(conf_frame, fg_color="transparent")
        conf_row.pack(fill="x", padx=10, pady=(0, 8))

        # Input field for the minimum confidence value (default is 0)
        ctk.CTkLabel(conf_row, text="Min:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        min_conf_entry = ctk.CTkEntry(conf_row, width=60, height=26,
                                       font=ctk.CTkFont(size=12), justify="center")
        min_conf_entry.pack(side="left", padx=(0, 16))
        min_conf_entry.insert(0, str(cur.get("min_conf", 0)))

        # Input field for the maximum confidence value (default is 100)
        ctk.CTkLabel(conf_row, text="Max:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        max_conf_entry = ctk.CTkEntry(conf_row, width=60, height=26,
                                       font=ctk.CTkFont(size=12), justify="center")
        max_conf_entry.pack(side="left")
        max_conf_entry.insert(0, str(cur.get("max_conf", 100)))

        # Action control buttons container frame positioned at the bottom of the modal
        btn_container = ctk.CTkFrame(popup, fg_color="transparent")
        btn_container.pack(fill="x", padx=12, pady=(4, 12))

        # Combine all checkbox selection variables into a single flat list to simplify bulk resets
        all_checkbox_vars = label_vars + type_vars + cat_vars + src_cat_vars + ann_vars + content_type_vars

        def _clear_selections():
            """
            Resets all checkboxes in the popup and reverts the confidence interval 
            entries to the standard 0 to 100 range. Does not close the window.
            """
            # Reset all categories and filters in the checkboxes
            for _, var in all_checkbox_vars:
                var.set(False)
            has_notes_var.set(False)
            
            # Revert confidence entry fields back to absolute defaults
            min_conf_entry.delete(0, "end")
            min_conf_entry.insert(0, "0")
            max_conf_entry.delete(0, "end")
            max_conf_entry.insert(0, "100")

        def _apply():
            """
            Gathers the selected filters from the dialog checklist variables and confidence fields.
            Updates the application state's advanced_filter dictionary and triggers database updates.
            """
            # Pull selected list values from checkboxes
            sel_labels = {v for v, var in label_vars if var.get()}
            sel_types = {v for v, var in type_vars if var.get()}
            sel_cats = {v for v, var in cat_vars if var.get() and v != "(no data)"}
            sel_src_cats = {v for v, var in src_cat_vars if var.get() and v != "(no data)"}
            sel_annotators = {v for v, var in ann_vars if var.get() and v != "(no data)"}
            sel_content_types = {v for v, var in content_type_vars if var.get()}

            # Parse minimum confidence threshold value, reverting to 0 on string parsing errors
            try:
                mn = int(min_conf_entry.get().strip())
            except ValueError:
                mn = 0
            
            # Parse maximum confidence threshold value, reverting to 100 on string parsing errors
            try:
                mx = int(max_conf_entry.get().strip())
            except ValueError:
                mx = 100
            
            # Clamp thresholds to allowable percentages (0 to 100)
            mn = max(0, min(100, mn))
            mx = max(0, min(100, mx))
            
            # Swap values if user inadvertently input them backwards
            if mn > mx:
                mn, mx = mx, mn

            # Determine whether any active filter rules have been configured by checking selections
            notes_checked = has_notes_var.get()
            has_filter = (
                bool(sel_labels) or bool(sel_types) or bool(sel_cats) or
                bool(sel_src_cats) or bool(sel_annotators) or bool(sel_content_types) or
                notes_checked or mn > 0 or mx < 100
            )

            # Build or clear the advanced filter model dictionary accordingly
            if has_filter:
                self.advanced_filter = {
                    "labels": sel_labels if sel_labels else None,
                    "types": sel_types if sel_types else None,
                    "categories": sel_cats if sel_cats else None,
                    "source_categories": sel_src_cats if sel_src_cats else None,
                    "annotators": sel_annotators if sel_annotators else None,
                    "content_types": sel_content_types if sel_content_types else None,
                    "has_notes": notes_checked,
                    "min_conf": mn if mn > 0 else None,
                    "max_conf": mx if mx < 100 else None,
                }
            else:
                self.advanced_filter = None

            # Apply the selected criteria to reload the active list, then close popup
            self._apply_advanced_filter()
            popup.destroy()

        def _clear_and_apply():
            """
            Deactivates all filter parameters and closes the window immediately,
            restoring access to all records in the review queue.
            """
            self.advanced_filter = None
            self._apply_advanced_filter()
            popup.destroy()

        # Row 1 layout: Apply Filter + Clear All Selections buttons placed side-by-side
        row1 = ctk.CTkFrame(btn_container, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 6))

        # Button to confirm selections and update list view
        ctk.CTkButton(row1, text="✅ Apply Filter", command=_apply,
                       height=36, font=ctk.CTkFont(size=14, weight="bold"),
                       fg_color="#2ecc71", hover_color="#27ae60",
                       text_color="black").pack(side="left", expand=True, fill="x", padx=(0, 6))

        # Button to clear checkboxes without submitting/applying or closing the popup
        ctk.CTkButton(row1, text="↺ Clear All", command=_clear_selections,
                       height=36, font=ctk.CTkFont(size=13),
                       fg_color="#555", hover_color="#777",
                       width=130).pack(side="left")

        # Row 2 layout: Clear Filter (disabling active settings) + Cancel buttons
        row2 = ctk.CTkFrame(btn_container, fg_color="transparent")
        row2.pack(fill="x")

        # Button to immediately wipe all active filter constraints from the review page
        ctk.CTkButton(row2, text="🗑️ Clear Filter", command=_clear_and_apply,
                       height=36, font=ctk.CTkFont(size=13, weight="bold"),
                       fg_color="#e74c3c", hover_color="#c0392b").pack(side="left", expand=True, fill="x", padx=(0, 6))

        # Button to exit modal layout without saving any changes
        ctk.CTkButton(row2, text="Cancel", command=popup.destroy,
                       height=36, font=ctk.CTkFont(size=13),
                       fg_color="transparent", border_width=1,
                       border_color="#555", width=130).pack(side="left")

    def _show_scripts_popup(self):
        """
        Opens a popup window with three columns for running utility scripts.
        All logic is inlined so it works in the bundled app without separate files.
        Column 1: Aggregate Datasets
        Column 2: Generate Kappa Sample
        Column 3: Calculate Kappa (Cohen's or Fleiss')
        """
        popup = ctk.CTkToplevel(self)
        popup.title("Scripts")
        popup.configure(fg_color="#1a1a2e")
        popup.attributes("-topmost", True)
        popup.resizable(True, True)

        pw, ph = 1100, 720
        popup.geometry(f"{pw}x{ph}")
        popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (pw // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (ph // 2)
        popup.geometry(f"+{x}+{y}")

        # Three-column container
        columns_frame = ctk.CTkFrame(popup, fg_color="transparent")
        columns_frame.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        columns_frame.columnconfigure(0, weight=2, uniform="cols")
        columns_frame.columnconfigure(1, weight=3, uniform="cols")
        columns_frame.columnconfigure(2, weight=2, uniform="cols")
        columns_frame.rowconfigure(0, weight=1)

        script_dir = str(SCRIPT_DIR)
        default_annotators_dir = str(SCRIPT_DIR / "all_annotators_dataset")
        default_output_csv = str(SCRIPT_DIR / "dataset.csv")
        default_output_images = str(SCRIPT_DIR / "images")
        default_output_videos = str(SCRIPT_DIR / "videos")
        default_kappa_input = str(CSV_PATH)
        default_kappa_output = str(KAPPA_CSV_PATH)

        # Helper to create input fields with label, default, browse, clear, and undo
        def _make_field(parent, label_text, default_value, row,
                        browse_dir=False, browse_file=False, browse_warning=None):
            ctk.CTkLabel(parent, text=label_text,
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#ccc", anchor="w").grid(
                             row=row, column=0, sticky="w", padx=8, pady=(6, 0))

            field_frame = ctk.CTkFrame(parent, fg_color="transparent")
            field_frame.grid(row=row + 1, column=0, sticky="ew", padx=8, pady=(2, 4))
            field_frame.columnconfigure(0, weight=1)

            entry = ctk.CTkEntry(field_frame, height=30, font=ctk.CTkFont(size=11),
                                  placeholder_text=label_text)
            entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
            entry.insert(0, default_value)

            undo_stack = [default_value]

            def _on_key(event):
                current = entry.get()
                if not undo_stack or undo_stack[-1] != current:
                    undo_stack.append(current)

            def _undo(event):
                if len(undo_stack) > 1:
                    undo_stack.pop()
                    entry.delete(0, "end")
                    entry.insert(0, undo_stack[-1])
                return "break"

            entry.bind("<KeyRelease>", _on_key)
            entry.bind("<Control-z>", _undo)
            entry.bind("<Command-z>", _undo)

            col = 1

            if browse_dir:
                def _browse():
                    popup.attributes("-topmost", False)
                    path = filedialog.askdirectory(initialdir=script_dir)
                    popup.attributes("-topmost", True)
                    if path:
                        undo_stack.append(entry.get())
                        entry.delete(0, "end")
                        entry.insert(0, path)
                ctk.CTkButton(field_frame, text="📂", width=30, height=30,
                               command=_browse, fg_color="#444",
                               hover_color="#555").grid(row=0, column=col, padx=(0, 2))
                col += 1

            if browse_file:
                def _browse_file():
                    popup.attributes("-topmost", False)
                    path = filedialog.askopenfilename(
                        initialdir=script_dir,
                        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
                    popup.attributes("-topmost", True)
                    if path:
                        undo_stack.append(entry.get())
                        entry.delete(0, "end")
                        entry.insert(0, path)
                ctk.CTkButton(field_frame, text="📂", width=30, height=30,
                               command=_browse_file, fg_color="#444",
                               hover_color="#555").grid(row=0, column=col, padx=(0, 2))
                col += 1

            def _clear():
                undo_stack.append(entry.get())
                entry.delete(0, "end")
            ctk.CTkButton(field_frame, text="✕", width=26, height=30,
                           command=_clear, fg_color="#555",
                           hover_color="#777", text_color="#e74c3c",
                           font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=col)

            return entry

        # ---- COLUMN 1: Aggregate Datasets ----
        left_card = ctk.CTkFrame(columns_frame, fg_color="#222244", corner_radius=10,
                                  border_width=1, border_color="#444")
        left_card.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=4)
        left_card.columnconfigure(0, weight=1)
        left_card.rowconfigure(20, weight=1)

        ctk.CTkLabel(left_card, text="📦 Aggregate Datasets",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
                         row=0, column=0, padx=8, pady=(10, 2), sticky="w")

        ctk.CTkLabel(left_card, text=(
            "• Merges all annotator datasets into one\n"
            "• Copies images & videos to output dirs\n"
            "• Each annotator folder must contain:\n"
            "   dataset.csv, images/, videos/\n"
            "• Place all folders inside one master dir"),
            font=ctk.CTkFont(size=11), text_color="#999",
            wraplength=300, justify="left", anchor="nw").grid(
                row=1, column=0, padx=10, pady=(2, 4), sticky="w")

        agg_master_entry = _make_field(left_card, "Master Folder",
                                        default_annotators_dir, row=2, browse_dir=True)
        agg_csv_entry = _make_field(left_card, "Output CSV",
                                     default_output_csv, row=4, browse_dir=True)
        agg_images_entry = _make_field(left_card, "Output Images Dir",
                                        default_output_images, row=6, browse_dir=True)
        agg_videos_entry = _make_field(left_card, "Output Videos Dir",
                                        default_output_videos, row=8, browse_dir=True)

        # Results popup helper: progress bar → scrollable result text
        def _show_result_popup(title, task_fn):
            """
            Opens a result popup with progress bar, runs task_fn in background,
            then shows the result/error in a scrollable text area.
            """
            rp = ctk.CTkToplevel(popup)
            rp.title(title)
            rp.configure(fg_color="#1a1a2e")
            rp.attributes("-topmost", True)
            rp.resizable(True, True)
            rp.geometry("560x420")
            rp.update_idletasks()
            rx = popup.winfo_x() + (popup.winfo_width() // 2) - 280
            ry = popup.winfo_y() + (popup.winfo_height() // 2) - 210
            rp.geometry(f"+{rx}+{ry}")

            # Header
            ctk.CTkLabel(rp, text=f"⏳ {title}",
                         font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(16, 8))

            # Status label
            status_label = ctk.CTkLabel(rp, text="Running...",
                                         font=ctk.CTkFont(size=12),
                                         text_color="#f39c12")
            status_label.pack(pady=(0, 8))

            # Progress bar (indeterminate)
            progress = ctk.CTkProgressBar(rp, mode="indeterminate",
                                           width=480, height=8)
            progress.pack(padx=30, pady=(0, 12))
            progress.start()

            # Scrollable text area (hidden initially, will fill middle)
            text_frame = ctk.CTkFrame(rp, fg_color="transparent")

            result_text = ctk.CTkTextbox(text_frame, font=ctk.CTkFont(family="Courier", size=12),
                                          fg_color="#111122", text_color="#ccc",
                                          wrap="word", activate_scrollbars=True,
                                          corner_radius=8)
            result_text.pack(fill="both", expand=True, padx=16, pady=(0, 8))

            # Close button (packed at bottom first so it stays anchored)
            close_btn = ctk.CTkButton(rp, text="Close", command=rp.destroy,
                                       height=36, font=ctk.CTkFont(size=13),
                                       fg_color="transparent", border_width=1,
                                       border_color="#555", width=130, state="disabled")
            close_btn.pack(side="bottom", pady=(0, 12))

            def _run():
                try:
                    result = task_fn()
                    def _show():
                        progress.stop()
                        progress.pack_forget()
                        status_label.configure(text="✅ Completed", text_color="#2ecc71")
                        text_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))
                        result_text.insert("1.0", result)
                        result_text.configure(state="disabled", text_color="#2ecc71")
                        close_btn.configure(state="normal")
                    self.after(0, _show)
                except Exception as e:
                    err_msg = str(e)
                    def _show_err():
                        progress.stop()
                        progress.pack_forget()
                        status_label.configure(text="❌ Error", text_color="#e74c3c")
                        text_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))
                        result_text.insert("1.0", err_msg)
                        result_text.configure(state="disabled", text_color="#e74c3c")
                        close_btn.configure(state="normal")
                    self.after(0, _show_err)
            threading.Thread(target=_run, daemon=True).start()

        def _run_aggregate():
            ann_dir = agg_master_entry.get().strip()
            out_csv = agg_csv_entry.get().strip() or default_output_csv
            out_img = agg_images_entry.get().strip() or default_output_images
            out_vid = agg_videos_entry.get().strip() or default_output_videos
            if not ann_dir:
                popup.attributes("-topmost", False)
                messagebox.showwarning("Missing Input", "Provide the master folder path.", parent=popup)
                popup.attributes("-topmost", True)
                return
            existing = []
            if os.path.exists(out_csv):
                existing.append(f"dataset.csv")
            if os.path.exists(out_img) and os.listdir(out_img):
                existing.append(f"images/ directory")
            if os.path.exists(out_vid) and os.listdir(out_vid):
                existing.append(f"videos/ directory")
            if existing:
                warn = "These outputs already exist and will be overwritten:\n\n" + \
                       "\n".join(f"  - {p}" for p in existing) + "\n\nContinue?"
                popup.attributes("-topmost", False)
                if not messagebox.askyesno("Overwrite Warning", warn, parent=popup):
                    popup.attributes("-topmost", True)
                    return
                popup.attributes("-topmost", True)
            _show_result_popup("Aggregate Datasets",
                               lambda: _aggregate_datasets(ann_dir, out_csv, out_img, out_vid))

        left_btn = ctk.CTkFrame(left_card, fg_color="transparent")
        left_btn.grid(row=20, column=0, padx=10, pady=(4, 10), sticky="sew")
        ctk.CTkButton(left_btn, text="▶ Run Aggregation", command=_run_aggregate,
                       height=36, font=ctk.CTkFont(size=13, weight="bold"),
                       fg_color="#2ecc71", hover_color="#27ae60",
                       text_color="black").pack(fill="x")

        # ---- COLUMN 2: Generate Kappa Sample ----
        mid_card = ctk.CTkFrame(columns_frame, fg_color="#222244", corner_radius=10,
                                 border_width=1, border_color="#444")
        mid_card.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)
        mid_card.columnconfigure(0, weight=1)
        mid_card.rowconfigure(30, weight=1)

        ctk.CTkLabel(mid_card, text="🎲 Generate Kappa Sample",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
                         row=0, column=0, padx=8, pady=(10, 2), sticky="w")

        ctk.CTkLabel(mid_card, text=(
            "• Balanced random sample for kappa testing\n"
            "• Customize Real/Fake split below\n"
            "• Fake sub-categories divide the Fake portion\n"
            "• Output loads in Re-label mode"),
            font=ctk.CTkFont(size=11), text_color="#999",
            wraplength=300, justify="left", anchor="nw").grid(
                row=1, column=0, padx=10, pady=(2, 4), sticky="w")

        kappa_input_entry = _make_field(mid_card, "Input CSV (master dataset)",
                                         default_kappa_input, row=2, browse_file=True)
        kappa_n_entry = _make_field(mid_card, "Sample Size (N)", "500", row=4)

        # --- Distribution: Real % / Fake % (must sum to 100) ---
        ctk.CTkLabel(mid_card, text="Distribution (% of total sample)",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#ccc", anchor="w").grid(
                         row=6, column=0, sticky="w", padx=8, pady=(6, 0))

        dist_frame = ctk.CTkFrame(mid_card, fg_color="transparent")
        dist_frame.grid(row=7, column=0, sticky="ew", padx=8, pady=(2, 4))
        dist_frame.columnconfigure(0, weight=1)
        dist_frame.columnconfigure(2, weight=1)

        real_sub = ctk.CTkFrame(dist_frame, fg_color="transparent")
        real_sub.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkLabel(real_sub, text="Real %", font=ctk.CTkFont(size=11),
                     text_color="#2ecc71").pack(anchor="w")
        real_pct_entry = ctk.CTkEntry(real_sub, height=28, font=ctk.CTkFont(size=11),
                                       placeholder_text="50.00")
        real_pct_entry.pack(fill="x")
        real_pct_entry.insert(0, "50.00")

        ctk.CTkLabel(dist_frame, text="+", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#888").grid(row=0, column=1, padx=4)

        fake_sub = ctk.CTkFrame(dist_frame, fg_color="transparent")
        fake_sub.grid(row=0, column=2, sticky="ew", padx=(4, 0))
        ctk.CTkLabel(fake_sub, text="Fake %", font=ctk.CTkFont(size=11),
                     text_color="#e74c3c").pack(anchor="w")
        fake_pct_entry = ctk.CTkEntry(fake_sub, height=28, font=ctk.CTkFont(size=11),
                                       placeholder_text="50.00")
        fake_pct_entry.pack(fill="x")
        fake_pct_entry.insert(0, "50.00")

        dist_sum_label = ctk.CTkLabel(dist_frame, text="= 100.00%",
                                       font=ctk.CTkFont(size=11, weight="bold"),
                                       text_color="#2ecc71")
        dist_sum_label.grid(row=0, column=3, padx=(6, 0))

        # Auto-fill: editing Real auto-calculates Fake, and vice versa
        _dist_updating = [False]

        def _on_real_pct_change(*_):
            if _dist_updating[0]:
                return
            val = real_pct_entry.get().strip()
            try:
                r = round(float(val), 2)
                if 0 <= r <= 100:
                    _dist_updating[0] = True
                    f = round(100.0 - r, 2)
                    fake_pct_entry.delete(0, "end")
                    fake_pct_entry.insert(0, f"{f:.2f}")
                    dist_sum_label.configure(text="= 100.00%", text_color="#2ecc71")
                    _dist_updating[0] = False
                else:
                    dist_sum_label.configure(text="Out of range", text_color="#e74c3c")
            except ValueError:
                dist_sum_label.configure(text="= ???", text_color="#e74c3c")

        def _on_fake_pct_change(*_):
            if _dist_updating[0]:
                return
            val = fake_pct_entry.get().strip()
            try:
                f = round(float(val), 2)
                if 0 <= f <= 100:
                    _dist_updating[0] = True
                    r = round(100.0 - f, 2)
                    real_pct_entry.delete(0, "end")
                    real_pct_entry.insert(0, f"{r:.2f}")
                    dist_sum_label.configure(text="= 100.00%", text_color="#2ecc71")
                    _dist_updating[0] = False
                else:
                    dist_sum_label.configure(text="Out of range", text_color="#e74c3c")
            except ValueError:
                dist_sum_label.configure(text="= ???", text_color="#e74c3c")

        real_pct_entry.bind("<KeyRelease>", _on_real_pct_change)
        fake_pct_entry.bind("<KeyRelease>", _on_fake_pct_change)

        # --- Fake Sub-categories: Misinfo / Satire / Clickbait (% of Fake portion, must sum to 100) ---
        ctk.CTkLabel(mid_card, text="Fake Sub-categories (% of Fake portion)",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#ccc", anchor="w").grid(
                         row=8, column=0, sticky="w", padx=8, pady=(6, 0))

        subcat_frame = ctk.CTkFrame(mid_card, fg_color="transparent")
        subcat_frame.grid(row=9, column=0, sticky="ew", padx=8, pady=(2, 4))
        subcat_frame.columnconfigure(0, weight=1)
        subcat_frame.columnconfigure(2, weight=1)
        subcat_frame.columnconfigure(4, weight=1)

        misinfo_sub = ctk.CTkFrame(subcat_frame, fg_color="transparent")
        misinfo_sub.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        ctk.CTkLabel(misinfo_sub, text="Misinfo %", font=ctk.CTkFont(size=10),
                     text_color="#f39c12").pack(anchor="w")
        misinfo_pct_entry = ctk.CTkEntry(misinfo_sub, height=28, font=ctk.CTkFont(size=11),
                                          placeholder_text="33.33")
        misinfo_pct_entry.pack(fill="x")
        misinfo_pct_entry.insert(0, "33.33")

        ctk.CTkLabel(subcat_frame, text="+", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#888").grid(row=0, column=1, padx=2)

        satire_sub = ctk.CTkFrame(subcat_frame, fg_color="transparent")
        satire_sub.grid(row=0, column=2, sticky="ew", padx=2)
        ctk.CTkLabel(satire_sub, text="Satire %", font=ctk.CTkFont(size=10),
                     text_color="#9b59b6").pack(anchor="w")
        satire_pct_entry = ctk.CTkEntry(satire_sub, height=28, font=ctk.CTkFont(size=11),
                                         placeholder_text="33.33")
        satire_pct_entry.pack(fill="x")
        satire_pct_entry.insert(0, "33.33")

        ctk.CTkLabel(subcat_frame, text="+", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#888").grid(row=0, column=3, padx=2)

        clickbait_sub = ctk.CTkFrame(subcat_frame, fg_color="transparent")
        clickbait_sub.grid(row=0, column=4, sticky="ew", padx=(2, 0))
        ctk.CTkLabel(clickbait_sub, text="Clickbait %", font=ctk.CTkFont(size=10),
                     text_color="#3498db").pack(anchor="w")
        clickbait_pct_entry = ctk.CTkEntry(clickbait_sub, height=28, font=ctk.CTkFont(size=11),
                                            placeholder_text="33.34")
        clickbait_pct_entry.pack(fill="x")
        clickbait_pct_entry.insert(0, "33.34")

        subcat_sum_label = ctk.CTkLabel(subcat_frame, text="= 100.00%",
                                         font=ctk.CTkFont(size=11, weight="bold"),
                                         text_color="#2ecc71")
        subcat_sum_label.grid(row=0, column=5, padx=(4, 0))

        # Auto-fill: first-to-last method
        # Editing Misinfo → splits remaining evenly to Satire & Clickbait
        # Editing Satire → auto-calculates Clickbait (100 - Misinfo - Satire)
        # Editing Clickbait → only updates sum label, no auto-fill
        _subcat_updating = [False]

        def _update_subcat_sum():
            """Update the sum label with current values."""
            try:
                m = float(misinfo_pct_entry.get().strip() or "0")
                s = float(satire_pct_entry.get().strip() or "0")
                c = float(clickbait_pct_entry.get().strip() or "0")
                total = round(m + s + c, 2)
                color = "#2ecc71" if abs(total - 100.0) < 0.02 else "#e74c3c"
                subcat_sum_label.configure(text=f"= {total:.2f}%", text_color=color)
            except ValueError:
                subcat_sum_label.configure(text="= ???", text_color="#e74c3c")

        def _on_misinfo_change(*_):
            if _subcat_updating[0]:
                return
            val = misinfo_pct_entry.get().strip()
            try:
                m = round(float(val), 2)
                if 0 <= m <= 100:
                    _subcat_updating[0] = True
                    remaining = round(100.0 - m, 2)
                    half = round(remaining / 2, 2)
                    other_half = round(remaining - half, 2)
                    satire_pct_entry.delete(0, "end")
                    satire_pct_entry.insert(0, f"{half:.2f}")
                    clickbait_pct_entry.delete(0, "end")
                    clickbait_pct_entry.insert(0, f"{other_half:.2f}")
                    _subcat_updating[0] = False
            except ValueError:
                pass
            _update_subcat_sum()

        def _on_satire_change(*_):
            if _subcat_updating[0]:
                return
            val_m = misinfo_pct_entry.get().strip()
            val_s = satire_pct_entry.get().strip()
            try:
                m = round(float(val_m or "0"), 2)
                s = round(float(val_s), 2)
                if 0 <= s <= 100:
                    _subcat_updating[0] = True
                    c = round(100.0 - m - s, 2)
                    clickbait_pct_entry.delete(0, "end")
                    clickbait_pct_entry.insert(0, f"{c:.2f}")
                    _subcat_updating[0] = False
            except ValueError:
                pass
            _update_subcat_sum()

        def _on_clickbait_change(*_):
            # Last field: no auto-fill, just update the sum label
            _update_subcat_sum()

        misinfo_pct_entry.bind("<KeyRelease>", _on_misinfo_change)
        satire_pct_entry.bind("<KeyRelease>", _on_satire_change)
        clickbait_pct_entry.bind("<KeyRelease>", _on_clickbait_change)

        kappa_output_entry = _make_field(mid_card, "Output CSV",
                                          default_kappa_output, row=10,
                                          browse_file=True)

        # Static warning note about changing the output filename
        ctk.CTkLabel(mid_card, text=(
            "⚠ Changing filename from 'relabeling_for_kappa.csv' "
            "will break Re-label mode auto-detection."),
            font=ctk.CTkFont(size=10), text_color="#e67e22",
            wraplength=300, justify="left", anchor="nw").grid(
                row=12, column=0, padx=10, pady=(0, 2), sticky="w")

        def _run_kappa_gen():
            input_csv = kappa_input_entry.get().strip()
            n_str = kappa_n_entry.get().strip()
            output_csv = kappa_output_entry.get().strip() or default_kappa_output
            if not input_csv:
                popup.attributes("-topmost", False)
                messagebox.showwarning("Missing Input", "Provide the input CSV path.", parent=popup)
                popup.attributes("-topmost", True)
                return
            try:
                n = int(n_str) if n_str else 500
                if n <= 0:
                    raise ValueError("Must be positive")
            except ValueError as e:
                popup.attributes("-topmost", False)
                messagebox.showwarning("Invalid", f"Bad sample size: {e}", parent=popup)
                popup.attributes("-topmost", True)
                return

            # Validate Real/Fake distribution
            try:
                r_pct = round(float(real_pct_entry.get().strip() or "50"), 2)
                f_pct = round(float(fake_pct_entry.get().strip() or "50"), 2)
                if abs(r_pct + f_pct - 100.0) > 0.01:
                    raise ValueError(f"Real ({r_pct}%) + Fake ({f_pct}%) = {r_pct + f_pct:.2f}%, must equal 100%")
                if r_pct < 0 or f_pct < 0:
                    raise ValueError("Percentages cannot be negative")
            except ValueError as e:
                popup.attributes("-topmost", False)
                messagebox.showwarning("Invalid Distribution", str(e), parent=popup)
                popup.attributes("-topmost", True)
                return

            # Validate Fake sub-category distribution
            try:
                m_pct = round(float(misinfo_pct_entry.get().strip() or "33.33"), 2)
                s_pct = round(float(satire_pct_entry.get().strip() or "33.33"), 2)
                c_pct = round(float(clickbait_pct_entry.get().strip() or "33.34"), 2)
                sub_total = round(m_pct + s_pct + c_pct, 2)
                if abs(sub_total - 100.0) > 0.02:
                    raise ValueError(
                        f"Misinfo ({m_pct}%) + Satire ({s_pct}%) + Clickbait ({c_pct}%) = {sub_total:.2f}%\n"
                        f"Fake sub-categories must sum to 100%")
                if m_pct < 0 or s_pct < 0 or c_pct < 0:
                    raise ValueError("Percentages cannot be negative")
            except ValueError as e:
                popup.attributes("-topmost", False)
                messagebox.showwarning("Invalid Sub-categories", str(e), parent=popup)
                popup.attributes("-topmost", True)
                return

            # Warn if output filename changed from default
            output_basename = os.path.basename(output_csv)
            if output_basename != "relabeling_for_kappa.csv":
                popup.attributes("-topmost", False)
                if not messagebox.askyesno("Filename Warning",
                    f"You changed the output filename to '{output_basename}'.\n\n"
                    "The Re-label mode expects 'relabeling_for_kappa.csv'.\n"
                    "The generated file will NOT load automatically in Re-label mode.\n\n"
                    "Continue anyway?", parent=popup):
                    popup.attributes("-topmost", True)
                    return
                popup.attributes("-topmost", True)

            if os.path.exists(output_csv):
                popup.attributes("-topmost", False)
                if not messagebox.askyesno("Overwrite Warning",
                    f"Output file already exists:\n  {output_csv}\n\nOverwrite?", parent=popup):
                    popup.attributes("-topmost", True)
                    return
                popup.attributes("-topmost", True)

            _show_result_popup("Generate Kappa Sample",
                               lambda: _generate_kappa_sample(input_csv, output_csv, n,
                                                               real_pct=r_pct, misinfo_pct=m_pct,
                                                               satire_pct=s_pct, clickbait_pct=c_pct))

        mid_btn = ctk.CTkFrame(mid_card, fg_color="transparent")
        mid_btn.grid(row=30, column=0, padx=10, pady=(4, 10), sticky="sew")
        ctk.CTkButton(mid_btn, text="▶ Generate Sample", command=_run_kappa_gen,
                       height=36, font=ctk.CTkFont(size=13, weight="bold"),
                       fg_color="#2ecc71", hover_color="#27ae60",
                       text_color="black").pack(fill="x")

        # ---- COLUMN 3: Calculate Kappa ----
        right_card = ctk.CTkFrame(columns_frame, fg_color="#222244", corner_radius=10,
                                   border_width=1, border_color="#444")
        right_card.grid(row=0, column=2, sticky="nsew", padx=(4, 0), pady=4)
        right_card.columnconfigure(0, weight=1)
        right_card.rowconfigure(20, weight=1)

        ctk.CTkLabel(right_card, text="📊 Calculate Kappa",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
                         row=0, column=0, padx=8, pady=(10, 2), sticky="w")

        ctk.CTkLabel(right_card, text=(
            "• Calculates inter-rater agreement\n"
            "• Computes for both Label & Multi-Category\n"
            "• Cohen: pairwise (every pair of annotators)\n"
            "• Fleiss: all annotators at once\n"
            "• All records must be fully labeled first"),
            font=ctk.CTkFont(size=11), text_color="#999",
            wraplength=300, justify="left", anchor="nw").grid(
                row=1, column=0, padx=10, pady=(2, 4), sticky="w")

        kappa_calc_entry = _make_field(right_card, "Kappa CSV File",
                                        default_kappa_output, row=2, browse_file=True)

        ctk.CTkLabel(right_card, text="Kappa Mode",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#ccc", anchor="w").grid(
                         row=4, column=0, sticky="w", padx=8, pady=(6, 0))

        kappa_mode_var = ctk.StringVar(value="Cohen's Kappa (pairwise)")
        ctk.CTkOptionMenu(
            right_card,
            values=["Cohen's Kappa (pairwise)", "Fleiss' Kappa (all raters)"],
            variable=kappa_mode_var,
            font=ctk.CTkFont(size=12),
            fg_color="#333", button_color="#444", height=30
        ).grid(row=5, column=0, sticky="ew", padx=8, pady=(2, 4))

        def _run_kappa_calc():
            csv_path = kappa_calc_entry.get().strip()
            if not csv_path:
                popup.attributes("-topmost", False)
                messagebox.showwarning("Missing Input", "Provide the kappa CSV path.", parent=popup)
                popup.attributes("-topmost", True)
                return
            mode = "cohen" if "Cohen" in kappa_mode_var.get() else "fleiss"
            _show_result_popup("Calculate Kappa",
                               lambda: _calculate_kappa(csv_path, mode=mode))

        right_btn = ctk.CTkFrame(right_card, fg_color="transparent")
        right_btn.grid(row=20, column=0, padx=10, pady=(4, 10), sticky="sew")
        ctk.CTkButton(right_btn, text="▶ Calculate Kappa", command=_run_kappa_calc,
                       height=36, font=ctk.CTkFont(size=13, weight="bold"),
                       fg_color="#2ecc71", hover_color="#27ae60",
                       text_color="black").pack(fill="x")

        # Close button
        ctk.CTkButton(popup, text="Close", command=popup.destroy,
                       height=36, font=ctk.CTkFont(size=13),
                       fg_color="transparent", border_width=1,
                       border_color="#555", width=130).pack(pady=(4, 12))

    def _create_stat_badge(self, parent, label, count, dot_color="#888"):
        """
        Creates and packs a visually stylized metric badge/card inside the stats bar.
        
        Each badge card is enclosed in a dark, rounded container with a subtle border.
        It contains a colored circular dot indicating status/category, a large bold
        counter showing the numeric value, and a smaller descriptive label.
        
        Args:
            parent: The Tkinter container widget that will host this badge.
            label: Text descriptor for the metric (e.g., "Fake", "Real", "Images").
            count: Numeric value/count to display.
            dot_color: Hex color string for the status dot indicator.
        """
        # Create the outer container frame for the statistic badge card.
        # This frame establishes the card boundaries, using a dark background color
        # and rounded corners for a modern, dashboard-like style.
        badge = ctk.CTkFrame(parent, fg_color="#1e1e3a", corner_radius=8,
                              border_width=1, border_color="#333")
        
        # Create an inner widget wrapper that handles spacing and layout within the card.
        # Keeping this transparent lets the parent frame's background color show through.
        inner = ctk.CTkFrame(badge, fg_color="transparent")
        inner.pack(padx=10, pady=6)
        
        # Draw the status indicator dot. We configure a tiny frame with rounded corners
        # (corner_radius = half of width/height) to create a perfect circle.
        dot = ctk.CTkFrame(inner, width=10, height=10, corner_radius=5,
                            fg_color=dot_color)
        dot.pack(side="left", padx=(0, 6))
        
        # Disable pack propagation on the dot frame. This is critical because without it,
        # Tkinter would shrink this empty container to 0x0 size since it has no child widgets.
        dot.pack_propagate(False)
        
        # Render the count text. We use a larger, bold font to make the numeric statistic
        # stand out as the primary metric of the card.
        ctk.CTkLabel(inner, text=str(count),
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ffffff").pack(side="left", padx=(0, 6))
        
        # Render the helper label text to describe what the count represents.
        # This uses a smaller, secondary text color to keep the dashboard visual hierarchy clean.
        ctk.CTkLabel(inner, text=label,
                     font=ctk.CTkFont(size=11),
                     text_color="#aaa").pack(side="left")

    def _create_stat_label(self, parent, text, filter_key=None, is_separator=False):
        """
        Helper method to instantiate stat labels inside a FlowFrame parent.
        
        These labels do not define click actions. Instead, they serve as display
        items or textual separators (e.g. pipe characters) in the categories list.
        Because they are placed in a FlowFrame, they do not need explicit manual
        packing; the parent layout manager arranges them automatically.
        
        Args:
            parent: The FlowFrame hosting the label list.
            text: Text content of the label.
            filter_key: Optional identifier for category filtering.
            is_separator: If True, renders a neutral separator style.
        """
        # If this is a decorative divider element (like a pipe separator "|"),
        # render it using a default font style without key-based color themes.
        if is_separator:
            lbl = ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=13))
            return

        # Determine label text color by checking the active Tkinter appearance mode (Dark vs Light).
        # This keeps text elements legible regardless of system-level styling preferences.
        color = "#ffffff" if ctk.get_appearance_mode() == "Dark" else "#000000"
        fnt = ctk.CTkFont(size=13)
        lbl = ctk.CTkLabel(parent, text=text, font=fnt, text_color=color)

    def _update_stats(self):
        """
        Recalculates and refreshes the database statistics dashboard at the top of the UI.
        
        This method aggregates count data for articles, classification labels, fake news
        sub-categories, and media types. It supports two operational scopes:
        1. Filtered subset: If the user is in Review mode and has an active search filter, 
           statistics are calculated dynamically from the loaded/filtered records in memory.
        2. Global dataset: Otherwise, statistics are fetched directly from the database 
           using backend helper functions.
           
        After calculating counts, all existing badge widgets are destroyed and recreated
        to avoid layout stacking, followed by a manual FlowFrame layout trigger.
        """
        # Determine whether we should compile statistics from the active filter results.
        # This is active only if we are in review mode and an advanced filter query is loaded.
        use_filtered = (self.current_mode == "review" and self.advanced_filter
                         and hasattr(self, 'dataset_records'))

        if use_filtered:
            # Aggregate category stats directly from the filtered memory list.
            records = self.dataset_records
            total = len(records)
            
            # Tally primary target authenticity classes
            fake = sum(1 for r in records if (r.get("label") or "") == "Fake")
            real = sum(1 for r in records if (r.get("label") or "") == "Real")
            
            # Set up aggregation trackers for fake news subtypes, categories, and media
            sub = {"Misinformation": 0, "Satire": 0, "Clickbait": 0}
            news_cats = {}
            img_count = 0
            vid_count = 0
            only_image = 0
            only_text = 0
            both_text_image = 0
            
            # Iterate through active records and aggregate counts
            for r in records:
                # Increment counts for fake news classifications (Misinformation, Satire, Clickbait)
                mc = (r.get("multi_category") or "").strip()
                if mc in sub:
                    sub[mc] += 1
                
                # Increment counts for news categories (e.g. Politics, Sports, Health)
                cat = (r.get("category") or "").strip()
                if cat:
                    news_cats[cat] = news_cats.get(cat, 0) + 1
                
                # Parse semicolon-delimited image paths and count files
                ip = (r.get("image_path") or "").strip()
                img_list = [p for p in ip.split(";") if p.strip()]
                if ip:
                    img_count += len(img_list)
                
                # Check for video attachments
                vp = (r.get("video_path") or "").strip()
                if vp:
                    vid_count += 1
                
                # Categorize the article format based on the presence of text vs media files
                has_text = bool((r.get("text") or "").strip())
                has_image = bool(img_list)
                has_media = has_image or bool(vp)
                
                if has_text and has_media:
                    both_text_image += 1
                elif has_text and not has_media:
                    only_text += 1
                elif not has_text and has_media:
                    only_image += 1
            
            # Retain a reference to the global unfiltered total to display alongside the subset size
            global_total = len(self.all_dataset_records)
        else:
            # Query global database stats directly from the CSV parser backend module.
            # This is used when there are no active filters or we are in standard annotate mode.
            counts = get_label_counts()
            img_count = get_image_count()
            vid_count = get_video_count()
            total = counts["total"]
            fake = counts["fake"]
            real = counts["real"]
            sub = counts["fake_subcategories"]
            news_cats = counts["news_categories"]
            only_image = counts["only_image"]
            only_text = counts["only_text"]
            both_text_image = counts["both_text_image"]
            global_total = None

        # Tear down all existing badge widgets from the main stats frame.
        # This prevents widgets from stacking on top of each other when redrawing.
        for widget in self.stats_frame.winfo_children():
            widget.destroy()
            
        # Clean up existing category label displays from the bottom statistics strip.
        for widget in self.category_stats_frame.winfo_children():
            widget.destroy()

        # Build total entries dashboard cards
        if use_filtered:
            # Display active records relative to the database totals (e.g. "Filtered / 45")
            self._create_stat_badge(self.stats_frame, f"Filtered / {global_total}", total, "#3498db")
        else:
            self._create_stat_badge(self.stats_frame, "Total", total, "#3498db")
        
        # Render Fake/Real category status badges.
        # If using active filters, we hide badges that have zero counts to keep the UI clean.
        if not use_filtered or fake > 0:
            self._create_stat_badge(self.stats_frame, "Fake", fake, "#e74c3c")
        if not use_filtered or real > 0:
            self._create_stat_badge(self.stats_frame, "Real", real, "#2ecc71")
        
        # Render subclassification badges for fine-grained Fake News subtypes
        if not use_filtered or sub["Misinformation"] > 0:
            self._create_stat_badge(self.stats_frame, "Misinfo", sub["Misinformation"], "#e67e22")
        if not use_filtered or sub["Satire"] > 0:
            self._create_stat_badge(self.stats_frame, "Satire", sub["Satire"], "#9b59b6")
        if not use_filtered or sub["Clickbait"] > 0:
            self._create_stat_badge(self.stats_frame, "Clickbait", sub["Clickbait"], "#f39c12")
        
        # Create a "See More" badge-style button
        see_more_badge = ctk.CTkFrame(
            self.stats_frame, fg_color="#1e1e3a", corner_radius=8,
            border_width=1, border_color="#333", cursor="hand2"
        )
        
        inner = ctk.CTkFrame(see_more_badge, fg_color="transparent")
        inner.pack(padx=10, pady=6)
        
        dot = ctk.CTkFrame(inner, width=10, height=10, corner_radius=5, fg_color="#3498db")
        dot.pack(side="left", padx=(0, 6))
        dot.pack_propagate(False)
        
        lbl = ctk.CTkLabel(
            inner, text="See More ▸",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#3498db"
        )
        lbl.pack(side="left")
        
        # Add hover effects to the see more badge frame and its children
        def on_enter(e):
            see_more_badge.configure(fg_color="#2c2c54")
        def on_leave(e):
            see_more_badge.configure(fg_color="#1e1e3a")
            
        see_more_badge.bind("<Enter>", on_enter)
        see_more_badge.bind("<Leave>", on_leave)
        inner.bind("<Enter>", on_enter)
        inner.bind("<Leave>", on_leave)
        dot.bind("<Enter>", on_enter)
        dot.bind("<Leave>", on_leave)
        lbl.bind("<Enter>", on_enter)
        lbl.bind("<Leave>", on_leave)
        
        # Bind click events
        see_more_badge.bind("<Button-1>", lambda e: self._show_detailed_stats_popup())
        inner.bind("<Button-1>", lambda e: self._show_detailed_stats_popup())
        dot.bind("<Button-1>", lambda e: self._show_detailed_stats_popup())
        lbl.bind("<Button-1>", lambda e: self._show_detailed_stats_popup())

        # Compile and layout the horizontal categories text bar
        if news_cats:
            # Instantiate section header
            lbl = ctk.CTkLabel(self.category_stats_frame, text="News Categories  ▸  ", font=ctk.CTkFont(size=12), text_color="#aaa")
            lbl.pack(side="left", padx=(0, 6))
            
            # Sort category keys alphabetically to guarantee a stable, predictable layout order
            sorted_cats = sorted(news_cats.items())
            for i, (cat, count) in enumerate(sorted_cats):
                self._create_stat_label(self.category_stats_frame, f"{cat}: {count}", filter_key=cat)
                
                # Append pipe separators between adjacent items, skipping the last element
                if i < len(sorted_cats) - 1:
                    self._create_stat_label(self.category_stats_frame, "|", is_separator=True)
        else:
            # Fallback message displayed when no categories have been saved yet
            lbl = ctk.CTkLabel(self.category_stats_frame, text="News Categories  ▸  No entries yet", font=ctk.CTkFont(size=12), text_color="#aaa")
            lbl.pack(side="left", padx=(0, 6))

        # Force Tkinter layout engine update to process changes before arranging widget coordinate paths
        self.stats_frame.update_idletasks()
        self.category_stats_frame.update_idletasks()
        
        # Call the FlowFrame layout manager arrange algorithm to calculate reflow positions
        self.stats_frame._arrange()
        self.category_stats_frame._arrange()

    def _get_records_for_detailed_stats(self):
        """
        Retrieves the list of records to compute detailed statistics on.
        If the app is in Review mode and filtering is active, it returns
        self.dataset_records (the filtered subset). Otherwise, it reads all
        records dynamically from dataset.csv.
        """
        use_filtered = (self.current_mode == "review" and self.advanced_filter
                         and hasattr(self, 'dataset_records'))
        if use_filtered:
            return self.dataset_records
        
        records = []
        if CSV_PATH.exists() and CSV_PATH.stat().st_size > 0:
            try:
                with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        records.append(row)
            except Exception as e:
                print(f"[WARNING] Failed to read CSV for detailed stats: {e}")
        return records

    def _filter_detailed_stats_records(self, records, selected_category="All Categories",
                                       selected_annotator="All Annotators"):
        filtered_records = records
        if selected_category != "All Categories":
            filtered_records = [
                r for r in filtered_records
                if (r.get("category") or "").strip() == selected_category
            ]
        if selected_annotator != "All Annotators":
            filtered_records = [
                r for r in filtered_records
                if (r.get("annotator") or "").strip() == selected_annotator
            ]
        return filtered_records

    def _detailed_stats_export_rows(self, stats):
        headers = ["Modality / Metric", *DETAILED_STATS_COLUMNS]
        rows = [headers]
        for metric_name in DETAILED_STATS_METRICS:
            rows.append([
                metric_name,
                *[str(stats[col_key][metric_name]) for col_key in DETAILED_STATS_COLUMNS]
            ])
        return rows

    def _ask_detailed_stats_export_scope(self, parent):
        """
        Opens a small modal with explicit export-scope buttons.
        Returns "current", "all", or None when canceled.
        """
        choice = {"value": None}

        dialog = ctk.CTkToplevel(parent)
        dialog.title("Export Statistics")
        dialog.configure(fg_color="#1a1a2e")
        dialog.transient(parent)
        dialog.grab_set()
        dialog.resizable(False, False)

        pw, ph = 420, 175
        dialog.geometry(f"{pw}x{ph}")
        dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (pw // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (ph // 2)
        dialog.geometry(f"+{x}+{y}")

        ctk.CTkLabel(
            dialog,
            text="Choose Export Scope",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color="#cdd6f4"
        ).pack(pady=(20, 6))

        ctk.CTkLabel(
            dialog,
            text="Pick exactly what should be written to the CSV.",
            font=ctk.CTkFont(size=12),
            text_color="#a6adc8"
        ).pack(pady=(0, 18))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=22)

        def finish(value):
            choice["value"] = value
            dialog.destroy()

        ctk.CTkButton(
            btn_frame,
            text="Current Dashboard",
            command=lambda: finish("current"),
            height=36,
            fg_color="#4f46e5",
            hover_color="#5c5cff"
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="All Local Categories",
            command=lambda: finish("all"),
            height=36,
            fg_color="#313244",
            hover_color="#45475a"
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            command=lambda: finish(None),
            height=36,
            fg_color="transparent",
            border_width=1,
            border_color="#555"
        ).pack(side="left", fill="x", expand=True)

        dialog.protocol("WM_DELETE_WINDOW", lambda: finish(None))
        parent.wait_window(dialog)
        return choice["value"]

    def _refresh_detailed_stats_filters(self, is_global, category_var, annotator_var,
                                        category_menu, annotator_menu, option_provider):
        """
        Keeps detailed dashboard filters aligned with the selected metrics scope.
        Category filtering is local-only because the Gist stores aggregate team metrics.
        """
        category_options, annotator_options = option_provider(is_global)

        if is_global:
            category_var.set("All Categories")
            category_values = ["All Categories"]
            category_state = "disabled"
        else:
            category_values = category_options
            category_state = "normal"
            if category_var.get() not in category_values:
                category_var.set("All Categories")

        if annotator_var.get() not in annotator_options:
            annotator_var.set("All Annotators")

        if category_menu is not None:
            category_menu.configure(values=category_values, state=category_state)
            if is_global:
                category_menu.pack_forget()
            elif not category_menu.winfo_manager():
                if annotator_menu is not None:
                    category_menu.pack(side="left", padx=(0, 10), before=annotator_menu)
                else:
                    category_menu.pack(side="left", padx=(0, 10))
        if annotator_menu is not None:
            annotator_menu.configure(values=annotator_options)

    def _show_detailed_stats_popup(self):
        """
        Displays a modal popup with a detailed dashboard breakdown of news modalities
        (Video, Image, Text combinations) across all authenticity categories.
        """
        popup = ctk.CTkToplevel(self)
        popup.title("Detailed Statistics Dashboard")
        popup.configure(fg_color="#11111b")  # Darker premium background
        popup.transient(self)
        popup.grab_set()
        popup.resizable(True, True)

        pw, ph = 960, 680
        popup.geometry(f"{pw}x{ph}")
        popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (pw // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (ph // 2)
        popup.geometry(f"+{x}+{y}")

        all_records = self._get_records_for_detailed_stats()
        global_annotator_filter_map = {}

        def _global_annotator_options():
            entries = []
            name_counts = {}
            global_annotator_filter_map.clear()

            for machine_uuid, machine_data in self.global_metrics_data.items():
                if not isinstance(machine_data, dict):
                    continue
                for ann_name, ann_stats in machine_data.items():
                    ann_label = str(ann_name).strip()
                    if isinstance(ann_stats, dict) and ann_label:
                        entries.append((ann_label, str(machine_uuid)))
                        name_counts[ann_label] = name_counts.get(ann_label, 0) + 1

            options = []
            for ann_label, machine_uuid in sorted(entries):
                if name_counts.get(ann_label, 0) > 1:
                    option_label = f"{ann_label}-{machine_uuid[-8:]}"
                else:
                    option_label = ann_label
                global_annotator_filter_map[option_label] = (ann_label, machine_uuid)
                options.append(option_label)
            return options

        def _dashboard_filter_options(is_global=False):
            local_categories = {
                (r.get("category") or "").strip()
                for r in all_records
                if (r.get("category") or "").strip()
            }
            preferred_categories = [c for c in CATEGORIES if c]
            extra_categories = sorted(local_categories - set(preferred_categories))
            category_values = ["All Categories"] + preferred_categories + extra_categories

            local_annotators = {
                (r.get("annotator") or "").strip()
                for r in all_records
                if (r.get("annotator") or "").strip()
            }
            if is_global:
                annotator_values = ["All Annotators"] + _global_annotator_options()
            else:
                annotator_values = ["All Annotators"] + sorted(local_annotators)
            return category_values, annotator_values

        # Top Controls Frame
        top_frame = ctk.CTkFrame(popup, fg_color="transparent")
        top_frame.pack(fill="x", padx=24, pady=(24, 10))
        
        ctk.CTkLabel(top_frame, text="Filter:", font=ctk.CTkFont(size=14, weight="bold"), text_color="#cdd6f4").pack(side="left", padx=(0, 10))
        
        category_options, annotator_options = _dashboard_filter_options(self.global_metrics_enabled.get())
        category_var = ctk.StringVar(value="All Categories")
        annotator_var = ctk.StringVar(value="All Annotators")
        category_menu = None
        annotator_menu = None
        
        def show_info():
            info_text = (
                "Dashboard Calculation Metrics:\n\n"
                "1. Local Metrics: Calculated from your local dataset.csv and can be filtered by category and annotator.\n\n"
                "2. Global Metrics (Team): Calculated from synced aggregate counts in the team's GitHub Gist. No raw article text, notes, sources, or media files are uploaded.\n\n"
                "3. Duplicate Names: If two synced machines use the same annotator name, the Team filter shows Name-last8uuid to keep them separate.\n\n"
                "4. Hidden by Default: Percentages only appear when you click a row or column header.\n\n"
                "5. Column Clicks (Vertical %): Shows the distribution of modalities for that specific column.\n\n"
                "6. Row Clicks (Horizontal %): 'Real' & 'Fake' are percentages of the 'Total' column. 'Misinfo', 'Satire', & 'Clickbait' are percentages of the 'Fake' column.\n\n"
                "7. Raw Counts: The 'Total Items' row and 'Total' column always show raw instance counts."
            )
            messagebox.showinfo("Metrics Info", info_text, parent=popup)

        info_btn = ctk.CTkButton(top_frame, text="❓", width=28, height=28, fg_color="transparent", hover_color="#313244", font=ctk.CTkFont(size=14), command=show_info)
        info_btn.pack(side="right", padx=(10, 0))
        
        # Add Team Sync and Global Metrics Toggle
        self.team_sync_btn = ctk.CTkButton(top_frame, text="🌐 Team Sync", command=self._show_team_sync_popup,
                                          width=100, height=28,
                                          font=ctk.CTkFont(size=13),
                                          fg_color="#27ae60", hover_color="#2ecc71",
                                          border_width=1, border_color="#555",
                                          corner_radius=6)
        self.team_sync_btn.pack(side="right", padx=(10, 10))

        def on_global_toggle():
            # Update the dashboard whenever the toggle is clicked
            draw_dashboard()

        self.active_detailed_popup = popup

        self.global_toggle = ctk.CTkSwitch(top_frame, text="Global Metrics (Team)", 
                                           variable=self.global_metrics_enabled,
                                           command=on_global_toggle,
                                           font=ctk.CTkFont(size=13, weight="bold"))
        self.global_toggle.pack(side="right", padx=10)

        self.sync_time_label = ctk.CTkLabel(top_frame, text="", font=ctk.CTkFont(size=11), text_color="#a6adc8")
        self.sync_time_label.pack(side="right", padx=5)

        # Container for the dashboard (Cards + Grid)
        dash_container = ctk.CTkFrame(popup, fg_color="transparent")
        dash_container.pack(fill="both", expand=True)
        
        # Active subset data for CSV export
        active_export_data = []

        def draw_dashboard(*args):
            nonlocal active_export_data
            for widget in dash_container.winfo_children():
                widget.destroy()

            is_global = self.global_metrics_enabled.get()
            self._refresh_detailed_stats_filters(
                is_global, category_var, annotator_var, category_menu, annotator_menu,
                _dashboard_filter_options
            )

            selected_category = category_var.get()
            selected_annotator = annotator_var.get()

            # Update sync time label
            cfg = get_full_config()
            if not cfg.get("gist_id") or not cfg.get("github_token"):
                self.sync_time_label.configure(text="Not connected")
            elif hasattr(self, 'last_global_sync_time') and self.last_global_sync_time:
                mins = int((time.time() - self.last_global_sync_time) / 60)
                if mins == 0:
                    self.sync_time_label.configure(text="Synced just now")
                else:
                    self.sync_time_label.configure(text=f"Synced {mins} min ago")
            else:
                self.sync_time_label.configure(text="Not synced yet")

            if is_global:
                # --- GLOBAL METRICS MODE ---
                # Build stats by aggregating from self.global_metrics_data
                stats = self._empty_detailed_stats()
                found_any = False
                selected_global_entry = global_annotator_filter_map.get(selected_annotator)
                for machine_uuid, machine_data in self.global_metrics_data.items():
                    if not isinstance(machine_data, dict):
                        continue
                    for ann_name, ann_stats in machine_data.items():
                        if not isinstance(ann_stats, dict):
                            continue
                        ann_label = str(ann_name).strip()
                        if selected_annotator != "All Annotators":
                            if selected_global_entry is None:
                                continue
                            selected_name, selected_machine_uuid = selected_global_entry
                            if ann_label != selected_name or str(machine_uuid) != selected_machine_uuid:
                                continue

                        if self._merge_detailed_stats(stats, ann_stats):
                            found_any = True
                
                if not found_any:
                    empty_frame = ctk.CTkFrame(dash_container, fg_color="transparent")
                    empty_frame.pack(expand=True)
                    if getattr(self, 'is_global_syncing', False):
                        ctk.CTkLabel(empty_frame, text="⏳", font=ctk.CTkFont(size=60)).pack(pady=(0, 10))
                        ctk.CTkLabel(empty_frame, text="Syncing Team Data...", font=ctk.CTkFont(size=24, weight="bold"), text_color="#f39c12").pack(pady=(0, 5))
                        ctk.CTkLabel(empty_frame, text="Please wait while we fetch the latest metrics from GitHub.", font=ctk.CTkFont(size=14), text_color="#a6adc8").pack()
                    else:
                        ctk.CTkLabel(empty_frame, text="📭", font=ctk.CTkFont(size=60)).pack(pady=(0, 10))
                        ctk.CTkLabel(empty_frame, text="No Team Data Available", font=ctk.CTkFont(size=24, weight="bold"), text_color="#cdd6f4").pack(pady=(0, 5))
                        ctk.CTkLabel(empty_frame, text="Ensure Team Sync is configured, or choose an annotator with synced metrics.", font=ctk.CTkFont(size=14), text_color="#a6adc8").pack()
                    active_export_data = []
                    return
            else:
                # --- LOCAL METRICS MODE ---
                # Filter records
                filtered_records = self._filter_detailed_stats_records(
                    all_records, selected_category, selected_annotator
                )

                # --- EMPTY STATE ---
                if not filtered_records:
                    empty_frame = ctk.CTkFrame(dash_container, fg_color="transparent")
                    empty_frame.pack(expand=True)
                    ctk.CTkLabel(empty_frame, text="📭", font=ctk.CTkFont(size=60)).pack(pady=(0, 10))
                    ctk.CTkLabel(empty_frame, text="No Data Available", font=ctk.CTkFont(size=24, weight="bold"), text_color="#cdd6f4").pack(pady=(0, 5))
                    ctk.CTkLabel(empty_frame, text=f"No annotated items match the current filters.", font=ctk.CTkFont(size=14), text_color="#a6adc8").pack()
                    active_export_data = []
                    return

                stats = self._compute_detailed_stats_for_records(filtered_records)

            # --- SUMMARY CARDS ---
            cards_frame = ctk.CTkFrame(dash_container, fg_color="transparent")
            cards_frame.pack(fill="x", padx=24, pady=(10, 20))
            cards_frame.grid_columnconfigure((0, 1, 2), weight=1, uniform="card")

            def create_card(parent, title, value, subtext, col, bg_color):
                c = ctk.CTkFrame(parent, fg_color=bg_color, corner_radius=12)
                c.grid(row=0, column=col, sticky="nsew", padx=8)
                ctk.CTkLabel(c, text=title, font=ctk.CTkFont(size=13, weight="bold"), text_color="#bac2de").pack(anchor="w", padx=16, pady=(10, 0))
                ctk.CTkLabel(c, text=str(value), font=ctk.CTkFont(size=28, weight="bold"), text_color="#ffffff").pack(anchor="w", padx=16, pady=(0, 0))
                ctk.CTkLabel(c, text=subtext, font=ctk.CTkFont(size=12), text_color="#a6adc8").pack(anchor="w", padx=16, pady=(0, 10))

            total_count = stats["Total"]["Total Items"]
            real_count = stats["Real"]["Total Items"]
            fake_count = stats["Fake"]["Total Items"]
            real_pct = int(real_count / total_count * 100) if total_count > 0 else 0
            fake_pct = int(fake_count / total_count * 100) if total_count > 0 else 0
            
            total_media = stats["Total"]["Total Images"] + stats["Total"]["Total Videos"]

            if is_global:
                create_card(cards_frame, "🌐 TEAM TOTAL ITEMS", total_count, "All annotators combined", 0, "#2c2c54")
                create_card(cards_frame, "Team Authenticity Split", f"{real_pct}% / {fake_pct}%", f"{real_count} Real, {fake_count} Fake", 1, "#2c2c54")
                create_card(cards_frame, "Team Total Media", total_media, f"{stats['Total']['Total Images']} Images, {stats['Total']['Total Videos']} Videos", 2, "#2c2c54")
            else:
                create_card(cards_frame, "Local Total Items", total_count, "Your annotated entries", 0, "#1e1e2e")
                create_card(cards_frame, "Local Authenticity Split", f"{real_pct}% / {fake_pct}%", f"{real_count} Real, {fake_count} Fake", 1, "#1e1e2e")
                create_card(cards_frame, "Local Total Media", total_media, f"{stats['Total']['Total Images']} Images, {stats['Total']['Total Videos']} Videos", 2, "#1e1e2e")

            # --- DETAILED GRID ---
            scroll = ctk.CTkScrollableFrame(dash_container, fg_color="#181825", corner_radius=16)
            scroll.pack(fill="both", expand=True, padx=24, pady=(0, 10))

            header_fg = "#181825"
            row_fg_even = "#1e1e2e"
            row_fg_odd = "#242436"
            hover_fg = "#313244"
            active_fg = "#4f46e5" 
            
            grid_frame = ctk.CTkFrame(scroll, fg_color="transparent")
            grid_frame.pack(fill="x", expand=True, padx=2, pady=2)
            
            grid_frame.columnconfigure(0, weight=2, minsize=180)
            for c in range(1, 7):
                grid_frame.columnconfigure(c, weight=1, uniform="col_stat", minsize=100)
                
            headers = ["Modality / Metric", *DETAILED_STATS_COLUMNS]
            export_rows = self._detailed_stats_export_rows(stats)
            
            active_highlight_row = [None]
            active_highlight_col = [None]
            row_cells = {}
            row_labels = {}
            col_cells = {i: [] for i in range(7)}
            col_labels = {i: [] for i in range(7)}
            row_default_colors = {}
            label_default_colors = {}

            def clear_highlights():
                if active_highlight_row[0] is not None:
                    old_row = active_highlight_row[0]
                    for cell in row_cells[old_row]:
                        cell.configure(fg_color=row_default_colors[old_row])
                    for label in row_labels[old_row]:
                        if label_default_colors[label] == "HIDDEN_PCT":
                            label.configure(text="", text_color="#9399b2")
                        else:
                            label.configure(text_color=label_default_colors[label])
                    active_highlight_row[0] = None
                
                if active_highlight_col[0] is not None:
                    old_col = active_highlight_col[0]
                    for r_idx, cell in col_cells[old_col]:
                        cell.configure(fg_color=row_default_colors[r_idx])
                    for label in col_labels[old_col]:
                        if label_default_colors[label] == "HIDDEN_PCT":
                            label.configure(text="", text_color="#9399b2")
                        else:
                            label.configure(text_color=label_default_colors[label])
                    active_highlight_col[0] = None

            for col_idx, h_text in enumerate(headers):
                cell_frame = ctk.CTkFrame(grid_frame, fg_color=header_fg, corner_radius=0, border_width=0, cursor="hand2")
                cell_frame.grid(row=0, column=col_idx, sticky="nsew", pady=(0, 4))
                lbl = ctk.CTkLabel(cell_frame, text=h_text, font=ctk.CTkFont(size=13, weight="bold"), text_color="#cdd6f4")
                lbl.pack(padx=6, pady=12, expand=True)
                
                # Bind column click
                cell_frame.bind("<Button-1>", lambda e, c=col_idx: on_col_click(c))
                lbl.bind("<Button-1>", lambda e, c=col_idx: on_col_click(c))

            def on_enter(e, r):
                if active_highlight_row[0] != r and active_highlight_col[0] is None:
                    for cell in row_cells[r]:
                        cell.configure(fg_color=hover_fg)

            def on_leave(e, r):
                if active_highlight_row[0] != r and active_highlight_col[0] is None:
                    for cell in row_cells[r]:
                        cell.configure(fg_color=row_default_colors[r])

            def on_row_click(row_idx):
                if active_highlight_row[0] == row_idx:
                    clear_highlights()
                    for cell in row_cells[row_idx]:
                        cell.configure(fg_color=hover_fg)
                else:
                    clear_highlights()
                    for cell in row_cells[row_idx]:
                        cell.configure(fg_color=active_fg)
                    for label in row_labels[row_idx]:
                        if label_default_colors[label] == "HIDDEN_PCT":
                            h_text = getattr(label, '_stored_horizontal_text', '')
                            h_color = getattr(label, '_horizontal_highlight_color', '#bac2de')
                            label.configure(text=h_text, text_color=h_color)
                        elif label_default_colors[label] in ("#6c7086", "#9399b2"):
                            label.configure(text_color="#bac2de") 
                        else:
                            label.configure(text_color="#ffffff")
                    active_highlight_row[0] = row_idx
                    
            def on_col_click(col_idx):
                if active_highlight_col[0] == col_idx:
                    clear_highlights()
                else:
                    clear_highlights()
                    for r_idx, cell in col_cells[col_idx]:
                        cell.configure(fg_color=active_fg)
                    for label in col_labels[col_idx]:
                        if label_default_colors[label] == "HIDDEN_PCT":
                            v_text = getattr(label, '_stored_vertical_text', '')
                            v_color = getattr(label, '_vertical_highlight_color', '#bac2de')
                            label.configure(text=v_text, text_color=v_color)
                        elif label_default_colors[label] in ("#6c7086", "#9399b2"):
                            label.configure(text_color="#bac2de") 
                        else:
                            label.configure(text_color="#ffffff")
                    active_highlight_col[0] = col_idx
                
            metrics = [
                ("Total Items", "#89b4fa"),
                ("Text Only", "#f38ba8"),
                ("Image Only", "#fab387"),
                ("Video Only", "#fab387"),
                ("Text + Image", "#f9e2af"),
                ("Text + Video", "#f9e2af"),
                ("Image + Video", "#f9e2af"),
                ("Text + Image + Video", "#cba6f7")
            ]

            for row_idx, (metric_name, dot_color) in enumerate(metrics, start=1):
                bg_color = row_fg_even if row_idx % 2 == 0 else row_fg_odd
                row_cells[row_idx] = []
                row_labels[row_idx] = []
                row_default_colors[row_idx] = bg_color
                
                cell_frame = ctk.CTkFrame(grid_frame, fg_color=bg_color, corner_radius=6, border_width=0, cursor="hand2")
                cell_frame.grid(row=row_idx, column=0, sticky="nsew", padx=(0, 2), pady=1)
                row_cells[row_idx].append(cell_frame)
                col_cells[0].append((row_idx, cell_frame))
                
                inner = ctk.CTkFrame(cell_frame, fg_color="transparent")
                inner.pack(padx=16, pady=12, anchor="w")
                
                dot = ctk.CTkFrame(inner, width=10, height=10, corner_radius=5, fg_color=dot_color)
                dot.pack(side="left", padx=(0, 10))
                dot.pack_propagate(False)
                
                lbl_weight = "bold" if row_idx == 1 else "normal"
                lbl = ctk.CTkLabel(inner, text=metric_name, font=ctk.CTkFont(size=14, weight=lbl_weight), text_color="#f5e0dc")
                lbl.pack(side="left")
                row_labels[row_idx].append(lbl)
                col_labels[0].append(lbl)
                label_default_colors[lbl] = "#f5e0dc"

                for widget in (cell_frame, inner, dot, lbl):
                    widget.bind("<Button-1>", lambda e, r=row_idx: on_row_click(r))
                    widget.bind("<Enter>", lambda e, r=row_idx: on_enter(e, r))
                    widget.bind("<Leave>", lambda e, r=row_idx: on_leave(e, r))

                for col_idx, col_key in enumerate(["Total", "Real", "Fake", "Misinfo", "Satire", "Clickbait"], start=1):
                    is_last_col = (col_idx == 6)
                    val_cell_frame = ctk.CTkFrame(grid_frame, fg_color=bg_color, corner_radius=6 if is_last_col else 0, border_width=0, cursor="hand2")
                    val_cell_frame.grid(row=row_idx, column=col_idx, sticky="nsew", padx=(0, 0 if is_last_col else 2), pady=1)
                    row_cells[row_idx].append(val_cell_frame)
                    col_cells[col_idx].append((row_idx, val_cell_frame))
                    
                    val = stats[col_key][metric_name]
                    text_color = "#f5e0dc" if val > 0 else "#6c7086"
                    weight = "bold" if val > 0 or row_idx == 1 else "normal"
                    
                    inner_val_frame = ctk.CTkFrame(val_cell_frame, fg_color="transparent")
                    inner_val_frame.pack(expand=True, pady=12)
                    
                    v_lbl = ctk.CTkLabel(inner_val_frame, text=str(val), font=ctk.CTkFont(size=14, weight=weight), text_color=text_color)
                    v_lbl.pack(side="left")
                    row_labels[row_idx].append(v_lbl)
                    col_labels[col_idx].append(v_lbl)
                    label_default_colors[v_lbl] = text_color
                    
                    vertical_pct = None
                    horizontal_pct = None
                    if row_idx > 1 and val > 0:
                        # --- Vertical Calculation ---
                        v_denom = 0
                        
                        # Sum up all modality items for this column to ensure vertical percentages sum to 100%
                        # excluding items that have no text, image, or video.
                        modality_sum = sum(stats[col_key][m] for m in [
                            "Text Only", "Image Only", "Video Only", 
                            "Text + Image", "Text + Video", "Image + Video", 
                            "Text + Image + Video"
                        ])
                        
                        if col_key in ["Real", "Fake"]:
                            v_denom = modality_sum
                        elif col_key in ["Misinfo", "Satire", "Clickbait"]:
                            # For subclasses, we want their vertical sum to add up to 100% of their own modality sum
                            # Wait, the prompt says "won't it be 100%". 
                            # If col is Misinfo, then v_denom = Misinfo modality_sum.
                            # So Misinfo modalities sum to 100% of Misinfo.
                            v_denom = modality_sum
                            
                        if v_denom > 0:
                            vertical_pct = int(round((val / v_denom) * 100))
                            
                        # --- Horizontal Calculation ---
                        h_denom = 0
                        if col_key in ["Real", "Fake"]:
                            h_denom = stats["Total"][metric_name]
                        elif col_key in ["Misinfo", "Satire", "Clickbait"]:
                            h_denom = stats["Fake"][metric_name]
                            
                        if h_denom > 0:
                            horizontal_pct = int(round((val / h_denom) * 100))

                    pct_lbl = None
                    if vertical_pct is not None or horizontal_pct is not None:
                        v_text = f"({vertical_pct}%)" if vertical_pct is not None else ""
                        h_text = f"({horizontal_pct}%)" if horizontal_pct is not None else ""
                        # We initialize with text="" to hide it visually without crashing CTk
                        pct_lbl = ctk.CTkLabel(inner_val_frame, text="", font=ctk.CTkFont(size=12, weight="bold"), text_color="#9399b2")
                        pct_lbl._stored_vertical_text = v_text
                        pct_lbl._stored_horizontal_text = h_text
                        
                        pct_lbl._vertical_highlight_color = "#bac2de"
                        if col_key in ["Misinfo", "Satire", "Clickbait"]:
                            pct_lbl._horizontal_highlight_color = "#fab387" # Soft orange to differentiate
                        else:
                            pct_lbl._horizontal_highlight_color = "#bac2de"
                            
                        pct_lbl.pack(side="left", padx=(6, 0))
                        row_labels[row_idx].append(pct_lbl)
                        col_labels[col_idx].append(pct_lbl)
                        label_default_colors[pct_lbl] = "HIDDEN_PCT"

                    val_cell_frame.bind("<Button-1>", lambda e, c=col_idx: on_col_click(c))
                    val_cell_frame.bind("<Enter>", lambda e, r=row_idx: on_enter(e, r))
                    val_cell_frame.bind("<Leave>", lambda e, r=row_idx: on_leave(e, r))
                    inner_val_frame.bind("<Button-1>", lambda e, c=col_idx: on_col_click(c))
                    inner_val_frame.bind("<Enter>", lambda e, r=row_idx: on_enter(e, r))
                    inner_val_frame.bind("<Leave>", lambda e, r=row_idx: on_leave(e, r))
                    v_lbl.bind("<Button-1>", lambda e, c=col_idx: on_col_click(c))
                    v_lbl.bind("<Enter>", lambda e, r=row_idx: on_enter(e, r))
                    v_lbl.bind("<Leave>", lambda e, r=row_idx: on_leave(e, r))
                    if pct_lbl:
                        pct_lbl.bind("<Button-1>", lambda e, c=col_idx: on_col_click(c))
                        pct_lbl.bind("<Enter>", lambda e, r=row_idx: on_enter(e, r))
                        pct_lbl.bind("<Leave>", lambda e, r=row_idx: on_leave(e, r))
            
            active_export_data = export_rows

        def on_filter_change(*args):
            draw_dashboard()

        category_menu = ctk.CTkOptionMenu(top_frame, values=category_options, variable=category_var, command=on_filter_change, fg_color="#313244", button_color="#4f46e5", button_hover_color="#5c5cff", font=ctk.CTkFont(size=13, weight="bold"))
        category_menu.pack(side="left", padx=(0, 10))
        annotator_menu = ctk.CTkOptionMenu(top_frame, values=annotator_options, variable=annotator_var, command=on_filter_change, fg_color="#313244", button_color="#4f46e5", button_hover_color="#5c5cff", font=ctk.CTkFont(size=13, weight="bold"))
        annotator_menu.pack(side="left")

        def export_csv():
            is_global_export = self.global_metrics_enabled.get()
            export_all_categories = False

            if not is_global_export:
                export_choice = self._ask_detailed_stats_export_scope(popup)
                if export_choice is None:
                    return
                export_all_categories = (export_choice == "all")

            selected_annotator = annotator_var.get()

            if export_all_categories:
                scoped_records = self._filter_detailed_stats_records(
                    all_records, "All Categories", selected_annotator
                )
                if not scoped_records:
                    messagebox.showinfo("Export", "No local data to export.", parent=popup)
                    return

                present_categories = {
                    (r.get("category") or "").strip()
                    for r in scoped_records
                    if (r.get("category") or "").strip()
                }
                preferred_categories = [c for c in CATEGORIES if c in present_categories]
                extra_categories = sorted(present_categories - set(preferred_categories))
                categories_to_export = ["All Categories"] + preferred_categories + extra_categories
                initialfile = "detailed_statistics_all_categories.csv"
            else:
                if not active_export_data:
                    messagebox.showinfo("Export", "No data to export.", parent=popup)
                    return
                initialfile = "detailed_statistics_current.csv"
            
            filepath = filedialog.asksaveasfilename(
                parent=popup,
                defaultextension=".csv",
                initialfile=initialfile,
                title="Save Detailed Statistics as CSV",
                filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
            )
            if filepath:
                try:
                    with open(filepath, "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow(["Scope", "Team" if is_global_export else "Local"])
                        writer.writerow(["Export", "All Categories" if export_all_categories else "Current Dashboard"])
                        writer.writerow(["Category", "All Categories" if export_all_categories else category_var.get()])
                        writer.writerow(["Annotator", selected_annotator])
                        writer.writerow([])

                        if export_all_categories:
                            for cat in categories_to_export:
                                if cat == "All Categories":
                                    category_records = scoped_records
                                else:
                                    category_records = self._filter_detailed_stats_records(
                                        scoped_records, cat, "All Annotators"
                                    )
                                if not category_records:
                                    continue

                                category_stats = self._compute_detailed_stats_for_records(category_records)
                                writer.writerow([f"=== CATEGORY: {cat.upper()} ==="])
                                writer.writerows(self._detailed_stats_export_rows(category_stats))
                                writer.writerow([])
                        else:
                            writer.writerows(active_export_data)
                            
                    messagebox.showinfo("Success", f"Statistics successfully exported to:\n{filepath}", parent=popup)
                except Exception as e:
                    messagebox.showerror("Export Failed", f"An error occurred while saving:\n{e}", parent=popup)

        # Bottom Frame
        bottom_frame = ctk.CTkFrame(popup, fg_color="transparent")
        bottom_frame.pack(fill="x", padx=24, pady=(0, 24))

        ctk.CTkButton(bottom_frame, text="Close", command=popup.destroy,
                       height=40, font=ctk.CTkFont(size=14, weight="bold"),
                       fg_color="transparent", border_width=1,
                       border_color="#555", width=120).pack(side="right", padx=(10, 0))
                       
        ctk.CTkButton(bottom_frame, text="📥 Export to CSV", command=export_csv,
                       height=40, font=ctk.CTkFont(size=14, weight="bold"),
                       fg_color="#313244", hover_color="#45475a", width=140).pack(side="right")

        # Initial draw
        popup.redraw_cmd = draw_dashboard
        draw_dashboard()

    # REVIEW MODE

    # REVIEW MODE

    def _toggle_mode(self, mode_name):
        """
        Manages transitions between Annotate, Review, and Re-label modes.
        
        This method acts as a router/coordinator when switching between application views.
        Before completing a switch, it checks for unsaved changes in the active mode
        and prompts the user appropriately. On successful confirmation, it performs
        the following setup steps:
        - Annotate mode: Restores the cached layout grid, switches primary buttons 
          to "Save Entry", recovers draft inputs, and updates statistics.
        - Review mode: Ingests the primary CSV database, updates primary buttons to 
          "Update Entry", reveals record navigation controls, and applies active filters.
        - Re-label mode: Ingests the kappa reliability dataset, makes primary article
          fields read-only, hides secondary inputs (like category or confidence), 
          adjusts container widths, and searches for the first unlabeled record.
        """
        # Save reference of the mode we are switching away from
        previous_mode = self.current_mode

        # Case 1: Switching to standard Annotate Mode
        if "Annotate" in mode_name:
            # If the application is already in annotate mode, do nothing
            if self.current_mode == "annotate":
                return
            
            # If leaving Review mode, check for unsaved edits on the active record first
            if self.current_mode == "review":
                if not self._check_unsaved_changes():
                    # Revert the dropdown selector if the user aborted the switch
                    self.mode_switcher.set("🔍 Review")
                    return
            
            # If leaving Re-label mode, check for unsaved decisions on the active reliability record
            if self.current_mode == "relabel":
                if not self._check_unsaved_kappa_changes():
                    # Revert the dropdown selector if the user aborted the switch
                    self.mode_switcher.set("🔄 Re-label")
                    return
                # Restore editing layouts modified specifically for Re-label mode
                self._exit_relabel_mode()
            
            # Set the internal state indicator to annotate mode
            self.current_mode = "annotate"
            
            # Hide navigation panels and filter settings widgets from the top bar
            self.nav_frame.grid_forget()
            self.filter_btn.pack_forget()
            self.filter_indicator.pack_forget()
            
            # Configure primary button to trigger entry save logic
            self.primary_btn.configure(text="💾  Save Entry", command=self._save_entry)
            self.primary_btn.pack_configure(padx=(0, 8))
            
            # Re-enable the secondary 'Clear All' button next to the save button
            self.secondary_btn.configure(text="🗑  Clear All", command=self._clear_all,
                                           fg_color="#444", hover_color="#555")
            self.secondary_btn.pack(side="left")
            
            # Restore regular annotation layouts, reload draft changes if cached, and refresh statistics
            self._restore_annotate_fields()
            self._restore_draft()
            self._update_stats()
            
        # Case 2: Switching to Review Mode (browsing previously saved records)
        elif "Review" in mode_name:
            # If the application is already in review mode, do nothing
            if self.current_mode == "review":
                return
            
            # Ensure any incomplete annotations in Annotate mode are saved or discarded
            if self.current_mode == "annotate":
                if not self._check_unsaved_annotate_changes():
                    self.mode_switcher.set("📝 Annotate")
                    return
            
            # Ensure any incomplete blind ratings in Re-label mode are resolved
            if self.current_mode == "relabel":
                if not self._check_unsaved_kappa_changes():
                    self.mode_switcher.set("🔄 Re-label")
                    return
                self._exit_relabel_mode()
            
            # Set the internal state indicator to review mode
            self.current_mode = "review"
            
            # Restore normal input fields that might have been hidden by Re-label mode
            self._restore_annotate_fields()
            
            # Load entries from the database file
            self._load_dataset()
            
            # If there are no saved records in dataset.csv, return to Annotate mode
            if not self.all_dataset_records:
                messagebox.showinfo("No Data",
                    "No entries found in dataset.csv.\nAnnotate some entries first!")
                self.mode_switcher.set("📝 Annotate")
                self.current_mode = "annotate"
                self._restore_draft()
                self._update_stats()
                return
                
            # Configure primary action button to trigger update modifications
            self.primary_btn.configure(text="💾  Update Entry", command=self._update_entry)
            self.primary_btn.pack_configure(padx=(0, 8))
            
            # Reconfigure secondary action button to serve as a delete button
            self.secondary_btn.configure(text="🗑  Delete", command=self._delete_entry,
                                          fg_color="#e74c3c", hover_color="#c0392b")
            self.secondary_btn.pack(side="left")
            
            # Make the record navigation bar and filter widgets visible
            self.nav_frame.grid(row=0, column=0, sticky="ew", padx=(8, 8), pady=6)
            self.filter_btn.pack(side="right", padx=(4, 0))
            self.filter_indicator.pack(side="right", padx=(4, 0))
            self._update_filter_indicator()
            
        # Case 3: Switching to Re-label (Kappa reliability check) Mode
        elif "Re-label" in mode_name:
            # If the application is already in relabel mode, do nothing
            if self.current_mode == "relabel":
                return
            
            # Ensure any unsaved reviews are committed or discarded first
            if self.current_mode == "review":
                if not self._check_unsaved_changes():
                    self.mode_switcher.set("🔍 Review")
                    return
            
            # Ensure any incomplete workspace entries in Annotate mode are resolved
            if self.current_mode == "annotate":
                if not self._check_unsaved_annotate_changes():
                    self.mode_switcher.set("📝 Annotate")
                    return
            
            # Set the internal state indicator to relabel mode
            self.current_mode = "relabel"
            
            # Trigger layout transformations and load the Kappa CSV file
            self._enter_relabel_mode()

    def _load_dataset(self):
        """
        Loads all records from the dataset CSV file into memory for review.
        
        Reads rows from dataset.csv, converting them into dictionaries, and then 
        applies the advanced checklist/filter criteria to populate the active subset.
        """
        # Reset the master records container list
        self.all_dataset_records = []
        
        # If the dataset CSV does not exist or is empty, initialize empty lists and return
        if not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0:
            self.dataset_records = []
            return
        
        # Read the file contents as dictionaries and append them to the master list
        with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.all_dataset_records.append(row)
                
        # Apply the active advanced filter settings to construct the subset list (dataset_records)
        self._apply_advanced_filter()

    def _display_record(self, index):
        """
        Populates all UI input and display fields with data from a specific record.
        
        Handles:
        - Enabling/disabling Prev/Next navigation buttons according to record bounds.
        - Updating the record counter indicator entry box.
        - Populating text fields, category select menus, confidence metrics, and notes.
        - Extracting and loading image arrays (verifying file paths relative to script).
        - Handling attached video playbacks or noting missing assets.
        
        Args:
            index: Zero-based integer index of the record inside dataset_records.
        """
        # Bounds check: do nothing if index is out of range or list is empty
        if not self.dataset_records or index < 0 or index >= len(self.dataset_records):
            return

        # Fetch the active record dictionary from the loaded subset
        record = self.dataset_records[index]

        # Get total records size for display configuration
        total = len(self.dataset_records)
        
        # Enable the index field to update the record counter text
        self.record_index_entry.configure(state="normal")
        self.record_index_entry.delete(0, "end")
        self.record_index_entry.insert(0, str(index + 1))
        self.record_total_label.configure(text=f"of {total}")
        
        # Disable navigation buttons at the boundaries of the list to prevent out-of-bounds errors
        self.prev_btn.configure(state="normal" if index > 0 else "disabled")
        self.next_btn.configure(state="normal" if index < total - 1 else "disabled")

        # Wipe all existing inputs in the workspace to prepare for the new record's properties
        self._clear_fields()

        # Insert the annotator name associated with this record
        self.annotator_entry.delete(0, "end")
        self.annotator_entry.insert(0, record.get("annotator") or "")

        # Set the Real/Fake classification label dropdown
        label = record.get("label") or ""
        if label:
            self.label_var.set(label)
            # Trigger the label change event handler to load/hide subcategory options
            self._on_label_change()

        # If labeled as Fake, set the subcategory news type selector dropdown
        multi_cat = record.get("multi_category") or ""
        if label == "Fake" and multi_cat in MULTI_CATEGORIES:
            self.multi_cat_var.set(multi_cat)

        # Set news category and platform source dropdown variables
        self.category_var.set(record.get("category") or "")
        self.source_cat_var.set(record.get("source_category") or "")

        # Insert the reference URL link or source description
        self.source_entry.delete(0, "end")
        self.source_entry.insert(0, record.get("source") or "")

        # Populate the additional annotator notes box
        self.notes_entry.delete("0.0", "end")
        notes = record.get("additional_notes") or ""
        if notes:
            self.notes_entry.insert("0.0", notes)

        # Populate the article headline title box
        self.heading_entry.delete("1.0", "end")
        heading = record.get("heading") or ""
        if heading:
            self.heading_entry.insert("1.0", heading)
        self._update_heading_search_visibility()

        # Populate the core news body text box
        self.text_box.delete("1.0", "end")
        text = record.get("text") or ""
        if text:
            self.text_box.insert("1.0", text)

        # Insert the confidence percentage metric value
        self.confidence_entry.delete(0, "end")
        self.confidence_entry.insert(0, record.get("annotation_confidence") or "100")

        # Reset media lists and missing asset references
        self.image_list.clear()
        self.video_path = None
        self.missing_media = []
        
        # Load and verify the attached video path if registered
        video_path_str = record.get("video_path") or ""
        if video_path_str:
            full_vid_path = SCRIPT_DIR / video_path_str
            if full_vid_path.exists():
                self.video_path = full_vid_path
            else:
                # Keep track of missing file references to notify the user
                self.missing_media.append(("video", video_path_str))
                
        # Parse and verify semicolon-delimited image paths
        image_paths = record.get("image_path") or ""
        if image_paths:
            for rel_path in image_paths.split(";"):
                rel_path = rel_path.strip()
                if rel_path:
                    full_path = SCRIPT_DIR / rel_path
                    if full_path.exists():
                        # Store verified path with a None placeholder for the PIL Image object
                        self.image_list.append((full_path, None))
                    else:
                        # Keep track of missing file references to notify the user
                        self.missing_media.append(("image", rel_path))
                        
        # Render the image previews and trigger placeholder graphics for missing files
        self._refresh_previews()

    def _check_unsaved_annotate_changes(self):
        """
        Checks for any unsaved changes when leaving Annotate mode.
        
        Reviews all input fields, text areas, dropdowns, and media slots. If any 
        contain values, prompts the user to save as a record, discard the current
        entries, or cancel the mode switch entirely.
        
        Returns:
            bool: True if safe to leave (confirmed save/discard or empty fields),
                  False if the user chose to cancel/stay.
        """
        # Flag indicating whether the workspace has modified unsaved elements
        changed = False
        
        # Sequentially check every input field to see if the user has entered any data.
        # If any element has a non-default value, we set the changed flag to True.
        if self.label_var.get() != "": changed = True
        elif self.heading_entry.get("1.0", "end-1c").strip() != "": changed = True
        elif self.text_box.get("1.0", "end-1c").strip() != "": changed = True
        elif self.source_entry.get().strip() != "": changed = True
        elif self.source_cat_var.get() != "": changed = True
        elif self.category_var.get() != "": changed = True
        elif self.multi_cat_var.get() != "": changed = True
        # A confidence score of "100" or empty string counts as default, other values denote edits
        elif self.confidence_entry.get().strip() not in ("", "100"): changed = True
        elif self.notes_entry.get("0.0", "end-1c").strip() != "": changed = True
        # Check if the user has loaded images or videos into the media bins
        elif len(self.image_list) > 0: changed = True
        elif self.video_path is not None: changed = True

        # If changes are detected, prompt the user with a decision dialog box
        if changed:
            ans = messagebox.askyesnocancel("Unsaved Entry",
                "You have started an annotation but haven't saved it.\n\n"
                "Do you want to save it now?\n"
                "(Yes = Save, No = Discard, Cancel = Stay)")
            
            # Action A: User clicked 'Cancel' (stay on the current page and abort mode toggle)
            if ans is None:
                return False
            
            # Action B: User clicked 'Yes' (commit the new annotation first)
            elif ans is True:
                # Attempt to save the entry. If validation checks fail, prevent leaving the mode.
                if not self._save_entry():
                    return False
            
            # Action C: User clicked 'No' (explicitly discard changes and clean the workspaces)
            else:
                self._clear_fields()
                
        # Safe to navigate
        return True

    def _check_unsaved_changes(self):
        """
        Checks for unsaved changes in the current review record before navigating away.
        
        Compares all UI input states against the original values stored in dataset_records.
        Inspects textual fields, category dropdowns, confidence levels, additional notes,
        image attachments, and video directories.
        
        Returns:
            bool: True if navigation can proceed (no changes or confirmed save/discard),
                  False if the navigation should be aborted.
        """
        # If there are no records in memory, we can navigate freely
        if not self.dataset_records or self.current_review_index < 0:
            return True
            
        # Retrieve the original database record dictionary for direct value comparison
        record = self.dataset_records[self.current_review_index]
        
        # Read the current values of all workspace fields in the UI
        annotator = self.annotator_entry.get().strip()
        label = self.label_var.get()
        heading = self.heading_entry.get("1.0", "end-1c").strip()
        text = self.text_box.get("1.0", "end-1c").strip()
        source = self.source_entry.get().strip()
        source_category = self.source_cat_var.get()
        category = self.category_var.get()
        # Set the subcategory classification conditionally based on label (Fake vs Real)
        multi_cat = self.multi_cat_var.get() if label == "Fake" else ("Real" if label == "Real" else "")
        confidence = self.confidence_entry.get().strip()
        notes = self.notes_entry.get("0.0", "end-1c").strip()
        
        # Track changes indicator
        changed = False
        
        # Check standard textual fields and combobox select values against original values
        if annotator != (record.get("annotator") or "").strip(): changed = True
        elif label != (record.get("label") or "").strip(): changed = True
        elif heading != (record.get("heading") or "").strip(): changed = True
        elif text != (record.get("text") or "").strip(): changed = True
        elif source != (record.get("source") or "").strip(): changed = True
        elif source_category != (record.get("source_category") or "").strip(): changed = True
        elif category != (record.get("category") or "").strip(): changed = True
        elif multi_cat != (record.get("multi_category") or "").strip(): changed = True
        elif confidence != (record.get("annotation_confidence") or "100").strip(): changed = True
        elif notes != (record.get("additional_notes") or "").strip(): changed = True
        
        # Check image selection list for differences if text comparison did not flag changes
        if not changed:
            # Parse saved image paths from CSV (splitting by semicolon and replacing backslashes for path normalization)
            orig_images = [p.strip().replace("\\", "/") for p in (record.get("image_path") or "").split(";") if p.strip()]
            
            # An altered list length immediately denotes modified assets lists
            if len(self.image_list) != len(orig_images):
                changed = True
            else:
                # Zip lists together and inspect path strings element by element
                for (path, pil_img), orig_rel_path in zip(self.image_list, orig_images):
                    # If path is None, it is a newly pasted screenshot image in memory, denoting changes
                    if path is None:
                        changed = True
                        break
                    try:
                        # Extract path relative to script directory to check against CSV storage pattern
                        rel = path.relative_to(SCRIPT_DIR)
                        if str(rel).replace("\\", "/") != orig_rel_path:
                            changed = True
                            break
                    except ValueError:
                        changed = True
                        break
                
            # Check video references for changes
            if not changed:
                orig_video = (record.get("video_path") or "").strip().replace("\\", "/")
                current_video = ""
                if self.video_path:
                    try:
                        current_video = str(self.video_path.relative_to(SCRIPT_DIR)).replace("\\", "/")
                    except ValueError:
                        # Video path outside the local folder workspace signals a new upload change
                        changed = True
                
                # Check for updates to the video path reference
                if not changed and orig_video != current_video:
                    changed = True

        # If no edits are detected, proceed with navigation
        if not changed:
            return True
            
        # Prompt user with an action selection dialog for unsaved review edits
        response = messagebox.askyesnocancel(
            "Unsaved Changes",
            "You have unsaved changes in this record.\n\n"
            "Do you want to save them before moving?"
        )
        
        # User choice Yes: attempt to save the active record edits
        if response is True:
            # Update the CSV database silently (without showing the generic confirmation alert)
            save_ok = self._update_entry(show_success=False)
            if not save_ok:
                # If save fails due to validation errors, offer a fallback to discard changes
                # to prevent the user from being trapped in an infinite error loop.
                discard = messagebox.askyesno(
                    "Save Failed",
                    "Could not save due to validation errors.\n\n"
                    "Do you want to discard your changes and continue?"
                )
                return discard
            return True
            
        # User choice No: discard modifications and allow navigation
        elif response is False:
            return True
            
        # User choice Cancel: remain on the current record
        else:
            return False

    def _next_record(self):
        """
        Navigates to the next record in the dataset subset.
        
        If currently in Re-label mode, delegates the navigation step to the kappa
        next record handler. Otherwise, verifies for unsaved edits in the active
        record. If safe, increments the review index pointer and displays the record.
        """
        # Route to the Kappa reliability navigation handler if the application is in Re-label mode
        if self.current_mode == "relabel":
            self._kappa_next_record()
            return
            
        # Ensure we are not already at the end of the loaded review subset
        if self.current_review_index < len(self.dataset_records) - 1:
            # Prompt user to resolve any unsaved changes before moving to the next record
            if not self._check_unsaved_changes():
                return
            # Increment index pointer and refresh UI layout fields with the next record
            self.current_review_index += 1
            self._display_record(self.current_review_index)

    def _prev_record(self):
        """
        Navigates to the previous record in the dataset subset.
        
        If currently in Re-label mode, delegates the navigation step to the kappa
        prev record handler. Otherwise, verifies index limits and checks for unsaved
        changes before decrementing the review index pointer and displaying the record.
        """
        # Route to the Kappa reliability navigation handler if the application is in Re-label mode
        if self.current_mode == "relabel":
            self._kappa_prev_record()
            return
            
        # Ensure we are not already at the beginning of the loaded review subset
        if self.current_review_index > 0:
            # Prompt user to resolve any unsaved changes before moving to the previous record
            if not self._check_unsaved_changes():
                return
            # Decrement index pointer and refresh UI layout fields with the previous record
            self.current_review_index -= 1
            self._display_record(self.current_review_index)

    def _jump_to_record(self, event=None):
        """
        Navigates directly to a record specified by the integer input in the navigation box.
        
        Converts the 1-based user input into a 0-based index. Validates the index bounds,
        verifies for unsaved edits, updates the review pointer, and displays the record.
        Reverts the navigation input box to the current index if invalid.
        """
        # Route to the Kappa reliability jump handler if the application is in Re-label mode
        if self.current_mode == "relabel":
            self._kappa_jump_to_record(event)
            return
            
        try:
            # Parse the user entry value as a 1-based record number
            val = int(self.record_index_entry.get().strip())
            # Convert to zero-based array index
            idx = val - 1
            
            # Ensure the targeted index lies within the boundaries of the active review list
            if 0 <= idx < len(self.dataset_records):
                # Only execute jump operations if the target index differs from the active one
                if self.current_review_index != idx:
                    # Check for unsaved changes before executing the index jump
                    if not self._check_unsaved_changes():
                        # Revert input entry text back to the active record number on navigation cancel
                        self.record_index_entry.delete(0, "end")
                        self.record_index_entry.insert(0, str(self.current_review_index + 1))
                        self.focus_set()
                        return
                    # Update index pointer and draw record data
                    self.current_review_index = idx
                    self._display_record(self.current_review_index)
                # Release keyboard focus from the input field to prevent cursor navigation conflicts
                self.focus_set()
            else:
                # Revert to current record indicator if user inputs an out-of-range index
                self.record_index_entry.delete(0, "end")
                self.record_index_entry.insert(0, str(self.current_review_index + 1))
                messagebox.showwarning("Invalid Record", f"Please enter a number between 1 and {len(self.dataset_records)}.")
        except ValueError:
            # Revert to current record indicator if user inputs a non-integer string
            self.record_index_entry.delete(0, "end")
            self.record_index_entry.insert(0, str(self.current_review_index + 1))

    def _update_entry(self, show_success=True):
        """
        Validates the UI input fields and commits changes to the current database record.
        
        Performs field requirement checks (e.g. category, source, non-empty media/text content).
        Copies any new external files (images or video clips) into local project storage sub-folders,
        generating unique filenames containing labels, counts, entry UUIDs, and annotator names.
        Saves new screenshots directly as PNGs.
        Rewrites the main database CSV file, updates dynamic filters, and updates the stats bar.
        
        Args:
            show_success: If True, displays a completion alert popup window.
            
        Returns:
            bool: True if validation and disk saving succeeded, False otherwise.
        """
        # Abort if there are no loaded review records in memory
        if not self.dataset_records:
            return False

        # Gather current string values from workspace widgets
        annotator = self.annotator_entry.get().strip()
        label = self.label_var.get()
        heading = self.heading_entry.get("1.0", "end-1c").strip()
        text = self.text_box.get("1.0", "end-1c").strip()
        source = self.source_entry.get().strip()
        source_category = self.source_cat_var.get()
        category = self.category_var.get()
        multi_cat = self.multi_cat_var.get()
        confidence_str = self.confidence_entry.get().strip()
        
        # Check for media attachments presence
        has_image = len(self.image_list) > 0
        has_media = has_image or (self.video_path is not None)

        # Enforce validation checks on mandatory inputs
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
        # Ensure there is at least one modal source (text description or file attachments)
        if not text and not has_media:
            errors.append("At least one of Text, Image, or Video must be provided.")

        # Parse and validate the confidence score field
        confidence = 100
        if confidence_str:
            try:
                confidence = int(confidence_str)
                # Bounded percentage value checks
                if not (0 <= confidence <= 100):
                    errors.append("Annotation Confidence must be between 0 and 100.")
            except ValueError:
                errors.append("Annotation Confidence must be a valid integer.")

        # Show verification errors to the user and abort transaction if validation failed
        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors))
            return False

        # Map Fake News Type subclass value to Real if the authenticity label is set to Real
        if label == "Real":
            multi_cat = "Real"

        # Retrieve entry ID and sanitize the annotator name for safe filename conversions
        record = self.dataset_records[self.current_review_index]
        entry_id = record.get("id") or generate_id()
        sanitized_annotator = sanitize_name(annotator)

        # Process image attachments list (keeping local paths, copying new uploads, writing screen captures)
        try:
            image_rel_paths = []
            for path, pil_img in self.image_list:
                if path:
                    try:
                        # If the path is already inside the local script folder, retain relative path format
                        rel = path.relative_to(SCRIPT_DIR)
                        image_rel_paths.append(str(rel).replace("\\", "/"))
                    except ValueError:
                        # Copy new external image files into the images sub-folder
                        img_count = get_image_count() + 1
                        ext = path.suffix.lower()
                        # Construct a unique, standard filename
                        img_filename = f"{label}_{img_count:05d}_{entry_id}_{sanitized_annotator}{ext}"
                        img_dest = IMAGES_DIR / img_filename
                        shutil.copy2(path, img_dest)
                        image_rel_paths.append(f"images/{img_filename}")
                else:
                    # Write pasted screenshot image objects directly to local disk as PNGs
                    img_count = get_image_count() + 1
                    img_filename = f"{label}_{img_count:05d}_{entry_id}_{sanitized_annotator}.png"
                    img_dest = IMAGES_DIR / img_filename
                    src_img = pil_img
                    # Ensure compatibility with RGB formatting
                    if src_img.mode == "RGBA":
                        src_img = src_img.convert("RGB")
                    src_img.save(img_dest)
                    image_rel_paths.append(f"images/{img_filename}")
    
            # Process video files attachments (copying external files if applicable)
            video_rel_path = ""
            if self.video_path:
                try:
                    # Retain relative path format if video is already located inside the project folders
                    rel = self.video_path.relative_to(SCRIPT_DIR)
                    video_rel_path = str(rel).replace("\\", "/")
                except ValueError:
                    # Copy external video file into the videos directory
                    vid_count = get_video_count() + 1
                    ext = self.video_path.suffix.lower()
                    # Construct a unique standard video filename
                    vid_filename = f"{label}_{vid_count:05d}_{entry_id}_{sanitized_annotator}{ext}"
                    vid_dest = VIDEOS_DIR / vid_filename
                    shutil.copy2(self.video_path, vid_dest)
                    video_rel_path = f"videos/{vid_filename}"
    
            # Assign modified UI values back to the active record dictionary
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
            record["video_path"] = video_rel_path
            
            # Maintain original save timestamp or populate if missing
            if "timestamp" not in record or not record.get("timestamp"):
                record["timestamp"] = datetime.now().isoformat()
    
            # Commit the updated list values to dataset.csv
            self._rewrite_csv()
        except Exception as e:
            # Notify on OS-level errors (like files locked by external editors)
            messagebox.showerror("Update Error", f"Failed to update entry. Please make sure the dataset CSV file is not open in Excel or another program.\n\nError: {e}")
            return False

        # Re-apply filters to refresh the active records list (and automatically filter out records that no longer match)
        self._apply_advanced_filter(keep_index=True)
        
        # Display completion alert window if requested
        if show_success:
            messagebox.showinfo("Update Complete",
                f"Record {self.current_review_index + 1} updated successfully!")
        return True

    def _delete_entry(self):
        """
        Deletes the currently displayed record from the database after confirmation.
        
        Pops the record from the active subset and general list, rewrites the dataset CSV, 
        and updates active indices. Returns to Annotate mode if no entries remain.
        """
        # Abort if there are no loaded review records in memory
        if not self.dataset_records:
            return

        # Double check delete intent by prompting a warning dialog window
        confirm = messagebox.askyesno("Confirm Delete",
            f"Are you sure you want to delete Record {self.current_review_index + 1}?\n\n"
            "This action cannot be undone.")
        if not confirm:
            return

        # Pop the target record from the active review subset list
        deleted_record = self.dataset_records.pop(self.current_review_index)
        
        # Locate the record's index in the master dataset tracking array by matching unique entry IDs
        all_idx = next((i for i, r in enumerate(self.all_dataset_records) if (r.get("id") or "") == (deleted_record.get("id") or "")), -1)
        if all_idx >= 0:
            # Pop the record from the master tracking list in memory
            self.all_dataset_records.pop(all_idx)

        # Attempt to save the deletion modification to disk
        try:
            self._rewrite_csv()
        except Exception as e:
            # Rollback layout lists in memory if the save operation fails (e.g. permission lock errors)
            # to protect data integrity and avoid sync discrepancies.
            self.dataset_records.insert(self.current_review_index, deleted_record)
            if all_idx >= 0:
                self.all_dataset_records.insert(all_idx, deleted_record)
            messagebox.showerror("Delete Error", f"Failed to delete entry. Please make sure the dataset CSV file is not open in Excel or another program.\n\nError: {e}")
            return

        # Re-apply filter settings to refresh review index pointers and layout lists
        self._apply_advanced_filter(keep_index=True)

        # Revert view back to Annotate Mode if no records remain in the database
        if not self.all_dataset_records:
            messagebox.showinfo("No Records", "All records have been deleted.")
            self.mode_switcher.set("📝 Annotate")
            self._toggle_mode("📝 Annotate")
            return

    def _rewrite_csv(self):
        """
        Rewrites the entire dataset CSV file from the general records database list.
        """
        # Open CSV file with standard settings: newline protection and utf-8 encoding support
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            # Construct standard writer, ignoring extra unexpected keys in record dictionaries
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
            # Write column headers row first
            writer.writeheader()
            # Serialize each record dictionary to file rows sequentially
            for record in self.all_dataset_records:
                writer.writerow(record)

    def _save_draft(self):
        """
        Saves the current values of all annotation fields to a temporary draft cache.
        
        This cache prevents the annotator from losing in-progress work when toggling
        between Annotate mode and Review/Re-label modes.
        """
        # Take a snapshot of the workspace inputs and save them in memory
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
            # Copy image_list reference to preserve pasted screenshots in memory
            "images": list(self.image_list),
            "video": self.video_path,
        }

    def _restore_draft(self):
        """
        Restores the cached draft annotation values to the UI input fields.
        
        This is called when returning to Annotate mode. If no draft has been cached,
        it resets all input fields to their defaults.
        """
        # If no draft is cached, just clear fields to their defaults and return
        if self.draft_annotation is None:
            self._clear_fields()
            return

        # Load draft and reset internal draft cache reference to release memory
        draft = self.draft_annotation
        self.draft_annotation = None

        # Wipe workspace controls first
        self._clear_fields()
        
        # Populate annotator name entry field
        self.annotator_entry.delete(0, "end")
        self.annotator_entry.insert(0, draft["annotator"])

        # Populate label fields and trigger updates
        if draft["label"]:
            self.label_var.set(draft["label"])
            self._on_label_change()

        # Populate subtype dropdown menu options if applicable
        if draft["multi_cat"]:
            self.multi_cat_var.set(draft["multi_cat"])

        # Set category and source drop-down variables
        self.category_var.set(draft["category"])
        self.source_cat_var.set(draft["source_category"])

        # Populate source description input
        self.source_entry.delete(0, "end")
        self.source_entry.insert(0, draft["source"])

        # Restore heading title text content
        self.heading_entry.delete("1.0", "end")
        if draft["heading"]:
            self.heading_entry.insert("1.0", draft["heading"])

        # Restore body text description content
        self.text_box.delete("1.0", "end")
        if draft["text"]:
            self.text_box.insert("1.0", draft["text"])

        # Restore confidence rating value
        self.confidence_entry.delete(0, "end")
        self.confidence_entry.insert(0, draft["confidence"] or "100")

        # Restore additional notes text area content
        self.notes_entry.delete("0.0", "end")
        notes = draft.get("additional_notes", "")
        if notes:
            self.notes_entry.insert("0.0", notes)

        # Restore attachments lists and refresh UI previews
        self.image_list = draft["images"]
        self.video_path = draft.get("video")
        self._refresh_previews()
        self._update_heading_search_visibility()

    def _get_resource_path(self, relative_path):
        """
        Resolves paths to internal static resources, supporting both development and production.
        
        This utility resolves file references when running in python environments or packaged
        inside PyInstaller single-file executables (referencing the _MEIPASS extraction root).
        
        Args:
            relative_path: Relative path string to the desired resource file.
            
        Returns:
            str: Resolved absolute path.
        """
        try:
            # When packaged with PyInstaller, assets are unpacked to a temporary folder
            # whose path is stored in the sys._MEIPASS system attribute.
            base_path = Path(sys._MEIPASS)
        except Exception:
            # During local development, resolve the file relative to the script directory
            base_path = Path(__file__).parent.resolve()
        
        return str(base_path / relative_path)

    def _parse_version_parts(self, version):
        """
        Converts a version tag like v9.1.0 into a comparable integer tuple.
        """
        parts = [int(part) for part in re.findall(r"\d+", version or "")]
        return tuple((parts + [0, 0, 0])[:3])

    def _remote_version_is_newer(self, latest_version, current_version):
        """
        Returns True only when the remote release version is newer than the local version.
        Falls back to string comparison if either version cannot be parsed.
        """
        latest_parts = self._parse_version_parts(latest_version)
        current_parts = self._parse_version_parts(current_version)
        if any(latest_parts) or any(current_parts):
            return latest_parts > current_parts
        return (latest_version or "").strip().lower() != (current_version or "").strip().lower()

    def _build_update_info(self, release_data):
        """
        Selects the correct release asset for the current platform.
        """
        system = platform.system()
        machine = platform.machine().lower()

        if system == "Darwin":
            if "arm" in machine or "aarch" in machine:
                asset_name = "FakeNewsAnnotator-macOS-AppleSilicon.zip"
            else:
                asset_name = "FakeNewsAnnotator-macOS-Intel.zip"
            package_type = "mac_zip"
        elif system == "Windows":
            asset_name = "FakeNewsAnnotator-Windows.exe"
            package_type = "windows_exe"
        else:
            asset_name = "FakeNewsAnnotator-Linux"
            package_type = "linux_binary"

        download_url = f"{UPDATE_DOWNLOAD_BASE_URL}/{asset_name}"
        for asset in release_data.get("assets", []):
            if asset.get("name") == asset_name and asset.get("browser_download_url"):
                download_url = asset["browser_download_url"]
                break

        return {
            "version": release_data.get("tag_name", "latest"),
            "asset_name": asset_name,
            "download_url": download_url,
            "package_type": package_type,
            "system": system,
        }

    def _get_current_app_path(self):
        """
        Returns the executable or .app bundle path that should be replaced by an update.
        """
        if getattr(sys, "frozen", False):
            exe_path = Path(sys.executable).resolve()
            if platform.system() == "Darwin" and ".app/Contents/MacOS" in exe_path.as_posix():
                return exe_path.parents[2]
            return exe_path
        return Path(__file__).resolve()

    def _get_update_download_path(self, update_info):
        """
        Returns a temporary path next to the app for the downloaded release asset.
        """
        updates_dir = SCRIPT_DIR / ".updates"
        updates_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".new" if update_info["package_type"] in {"windows_exe", "linux_binary"} else ".tmp"
        return updates_dir / f"{update_info['asset_name']}{suffix}"

    def _format_download_size(self, byte_count):
        """
        Formats bytes for compact updater status text.
        """
        mb_count = byte_count / (1024 * 1024)
        return f"{mb_count:.1f} MB"

    def _queue_update_ui(self, popup, callback):
        """
        Schedules a small UI mutation from the updater worker thread.
        """
        def run_callback():
            try:
                if popup.winfo_exists():
                    callback()
            except tk.TclError:
                pass

        try:
            self.after(0, run_callback)
        except tk.TclError:
            pass

    def _check_for_updates(self):
        """
        Checks for a new release of the tool on GitHub in a background thread.

        Reads version.json to parse the local version string, performs a GET request
        to the GitHub releases API endpoint, and triggers the update alert window if
        a newer release tag is detected.
        """
        try:
            version_file = self._get_resource_path("version.json")
            if not os.path.exists(version_file):
                return

            with open(version_file, "r") as f:
                data = json.load(f)
                current_version = data.get("version", "v1.0.0").strip()

            response = requests.get(UPDATE_API_URL, timeout=5)
            if response.status_code == 200:
                release_data = response.json()
                latest_tag = release_data.get("tag_name")
                if latest_tag and self._remote_version_is_newer(latest_tag, current_version):
                    update_info = self._build_update_info(release_data)
                    self.after(2000, lambda info=update_info: self._show_update_popup(info))
        except Exception as e:
            # Silently log update check errors since updates checking is non-critical for basic operation
            print(f"Update check failed (this is non-fatal): {e}")

    def _show_update_popup(self, update_info):
        """
        Renders the in-app updater popup with download progress and cancel support.
        """
        popup = ctk.CTkToplevel(self)
        popup.title("Update Available")
        popup.geometry("560x320")
        popup.attributes("-topmost", True)

        popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - 280
        y = self.winfo_y() + (self.winfo_height() // 2) - 160
        popup.geometry(f"+{x}+{y}")

        ctk.CTkLabel(
            popup,
            text=f"🎉 A new version ({update_info['version']}) is available!",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(pady=(22, 10))

        ctk.CTkLabel(
            popup,
            text="Download and install it automatically from inside the app.",
            font=ctk.CTkFont(size=14)
        ).pack(pady=(0, 8))

        ctk.CTkLabel(
            popup,
            text=f"Package: {update_info['asset_name']}",
            font=ctk.CTkFont(size=12),
            text_color="#a6adc8"
        ).pack(pady=(0, 8))

        progress_frame = ctk.CTkFrame(popup, fg_color="transparent")
        progress_bar = ctk.CTkProgressBar(progress_frame, height=14)
        progress_bar.set(0)
        progress_bar.pack(fill="x", padx=4, pady=(4, 8))

        status_label = ctk.CTkLabel(
            progress_frame,
            text="Ready to download.",
            font=ctk.CTkFont(size=13),
            text_color="#a6adc8"
        )
        status_label.pack()

        btn_frame = ctk.CTkFrame(popup, fg_color="transparent")
        btn_frame.pack(pady=20)

        def start_update():
            if self._update_download_thread and self._update_download_thread.is_alive():
                return

            progress_frame.pack(fill="x", padx=24, pady=(8, 0))
            progress_bar.set(0)
            status_label.configure(text="Starting download...")
            update_btn.configure(state="disabled", text="Downloading...")
            close_btn.configure(state="disabled")
            cancel_btn.configure(state="normal")

            self._update_download_cancel = threading.Event()
            self._update_download_thread = threading.Thread(
                target=self._download_update_worker,
                args=(update_info, popup, progress_bar, status_label, update_btn, cancel_btn, close_btn),
                daemon=True
            )
            self._update_download_thread.start()

        def cancel_update():
            if self._update_download_cancel:
                self._update_download_cancel.set()
                status_label.configure(text="Canceling download...")
                cancel_btn.configure(state="disabled")

        def close_popup():
            if self._update_download_thread and self._update_download_thread.is_alive():
                cancel_update()
                return
            popup.destroy()

        update_btn = ctk.CTkButton(btn_frame, text="Update Now", command=start_update)
        update_btn.pack(side="left", padx=8)

        cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Cancel",
            fg_color="#7f1d1d",
            hover_color="#991b1b",
            state="disabled",
            command=cancel_update
        )
        cancel_btn.pack(side="left", padx=8)

        close_btn = ctk.CTkButton(
            btn_frame,
            text="Later",
            fg_color="transparent",
            border_width=1,
            command=close_popup
        )
        close_btn.pack(side="left", padx=8)

        popup.protocol("WM_DELETE_WINDOW", close_popup)

    def _download_update_worker(self, update_info, popup, progress_bar, status_label, update_btn, cancel_btn, close_btn):
        """
        Downloads the update in the background, then launches the platform installer script.
        """
        download_path = None
        try:
            download_path = self._get_update_download_path(update_info)
            self._download_update_file(update_info["download_url"], download_path, popup, progress_bar, status_label)

            self._queue_update_ui(
                popup,
                lambda: (
                    progress_bar.set(1),
                    status_label.configure(text="Download complete. Installing and restarting...")
                )
            )
            self._install_downloaded_update(update_info, download_path)
        except UpdateCancelled:
            if download_path:
                try:
                    download_path.unlink()
                except FileNotFoundError:
                    pass
                except Exception as e:
                    print(f"[WARNING] Could not remove canceled update download: {e}")

            self._queue_update_ui(
                popup,
                lambda: (
                    progress_bar.set(0),
                    status_label.configure(text="Download canceled."),
                    update_btn.configure(state="normal", text="Update Now"),
                    cancel_btn.configure(state="disabled"),
                    close_btn.configure(state="normal")
                )
            )
        except Exception as e:
            if download_path and download_path.exists():
                try:
                    download_path.unlink()
                except Exception:
                    pass

            error_text = f"Update failed: {e}"
            print(error_text)
            self._queue_update_ui(
                popup,
                lambda: (
                    status_label.configure(text=error_text),
                    update_btn.configure(state="normal", text="Try Again"),
                    cancel_btn.configure(state="disabled"),
                    close_btn.configure(state="normal")
                )
            )
        finally:
            self._update_download_thread = None
            self._update_download_cancel = None

    def _download_update_file(self, download_url, download_path, popup, progress_bar, status_label):
        """
        Streams a release asset to disk while updating the progress bar.
        """
        if download_path.exists():
            download_path.unlink()

        downloaded = 0
        last_ui_update = 0

        with requests.get(download_url, stream=True, timeout=(10, 60)) as response:
            response.raise_for_status()
            total_size = int(response.headers.get("content-length") or 0)

            with open(download_path, "wb") as file_obj:
                for chunk in response.iter_content(chunk_size=UPDATE_CHUNK_SIZE):
                    if self._update_download_cancel and self._update_download_cancel.is_set():
                        raise UpdateCancelled()
                    if not chunk:
                        continue

                    file_obj.write(chunk)
                    downloaded += len(chunk)

                    now = time.time()
                    if now - last_ui_update < 0.1:
                        continue

                    last_ui_update = now
                    if total_size:
                        progress = min(downloaded / total_size, 1)
                        percent = int(progress * 100)
                        status_text = (
                            f"Downloading... {percent}% "
                            f"({self._format_download_size(downloaded)} / {self._format_download_size(total_size)})"
                        )
                    else:
                        progress = 0
                        status_text = f"Downloading... {self._format_download_size(downloaded)}"

                    self._queue_update_ui(
                        popup,
                        lambda value=progress, text=status_text: (
                            progress_bar.set(value),
                            status_label.configure(text=text)
                        )
                    )

        self._queue_update_ui(
            popup,
            lambda: (
                progress_bar.set(1),
                status_label.configure(text="Download complete.")
            )
        )

    def _install_downloaded_update(self, update_info, download_path):
        """
        Creates the platform-specific updater script and exits the current app.
        """
        if not getattr(sys, "frozen", False):
            raise RuntimeError("Automatic installation is available only in the packaged app.")

        if update_info["package_type"] == "windows_exe":
            self._write_and_launch_windows_updater(download_path)
        elif update_info["package_type"] == "mac_zip":
            extract_dir = download_path.parent / "extracted"
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            extract_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(download_path, "r") as archive:
                archive.extractall(extract_dir)

            new_app_path = self._find_extracted_macos_app(extract_dir)
            if not new_app_path:
                raise RuntimeError("The downloaded macOS archive did not contain a .app bundle.")

            self._write_and_launch_posix_updater(new_app_path, download_path.parent)
        else:
            os.chmod(download_path, os.stat(download_path).st_mode | 0o755)
            self._write_and_launch_posix_updater(download_path, download_path.parent)

    def _find_extracted_macos_app(self, extract_dir):
        """
        Locates the .app bundle inside a downloaded macOS release zip.
        """
        expected_app = extract_dir / "FakeNewsAnnotator.app"
        if expected_app.exists():
            return expected_app

        for app_path in extract_dir.rglob("*.app"):
            if "__MACOSX" not in app_path.parts:
                return app_path

        return None

    def _write_and_launch_windows_updater(self, new_file_path):
        """
        Writes a batch updater that swaps the Windows executable after this process exits.
        """
        target_path = self._get_current_app_path()
        script_path = new_file_path.parent / "updater.bat"
        backup_path = target_path.with_suffix(target_path.suffix + ".old")

        script = f"""@echo off
setlocal enabledelayedexpansion
set "TARGET={target_path}"
set "NEWFILE={new_file_path}"
set "BACKUP={backup_path}"
set RETRIES=0
timeout /t 2 /nobreak >nul
if exist "%BACKUP%" del /f /q "%BACKUP%" >nul 2>&1
:wait_for_exit
if exist "%TARGET%" (
    move /y "%TARGET%" "%BACKUP%" >nul 2>&1
    if errorlevel 1 (
        set /a RETRIES+=1
        if !RETRIES! GEQ 30 exit /b 1
        timeout /t 1 /nobreak >nul
        goto wait_for_exit
    )
)
move /y "%NEWFILE%" "%TARGET%" >nul
if errorlevel 1 (
    if exist "%BACKUP%" move /y "%BACKUP%" "%TARGET%" >nul
    exit /b 1
)
if exist "%BACKUP%" del /f /q "%BACKUP%" >nul 2>&1
start "" "%TARGET%"
del "%~f0"
"""
        script_path.write_text(script, encoding="utf-8")

        try:
            subprocess.run(["attrib", "+h", str(script_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except Exception:
            pass

        creation_flags = 0
        if hasattr(subprocess, "DETACHED_PROCESS"):
            creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

        subprocess.Popen(["cmd", "/c", str(script_path)], close_fds=True, creationflags=creation_flags)
        self._schedule_exit_for_update()

    def _write_and_launch_posix_updater(self, new_item_path, cleanup_dir):
        """
        Writes a shell updater that swaps the macOS app bundle or Linux binary.
        """
        target_path = self._get_current_app_path()
        script_path = cleanup_dir / "updater.sh"

        script = f"""#!/bin/sh
TARGET={shlex.quote(str(target_path))}
NEW_ITEM={shlex.quote(str(new_item_path))}
CLEANUP_DIR={shlex.quote(str(cleanup_dir))}
BACKUP="${{TARGET}}.update-backup"
TRIES=0
sleep 2
rm -rf "$BACKUP"
if [ -e "$TARGET" ]; then
    while ! mv "$TARGET" "$BACKUP" 2>/dev/null; do
        TRIES=$((TRIES + 1))
        if [ "$TRIES" -ge 30 ]; then
            exit 1
        fi
        sleep 1
    done
fi
if mv "$NEW_ITEM" "$TARGET"; then
    rm -rf "$BACKUP"
    if [ -d "$TARGET" ]; then
        xattr -dr com.apple.quarantine "$TARGET" >/dev/null 2>&1
        /usr/bin/open "$TARGET"
    else
        chmod +x "$TARGET" >/dev/null 2>&1
        "$TARGET" >/dev/null 2>&1 &
    fi
    rm -rf "$CLEANUP_DIR"
else
    if [ -e "$BACKUP" ]; then
        mv "$BACKUP" "$TARGET" 2>/dev/null
    fi
fi
"""
        script_path.write_text(script, encoding="utf-8")
        os.chmod(script_path, 0o755)
        subprocess.Popen(["/bin/sh", str(script_path)], close_fds=True)
        self._schedule_exit_for_update()

    def _schedule_exit_for_update(self):
        """
        Gives the updater script a moment to start, then exits the running app.
        """
        try:
            self.after(500, self._exit_for_update)
        except tk.TclError:
            os._exit(0)

    def _exit_for_update(self):
        """
        Terminates the current process so the updater script can replace it.
        """
        try:
            self.destroy()
        finally:
            os._exit(0)

    # RE-LABEL (KAPPA) MODE

    def _pack_radios_vertical(self):
        """
        Arranges fake news sub-classification radio buttons vertically.
        
        Used to stack buttons inside narrow columns (e.g. in Re-label mode).
        """
        # Detach radio button widgets from their horizontal positioning layouts first
        self.radio_misinfo.pack_forget()
        self.radio_satire.pack_forget()
        self.radio_clickbait.pack_forget()
        
        # Re-pack buttons vertically to fit inside the narrow sidebar during Re-label mode
        self.radio_misinfo.pack(anchor="w", pady=(10, 10))
        self.radio_satire.pack(anchor="w", pady=(0, 10))
        self.radio_clickbait.pack(anchor="w", pady=(0, 10))

    def _pack_radios_horizontal(self):
        """
        Arranges fake news sub-classification radio buttons horizontally.
        
        Used for regular, wide window layout distributions.
        """
        # Detach radio button widgets from their vertical alignment schemes first
        self.radio_misinfo.pack_forget()
        self.radio_satire.pack_forget()
        self.radio_clickbait.pack_forget()
        
        # Pack buttons side-by-side to distribute them horizontally across wide containers
        self.radio_misinfo.pack(side="left", padx=(0, 12))
        self.radio_satire.pack(side="left", padx=(0, 12))
        self.radio_clickbait.pack(side="left")

    def _enter_relabel_mode(self):
        """
        Initializes and sets up the Re-label mode for inter-rater agreement (Kappa) analysis.
        
        This workflow:
        - Ingests the secondary rating target database file (`relabeling_for_kappa.csv`).
        - Automatically hides input components that are only relevant for standard annotation 
          (e.g., categories, source descriptions, notes) to establish a clean interface.
        - Pre-fills the annotator entry field with the configuration-persisted rating name.
        - Deactivates heading title and core text fields to make article content read-only.
        - Automatically jumps to the first record that has not yet been rated by the active annotator.
        - Formats the left-hand text column wider and right-hand options column narrower.
        - Vertically stacks news type option buttons to fit the narrow control sidebar.
        - Refreshes reliability stats badges to reflect progress count.
        """
        # Load the inter-rater reliability database file.
        # Fall back to standard annotate mode if the target file cannot be processed or is empty.
        if not self._load_kappa_csv():
            self.mode_switcher.set("📝 Annotate")
            self.current_mode = "annotate"
            self._restore_draft()
            self._update_stats()
            return

        # Hide inputs and category controls not used in blind reviews to keep raters unbiased.
        self._hide_annotate_only_fields()

        # Clear active entry fields to remove any leftovers from previous records
        self._clear_fields()

        # Pre-populate reviewer/annotator name using the saved configuration file helper
        self.annotator_entry.delete(0, "end")
        saved_name = load_config()
        if saved_name:
            self.annotator_entry.insert(0, saved_name)

        # Draw review navigation panel bar and hide advanced search filtering buttons
        self.nav_frame.grid(row=0, column=0, sticky="ew", padx=(8, 8), pady=6)
        self.filter_btn.pack_forget()
        self.filter_indicator.pack_forget()

        # Set up primary button actions and hide secondary controls (like Delete or Clear All)
        self.primary_btn.configure(text="💾  Save Decision",
                                    command=self._save_kappa_decision)
        self.primary_btn.pack_configure(padx=(0, 0))
        self.secondary_btn.pack_forget()

        # Deactivate modification access to primary textual fields (heading and main body text)
        # to ensure raters cannot modify the news content.
        self.heading_entry.configure(state="disabled")
        self.text_box.configure(state="disabled")

        # Resume rating progress from the first uncompleted sample row associated with this reviewer name
        annotator = self.annotator_entry.get().strip()
        start_idx = self._find_first_unlabeled(annotator)
        self.current_kappa_index = start_idx

        # Restructure column grid weights to make the text reading column wider (weight 3)
        # and the right-hand options column narrower (weight 1).
        self.content_container.columnconfigure(0, weight=3)
        self.content_container.columnconfigure(1, weight=1)

        # Align bottom bar navigation column weights symmetrically with the columns above
        self.bottom_bar.columnconfigure(0, weight=3, uniform="btm")
        self.bottom_bar.columnconfigure(1, weight=1, uniform="btm")
        
        # Hide category frames to conserve sidebar space
        self.category_stats_frame.pack_forget()

        # Arrange Fake News subcategory radio buttons vertically to fit the narrow sidebar
        self._pack_radios_vertical()

        # Load reliability statistics and display target record
        self._update_kappa_stats()
        if self.kappa_records:
            self._display_kappa_record(self.current_kappa_index)

    def _exit_relabel_mode(self):
        """
        Cleans up layouts and re-enables standard workspace fields when leaving Re-label mode.
        
        This resets input text modifications states, restores normal equal column widths, 
        restores category lists visibilities, resets option buttons orientation to horizontal, 
        and resets navigation pointer frames states.
        """
        # Restore horizontal category list layout frame
        self.category_stats_frame.pack(fill="x", pady=(0, 6), after=self.stats_frame)

        # Restore normal editing access to headline and text fields
        self.heading_entry.configure(state="normal")
        self.text_box.configure(state="normal")

        # Hide review navigation layouts
        self.nav_frame.grid_forget()

        # Clear inter-rater variables in memory
        self.kappa_records = []
        self.kappa_csv_columns = []
        self.current_kappa_index = 0

        # Reset column layout weights to equal distribution (1:1 ratio)
        self.content_container.columnconfigure(0, weight=1, uniform="col")
        self.content_container.columnconfigure(1, weight=1, uniform="col")

        # Reset bottom bar layout weights to equal distribution
        self.bottom_bar.columnconfigure(0, weight=1, uniform="btm")
        self.bottom_bar.columnconfigure(1, weight=1, uniform="btm")

        # Restore horizontal radio button layout orientation
        self._pack_radios_horizontal()
        
        # Ensure the reviewed badge is hidden when leaving Re-label mode
        self.done_label.configure(image=None, text="")
        self.done_indicator_frame.pack_forget()

    def _restore_annotate_fields(self):
        """
        Restores all input frames that were hidden to support the Re-label layout.
        
        Iterates over the widget references cached during the layout switch and calls pack
        with their original geometry parameters.
        """
        # Iterate through cached widgets that were hidden during relabel mode setup
        if hasattr(self, '_hidden_relabel_widgets'):
            for widget, pack_info in self._hidden_relabel_widgets:
                try:
                    # Restore widget geometry using stored packing configurations
                    widget.pack(**pack_info)
                except Exception:
                    pass
            # Wipe cache list to clean up memory
            self._hidden_relabel_widgets = []

    def _hide_annotate_only_fields(self):
        """
        Hides UI widgets that are not relevant during blind inter-rater reliability rating.
        
        Iterates through the right-hand container components, identifying and packing-forgetting 
        widgets that do not match the annotator name entry or label toggles (such as topic categories, 
        source medium dropdowns, article URLs, confidence levels, or personal comments).
        Also hides media browse and paste options to enforce read-only viewing boundaries.
        """
        self._hidden_relabel_widgets = []
        keep_widgets = set()
        right_children = list(self.right_col.winfo_children())

        # Traverse right sidebar frames to isolate annotator and label inputs
        found_annotator = False
        found_label = False

        for i, child in enumerate(right_children):
            is_section_frame = False
            section_text = ""
            if isinstance(child, ctk.CTkFrame):
                # Search frames for title text matching key headers
                for sub in child.winfo_children():
                    if isinstance(sub, ctk.CTkLabel):
                        t = sub.cget("text")
                        if t:
                            section_text = t
                            is_section_frame = True
                            break

            if is_section_frame:
                # Retain the Annotator Name section frame
                if "Annotator" in section_text:
                    found_annotator = True
                    found_label = False
                    keep_widgets.add(child)
                    continue
                # Retain the Authenticity Label section frame
                elif "Authenticity" in section_text:
                    found_annotator = False
                    found_label = True
                    keep_widgets.add(child)
                    continue
                else:
                    found_annotator = False
                    found_label = False

            # Keep the annotator entry field
            if found_annotator and child == self.annotator_entry:
                keep_widgets.add(child)
                found_annotator = False
                continue

            # Keep the parent container holding the Fake/Real buttons
            if found_label and isinstance(child, ctk.CTkFrame):
                keep_widgets.add(child)
                found_label = False
                continue

            # Keep the fine-grained type frame and status indicator label
            if child in (self.multi_cat_frame, self.done_indicator_frame):
                keep_widgets.add(child)
                continue

        # Hide widgets not selected for retention, saving packing configurations for recovery
        for child in right_children:
            if child not in keep_widgets:
                pack_info = child.pack_info() if child.winfo_manager() == "pack" else None
                if pack_info:
                    restore_info = {
                        k: v for k, v in pack_info.items()
                        if k in ('side', 'fill', 'expand', 'padx', 'pady', 'anchor',
                                 'ipadx', 'ipady')
                    }
                    self._hidden_relabel_widgets.append((child, restore_info))
                    child.pack_forget()

        # Hide browse and copy buttons frame in the media attachments panel
        for child in self.left_col.winfo_children():
            if isinstance(child, ctk.CTkFrame):
                sub_children = child.winfo_children()
                # Detect the media actions frame by checking if it contains the browse buttons
                has_browse = any(
                    isinstance(sc, ctk.CTkButton) and "Browse" in (sc.cget("text") or "")
                    for sc in sub_children
                )
                if has_browse:
                    pack_info = child.pack_info() if child.winfo_manager() == "pack" else None
                    if pack_info:
                        restore_info = {
                            k: v for k, v in pack_info.items()
                            if k in ('side', 'fill', 'expand', 'padx', 'pady', 'anchor',
                                     'ipadx', 'ipady')
                        }
                        self._hidden_relabel_widgets.append((child, restore_info))
                        child.pack_forget()
                    break

    def _load_kappa_csv(self):
        """
        Ingests the secondary annotation database file into memory.
        
        Returns:
            bool: True if loaded successfully, False if missing/empty.
        """
        # Verify that the Kappa CSV target path exists on disk and is not empty
        if not KAPPA_CSV_PATH.exists() or KAPPA_CSV_PATH.stat().st_size == 0:
            messagebox.showinfo(
                "No Kappa Data",
                f"Kappa re-labeling CSV not found:\n{KAPPA_CSV_PATH}\n\n"
                "Run generate_kappa_sample.py first to create it."
            )
            return False

        # Reset the memory records array
        self.kappa_records = []
        
        # Read the Kappa dataset records from file
        with open(KAPPA_CSV_PATH, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            # Cache the current columns header list
            self.kappa_csv_columns = list(reader.fieldnames) if reader.fieldnames else []
            for row in reader:
                self.kappa_records.append(row)

        # Alert if the file contains only headers but no data rows
        if not self.kappa_records:
            messagebox.showinfo("No Kappa Data",
                "The kappa CSV file is empty.\n"
                "Run generate_kappa_sample.py first to populate it.")
            return False

        return True

    def _find_first_unlabeled(self, annotator_name):
        """
        Finds the index of the first record in the list that has not been rated by this annotator.
        
        Args:
            annotator_name: String name identifying the annotator.
            
        Returns:
            int: Zero-based record index, or 0 if all have been rated or name is blank.
        """
        # Default to index 0 if the annotator name field is empty or no records are loaded
        if not annotator_name or not self.kappa_records:
            return 0

        # Sanitize the input name to form the correct reviewer column prefix
        sanitized = sanitize_name(annotator_name)
        label_col = f"{sanitized}_label"

        # Search rows sequentially for a blank entry in this annotator's label column
        for i, record in enumerate(self.kappa_records):
            value = (record.get(label_col) or "").strip()
            # The first empty string value represents the first unrated record location
            if not value:
                return i

        # Fallback to starting index 0 if the annotator has completed all records
        return 0

    def _display_kappa_record(self, index):
        """
        Populates UI display fields with data from a specific record in Re-label mode.
        
        Loads article headline and body text into read-only display fields, refreshes image
        and video media previews, and checks if the active annotator has already rated this
        item. If a rating is present, pre-loads the label and sub-category inputs and shows 
        the completed badge.
        
        Args:
            index: Zero-based integer index of the record inside kappa_records.
        """
        # Bounds check: do nothing if index is out of range or list is empty
        if not self.kappa_records or index < 0 or index >= len(self.kappa_records):
            return

        # Fetch the active record dictionary from the Kappa list
        record = self.kappa_records[index]
        total = len(self.kappa_records)

        # Update the index counter entry text field
        self.record_index_entry.configure(state="normal")
        self.record_index_entry.delete(0, "end")
        self.record_index_entry.insert(0, str(index + 1))
        self.record_total_label.configure(text=f"of {total}")
        
        # Disable navigation buttons at the boundaries of the list to prevent out-of-bounds errors
        self.prev_btn.configure(state="normal" if index > 0 else "disabled")
        self.next_btn.configure(state="normal" if index < total - 1 else "disabled")

        # Clear the label selector dropdown inputs
        self.label_var.set("")
        self._update_label_toggles()
        self.multi_cat_frame.pack_forget()
        self.multi_cat_var.set("")

        # Temporarily enable heading text box to insert content, then set to read-only
        self.heading_entry.configure(state="normal")
        self.heading_entry.delete("1.0", "end")
        heading = record.get("heading") or ""
        if heading:
            self.heading_entry.insert("1.0", heading)
        self.heading_entry.configure(state="disabled")
        self._update_heading_search_visibility()

        # Temporarily enable news text box to insert content, then set to read-only
        self.text_box.configure(state="normal")
        self.text_box.delete("1.0", "end")
        text = record.get("text") or ""
        if text:
            self.text_box.insert("1.0", text)
        self.text_box.configure(state="disabled")

        # Reset media lists and missing asset references
        self.image_list.clear()
        self.video_path = None
        self.missing_media = []

        # Load and verify the attached video path if registered
        video_path_str = record.get("video_path") or ""
        if video_path_str:
            full_vid_path = SCRIPT_DIR / video_path_str
            if full_vid_path.exists():
                self.video_path = full_vid_path
            else:
                # Keep track of missing file references to notify the user
                self.missing_media.append(("video", video_path_str))

        # Parse and verify semicolon-delimited image paths
        image_paths = record.get("image_path") or ""
        if image_paths:
            for rel_path in image_paths.split(";"):
                rel_path = rel_path.strip()
                if rel_path:
                    full_path = SCRIPT_DIR / rel_path
                    if full_path.exists():
                        # Store verified path with a None placeholder for the PIL Image object
                        self.image_list.append((full_path, None))
                    else:
                        # Keep track of missing file references to notify the user
                        self.missing_media.append(("image", rel_path))
                        
        # Render the image previews and trigger placeholder graphics for missing files
        self._refresh_previews()

        # Check if the active annotator has already rated this item
        annotator = self.annotator_entry.get().strip()
        is_reviewed = False
        if annotator:
            sanitized = sanitize_name(annotator)
            label_col = f"{sanitized}_label"
            multi_col = f"{sanitized}_multi_category"

            existing_label = (record.get(label_col) or "").strip()
            existing_multi = (record.get(multi_col) or "").strip()

            # Pre-load the label and sub-category inputs if a rating is present
            if existing_label:
                is_reviewed = True
                self.label_var.set(existing_label)
                self._on_label_change()
                if existing_label == "Fake" and existing_multi in MULTI_CATEGORIES:
                    self.multi_cat_var.set(existing_multi)
                
        # Draw the visual completed badge if the record has been reviewed by the active user
        if is_reviewed:
            if self.reviewed_badge_img:
                self.done_label.configure(image=self.reviewed_badge_img, text="")
            else:
                self.done_label.configure(image=None, text="ALREADY REVIEWED", font=ctk.CTkFont(size=18, weight="bold"), text_color="#2ecc71")
            # Show the indicator frame
            self.done_indicator_frame.pack(side="bottom", expand=True, fill="both", padx=12, pady=(10, 20))
        else:
            self.done_label.configure(image=None, text="")
            # Hide the indicator frame completely if not reviewed
            self.done_indicator_frame.pack_forget()

        # Recalculate kappa rating stats
        self._update_kappa_stats()

    def _save_kappa_decision(self, auto_advance=True):
        """
        Saves the rating decision for the current record.
        
        Writes the ratings to `{annotator_name}_label` and `{annotator_name}_multi_category`
        columns inside `relabeling_for_kappa.csv`. Automatically adds columns to the header if new.
        
        Args:
            auto_advance: If True, moves to the next record in the queue after a successful save.
            
        Returns:
            bool: True if decision saved successfully, False if validation failed.
        """
        # Abort if no kappa records are loaded in memory
        if not self.kappa_records:
            return False

        # Gather inputs from workspace widgets
        annotator = self.annotator_entry.get().strip()
        label = self.label_var.get()
        multi_cat = self.multi_cat_var.get()

        # Validate entries
        errors = []
        if not annotator:
            errors.append("Annotator name is required.")
        if not label:
            errors.append("Label (Fake/Real) must be selected.")
        if label == "Fake" and not multi_cat:
            errors.append("Fake News Type (Misinformation/Satire/Clickbait) must be selected.")

        # Display errors window if validation checks failed
        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors))
            return False

        # Set multi-category value to Real if the authenticity label is set to Real
        if label == "Real":
            multi_cat = "Real"

        # Cache active username in config persistence file
        save_config(annotator)

        # Sanitize name to build dynamic column headers
        sanitized = sanitize_name(annotator)
        label_col = f"{sanitized}_label"
        multi_col = f"{sanitized}_multi_category"

        # Add new column headers to list if this is the first item reviewed by this annotator
        if label_col not in self.kappa_csv_columns:
            self.kappa_csv_columns.append(label_col)
        if multi_col not in self.kappa_csv_columns:
            self.kappa_csv_columns.append(multi_col)

        # Update record row in memory
        record = self.kappa_records[self.current_kappa_index]
        record[label_col] = label
        record[multi_col] = multi_cat

        # Commit memory updates to disk file
        try:
            self._rewrite_kappa_csv()
        except Exception as e:
            messagebox.showerror(
                "Save Error",
                f"Failed to save decision. Please make sure the kappa CSV "
                f"is not open in another program.\n\nError: {e}"
            )
            return False

        # Refresh stats bar metrics
        self._update_kappa_stats()
        
        # Display completed rating indicator badge
        if self.reviewed_badge_img:
            self.done_label.configure(image=self.reviewed_badge_img, text="")
        else:
            self.done_label.configure(image=None, text="ALREADY REVIEWED", font=ctk.CTkFont(size=18, weight="bold"), text_color="#2ecc71")

        # Repack the indicator frame to refresh visuals
        if not auto_advance:
            self.done_indicator_frame.pack(side="bottom", expand=True, fill="both", padx=12, pady=(10, 20))

        # Handle auto advance navigation transitions
        if auto_advance:
            if self.current_kappa_index < len(self.kappa_records) - 1:
                self.current_kappa_index += 1
                self._display_kappa_record(self.current_kappa_index)
            else:
                # Notify user when the end of the reliability review queue is reached
                # Trigger a popup message informing the user that they have successfully annotated 
                # every sample in the kappa queue. This ensures clear closure for the rating session.
                messagebox.showinfo("Done",
                    "All items have been labeled!\n"
                    "You can navigate back to review your decisions.")
                    
        # Return True to indicate that the record saving operation was completed successfully
        return True

    def _rewrite_kappa_csv(self):
        """
        Rewrites the kappa CSV file to commit updated decisions from memory to disk.
        
        This method aggregates the dynamic annotator columns (ratings) registered during
        the session across all loaded records. It constructs an ordered list of headers,
        ensuring that standard dataset fields remain first in the column order, followed
        by individual reviewer rating columns sorted alphabetically. Finally, it uses
        csv.DictWriter to safely overwrite the target CSV file with the updated records.
        """
        # Collect all existing columns currently present across any of the kappa record dicts
        all_cols = set(self.kappa_csv_columns)
        for record in self.kappa_records:
            all_cols.update(record.keys())

        # Segregate the columns to maintain a clean layout: standard fields are placed first,
        # and extra reviewer annotations are grouped and sorted alphabetically at the end.
        base_cols = [c for c in CSV_COLUMNS if c in all_cols]
        extra_cols = sorted([c for c in all_cols if c not in CSV_COLUMNS])
        ordered_cols = base_cols + extra_cols

        # Update the application's column cache with the finalized sequence
        self.kappa_csv_columns = ordered_cols

        # Open the target reliability CSV file with write access and UTF-8 encoding
        with open(KAPPA_CSV_PATH, "w", newline="", encoding="utf-8") as f:
            # Instantiate a DictWriter mapper configuration that ignores extraneous keys
            writer = csv.DictWriter(f, fieldnames=ordered_cols, extrasaction="ignore")
            
            # Write the column headers as the first line of the file
            writer.writeheader()
            
            # Iterate through the in-memory records and write each row to the file
            for record in self.kappa_records:
                row = {col: record.get(col, "") for col in ordered_cols}
                writer.writerow(row)

    def _update_kappa_stats(self):
        """
        Calculates and updates the stats panel specifically for the Re-label workspace.
        
        To prevent annotator bias during blind reliability checks, this method suppresses
        the distribution counts of Fake/Real labels and topic categories. Instead, it computes:
        - The total number of items loaded in the Kappa agreement queue.
        - The number of records already rated by the current active reviewer.
        - The number of pending records remaining for the active reviewer.
        It then clears existing stats badges and renders new cards for these metrics.
        """
        # Remove any existing stat widgets inside the container frames to prevent layout overlap
        for widget in self.stats_frame.winfo_children():
            widget.destroy()
        for widget in self.category_stats_frame.winfo_children():
            widget.destroy()

        # Retrieve the current status bounds
        total = len(self.kappa_records)
        annotator = self.annotator_entry.get().strip()

        # If a valid annotator name has been entered, count completed labels for that reviewer
        if annotator:
            sanitized = sanitize_name(annotator)
            label_col = f"{sanitized}_label"
            labeled = sum(1 for r in self.kappa_records
                          if (r.get(label_col) or "").strip())
            remaining = total - labeled
        else:
            # Revert to defaults if the annotator entry field is blank
            labeled = 0
            remaining = total

        # Render modern styled badges for total, completed, and pending records
        self._create_stat_badge(self.stats_frame, "Total Items", total, "#3498db")
        self._create_stat_badge(self.stats_frame, "Labeled", labeled, "#2ecc71")
        self._create_stat_badge(self.stats_frame, "Remaining", remaining, "#e67e22")

        # Request tkinter to recalculate and refresh geometry containers
        self.stats_frame.update_idletasks()
        self.category_stats_frame.update_idletasks()
        
        # Trigger the flow layout arrangement logic on the frames
        self.stats_frame._arrange()
        self.category_stats_frame._arrange()

    def _check_unsaved_kappa_changes(self):
        """
        Verifies if there are unsaved rating decisions on the active Kappa record.
        
        This method compares the current selection values in the dropdown widgets (such
        as Label and Fake News Type) against the committed values stored in the record dict.
        If a mismatch is detected, it raises a confirmation popup dialog allowing the user
        to save changes, discard them, or cancel the navigation action entirely.
        
        Returns:
            bool: True if it is safe to proceed with navigation (changes saved or discarded),
                  False if the user chose to cancel the navigation.
        """
        # If no kappa records are loaded or the index is invalid, no unsaved work exists
        if not self.kappa_records or self.current_kappa_index < 0:
            return True

        # Fetch the active record dictionary and current annotator name
        record = self.kappa_records[self.current_kappa_index]
        annotator = self.annotator_entry.get().strip()

        # If no annotator name has been specified, no editing column can be mapped
        if not annotator:
            return True

        # Map username to its corresponding rating column fields
        sanitized = sanitize_name(annotator)
        label_col = f"{sanitized}_label"
        multi_col = f"{sanitized}_multi_category"

        # Read the current selection states from the UI widgets
        current_label = self.label_var.get()
        current_multi = self.multi_cat_var.get() if current_label == "Fake" else ("Real" if current_label == "Real" else "")

        # Read the previously saved states from the in-memory record dict
        saved_label = (record.get(label_col) or "").strip()
        saved_multi = (record.get(multi_col) or "").strip()
        if saved_label == "Real":
            saved_multi = "Real"

        # Check for discrepancies between the UI widgets and the cached memory record
        changed = False
        if current_label != saved_label:
            changed = True
        elif current_label == "Fake" and current_multi != saved_multi:
            changed = True

        # If no differences are found, it is safe to navigate away
        if not changed:
            return True

        # Prompt the user with a standard confirmation dialog
        response = messagebox.askyesnocancel(
            "Unsaved Changes",
            "You have unsaved changes in this record.\n\n"
            "Do you want to save them before moving?"
        )

        # Handle user choice: True = Save, False = Discard, None = Cancel
        if response is True:
            # Attempt to write choices to memory and disk
            save_ok = self._save_kappa_decision(auto_advance=False)
            if not save_ok:
                # If validation fails, ask the user if they wish to discard changes to proceed
                discard = messagebox.askyesno(
                    "Save Failed",
                    "Could not save due to validation errors.\n\n"
                    "Do you want to discard your changes and continue?"
                )
                return discard
            return True
        elif response is False:
            # User explicitly chose to discard changes
            return True
        else:
            # User clicked Cancel, aborting navigation
            return False

    def _kappa_next_record(self):
        """
        Navigates forward to the next record in the Kappa reliability review queue.
        
        Performs dirty verification checks on the active item before moving. If verification
        passes and another record exists, increments the index counter and loads the new entry.
        """
        # Verify that we are not already at the final record in the list
        if self.current_kappa_index < len(self.kappa_records) - 1:
            # Run safety checks for unsaved changes before moving
            if not self._check_unsaved_kappa_changes():
                return
            
            # Increment index pointer and refresh UI field content
            self.current_kappa_index += 1
            self._display_kappa_record(self.current_kappa_index)

    def _kappa_prev_record(self):
        """
        Navigates backward to the previous record in the Kappa reliability review queue.
        
        Performs dirty verification checks on the active item before moving. If verification
        passes and another record exists, decrements the index counter and loads the new entry.
        """
        # Verify that we are not at the first record in the list
        if self.current_kappa_index > 0:
            # Run safety checks for unsaved changes before moving
            if not self._check_unsaved_kappa_changes():
                return
            
            # Decrement index pointer and refresh UI field content
            self.current_kappa_index -= 1
            self._display_kappa_record(self.current_kappa_index)

    def _kappa_jump_to_record(self, event=None):
        """
        Jumps directly to a user-entered record index in the reliability review list.
        
        Triggered by pressing Enter on the index input widget. Validates that the input is a
        valid integer within list boundaries, performs dirty checks, and displays the record.
        """
        try:
            # Retrieve and parse the numeric value entered in the text field
            val = int(self.record_index_entry.get().strip())
            idx = val - 1
            
            # Validate that the index is within the boundaries of loaded kappa records
            if 0 <= idx < len(self.kappa_records):
                if self.current_kappa_index != idx:
                    # Verify unsaved changes on the active record before leaping
                    if not self._check_unsaved_kappa_changes():
                        # Revert the index entry back to the active record number if cancelled
                        self.record_index_entry.delete(0, "end")
                        self.record_index_entry.insert(0, str(self.current_kappa_index + 1))
                        self.focus_set()
                        return
                    
                    # Update index and render the new record
                    self.current_kappa_index = idx
                    self._display_kappa_record(self.current_kappa_index)
                
                # Re-focus the main window
                self.focus_set()
            else:
                # Revert text input and show a warning popup if the value is out of range
                self.record_index_entry.delete(0, "end")
                self.record_index_entry.insert(0, str(self.current_kappa_index + 1))
                messagebox.showwarning("Invalid Record",
                    f"Please enter a number between 1 and {len(self.kappa_records)}.")
        except ValueError:
            # Revert text input to the active record number if parsing fails
            self.record_index_entry.delete(0, "end")
            self.record_index_entry.insert(0, str(self.current_kappa_index + 1))

    # ---------------------------------------------------------
    # GLOBAL METRICS SYNC LOGIC
    # ---------------------------------------------------------

    def _on_global_toggle_change(self):
        # Refresh the stats view
        self._update_stats()

    def _compute_metrics_for_subset(self, records):
        total_items = 0
        total_images = 0
        total_videos = 0
        text_only = 0
        image_only = 0
        video_only = 0
        text_image = 0
        text_video = 0
        image_video = 0
        text_image_video = 0

        for r in records:
            total_items += 1
            ip = (r.get("image_path") or "").strip()
            img_list = [p for p in ip.split(";") if p.strip()]
            total_images += len(img_list)
            
            vp = (r.get("video_path") or "").strip()
            has_video = bool(vp)
            if has_video:
                total_videos += 1
                
            t_content = (r.get("text") or "").strip()
            h_content = (r.get("heading") or "").strip()
            has_text = (len(t_content) + len(h_content)) >= MIN_TEXT_LENGTH
            
            has_image = bool(img_list)
            
            if has_text and not has_image and not has_video:
                text_only += 1
            elif not has_text and has_image and not has_video:
                image_only += 1
            elif not has_text and not has_image and has_video:
                video_only += 1
            elif has_text and has_image and not has_video:
                text_image += 1
            elif has_text and not has_image and has_video:
                text_video += 1
            elif not has_text and has_image and has_video:
                image_video += 1
            elif has_text and has_image and has_video:
                text_image_video += 1

        return {
            "Total Items": total_items,
            "Total Images": total_images,
            "Total Videos": total_videos,
            "Text Only": text_only,
            "Image Only": image_only,
            "Video Only": video_only,
            "Text + Image": text_image,
            "Text + Video": text_video,
            "Image + Video": image_video,
            "Text + Image + Video": text_image_video
        }

    def _empty_detailed_stats(self):
        return {
            col_name: {metric_name: 0 for metric_name in DETAILED_STATS_METRICS}
            for col_name in DETAILED_STATS_COLUMNS
        }

    def _compute_detailed_stats_for_records(self, records):
        subsets = {
            "Total": records,
            "Real": [r for r in records if (r.get("label") or "").strip() == "Real"],
            "Fake": [r for r in records if (r.get("label") or "").strip() == "Fake"],
            "Misinfo": [r for r in records if (r.get("label") or "").strip() == "Fake" and (r.get("multi_category") or "").strip() == "Misinformation"],
            "Satire": [r for r in records if (r.get("label") or "").strip() == "Fake" and (r.get("multi_category") or "").strip() == "Satire"],
            "Clickbait": [r for r in records if (r.get("label") or "").strip() == "Fake" and (r.get("multi_category") or "").strip() == "Clickbait"]
        }
        return {
            col_name: self._compute_metrics_for_subset(subset)
            for col_name, subset in subsets.items()
        }

    def _merge_detailed_stats(self, target, source):
        if not isinstance(source, dict):
            return False

        recognized = False
        for col_name in DETAILED_STATS_COLUMNS:
            subset_metrics = source.get(col_name)
            if not isinstance(subset_metrics, dict):
                continue
            recognized = True
            for metric_name in DETAILED_STATS_METRICS:
                try:
                    target[col_name][metric_name] += int(subset_metrics.get(metric_name, 0) or 0)
                except (TypeError, ValueError):
                    continue
        return recognized

    def _redraw_active_detailed_popup(self):
        popup = getattr(self, "active_detailed_popup", None)
        if popup is None:
            return
        try:
            if popup.winfo_exists() and hasattr(popup, "redraw_cmd"):
                popup.redraw_cmd()
        except tk.TclError:
            pass

    def _queue_detailed_stats_redraw(self):
        try:
            self.after(0, self._redraw_active_detailed_popup)
        except tk.TclError:
            pass

    def _calculate_grouped_local_stats(self):
        """
        Reads dataset.csv and groups detailed metrics by annotator name.
        """
        grouped_records = {}
        if not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0:
            return {}
        
        with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ann = (row.get("annotator") or "").strip() or "Unknown"
                if ann not in grouped_records:
                    grouped_records[ann] = []
                grouped_records[ann].append(row)
                
        return {
            ann: self._compute_detailed_stats_for_records(records)
            for ann, records in grouped_records.items()
        }

    def _sync_global_metrics_loop(self):
        """
        Runs every 5 minutes in a background thread to sync metrics.
        """
        threading.Thread(target=self._sync_global_metrics_worker, daemon=True).start()
        # Schedule the next run in 5 minutes (300,000 ms)
        self.after(300000, self._sync_global_metrics_loop)

    def _sync_global_metrics_worker(self):
        if not self._sync_lock.acquire(blocking=False):
            return

        sync_succeeded = False
        try:
            cfg = get_full_config()
            gist_id = cfg.get("gist_id")
            github_token = cfg.get("github_token")

            if not gist_id or not github_token:
                self.is_global_syncing = False
                self._queue_detailed_stats_redraw()
                return

            self.is_global_syncing = True
            self._queue_detailed_stats_redraw()

            machine_id = get_machine_id()
            current_local_stats = self._calculate_grouped_local_stats()
            needs_upload = self.last_uploaded_counts != current_local_stats

            headers = {
                "Authorization": f"token {github_token}",
                "Accept": "application/vnd.github.v3+json"
            }

            # 1. Fetch current Gist
            resp = requests.get(f"https://api.github.com/gists/{gist_id}", headers=headers, timeout=10)
            if resp.status_code != 200:
                print(f"[SYNC ERROR] Failed to fetch Gist: {resp.status_code}")
                return
                
            gist_data = resp.json()
            files = gist_data.get("files", {})
            if "metrics.json" not in files:
                global_data = {}
            else:
                try:
                    global_data = json.loads(files["metrics.json"]["content"])
                except Exception:
                    global_data = {}

            latest_cfg = get_full_config()
            if (latest_cfg.get("gist_id") != gist_id or
                    latest_cfg.get("github_token") != github_token):
                return
            
            # 2. Update local tracking variable for UI rendering
            self.global_metrics_data = dict(global_data)
            sync_succeeded = True
            
            if needs_upload:
                # 3. Merge our local stats into the global data
                global_data[machine_id] = current_local_stats
                
                # 4. Upload back to Gist
                payload = {
                    "files": {
                        "metrics.json": {
                            "content": json.dumps(global_data, indent=2)
                        }
                    }
                }
                patch_resp = requests.patch(f"https://api.github.com/gists/{gist_id}", json=payload, headers=headers, timeout=10)
                if patch_resp.status_code == 200:
                    self.last_uploaded_counts = current_local_stats
                    # Update local tracking again
                    self.global_metrics_data = dict(global_data)
                else:
                    print(f"[SYNC ERROR] Failed to update Gist: {patch_resp.status_code}")
                
        except Exception as e:
            print(f"[SYNC ERROR] Exception during sync: {e}")
        finally:
            self.is_global_syncing = False
            if sync_succeeded:
                self.last_global_sync_time = time.time()
            self._queue_detailed_stats_redraw()
            self._sync_lock.release()

    def _show_team_sync_popup(self):
        """
        Popup for configuring the GitHub Gist token.
        """
        popup = ctk.CTkToplevel(self)
        popup.title("Team Sync Setup")
        popup.configure(fg_color="#1a1a2e")
        if hasattr(self, 'active_detailed_popup') and self.active_detailed_popup.winfo_exists():
            popup.transient(self.active_detailed_popup)
        else:
            popup.transient(self)
        popup.grab_set()
        popup.resizable(False, False)
        
        pw, ph = 450, 380
        popup.geometry(f"{pw}x{ph}")
        popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (pw // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (ph // 2)
        popup.geometry(f"+{x}+{y}")

        ctk.CTkLabel(popup, text="🌐 Team Global Metrics Sync", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 10))
        ctk.CTkLabel(popup, text="Enter your Team's GitHub Gist ID and Access Token to sync\nyour metrics globally and view your teammates' progress.",
                     text_color="#aaa", font=ctk.CTkFont(size=12)).pack(pady=(0, 15))

        cfg = get_full_config()
        
        form_frame = ctk.CTkFrame(popup, fg_color="transparent")
        form_frame.pack(fill="x", padx=30, pady=10)
        
        ctk.CTkLabel(form_frame, text="GitHub Gist ID:", anchor="w").pack(fill="x")
        gist_entry = ctk.CTkEntry(form_frame, height=35)
        gist_entry.pack(fill="x", pady=(2, 12))
        if "gist_id" in cfg:
            gist_entry.insert(0, cfg["gist_id"])
            
        ctk.CTkLabel(form_frame, text="GitHub Access Token (PAT):", anchor="w").pack(fill="x")
        token_entry = ctk.CTkEntry(form_frame, height=35, show="*")
        token_entry.pack(fill="x", pady=(2, 5))
        if "github_token" in cfg:
            token_entry.insert(0, cfg["github_token"])
            
        error_label = ctk.CTkLabel(popup, text="", text_color="#e74c3c")
        error_label.pack(pady=5)
        
        btn_frame = ctk.CTkFrame(popup, fg_color="transparent")
        btn_frame.pack(fill="x", padx=30, pady=10)
        
        def save_creds():
            g_id = gist_entry.get().strip()
            tkn = token_entry.get().strip()
            if not g_id or not tkn:
                error_label.configure(text="Please fill in both fields.")
                return
                
            error_label.configure(text="Validating...", text_color="#f39c12")
            popup.update()
            
            # Validate with GitHub
            headers = {"Authorization": f"token {tkn}", "Accept": "application/vnd.github.v3+json"}
            try:
                resp = requests.get(f"https://api.github.com/gists/{g_id}", headers=headers, timeout=10)
                if resp.status_code == 200:
                    cfg["gist_id"] = g_id
                    cfg["github_token"] = tkn
                    save_full_config(cfg)
                    error_label.configure(text="Success! Sync enabled.", text_color="#2ecc71")
                    # Force an immediate sync
                    threading.Thread(target=self._sync_global_metrics_worker, daemon=True).start()
                    popup.after(1500, popup.destroy)
                else:
                    error_label.configure(text=f"Validation Failed (Code {resp.status_code}). Check your credentials.", text_color="#e74c3c")
            except Exception as e:
                error_label.configure(text=f"Network Error: {e}", text_color="#e74c3c")
                
        def delete_creds():
            g_id = cfg.get("gist_id")
            tkn = cfg.get("github_token")
            machine_uuid = cfg.get("machine_id")

            if g_id and tkn and machine_uuid:
                error_label.configure(text="Removing data from cloud...", text_color="#f39c12")
                popup.update()
                try:
                    headers = {"Authorization": f"token {tkn}", "Accept": "application/vnd.github.v3+json"}
                    resp = requests.get(f"https://api.github.com/gists/{g_id}", headers=headers, timeout=10)
                    if resp.status_code == 200:
                        gist_data = resp.json()
                        metrics_file = gist_data.get("files", {}).get("metrics.json")
                        if metrics_file:
                            try:
                                cloud_data = json.loads(metrics_file.get("content", "{}"))
                                if machine_uuid in cloud_data:
                                    del cloud_data[machine_uuid]
                                    patch_data = {"files": {"metrics.json": {"content": json.dumps(cloud_data, indent=2)}}}
                                    requests.patch(f"https://api.github.com/gists/{g_id}", headers=headers, json=patch_data, timeout=10)
                            except Exception:
                                pass
                except Exception:
                    pass

            if "gist_id" in cfg: del cfg["gist_id"]
            if "github_token" in cfg: del cfg["github_token"]
            save_full_config(cfg)
            self.global_metrics_data = {}
            self.last_global_sync_time = None
            self.last_uploaded_counts = {}
            self.global_metrics_enabled.set(False)
            
            self._queue_detailed_stats_redraw()
                
            popup.destroy()
        save_btn = ctk.CTkButton(btn_frame, text="💾 Save & Sync", command=save_creds, height=35, fg_color="#2ecc71", hover_color="#27ae60", text_color="black")
        save_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        del_btn = ctk.CTkButton(btn_frame, text="Disconnect", command=delete_creds, height=35, fg_color="#e74c3c", hover_color="#c0392b")
        del_btn.pack(side="left", fill="x", expand=True)

# Launch the Tkinter application main loop when running this script directly
if __name__ == "__main__":
    # Instantiate the main application window object
    app = AnnotatorTool()
    
    # Run the main event handling loop to process user interactions and draw widgets
    app.mainloop()
