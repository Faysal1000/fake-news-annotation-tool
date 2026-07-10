"""
Dataset aggregation and kappa sample generation.

Provides functionality to merge multiple annotator datasets and generate
balanced random samples according to custom label quotas.
"""

import os
import csv
import json
import shutil
import random
from pathlib import Path
from constants import CSV_COLUMNS

def aggregate_datasets(annotators_dir, output_csv_path, output_images_dir, output_videos_dir):
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
    all_non_dups = set()
    total_images_copied = 0
    total_videos_copied = 0

    for annotator in sorted(annotators):
        annotator_dir = os.path.join(annotators_dir, annotator)
        csv_path = os.path.join(annotator_dir, "dataset.csv")
        images_dir = os.path.join(annotator_dir, "images")
        videos_dir = os.path.join(annotator_dir, "videos")
        non_dups_path = os.path.join(annotator_dir, "non_duplicates.json")

        if os.path.isfile(non_dups_path):
            try:
                with open(non_dups_path, "r", encoding="utf-8") as f:
                    all_non_dups.update(json.load(f))
            except Exception as e:
                print(f"Error reading {non_dups_path}: {e}")

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
            
    if all_non_dups:
        output_non_dups_path = os.path.join(os.path.dirname(output_csv_path), "non_duplicates.json")
        try:
            with open(output_non_dups_path, "w", encoding="utf-8") as f:
                json.dump(list(all_non_dups), f)
        except Exception as e:
            print(f"Error saving aggregated non_duplicates.json: {e}")

    return (
        f"Aggregation complete!\n\n"
        f"Annotators found: {len(annotators)} ({', '.join(sorted(annotators))})\n"
        f"Total rows merged: {len(all_rows)}\n"
        f"Images copied: {total_images_copied}\n"
        f"Videos copied: {total_videos_copied}\n\n"
        f"Output CSV: {output_csv_path}"
    )

def _copy_sample_media(sample_rows, source_base, output_dir):
    """
    Copy the image/video files referenced by sample_rows from source_base into
    output_dir, preserving the relative "images/..." and "videos/..." layout.

    source_base: Path the CSV's media paths are relative to (the dataset folder).
    output_dir:  Destination folder for the copied media.

    Returns (images_copied, videos_copied, missing) where missing is a list of
    relative paths that were referenced but not found under source_base.
    """
    images_copied = 0
    videos_copied = 0
    missing = []
    seen = set()

    def _copy_one(rel_raw, is_image):
        nonlocal images_copied, videos_copied
        rel = rel_raw.strip().replace("\\", "/")
        if not rel or rel in seen:
            return
        seen.add(rel)
        src = source_base / rel
        if src.is_file():
            dst = output_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            if is_image:
                images_copied += 1
            else:
                videos_copied += 1
        else:
            missing.append(rel)

    for row in sample_rows:
        for rel in (row.get("image_path") or "").split(";"):
            if rel.strip():
                _copy_one(rel, True)
        vid = (row.get("video_path") or "").strip()
        if vid:
            _copy_one(vid, False)

    return images_copied, videos_copied, missing

def generate_kappa_sample(input_csv_path, n,
                           output_folder=None,
                           real_pct=50.0, misinfo_pct=33.33,
                           satire_pct=33.33, clickbait_pct=33.34):
    """
    Generate a balanced random sample from the master dataset for kappa testing.
    Distribution is configurable via percentage parameters.
    real_pct: percentage of total sample that should be Real.
    misinfo_pct/satire_pct/clickbait_pct: percentage of the Fake portion for each sub-category.

    Creates a self-contained, portable output folder containing:
      - relabeling_for_kappa.csv  (the sample CSV)
      - images/                   (only images referenced by the sample)
      - videos/                   (only videos referenced by the sample)

    The whole folder can be zipped and sent to a teammate for re-labeling.
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

    clean_rows = [{col: row.get(col, "") for col in CSV_COLUMNS} for row in result]

    # Build the self-contained output folder
    output_path = Path(output_folder) if output_folder else input_path.parent / "kappa_sample"
    output_path.mkdir(parents=True, exist_ok=True)

    # Clear any existing images/ and videos/ so stale files from a previous
    # run don't leak into the new self-contained package.
    for media_sub in ("images", "videos"):
        sub = output_path / media_sub
        if sub.is_dir():
            shutil.rmtree(sub)
        sub.mkdir(parents=True, exist_ok=True)

    # Write the sample CSV into the output folder
    csv_filename = "relabeling_for_kappa.csv"
    bundle_csv = output_path / csv_filename
    with open(bundle_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for clean_row in clean_rows:
            writer.writerow(clean_row)

    # Copy only the media referenced by the sampled rows into the output folder.
    images_copied, videos_copied, missing = _copy_sample_media(
        clean_rows, input_path.parent, output_path)

    total = len(result)
    fake_pct_used = round(100.0 - real_pct, 2)

    missing_note = ""
    if missing:
        preview = "\n".join(f"    {p}" for p in missing[:5])
        more = f"\n    ... ({len(missing)} total)" if len(missing) > 5 else ""
        missing_note = (
            f"\n\n⚠ {len(missing)} referenced media file(s) were not found "
            f"and could not be copied:\n{preview}{more}"
        )

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
        f"Output folder (send this whole folder to your teammate):\n"
        f"  {output_path}\n"
        f"    {csv_filename}\n"
        f"    images/  ({images_copied} file(s))\n"
        f"    videos/  ({videos_copied} file(s))"
        f"{missing_note}"
    )
