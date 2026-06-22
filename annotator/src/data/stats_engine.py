"""
Count functions for entries, images, videos, and labels.
"""

import csv
from app_paths import IMAGES_DIR, VIDEOS_DIR, CSV_PATH
from constants import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS

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
