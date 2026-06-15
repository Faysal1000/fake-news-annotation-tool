#!/usr/bin/env python3
"""
Generate Balanced Sample for Inter-Rater Reliability (Kappa) Testing


This script takes the master dataset.csv and generates a balanced random
sample CSV (`relabeling_for_kappa.csv`) with N items for inter-rater
reliability testing (Cohen's Kappa / Fleiss' Kappa).

Balancing Strategy:
  - 50% Real, 50% Fake
  - Within Fake: equal split across Misinformation, Satire, Clickbait
    (each ~16.7% of total N)
  - If a category has fewer items than its quota, all available items
    are used and the shortfall is redistributed proportionally.
  - Items are selected randomly within each category.

Usage:
    python generate_kappa_sample.py                          # Interactive (default N=500)
    python generate_kappa_sample.py --n 60                   # Sample 60 items
    python generate_kappa_sample.py --input dataset.csv --n 100 --output kappa_sample.csv

The output CSV reuses the same images/ and videos/ folders — no files are copied.
"""

import csv
import os
import sys
import random
import argparse
from pathlib import Path


# CONSTANTS
SCRIPT_DIR = Path(__file__).parent.resolve()
DEFAULT_INPUT = SCRIPT_DIR / "dataset.csv"
DEFAULT_OUTPUT = SCRIPT_DIR / "relabeling_for_kappa.csv"
DEFAULT_N = 500

# The columns to carry over from the master dataset
CSV_COLUMNS = [
    "id", "heading", "text", "image_path", "video_path", "label",
    "multi_category", "source", "source_category", "category",
    "annotator", "annotation_confidence", "additional_notes", "timestamp"
]

FAKE_SUBCATEGORIES = ["Misinformation", "Satire", "Clickbait"]


