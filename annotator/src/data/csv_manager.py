"""
CSV schema migration, directory generation, and unique UUID helper.
"""

import csv
import uuid
from app_paths import IMAGES_DIR, VIDEOS_DIR, CSV_PATH
from constants import CSV_COLUMNS

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