# SAMPLING LOGIC
def load_dataset(input_path):
    """Load all rows from the master dataset CSV.
    
    Returns:
        list[dict]: List of row dicts from the CSV.
    """
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    rows = []
    with open(input_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if not rows:
        print(f"Error: No data rows found in {input_path}", file=sys.stderr)
        sys.exit(1)

    return rows


def split_by_category(rows):
    """Split rows into Real and Fake subcategories.
    
    Returns:
        dict: {
            "Real": [rows...],
            "Misinformation": [rows...],
            "Satire": [rows...],
            "Clickbait": [rows...]
        }
    """
    buckets = {
        "Real": [],
        "Misinformation": [],
        "Satire": [],
        "Clickbait": [],
    }

    for row in rows:
        label = (row.get("label") or "").strip()
        multi_cat = (row.get("multi_category") or "").strip()

        if label == "Real":
            buckets["Real"].append(row)
        elif label == "Fake" and multi_cat in FAKE_SUBCATEGORIES:
            buckets[multi_cat].append(row)
        elif label == "Fake":
            # Fake entry without a recognized multi_category — skip or assign
            # We'll skip these since they don't fit the balancing schema
            print(f"  [WARN] Skipping Fake entry with unknown multi_category: "
                  f"'{multi_cat}' (id={row.get('id', '?')})")

    return buckets


def balanced_sample(rows, n):
    """Generate a balanced random sample of N items.
    
    Distribution:
      - 50% Real
      - 50% Fake, equally split among Misinformation, Satire, Clickbait
    
    If a category has fewer items than its quota, all available items are
    taken and the remaining quota is redistributed proportionally among
    categories that still have surplus.
    
    Args:
        rows: All dataset rows.
        n: Total number of items to sample.
    
    Returns:
        list[dict]: The sampled rows (shuffled).
    """
    buckets = split_by_category(rows)

    # Print available counts
    print("\n--- Available items per category ---")
    for cat, items in buckets.items():
        print(f"  {cat}: {len(items)}")
    print()

    # Calculate ideal quotas
    # Real = N/2, each Fake subcategory = N/6
    n_real = n // 2
    n_per_fake_sub = n // 6  # integer division
    # Handle remainder: distribute to Real first, then fake subs
    remainder = n - n_real - (n_per_fake_sub * 3)
    n_real += remainder

    quotas = {
        "Real": n_real,
        "Misinformation": n_per_fake_sub,
        "Satire": n_per_fake_sub,
        "Clickbait": n_per_fake_sub,
    }

    print("--- Target quotas ---")
    for cat, quota in quotas.items():
        print(f"  {cat}: {quota}")
    print()

    # Phase 1: Sample up to quota from each category
    sampled = {}
    shortfall = 0
    categories_with_surplus = []

    for cat, quota in quotas.items():
        available = buckets[cat]
        if len(available) <= quota:
            # Take all available
            sampled[cat] = list(available)
            shortfall += quota - len(available)
            if len(available) < quota:
                print(f"  [INFO] {cat}: only {len(available)} available "
                      f"(needed {quota}), shortfall = {quota - len(available)}")
        else:
            sampled[cat] = random.sample(available, quota)
            categories_with_surplus.append(cat)

    # Phase 2: Redistribute shortfall among categories with surplus
    if shortfall > 0 and categories_with_surplus:
        print(f"\n  Redistributing {shortfall} items among: "
              f"{', '.join(categories_with_surplus)}")
        
        while shortfall > 0 and categories_with_surplus:
            extra_per_cat = max(1, shortfall // len(categories_with_surplus))
            still_have_surplus = []

            for cat in categories_with_surplus:
                already_sampled_ids = {id(r) for r in sampled[cat]}
                remaining = [r for r in buckets[cat]
                             if id(r) not in already_sampled_ids]
                
                can_take = min(extra_per_cat, len(remaining), shortfall)
                if can_take > 0:
                    extra = random.sample(remaining, can_take)
                    sampled[cat].extend(extra)
                    shortfall -= can_take
                
                # Check if this category still has more items
                new_remaining = len(buckets[cat]) - len(sampled[cat])
                if new_remaining > 0:
                    still_have_surplus.append(cat)

            categories_with_surplus = still_have_surplus

    # Combine all sampled items
    result = []
    print("\n--- Actual sampled counts ---")
    for cat in ["Real", "Misinformation", "Satire", "Clickbait"]:
        items = sampled.get(cat, [])
        print(f"  {cat}: {len(items)}")
        result.extend(items)

    # Shuffle to avoid ordering by category
    random.shuffle(result)

    total = len(result)
    print(f"\n  Total sampled: {total} / {n} requested")
    if total < n:
        print(f"  [WARN] Could only sample {total} items (dataset too small "
              f"for requested N={n})")

    return result


def write_sample_csv(sampled_rows, output_path):
    """Write the sampled rows to the output CSV.
    
    Only writes the base dataset columns (no annotator decision columns yet).
    """
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in sampled_rows:
            # Ensure all columns exist in the row
            clean_row = {}
            for col in CSV_COLUMNS:
                clean_row[col] = row.get(col, "")
            writer.writerow(clean_row)

    print(f"\n✅ Sample written to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate a balanced sample from the master dataset "
                    "for inter-rater reliability (kappa) testing."
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        default=None,
        help=f"Path to the master dataset CSV (default: {DEFAULT_INPUT})"
    )
    parser.add_argument(
        "--n",
        type=int,
        default=None,
        help=f"Total number of items to sample (default: {DEFAULT_N})"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help=f"Output CSV path (default: {DEFAULT_OUTPUT})"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility (optional)"
    )

    args = parser.parse_args()

    # Resolve paths with interactive fallback
    if args.input:
        input_path = Path(args.input).resolve()
    else:
        user_input = input(f"Enter input CSV path [{DEFAULT_INPUT}]: ").strip()
        input_path = Path(user_input).resolve() if user_input else DEFAULT_INPUT

    if args.n is not None:
        n = args.n
    else:
        user_n = input(f"Enter number of items to sample [{DEFAULT_N}]: ").strip()
        n = int(user_n) if user_n else DEFAULT_N

    if args.output:
        output_path = Path(args.output).resolve()
    else:
        user_output = input(f"Enter output CSV path [{DEFAULT_OUTPUT}]: ").strip()
        output_path = Path(user_output).resolve() if user_output else DEFAULT_OUTPUT

    if args.seed is not None:
        random.seed(args.seed)

    print(f"\n{'='*60}")
    print(f"  Balanced Kappa Sample Generator")
    print(f"{'='*60}")
    print(f"  Input:  {input_path}")
    print(f"  Output: {output_path}")
    print(f"  N:      {n}")
    if args.seed is not None:
        print(f"  Seed:   {args.seed}")
    print(f"{'='*60}")

    # Load, sample, write
    rows = load_dataset(input_path)
    print(f"\nLoaded {len(rows)} total rows from dataset.")

    sampled = balanced_sample(rows, n)
    write_sample_csv(sampled, output_path)

    print(f"\nDone! You can now open the annotator tool and switch to "
          f"'Re-label' mode to start re-labeling.")


if __name__ == "__main__":
    main()
